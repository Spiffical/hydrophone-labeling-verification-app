// Hover behaviour for boxes on the modal spectrogram: only the hovered box
// shows its × and ✎ handles and a details tooltip, and its row in the box list
// (bbox_list.js) is highlighted.
(function () {
  const EDIT_TRACE_NAME = '__bbox_edit_handle__';
  const DELETE_TRACE_NAME = '__bbox_delete_handle__';
  const HANDLE_GLYPHS = { '✎': EDIT_TRACE_NAME, '×': DELETE_TRACE_NAME };
  // Pixels around a box and its handles that keep them shown, so the pointer
  // can travel from the box to its × or ✎.
  const ZONE_PAD = 10;

  // Read by bbox_clientside.js: graph clicks only act on the shown handles.
  const hover = { activeBox: null };
  window.bboxHover = hover;
  let activeZone = null;
  let tooltip = null;

  function plotOf(graph) {
    return graph.querySelector('.js-plotly-plot') || graph;
  }

  function within(rect, event, pad) {
    return (
      event.clientX >= rect.left - pad && event.clientX <= rect.right + pad &&
      event.clientY >= rect.top - pad && event.clientY <= rect.bottom + pad
    );
  }

  // Handle traces have no name in the DOM, so recognise them by their glyph.
  function handleTraces(plot) {
    const traces = [];
    plot.querySelectorAll('.scatterlayer .trace').forEach(function (element) {
      const glyph = element.querySelector('text');
      const name = glyph ? HANDLE_GLYPHS[String(glyph.textContent || '').trim()] : null;
      element.classList.toggle('modal-bbox-handle-trace', Boolean(name));
      element.classList.toggle('modal-bbox-handle-trace--edit', name === EDIT_TRACE_NAME);
      if (name) {
        const data = (Array.isArray(plot.data) ? plot.data : []).find(function (trace) {
          return trace && trace.name === name;
        });
        traces.push({
          name: name,
          // Point elements are in data order; customdata holds each point's box index.
          owners: data && Array.isArray(data.customdata) ? data.customdata : [],
          markers: Array.from(element.querySelectorAll('.points .point')),
          texts: Array.from(element.querySelectorAll('.text .textpoint')),
        });
      }
    });
    return traces;
  }

  // Show only the given box's handles; returns the shown handle rectangles.
  function showHandlesFor(plot, index) {
    const rects = [];
    handleTraces(plot).forEach(function (trace) {
      [trace.markers, trace.texts].forEach(function (nodes) {
        nodes.forEach(function (node, point) {
          const visible = index !== null && Number(trace.owners[point]) === index;
          node.classList.toggle('is-visible', visible);
          if (visible && nodes === trace.markers) {
            rects.push(node.getBoundingClientRect());
          }
        });
      });
    });
    return rects;
  }

  // The box under the pointer, using the "bbox-<index>" shape names set by the
  // figure builders. Where boxes overlap, the smallest one wins.
  function boxAtPointer(plot, event) {
    const shapes = plot.layout && Array.isArray(plot.layout.shapes) ? plot.layout.shapes : [];
    // Boxes on other pages of a long clip lie outside the plot area.
    const area = plot.querySelector('.nsewdrag');
    if (area && !within(area.getBoundingClientRect(), event, 0)) {
      return null;
    }
    let best = null;
    plot.querySelectorAll('.shapelayer path[data-index]').forEach(function (path) {
      const shape = shapes[Number(path.getAttribute('data-index'))];
      const match = shape && /^bbox-(\d+)$/.exec(String(shape.name || ''));
      if (!match) {
        return;
      }
      const bounds = path.getBoundingClientRect();
      if (bounds.width < 4 || bounds.height < 4 || !within(bounds, event, 0)) {
        return;
      }
      const area = bounds.width * bounds.height;
      if (!best || area < best.area) {
        best = { index: Number(match[1]), bounds: bounds, area: area };
      }
    });
    return best;
  }

  // The × lets clicks through to Plotly (see bbox_panel.css), so show a
  // pointer on the plot while it is under the pointer.
  function setOverDelete(plot, event) {
    const trace = event && handleTraces(plot).find(function (t) { return t.name === DELETE_TRACE_NAME; });
    const over = Boolean(trace && trace.markers.some(function (node) {
      return node.classList.contains('is-visible') && within(node.getBoundingClientRect(), event, 2);
    }));
    plot.classList.toggle('modal-bbox-over-delete', over);
  }

  function hideTooltip() {
    if (tooltip) {
      tooltip.hidden = true;
    }
  }

  function showTooltip(box, handleRects) {
    const details = window.bboxPanel && window.bboxPanel.describeBox(box.index);
    if (!details) {
      hideTooltip();
      return;
    }
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.className = 'modal-bbox-tooltip';
      tooltip.setAttribute('role', 'tooltip');
      document.body.appendChild(tooltip);
    }
    tooltip.textContent = '';
    const title = document.createElement('div');
    title.className = 'modal-bbox-tooltip__title';
    title.textContent = details.title;
    // Boxes of a species without tags have none to show.
    if (details.tag) {
      title.textContent += ' · ';
      const tag = document.createElement('span');
      tag.className = 'modal-bbox-tooltip__tag' + (details.untagged ? ' is-untagged' : '');
      tag.textContent = details.tag;
      title.appendChild(tag);
    }
    const detail = document.createElement('div');
    detail.className = 'modal-bbox-tooltip__detail';
    detail.textContent = details.detail;
    tooltip.appendChild(title);
    tooltip.appendChild(detail);
    tooltip.hidden = false;

    // Prefer below the box, where it cannot cover the × and ✎ handles.
    const gap = 6;
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    const b = box.bounds;
    const candidates = [
      { left: b.left, top: b.bottom + gap },
      { left: b.left, top: b.top - height - gap },
      { left: b.left - width - gap, top: b.top },
    ];
    const fits = function (spot) {
      return spot.left >= gap && spot.top >= gap &&
        spot.left + width <= window.innerWidth - gap && spot.top + height <= window.innerHeight - gap;
    };
    const coversHandle = function (spot) {
      return handleRects.some(function (r) {
        return spot.left < r.right && spot.left + width > r.left && spot.top < r.bottom && spot.top + height > r.top;
      });
    };
    const spot = candidates.find(function (c) { return fits(c) && !coversHandle(c); })
      || candidates.find(fits) || candidates[0];
    tooltip.style.left = Math.max(gap, Math.min(spot.left, window.innerWidth - width - gap)) + 'px';
    tooltip.style.top = Math.max(gap, Math.min(spot.top, window.innerHeight - height - gap)) + 'px';
  }

  function setActiveBox(plot, box) {
    if (!box) {
      if (hover.activeBox !== null) {
        hover.activeBox = null;
        activeZone = null;
        showHandlesFor(plot, null);
      }
      setOverDelete(plot, null);
      hideTooltip();
      if (window.bboxPanel) {
        window.bboxPanel.highlightRow(null);
      }
      return;
    }
    const handleRects = showHandlesFor(plot, box.index);
    const zone = { left: box.bounds.left, top: box.bounds.top, right: box.bounds.right, bottom: box.bounds.bottom };
    handleRects.forEach(function (r) {
      zone.left = Math.min(zone.left, r.left);
      zone.top = Math.min(zone.top, r.top);
      zone.right = Math.max(zone.right, r.right);
      zone.bottom = Math.max(zone.bottom, r.bottom);
    });
    activeZone = { zone: zone, box: box, handleRects: handleRects };
    hover.activeBox = box.index;
    showTooltip(box, handleRects);
    if (window.bboxPanel) {
      window.bboxPanel.highlightRow(box.index);
    }
  }

  function onMove(graph, event) {
    const plot = plotOf(graph);
    // Stay out of the way while drawing.
    if (plot.classList.contains('modal-bbox-draw-active')) {
      setActiveBox(plot, null);
      return;
    }
    // Keep the hovered box while a button is held: a click on its × or ✎
    // often moves the pointer a pixel, and the click must still count.
    if (event.buttons) {
      return;
    }
    const box = boxAtPointer(plot, event);
    if (box) {
      if (box.index !== hover.activeBox || !activeZone ||
          box.bounds.left !== activeZone.box.bounds.left || box.bounds.top !== activeZone.box.bounds.top) {
        setActiveBox(plot, box);
      }
      setOverDelete(plot, event);
      return;
    }
    // Off the box but still near it (e.g. on its way to the ×): keep it active.
    if (!(activeZone && within(activeZone.zone, event, ZONE_PAD))) {
      setActiveBox(plot, null);
      return;
    }
    setOverDelete(plot, event);
  }

  function bindGraph(graph) {
    if (!graph || graph.dataset.bboxHoverBound === 'true') {
      return;
    }
    graph.dataset.bboxHoverBound = 'true';
    graph.addEventListener('mousemove', function (event) {
      onMove(graph, event);
    });
    graph.addEventListener('mouseleave', function (event) {
      // Pressing on the plot makes Plotly cover the page (its drag cover),
      // which "leaves" the graph. Keep the hovered box so the click on its ×
      // reaches deleteBox, and let go of it only if the button is released
      // off the plot.
      if (event.buttons) {
        document.addEventListener('mouseup', function (up) {
          if (!within(graph.getBoundingClientRect(), up, 0)) {
            setActiveBox(plotOf(graph), null);
          }
        }, { once: true, capture: true });
        return;
      }
      setActiveBox(plotOf(graph), null);
    });
    // Open the editor from the shown ✎ directly; it takes the click itself.
    // The × lets the click through to Plotly, whose click data reaches
    // deleteBox in bbox_clientside.js.
    graph.addEventListener('click', function (event) {
      if (hover.activeBox === null || !window.bboxPanel) {
        return;
      }
      const edit = handleTraces(plotOf(graph)).find(function (trace) { return trace.name === EDIT_TRACE_NAME; });
      const hit = edit && edit.markers.some(function (node) {
        return node.classList.contains('is-visible') && within(node.getBoundingClientRect(), event, 4);
      });
      if (hit && window.bboxPanel.openEditor(hover.activeBox)) {
        hideTooltip();
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);
  }

  let lastBoxCount = null;

  // Reference boxes (ref-box-<i>, e.g. the expert's boxes on a correction
  // dashboard) are only to look at. Shape editing (edits.shapePosition) makes
  // every shape draggable, so a drag starting inside one would move it
  // instead of panning or drawing a box; let the pointer through to the plot.
  function passThroughReferenceShapes(plot, shapes) {
    plot.querySelectorAll('.shapelayer path[data-index]').forEach(function (path) {
      const shape = shapes[Number(path.getAttribute('data-index'))];
      if (shape && /^ref-box-/.test(String(shape.name || '')) && path.style.pointerEvents !== 'none') {
        path.style.pointerEvents = 'none';
      }
    });
  }

  // Plotly redraws recreate the handle elements; reapply the current state.
  function scan() {
    const graph = document.getElementById('modal-image-graph');
    if (!graph) {
      hover.activeBox = null;
      activeZone = null;
      lastBoxCount = null;
      hideTooltip();
      return;
    }
    bindGraph(graph);
    const plot = plotOf(graph);
    const shapes = plot.layout && Array.isArray(plot.layout.shapes) ? plot.layout.shapes : [];
    passThroughReferenceShapes(plot, shapes);
    const boxCount = shapes.filter(function (shape) { return /^bbox-\d+$/.test(String((shape || {}).name || '')); }).length;
    if (lastBoxCount !== null && boxCount !== lastBoxCount) {
      // Adding or deleting a box renumbers the rest; start hover afresh.
      setActiveBox(plot, null);
    }
    lastBoxCount = boxCount;
    showHandlesFor(plot, hover.activeBox);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scan, { once: true });
  } else {
    scan();
  }

  const observer = new MutationObserver(function (mutations) {
    for (const mutation of mutations) {
      const target = mutation.target;
      if (
        target &&
        target.closest &&
        (target.closest('#modal-image-graph') || target.id === 'modal-image-graph')
      ) {
        requestAnimationFrame(scan);
        return;
      }
    }
  });

  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
