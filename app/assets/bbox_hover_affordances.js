(function () {
  function markEditTrace(graph) {
    if (!graph || !graph.querySelectorAll) {
      return;
    }
    graph.querySelectorAll('.scatterlayer .trace').forEach(function (trace) {
      const textNodes = Array.from(trace.querySelectorAll('text'));
      const isEditTrace = textNodes.some(function (node) {
        return String(node.textContent || '').trim() === '\u270e';
      });
      trace.classList.toggle('modal-bbox-edit-trace', isEditTrace);
    });
  }

  function setEditTraceVisible(graph, visible) {
    if (!graph || !graph.querySelectorAll) {
      return;
    }
    graph.querySelectorAll('.scatterlayer .trace.modal-bbox-edit-trace').forEach(function (trace) {
      trace.classList.toggle('modal-bbox-edit-trace--visible', Boolean(visible));
    });
  }

  function pointerInsideBoxShape(graph, event) {
    const shapes = Array.from(graph.querySelectorAll('.shapelayer path'));
    return shapes.some(function (shape) {
      const bounds = shape.getBoundingClientRect();
      if (bounds.width < 4 || bounds.height < 4) {
        return false;
      }
      return (
        event.clientX >= bounds.left &&
        event.clientX <= bounds.right &&
        event.clientY >= bounds.top &&
        event.clientY <= bounds.bottom
      );
    });
  }

  function pointerInsideEditHandle(graph, event) {
    const trace = graph && graph.querySelector('.scatterlayer .trace.modal-bbox-edit-trace');
    if (!trace) {
      return false;
    }
    const markerNodes = Array.from(trace.querySelectorAll('.points path'));
    const textNodes = Array.from(trace.querySelectorAll('text'));
    const candidates = markerNodes.length ? markerNodes : textNodes;
    return candidates.some(function (node) {
      const bounds = node.getBoundingClientRect();
      const pad = 8;
      return (
        event.clientX >= bounds.left - pad &&
        event.clientX <= bounds.right + pad &&
        event.clientY >= bounds.top - pad &&
        event.clientY <= bounds.bottom + pad
      );
    });
  }

  function editIndexAtPointer(graph, event) {
    const trace = graph && graph.querySelector('.scatterlayer .trace.modal-bbox-edit-trace');
    if (!trace || !trace.classList.contains('modal-bbox-edit-trace--visible')) {
      return null;
    }
    const markerNodes = Array.from(trace.querySelectorAll('.points path'));
    const textNodes = Array.from(trace.querySelectorAll('text'));
    const candidates = markerNodes.length ? markerNodes : textNodes;
    for (let index = 0; index < candidates.length; index += 1) {
      const bounds = candidates[index].getBoundingClientRect();
      const pad = 8;
      if (
        event.clientX >= bounds.left - pad &&
        event.clientX <= bounds.right + pad &&
        event.clientY >= bounds.top - pad &&
        event.clientY <= bounds.bottom + pad
      ) {
        return index;
      }
    }
    return null;
  }

  function clickSidebarEditButton(index) {
    const buttons = Array.from(document.querySelectorAll('button[id]'));
    for (const button of buttons) {
      try {
        const parsed = JSON.parse(button.id);
        if (
          parsed &&
          parsed.type === 'modal-bbox-edit-btn' &&
          Number(parsed.index) === Number(index)
        ) {
          button.click();
          return true;
        }
      } catch (_error) {
        // Dash component ids are JSON strings only for pattern-matched controls.
      }
    }
    return false;
  }

  function bindGraph(graph) {
    if (!graph || graph.dataset.bboxHoverBound === 'true') {
      return;
    }
    graph.dataset.bboxHoverBound = 'true';
    graph.addEventListener('mousemove', function (event) {
      markEditTrace(graph);
      setEditTraceVisible(
        graph,
        pointerInsideBoxShape(graph, event) || pointerInsideEditHandle(graph, event)
      );
    });
    graph.addEventListener('mouseleave', function () {
      setEditTraceVisible(graph, false);
    });
    graph.addEventListener('click', function (event) {
      markEditTrace(graph);
      const index = editIndexAtPointer(graph, event);
      if (index === null) {
        return;
      }
      if (clickSidebarEditButton(index)) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);
  }

  function scan() {
    const graph = document.getElementById('modal-image-graph');
    markEditTrace(graph);
    bindGraph(graph);
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
