// Other visible ranges above or below the main spectrogram (view_callbacks.py)
// follow the main plot's time axis: the same plot-area edges and the same time
// window (page, zoom or pan), so a moment sits at the same place in every
// panel. Only the main plot zooms; the panels' axes are fixed.
(function () {
  'use strict';

  const MAIN = '#modal-image-graph .js-plotly-plot';
  const PANELS = '.spectrogram-modal-range-graph .js-plotly-plot';
  const TOLERANCE_PX = 0.5;
  let frame = null;

  function mainPlot() {
    return document.querySelector(MAIN);
  }

  function ready(gd) {
    return Boolean(gd && gd._fullLayout && gd._fullLayout._size && gd._fullLayout.xaxis);
  }

  // Margins that put a panel's plot area right under the main plot's.
  function marginsFor(panel, main) {
    const size = main._fullLayout._size;
    const mainRect = main.getBoundingClientRect();
    const rect = panel.getBoundingClientRect();
    if (!rect.width || !mainRect.width) {
      return null; // not on screen
    }
    const left = mainRect.left + size.l - rect.left;
    const right = rect.right - (mainRect.left + size.l + size.w);
    if (left < 0 || right < 0 || rect.width - left - right < 40) {
      return null;
    }
    return { l: Math.round(left), r: Math.round(right) };
  }

  function sameRange(a, b) {
    if (!Array.isArray(a) || !Array.isArray(b)) {
      return false;
    }
    const slack = (Math.abs(Number(b[1]) - Number(b[0])) || 1) * 1e-6;
    return Math.abs(Number(a[0]) - Number(b[0])) <= slack && Math.abs(Number(a[1]) - Number(b[1])) <= slack;
  }

  function sync() {
    frame = null;
    const main = mainPlot();
    bindMain(main);
    if (!ready(main) || !window.Plotly) {
      return;
    }
    const range = main._fullLayout.xaxis.range;
    document.querySelectorAll(PANELS).forEach(function (panel) {
      bindPanel(panel);
      if (!ready(panel)) {
        return;
      }
      const update = {};
      const margins = marginsFor(panel, main);
      const size = panel._fullLayout._size;
      if (margins && (Math.abs(size.l - margins.l) > TOLERANCE_PX || Math.abs(size.r - margins.r) > TOLERANCE_PX)) {
        update['margin.l'] = margins.l;
        update['margin.r'] = margins.r;
      }
      if (!sameRange(panel._fullLayout.xaxis.range, range)) {
        update['xaxis.range'] = [Number(range[0]), Number(range[1])];
      }
      if (Object.keys(update).length) {
        window.Plotly.relayout(panel, update);
      }
    });
  }

  function schedule() {
    if (frame === null) {
      frame = window.requestAnimationFrame(sync);
    }
  }

  function bindMain(gd) {
    if (!gd || gd._rangePanelsBound || typeof gd.on !== 'function') {
      return;
    }
    gd._rangePanelsBound = true;
    gd.on('plotly_afterplot', schedule);
    gd.on('plotly_relayout', schedule);
    // Follow while the reviewer drags, not only when the drag ends.
    gd.on('plotly_relayouting', schedule);
  }

  function bindPanel(gd) {
    if (!gd || gd._rangePanelBound || typeof gd.on !== 'function') {
      return;
    }
    gd._rangePanelBound = true;
    // A figure from the server comes back with its own margins and window.
    gd.on('plotly_afterplot', schedule);
  }

  // Panels are rebuilt with each clip and range change, and the main graph
  // remounts when the modal opens.
  new MutationObserver(function (mutations) {
    for (const mutation of mutations) {
      const target = mutation.target;
      if (!target || !target.closest) {
        continue;
      }
      const main = mainPlot();
      if (target.closest('.spectrogram-modal-range-stack') || (main && !main._rangePanelsBound && target.closest('#modal-image-graph'))) {
        bindMain(main);
        schedule();
        return;
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });

  window.modalRangePanels = { sync: sync };
}());
