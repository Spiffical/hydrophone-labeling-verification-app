const { test, expect } = require("playwright/test");

test.use({ channel: "chrome" });

test("a spectrogram modal preserves untouched automatic contrast", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(300_000);

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-auto-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", {
    timeout: 120_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /cmin=None&cmax=None/, {
    timeout: 60_000,
  });
  await firstImage.click();
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await page.locator("#image-modal summary.display-range-summary").click();
  await expect(page.locator("#modal-colorbar-readout")).toHaveText("Auto contrast", {
    timeout: 30_000,
  });

  await expect
    .poll(() => page.locator("#modal-image-graph").evaluate((element) => {
      const graph = element.querySelector(".js-plotly-plot");
      const meta = graph && graph.layout && graph.layout.meta;
      if (!meta) return null;
      return {
        autoMin: meta.auto_color_min,
        autoMax: meta.auto_color_max,
        displayMin: meta.display_color_min,
        displayMax: meta.display_color_max,
        pageMin: meta.page_display_color_min,
        pageMax: meta.page_display_color_max,
      };
    }), { timeout: 30_000 })
    .not.toBeNull();

  const renderedContrast = await page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    const meta = graph.layout.meta;
    return {
      autoMin: meta.auto_color_min,
      autoMax: meta.auto_color_max,
      displayMin: meta.display_color_min,
      displayMax: meta.display_color_max,
      pageMin: meta.page_display_color_min,
      pageMax: meta.page_display_color_max,
    };
  });
  const controls = await page.evaluate(() => ({
    min: Number(document.querySelector("#modal-colorbar-manual-min-input").value),
    max: Number(document.querySelector("#modal-colorbar-manual-max-input").value),
  }));

  expect(renderedContrast.pageMin).toBeNull();
  expect(renderedContrast.pageMax).toBeNull();
  expect(renderedContrast.displayMin).toBeCloseTo(renderedContrast.autoMin, 5);
  expect(renderedContrast.displayMax).toBeCloseTo(renderedContrast.autoMax, 5);
  expect(controls.min).toBeCloseTo(renderedContrast.autoMin, 1);
  expect(controls.max).toBeCloseTo(renderedContrast.autoMax, 1);
  expect([renderedContrast.displayMin, renderedContrast.displayMax]).not.toEqual([-90, -10]);
});

