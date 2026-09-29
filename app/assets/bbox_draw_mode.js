// Draw mode for the spectrogram modal: after "Draw" in the toolbar (or B),
// every drag on the spectrogram adds a box for the chosen label, across clips,
// until it is switched off with B, Esc or one of Plotly's pan/zoom tools.
// A + click next to a label still draws a single box.
(function () {
  'use strict';

  // Shared with bbox_clientside.js, which keeps drawing after each new box.
  const state = window.bboxDraw = window.bboxDraw || { sticky: false, label: null };
  const listeners = new Set();
  let rearmTimer = null;

  function notify() {
    listeners.forEach(function (listener) {
      try {
        listener();
      } catch (_error) {
        // A broken listener must not stop drawing.
      }
    });
  }

  function plot() {
    return document.querySelector('#modal-image-graph .js-plotly-plot');
  }

  // Labels that can take boxes: the + buttons next to labels in the sidebar.
  function labelButtons() {
    const panel = document.getElementById('modal-item-actions');
    const found = [];
    if (!panel) {
      return found;
    }
    panel.querySelectorAll('button[id^="{"]').forEach(function (button) {
      try {
        const id = JSON.parse(button.id);
        if (id && id.type === 'modal-label-add-box' && id.label && !button.disabled) {
          found.push({ label: String(id.label), button: button });
        }
      } catch (_error) {
        // Not a pattern-matched Dash id.
      }
    });
    return found;
  }

  function currentTarget() {
    const buttons = labelButtons();
    return buttons.find(function (entry) { return entry.label === state.label; }) || buttons[0] || null;
  }

  // Arm through the label's + button so the usual checks (profile, mode) and
  // the undo snapshot for new boxes apply.
  function arm() {
    const target = currentTarget();
    if (!target) {
      return false;
    }
    state.label = target.label;
    target.button.click();
    return true;
  }

  function canEdit() {
    return Boolean(window.bboxPanel && window.bboxPanel.canEdit());
  }

  function enable(label) {
    if (!canEdit()) {
      return false;
    }
    if (label) {
      state.label = label;
    }
    state.sticky = true;
    if (!arm()) {
      state.sticky = false;
    }
    notify();
    return state.sticky;
  }

  function disable() {
    if (!state.sticky) {
      return;
    }
    state.sticky = false;
    const dc = window.dash_clientside || {};
    if (typeof dc.set_props === 'function') {
      dc.set_props('modal-active-box-label', { data: null });
    }
    if (dc.bboxInteractions && typeof dc.bboxInteractions.setPanMode === 'function') {
      dc.bboxInteractions.setPanMode();
    }
    notify();
  }

  // Opening another clip, or a redraw from the server, resets Plotly to pan.
  function scheduleRearm() {
    if (rearmTimer !== null) {
      window.clearTimeout(rearmTimer);
    }
    rearmTimer = window.setTimeout(function () {
      rearmTimer = null;
      if (!state.sticky) {
        return;
      }
      if (!canEdit()) {
        // E.g. switched to Explore mode: stop rather than prompt on every redraw.
        disable();
        return;
      }
      const gd = plot();
      if (gd && gd._fullLayout && gd._fullLayout.dragmode !== 'drawrect') {
        arm();
      }
    }, 120);
  }

  function bindPlot() {
    const gd = plot();
    if (!gd || gd.dataset.bboxDrawBound === 'true' || typeof gd.on !== 'function') {
      return;
    }
    gd.dataset.bboxDrawBound = 'true';
    gd.on('plotly_afterplot', function () {
      if (state.sticky) {
        scheduleRearm();
      }
    });
  }

  // Picking pan, zoom or another Plotly tool means the reviewer wants to stop drawing.
  document.addEventListener('click', function (event) {
    if (!state.sticky || !event.isTrusted || !event.target.closest) {
      return;
    }
    const tool = event.target.closest('#modal-image-graph .modebar-btn[data-attr="dragmode"]');
    if (tool && tool.getAttribute('data-val') !== 'drawrect') {
      disable();
    }
  }, true);

  // The graph remounts when the modal opens, and the label list changes with
  // each clip; keep the plot bound and the toolbar current.
  new MutationObserver(function (mutations) {
    let labelsChanged = false;
    for (const mutation of mutations) {
      const target = mutation.target;
      if (!target || !target.closest) {
        continue;
      }
      if (target.closest('#modal-image-graph')) {
        bindPlot();
      }
      if (target.closest('#modal-item-actions') || target.id === 'modal-item-actions') {
        labelsChanged = true;
      }
    }
    if (labelsChanged) {
      notify();
      if (state.sticky) {
        scheduleRearm();
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });

  window.bboxDrawMode = {
    enable: enable,
    disable: disable,
    toggle: function () {
      if (state.sticky) {
        disable();
        return false;
      }
      return enable();
    },
    isOn: function () {
      return state.sticky;
    },
    label: function () {
      const target = currentTarget();
      return target ? target.label : null;
    },
    labels: function () {
      return labelButtons().map(function (entry) { return entry.label; });
    },
    setLabel: function (label) {
      state.label = label;
      if (state.sticky) {
        arm();
      }
      notify();
    },
    subscribe: function (listener) {
      listeners.add(listener);
      return function () { listeners.delete(listener); };
    },
  };
}());
