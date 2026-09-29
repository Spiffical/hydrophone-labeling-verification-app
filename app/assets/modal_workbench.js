// One-screen spectrogram modal: "Save and next" in the header and the
// "Audio tools" toggle under the plot.
(function () {
  'use strict';

  const AUDIO_TOOLS_KEY = 'modalWorkbench.audioTools';
  const SAVE_TIMEOUT_MS = 10000;
  const SAVE_POLL_MS = 120;
  let saving = false;

  function actionButton(types) {
    return Array.from(document.querySelectorAll('#modal-item-actions button[id^="{"]')).find(function (button) {
      try {
        const id = JSON.parse(button.id);
        return Boolean(id && id.scope === 'modal' && types.indexOf(id.type) !== -1);
      } catch (_error) {
        return false;
      }
    }) || null;
  }

  // Verify mode saves with modal-action-confirm, label mode with modal-label-save.
  function saveButton() {
    return actionButton(['modal-action-confirm', 'modal-label-save']);
  }

  function goNext() {
    const next = document.getElementById('modal-nav-next');
    if (next && !next.disabled && next.getAttribute('aria-disabled') !== 'true') {
      next.click();
    }
  }

  function setSaving(value) {
    saving = value;
    const button = document.getElementById('modal-save-next');
    if (button) {
      button.disabled = value;
      button.classList.toggle('is-saving', value);
    }
  }

  // Save when there are edits (Save is only enabled then), wait for the save to
  // finish, then open the next clip. If the save does not finish, stay here.
  function saveAndNext() {
    if (saving) {
      return;
    }
    const save = saveButton();
    if (!save || save.disabled) {
      goNext();
      return;
    }
    setSaving(true);
    save.click();
    const started = Date.now();
    (function waitForSave() {
      const current = saveButton();
      if (current && !current.disabled) {
        if (Date.now() - started < SAVE_TIMEOUT_MS) {
          window.setTimeout(waitForSave, SAVE_POLL_MS);
        } else {
          setSaving(false);
        }
        return;
      }
      setSaving(false);
      goNext();
    }());
  }

  function readAudioTools() {
    try {
      return window.localStorage.getItem(AUDIO_TOOLS_KEY) === '1';
    } catch (_error) {
      return false;
    }
  }

  // Remembered per browser; the class lives on <body> so it survives the audio
  // player re-rendering for each clip.
  function applyAudioTools(open) {
    document.body.classList.toggle('modal-audio-tools-open', open);
    document.querySelectorAll('.modal-audio-tools-toggle').forEach(function (button) {
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  document.addEventListener('click', function (event) {
    const target = event.target.closest ? event.target : null;
    if (!target) {
      return;
    }
    if (target.closest('.modal-audio-tools-toggle')) {
      const open = !document.body.classList.contains('modal-audio-tools-open');
      applyAudioTools(open);
      try {
        window.localStorage.setItem(AUDIO_TOOLS_KEY, open ? '1' : '0');
      } catch (_error) {
        // Storage can be blocked; the toggle still works for this page.
      }
    } else if (target.closest('#modal-save-next')) {
      event.preventDefault();
      saveAndNext();
    }
  });

  function start() {
    applyAudioTools(readAudioTools());
    // Keep aria-expanded right on the toggle rendered with each clip's player.
    new MutationObserver(function (mutations) {
      if (mutations.some(function (m) { return m.target && m.target.id === 'modal-audio-player'; })) {
        applyAudioTools(document.body.classList.contains('modal-audio-tools-open'));
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.body) {
    start();
  } else {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  }

  window.modalWorkbench = { saveAndNext: saveAndNext };
}());
