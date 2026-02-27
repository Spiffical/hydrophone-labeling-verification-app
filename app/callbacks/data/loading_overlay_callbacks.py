"""Clientside loading-overlay callback for dataset load/filter events."""

from dash import Input, Output, State


def register_loading_overlay_callbacks(app):
    app.clientside_callback(
        """
        function(loadTrigger, labelReload, verifyReload, exploreReload, dateVal, deviceVal, mode, labelData, verifyData, exploreData) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (!ctx || !ctx.triggered || ctx.triggered.length === 0) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }

            var triggered = ctx.triggered[0];
            var triggerId = triggered.prop_id.split('.')[0];
            var triggerVal = triggered.value;

            function show(title, subtitle) {
                return [{display: "flex"}, title, subtitle];
            }

            if (triggerId === "data-load-trigger-store" && loadTrigger && loadTrigger.mode) {
                var title = "Loading dataset...";
                var subtitle = "Applying configuration and preparing your workspace.";
                if (loadTrigger.mode === "verify") {
                    subtitle = "Applying configuration and loading predictions.";
                } else if (loadTrigger.mode === "label") {
                    subtitle = "Applying configuration and loading items.";
                } else if (loadTrigger.mode === "explore") {
                    subtitle = "Applying configuration and loading items for exploration.";
                }
                return show(title, subtitle);
            }

            if (!triggerVal) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }

            if (triggerId === "label-reload" && mode === "label") {
                return show("Loading dataset...", "Reloading items.");
            }
            if (triggerId === "verify-reload" && mode === "verify") {
                return show("Loading dataset...", "Reloading predictions.");
            }
            if (triggerId === "explore-reload" && mode === "explore") {
                return show("Loading dataset...", "Reloading items for exploration.");
            }

            if (triggerId === "global-date-selector" || triggerId === "global-device-selector") {
                var tabData = mode === "label" ? labelData : (mode === "verify" ? verifyData : exploreData);
                var hasSource = tabData && tabData.source_data_dir;
                if (!hasSource) {
                    return [dc.no_update, dc.no_update, dc.no_update];
                }
                var title2 = "Updating filters...";
                var subtitle2 = "Loading data for the selected date/device.";
                if (mode === "verify") {
                    subtitle2 = "Loading predictions for the selected date/device.";
                } else if (mode === "explore") {
                    subtitle2 = "Loading items for exploration.";
                }
                return show(title2, subtitle2);
            }

            return [dc.no_update, dc.no_update, dc.no_update];
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Output("data-load-title", "children", allow_duplicate=True),
        Output("data-load-subtitle", "children", allow_duplicate=True),
        Input("data-load-trigger-store", "data"),
        Input("label-reload", "n_clicks"),
        Input("verify-reload", "n_clicks"),
        Input("explore-reload", "n_clicks"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        prevent_initial_call=True,
    )
