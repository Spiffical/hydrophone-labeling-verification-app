// Resize boxes on the modal spectrogram from their edges and corners at any
// zoom. Plotly's shape editing (edits.shapePosition) ignores drags under 8 px
// and will not make a box 10 px wide or less, so a box under about 18 px on
// screen (a 2 s call on a 5-minute page) could not be tightened at all, and a
// press on a box of 10 px or less moved it instead. This takes over presses
// in a box's outer thirds (Plotly's resize zones) or just outside its edges,
// and reports the new size the way Plotly does (shapes[i].x1 ...), so
// bbox_clientside.js records it like any other resize. Only the dragged edges
// are reported. A press in a box's middle third still moves it (Plotly).
(function () {
  'use strict';

  // Reach beyond a box's edges, in screen pixels.
  const OUTSIDE_PX = 5;
  // Smallest box a resize leaves on screen.
  const MIN_PX = 2;
  // A press that moves less than this is a click, not a resize.
  const CLICK_PX = 1;
  const CURSOR_CLASSES = {
    ew: 'bbox-edge-ew',
    ns: 'bbox-edge-ns',
    nwse: 'bbox-edge-nwse',
    nesw: 'bbox-edge-nesw',
  };
  const BOX_SHAPE = /^bbox-\d+$/;

  let drag = null;

  // The edges of rect (client pixels) a press at (x, y) would take: each side's
  // outer third of the box, or up to OUTSIDE_PX beyond it. Null in the middle
  // third (a move) and away from the box.
  function edgesAt(rect, x, y) {
    if (x < rect.left - OUTSIDE_PX || x > rect.right + OUTSIDE_PX ||
        y < rect.top - OUTSIDE_PX || y > rect.bottom + OUTSIDE_PX) {
      return null;
    }
    const thirdX = (rect.right - rect.left) / 3;
    const thirdY = (rect.bottom - rect.top) / 3;
    const edges = {
      left: x <= rect.left + thirdX,
      right: x >= rect.right - thirdX,
      top: y <= rect.top + thirdY,
      bottom: y >= rect.bottom - thirdY,
    };
    if (edges.left && edges.right) {
      edges.left = Math.abs(x - rect.left) <= Math.abs(x - rect.right);
      edges.right = !edges.left;
    }
    if (edges.top && edges.bottom) {
      edges.top = Math.abs(y - rect.top) <= Math.abs(y - rect.bottom);
      edges.bottom = !edges.top;
    }
    return edges.left || edges.right || edges.top || edges.bottom ? edges : null;
  }

  // How far (x, y) is from the nearest of the given edges of rect.
  function edgeDistance(rect, edges, x, y) {
    const distances = [];
    if (edges.left) distances.push(Math.abs(x - rect.left));
    if (edges.right) distances.push(Math.abs(x - rect.right));
    if (edges.top) distances.push(Math.abs(y - rect.top));
    if (edges.bottom) distances.push(Math.abs(y - rect.bottom));
    return Math.min.apply(null, distances);
  }

  // Of boxes [{ name, rect }], the one whose edge is nearest to the press,
  // with the edges it would take; the smaller box on a tie. Edges outside
  // area (the plot, client pixels) are not offered.
  function pickEdge(boxes, x, y, area) {
    let best = null;
    (Array.isArray(boxes) ? boxes : []).forEach(function (box) {
      const edges = edgesAt(box.rect, x, y);
      if (!edges) {
        return;
      }
      if (area) {
        edges.left = edges.left && box.rect.left >= area.left - OUTSIDE_PX;
        edges.right = edges.right && box.rect.right <= area.right + OUTSIDE_PX;
        edges.top = edges.top && box.rect.top >= area.top - OUTSIDE_PX;
        edges.bottom = edges.bottom && box.rect.bottom <= area.bottom + OUTSIDE_PX;
        if (!edges.left && !edges.right && !edges.top && !edges.bottom) {
          return;
        }
      }
      const distance = edgeDistance(box.rect, edges, x, y);
      const size = (box.rect.right - box.rect.left) * (box.rect.bottom - box.rect.top);
      if (!best || distance < best.distance || (distance === best.distance && size < best.size)) {
        best = { box: box, edges: edges, distance: distance, size: size };
      }
    });
    return best ? { name: best.box.name, rect: best.box.rect, edges: best.edges } : null;
  }

  function cursorFor(edges) {
    if (!edges) {
      return null;
    }
    const horizontal = edges.left || edges.right;
    const vertical = edges.top || edges.bottom;
    if (horizontal && vertical) {
      return (edges.left && edges.top) || (edges.right && edges.bottom) ? 'nwse' : 'nesw';
    }
    return horizontal ? 'ew' : 'ns';
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  // The box after moving its edges by (dx, dy) pixels, kept inside bounds
  // (the plot) and at least MIN_PX across.
  function resizeRect(rect, edges, dx, dy, bounds) {
    const next = { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    if (edges.left) next.left = clamp(rect.left + dx, Math.min(bounds.left, rect.left), rect.right - MIN_PX);
    if (edges.right) next.right = clamp(rect.right + dx, rect.left + MIN_PX, Math.max(bounds.right, rect.right));
    if (edges.top) next.top = clamp(rect.top + dy, Math.min(bounds.top, rect.top), rect.bottom - MIN_PX);
    if (edges.bottom) next.bottom = clamp(rect.bottom + dy, rect.top + MIN_PX, Math.max(bounds.bottom, rect.bottom));
    return next;
  }

  // The relayout Plotly would report for the resized shape at position: only
  // the moved edges, in axis units. geometry maps client pixels to axis units.
  function updateFor(position, shape, edges, next, geometry) {
    const update = {};
    const leftKey = geometry.toClientX(shape.x0) <= geometry.toClientX(shape.x1) ? 'x0' : 'x1';
    const rightKey = leftKey === 'x0' ? 'x1' : 'x0';
    const topKey = geometry.toClientY(shape.y0) <= geometry.toClientY(shape.y1) ? 'y0' : 'y1';
    const bottomKey = topKey === 'y0' ? 'y1' : 'y0';
    const key = function (name) { return 'shapes[' + position + '].' + name; };
    if (edges.left) update[key(leftKey)] = geometry.fromClientX(next.left);
    if (edges.right) update[key(rightKey)] = geometry.fromClientX(next.right);
    if (edges.top) update[key(topKey)] = geometry.fromClientY(next.top);
    if (edges.bottom) update[key(bottomKey)] = geometry.fromClientY(next.bottom);
    return update;
  }

  function plotOf(graph) {
    return (graph && graph.querySelector && graph.querySelector('.js-plotly-plot')) || graph;
  }

  function canEdit() {
    return Boolean(window.bboxPanel && typeof window.bboxPanel.canEdit === 'function' && window.bboxPanel.canEdit());
  }

  // Client-pixel <-> axis-unit conversions for the main plot, and its area.
  function geometryOf(gd) {
    const full = gd && gd._fullLayout;
    const xa = full && full.xaxis;
    const ya = full && full.yaxis;
    const cover = gd && gd.querySelector && (gd.querySelector('.nsewdrag[data-subplot="xy"]') || gd.querySelector('.nsewdrag'));
    if (!xa || !ya || !cover || typeof xa.d2p !== 'function' || typeof ya.d2p !== 'function') {
      return null;
    }
    const area = cover.getBoundingClientRect();
    if (!(area.width > 0) || !(area.height > 0)) {
      return null;
    }
    return {
      area: area,
      toClientX: function (value) { return area.left + xa.d2p(value); },
      toClientY: function (value) { return area.top + ya.d2p(value); },
      fromClientX: function (pixel) { return xa.p2d(pixel - area.left); },
      fromClientY: function (pixel) { return ya.p2d(pixel - area.top); },
    };
  }

  function boxRects(gd, geometry) {
    const shapes = gd.layout && Array.isArray(gd.layout.shapes) ? gd.layout.shapes : [];
    const boxes = [];
    shapes.forEach(function (shape) {
      if (!shape || shape.type !== 'rect' || !BOX_SHAPE.test(String(shape.name || ''))) {
        return;
      }
      const xs = [geometry.toClientX(shape.x0), geometry.toClientX(shape.x1)];
      const ys = [geometry.toClientY(shape.y0), geometry.toClientY(shape.y1)];
      if (xs.concat(ys).some(function (value) { return !Number.isFinite(value); })) {
        return;
      }
      boxes.push({
        name: shape.name,
        rect: { left: Math.min(xs[0], xs[1]), right: Math.max(xs[0], xs[1]), top: Math.min(ys[0], ys[1]), bottom: Math.max(ys[0], ys[1]) },
      });
    });
    return boxes;
  }

  // The shown × and ✎ handles take their own clicks (bbox_hover_affordances.js).
  function overHandle(gd, x, y) {
    return Array.from(gd.querySelectorAll('.modal-bbox-handle-trace .point.is-visible')).some(function (node) {
      const r = node.getBoundingClientRect();
      return x >= r.left - 3 && x <= r.right + 3 && y >= r.top - 3 && y <= r.bottom + 3;
    });
  }

  function inside(area, x, y) {
    return x >= area.left && x <= area.right && y >= area.top && y <= area.bottom;
  }

  // The box edge a press at the event would resize, if any.
  function targetAt(gd, event) {
    const geometry = geometryOf(gd);
    if (!geometry || !inside(geometry.area, event.clientX, event.clientY) || overHandle(gd, event.clientX, event.clientY)) {
      return null;
    }
    const hit = pickEdge(boxRects(gd, geometry), event.clientX, event.clientY, geometry.area);
    return hit ? Object.assign(hit, { geometry: geometry }) : null;
  }

  function setCursor(gd, kind) {
    Object.keys(CURSOR_CLASSES).forEach(function (name) {
      gd.classList.toggle(CURSOR_CLASSES[name], name === kind);
    });
  }

  function shapePaths(gd, position) {
    return Array.from(gd.querySelectorAll('.shapelayer path[data-index="' + position + '"]'));
  }

  function drawRect(paths, rect) {
    paths.forEach(function (path) {
      const svg = path.ownerSVGElement;
      const origin = svg ? svg.getBoundingClientRect() : { left: 0, top: 0 };
      const x0 = rect.left - origin.left;
      const x1 = rect.right - origin.left;
      const y0 = rect.bottom - origin.top;
      const y1 = rect.top - origin.top;
      path.setAttribute('d', 'M' + x0 + ',' + y0 + 'H' + x1 + 'V' + y1 + 'H' + x0 + 'Z');
    });
  }

  function positionOf(gd, name) {
    const shapes = gd.layout && Array.isArray(gd.layout.shapes) ? gd.layout.shapes : [];
    return shapes.findIndex(function (shape) { return shape && shape.name === name; });
  }

  function swallowNextClick() {
    const until = Date.now() + 500;
    window.addEventListener('click', function (event) {
      if (Date.now() <= until) {
        event.stopPropagation();
        event.preventDefault();
      }
    }, { capture: true, once: true });
  }

  function stopDrag() {
    window.removeEventListener('mousemove', onDragMove, true);
    window.removeEventListener('mouseup', onDragEnd, true);
    window.removeEventListener('keydown', onDragKey, true);
    if (drag) {
      drag.gd.classList.remove('bbox-edge-dragging');
      setCursor(drag.gd, null);
    }
    drag = null;
  }

  function onDragMove(event) {
    if (!drag) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (!drag.moved && Math.abs(dx) < CLICK_PX && Math.abs(dy) < CLICK_PX) {
      return;
    }
    drag.moved = true;
    drag.next = resizeRect(drag.rect, drag.edges, dx, dy, drag.geometry.area);
    drawRect(shapePaths(drag.gd, drag.position), drag.next);
  }

  function onDragEnd(event) {
    if (!drag) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const finished = drag;
    stopDrag();
    swallowNextClick();
    if (!finished.moved || !finished.next) {
      return;
    }
    // A redraw while dragging can renumber the shapes; find the box again.
    const position = positionOf(finished.gd, finished.name);
    const shape = position >= 0 ? finished.gd.layout.shapes[position] : null;
    if (!shape || !window.Plotly || typeof window.Plotly.relayout !== 'function') {
      return;
    }
    const update = updateFor(position, shape, finished.edges, finished.next, finished.geometry);
    Promise.resolve(window.Plotly.relayout(finished.gd, update)).catch(function () {
      // The next redraw shows the box as it is.
    });
  }

  function onDragKey(event) {
    if (!drag || event.key !== 'Escape') {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    drag.paths.forEach(function (path, index) {
      path.setAttribute('d', drag.originalPaths[index]);
    });
    stopDrag();
  }

  function onMouseDown(event) {
    if (drag || event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || !canEdit()) {
      return;
    }
    const gd = plotOf(event.currentTarget);
    const target = targetAt(gd, event);
    if (!target) {
      return;
    }
    // Plotly starts its own drags from mousedown on its layers below.
    event.preventDefault();
    event.stopPropagation();
    const position = positionOf(gd, target.name);
    const paths = shapePaths(gd, position);
    drag = {
      gd: gd,
      name: target.name,
      position: position,
      rect: target.rect,
      edges: target.edges,
      geometry: target.geometry,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
      next: null,
      paths: paths,
      originalPaths: paths.map(function (path) { return path.getAttribute('d'); }),
    };
    gd.classList.add('bbox-edge-dragging');
    setCursor(gd, cursorFor(target.edges));
    window.addEventListener('mousemove', onDragMove, true);
    window.addEventListener('mouseup', onDragEnd, true);
    window.addEventListener('keydown', onDragKey, true);
  }

  // Show a resize cursor where a press would resize.
  function onHover(event) {
    if (drag || event.buttons) {
      return;
    }
    const gd = plotOf(event.currentTarget);
    const target = canEdit() ? targetAt(gd, event) : null;
    setCursor(gd, target ? cursorFor(target.edges) : null);
  }

  function onLeave(event) {
    if (!drag) {
      setCursor(plotOf(event.currentTarget), null);
    }
  }

  function bind() {
    const graph = document.getElementById('modal-image-graph');
    if (!graph || graph.dataset.bboxEdgeResizeBound === 'true') {
      return;
    }
    graph.dataset.bboxEdgeResizeBound = 'true';
    graph.addEventListener('mousedown', onMouseDown, true);
    graph.addEventListener('mousemove', onHover, true);
    graph.addEventListener('mouseleave', onLeave);
  }

  if (typeof document !== 'undefined' && document.documentElement && typeof MutationObserver !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', bind, { once: true });
    } else {
      bind();
    }
    // The graph mounts when the modal opens.
    new MutationObserver(bind).observe(document.documentElement, { childList: true, subtree: true });
  }

  window.bboxEdgeResize = {
    // For tests.
    edgesAt: edgesAt,
    pickEdge: pickEdge,
    cursorFor: cursorFor,
    resizeRect: resizeRect,
    updateFor: updateFor,
    OUTSIDE_PX: OUTSIDE_PX,
    MIN_PX: MIN_PX,
  };
}());
