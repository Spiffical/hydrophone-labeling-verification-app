const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("modal axis scale and frequency controls remain responsive", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(300_000);
  const dashErrors = [];
  page.on("pageerror", (error) => console.log("page-error", error.message));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      console.log(`browser-${message.type()}`, message.text());
    }
  });
  page.on("response", async (response) => {
    if (response.status() >= 400 && response.url().includes("_dash-update-component")) {
      dashErrors.push({ status: response.status(), body: await response.text() });
    }
  });

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-axis-${Date.now()}`, {
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

  const graphState = () => page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    return graph && {
      type: graph.layout.yaxis.type,
      range: graph.layout.yaxis.range,
      minimumHz: graph.layout.meta.display_y_min_hz,
      maximumHz: graph.layout.meta.display_y_max_hz,
    };
  });
  const initial = await graphState();
  expect(initial.type).toBe("linear");
  const frequencyMinimum = page.locator('#modal-yaxis-slider [role="slider"]').first();
  const transitionDurations = {};

  for (const targetScale of ["log", "linear"]) {
    const beforeScale = await graphState();
    const transitionStarted = Date.now();
    await page.locator(`#modal-y-axis-toggle input[value="${targetScale}"]`).check();
    await expect(page.locator("#modal-busy-overlay")).toBeVisible({ timeout: 2_000 });
    await expect
      .poll(graphState, { timeout: 30_000, message: JSON.stringify({ beforeScale, dashErrors }) })
      .toMatchObject({ type: targetScale });
    if (targetScale === "linear") {
      await expect
        .poll(() => page.locator("#modal-image-graph").evaluate((element) => {
          const graph = element.querySelector(".js-plotly-plot");
          const images = graph && graph.layout && graph.layout.images;
          return Array.isArray(images) && images.length > 0 && Boolean(images[0].source);
        }), { timeout: 30_000 })
        .toBe(true);
    }
    await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 30_000 });
    transitionDurations[targetScale] = Date.now() - transitionStarted;

    const beforeFrequency = await graphState();
    await frequencyMinimum.focus();
    for (let index = 0; index < 6; index += 1) {
      await frequencyMinimum.press("ArrowRight");
    }
    await expect
      .poll(graphState, { timeout: 10_000, message: JSON.stringify({ beforeFrequency, dashErrors }) })
      .not.toMatchObject({ minimumHz: beforeFrequency.minimumHz });
    await expect(page.locator("#modal-yaxis-min-input")).not.toHaveValue("", {
      timeout: 10_000,
    });
    await expect
      .poll(async () => {
        const rendered = await graphState();
        const committed = Number(await page.locator("#modal-yaxis-min-input").inputValue());
        return Math.abs(rendered.minimumHz - committed);
      }, { timeout: 10_000 })
      .toBeLessThan(0.001);
  }

  const currentColormap = await page.locator('#modal-colormap-toggle input:checked').inputValue();
  const targetColormap = currentColormap === "default" ? "hydrophone" : "default";
  const colormapStarted = Date.now();
  await page.locator(`#modal-colormap-toggle input[value="${targetColormap}"]`).check();
  await expect(page.locator("#modal-busy-overlay")).toBeVisible({ timeout: 2_000 });
  await expect
    .poll(() => page.locator("#modal-image-graph").evaluate((element) => {
      const graph = element.querySelector(".js-plotly-plot");
      const images = graph && graph.layout && graph.layout.images;
      return Array.isArray(images) && images.length ? images[0].source : "";
    }), { timeout: 30_000 })
    .toContain(`cm=${targetColormap}`);
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 30_000 });
  transitionDurations.colormap = Date.now() - colormapStarted;

  console.log("modal-axis-transition-ms", JSON.stringify(transitionDurations));
  expect(transitionDurations.linear).toBeLessThan(5_000);
  expect(transitionDurations.colormap).toBeLessThan(5_000);
  expect(dashErrors).toEqual([]);
});
