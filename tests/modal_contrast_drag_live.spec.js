const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("linear modal contrast previews update before slider release", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(300_000);
  const dashErrors = [];
  page.on("pageerror", (error) => console.log("page-error", error.message));
  page.on("response", async (response) => {
    if (response.status() >= 400 && response.url().includes("_dash-update-component")) {
      dashErrors.push({ status: response.status(), body: await response.text() });
    }
  });

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-linear-drag-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", {
    timeout: 120_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /item-image/, { timeout: 60_000 });
  await firstImage.click();
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });
  await page.locator("#image-modal summary.display-range-summary").click();
  await expect(page.locator('#modal-y-axis-toggle input[value="linear"]')).toBeChecked();

  const imageSource = () => page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    const images = graph && graph.layout && graph.layout.images;
    return Array.isArray(images) && images.length ? images[0].source : "";
  });
  const renderedContrast = () => page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    const meta = graph && graph.layout && graph.layout.meta;
    return meta ? [meta.display_color_min, meta.display_color_max] : [];
  });
  const initialSource = await imageSource();
  const contrastHandle = page.locator('#modal-colorbar-slider [role="slider"]').first();
  const box = await contrastHandle.boundingBox();
  expect(box).not.toBeNull();

  const started = Date.now();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  try {
    await page.mouse.move(box.x + box.width / 2 + 35, box.y + box.height / 2, { steps: 8 });
    await expect.poll(imageSource, { timeout: 5_000 }).not.toBe(initialSource);
    const firstPreviewSource = await imageSource();
    expect(firstPreviewSource).toMatch(/^blob:/);

    await page.mouse.move(box.x + box.width / 2 + 65, box.y + box.height / 2, { steps: 8 });
    await expect.poll(imageSource, { timeout: 5_000 }).not.toBe(firstPreviewSource);
  } finally {
    await page.mouse.up();
  }
  const previewDuration = Date.now() - started;

  await expect(page.locator("#modal-colorbar-min-input")).not.toHaveValue("", {
    timeout: 10_000,
  });
  const committedContrast = await Promise.all([
    page.locator("#modal-colorbar-min-input").inputValue(),
    page.locator("#modal-colorbar-max-input").inputValue(),
  ]).then((values) => values.map(Number));
  await expect.poll(renderedContrast, { timeout: 5_000 }).toEqual(committedContrast);
  await page.waitForTimeout(750);
  expect(await renderedContrast()).toEqual(committedContrast);
  console.log("modal-linear-contrast-drag-ms", previewDuration);
  expect(previewDuration).toBeLessThan(5_000);
  expect(dashErrors).toEqual([]);
});

test("linear modal contrast remains committed after repeated fast releases", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(300_000);

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-linear-release-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", { timeout: 120_000 });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();
  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /item-image/, { timeout: 60_000 });
  await firstImage.click();
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });
  await page.locator("#image-modal summary.display-range-summary").click();

  const handle = page.locator('#modal-colorbar-slider [role="slider"]').first();
  for (const offset of [30, -18, 42, -12, 36]) {
    const box = await handle.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + offset, box.y + box.height / 2, { steps: 3 });
    await page.mouse.up();
  }

  const sliderContrast = await page.locator(
    '#modal-colorbar-slider [role="slider"]',
  ).evaluateAll((handles) => handles.map((handle) => Number(handle.getAttribute("aria-valuenow"))));
  await expect.poll(async () => Promise.all([
    page.locator("#modal-colorbar-min-input").inputValue(),
    page.locator("#modal-colorbar-max-input").inputValue(),
  ]).then((values) => values.map(Number)), { timeout: 10_000 }).toEqual(sliderContrast);
  const committed = sliderContrast;
  const rendered = () => page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    return [graph.layout.meta.display_color_min, graph.layout.meta.display_color_max];
  });
  await expect.poll(rendered, { timeout: 10_000 }).toEqual(committed);
  await page.waitForTimeout(1_000);
  expect(await rendered()).toEqual(committed);
});
