/* Keep heatmap arrays and embedded image bytes in the browser during edits. */
(function () {
  'use strict';

  function unchangedOrNext(previous, next) {
    return JSON.stringify(previous) === JSON.stringify(next)
      ? window.dash_clientside.no_update : next;
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    modalPerformance: {
      figureContext: function (figure, itemId, previousContext, previousMeta) {
        const layout = (figure && figure.layout) || {};
        const contextLayout = {};
        // Overlay helpers need axis metadata, shapes and source annotations only.
        // Exclude templates, layout.images and all trace coordinate/matrix arrays.
        ['meta', 'shapes', 'annotations', 'xaxis', 'yaxis', 'editrevision', 'uirevision'].forEach(function (key) {
          if (layout[key] !== undefined) contextLayout[key] = layout[key];
        });
        const context = {
          item_id: itemId || null,
          layout: contextLayout,
          data: ((figure && figure.data) || []).map(function (trace) {
            return { type: trace.type, name: trace.name };
          }),
        };
        const meta = { item_id: itemId || null, layout: { meta: layout.meta || {} } };
        // Box edits must not reset display sliders or trigger their server callbacks.
        return [unchangedOrNext(previousContext, context), unchangedOrNext(previousMeta, meta)];
      },
    },
  });
}());
