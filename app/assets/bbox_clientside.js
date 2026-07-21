(function () {
  const DELETE_TRACE = '__bbox_delete_handle__';
  const EDIT_TRACE = '__bbox_edit_handle__';

  function dashContext() {
    return (window.dash_clientside || {}).callback_context || null;
  }

  function noUpdate() {
    return (window.dash_clientside || {}).no_update;
  }

  function noUpdates(count) {
    return Array.from({ length: count }, noUpdate);
  }

  function profileIsComplete(profile) {
    const value = profile || {};
    const name = String(value.name || '').trim();
    const email = String(value.email || '').trim();
    return Boolean(name) && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
  }

  function parseTriggeredId(context) {
    if (!context) {
      return null;
    }
    if (context.triggered_id !== undefined && context.triggered_id !== null) {
      return context.triggered_id;
    }
    const triggered = context.triggered && context.triggered[0];
    const propId = triggered && triggered.prop_id;
    if (!propId) {
      return null;
    }
    const rawId = propId.slice(0, propId.lastIndexOf('.'));
    if (rawId.charAt(0) !== '{') {
      return rawId;
    }
    try {
      return JSON.parse(rawId);
    } catch (_error) {
      return null;
    }
  }

  function triggeredValue(context) {
    const triggered = context && context.triggered && context.triggered[0];
    return triggered ? triggered.value : null;
  }

  function coerceIndex(value) {
    let candidate = value;
    if (Array.isArray(candidate)) {
      candidate = candidate[0];
    } else if (candidate && typeof candidate === 'object') {
      candidate = candidate.box_index !== undefined ? candidate.box_index : candidate.index;
    }
    if (candidate === null || candidate === undefined || candidate === '' || typeof candidate === 'boolean') {
      return null;
    }
    const number = Number(candidate);
    return Number.isFinite(number) ? Math.trunc(number) : null;
  }

  function graphElement() {
    const wrapper = document.getElementById('modal-image-graph');
    if (!wrapper) {
      return null;
    }
    if (wrapper.classList && wrapper.classList.contains('js-plotly-plot')) {
      return wrapper;
    }
    return wrapper.querySelector ? wrapper.querySelector('.js-plotly-plot') : null;
  }

  function setPanModeImmediately(graph) {
    const target = graph || graphElement();
    if (!target) {
      return false;
    }
    target.classList.remove('modal-bbox-draw-active');
    if (target._fullLayout && target._fullLayout.dragmode === 'pan') {
      return true;
    }
    const panButton = target.querySelector(
      '.modebar-btn[data-attr="dragmode"][data-val="pan"]'
    );
    if (panButton) {
      panButton.click();
      return true;
    }
    if (window.Plotly && typeof window.Plotly.relayout === 'function') {
      window.Plotly.relayout(target, { dragmode: 'pan' });
      return true;
    }
    return false;
  }

  function setDrawModeImmediately() {
    const graph = graphElement();
    if (!graph) {
      return;
    }
    graph.classList.add('modal-bbox-draw-active');
    const drawButton = graph.querySelector(
      '.modebar-btn[data-attr="dragmode"][data-val="drawrect"]'
    );
    if (drawButton) {
      drawButton.click();
    } else if (window.Plotly && typeof window.Plotly.relayout === 'function') {
      window.Plotly.relayout(graph, { dragmode: 'drawrect' });
    }
    if (typeof graph.on === 'function' && graph.dataset.bboxDrawResetBound !== 'true') {
      graph.dataset.bboxDrawResetBound = 'true';
      graph.on('plotly_relayout', function (payload) {
        const update = payload || {};
        const keys = Object.keys(update);
        const completedShape = keys.some(function (key) {
          return key === 'shapes' || /^shapes\[\d+\]\./.test(key);
        });
        if (completedShape || (update.dragmode && update.dragmode !== 'drawrect')) {
          graph.classList.remove('modal-bbox-draw-active');
        }
      });
    }
  }

  function pointForClick(clickData) {
    const points = clickData && clickData.points;
    return Array.isArray(points) && points.length && points[0] && typeof points[0] === 'object'
      ? points[0]
      : null;
  }

  function traceForPoint(point, figure) {
    const curveNumber = coerceIndex(point && point.curveNumber);
    const traces = figure && figure.data;
    if (curveNumber === null || !Array.isArray(traces) || curveNumber < 0 || curveNumber >= traces.length) {
      return null;
    }
    const trace = traces[curveNumber];
    return trace && typeof trace === 'object' ? trace : null;
  }

  function boxIndexFromGraphClick(clickData, figure, expectedTraceName) {
    const point = pointForClick(clickData);
    const trace = traceForPoint(point, figure);
    if (!point || !trace || trace.name !== expectedTraceName) {
      return null;
    }
    return coerceIndex(point.customdata);
  }

  function cloneValue(value) {
    if (value === null || value === undefined) {
      return value;
    }
    return JSON.parse(JSON.stringify(value));
  }

  function safeNumber(value, fallback) {
    if (value === null || value === undefined || value === '') {
      return fallback;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function roundTo(value, places) {
    const factor = Math.pow(10, places);
    return Math.round((value + Number.EPSILON) * factor) / factor;
  }

  function axisMetaFromFigure(figure) {
    const layout = figure && typeof figure.layout === 'object' ? figure.layout : {};
    const meta = layout.meta && typeof layout.meta === 'object' ? layout.meta : {};
    const xaxis = layout.xaxis && typeof layout.xaxis === 'object' ? layout.xaxis : {};
    const yaxis = layout.yaxis && typeof layout.yaxis === 'object' ? layout.yaxis : {};
    const xRange = Array.isArray(xaxis.range) ? xaxis.range : [];
    const yRange = Array.isArray(yaxis.range) ? yaxis.range : [];
    const xMin = safeNumber(meta.x_min, safeNumber(xRange[0], 0));
    let xMax = safeNumber(meta.x_max, safeNumber(xRange[1], 1));
    const yMin = safeNumber(meta.y_min, safeNumber(yRange[0], 0));
    let yMax = safeNumber(meta.y_max, safeNumber(yRange[1], 1));
    if (xMax <= xMin) {
      xMax = xMin + 1;
    }
    if (yMax <= yMin) {
      yMax = yMin + 1;
    }
    return {
      x_to_seconds: safeNumber(meta.x_to_seconds, 1) || 1,
      y_to_hz: safeNumber(meta.y_to_hz, 1) || 1,
      x_min: xMin,
      x_max: xMax,
      y_min: yMin,
      y_max: yMax,
    };
  }

  function extentToShape(extent, axisMeta) {
    if (!extent || typeof extent !== 'object' || !extent.type || extent.type === 'clip') {
      return null;
    }
    const xFactor = axisMeta.x_to_seconds || 1;
    const yFactor = axisMeta.y_to_hz || 1;
    const shape = { type: 'rect' };
    if (extent.type === 'time_range' || extent.type === 'time_freq_box') {
      const timeStart = safeNumber(extent.time_start_sec, null);
      const timeEnd = safeNumber(extent.time_end_sec, null);
      if (timeStart === null || timeEnd === null) {
        return null;
      }
      shape.x0 = timeStart / xFactor;
      shape.x1 = timeEnd / xFactor;
    } else {
      shape.x0 = axisMeta.x_min;
      shape.x1 = axisMeta.x_max;
    }
    if (extent.type === 'freq_range' || extent.type === 'time_freq_box') {
      const freqMin = safeNumber(extent.freq_min_hz, null);
      const freqMax = safeNumber(extent.freq_max_hz, null);
      if (freqMin === null || freqMax === null) {
        return null;
      }
      shape.y0 = freqMin / yFactor;
      shape.y1 = freqMax / yFactor;
    } else {
      shape.y0 = axisMeta.y_min;
      shape.y1 = axisMeta.y_max;
    }
    if ([shape.x0, shape.x1, shape.y0, shape.y1].some(function (value) { return value === null; })) {
      return null;
    }
    const x0 = clamp(Math.min(shape.x0, shape.x1), axisMeta.x_min, axisMeta.x_max);
    const x1 = clamp(Math.max(shape.x0, shape.x1), axisMeta.x_min, axisMeta.x_max);
    const y0 = clamp(Math.min(shape.y0, shape.y1), axisMeta.y_min, axisMeta.y_max);
    const y1 = clamp(Math.max(shape.y0, shape.y1), axisMeta.y_min, axisMeta.y_max);
    return { type: 'rect', x0: x0, x1: x1, y0: y0, y1: y1 };
  }

  function shapeToExtent(shape, axisMeta) {
    if (!shape || typeof shape !== 'object') {
      return null;
    }
    let x0 = safeNumber(shape.x0, null);
    let x1 = safeNumber(shape.x1, null);
    let y0 = safeNumber(shape.y0, null);
    let y1 = safeNumber(shape.y1, null);
    if ([x0, x1, y0, y1].some(function (value) { return value === null; })) {
      return null;
    }
    const rawX0 = x0;
    const rawX1 = x1;
    const rawY0 = y0;
    const rawY1 = y1;
    x0 = clamp(Math.min(rawX0, rawX1), axisMeta.x_min, axisMeta.x_max);
    x1 = clamp(Math.max(rawX0, rawX1), axisMeta.x_min, axisMeta.x_max);
    y0 = clamp(Math.min(rawY0, rawY1), axisMeta.y_min, axisMeta.y_max);
    y1 = clamp(Math.max(rawY0, rawY1), axisMeta.y_min, axisMeta.y_max);
    const xSpan = Math.max(1e-9, axisMeta.x_max - axisMeta.x_min);
    const ySpan = Math.max(1e-9, axisMeta.y_max - axisMeta.y_min);
    if ((x1 - x0) < Math.max(1e-9, xSpan * 1e-4) || (y1 - y0) < Math.max(1e-9, ySpan * 1e-4)) {
      return null;
    }
    const fullX = Math.abs((x1 - x0) - xSpan) <= 0.005 * xSpan;
    const fullY = Math.abs((y1 - y0) - ySpan) <= 0.005 * ySpan;
    if (fullX && fullY) {
      return { type: 'clip' };
    }
    if (fullY) {
      return {
        type: 'time_range',
        time_start_sec: Math.max(0, roundTo(x0 * axisMeta.x_to_seconds, 3)),
        time_end_sec: Math.max(0, roundTo(x1 * axisMeta.x_to_seconds, 3)),
      };
    }
    if (fullX) {
      return {
        type: 'freq_range',
        freq_min_hz: Math.max(0, roundTo(y0 * axisMeta.y_to_hz, 3)),
        freq_max_hz: Math.max(0, roundTo(y1 * axisMeta.y_to_hz, 3)),
      };
    }
    return {
      type: 'time_freq_box',
      time_start_sec: Math.max(0, roundTo(x0 * axisMeta.x_to_seconds, 3)),
      time_end_sec: Math.max(0, roundTo(x1 * axisMeta.x_to_seconds, 3)),
      freq_min_hz: Math.max(0, roundTo(y0 * axisMeta.y_to_hz, 3)),
      freq_max_hz: Math.max(0, roundTo(y1 * axisMeta.y_to_hz, 3)),
    };
  }

  function shapeSignature(shape) {
    if (!shape || typeof shape !== 'object') {
      return null;
    }
    const values = [shape.x0, shape.x1, shape.y0, shape.y1].map(function (value) {
      return safeNumber(value, null);
    });
    if (values.some(function (value) { return value === null; })) {
      return null;
    }
    return [
      roundTo(Math.min(values[0], values[1]), 6),
      roundTo(Math.max(values[0], values[1]), 6),
      roundTo(Math.min(values[2], values[3]), 6),
      roundTo(Math.max(values[2], values[3]), 6),
    ].join('|');
  }

  function boxSignature(box, axisMeta) {
    return shapeSignature(extentToShape(box && box.annotation_extent, axisMeta));
  }

  function normalizedBoxes(boxes) {
    return (Array.isArray(boxes) ? boxes : []).map(function (box) {
      const extent = box && typeof box.annotation_extent === 'object' ? box.annotation_extent : {};
      const normalizedExtent = { type: extent.type || null };
      ['time_start_sec', 'time_end_sec', 'freq_min_hz', 'freq_max_hz'].forEach(function (key) {
        const value = safeNumber(extent[key], null);
        if (value !== null) {
          normalizedExtent[key] = roundTo(value, 3);
        }
      });
      return {
        label: String((box && box.label) || '').trim(),
        tag: String((box && box.tag) || '').trim(),
        source: (box && box.source) || null,
        decision: (box && box.decision) || null,
        annotation_extent: normalizedExtent,
      };
    });
  }

  function boxesEquivalent(left, right) {
    return JSON.stringify(normalizedBoxes(left)) === JSON.stringify(normalizedBoxes(right));
  }

  function parseActiveTarget(activeTarget) {
    if (activeTarget && typeof activeTarget === 'object') {
      return {
        label: String(activeTarget.label || '').trim(),
        allowExisting: Boolean(activeTarget.allow_existing),
      };
    }
    return {
      label: typeof activeTarget === 'string' ? activeTarget.trim() : '',
      allowExisting: false,
    };
  }

  // Keep browser-rendered box colors identical to Python's SHA-1 label palette.
  function sha1(message) {
    const utf8 = unescape(encodeURIComponent(message));
    const words = [];
    for (let index = 0; index < utf8.length; index += 1) {
      words[index >> 2] = (words[index >> 2] || 0) | utf8.charCodeAt(index) << (24 - (index % 4) * 8);
    }
    words[utf8.length >> 2] = (words[utf8.length >> 2] || 0) | 0x80 << (24 - (utf8.length % 4) * 8);
    words[((utf8.length + 8 >> 6) + 1) * 16 - 1] = utf8.length * 8;
    let h0 = 0x67452301;
    let h1 = 0xefcdab89;
    let h2 = 0x98badcfe;
    let h3 = 0x10325476;
    let h4 = 0xc3d2e1f0;
    for (let offset = 0; offset < words.length; offset += 16) {
      const schedule = new Array(80);
      for (let index = 0; index < 80; index += 1) {
        if (index < 16) {
          schedule[index] = words[offset + index] || 0;
        } else {
          const value = schedule[index - 3] ^ schedule[index - 8] ^ schedule[index - 14] ^ schedule[index - 16];
          schedule[index] = (value << 1) | (value >>> 31);
        }
      }
      let a = h0;
      let b = h1;
      let c = h2;
      let d = h3;
      let e = h4;
      for (let index = 0; index < 80; index += 1) {
        let f;
        let k;
        if (index < 20) {
          f = (b & c) | (~b & d);
          k = 0x5a827999;
        } else if (index < 40) {
          f = b ^ c ^ d;
          k = 0x6ed9eba1;
        } else if (index < 60) {
          f = (b & c) | (b & d) | (c & d);
          k = 0x8f1bbcdc;
        } else {
          f = b ^ c ^ d;
          k = 0xca62c1d6;
        }
        const rotated = (a << 5) | (a >>> 27);
        const temp = (rotated + f + e + k + schedule[index]) | 0;
        e = d;
        d = c;
        c = (b << 30) | (b >>> 2);
        b = a;
        a = temp;
      }
      h0 = (h0 + a) | 0;
      h1 = (h1 + b) | 0;
      h2 = (h2 + c) | 0;
      h3 = (h3 + d) | 0;
      h4 = (h4 + e) | 0;
    }
    return [h0, h1, h2, h3, h4].map(function (value) {
      return ('00000000' + (value >>> 0).toString(16)).slice(-8);
    }).join('');
  }

  function hsvToRgb(hue, saturation, value) {
    const sector = Math.floor(hue * 6);
    const fraction = hue * 6 - sector;
    const p = value * (1 - saturation);
    const q = value * (1 - fraction * saturation);
    const t = value * (1 - (1 - fraction) * saturation);
    const choices = [
      [value, t, p], [q, value, p], [p, value, t],
      [p, q, value], [t, p, value], [value, p, q],
    ];
    return choices[sector % 6].map(function (channel) { return Math.floor(channel * 255); });
  }

  function boxStyle(box) {
    const normalized = String((box && box.label) || '').trim().toLowerCase() || 'unlabeled';
    const digest = sha1(normalized);
    const rgb = hsvToRgb(
      (parseInt(digest.slice(0, 8), 16) % 360) / 360,
      0.64 + (parseInt(digest.slice(8, 10), 16) % 20) / 100,
      0.70 + (parseInt(digest.slice(10, 12), 16) % 18) / 100
    );
    const rgba = function (alpha) {
      return 'rgba(' + rgb[0] + ', ' + rgb[1] + ', ' + rgb[2] + ', ' + alpha + ')';
    };
    if (box && box.decision === 'rejected') {
      return { lineColor: rgba(0.98), lineDash: 'dot', fillColor: rgba(0.20) };
    }
    if (box && box.source === 'model') {
      return { lineColor: rgba(0.95), lineDash: 'dash', fillColor: rgba(0.14) };
    }
    return { lineColor: rgba(0.95), lineDash: 'solid', fillColor: rgba(0.18) };
  }

  function leafLabel(label) {
    const parts = String(label || '').split('>').map(function (part) { return part.trim(); }).filter(Boolean);
    return parts.length ? parts[parts.length - 1] : 'Unlabeled';
  }

  function hoverNumber(value, suffix) {
    const number = safeNumber(value, null);
    return number === null ? 'n/a' : Number(number.toPrecision(3)) + suffix;
  }

  function boxHoverText(box, rect) {
    const extent = box && typeof box.annotation_extent === 'object' ? box.annotation_extent : {};
    return 'Edit box<br>' +
      'Classification: ' + ((box && box.label) || 'Unlabeled') + '<br>' +
      'Tag: ' + ((box && box.tag) || 'No tag') + '<br>' +
      'Time: ' + hoverNumber(extent.time_start_sec !== undefined ? extent.time_start_sec : rect.x0, 's') +
      ' - ' + hoverNumber(extent.time_end_sec !== undefined ? extent.time_end_sec : rect.x1, 's') + '<br>' +
      'Frequency: ' + hoverNumber(extent.freq_min_hz !== undefined ? extent.freq_min_hz : rect.y0, 'Hz') +
      ' - ' + hoverNumber(extent.freq_max_hz !== undefined ? extent.freq_max_hz : rect.y1, 'Hz') +
      '<extra></extra>';
  }

  function applyBoxesToFigure(figure, boxes) {
    if (!figure || typeof figure !== 'object') {
      return figure;
    }
    const nextFigure = Object.assign({}, figure);
    const layout = Object.assign({}, figure.layout || {});
    const axisMeta = axisMetaFromFigure(figure);
    const xSpan = Math.max(1e-9, axisMeta.x_max - axisMeta.x_min);
    const ySpan = Math.max(1e-9, axisMeta.y_max - axisMeta.y_min);
    const existingShapes = Array.isArray(layout.shapes) ? layout.shapes : [];
    let markerShape = existingShapes.find(function (shape) {
      return shape && (shape.name === 'playback-marker' || (shape.type === 'line' && shape.yref === 'paper'));
    });
    markerShape = markerShape || {
      type: 'line', x0: 0, x1: 0, y0: 0, y1: 1, yref: 'paper', editable: false,
      name: 'playback-marker', line: { color: 'rgba(255, 0, 0, 0)', width: 2, dash: 'solid' },
    };

    const prepared = [];
    (Array.isArray(boxes) ? boxes : []).forEach(function (box, boxIndex) {
      if (!box || typeof box !== 'object') {
        return;
      }
      const shape = extentToShape(box.annotation_extent, axisMeta);
      if (!shape) {
        return;
      }
      prepared.push({ boxIndex: boxIndex, box: box, style: boxStyle(box), rect: shape });
    });

    const allRects = prepared.map(function (entry) { return entry.rect; });
    const placedHandles = [];
    const edgePadX = Math.max(1e-6, 0.012 * xSpan);
    const edgePadY = Math.max(1e-6, 0.014 * ySpan);
    let xBoundMin = axisMeta.x_min + edgePadX;
    let xBoundMax = axisMeta.x_max - edgePadX;
    let yBoundMin = axisMeta.y_min + edgePadY;
    let yBoundMax = axisMeta.y_max - edgePadY;
    if (xBoundMax <= xBoundMin) {
      xBoundMin = axisMeta.x_min;
      xBoundMax = axisMeta.x_max;
    }
    if (yBoundMax <= yBoundMin) {
      yBoundMin = axisMeta.y_min;
      yBoundMax = axisMeta.y_max;
    }
    const pointInRect = function (x, y, rect, padX, padY) {
      return x >= rect.x0 - padX && x <= rect.x1 + padX && y >= rect.y0 - padY && y <= rect.y1 + padY;
    };
    const handleIsFree = function (x, y, rectPadX, rectPadY) {
      return !allRects.some(function (rect) { return pointInRect(x, y, rect, rectPadX, rectPadY); }) &&
        !placedHandles.some(function (handle) {
          return Math.abs(x - handle[0]) <= 0.020 * xSpan && Math.abs(y - handle[1]) <= 0.030 * ySpan;
        });
    };
    const chooseDeleteHandle = function (rect, boxIndex) {
      const candidates = [
        [rect.x1 + 0.012 * xSpan, rect.y1 + 0.012 * ySpan],
        [rect.x0 - 0.012 * xSpan, rect.y1 + 0.012 * ySpan],
        [rect.x1 + 0.012 * xSpan, rect.y0 - 0.012 * ySpan],
        [rect.x0 - 0.012 * xSpan, rect.y0 - 0.012 * ySpan],
        [rect.x1 - 0.008 * xSpan, rect.y1 + 0.010 * ySpan],
        [rect.x0 + 0.008 * xSpan, rect.y1 + 0.010 * ySpan],
      ];
      for (let index = 0; index < candidates.length; index += 1) {
        const x = clamp(candidates[index][0], xBoundMin, xBoundMax);
        const y = clamp(candidates[index][1], yBoundMin, yBoundMax);
        if (handleIsFree(x, y, 0.002 * xSpan, 0.002 * ySpan)) {
          return [x, y];
        }
      }
      const rowOffset = boxIndex % 3;
      for (let rowStep = 0; rowStep < 10; rowStep += 1) {
        const row = (rowOffset + rowStep) % 10;
        const y = clamp(yBoundMax - row * 0.08 * ySpan, yBoundMin, yBoundMax);
        for (let column = 0; column < 12; column += 1) {
          const x = clamp(xBoundMax - column * 0.06 * xSpan, xBoundMin, xBoundMax);
          if (handleIsFree(x, y, 0.002 * xSpan, 0.002 * ySpan)) {
            return [x, y];
          }
        }
      }
      return [
        clamp(rect.x1 - 0.006 * xSpan, xBoundMin, xBoundMax),
        clamp(rect.y1 - 0.006 * ySpan - (boxIndex % 6) * 0.022 * ySpan, yBoundMin, yBoundMax),
      ];
    };
    const chooseEditHandle = function (rect) {
      const midY = rect.y0 + (rect.y1 - rect.y0) / 2;
      const candidates = [
        [rect.x1 + 0.018 * xSpan, midY],
        [rect.x1 - 0.026 * xSpan, rect.y0 - 0.022 * ySpan],
        [rect.x0 + 0.026 * xSpan, rect.y0 - 0.022 * ySpan],
        [rect.x0 - 0.018 * xSpan, midY],
        [rect.x1 - 0.026 * xSpan, rect.y1 + 0.022 * ySpan],
        [rect.x0 + 0.026 * xSpan, rect.y1 + 0.022 * ySpan],
      ];
      for (let index = 0; index < candidates.length; index += 1) {
        const x = clamp(candidates[index][0], xBoundMin, xBoundMax);
        const y = clamp(candidates[index][1], yBoundMin, yBoundMax);
        if (!pointInRect(x, y, rect, 0.004 * xSpan, 0.004 * ySpan) &&
            !placedHandles.some(function (handle) {
              return Math.abs(x - handle[0]) <= 0.020 * xSpan && Math.abs(y - handle[1]) <= 0.030 * ySpan;
            })) {
          return [x, y];
        }
      }
      return [clamp((rect.x0 + rect.x1) / 2, xBoundMin, xBoundMax), clamp((rect.y0 + rect.y1) / 2, yBoundMin, yBoundMax)];
    };

    const shapes = [markerShape];
    const annotations = [];
    const deleteX = [];
    const deleteY = [];
    const deleteIndices = [];
    const editX = [];
    const editY = [];
    const editIndices = [];
    const editHover = [];
    prepared.forEach(function (entry) {
      const rect = entry.rect;
      const style = entry.style;
      shapes.push({
        type: 'rect', x0: rect.x0, x1: rect.x1, y0: rect.y0, y1: rect.y1,
        line: { color: style.lineColor, width: 2, dash: style.lineDash },
        fillcolor: style.fillColor, editable: true, layer: 'above',
      });
      let annotationText = 'Box ' + (entry.boxIndex + 1) + ': ' + leafLabel(entry.box.label);
      if (entry.box.tag) {
        annotationText += ' · ' + entry.box.tag;
      }
      annotations.push({
        x: clamp(rect.x0 + 0.004 * xSpan, axisMeta.x_min, axisMeta.x_max),
        y: clamp(rect.y1 - 0.004 * ySpan, axisMeta.y_min, axisMeta.y_max),
        xref: 'x', yref: 'y', xanchor: 'left', yanchor: 'top', showarrow: false,
        editable: false, text: annotationText, font: { size: 11, color: style.lineColor },
        bgcolor: 'rgba(255,255,255,0.78)', borderpad: 2,
      });
      const deleteHandle = chooseDeleteHandle(rect, entry.boxIndex);
      placedHandles.push(deleteHandle);
      deleteX.push(deleteHandle[0]);
      deleteY.push(deleteHandle[1]);
      deleteIndices.push(entry.boxIndex);
      const editHandle = chooseEditHandle(rect);
      editX.push(editHandle[0]);
      editY.push(editHandle[1]);
      editIndices.push(entry.boxIndex);
      editHover.push(boxHoverText(entry.box, rect));
    });

    layout.shapes = shapes;
    layout.annotations = annotations;
    layout.dragmode = 'pan';
    layout.editrevision = 'bbox-client-' + Date.now();
    const data = (Array.isArray(figure.data) ? figure.data : []).filter(function (trace) {
      return !trace || (trace.name !== DELETE_TRACE && trace.name !== EDIT_TRACE);
    });
    if (editIndices.length) {
      data.push({
        type: 'scatter', mode: 'markers+text', name: EDIT_TRACE, showlegend: false,
        x: editX, y: editY, customdata: editIndices, text: editIndices.map(function () { return '✎'; }),
        textposition: 'middle center', textfont: { size: 12, color: '#ffffff' },
        marker: { size: 22, opacity: 0.95, color: 'rgba(13, 110, 253, 0.94)', line: { color: '#ffffff', width: 1 }, symbol: 'square' },
        opacity: 1,
        selectedpoints: [],
        selected: {
          marker: { opacity: 0.92, color: 'rgba(13, 110, 253, 0.96)', line: { color: '#ffffff', width: 1 } },
          textfont: { color: '#ffffff' },
        },
        unselected: {
          marker: { opacity: 0.95, color: 'rgba(13, 110, 253, 0.94)', line: { color: '#ffffff', width: 1 } },
          textfont: { color: '#ffffff' },
        },
        hovertemplate: editHover,
        cliponaxis: true,
      });
    }
    if (deleteIndices.length) {
      data.push({
        type: 'scatter', mode: 'markers+text', name: DELETE_TRACE, showlegend: false,
        x: deleteX, y: deleteY, customdata: deleteIndices, text: deleteIndices.map(function () { return '×'; }),
        textposition: 'middle center', textfont: { size: 12, color: '#ffffff' },
        marker: { size: 18, opacity: 1, color: 'rgba(220, 53, 69, 0.98)', line: { color: '#ffffff', width: 1 }, symbol: 'square' },
        opacity: 1,
        selectedpoints: [],
        selected: {
          marker: { opacity: 1, color: 'rgba(220, 53, 69, 0.98)', line: { color: '#ffffff', width: 1 } },
          textfont: { color: '#ffffff' },
        },
        unselected: {
          marker: { opacity: 1, color: 'rgba(220, 53, 69, 0.98)', line: { color: '#ffffff', width: 1 } },
          textfont: { color: '#ffffff' },
        },
        hovertemplate: 'Delete box<extra></extra>',
        cliponaxis: true,
      });
    }
    nextFigure.data = data;
    nextFigure.layout = layout;
    setPanModeImmediately();
    return nextFigure;
  }

  function updateBoxesFromRelayout(relayoutData, boxes, activeTarget, axisMeta) {
    if (!relayoutData || typeof relayoutData !== 'object') {
      return null;
    }
    const keys = Object.keys(relayoutData);
    if (keys.length && keys.every(function (key) { return key === 'shapes[0].x0' || key === 'shapes[0].x1'; })) {
      return null;
    }
    const target = parseActiveTarget(activeTarget);
    const existingLabels = boxes.map(function (box) { return String((box && box.label) || '').trim(); });
    const addMode = Boolean(target.label) && (target.allowExisting || existingLabels.indexOf(target.label) < 0);
    let updated = false;
    let forceResync = false;
    let clearActive = false;
    const payloadShapes = Array.isArray(relayoutData.shapes)
      ? relayoutData.shapes.filter(function (shape) { return shape && shape.type === 'rect'; })
      : null;

    if (payloadShapes && addMode) {
      const existingSignatures = new Set(boxes.map(function (box) { return boxSignature(box, axisMeta); }).filter(Boolean));
      const newShape = payloadShapes.find(function (shape) {
        const signature = shapeSignature(shape);
        return signature && !existingSignatures.has(signature);
      });
      const extent = shapeToExtent(newShape, axisMeta);
      if (extent && extent.type !== 'clip') {
        boxes.push({ label: target.label, annotation_extent: extent, source: 'manual', decision: 'added' });
        updated = true;
        clearActive = true;
      }
    } else if (payloadShapes && !addMode) {
      const payloadCounts = {};
      payloadShapes.forEach(function (shape) {
        const signature = shapeSignature(shape);
        if (signature) {
          payloadCounts[signature] = (payloadCounts[signature] || 0) + 1;
        }
      });
      const keptCounts = {};
      boxes = boxes.filter(function (box) {
        const signature = boxSignature(box, axisMeta);
        if (!signature) {
          return true;
        }
        const used = keptCounts[signature] || 0;
        if (used < (payloadCounts[signature] || 0)) {
          keptCounts[signature] = used + 1;
          return true;
        }
        updated = true;
        return false;
      });
      if (payloadShapes.length > boxes.length) {
        forceResync = true;
      }
    }

    const coordUpdates = {};
    keys.forEach(function (key) {
      const match = String(key).match(/^shapes\[(\d+)\]\.(x0|x1|y0|y1)$/);
      if (!match || Number(match[1]) <= 0) {
        return;
      }
      const boxIndex = Number(match[1]) - 1;
      coordUpdates[boxIndex] = coordUpdates[boxIndex] || {};
      coordUpdates[boxIndex][match[2]] = safeNumber(relayoutData[key], null);
    });
    Object.keys(coordUpdates).forEach(function (rawIndex) {
      const boxIndex = Number(rawIndex);
      const updates = coordUpdates[rawIndex];
      if (addMode) {
        if (boxIndex < boxes.length || !target.label || !['x0', 'x1', 'y0', 'y1'].every(function (key) { return updates[key] !== null && updates[key] !== undefined; })) {
          return;
        }
        const extent = shapeToExtent(Object.assign({ type: 'rect' }, updates), axisMeta);
        if (extent && extent.type !== 'clip') {
          boxes.push({ label: target.label, annotation_extent: extent, source: 'manual', decision: 'added' });
          updated = true;
          clearActive = true;
        }
        return;
      }
      if (boxIndex >= boxes.length) {
        forceResync = true;
        return;
      }
      const shape = extentToShape(boxes[boxIndex].annotation_extent, axisMeta) || { type: 'rect' };
      ['x0', 'x1', 'y0', 'y1'].forEach(function (key) {
        if (updates[key] !== null && updates[key] !== undefined) {
          shape[key] = updates[key];
        }
      });
      const extent = shapeToExtent(shape, axisMeta);
      if (extent && extent.type !== 'clip' && JSON.stringify(extent) !== JSON.stringify(boxes[boxIndex].annotation_extent)) {
        boxes[boxIndex] = Object.assign({}, boxes[boxIndex], { annotation_extent: extent });
        updated = true;
      }
    });
    return updated || forceResync ? { boxes: boxes, updated: updated, clearActive: clearActive } : null;
  }

  function editorValues(boxIndex, box) {
    const extent = box && box.annotation_extent && typeof box.annotation_extent === 'object'
      ? box.annotation_extent
      : {};
    const source = box.source || 'manual';
    const decision = box.decision || 'added';
    return [
      true,
      boxIndex,
      box.label || null,
      box.tag || null,
      extent.time_start_sec,
      extent.time_end_sec,
      extent.freq_min_hz,
      extent.freq_max_hz,
      'Box ' + (boxIndex + 1) + ' | source: ' + source + ' | state: ' + decision,
      '',
    ];
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    bboxInteractions: Object.assign({}, (window.dash_clientside || {}).bboxInteractions, {
      applyBoxesToFigure: function (figure, boxes) {
        return applyBoxesToFigure(figure, boxes);
      },

      activateDraw: function (
        _addBoxClicks,
        profile,
        mode,
        currentItemId,
        bboxStore,
        modalItem,
        unsavedStore
      ) {
        const context = dashContext();
        const triggeredId = parseTriggeredId(context);
        if (
          mode === 'explore' ||
          !currentItemId ||
          !profileIsComplete(profile) ||
          !triggeredId ||
          typeof triggeredId !== 'object' ||
          triggeredId.type !== 'modal-label-add-box' ||
          Number(triggeredValue(context) || 0) <= 0
        ) {
          return noUpdates(2);
        }
        const label = String(triggeredId.label || '').trim();
        if (!label) {
          return noUpdates(2);
        }
        setDrawModeImmediately();
        const store = bboxStore && typeof bboxStore === 'object' ? bboxStore : {};
        return [
          { label: label, allow_existing: true },
          {
            kind: 'draw',
            phase: 'drawing',
            item_id: currentItemId,
            started_at: Date.now(),
            boxes: cloneValue(store.item_id === currentItemId && Array.isArray(store.boxes) ? store.boxes : []),
            item: cloneValue(modalItem),
            unsaved: cloneValue(unsavedStore) || { dirty: false, item_id: currentItemId },
          },
        ];
      },

      updateBoxesFromGraph: function (
        relayoutData,
        bboxStore,
        figure,
        activeBoxLabel,
        currentItemId,
        mode,
        profile,
        interactionStore
      ) {
        const noChange = noUpdates(5);
        if (
          mode === 'explore' ||
          !currentItemId ||
          !profileIsComplete(profile) ||
          !relayoutData ||
          typeof relayoutData !== 'object'
        ) {
          return noChange;
        }
        const store = bboxStore && typeof bboxStore === 'object' ? bboxStore : {};
        const boxes = store.item_id === currentItemId && Array.isArray(store.boxes)
          ? cloneValue(store.boxes)
          : [];
        const result = updateBoxesFromRelayout(
          relayoutData,
          boxes,
          activeBoxLabel,
          axisMetaFromFigure(figure)
        );
        if (!result) {
          return noChange;
        }
        const nextStore = Object.assign({}, store, { item_id: currentItemId, boxes: result.boxes });
        let nextInteraction = noUpdate();
        if (
          interactionStore &&
          interactionStore.kind === 'draw' &&
          interactionStore.item_id === currentItemId
        ) {
          nextInteraction = Object.assign({}, interactionStore, {
            phase: 'drawn',
            completed_at: Date.now(),
          });
        }
        return [
          nextStore,
          applyBoxesToFigure(figure, result.boxes),
          result.clearActive ? null : noUpdate(),
          result.updated ? { dirty: true, item_id: currentItemId } : noUpdate(),
          nextInteraction,
        ];
      },

      deleteBox: function (
        clickData,
        bboxStore,
        figure,
        currentItemId,
        mode,
        profile,
        interactionStore,
        unsavedStore
      ) {
        const noChange = noUpdates(6);
        if (mode === 'explore' || !currentItemId || !profileIsComplete(profile)) {
          return noChange;
        }
        const boxIndex = boxIndexFromGraphClick(clickData, figure, DELETE_TRACE);
        const store = bboxStore && typeof bboxStore === 'object' ? bboxStore : {};
        const boxes = Array.isArray(store.boxes) ? store.boxes.slice() : [];
        if (
          boxIndex === null ||
          store.item_id !== currentItemId ||
          boxIndex < 0 ||
          boxIndex >= boxes.length
        ) {
          return noChange;
        }
        boxes.splice(boxIndex, 1);
        const nextStore = Object.assign({}, store, { item_id: currentItemId, boxes: boxes });
        const rollsBackDraw = Boolean(
          interactionStore &&
          interactionStore.kind === 'draw' &&
          interactionStore.phase === 'drawn' &&
          interactionStore.item_id === currentItemId &&
          unsavedStore &&
          unsavedStore.dirty === true &&
          boxesEquivalent(boxes, interactionStore.boxes)
        );
        const priorUnsaved = interactionStore && interactionStore.unsaved;
        const restoredUnsaved = priorUnsaved && typeof priorUnsaved === 'object'
          ? priorUnsaved
          : { dirty: false, item_id: currentItemId };
        const restoredItem = rollsBackDraw && interactionStore.item && typeof interactionStore.item === 'object'
          ? interactionStore.item
          : noUpdate();
        const nextUnsaved = rollsBackDraw
          ? restoredUnsaved
          : { dirty: true, item_id: currentItemId };
        const nextInteraction = rollsBackDraw ? null : noUpdate();
        return [
          nextStore,
          applyBoxesToFigure(figure, boxes),
          noUpdate(),
          nextUnsaved,
          restoredItem,
          nextInteraction,
        ];
      },

      openEditor: function (
        graphClickData,
        _editClicks,
        bboxStore,
        figure,
        currentItemId,
        mode,
        profile
      ) {
        const noChange = noUpdates(10);
        if (mode === 'explore' || !currentItemId || !profileIsComplete(profile)) {
          return noChange;
        }
        const context = dashContext();
        const triggeredId = parseTriggeredId(context);
        let boxIndex = null;
        if (triggeredId === 'modal-image-graph') {
          boxIndex = boxIndexFromGraphClick(graphClickData, figure, EDIT_TRACE);
        } else if (
          triggeredId &&
          typeof triggeredId === 'object' &&
          triggeredId.type === 'modal-bbox-edit-btn' &&
          Number(triggeredValue(context) || 0) > 0
        ) {
          boxIndex = coerceIndex(triggeredId.index);
        }
        const store = bboxStore && typeof bboxStore === 'object' ? bboxStore : {};
        const boxes = Array.isArray(store.boxes) ? store.boxes : [];
        if (
          boxIndex === null ||
          store.item_id !== currentItemId ||
          boxIndex < 0 ||
          boxIndex >= boxes.length ||
          !boxes[boxIndex] ||
          typeof boxes[boxIndex] !== 'object'
        ) {
          return noChange;
        }
        return editorValues(boxIndex, boxes[boxIndex]);
      },
    }),
  });
})();
