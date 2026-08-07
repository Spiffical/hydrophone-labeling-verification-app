const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("modal navigation stays responsive across neighboring spectrograms", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(180_000);

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-nav-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", {
    timeout: 30_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /item-image/, { timeout: 60_000 });
  await firstImage.click();
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });

  const renderedImage = await page.locator("#modal-image-graph").evaluate(async (container) => {
    const graph = container.querySelector(".js-plotly-plot");
    const source = graph && graph.layout && graph.layout.images && graph.layout.images[0].source;
    const sourceShape = graph && graph.layout && graph.layout.meta
      ? graph.layout.meta.source_matrix_shape
      : null;
    const response = await fetch(source);
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);
    return {
      source,
      sourceShape,
      bytes: blob.size,
      width: bitmap.width,
      height: bitmap.height,
    };
  });
  console.log("modal-image", JSON.stringify({
    width: renderedImage.width,
    height: renderedImage.height,
    bytes: renderedImage.bytes,
  }));
  expect(renderedImage.source).toContain("/modal-image/");
  expect(renderedImage.sourceShape).toEqual([renderedImage.height, renderedImage.width]);
  expect(renderedImage.sourceShape).toEqual([854, 1000]);

  if (process.env.MODAL_SCREENSHOT_PATH) {
    await page.screenshot({ path: process.env.MODAL_SCREENSHOT_PATH, fullPage: true });
  }

  const durations = [];
  for (let index = 0; index < 5; index += 1) {
    const previousHeader = await page.locator("#modal-header").innerText();
    const startedAt = Date.now();
    await page.locator("#modal-nav-next").click();
    await expect(page.locator("#modal-header")).not.toHaveText(previousHeader, {
      timeout: 60_000,
    });
    await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });
    await expect(page.locator("#modal-image-graph")).not.toHaveAttribute(
      "data-dash-is-loading",
      "true",
      { timeout: 60_000 },
    );
    durations.push(Date.now() - startedAt);
  }

  console.log("modal-navigation-ms", JSON.stringify(durations));
  expect(durations).toHaveLength(5);
  const sortedDurations = [...durations].sort((left, right) => left - right);
  expect(sortedDurations[Math.floor(sortedDurations.length / 2)]).toBeLessThan(1500);
  expect(Math.max(...durations)).toBeLessThan(2500);
});
