(function () {
  function noUpdate() {
    return (window.dash_clientside || {}).no_update;
  }

  function noUpdates(count) {
    return Array.from({ length: count }, noUpdate);
  }

  function profileIsComplete(profile) {
    const value = profile || {};
    const name = String(value.name || '').trim();
    const email = String(value.email || '').trim();
    return Boolean(name) && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
  }

  function dashContext() {
    return (window.dash_clientside || {}).callback_context || null;
  }

  function parseTriggeredId(context) {
    if (!context) {
      return null;
    }
    if (context.triggered_id !== undefined && context.triggered_id !== null) {
      return context.triggered_id;
    }
    const triggered = context.triggered && context.triggered[0];
    const propId = triggered && triggered.prop_id;
    if (!propId) {
      return null;
    }
    const rawId = propId.slice(0, propId.lastIndexOf('.'));
    try {
      return rawId.charAt(0) === '{' ? JSON.parse(rawId) : rawId;
    } catch (_error) {
      return null;
    }
  }

  function triggeredValue(context) {
    const triggered = context && context.triggered && context.triggered[0];
    return triggered ? triggered.value : null;
  }

  function updatesFor(ids, key, value) {
    let matched = false;
    const updates = (ids || []).map(function (id) {
      if (id && id.target === key) {
        matched = true;
        return value;
      }
      return noUpdate();
    });
    return matched ? updates : noUpdate();
  }

  function updatesForItem(ids, itemId, value) {
    let matched = false;
    const updates = (ids || []).map(function (id) {
      if (id && id.item_id === itemId) {
        matched = true;
        return value;
      }
      return noUpdate();
    });
    return matched ? updates : noUpdate();
  }

  function updatesForAll(ids, value) {
    return ids && ids.length ? ids.map(function () { return value; }) : noUpdate();
  }

  function cardItemId(target) {
    const value = String(target || '');
    const separatorIndex = value.lastIndexOf('||');
    return separatorIndex > 0 ? value.slice(0, separatorIndex) : '';
  }

  function decisionState(action) {
    if (action === 'accept') {
      return { name: 'model-accepted', text: 'accepted' };
    }
    if (action === 'reject') {
      return { name: 'model-rejected', text: 'rejected' };
    }
    return { name: 'deleted', text: '' };
  }

  function actionFromType(type) {
    if (String(type || '').endsWith('accept')) {
      return 'accept';
    }
    if (String(type || '').endsWith('reject')) {
      return 'reject';
    }
    return 'delete';
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    verificationInteractions: Object.assign(
      {},
      (window.dash_clientside || {}).verificationInteractions,
      {
        optimisticDecision: function (
          _cardAccept,
          _cardReject,
          _cardDelete,
          _modalAccept,
          _modalReject,
          _modalDelete,
          cardBadgeIds,
          cardStateIds,
          cardAcceptIds,
          cardRejectIds,
          cardSaveIds,
          modalBadgeIds,
          modalRowIds,
          modalStateIds,
          modalAcceptIds,
          modalRejectIds,
          modalSaveIds,
          profile
        ) {
          const noChange = noUpdates(17);
          const context = dashContext();
          const triggeredId = parseTriggeredId(context);
          if (
            !profileIsComplete(profile) ||
            !triggeredId ||
            typeof triggeredId !== 'object' ||
            Number(triggeredValue(context) || 0) <= 0
          ) {
            return noChange;
          }

          const type = String(triggeredId.type || '');
          const isModal = type.indexOf('modal-verify-label-') === 0;
          const isCard = !isModal && type.indexOf('verify-label-') === 0;
          const target = String(triggeredId.target || triggeredId.label || '').trim();
          if ((!isCard && !isModal) || !target) {
            return noChange;
          }

          const action = actionFromType(type);
          const state = decisionState(action);
          const className = 'verify-label-badge verify-label-badge--' + state.name + ' verify-label-badge--row';
          const acceptDisabled = action === 'accept';
          const rejectDisabled = action === 'reject';
          const hiddenStyle = action === 'delete' ? { display: 'none' } : {};

          if (isCard) {
            const itemId = cardItemId(target) || String(triggeredId.item_id || '').trim();
            if (!itemId) {
              return noChange;
            }
            return [
              updatesFor(cardBadgeIds, target, className),
              updatesFor(cardBadgeIds, target, hiddenStyle),
              updatesFor(cardStateIds, target, state.text),
              updatesFor(cardAcceptIds, target, acceptDisabled),
              updatesFor(cardRejectIds, target, rejectDisabled),
              updatesForItem(cardSaveIds, itemId, false),
              updatesForItem(cardSaveIds, itemId, 'success'),
              updatesForItem(cardSaveIds, itemId, false),
              noUpdate(),
              noUpdate(),
              noUpdate(),
              noUpdate(),
              noUpdate(),
              noUpdate(),
              noUpdate(),
              noUpdate(),
              noUpdate(),
            ];
          }

          const rowClass = 'modal-label-row modal-label-row--verify modal-label-row--' + state.name;
          return [
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            updatesFor(modalBadgeIds, target, className),
            updatesFor(modalRowIds, target, rowClass),
            updatesFor(modalRowIds, target, hiddenStyle),
            updatesFor(modalStateIds, target, state.text),
            updatesFor(modalAcceptIds, target, acceptDisabled),
            updatesFor(modalRejectIds, target, rejectDisabled),
            updatesForAll(modalSaveIds, false),
            updatesForAll(modalSaveIds, 'success'),
            updatesForAll(modalSaveIds, false),
          ];
        },

        optimisticModalFigure: function (
          _modalReject,
          _modalDelete,
          bboxStore,
          figure,
          currentItemId,
          profile
        ) {
          const context = dashContext();
          const triggeredId = parseTriggeredId(context);
          if (
            !profileIsComplete(profile) ||
            !currentItemId ||
            !triggeredId ||
            typeof triggeredId !== 'object' ||
            Number(triggeredValue(context) || 0) <= 0
          ) {
            return noUpdate();
          }
          const type = String(triggeredId.type || '');
          if (type !== 'modal-verify-label-reject' && type !== 'modal-verify-label-delete') {
            return noUpdate();
          }
          const label = String(triggeredId.target || triggeredId.label || '').trim();
          const store = bboxStore && typeof bboxStore === 'object' ? bboxStore : {};
          if (!label || store.item_id !== currentItemId || !Array.isArray(store.boxes)) {
            return noUpdate();
          }
          const boxes = store.boxes.filter(function (box) {
            return !box || String(box.label || '').trim() !== label;
          });
          if (boxes.length === store.boxes.length) {
            return noUpdate();
          }
          const bbox = (window.dash_clientside || {}).bboxInteractions || {};
          return typeof bbox.applyBoxesToFigure === 'function'
            ? bbox.applyBoxesToFigure(figure, boxes)
            : noUpdate();
        },

        optimisticLabelDelete: function (
          _deleteClicks,
          badgeIds,
          saveIds,
          profile,
          mode
        ) {
          const noChange = noUpdates(4);
          const context = dashContext();
          const triggeredId = parseTriggeredId(context);
          if (
            mode !== 'label' ||
            !profileIsComplete(profile) ||
            !triggeredId ||
            typeof triggeredId !== 'object' ||
            triggeredId.type !== 'label-label-delete' ||
            Number(triggeredValue(context) || 0) <= 0
          ) {
            return noChange;
          }
          const target = String(triggeredId.target || '').trim();
          const itemId = cardItemId(target);
          if (!target || !itemId) {
            return noChange;
          }
          return [
            updatesFor(badgeIds, target, { display: 'none' }),
            updatesForItem(saveIds, itemId, false),
            updatesForItem(saveIds, itemId, 'success'),
            updatesForItem(saveIds, itemId, false),
          ];
        },
      }
    ),
  });
})();
