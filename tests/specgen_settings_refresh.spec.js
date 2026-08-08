const path = require("path");
const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("a settings refresh replaces the source of an already-wired image", async ({ page }) => {
  const imageData = `data:image/svg+xml,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2" fill="black"/></svg>',
  )}`;
  const existingSrc = `${imageData}#src=existing&ov=0.9`;
  const generatedSrc = `${imageData}#src=audio_generated&ov=0.5`;

  await page.setContent(`
    <div id="verify-grid">
      <div class="spectrogram-image-container spec-loaded">
        <img class="spectrogram-image" src="${existingSrc}" data-src="${existingSrc}">
      </div>
    </div>
  `);
  await page.addScriptTag({
    path: path.resolve(__dirname, "../app/assets/spectrogram_image_loading.js"),
  });

  const image = page.locator("#verify-grid img.spectrogram-image");
  await expect
    .poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 1))
    .toBe(true);

  await image.evaluate((element) => {
    element.__spectrogramAwaitingDataSrc = element.getAttribute("data-src");
    element.__spectrogramForceLoad = true;
    element.__spectrogramLazyActivated = true;
    element.__spectrogramSrcChanging = true;
    element.closest(".spectrogram-image-container").className =
      "spectrogram-image-container spec-loading";
    element.setAttribute(
      "src",
      "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==",
    );
  });
  await page.waitForTimeout(50);
  await expect(image).not.toHaveAttribute("src", /src=existing/);

  await image.evaluate((element, nextSrc) => {
    element.setAttribute("data-src", nextSrc);
  }, generatedSrc);

  await expect(image).toHaveAttribute("src", /src=audio_generated&ov=0\.5/);
  await expect
    .poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 1))
    .toBe(true);

  await page.evaluate((nextSrc) => {
    window.__specgenOverlayLatestRequest = {
      mode: "verify",
      trigger_id: "verify-generate-spectrograms-btn",
    };
    const container = document.createElement("div");
    container.className = "spectrogram-image-container spec-loading";
    const replacement = document.createElement("img");
    replacement.className = "spectrogram-image";
    replacement.setAttribute("data-src", nextSrc);
    replacement.setAttribute(
      "src",
      "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==",
    );
    container.appendChild(replacement);
    document.querySelector("#verify-grid").replaceChildren(container);
  }, generatedSrc);

  const replacement = page.locator("#verify-grid img.spectrogram-image");
  await expect(replacement).toHaveAttribute("src", /src=audio_generated&ov=0\.5/);
  await expect
    .poll(() => replacement.evaluate((element) => element.complete && element.naturalWidth > 1))
    .toBe(true);
});

test("an explicit spectrogram refresh eagerly loads every image on the current page", async ({ page }) => {
  const images = Array.from({ length: 25 }, (_, index) => {
    const generatedSrc = `data:image/svg+xml,${encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2" fill="black"/></svg>`,
    )}#generated-${index}`;
    return `
      <div class="spectrogram-image-container" style="height: 500px">
        <img
          class="spectrogram-image"
          data-lazy-spectrogram="true"
          data-src="${generatedSrc}"
          src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
        >
      </div>
    `;
  }).join("");

  await page.setContent(`<div id="verify-grid">${images}</div>`);
  await page.evaluate(() => {
    window.__specgenOverlayLatestRequest = {
      mode: "verify",
      trigger_id: "verify-colormap-toggle",
      update_kind: "colormap",
      colormap_label: "O3.0",
    };
  });
  await page.addScriptTag({
    path: path.resolve(__dirname, "../app/assets/spectrogram_image_loading.js"),
  });

  await expect
    .poll(() => page.locator("#verify-grid img[src*='#generated-']").count())
    .toBe(25);
});

