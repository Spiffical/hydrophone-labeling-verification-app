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

  function getImageSrc(img) {
    return String((img && (img.currentSrc || img.src || img.getAttribute('src'))) || '').trim();
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
      return getImageSrc(img) && img.complete && Number(img.naturalWidth || 0) > 0;
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
    const hasSrc = Boolean(src);
    const isLoaded = hasSrc && img.complete && Number(img.naturalWidth || 0) > 0;
    const isError = hasSrc && img.complete && Number(img.naturalWidth || 0) <= 0;

    container.classList.toggle('spec-loaded', isLoaded);
    container.classList.toggle('spec-error', isError);
    container.classList.toggle('spec-loading', hasSrc && !isLoaded && !isError);
    img.__spectrogramLastSrc = src;
    maybeReleasePageSwitching();
  }

  function wireImage(img) {
    if (!img || img.__spectrogramLoadingWired) {
      updateImageState(img);
      return;
    }
    img.__spectrogramLoadingWired = true;
    img.addEventListener('load', function () {
      img.__spectrogramSrcChanging = false;
      updateImageState(img);
    });
    img.addEventListener('error', function () {
      img.__spectrogramSrcChanging = false;
      updateImageState(img);
    });
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
