(function () {
    const controls = ['verify-threshold-slider', 'verify-status-filter'];

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        progressSegment: {
            // Clicking a bar segment sets the range and status to match it, so any other
            // change means the reviewer has moved on. This runs in the browser because the
            // grid waits for it: a server round trip here would slow every filter change.
            release: function (range, status, classes, allCategories, date, device, view) {
                const dc = window.dash_clientside;
                const segment = view && view.segment;
                if (!segment) return dc.no_update;
                const changed = (dc.callback_context.triggered || []).map(t => t.prop_id.split('.')[0]);
                const matches = changed.every(id => controls.includes(id))
                    && status === segment.state
                    && Array.isArray(range)
                    && range[0] === segment.range[0]
                    && range[1] === segment.range[1];
                return matches ? dc.no_update : Object.assign({}, view, { segment: null });
            },
        },
    });
}());
