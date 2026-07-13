(function () {
  const PAGE_SWITCHING_CLASS = 'spec-grid-page-switching';
  const PAGE_BUTTON_IDS = new Set([
    'label-prev-page',
    'label-next-page',
    'label-goto-page',
    'verify-prev-page',
    'verify-next-page',
    'verify-goto-page',
    'explore-prev-page',
    'explore-next-page',
    'explore-goto-page'
  ]);
  const TRANSPARENT_IMAGE_PREFIX = 'data:image/gif;base64,R0lGODlhAQABA';
  let lazyImageObserver = null;

  function getDeferredSrc(img) {
    return String((img && img.dataset && img.dataset.src) || '').trim();
  }

  function isTransparentPlaceholder(src) {
    return String(src || '').indexOf(TRANSPARENT_IMAGE_PREFIX) === 0;
  }

  function getActiveGrid(triggerId) {
    if (triggerId && triggerId.indexOf('label-') === 0) {
      return document.getElementById('label-grid');
    }
    if (triggerId && triggerId.indexOf('verify-') === 0) {
      return document.getElementById('verify-grid');
    }
    if (triggerId && triggerId.indexOf('explore-') === 0) {
      return document.getElementById('explore-grid');
    }
    function isVisible(el) {
      return Boolean(el && (el.offsetParent || el.getClientRects().length > 0));
    }
    const verifyGrid = document.getElementById('verify-grid');
    if (isVisible(verifyGrid)) {
      return verifyGrid;
    }
    const labelGrid = document.getElementById('label-grid');
    if (isVisible(labelGrid)) {
      return labelGrid;
    }
    const exploreGrid = document.getElementById('explore-grid');
    if (isVisible(exploreGrid)) {
      return exploreGrid;
    }
    return document.getElementById('verify-grid') || document.getElementById('label-grid') || document.getElementById('explore-grid') || null;
  }

  function getGridForMode(mode) {
    if (mode === 'label') {
      return document.getElementById('label-grid');
    }
    if (mode === 'explore') {
      return document.getElementById('explore-grid');
    }
    return document.getElementById('verify-grid');
  }

  function pageInfoMatchesRequest(mode, requestPage) {
    if (!Number.isFinite(Number(requestPage)) || Number(requestPage) < 0) {
      return true;
    }
    const infoId = mode === 'label'
      ? 'label-page-info'
      : mode === 'explore'
        ? 'explore-page-info'
        : 'verify-page-info';
    const infoText = String((document.getElementById(infoId) || {}).textContent || '');
    const match = infoText.match(/Page\s+(\d+)\s+of\s+\d+/i);
    if (!match) {
      return false;
    }
    return Number(match[1]) - 1 === Number(requestPage);
  }

  function getImageSrc(img) {
    return String((img && (img.currentSrc || img.src || img.getAttribute('src'))) || '').trim();
  }

  function isDeferredAndInactive(img) {
    const deferredSrc = getDeferredSrc(img);
    if (!deferredSrc) {
      return false;
    }
    const src = getImageSrc(img);
    return !src || isTransparentPlaceholder(src) || src !== deferredSrc;
  }

  function isNearViewport(img) {
    if (!img || !img.getBoundingClientRect) {
      return false;
    }
    const rect = img.getBoundingClientRect();
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    const margin = 600;
    return (
      rect.bottom >= -margin &&
      rect.top <= viewportHeight + margin &&
      rect.right >= -margin &&
      rect.left <= viewportWidth + margin
    );
  }

  function activateDeferredImage(img) {
    const deferredSrc = getDeferredSrc(img);
    if (!img || !deferredSrc || !isDeferredAndInactive(img)) {
      return;
    }
    setContainerLoading(img);
    img.__spectrogramLazyActivated = true;
    img.src = deferredSrc;
  }

  function getLazyImageObserver() {
    if (lazyImageObserver || !('IntersectionObserver' in window)) {
      return lazyImageObserver;
    }
    lazyImageObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry || !entry.isIntersecting) {
          return;
        }
        lazyImageObserver.unobserve(entry.target);
        activateDeferredImage(entry.target);
      });
    }, { rootMargin: '600px 0px' });
    return lazyImageObserver;
  }

  function setContainerLoading(img) {
    const container = img && img.closest ? img.closest('.spectrogram-image-container') : null;
    if (!container) {
      return;
    }
    container.classList.remove('spec-loaded', 'spec-error');
    container.classList.add('spec-loading');
  }

  function markPageSwitching(triggerId) {
    const grid = getActiveGrid(triggerId);
    if (!grid) {
      return;
    }
    grid.classList.add(PAGE_SWITCHING_CLASS);
    window.__spectrogramPageSwitch = {
      startedAtMs: Date.now(),
      sawGridMutation: false
    };
  }

  function noteGridMutation(mutation) {
    const state = window.__spectrogramPageSwitch;
    if (!state || !mutation) {
      return;
    }
    const target = mutation.target && mutation.target.closest ? mutation.target.closest('.grid-shell') : null;
    const addedInGrid = Array.from(mutation.addedNodes || []).some(function (node) {
      if (!node || node.nodeType !== 1) {
        return false;
      }
      return (
        (node.matches && node.matches('.grid-shell, .spectrogram-card, .spectrogram-image-container, img.spectrogram-image')) ||
        (node.querySelector && node.querySelector('.spectrogram-card, .spectrogram-image-container, img.spectrogram-image'))
      );
    });
    if (target || addedInGrid) {
      state.sawGridMutation = true;
    }
  }

  function allGridImagesReady(grid) {
    if (!grid) {
      return false;
    }
    const images = Array.from(grid.querySelectorAll('img.spectrogram-image'));
    if (images.length === 0) {
      return false;
    }
    return images.every(function (img) {
      if (isDeferredAndInactive(img)) {
        return !isNearViewport(img);
      }
      const src = getImageSrc(img);
      return src && !isTransparentPlaceholder(src) && img.complete && Number(img.naturalWidth || 0) > 1;
    });
  }

  function maybeReleasePageSwitching() {
    const state = window.__spectrogramPageSwitch;
    const grid = getActiveGrid();
    if (!state || !grid || !grid.classList.contains(PAGE_SWITCHING_CLASS)) {
      return;
    }
    const elapsedMs = Date.now() - Number(state.startedAtMs || 0);
    if ((state.sawGridMutation && elapsedMs > 250 && allGridImagesReady(grid)) || elapsedMs > 30000) {
      grid.classList.remove(PAGE_SWITCHING_CLASS);
      window.__spectrogramPageSwitch = null;
    }
    maybeHideSpecgenOverlayWhenGridReady('page-switch');
  }

  function maybeHideSpecgenOverlayWhenGridReady(reason) {
    const overlay = document.getElementById('specgen-page-loading-overlay');
    if (!overlay || getComputedStyle(overlay).display === 'none') {
      return;
    }
    const request = window.__specgenOverlayLatestRequest || null;
    const mode = String((request && request.mode) || '').trim() || 'verify';
    if (request && !pageInfoMatchesRequest(mode, request.page)) {
      return;
    }
    const grid = getGridForMode(mode);
    if (!grid || String(grid.textContent || '').indexOf('Preparing spectrogram cards') !== -1) {
      return;
    }
    const cardsRendered = grid.querySelectorAll('.spectrogram-card').length > 0;
    const requestKey = [
      mode,
      String((request && request.page) ?? ''),
      String((request && request.requested_at_ms) ?? '')
    ].join(':');
    if (cardsRendered) {
      const renderedState = window.__specgenOverlayPageRendered || {};
      if (renderedState.key !== requestKey) {
        window.__specgenOverlayPageRendered = { key: requestKey, at_ms: Date.now() };
      }
    }
    const renderedAtMs = Number((window.__specgenOverlayPageRendered || {}).at_ms || 0);
    const renderedAgeMs = renderedAtMs > 0 ? Date.now() - renderedAtMs : 0;
    const graceReady = cardsRendered && renderedAgeMs > 12000;
    const hideReason = graceReady ? 'page-render-grace' : (reason || 'grid-ready');
    if (!allGridImagesReady(grid) && !graceReady) {
      return;
    }
    overlay.style.display = 'none';
    window.__specgenOverlayLatestRequest = null;
    window.__specgenOverlayPageRendered = null;
    window.__specgenOverlayDomReady = {
      mode: mode,
      reason: hideReason,
      at_ms: Date.now()
    };
    window.__specgenOverlayLast = 'asset-hide:' + hideReason;
    window.__specgenOverlayLastMeta = window.__specgenOverlayDomReady;
  }

  function updateImageState(img) {
    if (!img || !img.classList || !img.classList.contains('spectrogram-image')) {
      return;
    }
    const container = img.closest('.spectrogram-image-container');
    if (!container) {
      return;
    }

    const src = getImageSrc(img);
    if (isDeferredAndInactive(img)) {
      container.classList.remove('spec-loaded', 'spec-error');
      container.classList.add('spec-loading');
      img.__spectrogramLastSrc = src;
      maybeReleasePageSwitching();
      return;
    }
    const hasSrc = Boolean(src);
    const isPlaceholder = isTransparentPlaceholder(src);
    const isLoaded = hasSrc && !isPlaceholder && img.complete && Number(img.naturalWidth || 0) > 1;
    const isError = hasSrc && !isPlaceholder && img.complete && Number(img.naturalWidth || 0) <= 0;

    container.classList.toggle('spec-loaded', isLoaded);
    container.classList.toggle('spec-error', isError);
    container.classList.toggle('spec-loading', hasSrc && !isLoaded && !isError);
    img.__spectrogramLastSrc = src;
    maybeReleasePageSwitching();
    maybeHideSpecgenOverlayWhenGridReady('image-state');
  }

  function wireImage(img) {
    if (!img || img.__spectrogramLoadingWired) {
      updateImageState(img);
      return;
    }
    img.__spectrogramLoadingWired = true;
    img.setAttribute('decoding', 'async');
    img.addEventListener('load', function () {
      img.__spectrogramSrcChanging = false;
      updateImageState(img);
    });
    img.addEventListener('error', function () {
      img.__spectrogramSrcChanging = false;
      updateImageState(img);
    });
    if (getDeferredSrc(img) && isDeferredAndInactive(img)) {
      const observer = getLazyImageObserver();
      if (observer) {
        observer.observe(img);
      } else {
        activateDeferredImage(img);
      }
      updateImageState(img);
      return;
    }
    updateImageState(img);
  }

  function handleImageSrcMutation(img) {
    if (!img || !img.matches || !img.matches('img.spectrogram-image')) {
      return;
    }
    const src = getImageSrc(img);
    if (src && src !== img.__spectrogramLastSrc) {
      img.__spectrogramSrcChanging = true;
      img.__spectrogramLastSrc = src;
      setContainerLoading(img);
      if (window.__spectrogramPageSwitch) {
        window.__spectrogramPageSwitch.sawGridMutation = true;
      }
      requestAnimationFrame(function () {
        if (!img.__spectrogramSrcChanging) {
          updateImageState(img);
        }
      });
      return;
    }
    wireImage(img);
  }

  function scan() {
    document.querySelectorAll('img.spectrogram-image').forEach(wireImage);
    maybeReleasePageSwitching();
    maybeHideSpecgenOverlayWhenGridReady('scan');
  }

  document.addEventListener('click', function (event) {
    const button = event.target && event.target.closest ? event.target.closest('button') : null;
    if (button && PAGE_BUTTON_IDS.has(button.id) && !button.disabled && button.getAttribute('aria-disabled') !== 'true') {
      markPageSwitching(button.id);
    }
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scan, { once: true });
  } else {
    scan();
  }

  const observer = new MutationObserver(function (mutations) {
    let shouldScan = false;
    for (const mutation of mutations) {
      if (mutation.type === 'childList') {
        noteGridMutation(mutation);
        shouldScan = true;
        continue;
      }
      if (mutation.type === 'attributes' && mutation.target && mutation.target.matches && mutation.target.matches('img.spectrogram-image')) {
        handleImageSrcMutation(mutation.target);
      }
    }
    if (shouldScan) {
      requestAnimationFrame(scan);
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['src']
  });

  window.setInterval(scan, 1000);
})();
