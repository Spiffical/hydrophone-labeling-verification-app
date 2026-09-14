const { test, expect } = require("playwright/test");

test.use({ channel: "chrome", viewport: { width: 1487, height: 1058 } });

test("compact command bar preserves the complete verify workflow", async ({ page }) => {
  test.skip(!process.env.VERIFY_LIVE_BASE_URL, "Set VERIFY_LIVE_BASE_URL for the live check.");
  test.setTimeout(180_000);

  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.__qaObservedTitles = [];
    document.addEventListener("DOMContentLoaded", () => {
      const recordTitle = () => window.__qaObservedTitles.push(document.title);
      recordTitle();
      new MutationObserver(recordTitle).observe(document.head, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }, { once: true });
  });

  await page.goto(`${process.env.VERIFY_LIVE_BASE_URL}/?qa=compact-header-${Date.now()}`, {
    waitUntil: "domcontentloaded",
    timeout: 120_000,
  });

  const commandBar = page.locator("#app-command-bar");
  await expect(commandBar).toBeVisible({ timeout: 60_000 });
  await expect(page).toHaveTitle("Hydrophone Acoustic Review Suite");
  await expect(commandBar).toHaveClass(/app-command-bar--verify/);
  await expect(page.locator("#global-date-selector")).toBeVisible();
  await expect(page.locator("#global-device-selector")).toBeVisible();
  await expect(page.locator("#global-load-btn")).toBeHidden();
  await expect(page.locator("#verify-reload")).toBeHidden();
  await expect(page.getByRole("heading", { name: "Verify Mode" })).toHaveCount(0);

  await page.locator("#global-date-selector").click();
  await page.getByText("2026-04-08", { exact: true }).last().click();

  const commandBounds = await commandBar.boundingBox();
  expect(commandBounds).not.toBeNull();
  await page.screenshot({
    path: "output/playwright/compact-header-loading.png",
    fullPage: false,
  });
  expect(commandBounds.height).toBeLessThanOrEqual(130);

  await expect(page.locator("#verify-grid")).toBeVisible();
  await expect(page.locator("#verify-grid .spectrogram-card").first()).toBeVisible({
    timeout: 120_000,
  });
  await expect(
    page.locator("details[data-command-panel] > summary .command-panel-caret"),
  ).toHaveCount(3);

  const reviewTool = page.locator(".command-tool--review");
  await reviewTool.locator(":scope > summary").click();
  await expect(reviewTool.locator(".command-popover--review")).toBeVisible();
  await expect(page.locator("#verify-status-filter")).toBeVisible();
  await expect(page.locator("#verify-threshold-slider")).toBeVisible();
  const statusTrigger = await page.locator("#verify-status-filter").boundingBox();
  const classTrigger = await page.locator("#verify-class-filter-toggle").boundingBox();
  expect(statusTrigger).not.toBeNull();
  expect(classTrigger).not.toBeNull();
  expect(Math.abs(statusTrigger.width - classTrigger.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(statusTrigger.height - classTrigger.height)).toBeLessThanOrEqual(1);
  const triggerStyles = await page.locator(
    "#verify-status-filter, #verify-class-filter-toggle",
  ).evaluateAll((elements) => elements.map((element) => {
    const style = window.getComputedStyle(element);
    return {
      borderRadius: style.borderRadius,
      borderColor: style.borderColor,
      backgroundColor: style.backgroundColor,
      fontSize: style.fontSize,
    };
  }));
  expect(triggerStyles[0]).toEqual(triggerStyles[1]);
  await page.screenshot({
    path: "output/playwright/compact-header-review.png",
    fullPage: false,
  });

  await page.locator(".command-filter-context").click({ position: { x: 2, y: 2 } });
  await expect(reviewTool).not.toHaveAttribute("open", "");
  await reviewTool.locator(":scope > summary").click();
  await expect(reviewTool).toHaveAttribute("open", "");

  const displayTool = page.locator("#verify-display-settings-details");
  await displayTool.locator(":scope > summary").click();
  await expect(reviewTool).not.toHaveAttribute("open", "");
  await expect(displayTool).toHaveAttribute("open", "");
  await expect(displayTool.locator(".display-range-content")).toBeVisible();
  await expect(page.getByRole("radio", { name: "Existing files" })).toBeChecked();
  await expect(page.getByRole("radio", { name: "Generate from audio" })).toBeEnabled();
  await expect(page.locator("#verify-fft-parameters-collapse")).not.toBeVisible();
  await expect(page.locator("#verify-generate-spectrograms-btn")).not.toBeVisible();
  await page.getByRole("radio", { name: "Generate from audio" }).click();
  await expect(page.locator("#verify-fft-parameters-collapse")).toBeVisible();
  await expect(displayTool.getByText("FFT parameters", { exact: true })).toBeVisible();
  await expect(page.locator("#verify-spec-win-dur")).toBeEnabled();
  await expect(page.locator("#verify-spec-overlap")).toBeEnabled();
  await expect(page.locator("#verify-generate-spectrograms-btn")).toBeVisible();
  await page.getByRole("radio", { name: "Existing files" }).click();
  await expect(page.locator("#verify-fft-parameters-collapse")).not.toBeVisible();
  await expect(page.locator("#verify-colormap-toggle")).toBeVisible();
  await expect(displayTool.getByText("O3.0 colormap", { exact: true })).toBeVisible();
  const presetOptions = page.locator("#verify-spectrogram-preset input[type=radio]");
  await expect(presetOptions).toHaveCount(5);
  await expect(page.getByRole("radio", { name: "Recommended" })).toBeDisabled();
  await expect(page.getByRole("radio", { name: "Low | 5-125 Hz" })).toBeEnabled();
  await expect(page.getByRole("radio", { name: "Mid | 100-2,000 Hz" })).toBeEnabled();
  await expect(page.getByRole("radio", { name: "High | 500-8,000 Hz" })).toBeEnabled();
  await expect(page.getByRole("radio", { name: "Custom" })).toBeEnabled();
  await expect(page.locator("#verify-yaxis-manual-min-input")).not.toHaveValue("");
  await expect(page.locator("#verify-colorbar-manual-min-input")).not.toHaveValue("");
  const displayGroups = displayTool.locator(".display-range-group");
  const firstDisplayGroup = await displayGroups.nth(0).boundingBox();
  const secondDisplayGroup = await displayGroups.nth(1).boundingBox();
  expect(firstDisplayGroup).not.toBeNull();
  expect(secondDisplayGroup).not.toBeNull();
  expect(secondDisplayGroup.y).toBeGreaterThanOrEqual(
    firstDisplayGroup.y + firstDisplayGroup.height,
  );
  await expect(displayTool.locator(".rc-slider-mark, .dash-slider-mark").first()).toBeHidden();
  await page.screenshot({
    path: "output/playwright/compact-header-display.png",
    fullPage: false,
  });
  await page.getByRole("button", { name: "Close spectrogram settings" }).click();
  await expect(displayTool).not.toHaveAttribute("open", "");
  await displayTool.locator(":scope > summary").click();

  const dataTool = page.locator(".command-tool--data");
  await dataTool.locator(":scope > summary").click();
  await expect(displayTool).not.toHaveAttribute("open", "");
  await expect(dataTool).toHaveAttribute("open", "");
  await expect(dataTool.locator(".command-popover--data")).toBeVisible();
  await expect(page.locator("#open-folder-browser")).toBeVisible();
  await expect(dataTool.getByText("Application settings", { exact: true })).toHaveCount(0);
  await page.screenshot({
    path: "output/playwright/compact-header-data.png",
    fullPage: false,
  });
  await reviewTool.locator(":scope > summary").click();
  await expect(dataTool).not.toHaveAttribute("open", "");
  await expect(reviewTool).toHaveAttribute("open", "");
  await reviewTool.locator(":scope > summary").click();
  await expect(reviewTool).not.toHaveAttribute("open", "");

  await expect(page.locator("#app-config-btn")).toBeVisible();
  await page.locator("#app-config-btn").click();
  await expect(page.locator("#app-config-modal")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#app-config-items-per-page")).toBeVisible();
  await expect(page.locator("#app-config-cache-size")).toBeVisible();
  await expect(page.locator("#app-config-spectrogram-source")).toHaveCount(0);
  await expect(page.locator("#app-config-spec-win-dur")).toHaveCount(0);
  await page.locator("#app-config-cancel").click();
  await expect(page.locator("#app-config-modal")).toBeHidden();

  await expect(page.locator("#verify-prev-page")).toBeVisible();
  await expect(page.locator("#verify-next-page")).toBeVisible();
  await expect(page.locator("#verify-page-info")).toContainText(/(?:\d+|Indexing)\s*(?:\/|\.\.\.)/);
  const pageJump = page.locator(".command-page-jump");
  await pageJump.locator(":scope > summary").click();
  await expect(pageJump).toHaveAttribute("open", "");
  await reviewTool.locator(":scope > summary").click();
  await expect(pageJump).not.toHaveAttribute("open", "");
  await expect(reviewTool).toHaveAttribute("open", "");
  await pageJump.locator(":scope > summary").click();
  await expect(reviewTool).not.toHaveAttribute("open", "");
  await expect(pageJump).toHaveAttribute("open", "");
  await page.locator(".command-filter-context").click({ position: { x: 2, y: 2 } });
  await expect(pageJump).not.toHaveAttribute("open", "");

  await page.screenshot({
    path: "output/playwright/compact-header-desktop.png",
    fullPage: false,
  });
  await expect(page).toHaveTitle("Hydrophone Acoustic Review Suite");
  expect(await page.evaluate(() => window.__qaObservedTitles)).not.toContain("undefined");

  await page.setViewportSize({ width: 1180, height: 800 });
  const deviceBounds = await page.locator(".command-select--device").boundingBox();
  const reviewBounds = await reviewTool.locator(":scope > summary").boundingBox();
  expect(deviceBounds).not.toBeNull();
  expect(reviewBounds).not.toBeNull();
  expect(deviceBounds.x + deviceBounds.width).toBeLessThanOrEqual(reviewBounds.x - 5);
  const overlaps = await page.locator("#app-command-bar > *:visible").evaluateAll((elements) => {
    const boxes = elements.map((element) => ({
      name: element.id || element.className,
      box: element.getBoundingClientRect(),
    }));
    const collisions = [];
    for (let index = 0; index < boxes.length; index += 1) {
      for (let candidate = index + 1; candidate < boxes.length; candidate += 1) {
        const left = boxes[index];
        const right = boxes[candidate];
        const intersects = (
          left.box.left < right.box.right
          && left.box.right > right.box.left
          && left.box.top < right.box.bottom
          && left.box.bottom > right.box.top
        );
        if (intersects) collisions.push(`${left.name} <> ${right.name}`);
      }
    }
    return collisions;
  });
  expect(overlaps).toEqual([]);
  await page.screenshot({
    path: "output/playwright/compact-header-narrow.png",
    fullPage: false,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(commandBar).toBeVisible();
  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: "output/playwright/compact-header-mobile.png",
    fullPage: false,
  });

  expect(consoleErrors).toEqual([]);
});
