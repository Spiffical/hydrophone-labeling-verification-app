const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("modal reset restores canonical axes and reopening commits the new recording", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(240_000);

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-reset-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", { timeout: 60_000 });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  const cards = page.locator("#verify-grid img.spectrogram-image");
  await expect(cards.first()).toBeVisible({ timeout: 60_000 });
  await cards.first().click();
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });

  const canonical = await page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    const meta = graph.layout.meta;
    return {
      x: [meta.x_min, meta.x_max],
      y: [meta.display_y_min_hz / meta.y_to_hz, meta.display_y_max_hz / meta.y_to_hz],
      item: meta.modal_item_id,
    };
  });
  await page.locator("#modal-image-graph").evaluate(async (element) => {
    const graph = element.querySelector(".js-plotly-plot");
    await window.Plotly.relayout(graph, {
      "xaxis.range": [100, 150],
      "yaxis.range": [0.03, 5],
    });
  });
  await page.getByRole("button", { name: "Reset axes" }).click();
  await expect.poll(() => page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    return { x: graph.layout.xaxis.range, y: graph.layout.yaxis.range };
  })).toEqual({ x: canonical.x, y: canonical.y });

  await page.locator("#close-modal-header").click();
  await expect(page.locator("#image-modal")).toBeHidden();
  await cards.nth(1).click();
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 10_000 });
  await expect.poll(() => page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    return graph.layout.meta.modal_item_id;
  })).not.toBe(canonical.item);
  await expect(page.locator("#modal-image-graph")).toHaveCSS("visibility", "visible");
});
