// Page windows for long clips in the spectrogram modal, shared by the pager
// (modal_paging.js) and box handle placement (bbox_clientside.js). Mirrors
// modal_page_windows in app/services/modal_boxes.py.
(function () {
  'use strict';

  // Clips up to this much longer than a page are still shown whole.
  const TOLERANCE = 1.1;
  const STORAGE_KEY = 'modalPaging.seconds';

  // Equal-width pages from xMin; the last page ends at xMax and overlaps the
  // one before it, so every page has the same zoom.
  function windows(xMin, xMax, pageLength) {
    const span = xMax - xMin;
    const length = Number(pageLength);
    if (!(length > 0) || !(span > length * TOLERANCE)) {
      return [[xMin, xMax]];
    }
    const count = Math.ceil(span / length);
    const pages = [];
    for (let index = 0; index < count; index += 1) {
      let start = xMin + index * length;
      let end = start + length;
      if (end > xMax) {
        start = xMax - length;
        end = xMax;
      }
      pages.push([start, end]);
    }
    return pages;
  }

  // The page a box belongs to: the first that holds all of it, else the one
  // holding its start.
  function windowForRange(x0, x1, pages) {
    for (let index = 0; index < pages.length; index += 1) {
      if (pages[index][0] <= x0 && x1 <= pages[index][1]) {
        return pages[index];
      }
    }
    for (let index = 0; index < pages.length; index += 1) {
      if (pages[index][0] <= x0 && x0 < pages[index][1]) {
        return pages[index];
      }
    }
    return pages[pages.length - 1];
  }

  function storedSeconds() {
    try {
      return Number(window.localStorage.getItem(STORAGE_KEY)) || null;
    } catch (_error) {
      return null;
    }
  }

  function storeSeconds(seconds) {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(seconds));
    } catch (_error) {
      // Storage can be blocked; the choice then lasts for this page only.
    }
  }

  function options(meta) {
    return (Array.isArray(meta && meta.page_seconds_options) ? meta.page_seconds_options : [])
      .map(Number)
      .filter(function (value) { return value > 0; });
  }

  // Page length in seconds: the reviewer's pick when this dashboard offers it.
  function selectedSeconds(meta) {
    const stored = storedSeconds();
    if (stored && options(meta).indexOf(stored) !== -1) {
      return stored;
    }
    const fallback = Number(meta && meta.page_seconds);
    return fallback > 0 ? fallback : null;
  }

  // Pages for a figure's layout.meta, in plot units.
  function pagesForMeta(meta) {
    const xMin = Number(meta && meta.x_min);
    const xMax = Number(meta && meta.x_max);
    if (!Number.isFinite(xMin) || !Number.isFinite(xMax) || xMax <= xMin) {
      return [];
    }
    const seconds = selectedSeconds(meta);
    const xToSeconds = Number(meta.x_to_seconds) || 1;
    return windows(xMin, xMax, seconds ? seconds / xToSeconds : null);
  }

  window.modalPages = {
    windows: windows,
    windowForRange: windowForRange,
    options: options,
    selectedSeconds: selectedSeconds,
    storeSeconds: storeSeconds,
    pagesForMeta: pagesForMeta,
  };
}());
