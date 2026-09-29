// Sizes of the spectrograms stacked in the modal's plot column: drag the
// splitter between two panels to give one more height and the other less,
// minimize a panel to its header, and "Add spectrogram" opens the Spectrograms
// menu. Panels are keyed by range ("main" for the main plot); sizes and
// minimized panels are remembered in this browser.
(function () {
  'use strict';

  const STORAGE_KEY = 'modalRangeLayout.v1';
  const PANEL = '.spectrogram-modal-plot-section[data-range-key]';
  const KEY_STEP_PX = 24;
  const state = load();
  let drag = null;

  function load() {
    try {
      const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}');
      return {
        sizes: stored && typeof stored.sizes === 'object' && stored.sizes ? stored.sizes : {},
        minimized: stored && typeof stored.minimized === 'object' && stored.minimized ? stored.minimized : {},
      };
    } catch (_error) {
      return { sizes: {}, minimized: {} };
    }
  }

  function save() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (_error) {
      // Private windows or blocked storage: sizes last for this page only.
    }
  }

  function column() {
    return document.querySelector('.modal-workbench-plot');
  }

  function panels() {
    const root = column();
    return root ? Array.from(root.querySelectorAll(PANEL)) : [];
  }

  function keyOf(panel) {
    return panel.getAttribute('data-range-key');
  }

  function apply() {
    panels().forEach(function (panel) {
      const key = keyOf(panel);
      const grow = Number(state.sizes[key]);
      const value = Number.isFinite(grow) && grow > 0 ? String(grow) : '';
      if (panel.style.flexGrow !== value) {
        panel.style.flexGrow = value;
      }
      const minimized = Boolean(state.minimized[key]);
      panel.classList.toggle('is-minimized', minimized);
      const button = panel.querySelector('[data-panel-action="minimize"]');
      if (button) {
        button.setAttribute('aria-expanded', minimized ? 'false' : 'true');
        button.title = minimized ? 'Restore' : 'Minimize';
        const icon = button.querySelector('i');
        if (icon) {
          icon.className = minimized ? 'bi bi-chevron-down' : 'bi bi-dash-lg';
        }
      }
    });
  }

  // The nearest panels either side of a splitter that are not minimized.
  function neighbours(splitter) {
    const all = panels();
    let before = null;
    let after = null;
    all.forEach(function (panel) {
      if (panel.classList.contains('is-minimized')) {
        return;
      }
      // eslint-disable-next-line no-bitwise
      const precedes = panel.compareDocumentPosition(splitter) & Node.DOCUMENT_POSITION_FOLLOWING;
      if (precedes) {
        before = panel;
      } else if (!after) {
        after = panel;
      }
    });
    return before && after ? { before: before, after: after } : null;
  }

  function flexGrowOf(panel) {
    const value = parseFloat(window.getComputedStyle(panel).flexGrow);
    return Number.isFinite(value) && value > 0 ? value : 1;
  }

  function minHeightOf(panel) {
    const value = parseFloat(window.getComputedStyle(panel).minHeight);
    return Number.isFinite(value) && value > 0 ? value : 120;
  }

  function beginResize(splitter) {
    const pair = neighbours(splitter);
    if (!pair) {
      return null;
    }
    const beforeHeight = pair.before.getBoundingClientRect().height;
    const afterHeight = pair.after.getBoundingClientRect().height;
    return {
      splitter: splitter,
      before: pair.before,
      after: pair.after,
      beforeHeight: beforeHeight,
      afterHeight: afterHeight,
      growTotal: flexGrowOf(pair.before) + flexGrowOf(pair.after),
      beforeMin: minHeightOf(pair.before),
      afterMin: minHeightOf(pair.after),
    };
  }

  // Heights follow flex-grow (every panel's basis is 0), so share the pair's
  // total grow in the ratio of the heights the drag asks for.
  function resizeBy(resize, delta) {
    const total = resize.beforeHeight + resize.afterHeight;
    const lower = Math.min(resize.beforeMin, total / 2);
    const upper = Math.max(lower, total - Math.min(resize.afterMin, total / 2));
    const beforeHeight = Math.max(lower, Math.min(upper, resize.beforeHeight + delta));
    const beforeGrow = resize.growTotal * (beforeHeight / total);
    const afterGrow = resize.growTotal - beforeGrow;
    state.sizes[keyOf(resize.before)] = Math.round(beforeGrow * 1000) / 1000;
    state.sizes[keyOf(resize.after)] = Math.round(afterGrow * 1000) / 1000;
    apply();
  }

  function resetPair(splitter) {
    const pair = neighbours(splitter);
    if (!pair) {
      return;
    }
    delete state.sizes[keyOf(pair.before)];
    delete state.sizes[keyOf(pair.after)];
    apply();
    save();
  }

  document.addEventListener('pointerdown', function (event) {
    const splitter = event.target && event.target.closest ? event.target.closest('.spectrogram-panel-splitter') : null;
    if (!splitter || event.button !== 0) {
      return;
    }
    const resize = beginResize(splitter);
    if (!resize) {
      return;
    }
    event.preventDefault();
    drag = Object.assign(resize, { startY: event.clientY, pointerId: event.pointerId, frame: null, delta: 0 });
    if (typeof splitter.setPointerCapture === 'function') {
      splitter.setPointerCapture(event.pointerId);
    }
    splitter.classList.add('is-active');
    const root = column();
    if (root) {
      root.classList.add('is-resizing');
    }
  });

  document.addEventListener('pointermove', function (event) {
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    drag.delta = event.clientY - drag.startY;
    if (drag.frame === null) {
      drag.frame = window.requestAnimationFrame(function () {
        if (drag) {
          drag.frame = null;
          resizeBy(drag, drag.delta);
        }
      });
    }
  });

  function endDrag(event) {
    if (!drag || (event && event.pointerId !== drag.pointerId)) {
      return;
    }
    resizeBy(drag, drag.delta);
    drag.splitter.classList.remove('is-active');
    const root = column();
    if (root) {
      root.classList.remove('is-resizing');
    }
    drag = null;
    save();
  }
  document.addEventListener('pointerup', endDrag);
  document.addEventListener('pointercancel', endDrag);

  document.addEventListener('dblclick', function (event) {
    const splitter = event.target && event.target.closest ? event.target.closest('.spectrogram-panel-splitter') : null;
    if (splitter) {
      resetPair(splitter);
    }
  });

  // Arrow keys on a focused splitter move it.
  document.addEventListener('keydown', function (event) {
    const splitter = event.target && event.target.classList && event.target.classList.contains('spectrogram-panel-splitter')
      ? event.target
      : null;
    if (!splitter || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) {
      return;
    }
    const resize = beginResize(splitter);
    if (!resize) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    resizeBy(resize, event.key === 'ArrowUp' ? -KEY_STEP_PX : KEY_STEP_PX);
    save();
  }, true);

  document.addEventListener('click', function (event) {
    const target = event.target && event.target.closest ? event.target : null;
    if (!target) {
      return;
    }
    const minimize = target.closest('[data-panel-action="minimize"]');
    if (minimize) {
      const panel = minimize.closest(PANEL);
      if (panel) {
        const key = keyOf(panel);
        if (state.minimized[key]) {
          delete state.minimized[key];
        } else {
          state.minimized[key] = true;
        }
        apply();
        save();
      }
      return;
    }
    if (target.closest('#modal-spectrogram-apply-ranges')) {
      // The new set of spectrograms is drawn under the menu; get out of the way.
      window.setTimeout(function () {
        const menu = document.getElementById('modal-ranges-menu');
        if (menu) {
          menu.open = false;
        }
      }, 150);
      return;
    }
    if (target.closest('.modal-add-range-btn')) {
      const menu = document.getElementById('modal-ranges-menu');
      if (menu) {
        menu.open = true;
        const first = menu.querySelector('input, button');
        if (first && typeof first.focus === 'function') {
          first.focus({ preventScroll: true });
        }
      }
    }
  });

  // Panels are rebuilt with each clip and range change.
  new MutationObserver(function (mutations) {
    for (const mutation of mutations) {
      const target = mutation.target;
      if (target && target.closest && target.closest('.modal-workbench-plot')) {
        apply();
        return;
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });

  window.modalRangeLayout = {
    apply: apply,
    state: state,
    // For tests.
    resizeBy: resizeBy,
    beginResize: beginResize,
  };
}());
