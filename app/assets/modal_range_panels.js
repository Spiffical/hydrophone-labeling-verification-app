// Other visible ranges above or below the main spectrogram (view_callbacks.py)
// follow the main plot's time axis: the same plot-area edges and the same time
// window (page, zoom or pan), so a moment sits at the same place in every
// panel. Scrolling over a panel zooms like scrolling over the main plot: the
// time window on the main plot, which every panel follows, and the panel's
// own frequency axis within its band. A double-click resets the zoom.
//
// Each panel also shows the clip's boxes that reach into its frequency band,
// and in draw mode a drag on a panel adds a box there (bbox_list.js addBox).
(function () {
  'use strict';

  const MAIN = '#modal-image-graph .js-plotly-plot';
  const PANELS = '.spectrogram-modal-range-graph .js-plotly-plot';
  const TOLERANCE_PX = 0.5;
  const OWN_SHAPE = 'panel-box-';
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

  function panelMeta(panel) {
    const meta = (panel.layout && panel.layout.meta) || {};
    return {
      fmin: Number(meta.freq_min_hz),
      fmax: Number(meta.freq_max_hz),
      xMin: Number(meta.x_min),
      xMax: Number(meta.x_max),
      xToSeconds: Number(meta.x_to_seconds) || 1,
      log: Boolean(panel._fullLayout && panel._fullLayout.yaxis && panel._fullLayout.yaxis.type === 'log'),
    };
  }

  // Boxes that reach into this panel's band, styled as on the main plot. Parts
  // outside the band are cut off by the plot area, not redrawn at its edge.
  function panelShapes(panel, boxes) {
    const meta = panelMeta(panel);
    if (!Number.isFinite(meta.fmin) || !Number.isFinite(meta.fmax) || meta.fmax <= meta.fmin) {
      return [];
    }
    const geometry = window.bboxGeometry;
    const shapes = [];
    (Array.isArray(boxes) ? boxes : []).forEach(function (box, index) {
      const extent = box && box.annotation_extent;
      if (!extent || typeof extent !== 'object' || !extent.type || extent.type === 'clip') {
        return;
      }
      const hasTime = extent.type === 'time_freq_box' || extent.type === 'time_range';
      const hasFreq = extent.type === 'time_freq_box' || extent.type === 'freq_range';
      const x0 = hasTime ? Number(extent.time_start_sec) / meta.xToSeconds : meta.xMin;
      const x1 = hasTime ? Number(extent.time_end_sec) / meta.xToSeconds : meta.xMax;
      let y0 = hasFreq ? Number(extent.freq_min_hz) : meta.fmin;
      let y1 = hasFreq ? Number(extent.freq_max_hz) : meta.fmax;
      if (![x0, x1, y0, y1].every(Number.isFinite) || y1 <= meta.fmin || y0 >= meta.fmax) {
        return; // outside this band
      }
      if (meta.log) {
        // A log axis has no 0 Hz; start the box at the band's bottom.
        y0 = Math.max(y0, meta.fmin);
      }
      const style = geometry && typeof geometry.boxStyle === 'function'
        ? geometry.boxStyle(box)
        : { lineColor: 'rgba(255, 99, 71, 0.95)', lineDash: 'solid', fillColor: 'rgba(255, 99, 71, 0.18)' };
      shapes.push({
        type: 'rect',
        xref: 'x',
        yref: 'y',
        x0: x0,
        x1: x1,
        y0: y0,
        y1: y1,
        name: OWN_SHAPE + index,
        editable: false,
        layer: 'above',
        line: { color: style.lineColor, width: 2, dash: style.lineDash },
        fillcolor: style.fillColor,
      });
    });
    return shapes;
  }

  // A box drawn on a panel, in seconds and Hz. A box the full height of the
  // band is still limited to the band, not every frequency.
  function extentFromPanelShape(panel, shape) {
    const geometry = window.bboxGeometry;
    const meta = panelMeta(panel);
    if (!geometry || typeof geometry.shapeToExtent !== 'function') {
      return null;
    }
    const extent = geometry.shapeToExtent(shape, {
      x_to_seconds: meta.xToSeconds,
      y_to_hz: 1,
      x_min: meta.xMin,
      x_max: meta.xMax,
      y_min: meta.fmin,
      y_max: meta.fmax,
    });
    if (!extent) {
      return null;
    }
    if (extent.type === 'time_range' || extent.type === 'clip') {
      const lower = Math.min(Number(shape.x0), Number(shape.x1));
      const upper = Math.max(Number(shape.x0), Number(shape.x1));
      return {
        type: 'time_freq_box',
        time_start_sec: Math.max(0, Math.round(Math.max(lower, meta.xMin) * meta.xToSeconds * 1000) / 1000),
        time_end_sec: Math.max(0, Math.round(Math.min(upper, meta.xMax) * meta.xToSeconds * 1000) / 1000),
        freq_min_hz: meta.fmin,
        freq_max_hz: meta.fmax,
      };
    }
    return extent;
  }

  function canDraw() {
    const draw = window.bboxDrawMode;
    const panel = window.bboxPanel;
    return Boolean(
      draw && typeof draw.isOn === 'function' && draw.isOn() &&
      panel && typeof panel.canEdit === 'function' && panel.canEdit()
    );
  }

  function currentBoxes() {
    const panel = window.bboxPanel;
    return panel && typeof panel.boxes === 'function' ? panel.boxes() : [];
  }

  // The red playback line (audio_controls.js) on every panel.
  function refreshPlayback() {
    const audio = document.getElementById('modal-player-audio');
    if (
      audio && typeof window.updateSpectrogramPlaybackMarker === 'function' &&
      Number.isFinite(audio.duration) && audio.duration > 0
    ) {
      window.updateSpectrogramPlaybackMarker(audio.currentTime || 0, audio.duration);
    }
  }

  function sync() {
    frame = null;
    const main = mainPlot();
    bindMain(main);
    if (!ready(main) || !window.Plotly) {
      return;
    }
    const range = main._fullLayout.xaxis.range;
    const boxes = currentBoxes();
    const drawing = canDraw();
    document.querySelectorAll(PANELS).forEach(function (panel) {
      bindPanel(panel);
      if (!ready(panel)) {
        return;
      }
      // A figure from the server replaces the layout, and with it the boxes.
      if (panel._rangePanelLayout !== panel.layout) {
        panel._rangePanelLayout = panel.layout;
        panel._rangePanelShapes = null;
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
      const zoom = bandZoom[zoomKey(panel)];
      if (zoom && panel._fullLayout.yaxis && !sameRange(panel._fullLayout.yaxis.range, zoom)) {
        update['yaxis.range'] = zoom.slice();
      }
      const shapes = panelShapes(panel, boxes);
      const signature = JSON.stringify(shapes);
      if (panel._rangePanelShapes !== signature) {
        update.shapes = shapes;
      }
      const dragmode = drawing ? 'drawrect' : false;
      if (panel._fullLayout.dragmode !== dragmode) {
        update.dragmode = dragmode;
        if (drawing) {
          update.newshape = { line: { color: 'rgba(255, 99, 71, 0.95)', width: 2 }, fillcolor: 'rgba(255, 99, 71, 0.18)' };
        }
      }
      if (Object.keys(update).length) {
        panel._rangePanelShapes = signature;
        window.Plotly.relayout(panel, update);
      }
    });
    refreshPlayback();
  }

  function schedule() {
    if (frame === null) {
      frame = window.requestAnimationFrame(sync);
    }
  }

  // A drag on a panel in draw mode: Plotly adds an unnamed shape; turn it into
  // a box, and put the store's boxes back on the panel.
  function onPanelRelayout(panel, event) {
    if (!event || !Array.isArray(event.shapes)) {
      return;
    }
    const drawn = event.shapes.filter(function (shape) {
      return shape && !(typeof shape.name === 'string' && shape.name.indexOf(OWN_SHAPE) === 0);
    });
    if (!drawn.length) {
      return;
    }
    panel._rangePanelShapes = null;
    if (canDraw()) {
      const extent = extentFromPanelShape(panel, drawn[drawn.length - 1]);
      if (extent) {
        window.bboxPanel.addBox(extent);
      }
    }
    schedule();
  }

  // ---------------------------------------------------------------------------
  // Scroll zoom over a panel. The step is Plotly's own (the main plot's
  // scrollZoom, modal.py), and steps are applied once per frame.

  let wheel = null;

  // Each panel's frequency zoom, by its figure's uirevision (clip, range and
  // band; view_callbacks.py). Dash re-creates the panels when it sends them
  // again (after a box is drawn, say), and sync() puts the zoom back.
  const bandZoom = {};

  function zoomKey(panel) {
    const uirevision = panel && panel.layout && panel.layout.uirevision;
    return uirevision ? String(uirevision) : null;
  }

  // The panel's band on its frequency axis (log axes count in decades).
  function bandOf(panel) {
    const meta = panelMeta(panel);
    if (!Number.isFinite(meta.fmin) || !Number.isFinite(meta.fmax) || meta.fmax <= meta.fmin) {
      return null;
    }
    return meta.log ? [Math.log10(Math.max(meta.fmin, 1e-9)), Math.log10(meta.fmax)] : [meta.fmin, meta.fmax];
  }

  // [lower, upper] zoomed by `factor` about `at`, kept inside `band` if given.
  function zoomAbout(range, at, factor, band) {
    let lower = at + (range[0] - at) * factor;
    let upper = at + (range[1] - at) * factor;
    if (!band) {
      return [lower, upper];
    }
    if (upper - lower >= band[1] - band[0]) {
      return [band[0], band[1]];
    }
    if (lower < band[0]) {
      upper += band[0] - lower;
      lower = band[0];
    }
    if (upper > band[1]) {
      lower -= upper - band[1];
      upper = band[1];
    }
    return [lower, upper];
  }

  // Zoom changes are GUI edits, which Plotly keeps when Dash sends the same
  // figure again (uirevision; modal_paging.js): the main plot's time window,
  // which the panels follow in sync(), and a panel's frequency axis, which
  // its figure keeps per clip and range (view_callbacks.py).
  function relayoutGui(gd, update) {
    const paging = window.modalPaging;
    return paging && typeof paging.relayout === 'function'
      ? paging.relayout(gd, update)
      : window.Plotly.relayout(gd, update);
  }

  function applyWheel() {
    const step = wheel;
    wheel = null;
    const main = mainPlot();
    if (!step || !ready(main) || !ready(step.panel) || !window.Plotly) {
      return;
    }
    relayoutGui(main, {
      'xaxis.range': zoomAbout(main._fullLayout.xaxis.range.map(Number), step.time, step.factor, null),
      'xaxis.autorange': false,
    });
    const band = bandOf(step.panel);
    if (band) {
      const range = zoomAbout(step.panel._fullLayout.yaxis.range.map(Number), step.freq, step.factor, band);
      const key = zoomKey(step.panel);
      if (key && sameRange(range, band)) {
        delete bandZoom[key];
      } else if (key) {
        bandZoom[key] = range;
      }
      relayoutGui(step.panel, { 'yaxis.range': range });
    }
  }

  function onPanelWheel(panel, event) {
    const main = mainPlot();
    if (!ready(main) || !ready(panel) || !panel._fullLayout.yaxis) {
      return;
    }
    const size = panel._fullLayout._size;
    const rect = panel.getBoundingClientRect();
    const across = (event.clientX - rect.left - size.l) / size.w;
    const up = (rect.top + size.t + size.h - event.clientY) / size.h;
    if (!(across >= 0 && across <= 1 && up >= 0 && up <= 1)) {
      return; // over the axes or margins: the page scrolls
    }
    event.preventDefault();
    const delta = -Number(event.deltaY) || 0;
    const factor = Math.exp(-Math.min(Math.max(delta, -20), 20) / 200);
    const time = main._fullLayout.xaxis.range.map(Number);
    const freq = panel._fullLayout.yaxis.range.map(Number);
    const pending = wheel && wheel.panel === panel;
    wheel = { panel: panel, factor: (pending ? wheel.factor : 1) * factor,
      time: time[0] + (time[1] - time[0]) * across, freq: freq[0] + (freq[1] - freq[0]) * up };
    if (!pending) {
      window.requestAnimationFrame(applyWheel);
    }
  }

  // Every panel back to its whole band (also on the main plot's reset,
  // modal_lifecycle_clientside.js).
  function resetBands() {
    Object.keys(bandZoom).forEach(function (key) { delete bandZoom[key]; });
    if (!window.Plotly) {
      return;
    }
    document.querySelectorAll(PANELS).forEach(function (panel) {
      const band = ready(panel) && panel._fullLayout.yaxis ? bandOf(panel) : null;
      if (band && !sameRange(panel._fullLayout.yaxis.range, band)) {
        relayoutGui(panel, { 'yaxis.range': band });
      }
    });
  }

  // A double-click on a panel resets the zoom as one on the main plot does:
  // Plotly's autorange there goes back to the page (modal_lifecycle_clientside.js),
  // and with it every panel to its band. Plotly's drag cover takes the native
  // double-click; the clicks it sends on afterwards count (event.detail).
  function onPanelClick(event) {
    const main = mainPlot();
    if (event && event.detail === 2 && ready(main) && window.Plotly) {
      window.Plotly.relayout(main, { 'xaxis.autorange': true, 'yaxis.autorange': true });
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
    gd.on('plotly_relayout', function (event) { onPanelRelayout(gd, event); });
    if (typeof gd.addEventListener === 'function') {
      gd.addEventListener('wheel', function (event) { onPanelWheel(gd, event); }, { passive: false });
      gd.addEventListener('click', onPanelClick);
    }
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

  // Draw mode on or off, or another label to draw.
  if (window.bboxDrawMode && typeof window.bboxDrawMode.subscribe === 'function') {
    window.bboxDrawMode.subscribe(schedule);
  }

  window.modalRangePanels = {
    sync: sync,
    schedule: schedule,
    resetBands: resetBands,
    // For tests.
    panelShapes: panelShapes,
    extentFromPanelShape: extentFromPanelShape,
  };
}());
