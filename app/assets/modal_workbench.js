// One-screen spectrogram modal: "Save and next" in the header and the
// "Audio tools" toggle under the plot.
(function () {
  'use strict';

  const AUDIO_TOOLS_KEY = 'modalWorkbench.audioTools';
  const SAVE_TIMEOUT_MS = 10000;
  const SAVE_POLL_MS = 120;
  const DECISION_TIMEOUT_MS = 12000;
  const DECISION_START_MS = 300;
  const QUIET_MS = 200;
  let saving = false;
  // A label decision (✓, ×, delete) reaches the server's copy of the clip only
  // when its request is answered, though the app enables Save at once. On a slow
  // link a quick save could run without the decision, and the late answer would
  // then mark the clip unsaved. So saving and moving wait for an answer still on
  // its way: after a decision click until no Dash callback request is left in
  // flight (an answer can change nothing, e.g. without a reviewer profile), after
  // a Save click until Save is disabled again.
  const decision = { since: 0, kind: '' };
  // Save and arrow clicks held back meanwhile, clicked again in the order they
  // were made (an arrow after a held Save then waits for that save in turn).
  const heldClicks = [];
  let released = null;
  let callbacksInFlight = 0;
  let callbacksDoneAt = 0;

  if (typeof window.fetch === 'function') {
    const fetchImpl = window.fetch;
    window.fetch = function (input) {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.indexOf('_dash-update-component') === -1) {
        return fetchImpl.apply(this, arguments);
      }
      callbacksInFlight += 1;
      return fetchImpl.apply(this, arguments).finally(function () {
        callbacksInFlight -= 1;
        callbacksDoneAt = Date.now();
      });
    };
  }

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

  function buttonType(button) {
    try {
      const id = JSON.parse(button.id);
      return id && typeof id.type === 'string' ? id.type : '';
    } catch (_error) {
      return '';
    }
  }

  function isDecisionButton(button) {
    return /^modal-verify-label-(accept|reject|delete)$/.test(buttonType(button));
  }

  function isSaveButton(button) {
    return ['modal-action-confirm', 'modal-label-save'].indexOf(buttonType(button)) !== -1;
  }

  function decisionPending() {
    if (!decision.since) {
      return false;
    }
    const age = Date.now() - decision.since;
    if (age < DECISION_TIMEOUT_MS) {
      // Dash sends the request at once; a short grace covers the moment before it starts.
      if (age < DECISION_START_MS) {
        return true;
      }
      // A save is in once Save is disabled again (its follow-up callbacks change
      // nothing that matters); a decision once no callback request is in flight.
      const save = decision.kind === 'save' ? saveButton() : null;
      const saved = decision.kind === 'save' && (!save || save.disabled);
      if (!saved && callbacksInFlight > 0) {
        return true;
      }
    }
    decision.since = 0;
    return false;
  }

  // Runs `then` once no decision or save is on its way and no callback request
  // has been in flight for QUIET_MS (an answer's follow-up callbacks start just
  // after it), or after DECISION_TIMEOUT_MS at the latest. On a settled clip that
  // is at once.
  function afterDecisions(then) {
    const started = Date.now();
    (function poll() {
      const busy = decisionPending() || callbacksInFlight > 0 || Date.now() - callbacksDoneAt < QUIET_MS;
      if (busy && Date.now() - started < DECISION_TIMEOUT_MS) {
        window.setTimeout(poll, SAVE_POLL_MS);
        return;
      }
      then();
    }());
  }

  // A click the hold below lets through.
  function clickThrough(button) {
    released = button;
    try {
      button.click();
    } finally {
      released = null;
    }
  }

  function releaseHeldClicks() {
    afterDecisions(function () {
      const find = heldClicks.shift();
      // The answer re-renders the labels panel, so find the button again.
      const current = find && find();
      if (current && !current.disabled) {
        clickThrough(current);
      }
      if (heldClicks.length) {
        releaseHeldClicks();
      }
    });
  }

  // Save when there are edits (Save is only enabled then), wait for the save to
  // finish, then open the next clip. If the save does not finish, stay here.
  function saveAndNext() {
    if (saving) {
      return;
    }
    // A held Save or arrow would only repeat this or move a second time.
    heldClicks.length = 0;
    setSaving(true);
    afterDecisions(function () {
      const save = saveButton();
      if (!save || save.disabled) {
        setSaving(false);
        goNext();
        return;
      }
      clickThrough(save);
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
        // Saved: the clip is no longer unsaved, so the move need not wait for anything else.
        decision.since = 0;
        setSaving(false);
        goNext();
      }());
    });
  }

  // Decision clicks start the wait. Save (the app enables it at once, before the
  // server has the decision) and the arrows (buttons and keys) wait for it, so a
  // save never runs without the decision and a decision never lands on the next clip.
  // While "Save and next" runs they are dropped: it saves and moves on by itself.
  document.addEventListener('click', function (event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) {
      return;
    }
    const button = target.closest('#modal-item-actions button[id^="{"]');
    if (button && isDecisionButton(button)) {
      decision.since = Date.now();
      decision.kind = 'decision';
      return;
    }
    const held = button && isSaveButton(button) ? button : target.closest('#modal-nav-next, #modal-nav-prev');
    if (!held) {
      return;
    }
    if (held !== released && (saving || heldClicks.length || decisionPending())) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!saving) {
        const navId = isSaveButton(held) ? null : held.id;
        heldClicks.push(navId ? function () { return document.getElementById(navId); } : saveButton);
        if (heldClicks.length === 1) {
          releaseHeldClicks();
        }
      }
      return;
    }
    if (isSaveButton(held)) {
      // Until the save is back the clip still counts as unsaved, so the arrows wait for it too.
      decision.since = Date.now();
      decision.kind = 'save';
    }
  }, true);

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

  window.modalWorkbench = {
    saveAndNext: saveAndNext,
    // For tests: whether a label decision is still on its way to the server.
    decisionPending: decisionPending,
  };
}());
