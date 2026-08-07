const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("modal contrast and frequency changes are local and latest-wins", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(180_000);
  page.on("pageerror", (error) => console.log("page-error", error.message));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      console.log(`browser-${message.type()}`, message.text());
    }
  });
  page.on("response", async (response) => {
    if (response.status() >= 400 && response.url().includes("_dash-update-component")) {
      console.log("dash-error", response.status(), await response.text());
    }
  });

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-display-perf-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#global-date-selector")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#global-active-selection")).not.toHaveText("", { timeout: 60_000 });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(page.locator("#global-active-selection")).toContainText("2026-04-08", { timeout: 60_000 });

  const matrixResponse = page.waitForResponse(
    (response) => response.url().includes("/modal-data/") && response.status() === 200,
    { timeout: 60_000 },
  );
  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /item-image/, { timeout: 60_000 });
  await firstImage.click();
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });
  const rawMatrixResponse = await matrixResponse;
  const rawMatrixShape = [
    Number(rawMatrixResponse.headers()["x-spectrogram-rows"]),
    Number(rawMatrixResponse.headers()["x-spectrogram-columns"]),
  ];

  await page.locator("#image-modal summary.display-range-summary").click();
  const colorHandle = page.locator('#modal-colorbar-slider [role="slider"]').first();
  const frequencyHandle = page.locator('#modal-yaxis-slider [role="slider"]').first();

  const contrastStarted = Date.now();
  await colorHandle.focus();
  for (let index = 0; index < 6; index += 1) {
    await page.keyboard.press("ArrowRight");
  }
  await expect.poll(
    () => page.locator("#modal-image-graph").evaluate((element) => {
      const graph = element.querySelector(".js-plotly-plot");
      const source = graph && graph.layout && graph.layout.images && graph.layout.images[0].source;
      return source && source.startsWith("blob:");
    }),
    { timeout: 5_000 },
  ).toBe(true);
  const contrastDuration = Date.now() - contrastStarted;

  const frequencyBefore = await page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    return graph.layout.meta.display_y_min_hz;
  });
  const frequencyStarted = Date.now();
  await frequencyHandle.focus();
  for (let index = 0; index < 6; index += 1) {
    await page.keyboard.press("ArrowRight");
  }
  await expect.poll(
    () => page.locator("#modal-image-graph").evaluate((element) => {
      const graph = element.querySelector(".js-plotly-plot");
      return graph.layout.meta.display_y_min_hz;
    }),
    { timeout: 2_000 },
  ).not.toBe(frequencyBefore);
  const frequencyDuration = Date.now() - frequencyStarted;

  // Let Dash finish committing the keyboard-driven slider value before the
  // isolated latest-wins probe below starts its own render sequence.
  await page.waitForTimeout(300);
  const latestWins = await page.locator("#modal-image-graph").evaluate(async (element) => {
    const graph = element.querySelector(".js-plotly-plot");
    const figure = { data: graph.data, layout: graph.layout };
    const update = window.dash_clientside.modalDisplay.updateCommitted;
    const args = (minimum) => [
      "default", "linear",
      null, null, minimum, -10,
      null, null, null, null, null, null,
      null, null, null, null, null, null,
      "verify", figure,
    ];
    const stale = update(...args(-80));
    const latest = update(...args(-65));
    const [staleResult, latestResult] = await Promise.all([stale, latest]);
    return {
      staleCancelled: staleResult === window.dash_clientside.no_update,
      latestMinimum: latestResult.layout.meta.display_color_min,
      latestSource: latestResult.layout.images[0].source,
    };
  });

  const renderedShape = await page.locator("#modal-image-graph").evaluate(async (element) => {
    const graph = element.querySelector(".js-plotly-plot");
    const source = graph.layout.images[0].source;
    const bitmap = await createImageBitmap(await (await fetch(source)).blob());
    const result = {
      source: graph.layout.meta.source_matrix_shape,
      png: [bitmap.height, bitmap.width],
    };
    bitmap.close();
    return result;
  });

  console.log("modal-display-ms", JSON.stringify({ contrastDuration, frequencyDuration }));
  expect(contrastDuration).toBeLessThan(1500);
  expect(frequencyDuration).toBeLessThan(750);
  expect(latestWins.staleCancelled).toBe(true);
  expect(latestWins.latestMinimum).toBe(-65);
  expect(latestWins.latestSource).toMatch(/^blob:/);
  expect(rawMatrixShape).toEqual(renderedShape.source);
  expect(renderedShape.png).toEqual(renderedShape.source);
});
