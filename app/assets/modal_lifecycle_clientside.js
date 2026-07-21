(function () {
  function noUpdate() {
    return (window.dash_clientside || {}).no_update;
  }

  function noUpdates(count) {
    return Array.from({ length: count }, noUpdate);
  }

  function context() {
    return (window.dash_clientside || {}).callback_context || null;
  }

  function triggeredId(callbackContext) {
    if (!callbackContext) {
      return null;
    }
    if (callbackContext.triggered_id !== undefined && callbackContext.triggered_id !== null) {
      return callbackContext.triggered_id;
    }
    const triggered = callbackContext.triggered && callbackContext.triggered[0];
    const propId = triggered && triggered.prop_id;
    if (!propId) {
      return null;
    }
    const rawId = propId.slice(0, propId.lastIndexOf('.'));
    if (rawId.charAt(0) !== '{') {
      return rawId;
    }
    try {
      return JSON.parse(rawId);
    } catch (_error) {
      return null;
    }
  }

  function triggeredValue(callbackContext) {
    const triggered = callbackContext && callbackContext.triggered && callbackContext.triggered[0];
    return triggered ? triggered.value : null;
  }

  function isDirtyForItem(unsavedStore, currentItemId) {
    if (!unsavedStore || unsavedStore.dirty !== true) {
      return false;
    }
    const dirtyItemId = String(unsavedStore.item_id || '').trim();
    const current = String(currentItemId || '').trim();
    return !current || !dirtyItemId || dirtyItemId === current;
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    modalLifecycle: Object.assign({}, (window.dash_clientside || {}).modalLifecycle, {
      openImmediately: function (_imageClicks, unsavedStore, currentItemId) {
        const callbackContext = context();
        const id = triggeredId(callbackContext);
        if (
          !id ||
          typeof id !== 'object' ||
          id.type !== 'spectrogram-image' ||
          Number(triggeredValue(callbackContext) || 0) <= 0
        ) {
          return noUpdates(3);
        }
        const itemId = String(id.item_id || '').trim();
        if (!itemId || isDirtyForItem(unsavedStore, currentItemId)) {
          return noUpdates(3);
        }
        return [true, true, { item_id: itemId, ts: Date.now() }];
      },

      closeImmediately: function (
        _footerClicks,
        _headerClicks,
        unsavedStore,
        currentItemId
      ) {
        const callbackContext = context();
        const id = triggeredId(callbackContext);
        if (
          (id !== 'close-modal' && id !== 'close-modal-header') ||
          Number(triggeredValue(callbackContext) || 0) <= 0
        ) {
          return noUpdates(10);
        }
        if (isDirtyForItem(unsavedStore, currentItemId)) {
          return [
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            true,
            { kind: 'close' },
            false,
          ];
        }
        return [
          false,
          null,
          null,
          { item_id: null, boxes: [] },
          null,
          null,
          { dirty: false, item_id: null },
          false,
          null,
          false,
        ];
      },

      applyForcedAction: function (payload) {
        const action = payload && payload.action;
        if (!action || (action.kind !== 'open' && action.kind !== 'close')) {
          return noUpdates(2);
        }
        return action.kind === 'open' ? [true, true] : [false, false];
      },

      finishLoading: function (_modalItem) {
        return false;
      },
    }),
  });
})();
