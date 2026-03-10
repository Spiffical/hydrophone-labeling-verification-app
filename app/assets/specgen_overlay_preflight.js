(function () {
  const TRIGGERS = new Set([
    'app-config-save',
    'label-prev-page', 'label-next-page', 'label-goto-page',
    'verify-prev-page', 'verify-next-page', 'verify-goto-page',
    'explore-prev-page', 'explore-next-page', 'explore-goto-page'
  ]);
  const STALE_OVERLAY_IDLE_MS = 12000;

  function resetOverlayState() {
    window.__specgenOverlayPreflight = null;
    window.__specgenOverlayLatestRequest = null;
    window.__specgenOverlayPageHint = null;
    window.__specgenOverlayLast = 'init:reset';
    window.__specgenOverlayLastMeta = {
      reset: true,
      at_ms: Date.now()
    };
    window.__specgenOverlayLastChangedAtMs = Date.now();

    const overlay = document.getElementById('specgen-page-loading-overlay');
    if (overlay) {
      overlay.style.display = 'none';
    }
  }

  function showOverlayNow(triggerId) {
    const overlay = document.getElementById('specgen-page-loading-overlay');
    if (!overlay) return;

    const titleEl = document.getElementById('specgen-load-title');
    const subtitleEl = document.getElementById('specgen-load-subtitle');
    const textEl = document.getElementById('specgen-load-progress-text');
    const fillEl = document.getElementById('specgen-load-progress-fill');

    overlay.style.display = 'flex';
    if (titleEl) titleEl.textContent = 'Generating spectrograms...';
    if (subtitleEl) subtitleEl.textContent = 'Preparing spectrograms for this page...';
    if (textEl) textEl.textContent = 'Preparing current page...';
    if (fillEl) {
      fillEl.className = 'specgen-load-progress-fill';
      fillEl.style.width = '34%';
    }

    window.__specgenOverlayPreflight = {
      trigger_id: triggerId,
      shown_at_ms: Date.now()
    };
    window.__specgenOverlayLastChangedAtMs = Date.now();
  }

  function selectorForMode(mode) {
    if (mode === 'verify') return '#verify-grid img.spectrogram-image';
    if (mode === 'explore') return '#explore-grid img.spectrogram-image';
    return '#label-grid img.spectrogram-image';
  }

  function domStatsForMode(mode) {
    const imgs = Array.from(document.querySelectorAll(selectorForMode(mode)));
    let loaded = 0;
    for (const img of imgs) {
      if (img.complete && Number(img.naturalWidth || 0) > 0) {
        loaded += 1;
      }
    }
    return {
      total: imgs.length,
      loaded,
      pending: Math.max(0, imgs.length - loaded),
    };
  }

  function hideOverlayFromWatchdog(reason) {
    const overlay = document.getElementById('specgen-page-loading-overlay');
    const titleEl = document.getElementById('specgen-load-title');
    const subtitleEl = document.getElementById('specgen-load-subtitle');
    const textEl = document.getElementById('specgen-load-progress-text');
    const fillEl = document.getElementById('specgen-load-progress-fill');

    if (overlay) {
      overlay.style.display = 'none';
    }
    if (titleEl) titleEl.textContent = '';
    if (subtitleEl) subtitleEl.textContent = '';
    if (textEl) textEl.textContent = '';
    if (fillEl) {
      fillEl.className = 'specgen-load-progress-fill';
      fillEl.style.width = '0%';
    }

    window.__specgenOverlayPreflight = null;
    window.__specgenOverlayLatestRequest = null;
    window.__specgenOverlayLast = `watchdog-hide:${reason}`;
    window.__specgenOverlayLastMeta = {
      watchdog: true,
      reason,
      at_ms: Date.now(),
    };
    window.__specgenOverlayLastChangedAtMs = Date.now();
  }

  function runWatchdog() {
    const overlay = document.getElementById('specgen-page-loading-overlay');
    if (!overlay) return;
    if (getComputedStyle(overlay).display === 'none') return;

    const lastChangedAtMs = Number(window.__specgenOverlayLastChangedAtMs || 0);
    if (!Number.isFinite(lastChangedAtMs) || lastChangedAtMs <= 0) return;
    const idleMs = Date.now() - lastChangedAtMs;
    if (idleMs < STALE_OVERLAY_IDLE_MS) return;

    const request = window.__specgenOverlayLatestRequest || {};
    const mode = typeof request.mode === 'string' ? request.mode : 'label';
    const domStats = domStatsForMode(mode);

    if (domStats.total > 0 && domStats.pending <= 0) {
      hideOverlayFromWatchdog('dom-ready');
      return;
    }

    hideOverlayFromWatchdog('stale');
  }

  document.addEventListener('click', function (evt) {
    const target = evt.target && evt.target.closest ? evt.target.closest('[id]') : null;
    if (!target) return;
    const triggerId = target.id;
    if (!TRIGGERS.has(triggerId)) return;

    requestAnimationFrame(function () {
      showOverlayNow(triggerId);
    });
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', resetOverlayState, { once: true });
  } else {
    requestAnimationFrame(resetOverlayState);
  }

  window.addEventListener('beforeunload', resetOverlayState);
  window.setInterval(runWatchdog, 1000);
})();