test("a spectrogram modal inherits the active page display settings", async ({ page }) => {
  test.skip(!process.env.MODAL_LIVE_BASE_URL, "Set MODAL_LIVE_BASE_URL for the live data check.");
  test.setTimeout(300_000);
  page.on("response", async (response) => {
    if (response.status() >= 400 && response.url().includes("_dash-update-component")) {
      console.log("dash-error", response.status(), await response.text());
    }
  });

  await page.goto(`${process.env.MODAL_LIVE_BASE_URL}/?qa=modal-display-${Date.now()}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("#verify-page-info")).toHaveText("No matches", {
    timeout: 120_000,
  });
  await page.locator("#global-date-selector").click();
  await page.getByRole("option", { name: "2026-04-08", exact: true }).click();

  const firstImage = page.locator("#verify-grid img.spectrogram-image").first();
  await expect(firstImage).toHaveAttribute("data-src", /item-image/, { timeout: 60_000 });
  await page.locator("#verify-display-settings-summary").click();
  await expect(page.locator("#verify-yaxis-manual-min-input")).not.toHaveValue("", {
    timeout: 30_000,
  });
  await expect(page.locator("#verify-colorbar-manual-min-input")).not.toHaveValue("", {
    timeout: 30_000,
  });
  await page.locator("#verify-colormap-toggle").check();
  await page.locator("#verify-yaxis-toggle").check();

  const yMinHandle = page.locator('#verify-yaxis-slider [role="slider"]').first();
  await yMinHandle.focus();
  await yMinHandle.press("ArrowRight");
  await expect(page.locator("#verify-yaxis-min-input")).not.toHaveValue("", { timeout: 30_000 });

  const colorMinHandle = page.locator('#verify-colorbar-slider [role="slider"]').first();
  await colorMinHandle.focus();
  await colorMinHandle.press("ArrowRight");
  await expect(page.locator("#verify-colorbar-min-input")).not.toHaveValue("", {
    timeout: 30_000,
  });

  const pageRanges = await page.evaluate(() => ({
    yMin: Number(document.querySelector("#verify-yaxis-min-input").value),
    yMax: Number(document.querySelector("#verify-yaxis-max-input").value),
    colorMin: Number(document.querySelector("#verify-colorbar-min-input").value),
    colorMax: Number(document.querySelector("#verify-colorbar-max-input").value),
  }));
  const stableFrequencyMaximum = await page.locator("#verify-yaxis-manual-max-input").inputValue();
  await page.waitForTimeout(1_500);
  await expect(page.locator("#verify-yaxis-manual-max-input")).toHaveValue(stableFrequencyMaximum);
  console.log("page-display-ranges", JSON.stringify(pageRanges));

  await expect(firstImage).toHaveAttribute("data-src", /cm=hydrophone/, { timeout: 60_000 });
  await expect(firstImage).toHaveAttribute("data-src", /ys=log/, { timeout: 60_000 });
  await expect(firstImage).not.toHaveAttribute("data-src", /ymin=None/, { timeout: 60_000 });
  await expect(firstImage).not.toHaveAttribute("data-src", /cmin=None/, { timeout: 60_000 });

  await firstImage.click();
  await expect(page.locator("#image-modal")).toBeVisible({ timeout: 30_000 });
  await page.locator("#image-modal summary.display-range-summary").click();
  await expect(page.locator('#modal-colormap-toggle input[value="hydrophone"]')).toBeChecked();
  await expect(page.locator('#modal-y-axis-toggle input[value="log"]')).toBeChecked();
  await expect(page.locator("#modal-yaxis-readout")).toContainText("Using page range");
  await expect(page.locator("#modal-yaxis-manual-min-input")).not.toHaveValue("", {
    timeout: 30_000,
  });
  await expect(page.locator("#modal-colorbar-readout")).toContainText("Using page contrast", {
    timeout: 30_000,
  });
  await expect
    .poll(() => page.locator("#modal-image-graph").evaluate((element) => {
      const graph = element.querySelector(".js-plotly-plot");
      const meta = graph && graph.layout && graph.layout.meta;
      return meta && {
        yAxisType: graph.layout.yaxis.type,
        yMin: meta.display_y_min_hz,
        yMax: meta.display_y_max_hz,
        colorMin: meta.display_color_min,
        colorMax: meta.display_color_max,
      };
    }), { timeout: 30_000 })
    .not.toBeNull();
  const renderedRanges = await page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    const meta = graph.layout.meta;
    return {
      yAxisType: graph.layout.yaxis.type,
      yMin: meta.display_y_min_hz,
      yMax: meta.display_y_max_hz,
      colorMin: meta.display_color_min,
      colorMax: meta.display_color_max,
      usesPageY: meta.uses_page_y_range,
      usesPageColor: meta.uses_page_color_range,
      pageYMin: meta.page_display_y_min_hz,
      pageYMax: meta.page_display_y_max_hz,
      pageColorMin: meta.page_display_color_min,
      pageColorMax: meta.page_display_color_max,
      xGrid: graph.layout.xaxis.showgrid,
      yGrid: graph.layout.yaxis.showgrid,
    };
  });
  const modalControls = await page.evaluate(() => ({
    yMin: Number(document.querySelector("#modal-yaxis-manual-min-input").value),
    yMax: Number(document.querySelector("#modal-yaxis-manual-max-input").value),
    colorMin: Number(document.querySelector("#modal-colorbar-manual-min-input").value),
    colorMax: Number(document.querySelector("#modal-colorbar-manual-max-input").value),
  }));
  console.log("modal-display-ranges", JSON.stringify({ renderedRanges, modalControls }));
  expect(renderedRanges.yAxisType).toBe("log");
  expect(renderedRanges.yMin).toBeCloseTo(pageRanges.yMin, 5);
  expect(renderedRanges.yMax).toBeCloseTo(pageRanges.yMax, 5);
  expect(renderedRanges.colorMin).toBeCloseTo(pageRanges.colorMin, 5);
  expect(renderedRanges.colorMax).toBeCloseTo(pageRanges.colorMax, 5);
  expect(renderedRanges.xGrid).toBe(false);
  expect(renderedRanges.yGrid).toBe(false);
  expect(modalControls.yMin).toBeCloseTo(pageRanges.yMin, 0);
  expect(modalControls.yMax).toBeCloseTo(pageRanges.yMax, 0);
  expect(modalControls.colorMin).toBeCloseTo(pageRanges.colorMin, 1);
  expect(modalControls.colorMax).toBeCloseTo(pageRanges.colorMax, 1);

  const modalColorMinimum = page.locator('#modal-colorbar-slider [role="slider"]').first();
  await modalColorMinimum.focus();
  await modalColorMinimum.press("ArrowRight");
  await expect
    .poll(() => page.locator("#modal-image-graph").evaluate((element) => {
      const graph = element.querySelector(".js-plotly-plot");
      return graph.layout.meta.display_color_min;
    }))
    .toBeGreaterThan(pageRanges.colorMin);
  const adjustedContrast = await page.locator("#modal-image-graph").evaluate((element) => {
    const graph = element.querySelector(".js-plotly-plot");
    return [graph.layout.meta.display_color_min, graph.layout.meta.display_color_max];
  });
  expect(adjustedContrast[0]).toBeCloseTo(pageRanges.colorMin + 0.1, 1);
  expect(adjustedContrast[1]).toBeCloseTo(pageRanges.colorMax, 1);
});
