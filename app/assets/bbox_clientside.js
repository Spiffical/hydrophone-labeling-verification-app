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

  function customDataIndex(value) {
    return coerceIndex(value);
  }

  function updateCustomDataIndex(value, deletedIndex) {
    const current = customDataIndex(value);
    if (current === null) {
      return value;
    }
    const nextIndex = current > deletedIndex ? current - 1 : current;
    if (Array.isArray(value)) {
      const next = value.slice();
      next[0] = nextIndex;
      return next;
    }
    if (value && typeof value === 'object') {
      const next = Object.assign({}, value);
      if (next.box_index !== undefined) {
        next.box_index = nextIndex;
      } else {
        next.index = nextIndex;
      }
      return next;
    }
    return nextIndex;
  }

  function removeTracePoint(trace, deletedIndex) {
    const customData = Array.isArray(trace.customdata) ? trace.customdata : [];
    const pointIndex = customData.findIndex(function (value) {
      return customDataIndex(value) === deletedIndex;
    });
    if (pointIndex < 0) {
      return { trace: trace, pointIndex: null };
    }

    const nextTrace = Object.assign({}, trace);
    ['x', 'y', 'customdata', 'text'].forEach(function (field) {
      if (!Array.isArray(trace[field])) {
        return;
      }
      const values = trace[field].slice();
      values.splice(pointIndex, 1);
      nextTrace[field] = field === 'customdata'
        ? values.map(function (value) { return updateCustomDataIndex(value, deletedIndex); })
        : values;
    });
    if (Array.isArray(trace.hovertemplate)) {
      const hover = trace.hovertemplate.slice();
      hover.splice(pointIndex, 1);
      nextTrace.hovertemplate = hover;
    }
    nextTrace.selectedpoints = [];
    return { trace: nextTrace, pointIndex: pointIndex };
  }

  function removeBoxFromFigure(figure, boxIndex) {
    if (!figure || typeof figure !== 'object') {
      return figure;
    }
    const nextFigure = Object.assign({}, figure);
    const sourceData = Array.isArray(figure.data) ? figure.data : [];
    let overlayPointIndex = null;
    nextFigure.data = sourceData.map(function (trace) {
      if (!trace || (trace.name !== DELETE_TRACE && trace.name !== EDIT_TRACE)) {
        return trace;
      }
      const result = removeTracePoint(trace, boxIndex);
      if (trace.name === DELETE_TRACE && result.pointIndex !== null) {
        overlayPointIndex = result.pointIndex;
      }
      return result.trace;
    });

    const layout = Object.assign({}, figure.layout || {});
    const pointIndex = overlayPointIndex === null ? boxIndex : overlayPointIndex;
    if (Array.isArray(layout.shapes)) {
      const shapes = layout.shapes.slice();
      const rectPositions = [];
      shapes.forEach(function (shape, index) {
        if (shape && shape.type === 'rect') {
          rectPositions.push(index);
        }
      });
      if (pointIndex >= 0 && pointIndex < rectPositions.length) {
        shapes.splice(rectPositions[pointIndex], 1);
      }
      layout.shapes = shapes;
    }
    if (Array.isArray(layout.annotations)) {
      const annotations = layout.annotations.slice();
      if (pointIndex >= 0 && pointIndex < annotations.length) {
        annotations.splice(pointIndex, 1);
      }
      layout.annotations = annotations.map(function (annotation, index) {
        if (!annotation || typeof annotation !== 'object') {
          return annotation;
        }
        const next = Object.assign({}, annotation);
        next.text = String(next.text || '').replace(/^Box\s+\d+:/, 'Box ' + (index + 1) + ':');
        return next;
      });
    }
    layout.dragmode = 'pan';
    layout.editrevision = 'bbox-client-' + Date.now();
    nextFigure.layout = layout;

    const graph = graphElement();
    if (graph) {
      graph.classList.remove('modal-bbox-draw-active');
    }
    return nextFigure;
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
      activateDraw: function (_addBoxClicks, profile, mode) {
        const context = dashContext();
        const triggeredId = parseTriggeredId(context);
        if (
          mode === 'explore' ||
          !profileIsComplete(profile) ||
          !triggeredId ||
          typeof triggeredId !== 'object' ||
          triggeredId.type !== 'modal-label-add-box' ||
          Number(triggeredValue(context) || 0) <= 0
        ) {
          return noUpdate();
        }
        const label = String(triggeredId.label || '').trim();
        if (!label) {
          return noUpdate();
        }
        setDrawModeImmediately();
        return { label: label, allow_existing: true };
      },

      settleMode: function (bboxStore) {
        if (!bboxStore || typeof bboxStore !== 'object' || !bboxStore.item_id) {
          return noUpdate();
        }
        return setPanModeImmediately()
          ? { item_id: bboxStore.item_id, settled_at: Date.now() }
          : noUpdate();
      },

      deleteBox: function (clickData, bboxStore, figure, currentItemId, mode, profile) {
        const noChange = noUpdates(4);
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
        return [
          nextStore,
          removeBoxFromFigure(figure, boxIndex),
          noUpdate(),
          { dirty: true, item_id: currentItemId },
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
