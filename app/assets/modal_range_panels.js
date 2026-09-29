// Other visible ranges above or below the main spectrogram (view_callbacks.py)
// follow the main plot's time axis: the same plot-area edges and the same time
// window (page, zoom or pan), so a moment sits at the same place in every
// panel. Only the main plot zooms; the panels' axes are fixed.
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
    // For tests.
    panelShapes: panelShapes,
    extentFromPanelShape: extentFromPanelShape,
  };
}());
