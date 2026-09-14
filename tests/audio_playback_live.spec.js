const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("a live verification card loads playable audio", async ({ page }) => {
  test.skip(!process.env.AUDIO_LIVE_BASE_URL, "Set AUDIO_LIVE_BASE_URL for the live data check.");
  test.setTimeout(120_000);

  await page.goto(`${process.env.AUDIO_LIVE_BASE_URL}/?qa=audio-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", {
    timeout: 30_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  const playButton = page.locator('button[id^="card-"][id$="-play-btn"]').first();
  await expect(playButton).toBeVisible({ timeout: 60_000 });
  const playerId = (await playButton.getAttribute("id")).replace(/-play-btn$/, "");
  const audio = page.locator(`#${playerId}-audio`);
  const audioResponse = page.waitForResponse(
    (response) => response.url().includes("/audio-file/") && [200, 206].includes(response.status()),
    { timeout: 60_000 },
  );

  await playButton.click();
  const response = await audioResponse;
  expect([200, 206]).toContain(response.status());
  await expect
    .poll(
      () => audio.evaluate((element) => (
        element.src.includes("/audio-file/") &&
        element.readyState > 0 &&
        element.error === null
      )),
      { timeout: 60_000 },
    )
    .toBe(true);
});

test("modal settings persist while playback position resets for the next recording", async ({ page }) => {
  test.skip(!process.env.AUDIO_LIVE_BASE_URL, "Set AUDIO_LIVE_BASE_URL for the live data check.");
  test.setTimeout(120_000);

  await page.goto(`${process.env.AUDIO_LIVE_BASE_URL}/?qa=gain-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", {
    timeout: 30_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  await page.locator("#verify-grid img.spectrogram-image").first().click({ timeout: 60_000 });
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });
  await expect(page.locator("#modal-player-gain-display")).toHaveText("1.0x");

  await page.locator("#image-modal summary.display-range-summary").click();
  const originalColormap = await page.locator('#modal-colormap-toggle input:checked').inputValue();
  const expectedColormap = originalColormap === "default" ? "hydrophone" : "default";
  await page.locator(`#modal-colormap-toggle input[value="${expectedColormap}"]`).check();
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 30_000 });

  const originalScale = await page.locator('#modal-y-axis-toggle input:checked').inputValue();
  const expectedScale = originalScale === "linear" ? "log" : "linear";
  await page.locator(`#modal-y-axis-toggle input[value="${expectedScale}"]`).check();
  await expect
    .poll(() => page.locator("#modal-image-graph").evaluate((element) => {
      const graph = element.querySelector(".js-plotly-plot");
      return graph && graph.layout.yaxis.type;
    }), { timeout: 30_000 })
    .toBe(expectedScale);
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 30_000 });

  const pitchHandle = page.locator('#modal-player-pitch-slider [role="slider"]');
  await pitchHandle.focus();
  await pitchHandle.press("End");
  await expect(page.locator("#modal-player-pitch-display")).toHaveText("4.00x");

  const gainHandle = page.locator('#modal-player-gain-slider [role="slider"]');
  await gainHandle.focus();
  await gainHandle.press("End");
  await expect(page.locator("#modal-player-gain-display")).toHaveText("50.0x");

  const eqSlider = page.locator("#modal-player-eq-80-slider");
  const eqHandle = eqSlider.locator('[role="slider"]');
  const eqBounds = await eqHandle.boundingBox();
  expect(eqBounds).not.toBeNull();
  await page.mouse.move(
    eqBounds.x + (eqBounds.width / 2),
    eqBounds.y + (eqBounds.height / 2),
  );
  await page.mouse.down();
  await page.mouse.move(
    eqBounds.x + (eqBounds.width / 2),
    eqBounds.y - 30,
    { steps: 5 },
  );
  await page.mouse.up();
  await expect(eqHandle).not.toHaveAttribute("aria-valuenow", "0");
  const expectedEqValue = await eqHandle.getAttribute("aria-valuenow");

  await page.locator("#modal-player-visible-filter-toggle").check();
  await expect(page.locator("#modal-player-visible-filter-toggle")).toBeChecked();

  const originalAudioSource = await page.locator("#modal-player-audio").getAttribute("data-audio-src");
  await expect
    .poll(() => page.locator("#modal-player-audio").evaluate((audio) => (
      Number.isFinite(audio.duration) && audio.duration > 60
    )), { timeout: 30_000 })
    .toBe(true);
  await page.locator("#modal-player-audio").evaluate((audio) => {
    audio.currentTime = 45;
    audio.dispatchEvent(new Event("timeupdate"));
  });
  await expect(page.locator("#modal-player-current-time")).toHaveText("0:45");
  await expect(page.locator("#modal-player-time-slider")).not.toHaveValue("0");

  await page.locator("#modal-nav-next").click();
  await expect(page.locator("#modal-player-gain-display")).toHaveText("50.0x", {
    timeout: 30_000,
  });
  await expect(page.locator("#modal-player-pitch-display")).toHaveText("4.00x");
  await expect(page.locator('#modal-player-eq-80-slider [role="slider"]')).toHaveAttribute(
    "aria-valuenow",
    expectedEqValue,
  );
  await expect(page.locator("#modal-player-visible-filter-toggle")).toBeChecked();
  await expect(page.locator("#modal-player-audio")).not.toHaveAttribute(
    "data-audio-src",
    originalAudioSource,
  );
  await expect
    .poll(() => page.locator("#modal-player-audio").evaluate((audio) => audio.currentTime), {
      timeout: 10_000,
    })
    .toBeLessThan(0.05);
  await expect(page.locator("#modal-player-current-time")).toHaveText("0:00");
  await expect(page.locator("#modal-player-time-slider")).toHaveValue("0");
  await expect(page.locator(`#modal-colormap-toggle input[value="${expectedColormap}"]`)).toBeChecked();
  await expect(page.locator(`#modal-y-axis-toggle input[value="${expectedScale}"]`)).toBeChecked();
  await expect
    .poll(() => page.locator("#modal-player-audio").evaluate((audio) => ({
      gain: audio.gainNode && audio.gainNode.gain.value,
      requestedGain: audio.requestedGain,
      playbackRate: audio.playbackRate,
      playbackRequested: audio.userRequestedPlayback,
    })), { timeout: 10_000 })
    .toEqual({ gain: 0, requestedGain: 50, playbackRate: 4, playbackRequested: false });
  expect(await page.locator('audio[id^="card-"]').first().evaluate((audio) => Boolean(audio.gainNode)))
    .toBe(false);
});

