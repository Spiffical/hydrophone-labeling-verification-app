const { test, expect } = require("playwright/test");

test("specgen overlay appears for uncached pages and source changes", async ({ page }) => {
  const logs = [];
  page.on("console", (msg) => {
    const t = `[${msg.type()}] ${msg.text()}`;
    logs.push(t);
    if (t.includes("specgen-overlay")) {
      console.log(t);
    }
  });

  await page.goto("http://127.0.0.1:8053", { waitUntil: "domcontentloaded" });

  const overlay = page.locator("#specgen-page-loading-overlay");
  const subtitle = page.locator("#specgen-load-subtitle");

  await page.click("#label-next-page");
  await expect(overlay).toBeVisible({ timeout: 15000 });
  await expect(subtitle).toContainText("remaining on this page", { timeout: 5000 });
  console.log("OVERLAY_TEXT_1:", await subtitle.textContent());
  await expect(overlay).toBeHidden({ timeout: 30000 });

  await page.locator("#label-display-settings-details > summary").click();
  await page.getByRole("radio", { name: "Generate from audio" }).click();
  await expect(page.locator("#label-fft-parameters-collapse")).toBeVisible();
  await page.fill("#label-spec-overlap", "0.5");
  await expect(overlay).toBeHidden();
  await page.locator("#label-generate-spectrograms-btn").click();
  await expect(overlay).toBeVisible({ timeout: 15000 });
  await expect(subtitle).toContainText("remaining on this page", { timeout: 5000 });
  console.log("OVERLAY_TEXT_2:", await subtitle.textContent());
  await expect(overlay).toBeHidden({ timeout: 30000 });

  const showLogs = logs.filter((x) => x.includes("[specgen-overlay] showing"));
  console.log("SPECGEN_SHOW_LOG_COUNT:", showLogs.length);
  if (!showLogs.length) {
    console.log("ALL_SPECGEN_LOGS:", logs.filter((x) => x.includes("specgen-overlay")).join("\n"));
  }

  await page.screenshot({ path: "/tmp/specgen_overlay_final.png", fullPage: true });
  expect(showLogs.length).toBeGreaterThan(0);
});
