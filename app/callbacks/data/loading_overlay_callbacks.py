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
            pollTick,
            labelStatus,
            verifyStatus,
            exploreStatus,
            labelReady,
            verifyReady,
            exploreReady,
            labelPage,
            verifyPage,
            explorePage
        ) {
            var dc = (window.dash_clientside || {});
            var noUpdate = dc.no_update;
            var _ = pollTick, _ready1 = labelReady, _ready2 = verifyReady, _ready3 = exploreReady;

            function asInt(v, fallback) {
                var n = Number(v);
                if (!Number.isFinite(n)) return fallback;
                n = Math.floor(n);
                return n < 0 ? 0 : n;
            }

            function asFloat(v, fallback) {
                var n = Number(v);
                return Number.isFinite(n) ? n : fallback;
            }

            function nearlyEqual(a, b) {
                return Math.abs(a - b) <= 1e-9;
            }

            function extractCfgParams(inputCfg) {
                var spec = ((inputCfg || {}).spectrogram_render || {});
                return {
                    win_dur_s: asFloat(spec.win_dur_s, 1.0),
                    overlap: asFloat(spec.overlap, 0.9),
                    freq_min_hz: asFloat(spec.freq_min_hz, 5.0),
                    freq_max_hz: asFloat(spec.freq_max_hz, 100.0)
                };
            }

            function paramsMatch(statusParams, cfgParams) {
                if (!statusParams || typeof statusParams !== "object") return false;
                return (
                    nearlyEqual(asFloat(statusParams.win_dur_s, NaN), cfgParams.win_dur_s) &&
                    nearlyEqual(asFloat(statusParams.overlap, NaN), cfgParams.overlap) &&
                    nearlyEqual(asFloat(statusParams.freq_min_hz, NaN), cfgParams.freq_min_hz) &&
                    nearlyEqual(asFloat(statusParams.freq_max_hz, NaN), cfgParams.freq_max_hz)
                );
            }

            function getCurrentStatus() {
                if (mode === "verify") return verifyStatus || null;
                if (mode === "explore") return exploreStatus || null;
                return labelStatus || null;
            }

            function getCurrentPage() {
                if (mode === "verify") return asInt(verifyPage, 0);
                if (mode === "explore") return asInt(explorePage, 0);
                return asInt(labelPage, 0);
            }

            var status = getCurrentStatus();
            var source =
                (status && status.source) ||
                (((cfg || {}).display || {}).spectrogram_source) ||
                (((cfg || {}).spectrogram_render || {}).source) ||
                "existing";

            if (source !== "audio_generated") {
                console.debug("[specgen-overlay] hidden: source-not-audio", {mode: mode, source: source});
                return [{display: "none"}, noUpdate, noUpdate];
            }

            if (!status || typeof status !== "object") {
                console.debug("[specgen-overlay] hidden: missing-status", {mode: mode});
                return [{display: "none"}, noUpdate, noUpdate];
            }

            var activePage = getCurrentPage();
            var statusPage = asInt(status.page_index, 0);
            var cfgParams = extractCfgParams(cfg);
            var statusParams = status.params || null;
            var statusIsForActivePage = (statusPage === activePage);
            var statusIsForCurrentParams = paramsMatch(statusParams, cfgParams);

            if (!statusIsForActivePage || !statusIsForCurrentParams) {
                var staleReason = !statusIsForActivePage ? "page-mismatch" : "params-mismatch";
                var staleSubtitle =
                    staleReason === "page-mismatch"
                        ? "Preparing spectrograms for this page..."
                        : "Applying new spectrogram settings to this page...";
                console.debug("[specgen-overlay] showing: stale-status", {
                    mode: mode,
                    stale_reason: staleReason,
                    active_page: activePage,
                    status_page: statusPage,
                    cfg_params: cfgParams,
                    status_params: statusParams,
                    pending: status.pending,
                    eligible: status.eligible
                });
                return [{display: "flex"}, "Generating spectrograms...", staleSubtitle];
            }

            var pending = asInt(status.pending, 0);
            if (!(pending > 0)) {
                console.debug("[specgen-overlay] hidden: page-ready", {
                    mode: mode,
                    page: activePage,
                    pending: pending,
                    eligible: status.eligible,
                    source: source,
                    params: statusParams
                });
                return [{display: "none"}, noUpdate, noUpdate];
            }

            var eligible = asInt(status.eligible, asInt(status.total, pending));
            if (eligible < pending) {
                eligible = pending;
            }
            var done = Math.max(0, eligible - pending);
            var title = "Generating spectrograms...";
            var subtitle =
                pending + " audio file" + (pending === 1 ? "" : "s") +
                " remaining on this page (" + done + "/" + eligible + " ready)";

            console.debug("[specgen-overlay] showing: pending", {
                mode: mode,
                page: activePage,
                pending: pending,
                eligible: eligible,
                done: done,
                source: source,
                params: statusParams
            });
            return [{display: "flex"}, title, subtitle];
        }
        """,
        Output("specgen-page-loading-overlay", "style"),
        Output("specgen-load-title", "children"),
        Output("specgen-load-subtitle", "children"),
        Input("mode-tabs", "data"),
        Input("config-store", "data"),
        Input("specgen-overlay-poll", "n_intervals"),
        Input("label-page-specgen-store", "data"),
        Input("verify-page-specgen-store", "data"),
        Input("explore-page-specgen-store", "data"),
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        Input("label-current-page", "data"),
        Input("verify-current-page", "data"),
        Input("explore-current-page", "data"),
        prevent_initial_call=True,
    )
