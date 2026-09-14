const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("modal zoom progressively swaps in a viewport-resolution source crop", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(180_000);

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-zoom-detail-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", { timeout: 60_000 });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();
  await page.locator("#verify-grid img.spectrogram-image").first().click();
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });

  const graph = page.locator("#modal-image-graph");
  const before = await graph.evaluate((element) => {
    const plot = element.querySelector(".js-plotly-plot");
    return {
      source: plot.layout.images[0].source,
      x: plot.layout.xaxis.range,
      y: plot.layout.yaxis.range,
    };
  });
  const started = Date.now();
  await graph.evaluate(async (element) => {
    const plot = element.querySelector(".js-plotly-plot");
    await window.Plotly.relayout(plot, {
      "xaxis.range": [1.0, 2.0],
      "yaxis.range": [1.0, 5.0],
    });
  });
  await expect.poll(() => graph.evaluate((element) => {
    const plot = element.querySelector(".js-plotly-plot");
    return plot.layout.images[0].sizex;
  }), { timeout: 5_000 }).toBeLessThan(before.x[1] - before.x[0]);
  const refined = await graph.evaluate((element) => {
    const plot = element.querySelector(".js-plotly-plot");
    const image = plot.layout.images[0];
    return {
      source: image.source,
      x: plot.layout.xaxis.range,
      y: plot.layout.yaxis.range,
      imageX: image.x,
      imageY: image.y,
      imageWidth: image.sizex,
      imageHeight: image.sizey,
    };
  });
  expect(refined.source).not.toBe(before.source);
  expect(refined.x).toEqual([1.0, 2.0]);
  expect(refined.y).toEqual([1.0, 5.0]);
  expect(refined.imageWidth).toBeLessThan(before.x[1] - before.x[0]);
  expect(refined.imageHeight).toBeLessThan(before.y[1] - before.y[0]);
  expect(Date.now() - started).toBeLessThan(5_000);

  await page.getByRole("button", { name: "Reset axes" }).click();
  await expect.poll(() => graph.evaluate((element) => {
    const plot = element.querySelector(".js-plotly-plot");
    return { x: plot.layout.xaxis.range, y: plot.layout.yaxis.range };
  })).toEqual({ x: before.x, y: before.y });

  await page.locator("#modal-nav-next").click();
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });
  const nextCanonical = await graph.evaluate((element) => {
    const plot = element.querySelector(".js-plotly-plot");
    const meta = plot.layout.meta;
    return {
      x: [meta.x_min, meta.x_max],
      y: [meta.display_y_min_hz / meta.y_to_hz, meta.display_y_max_hz / meta.y_to_hz],
    };
  });
  await graph.evaluate(async (element) => {
    const plot = element.querySelector(".js-plotly-plot");
    await window.Plotly.relayout(plot, {
      "xaxis.range": [1.0, 2.0],
      "yaxis.range": [1.0, 5.0],
    });
  });
  await page.getByRole("button", { name: "Reset axes" }).click();
  await expect.poll(() => graph.evaluate((element) => {
    const plot = element.querySelector(".js-plotly-plot");
    return { x: plot.layout.xaxis.range, y: plot.layout.yaxis.range };
  })).toEqual(nextCanonical);
});
