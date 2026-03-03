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

    app.clientside_callback(
        """
        function(
            mode,
            cfg,
            labelLoadingState,
            verifyLoadingState,
            exploreLoadingState,
            labelStatus,
            verifyStatus,
            exploreStatus,
            labelPage,
            verifyPage,
            explorePage
        ) {
            var dc = (window.dash_clientside || {});
            var noUpdate = dc.no_update;

            function isLoading(state) {
                return !!(state && state.is_loading);
            }
            function getCurrentLoading() {
                if (mode === "verify") return isLoading(verifyLoadingState);
                if (mode === "explore") return isLoading(exploreLoadingState);
                return isLoading(labelLoadingState);
            }
            function getCurrentStatus() {
                if (mode === "verify") return verifyStatus || null;
                if (mode === "explore") return exploreStatus || null;
                return labelStatus || null;
            }
            function getCurrentPage() {
                if (mode === "verify") return Number(verifyPage || 0);
                if (mode === "explore") return Number(explorePage || 0);
                return Number(labelPage || 0);
            }

            if (!getCurrentLoading()) {
                return [{display: "none"}, noUpdate, noUpdate];
            }

            var source = (((cfg || {}).display || {}).spectrogram_source) || "existing";
            if (source !== "audio_generated") {
                return [{display: "none"}, noUpdate, noUpdate];
            }

            var status = getCurrentStatus();
            if (!status || typeof status !== "object") {
                return [{display: "none"}, noUpdate, noUpdate];
            }

            var statusPage = Number(status.page_index);
            var currentPage = getCurrentPage();
            if (Number.isFinite(statusPage) && statusPage !== currentPage) {
                return [{display: "none"}, noUpdate, noUpdate];
            }

            var pending = Number(status.pending || 0);
            if (!(pending > 0)) {
                return [{display: "none"}, noUpdate, noUpdate];
            }

            var eligible = Number(status.eligible || status.total || pending);
            if (!Number.isFinite(eligible) || eligible < pending) {
                eligible = pending;
            }
            var done = Math.max(0, eligible - pending);
            var title = "Generating spectrograms...";
            var subtitle =
                pending + " audio file" + (pending === 1 ? "" : "s") +
                " remaining on this page (" + done + "/" + eligible + " ready)";

            return [{display: "flex"}, title, subtitle];
        }
        """,
        Output("specgen-page-loading-overlay", "style"),
        Output("specgen-load-title", "children"),
        Output("specgen-load-subtitle", "children"),
        Input("mode-tabs", "data"),
        Input("config-store", "data"),
        Input("label-grid", "loading_state"),
        Input("verify-grid", "loading_state"),
        Input("explore-grid", "loading_state"),
        Input("label-page-specgen-store", "data"),
        Input("verify-page-specgen-store", "data"),
        Input("explore-page-specgen-store", "data"),
        Input("label-current-page", "data"),
        Input("verify-current-page", "data"),
        Input("explore-current-page", "data"),
        prevent_initial_call=True,
    )
