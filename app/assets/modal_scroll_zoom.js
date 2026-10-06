// Scrolling over a spectrogram in the modal zooms about the pointer. Plotly's
// own scroll zoom is off (modal.py): it commits a zoom 50 ms after each wheel
// tick, and a tick that arrived while it was committing later committed an
// older view, so the plot jumped back and forth while zooming. Here wheel
// ticks add up and are applied once per frame as one GUI edit, which Dash
// re-plots keep (modal_paging.js). Plotly's step is kept: e^0.1 at most per
// tick.
//
// Over the main plot, time and frequency zoom, out to the whole clip and the
// plot's band. Over another spectrogram (modal_range_panels.js), time zooms on
// the main plot, which every panel follows, and frequency within the panel's
// band. Over the axes, colour bar or margins the page scrolls as usual.
(function () {
  'use strict';

  const MAIN = '#modal-image-graph .js-plotly-plot';
  const PANEL = '.spectrogram-modal-range-graph .js-plotly-plot';
  let pending = null;

  function ready(gd) {
    const layout = gd && gd._fullLayout;
    return Boolean(layout && layout._size && layout.xaxis && layout.yaxis);
  }

  function wheelFactor(event) {
    const delta = -Number(event.deltaY) || 0;
    return Math.exp(-Math.min(Math.max(delta, -20), 20) / 200);
  }

  // [lower, upper] zoomed by `factor` about `at`, kept inside `limits` if given.
  function zoomAbout(range, at, factor, limits) {
    let lower = at + (range[0] - at) * factor;
    let upper = at + (range[1] - at) * factor;
    if (!limits) {
      return [lower, upper];
    }
    if (upper - lower >= limits[1] - limits[0]) {
      return [limits[0], limits[1]];
    }
    if (lower < limits[0]) {
      upper += limits[0] - lower;
      lower = limits[0];
    }
    if (upper > limits[1]) {
      lower -= upper - limits[1];
      upper = limits[1];
    }
    return [lower, upper];
  }

  function relayoutGui(gd, update) {
    const paging = window.modalPaging;
    return paging && typeof paging.relayout === 'function'
      ? paging.relayout(gd, update)
      : window.Plotly.relayout(gd, update);
  }

  // The whole clip, and the main plot's band on its frequency axis (log axes
  // count in decades), as Home shows them (modal_lifecycle_clientside.js).
  function mainLimits(main) {
    const meta = (main.layout && main.layout.meta) || {};
    const xMin = Number(meta.x_min);
    const xMax = Number(meta.x_max);
    const yToHz = Number(meta.y_to_hz) || 1;
    let yMin = Number(meta.display_y_min_hz) / yToHz;
    let yMax = Number(meta.display_y_max_hz) / yToHz;
    if (main._fullLayout.yaxis.type === 'log') {
      yMin = yMin > 0 ? Math.log10(yMin) : NaN;
      yMax = yMax > 0 ? Math.log10(yMax) : NaN;
    }
    return {
      x: Number.isFinite(xMin) && Number.isFinite(xMax) && xMax > xMin ? [xMin, xMax] : null,
      y: Number.isFinite(yMin) && Number.isFinite(yMax) && yMax > yMin ? [yMin, yMax] : null,
    };
  }

  function apply() {
    const step = pending;
    pending = null;
    const main = document.querySelector(MAIN);
    if (!step || !ready(main) || !window.Plotly) {
      return;
    }
    const limits = mainLimits(main);
    const time = main._fullLayout.xaxis.range.map(Number);
    const update = {};
    const nextTime = zoomAbout(time, step.time, step.factor, limits.x);
    if (!same(nextTime, time)) {
      update['xaxis.range'] = nextTime;
      update['xaxis.autorange'] = false;
    }
    if (!step.panel) {
      const freq = main._fullLayout.yaxis.range.map(Number);
      const nextFreq = zoomAbout(freq, step.freq, step.factor, limits.y);
      if (!same(nextFreq, freq)) {
        update['yaxis.range'] = nextFreq;
        update['yaxis.autorange'] = false;
      }
    }
    // At the limits a tick changes nothing; leave the plot alone.
    if (Object.keys(update).length) {
      relayoutGui(main, update);
    }
    const panels = window.modalRangePanels;
    if (step.panel && ready(step.panel) && panels && typeof panels.zoomBand === 'function') {
      const freq = step.panel._fullLayout.yaxis.range.map(Number);
      const nextFreq = zoomAbout(freq, step.freq, step.factor, panels.bandOf(step.panel));
      if (!same(nextFreq, freq)) {
        panels.zoomBand(step.panel, nextFreq);
      }
    }
  }

  function same(left, right) {
    const slack = Math.abs(right[1] - right[0]) * 1e-9;
    return Math.abs(left[0] - right[0]) <= slack && Math.abs(left[1] - right[1]) <= slack;
  }

  function onWheel(event) {
    const target = event.target && typeof event.target.closest === 'function' ? event.target : null;
    const gd = target && (target.closest(MAIN) || target.closest(PANEL));
    const main = document.querySelector(MAIN);
    if (!gd || !ready(gd) || !ready(main)) {
      return;
    }
    const size = gd._fullLayout._size;
    const rect = gd.getBoundingClientRect();
    const across = (event.clientX - rect.left - size.l) / size.w;
    const up = (rect.top + size.t + size.h - event.clientY) / size.h;
    if (!(across >= 0 && across <= 1 && up >= 0 && up <= 1)) {
      return;
    }
    event.preventDefault();
    const panel = gd === main ? null : gd;
    const time = main._fullLayout.xaxis.range.map(Number);
    const freq = gd._fullLayout.yaxis.range.map(Number);
    const same = Boolean(pending) && pending.panel === panel;
    pending = {
      panel: panel,
      factor: (same ? pending.factor : 1) * wheelFactor(event),
      time: time[0] + (time[1] - time[0]) * across,
      freq: freq[0] + (freq[1] - freq[0]) * up,
    };
    if (!same) {
      window.requestAnimationFrame(apply);
    }
  }

  document.addEventListener('wheel', onWheel, { capture: true, passive: false });

  window.modalScrollZoom = {
    // For tests.
    zoomAbout: zoomAbout,
    mainLimits: mainLimits,
  };
}());