test("the live app regenerates the visible page after changing display settings", async ({ page }) => {
  test.skip(!process.env.SPECGEN_LIVE_BASE_URL, "Set SPECGEN_LIVE_BASE_URL for the live data check.");
  test.setTimeout(240_000);

  await page.goto(`${process.env.SPECGEN_LIVE_BASE_URL}/?qa=specgen-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText(/^(?:No matches|0 \/ 0)$/, {
    timeout: 30_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /src=existing/, { timeout: 90_000 });
  await firstImage.scrollIntoViewIfNeeded();
  await expect
    .poll(() => firstImage.evaluate((element) => element.complete && element.naturalWidth > 1), {
      timeout: 30_000,
    })
    .toBe(true);

  const displayTool = page.locator("#verify-display-settings-details");
  await displayTool.locator(":scope > summary").click();
  await page.evaluate(() => {
    window.__qaSpecgenOverlayEvents = [];
    const overlay = document.querySelector("#specgen-page-loading-overlay");
    window.__qaSpecgenOverlayObserver = new MutationObserver(() => {
      window.__qaSpecgenOverlayEvents.push({
        display: overlay.style.display,
        title: document.querySelector("#specgen-load-title")?.textContent || "",
      });
    });
    window.__qaSpecgenOverlayObserver.observe(overlay, {
      attributes: true,
      attributeFilter: ["style"],
      childList: true,
      characterData: true,
      subtree: true,
    });
  });

  await page
    .locator("#verify-spectrogram-source")
    .getByText("Generate from audio", { exact: true })
    .click();
  await expect(page.locator("#verify-fft-parameters-collapse")).toBeVisible();
  await page.locator("#verify-spec-overlap").fill("0.5");
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.__qaSpecgenOverlayEvents)).toEqual([]);
  await expect(firstImage).toHaveAttribute("data-src", /src=existing/);
  await page.locator("#verify-generate-spectrograms-btn").click();
  await expect(page.locator("#verify-generate-spectrograms-btn")).toBeDisabled();
  await expect(page.locator("#verify-generate-spectrograms-btn")).toHaveAttribute(
    "aria-busy",
    "true",
  );
  await expect(page.locator("#verify-generate-spectrograms-label")).toContainText("Generating");
  await expect(page.locator("#verify-generate-spectrograms-icon")).toHaveClass(
    /spectrogram-button-spinner/,
  );
  await expect
    .poll(() => page.evaluate(() => window.__qaSpecgenOverlayEvents), { timeout: 1_000 })
    .toContainEqual({ display: "flex", title: "Generating spectrograms" });
  await expect(firstImage).toHaveAttribute("data-src", /src=audio_generated.*ov=0\.5/, {
    timeout: 60_000,
  });
  await expect(firstImage).toHaveAttribute("src", /src=audio_generated.*ov=0\.5/, {
    timeout: 60_000,
  });
  await expect
    .poll(() => firstImage.evaluate((element) => element.complete && element.naturalWidth > 1), {
      timeout: 120_000,
    })
    .toBe(true);
  await expect(page.locator("#specgen-load-progress-text")).toHaveText(
    /(?:[1-9]|1\d|2[0-5]) of 25 ready/,
    { timeout: 30_000 },
  );
  await expect
    .poll(
      () => page.locator("#verify-grid img[data-src*='src=audio_generated']").count(),
      { timeout: 120_000 },
    )
    .toBe(25);
  await expect(page.locator("#specgen-page-loading-overlay")).toBeHidden({ timeout: 180_000 });
  await expect(page.locator("#verify-generate-spectrograms-label")).toHaveText(
    "Generate spectrograms",
  );
  await expect(page.locator("#verify-generate-spectrograms-btn")).toBeEnabled();
  await expect(page.locator("#verify-generate-spectrograms-btn")).toHaveAttribute(
    "aria-busy",
    "false",
  );

  const generatedDefaultSource = await firstImage.getAttribute("data-src");
  await page.locator("#verify-colormap-toggle").check();
  await expect(page.locator("#specgen-page-loading-overlay")).toBeVisible({ timeout: 1_000 });
  await expect(page.locator("#specgen-load-title")).toHaveText("Updating spectrograms");
  await expect(page.locator("#specgen-load-subtitle")).toContainText("O3.0 colormap");
  await expect(firstImage).toHaveAttribute("data-src", /src=audio_generated.*cm=hydrophone/, {
    timeout: 60_000,
  });
  await expect
    .poll(() => firstImage.evaluate((element) => element.complete && element.naturalWidth > 1), {
      timeout: 120_000,
    })
    .toBe(true);
  expect(await firstImage.getAttribute("data-src")).not.toBe(generatedDefaultSource);
  await expect(page.locator("#specgen-page-loading-overlay")).toBeHidden({ timeout: 180_000 });
});
