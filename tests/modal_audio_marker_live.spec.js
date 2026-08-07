const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("modal playback marker follows plot time and stays inside the x-axis", async ({ page }) => {
  test.skip(!process.env.AUDIO_LIVE_BASE_URL, "Set AUDIO_LIVE_BASE_URL for the live data check.");
  test.setTimeout(180_000);

  await page.goto(`${process.env.AUDIO_LIVE_BASE_URL}/?qa=audio-marker-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", { timeout: 120_000 });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();
  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /item-image/, { timeout: 60_000 });
  await firstImage.click();
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#modal-busy-overlay")).toBeHidden({ timeout: 60_000 });

  const audio = page.locator("#modal-player-audio");
  await expect.poll(() => audio.evaluate((element) => element.duration), {
    timeout: 60_000,
  }).toBeGreaterThan(0);

  const result = await page.locator("#modal-image-graph").evaluate(async (container) => {
    const graph = container.querySelector(".js-plotly-plot");
    const audioElement = document.getElementById("modal-player-audio");
    const meta = graph.layout.meta;
    const plottedSeconds = (meta.x_max - meta.x_min) * meta.x_to_seconds;
    const checkpoints = [0, plottedSeconds * 0.25, plottedSeconds * 0.5, plottedSeconds];
    const samples = [];

    for (const seconds of checkpoints) {
      const actualSeconds = Math.min(seconds, audioElement.duration);
      audioElement.currentTime = actualSeconds;
      audioElement.dispatchEvent(new Event("timeupdate"));
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const marker = graph.layout.shapes.find((shape) => shape.name === "playback-marker");
      const axis = graph._fullLayout.xaxis;
      const yAxis = graph._fullLayout.yaxis;
      const expected = Math.min(meta.x_max, meta.x_min + (actualSeconds / meta.x_to_seconds));
      const markerPixel = axis._offset + axis.d2p(marker.x0);
      const svgRoot = graph.querySelector(".svg-container");
      const renderedMarker = graph.querySelector(".hydro-playback-marker-overlay");
      const rootBounds = svgRoot.getBoundingClientRect();
      const markerBounds = renderedMarker.getBoundingClientRect();
      samples.push({
        seconds: actualSeconds,
        expected,
        actual: marker.x0,
        markerPixel,
        renderedMarkerPixel: markerBounds.left - rootBounds.left + (markerBounds.width / 2),
        renderedTop: markerBounds.top - rootBounds.top,
        renderedBottom: markerBounds.bottom - rootBounds.top,
        axisLeft: axis._offset,
        axisRight: axis._offset + axis._length,
        axisTop: yAxis._offset,
        axisBottom: yAxis._offset + yAxis._length,
      });
    }
    return {
      audioDuration: audioElement.duration,
      plottedSeconds,
      xMin: meta.x_min,
      xMax: meta.x_max,
      xToSeconds: meta.x_to_seconds,
      samples,
    };
  });

  console.log("modal-audio-marker", JSON.stringify(result));
  expect(result.xToSeconds).toBe(60);
  expect(result.plottedSeconds).toBeGreaterThan(295);
  expect(result.plottedSeconds).toBeLessThanOrEqual(301);
  for (const sample of result.samples) {
    expect(sample.actual).toBeCloseTo(sample.expected, 5);
    expect(sample.actual).toBeGreaterThanOrEqual(result.xMin);
    expect(sample.actual).toBeLessThanOrEqual(result.xMax);
    expect(sample.markerPixel).toBeGreaterThanOrEqual(sample.axisLeft - 0.5);
    expect(sample.markerPixel).toBeLessThanOrEqual(sample.axisRight + 0.5);
    expect(sample.renderedMarkerPixel).toBeCloseTo(sample.markerPixel, 1);
    expect(sample.renderedTop).toBeCloseTo(sample.axisTop, 1);
    expect(sample.renderedBottom).toBeCloseTo(sample.axisBottom, 1);
  }
});
