const { test, expect } = require("playwright/test");

// Saves a review: run it against a disposable copy of the data, never the archive.
// VERIFY_LIVE_BASE_URL is the app; VERIFY_LIVE_DATE a day with unverified clips.
test.use({ channel: "chrome", viewport: { width: 1440, height: 900 } });

const statusCount = async (page, value) => {
  const label = await page.locator(`#verify-status-filter option[value="${value}"]`).textContent();
  return Number((label.match(/\(([\d,]+)\)/) || [])[1].replace(",", ""));
};

const settled = (page) => expect(page.locator("#specgen-page-loading-overlay")).toBeHidden({ timeout: 60_000 });

// The count follows a filter change by a round trip: wait for it to stop moving.
async function settledCount(page, value) {
  let previous;
  await expect.poll(async () => {
    const current = await statusCount(page, value);
    const unchanged = current === previous;
    previous = current;
    return unchanged;
  }, { intervals: [900], timeout: 30_000 }).toBe(true);
  return previous;
}

async function setRange(page, lower, upper) {
  const thumbs = page.locator("#verify-threshold-slider [role=slider]");
  for (const [index, target] of [[1, upper], [0, lower]]) {
    const thumb = thumbs.nth(index);
    await thumb.focus();
    let value = Number(await thumb.getAttribute("aria-valuenow"));
    while (value !== target) {
      await page.keyboard.press(value < target ? "ArrowRight" : "ArrowLeft");
      value = Number(await thumb.getAttribute("aria-valuenow"));
    }
  }
  await settled(page);
}

test("review page filters, orders and counts clips, and a review reaches them all", async ({ page }) => {
  test.skip(
    !process.env.VERIFY_LIVE_BASE_URL || !process.env.VERIFY_LIVE_DATE,
    "Set VERIFY_LIVE_BASE_URL and VERIFY_LIVE_DATE for the live check.",
  );
  test.setTimeout(180_000);

  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.addInitScript(() => {
    if (window.sessionStorage.getItem("qa-ready")) return;
    window.localStorage.clear();
    window.sessionStorage.setItem("qa-ready", "1");
    window.localStorage.setItem("user-profile-store", JSON.stringify({ name: "QA", email: "qa@example.test" }));
  });
  await page.goto(`${process.env.VERIFY_LIVE_BASE_URL}/?qa=review-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });

  await page.locator("#global-date-selector").click();
  await page.getByText(process.env.VERIFY_LIVE_DATE, { exact: true }).last().click();
  await expect(page.locator(".review-card").first()).toBeVisible({ timeout: 60_000 });
  await settled(page);

  // Every category of the hierarchy is offered, whatever the model outputs.
  for (const category of ["Biophony", "Geophony", "Anthropophony", "Instrumentation", "Other"]) {
    await expect(page.locator(".review-category-toggle", { hasText: category })).toBeVisible();
  }

  // The range decides what is in view.
  await setRange(page, 28, 100);
  const inRange = await settledCount(page, "unverified");
  expect(inRange).toBeGreaterThan(0);
  await setRange(page, 40, 100);
  expect(await settledCount(page, "unverified")).toBeLessThan(inRange);
  await setRange(page, 28, 100);
  expect(await settledCount(page, "unverified")).toBe(inRange);

  // Precision shows the highest confidence first, ambient being excluded.
  const confidences = await page.locator(".review-card").evaluateAll((cards) =>
    cards.map((card) =>
      Math.max(
        ...[...card.querySelectorAll(".review-label")]
          .filter((label) => !label.title.startsWith("Other > Ambient sound"))
          .map((label) => Number((label.title.match(/(\d+)% confidence/) || [])[1]))
          .filter(Number.isFinite),
      ),
    ),
  );
  expect(confidences.length).toBeGreaterThan(1);
  expect(confidences).toEqual([...confidences].sort((a, b) => b - a));

  // Shuffle deals a new order, and again on a second click.
  const times = () => page.locator(".review-card-time").allTextContents();
  const precisionOrder = await times();
  await page.locator("#verify-order-shuffle").click();
  await settled(page);
  await expect.poll(times).not.toEqual(precisionOrder);
  const shuffled = await times();
  await page.locator("#verify-order-shuffle").click();
  await settled(page);
  await expect.poll(times).not.toEqual(shuffled);
  await page.locator("#verify-order-precision").click();
  await settled(page);

  // A category menu lists its whole branch.
  const menu = page.locator(".review-category--biophony .review-category-menu");
  await menu.locator(":scope > summary").click();
  await expect(menu.locator(".review-tree")).toBeVisible();
  await page.mouse.click(2, 600);
  await expect(menu).not.toHaveAttribute("open", "");

  // Reviewing with a label the model cannot output: the whole card opens the clip.
  const unverifiedBefore = await settledCount(page, "unverified");
  await page.locator(".review-card .review-card-heading").first().click();
  await expect(page.locator(".modal.show")).toBeVisible({ timeout: 30_000 });
  await page.locator(".modal.show button", { hasText: "Edit labels" }).first().click();
  const editor = page.locator(".label-editor-modal.show");
  await expect(editor).toBeVisible({ timeout: 15_000 });
  await editor.getByPlaceholder("Search labels...").fill("Fin whale");
  await editor.getByText("Fin whale", { exact: true }).first().click();
  await page.locator("#label-editor-save").click();
  await expect(editor).toBeHidden({ timeout: 15_000 });
  await page.locator("#close-modal-header").click();
  await settled(page);

  await expect.poll(() => statusCount(page, "unverified")).toBe(unverifiedBefore - 1);
  await expect(page.locator("#verify-progress-total .review-total-count")).toContainText(/^1\//);

  await page.locator("#verify-status-filter").selectOption("verified");
  await page.locator(".review-category--biophony .review-category-toggle").click();
  await settled(page);
  await expect(page.locator(".review-card .review-label--biophony").first()).toHaveText("Fin whale");

  // Settings survive a reload.
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("#verify-selection-summary")).toHaveText("Biophony", { timeout: 30_000 });
  await expect(page.locator("#verify-status-filter")).toHaveValue("verified");

  expect(consoleErrors).toEqual([]);
});