test("paused modal audio remains silent and stationary", async ({ page }) => {
  test.skip(!process.env.AUDIO_LIVE_BASE_URL, "Set AUDIO_LIVE_BASE_URL for the live data check.");
  test.setTimeout(120_000);

  await page.goto(`${process.env.AUDIO_LIVE_BASE_URL}/?qa=pause-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", {
    timeout: 30_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();
  await page.locator("#verify-grid img.spectrogram-image").first().click({ timeout: 60_000 });
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });

  const audio = page.locator("#modal-player-audio");
  await audio.evaluate((element) => {
    window.__pauseQaEvents = [];
    ["play", "playing", "pause"].forEach((eventName) => {
      element.addEventListener(eventName, () => {
        window.__pauseQaEvents.push({ eventName, at: element.currentTime });
      });
    });
  });
  await page.locator("#modal-player-play-btn").click();
  await expect.poll(() => audio.evaluate((element) => element.currentTime), {
    timeout: 30_000,
  }).toBeGreaterThan(0.5);
  await page.locator("#modal-player-play-btn").click();
  await expect.poll(() => audio.evaluate((element) => element.paused)).toBe(true);
  await expect.poll(() => page.evaluate(() => (
    window.__pauseQaEvents.filter((event) => event.eventName === "pause").length
  ))).toBeGreaterThan(0);

  const pausedAt = await audio.evaluate((element) => element.currentTime);
  const eventCount = await page.evaluate(() => window.__pauseQaEvents.length);
  await expect.poll(() => audio.evaluate((element) => (
    element.gainNode ? element.gainNode.gain.value : 0
  ))).toBe(0);

  await page.waitForTimeout(22_000);

  const finalState = await audio.evaluate((element) => ({
    paused: element.paused,
    currentTime: element.currentTime,
    gain: element.gainNode ? element.gainNode.gain.value : 0,
    contextState: element.audioContext ? element.audioContext.state : "unavailable",
  }));
  expect(finalState.paused).toBe(true);
  expect(Math.abs(finalState.currentTime - pausedAt)).toBeLessThan(0.05);
  expect(finalState.gain).toBe(0);
  expect(["suspended", "unavailable"]).toContain(finalState.contextState);
  expect(await page.evaluate(() => window.__pauseQaEvents.length)).toBe(eventCount);
});
