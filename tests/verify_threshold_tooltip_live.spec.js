const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("confidence threshold value is visible only while sliding", async ({ page }) => {
  test.skip(!process.env.VERIFY_LIVE_BASE_URL, "Set VERIFY_LIVE_BASE_URL for the live check.");
  test.setTimeout(120_000);

  await page.goto(`${process.env.VERIFY_LIVE_BASE_URL}/?qa=threshold-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await page.locator(".command-tool--review > summary").click();
  await expect(page.locator("#verify-threshold-slider [role=slider]")).toBeVisible({
    timeout: 60_000,
  });

  const handle = page.locator("#verify-threshold-slider [role=slider]");
  const tooltip = page.locator("[role=tooltip], .dash-slider-tooltip").filter({ hasText: /^0(?:\.\d+)?$/ });
  await expect(tooltip).toBeHidden();

  const bounds = await handle.boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.move(bounds.x + (bounds.width / 2), bounds.y + (bounds.height / 2));
  await page.mouse.down();
  try {
    await page.mouse.move(bounds.x + (bounds.width / 2) + 24, bounds.y + (bounds.height / 2), {
      steps: 5,
    });
    await expect(page.locator("[role=tooltip], .dash-slider-tooltip").filter({
      hasText: /^(?:0(?:\.\d+)?|1(?:\.0+)?)$/,
    })).toBeVisible();
  } finally {
    await page.mouse.up();
  }

  await page.mouse.move(0, 0);
  await expect(page.locator("[role=tooltip], .dash-slider-tooltip")).toBeHidden();
});
