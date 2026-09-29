// Long clips in the spectrogram modal are shown a page at a time (300 s by
// default; display.modal_page_seconds, with a closer 120 s option). This draws
// the pager above the plot and the clip overview under it, moves between pages
// ([ and ], see modal_shortcuts.js), turns the page as playback runs, and puts
// the page back when Dash replaces the figure. Page windows: modal_pages.js.
(function () {
  'use strict';

  const BAR_ID = 'modal-page-bar';
  const OVERVIEW_ID = 'modal-page-overview';
  const AUDIO_ID = 'modal-player-audio';
  const state = {
    itemId: null,
    layout: null, // gd.layout last seen; a new object means Dash sent a new figure
    range: null, // the x range the reviewer is on
  };

  function plot() {
    return document.querySelector('#modal-image-graph .js-plotly-plot');
  }

  function metaOf(gd) {
    return (gd && gd.layout && gd.layout.meta) || null;
  }

  function liveRange(gd) {
    const range = gd && gd._fullLayout && gd._fullLayout.xaxis && gd._fullLayout.xaxis.range;
    if (!Array.isArray(range) || range.length !== 2) {
      return null;
    }
    const lower = Number(range[0]);
    const upper = Number(range[1]);
    return Number.isFinite(lower) && Number.isFinite(upper) && upper > lower ? [lower, upper] : null;
  }

  function pagesOf(gd) {
    const meta = metaOf(gd);
    return meta && window.modalPages ? window.modalPages.pagesForMeta(meta) : [];
  }

  function sameRange(left, right) {
    if (!left || !right) {
      return false;
    }
    const tolerance = 1e-4 * Math.max(1e-9, right[1] - right[0]);
    return Math.abs(left[0] - right[0]) <= tolerance && Math.abs(left[1] - right[1]) <= tolerance;
  }

  // The page the view is on: an exact match, else the page holding its centre.
  function viewIndex(pages, range) {
    if (!range || !pages.length) {
      return 0;
    }
    for (let index = 0; index < pages.length; index += 1) {
      if (sameRange(range, pages[index])) {
        return index;
      }
    }
    const centre = (range[0] + range[1]) / 2;
    for (let index = 0; index < pages.length; index += 1) {
      if (pages[index][0] <= centre && centre < pages[index][1]) {
        return index;
      }
    }
    return centre < pages[0][0] ? 0 : pages.length - 1;
  }

  // The page whose middle is nearest x (pages overlap at the end of the clip).
  function pageNear(pages, x) {
    let best = 0;
    pages.forEach(function (page, index) {
      const middle = (page[0] + page[1]) / 2;
      const bestMiddle = (pages[best][0] + pages[best][1]) / 2;
      if (Math.abs(middle - x) < Math.abs(bestMiddle - x)) {
        best = index;
      }
    });
    return best;
  }

  // Plotly keeps ranges set with the mouse when Dash re-plots the figure
  // (uirevision) but not ones set with Plotly.relayout, and dcc.Graph re-plots
  // its stored figure after every drawn or edited box. So page changes are
  // made as GUI edits, the way Plotly's own pan does (its internal
  // _guiRelayout sets this flag around relayout).
  function guiRelayout(gd, update) {
    const fullLayout = gd._fullLayout;
    if (fullLayout) {
      fullLayout._guiEditing = true;
    }
    try {
      return Promise.resolve(window.Plotly.relayout(gd, update));
    } finally {
      if (fullLayout) {
        fullLayout._guiEditing = false;
      }
    }
  }

  function moveTo(range) {
    const gd = plot();
    if (!gd || !window.Plotly || !range) {
      return Promise.resolve(false);
    }
    state.range = [range[0], range[1]];
    const current = liveRange(gd);
    if (current && sameRange(current, state.range)) {
      render();
      return Promise.resolve(true);
    }
    return guiRelayout(gd, { 'xaxis.range': state.range.slice(), 'xaxis.autorange': false })
      .then(function () { return true; });
  }

  function goTo(index) {
    const pages = pagesOf(plot());
    if (pages.length < 2) {
      return false;
    }
    moveTo(pages[Math.max(0, Math.min(pages.length - 1, index))]);
    return true;
  }

  function step(delta) {
    const gd = plot();
    const pages = pagesOf(gd);
    if (pages.length < 2) {
      return false;
    }
    return goTo(viewIndex(pages, liveRange(gd)) + delta);
  }

  // Bring a stretch of the clip (plot units) into view: its page, unless the
  // view already shows all of it.
  function show(x0, x1) {
    const gd = plot();
    const pages = pagesOf(gd);
    const range = liveRange(gd);
    if (pages.length < 2 || !range) {
      return false;
    }
    if (range[0] <= x0 && x1 <= range[1]) {
      return true;
    }
    moveTo(window.modalPages.windowForRange(x0, x1, pages));
    return true;
  }

  function audio() {
    return document.getElementById(AUDIO_ID);
  }

  // Seconds into the clip at x = 0: the first frame's centre (image_processing.py).
  function originSeconds(meta) {
    const origin = Number(meta.x_origin_seconds);
    return Number.isFinite(origin) ? origin : 0;
  }

  // Plot position of the audio clock (see updateSpectrogramPlaybackMarker).
  function playheadX(meta, element) {
    const seconds = Number(element && element.currentTime);
    if (!Number.isFinite(seconds)) {
      return null;
    }
    return Number(meta.x_min) + (seconds - originSeconds(meta)) / (Number(meta.x_to_seconds) || 1);
  }

  function syncMarker() {
    const element = audio();
    if (element && typeof window.updateSpectrogramPlaybackMarker === 'function' &&
        Number.isFinite(element.duration) && element.duration > 0) {
      window.updateSpectrogramPlaybackMarker(element.currentTime, element.duration);
    }
  }

  // Box handles on a figure from the server are placed for the dashboard's
  // page length; redraw them when the reviewer picked another.
  function redrawHandles(gd) {
    const meta = metaOf(gd);
    const dc = window.dash_clientside || {};
    if (!meta || !window.modalPages || typeof dc.set_props !== 'function') {
      return;
    }
    const placedFor = Number(meta.handle_page_seconds) || Number(meta.page_seconds) || null;
    if (placedFor !== window.modalPages.selectedSeconds(meta)) {
      dc.set_props('modal-bbox-command-store', {
        data: { action: 'redraw', item_id: meta.modal_item_id, nonce: Date.now() },
      });
    }
  }

  function onNewFigure(gd) {
    const meta = metaOf(gd);
    const itemId = meta && meta.modal_item_id ? String(meta.modal_item_id) : null;
    const pages = pagesOf(gd);
    if (itemId !== state.itemId) {
      // A new clip opens on its first page.
      state.itemId = itemId;
      state.range = pages.length > 1 ? pages[0].slice() : null;
    } else if (pages.length < 2) {
      state.range = null;
    }
    const live = liveRange(gd);
    const target = state.range || (pages.length === 1 ? pages[0] : null);
    const moved = target && live && !sameRange(live, target) ? moveTo(target) : Promise.resolve(false);
    moved.then(function () { redrawHandles(gd); });
  }

  function onAfterPlot() {
    const gd = plot();
    if (gd && gd.layout !== state.layout) {
      state.layout = gd.layout;
      onNewFigure(gd);
    }
    render();
  }

  function onRelayout(update) {
    if (!update || !Object.keys(update).some(function (key) {
      return key.indexOf('xaxis.range') === 0 || key === 'xaxis.autorange';
    })) {
      return;
    }
    // A double-click zooms out to the whole clip for a moment before the reset
    // in modal_lifecycle_clientside.js returns to this page; keep the page.
    const range = update['xaxis.autorange'] === true ? null : liveRange(plot());
    if (range) {
      state.range = range;
    }
    render();
    syncMarker();
  }

  function bindPlot(gd) {
    if (!gd || gd._modalPagingBound || typeof gd.on !== 'function') {
      return;
    }
    gd._modalPagingBound = true;
    gd.on('plotly_afterplot', onAfterPlot);
    gd.on('plotly_relayout', onRelayout);
    onAfterPlot();
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  function el(tag, className, attrs, children) {
    const node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    Object.keys(attrs || {}).forEach(function (key) {
      if (attrs[key] !== null && attrs[key] !== undefined && attrs[key] !== false) {
        node.setAttribute(key, attrs[key] === true ? '' : String(attrs[key]));
      }
    });
    (children || []).forEach(function (child) {
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return node;
  }

  function seconds(meta, x) {
    return Math.round((x - Number(meta.x_min)) * (Number(meta.x_to_seconds) || 1));
  }

  function formatRange(meta, range) {
    return seconds(meta, range[0]).toLocaleString() + '–' + seconds(meta, range[1]).toLocaleString() + ' s';
  }

  function renderBar(bar, gd, meta, pages) {
    bar.textContent = '';
    const options = window.modalPages.options(meta);
    const xMin = Number(meta.x_min);
    const xMax = Number(meta.x_max);
    const xToSeconds = Number(meta.x_to_seconds) || 1;
    // Offer the pager when some page length would split this clip.
    const pageable = options.some(function (value) {
      return window.modalPages.windows(xMin, xMax, value / xToSeconds).length > 1;
    });
    bar.hidden = !pageable;
    if (!pageable) {
      return;
    }
    const range = liveRange(gd) || pages[0];
    const index = viewIndex(pages, range);
    const paged = pages.length > 1;
    bar.appendChild(el('button', 'modal-page-step', {
      type: 'button', 'data-page-step': '-1', disabled: !paged || index === 0,
      title: 'Previous page ([)', 'aria-label': 'Previous page',
    }, [el('i', 'bi bi-chevron-left', { 'aria-hidden': 'true' })]));
    bar.appendChild(el('span', 'modal-page-label', { 'aria-live': 'polite' }, paged ? [
      el('b', null, null, [formatRange(meta, range)]),
      el('span', 'modal-page-count', null, [' · ' + (index + 1) + ' / ' + pages.length]),
    ] : [el('b', null, null, ['Whole clip · ' + seconds(meta, xMax).toLocaleString() + ' s'])]));
    bar.appendChild(el('button', 'modal-page-step', {
      type: 'button', 'data-page-step': '1', disabled: !paged || index === pages.length - 1,
      title: 'Next page (])', 'aria-label': 'Next page',
    }, [el('i', 'bi bi-chevron-right', { 'aria-hidden': 'true' })]));
    if (options.length > 1) {
      const select = el('select', 'modal-page-length form-select form-select-sm', {
        'aria-label': 'Page length', title: 'How much of a long clip to show at once',
      }, options.map(function (value) {
        return el('option', null, { value: value }, [value + ' s pages']);
      }));
      select.value = String(window.modalPages.selectedSeconds(meta));
      bar.appendChild(select);
    }
  }

  function renderOverview(overview, gd, meta, pages) {
    overview.textContent = '';
    overview.hidden = pages.length < 2;
    const area = gd && gd.querySelector('.nsewdrag');
    if (overview.hidden || !area) {
      return;
    }
    const xMin = Number(meta.x_min);
    const span = Math.max(1e-9, Number(meta.x_max) - xMin);
    const xToSeconds = Number(meta.x_to_seconds) || 1;
    const percent = function (x) {
      return Math.max(0, Math.min(100, ((x - xMin) / span) * 100));
    };
    const track = el('div', 'modal-page-overview__track', {
      role: 'button', tabindex: '-1',
      title: 'Whole clip: click to go there. Boxes are marked; amber ones have no tag.',
      'aria-label': 'Clip overview',
    });
    // Line the track up with the plot area.
    const areaRect = area.getBoundingClientRect();
    const hostRect = overview.getBoundingClientRect();
    track.style.marginLeft = Math.max(0, areaRect.left - hostRect.left) + 'px';
    track.style.width = Math.max(40, areaRect.width) + 'px';
    pages.slice(1).forEach(function (page) {
      track.appendChild(el('span', 'modal-page-overview__edge', { style: 'left:' + percent(page[0]) + '%' }));
    });
    const panel = window.bboxPanel;
    const boxes = panel && typeof panel.boxes === 'function' ? panel.boxes() : [];
    // Only boxes of a species with tags are marked untagged (bbox_list.js).
    const needsTag = panel && typeof panel.needsTag === 'function'
      ? panel.needsTag
      : function (box) { return !(typeof box.tag === 'string' && box.tag.trim()); };
    boxes.forEach(function (box) {
      const extent = box && box.annotation_extent;
      const start = Number(extent && extent.time_start_sec);
      const end = Number(extent && extent.time_end_sec);
      if (!Number.isFinite(start) || !Number.isFinite(end)) {
        return;
      }
      const left = percent(start / xToSeconds);
      track.appendChild(el('span', 'modal-page-overview__box' + (needsTag(box) ? ' is-untagged' : ''), {
        style: 'left:' + left + '%;width:' + Math.max(0, percent(end / xToSeconds) - left) + '%',
      }));
    });
    const range = liveRange(gd) || pages[0];
    track.appendChild(el('span', 'modal-page-overview__view', {
      style: 'left:' + percent(range[0]) + '%;width:' + (percent(range[1]) - percent(range[0])) + '%',
    }));
    overview.appendChild(track);
  }

  function render() {
    const bar = document.getElementById(BAR_ID);
    const overview = document.getElementById(OVERVIEW_ID);
    const gd = plot();
    const meta = metaOf(gd);
    if (!bar || !overview) {
      return;
    }
    if (!meta || !window.modalPages || !Number.isFinite(Number(meta.x_max))) {
      bar.hidden = true;
      overview.hidden = true;
      return;
    }
    const pages = pagesOf(gd);
    renderBar(bar, gd, meta, pages);
    renderOverview(overview, gd, meta, pages);
  }

  // ---------------------------------------------------------------------------
  // Events
  // ---------------------------------------------------------------------------

  document.addEventListener('click', function (event) {
    const target = event.target && event.target.closest ? event.target : null;
    if (!target) {
      return;
    }
    const stepButton = target.closest('#' + BAR_ID + ' [data-page-step]');
    if (stepButton) {
      step(Number(stepButton.getAttribute('data-page-step')));
      return;
    }
    const track = target.closest('#' + OVERVIEW_ID + ' .modal-page-overview__track');
    if (track) {
      const gd = plot();
      const meta = metaOf(gd);
      const pages = pagesOf(gd);
      const box = track.getBoundingClientRect();
      if (meta && pages.length > 1 && box.width > 0) {
        const fraction = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
        const x = Number(meta.x_min) + fraction * (Number(meta.x_max) - Number(meta.x_min));
        goTo(pageNear(pages, x));
      }
    }
  });

  document.addEventListener('change', function (event) {
    const select = event.target && event.target.closest ? event.target.closest('#' + BAR_ID + ' .modal-page-length') : null;
    const gd = plot();
    const meta = metaOf(gd);
    if (!select || !meta) {
      return;
    }
    const range = liveRange(gd);
    window.modalPages.storeSeconds(Number(select.value));
    const pages = pagesOf(gd);
    // Stay near the same part of the clip.
    state.range = pages.length > 1 && range ? pages[pageNear(pages, (range[0] + range[1]) / 2)].slice() : null;
    moveTo(state.range || pages[0]).then(function () { redrawHandles(gd); });
  });

  // Turn the page as playback reaches the end of the view. Media events do
  // not bubble, so listen in the capture phase.
  document.addEventListener('timeupdate', function (event) {
    const element = event.target;
    if (!element || element.id !== AUDIO_ID || element.paused) {
      return;
    }
    const gd = plot();
    const meta = metaOf(gd);
    const pages = pagesOf(gd);
    const range = liveRange(gd);
    const x = meta ? playheadX(meta, element) : null;
    if (pages.length < 2 || !range || x === null || (x >= range[0] && x <= range[1])) {
      return;
    }
    for (let index = 0; index < pages.length; index += 1) {
      if (pages[index][0] <= x && x < pages[index][1]) {
        moveTo(pages[index]);
        return;
      }
    }
  }, true);

  // Play what is on screen: when the playhead is off this page, start from the
  // page's beginning. The player seeks to its slider on play (audio_controls.js).
  document.addEventListener('click', function (event) {
    const button = event.target && event.target.closest ? event.target.closest('#modal-player-play-btn') : null;
    const element = audio();
    const gd = plot();
    const meta = metaOf(gd);
    const range = liveRange(gd);
    if (!button || !element || !element.paused || !meta || !range || pagesOf(gd).length < 2) {
      return;
    }
    const x = playheadX(meta, element);
    const slider = document.getElementById('modal-player-time-slider');
    if (x === null || (x >= range[0] && x < range[1]) || !slider || !(element.duration > 0) ||
        typeof window.setSliderVisualProgress !== 'function') {
      return;
    }
    const startSeconds = (range[0] - Number(meta.x_min)) * (Number(meta.x_to_seconds) || 1) + originSeconds(meta);
    window.setSliderVisualProgress(slider, (Math.max(0, startSeconds) / element.duration) * 100);
  }, true);

  // The graph remounts when the modal opens; keep it bound.
  new MutationObserver(function (mutations) {
    for (const mutation of mutations) {
      if (mutation.target && mutation.target.closest && mutation.target.closest('#modal-image-graph')) {
        bindPlot(plot());
        return;
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('resize', function () { render(); });

  window.modalPaging = {
    step: step,
    goTo: goTo,
    show: show,
    refresh: render,
    relayout: guiRelayout,
    // Home and double-click reset go back to this page (modal_lifecycle_clientside.js).
    homeRange: function () {
      const gd = plot();
      const pages = pagesOf(gd);
      return pages.length > 1 ? pages[viewIndex(pages, state.range || liveRange(gd))].slice() : null;
    },
  };
}());
