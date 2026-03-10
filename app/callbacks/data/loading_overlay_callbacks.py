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

            function show(title, subtitle, overlayMode) {
                window.__dataLoadOverlayState = {
                    mode: String(overlayMode || mode || "label"),
                    reason: String(triggerId || ""),
                    shown_at_ms: Date.now()
                };
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
                return show(title, subtitle, loadTrigger.mode);
            }

            if (!triggerVal) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }

            if (triggerId === "label-reload" && mode === "label") {
                return show("Loading dataset...", "Reloading items.", "label");
            }
            if (triggerId === "verify-reload" && mode === "verify") {
                return show("Loading dataset...", "Reloading predictions.", "verify");
            }
            if (triggerId === "explore-reload" && mode === "explore") {
                return show("Loading dataset...", "Reloading items for exploration.", "explore");
            }

            if (triggerId === "global-date-selector" || triggerId === "global-device-selector") {
                var tabData = mode === "label" ? labelData : (mode === "verify" ? verifyData : exploreData);
                var hasSource = tabData && tabData.source_data_dir;
                var summary = (tabData && tabData.summary) || {};
                var activeDate = summary.active_date || null;
                var activeDevice = summary.active_hydrophone || null;
                if (!hasSource) {
                    return [dc.no_update, dc.no_update, dc.no_update];
                }
                if (triggerId === "global-date-selector" && dateVal === activeDate) {
                    return [dc.no_update, dc.no_update, dc.no_update];
                }
                if (triggerId === "global-device-selector" && deviceVal === activeDevice) {
                    return [dc.no_update, dc.no_update, dc.no_update];
                }
                var title2 = "Updating filters...";
                var subtitle2 = "Loading data for the selected date/device.";
                if (mode === "verify") {
                    subtitle2 = "Loading predictions for the selected date/device.";
                } else if (mode === "explore") {
                    subtitle2 = "Loading items for exploration.";
                }
                return show(title2, subtitle2, mode);
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
        function(labelReady, verifyReady, exploreReady) {
            var dc = (window.dash_clientside || {});
            var overlayState = window.__dataLoadOverlayState || null;
            if (!overlayState || typeof overlayState !== "object") {
                return dc.no_update;
            }

            var overlayEl = document.getElementById("data-config-loading-overlay");
            if (!overlayEl || overlayEl.style.display === "none") {
                window.__dataLoadOverlayState = null;
                return dc.no_update;
            }

            function asFloat(v, fallback) {
                var n = Number(v);
                return Number.isFinite(n) ? n : fallback;
            }

            var overlayMode = String(overlayState.mode || "label");
            var readyPayload = overlayMode === "verify"
                ? verifyReady
                : overlayMode === "explore"
                    ? exploreReady
                    : labelReady;
            if (!readyPayload || typeof readyPayload !== "object") {
                return dc.no_update;
            }

            var shownAtMs = asFloat(overlayState.shown_at_ms, 0.0);
            var renderedAtMs = asFloat(readyPayload.rendered_at, 0.0) * 1000.0;
            if (renderedAtMs <= 0.0) {
                return dc.no_update;
            }

            // Render callbacks stamp `rendered_at` on every load/filter/reload completion.
            if (renderedAtMs >= (shownAtMs - 1500.0)) {
                window.__dataLoadOverlayState = null;
                return {"display": "none"};
            }

            return dc.no_update;
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        prevent_initial_call=True,
    )


    app.clientside_callback(
        """
        function(request, mode, cfg, labelStatus, verifyStatus, exploreStatus, labelReady, verifyReady, exploreReady) {
            var spec = ((cfg || {}).spectrogram_render || {});
            var source = String(spec.source || "existing");
            var requestTimingSlackMs = 1500.0;
            if (source !== "audio_generated") {
                return true;
            }

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
            function paramsMatch(a, b) {
                if (!a || !b) return false;
                var keys = ["win_dur_s", "overlap", "freq_min_hz", "freq_max_hz"];
                for (var i = 0; i < keys.length; i += 1) {
                    var k = keys[i];
                    if (Math.abs(asFloat(a[k], NaN) - asFloat(b[k], NaN)) > 1e-6) {
                        return false;
                    }
                }
                return true;
            }
            function statusForMode(m) {
                if (m === "verify") return verifyStatus || null;
                if (m === "explore") return exploreStatus || null;
                return labelStatus || null;
            }
            function readyForMode(m) {
                if (m === "verify") return verifyReady || null;
                if (m === "explore") return exploreReady || null;
                return labelReady || null;
            }
            function selectorForMode(m) {
                if (m === "verify") return "#verify-grid img.spectrogram-image";
                if (m === "explore") return "#explore-grid img.spectrogram-image";
                return "#label-grid img.spectrogram-image";
            }
            function domStatsForMode(m) {
                var imgs = Array.from(document.querySelectorAll(selectorForMode(m)));
                var total = imgs.length;
                var loaded = 0;
                for (var i = 0; i < imgs.length; i += 1) {
                    var img = imgs[i];
                    if (!!img.complete && asInt(img.naturalWidth, 0) > 0) {
                        loaded += 1;
                    }
                }
                return {
                    total: total,
                    loaded: loaded,
                    pending: Math.max(0, total - loaded)
                };
            }

            var activeMode = String(mode || "label");
            var activeStatus = statusForMode(activeMode);
            if (activeStatus && asInt(activeStatus.pending, 0) > 0) {
                return false;
            }

            if (!request || typeof request !== "object") {
                var activeReady = readyForMode(activeMode);
                if (
                    activeStatus &&
                    typeof activeStatus === "object" &&
                    activeReady &&
                    typeof activeReady === "object"
                ) {
                    var activeReadyPage = asInt(activeReady.page, -1);
                    var activeStatusPage = asInt(activeStatus.page_index, -2);
                    if (activeReadyPage === activeStatusPage) {
                        var activeDom = domStatsForMode(activeMode);
                        if (activeDom.total > 0 && activeDom.pending > 0) {
                            return false;
                        }
                    }
                }
                return true;
            }

            var reqMode = String(request.mode || activeMode);
            var reqStatus = statusForMode(reqMode);
            var reqReady = readyForMode(reqMode);
            var requestedAtMs = asFloat(request.requested_at_ms, 0.0);
            if (requestedAtMs <= 0.0) {
                return false;
            }

            if (Date.now() - requestedAtMs > 120000.0) {
                return true;
            }

            if (!reqStatus || typeof reqStatus !== "object") {
                if (reqReady && typeof reqReady === "object") {
                    var reqReadyPageMissing = asInt(reqReady.page, -1);
                    var reqReadyAtMissing = asFloat(reqReady.rendered_at, 0.0) * 1000.0;
                    if (reqReadyPageMissing === asInt(request.page, -2) && reqReadyAtMissing >= (requestedAtMs - requestTimingSlackMs)) {
                        var reqMissingDom = domStatsForMode(reqMode);
                        if (reqMissingDom.total > 0 && reqMissingDom.pending <= 0) {
                            return true;
                        }
                    }
                }
                return false;
            }

            var statusParams = reqStatus.params || null;
            if (!paramsMatch(request.params || null, statusParams)) {
                return false;
            }

            var statusPending = asInt(reqStatus.pending, 0);
            if (statusPending > 0) {
                return false;
            }

            if (!reqReady || typeof reqReady !== "object") {
                return false;
            }
            var readyPage = asInt(reqReady.page, -1);
            var statusPage = asInt(reqStatus.page_index, -2);
            var readyAtMs = asFloat(reqReady.rendered_at, 0.0) * 1000.0;
            if (readyPage === statusPage && readyAtMs >= (requestedAtMs - requestTimingSlackMs)) {
                var reqDom = domStatsForMode(reqMode);
                var reqEligible = Math.max(
                    asInt(reqStatus.pending, 0),
                    asInt(reqStatus.eligible, asInt(reqStatus.total, 0))
                );
                if (reqDom.total > 0) {
                    return reqDom.pending <= 0;
                }
                return reqEligible <= 0;
            }
            if (Date.now() - requestedAtMs > 15000.0) {
                return true;
            }
            return false;
        }
        """,
        Output("specgen-overlay-poll", "disabled"),
        Input("specgen-overlay-request-store", "data"),
        Input("mode-tabs", "data"),
        Input("config-store", "data"),
        Input("label-page-specgen-store", "data"),
        Input("verify-page-specgen-store", "data"),
        Input("explore-page-specgen-store", "data"),
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        prevent_initial_call=False,
    )

    app.clientside_callback(
        """
        function(
            saveClicks,
            labelPrevClicks,
            labelNextClicks,
            labelGotoClicks,
            verifyPrevClicks,
            verifyNextClicks,
            verifyGotoClicks,
            explorePrevClicks,
            exploreNextClicks,
            exploreGotoClicks,
            mode,
            cfg,
            labelPage,
            verifyPage,
            explorePage,
            modalSource,
            modalWinDur,
            modalOverlap,
            modalFreqMin,
            modalFreqMax,
            labelGotoValue,
            labelPageMax,
            verifyGotoValue,
            verifyPageMax,
            exploreGotoValue,
            explorePageMax,
            labelData,
            exploreData
        ) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (!ctx || !ctx.triggered || ctx.triggered.length === 0) {
                return dc.no_update;
            }
            var triggerId = String(ctx.triggered[0].prop_id || "").split(".")[0];
            if (
                triggerId !== "app-config-save" &&
                triggerId !== "label-prev-page" &&
                triggerId !== "label-next-page" &&
                triggerId !== "label-goto-page" &&
                triggerId !== "verify-prev-page" &&
                triggerId !== "verify-next-page" &&
                triggerId !== "verify-goto-page" &&
                triggerId !== "explore-prev-page" &&
                triggerId !== "explore-next-page" &&
                triggerId !== "explore-goto-page"
            ) {
                return dc.no_update;
            }

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
            function countEligibleOnPage(data, pageIndex, itemsPerPage) {
                var items = (((data || {}).items) || []);
                if (!Array.isArray(items) || items.length === 0) return 0;
                var startIdx = Math.max(0, asInt(pageIndex, 0)) * Math.max(1, asInt(itemsPerPage, 25));
                var endIdx = startIdx + Math.max(1, asInt(itemsPerPage, 25));
                var eligible = 0;
                for (var i = startIdx; i < endIdx && i < items.length; i += 1) {
                    var item = items[i];
                    if (item && item.audio_path) {
                        eligible += 1;
                    }
                }
                return eligible;
            }
            function syncOverlayEstimate(request) {
                var overlayEl = document.getElementById("specgen-page-loading-overlay");
                var titleEl = document.getElementById("specgen-load-title");
                var subtitleEl = document.getElementById("specgen-load-subtitle");
                var progressEl = document.getElementById("specgen-load-progress-text");
                var fillEl = document.getElementById("specgen-load-progress-fill");
                if (overlayEl) {
                    overlayEl.style.display = "flex";
                }
                if (titleEl) {
                    titleEl.textContent = "Generating spectrograms...";
                }
                var estimatedEligible = asInt((request || {}).estimated_eligible, -1);
                var estimatedPending = asInt((request || {}).estimated_pending, -1);
                if (estimatedEligible > 0 && estimatedPending >= 0) {
                    if (subtitleEl) {
                        subtitleEl.textContent =
                            estimatedPending + " audio file" + (estimatedPending === 1 ? "" : "s") +
                            " remaining on this page (0/" + estimatedEligible + " ready)";
                    }
                    if (progressEl) {
                        progressEl.textContent = "0/" + estimatedEligible + " spectrograms ready (" + estimatedPending + " left)";
                    }
                    if (fillEl) {
                        fillEl.style.width = "0%";
                        fillEl.className = "specgen-load-progress-fill specgen-load-progress-fill--determinate";
                    }
                    window.__specgenOverlayLast = "show:" + String((request || {}).mode || "") + ":" + String(estimatedPending);
                    window.__specgenOverlayLastMeta = {
                        mode: (request || {}).mode || null,
                        request_page: (request || {}).page || null,
                        pending: estimatedPending,
                        eligible: estimatedEligible,
                        estimated: true
                    };
                    window.__specgenOverlayLastChangedAtMs = Date.now();
                    return;
                }
                if (subtitleEl) {
                    subtitleEl.textContent = "Preparing spectrograms for this page...";
                }
                if (progressEl) {
                    progressEl.textContent = "Preparing current page...";
                }
                if (fillEl) {
                    fillEl.style.width = "34%";
                    fillEl.className = "specgen-load-progress-fill";
                }
                window.__specgenOverlayLastChangedAtMs = Date.now();
            }

            var spec = ((cfg || {}).spectrogram_render || {});
            var source = String(spec.source || "existing");
            var params = {
                win_dur_s: asFloat(spec.win_dur_s, 1.0),
                overlap: asFloat(spec.overlap, 0.9),
                freq_min_hz: asFloat(spec.freq_min_hz, 5.0),
                freq_max_hz: asFloat(spec.freq_max_hz, 100.0)
            };
            if (triggerId === "app-config-save") {
                source = String(modalSource || source || "existing");
                params = {
                    win_dur_s: asFloat(modalWinDur, params.win_dur_s),
                    overlap: asFloat(modalOverlap, params.overlap),
                    freq_min_hz: asFloat(modalFreqMin, params.freq_min_hz),
                    freq_max_hz: asFloat(modalFreqMax, params.freq_max_hz)
                };
            }
            if (source !== "audio_generated") {
                return null;
            }

            var activeMode = String(mode || "label");
            var page = activeMode === "verify"
                ? asInt(verifyPage, 0)
                : activeMode === "explore"
                    ? asInt(explorePage, 0)
                    : asInt(labelPage, 0);
            var nowMs = Date.now();

            function clampPage(p, maxPages) {
                var maxP = asInt(maxPages, 1);
                if (maxP < 1) maxP = 1;
                var pi = asInt(p, 0);
                if (pi < 0) return 0;
                if (pi > (maxP - 1)) return maxP - 1;
                return pi;
            }

            // Keep a short-lived local tracker so rapid next/prev clicks can still request
            // the likely target page even before Dash round-trips current-page store updates.
            var perModeState = window.__specgenOverlayPageHint || {};
            var modeState = perModeState[activeMode] || null;
            var hintPage = page;
            if (modeState && (nowMs - asFloat(modeState.at_ms, 0)) < 5000.0) {
                hintPage = asInt(modeState.page, page);
            }

            if (triggerId === "label-prev-page" || triggerId === "label-next-page" || triggerId === "label-goto-page") {
                if (activeMode === "label") {
                    if (triggerId === "label-prev-page") page = clampPage(hintPage - 1, labelPageMax);
                    else if (triggerId === "label-next-page") page = clampPage(hintPage + 1, labelPageMax);
                    else page = clampPage(asInt(labelGotoValue, hintPage + 1) - 1, labelPageMax);
                }
            } else if (triggerId === "verify-prev-page" || triggerId === "verify-next-page" || triggerId === "verify-goto-page") {
                if (activeMode === "verify") {
                    if (triggerId === "verify-prev-page") page = clampPage(hintPage - 1, verifyPageMax);
                    else if (triggerId === "verify-next-page") page = clampPage(hintPage + 1, verifyPageMax);
                    else page = clampPage(asInt(verifyGotoValue, hintPage + 1) - 1, verifyPageMax);
                }
            } else if (triggerId === "explore-prev-page" || triggerId === "explore-next-page" || triggerId === "explore-goto-page") {
                if (activeMode === "explore") {
                    if (triggerId === "explore-prev-page") page = clampPage(hintPage - 1, explorePageMax);
                    else if (triggerId === "explore-next-page") page = clampPage(hintPage + 1, explorePageMax);
                    else page = clampPage(asInt(exploreGotoValue, hintPage + 1) - 1, explorePageMax);
                }
            }

            perModeState[activeMode] = {page: page, at_ms: nowMs};
            window.__specgenOverlayPageHint = perModeState;

            var itemsPerPage = Math.max(1, asInt((((cfg || {}).display || {}).items_per_page), 25));
            var estimatedEligible = -1;
            if (activeMode === "label") {
                estimatedEligible = countEligibleOnPage(labelData, page, itemsPerPage);
            } else if (activeMode === "explore") {
                estimatedEligible = countEligibleOnPage(exploreData, page, itemsPerPage);
            }

            var request = {
                mode: activeMode,
                page: page,
                params: params,
                trigger_id: triggerId,
                requested_at_ms: nowMs,
                estimated_eligible: estimatedEligible,
                estimated_pending: estimatedEligible
            };
            window.__specgenOverlayLatestRequest = request;
            syncOverlayEstimate(request);
            return request;
        }
        """,
        Output("specgen-overlay-request-store", "data"),
        Input("app-config-save", "n_clicks"),
        Input("label-prev-page", "n_clicks"),
        Input("label-next-page", "n_clicks"),
        Input("label-goto-page", "n_clicks"),
        Input("verify-prev-page", "n_clicks"),
        Input("verify-next-page", "n_clicks"),
        Input("verify-goto-page", "n_clicks"),
        Input("explore-prev-page", "n_clicks"),
        Input("explore-next-page", "n_clicks"),
        Input("explore-goto-page", "n_clicks"),
        State("mode-tabs", "data"),
        State("config-store", "data"),
        State("label-current-page", "data"),
        State("verify-current-page", "data"),
        State("explore-current-page", "data"),
        State("app-config-spectrogram-source", "value"),
        State("app-config-spec-win-dur", "value"),
        State("app-config-spec-overlap", "value"),
        State("app-config-spec-freq-min", "value"),
        State("app-config-spec-freq-max", "value"),
        State("label-page-input", "value"),
        State("label-page-input", "max"),
        State("verify-page-input", "value"),
        State("verify-page-input", "max"),
        State("explore-page-input", "value"),
        State("explore-page-input", "max"),
        State("label-data-store", "data"),
        State("explore-data-store", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(
            request,
            previewStatus,
            pollTick,
            mode,
            labelStatus,
            verifyStatus,
            exploreStatus,
            labelReady,
            verifyReady,
            exploreReady
        ) {
            var dc = (window.dash_clientside || {});
            var noUpdate = dc.no_update;
            try {
                var requestTimingSlackMs = 1500.0;
                var requestTimeoutMs = 120000.0;
                var staleRequestGraceMs = 15000.0;

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
                function paramsMatch(a, b) {
                    if (!a || !b) return false;
                    var keys = ["win_dur_s", "overlap", "freq_min_hz", "freq_max_hz"];
                    for (var i = 0; i < keys.length; i += 1) {
                        var k = keys[i];
                        if (Math.abs(asFloat(a[k], NaN) - asFloat(b[k], NaN)) > 1e-6) {
                            return false;
                        }
                    }
                    return true;
                }
                function setMarker(marker, extra) {
                    window.__specgenOverlayLast = marker;
                    window.__specgenOverlayLastMeta = extra || null;
                    window.__specgenOverlayLastChangedAtMs = Date.now();
                }
                function hide(reason, extra) {
                    var overlayEl = document.getElementById("specgen-page-loading-overlay");
                    var titleEl = document.getElementById("specgen-load-title");
                    var subtitleEl = document.getElementById("specgen-load-subtitle");
                    var progressEl = document.getElementById("specgen-load-progress-text");
                    var fillEl = document.getElementById("specgen-load-progress-fill");
                    if (overlayEl) {
                        overlayEl.style.display = "none";
                    }
                    window.__specgenOverlayPreflight = null;
                    window.__specgenOverlayLatestRequest = null;
                    setMarker("hide:" + String(reason || ""), extra);
                    if (titleEl) titleEl.textContent = "";
                    if (subtitleEl) subtitleEl.textContent = "";
                    if (progressEl) progressEl.textContent = "";
                    if (fillEl) {
                        fillEl.style.width = "0%";
                        fillEl.className = "specgen-load-progress-fill";
                    }
                    return [{display: "none"}, "", "", "", {width: "0%"}, "specgen-load-progress-fill"];
                }
                function show(subtitle, extra) {
                    var marker = "show:" + String((extra || {}).mode || "") + ":" + String((extra || {}).pending || "prep");
                    var overlayEl = document.getElementById("specgen-page-loading-overlay");
                    var titleEl = document.getElementById("specgen-load-title");
                    var subtitleEl = document.getElementById("specgen-load-subtitle");
                    var progressEl = document.getElementById("specgen-load-progress-text");
                    var fillEl = document.getElementById("specgen-load-progress-fill");
                    if (overlayEl) {
                        overlayEl.style.display = "flex";
                    }
                    setMarker(marker, extra);
                    var progressText = "Preparing current page...";
                    var fillStyle = {width: "34%"};
                    var fillClass = "specgen-load-progress-fill";
                    var eligible = asInt((extra || {}).eligible, 0);
                    var pending = asInt((extra || {}).pending, -1);
                    if (eligible > 0 && pending >= 0) {
                        if (pending > eligible) pending = eligible;
                        var done = Math.max(0, eligible - pending);
                        var pct = Math.round((done / Math.max(1, eligible)) * 100.0);
                        if (pct < 0) pct = 0;
                        if (pct > 100) pct = 100;
                        progressText = done + "/" + eligible + " spectrograms ready (" + pending + " left)";
                        fillStyle = {width: String(pct) + "%"};
                        fillClass = "specgen-load-progress-fill specgen-load-progress-fill--determinate";
                    }
                    if (titleEl) titleEl.textContent = "Generating spectrograms...";
                    if (subtitleEl) subtitleEl.textContent = subtitle || "Preparing spectrograms for this page...";
                    if (progressEl) progressEl.textContent = progressText;
                    if (fillEl) {
                        fillEl.style.width = fillStyle.width;
                        fillEl.className = fillClass;
                    }
                    return [
                        {display: "flex"},
                        "Generating spectrograms...",
                        subtitle || "Preparing spectrograms for this page...",
                        progressText,
                        fillStyle,
                        fillClass
                    ];
                }
                function selectorForMode(m) {
                    if (m === "verify") return "#verify-grid img.spectrogram-image";
                    if (m === "explore") return "#explore-grid img.spectrogram-image";
                    return "#label-grid img.spectrogram-image";
                }
                function domStatsForMode(m) {
                    var imgs = Array.from(document.querySelectorAll(selectorForMode(m)));
                    var total = imgs.length;
                    var loaded = 0;
                    var failed = 0;
                    for (var i = 0; i < imgs.length; i += 1) {
                        var img = imgs[i];
                        var complete = !!img.complete;
                        var naturalWidth = asInt(img.naturalWidth, 0);
                        if (complete && naturalWidth > 0) {
                            loaded += 1;
                        } else if (complete && String(img.getAttribute("src") || "")) {
                            failed += 1;
                        }
                    }
                    return {
                        total: total,
                        loaded: loaded,
                        failed: failed,
                        pending: Math.max(0, total - loaded)
                    };
                }
                function readyPageInfo(m, reqPage, requestedAtMs) {
                    var readyPayload = readyForMode(m);
                    if (!readyPayload || typeof readyPayload !== "object") {
                        return {
                            payload: null,
                            page: -1,
                            at_ms: 0.0,
                            fresh: false,
                            matches_request: false
                        };
                    }
                    var pageIndex = asInt(readyPayload.page, -1);
                    var atMs = asFloat(readyPayload.rendered_at, 0.0) * 1000.0;
                    var fresh = atMs >= (requestedAtMs - requestTimingSlackMs);
                    return {
                        payload: readyPayload,
                        page: pageIndex,
                        at_ms: atMs,
                        fresh: fresh,
                        matches_request: fresh && pageIndex === reqPage
                    };
                }
                function overlaySubtitleFor(kind, pending, done, eligible) {
                    if (kind === "image") {
                        return pending + " spectrogram" + (pending === 1 ? "" : "s") +
                            " remaining to load on this page (" + done + "/" + eligible + " ready)";
                    }
                    return pending + " audio file" + (pending === 1 ? "" : "s") +
                        " remaining on this page (" + done + "/" + eligible + " ready)";
                }
                function statusForMode(m) {
                    if (m === "verify") return verifyStatus || null;
                    if (m === "explore") return exploreStatus || null;
                    return labelStatus || null;
                }
                function requestStatusForMode(m, req) {
                    var liveStatus = statusForMode(m);
                    if (!previewStatus || typeof previewStatus !== "object") {
                        return liveStatus || null;
                    }
                    var requestPage = asInt(((req || {}).page), -1);
                    var requestParams = ((req || {}).params) || null;
                    var previewMode = String(previewStatus.mode || m);
                    var previewPage = asInt(previewStatus.page_index, -2);
                    if (previewMode !== m || previewPage !== requestPage) {
                        return liveStatus || null;
                    }
                    if (!paramsMatch(requestParams, previewStatus.params || null)) {
                        return liveStatus || null;
                    }
                    if (!liveStatus || typeof liveStatus !== "object") {
                        return previewStatus;
                    }
                    var livePage = asInt(liveStatus.page_index, -3);
                    var liveAtMs = asFloat(liveStatus.computed_at, 0.0) * 1000.0;
                    var previewAtMs = asFloat(previewStatus.computed_at, 0.0) * 1000.0;
                    var liveMatchesRequest = (
                        livePage === requestPage &&
                        paramsMatch(requestParams, liveStatus.params || null)
                    );
                    if (!liveMatchesRequest || previewAtMs > liveAtMs) {
                        return previewStatus;
                    }
                    return liveStatus;
                }
                function readyForMode(m) {
                    if (m === "verify") return verifyReady || null;
                    if (m === "explore") return exploreReady || null;
                    return labelReady || null;
                }

                var activeRequest = (request && typeof request === "object")
                    ? request
                    : (window.__specgenOverlayLatestRequest || null);
                if (!activeRequest || typeof activeRequest !== "object") {
                    var fallbackMode = String(mode || "label");
                    var fallbackStatus = statusForMode(fallbackMode);
                    if (fallbackStatus && typeof fallbackStatus === "object") {
                        var fallbackPage = asInt(fallbackStatus.page_index, -1);
                        var fallbackPending = Math.max(0, asInt(fallbackStatus.pending, 0));
                        var fallbackEligible = Math.max(
                            fallbackPending,
                            asInt(fallbackStatus.eligible, asInt(fallbackStatus.total, fallbackPending))
                        );
                        if (fallbackPending > 0) {
                            var fallbackDone = Math.max(0, fallbackEligible - fallbackPending);
                            return show(
                                fallbackPending + " audio file" + (fallbackPending === 1 ? "" : "s") +
                                " remaining on this page (" + fallbackDone + "/" + fallbackEligible + " ready)",
                                {
                                    mode: fallbackMode,
                                    pending: fallbackPending,
                                    eligible: fallbackEligible,
                                    status_page: fallbackPage,
                                    fallback: true
                                }
                            );
                        }
                        var fallbackReadyInfo = readyPageInfo(fallbackMode, fallbackPage, Date.now());
                        if (fallbackReadyInfo.matches_request) {
                            var fallbackDom = domStatsForMode(fallbackMode);
                            if (fallbackDom.total > 0 && fallbackDom.pending > 0) {
                                var fallbackDomEligible = Math.max(fallbackEligible, fallbackDom.total);
                                return show(
                                    overlaySubtitleFor("image", fallbackDom.pending, fallbackDom.loaded, fallbackDomEligible),
                                    {
                                        mode: fallbackMode,
                                        pending: fallbackDom.pending,
                                        eligible: fallbackDomEligible,
                                        status_page: fallbackPage,
                                        ready_page: fallbackReadyInfo.page,
                                        dom_total: fallbackDom.total,
                                        dom_loaded: fallbackDom.loaded,
                                        dom_failed: fallbackDom.failed,
                                        fallback: true,
                                        phase: "image"
                                    }
                                );
                            }
                            if (fallbackReadyInfo.page === fallbackPage) {
                                return hide("no-request-page-already-rendered", {
                                    mode: fallbackMode,
                                    status_page: fallbackPage,
                                    ready_page: fallbackReadyInfo.page
                                });
                            }
                        }
                    }
                    return hide("no-request");
                }

                var activeMode = String(activeRequest.mode || mode || "label");
                var st = requestStatusForMode(activeMode, activeRequest);
                var ready = readyForMode(activeMode);
                var requestPage = asInt(activeRequest.page, -1);
                var requestParams = activeRequest.params || null;
                var requestedAtMs = asFloat(activeRequest.requested_at_ms, 0.0);
                var estimatedEligible = Math.max(0, asInt(activeRequest.estimated_eligible, -1));
                var estimatedPending = Math.max(0, asInt(activeRequest.estimated_pending, -1));
                if (requestedAtMs <= 0.0) {
                    requestedAtMs = Date.now();
                }
                var readyInfo = readyPageInfo(activeMode, requestPage, requestedAtMs);
                var domStats = readyInfo.matches_request ? domStatsForMode(activeMode) : {
                    total: 0,
                    loaded: 0,
                    failed: 0,
                    pending: 0
                };

                if (!st || typeof st !== "object") {
                    var ageWithoutStatusMs = Date.now() - requestedAtMs;
                    if (readyInfo.matches_request && domStats.total > 0 && domStats.pending <= 0) {
                        return hide("missing-status-dom-ready", {
                            mode: activeMode,
                            request_page: requestPage,
                            age_ms: ageWithoutStatusMs,
                            ready_page: readyInfo.page,
                            dom_total: domStats.total,
                            dom_loaded: domStats.loaded
                        });
                    }
                    if (ageWithoutStatusMs > requestTimeoutMs) {
                        return hide("request-timeout-missing-status", {
                            mode: activeMode,
                            request_page: requestPage,
                            age_ms: ageWithoutStatusMs
                        });
                    }
                    if (ageWithoutStatusMs > staleRequestGraceMs) {
                        return hide("missing-status-stale", {
                            mode: activeMode,
                            request_page: requestPage,
                            age_ms: ageWithoutStatusMs,
                            ready_page: readyInfo.page,
                            dom_total: domStats.total,
                            dom_loaded: domStats.loaded,
                            dom_pending: domStats.pending
                        });
                    }
                    if (readyInfo.matches_request && domStats.total > 0 && domStats.pending > 0) {
                        return show(
                            overlaySubtitleFor("image", domStats.pending, domStats.loaded, domStats.total),
                            {
                                mode: activeMode,
                                pending: domStats.pending,
                                eligible: domStats.total,
                                request_page: requestPage,
                                age_ms: ageWithoutStatusMs,
                                ready_page: readyInfo.page,
                                dom_total: domStats.total,
                                dom_loaded: domStats.loaded,
                                dom_failed: domStats.failed,
                                missing_status: true,
                                phase: "image"
                            }
                        );
                    }
                    if (estimatedEligible > 0) {
                        return show(
                            overlaySubtitleFor("audio", estimatedPending, 0, estimatedEligible),
                            {
                                mode: activeMode,
                                pending: estimatedPending,
                                eligible: estimatedEligible,
                                request_page: requestPage,
                                age_ms: ageWithoutStatusMs,
                                missing_status: true,
                                estimated: true
                            }
                        );
                    }
                    return show("Preparing spectrograms for this page...", {
                        mode: activeMode,
                        request_page: requestPage,
                        age_ms: ageWithoutStatusMs,
                        missing_status: true
                    });
                }

                var statusPage = asInt(st.page_index, -1);
                var statusAtMs = asFloat(st.computed_at, 0.0) * 1000.0;
                var statusPending = Math.max(0, asInt(st.pending, 0));
                var statusEligible = Math.max(
                    statusPending,
                    asInt(st.eligible, asInt(st.total, statusPending))
                );
                var statusFresh = statusAtMs >= (requestedAtMs - requestTimingSlackMs);
                var statusParamsAligned = paramsMatch(requestParams, st.params || null);
                var statusCurrent = statusFresh && statusParamsAligned && statusPage === requestPage;
                var effectiveEligible = statusEligible;
                var effectivePending = statusPending;
                var overlayKind = "audio";

                if (readyInfo.matches_request && domStats.total > 0) {
                    effectiveEligible = Math.max(statusEligible, domStats.total);
                    effectivePending = Math.max(statusPending, domStats.pending);
                    if (domStats.pending > statusPending) {
                        overlayKind = "image";
                    }
                }

                if (statusCurrent && effectivePending > 0) {
                    var statusDone = Math.max(0, effectiveEligible - effectivePending);
                    return show(
                        overlaySubtitleFor(overlayKind, effectivePending, statusDone, effectiveEligible),
                        {
                            mode: activeMode,
                            pending: effectivePending,
                            eligible: effectiveEligible,
                            request_page: requestPage,
                            status_page: statusPage,
                            status_at_ms: statusAtMs,
                            dom_total: domStats.total,
                            dom_loaded: domStats.loaded,
                            dom_failed: domStats.failed,
                            phase: overlayKind
                        }
                    );
                }

                if (statusCurrent && statusPending <= 0) {
                    if (readyInfo.matches_request && domStats.total > 0 && domStats.pending > 0) {
                        return show(
                            overlaySubtitleFor("image", domStats.pending, domStats.loaded, Math.max(statusEligible, domStats.total)),
                            {
                                mode: activeMode,
                                pending: domStats.pending,
                                eligible: Math.max(statusEligible, domStats.total),
                                request_page: requestPage,
                                status_page: statusPage,
                                status_at_ms: statusAtMs,
                                dom_total: domStats.total,
                                dom_loaded: domStats.loaded,
                                dom_failed: domStats.failed,
                                phase: "image"
                            }
                        );
                    }
                    return hide("status-ready-no-pending", {
                        mode: activeMode,
                        request_page: requestPage,
                        status_page: statusPage,
                        status_at_ms: statusAtMs,
                        requested_at_ms: requestedAtMs
                    });
                }

                if (readyInfo.payload) {
                    if (
                        readyInfo.matches_request &&
                        statusCurrent &&
                        statusEligible <= 0
                    ) {
                        if (domStats.total > 0 && domStats.pending > 0) {
                            return show(
                                overlaySubtitleFor("image", domStats.pending, domStats.loaded, domStats.total),
                                {
                                    mode: activeMode,
                                    pending: domStats.pending,
                                    eligible: domStats.total,
                                    request_page: requestPage,
                                    status_page: statusPage,
                                    ready_page: readyInfo.page,
                                    ready_at_ms: readyInfo.at_ms,
                                    dom_total: domStats.total,
                                    dom_loaded: domStats.loaded,
                                    dom_failed: domStats.failed,
                                    phase: "image"
                                }
                            );
                        }
                        return hide("render-ready-no-eligible-work", {
                            mode: activeMode,
                            request_page: requestPage,
                            status_page: statusPage,
                            ready_page: readyInfo.page,
                            ready_at_ms: readyInfo.at_ms,
                            requested_at_ms: requestedAtMs
                        });
                    }
                }

                var ageMs = Date.now() - requestedAtMs;
                if (readyInfo.matches_request && domStats.total > 0) {
                    if (domStats.pending > 0) {
                        return show(
                            overlaySubtitleFor("image", domStats.pending, domStats.loaded, domStats.total),
                            {
                                mode: activeMode,
                                pending: domStats.pending,
                                eligible: domStats.total,
                                request_page: requestPage,
                                status_page: statusPage,
                                status_fresh: statusFresh,
                                status_params_aligned: statusParamsAligned,
                                age_ms: ageMs,
                                dom_total: domStats.total,
                                dom_loaded: domStats.loaded,
                                dom_failed: domStats.failed,
                                phase: "image"
                            }
                        );
                    }
                    return hide("dom-ready-request-mismatch", {
                        mode: activeMode,
                        request_page: requestPage,
                        status_page: statusPage,
                        age_ms: ageMs,
                        ready_page: readyInfo.page,
                        dom_total: domStats.total,
                        dom_loaded: domStats.loaded
                    });
                }
                if (ageMs > requestTimeoutMs) {
                    return hide("request-timeout", {
                        mode: activeMode,
                        request_page: requestPage,
                        status_page: statusPage,
                        age_ms: ageMs
                    });
                }
                if (ageMs > staleRequestGraceMs) {
                    return hide("stale-request", {
                        mode: activeMode,
                        request_page: requestPage,
                        status_page: statusPage,
                        age_ms: ageMs,
                        status_fresh: statusFresh,
                        status_params_aligned: statusParamsAligned
                    });
                }
                if (estimatedEligible > 0) {
                    return show(
                        overlaySubtitleFor("audio", estimatedPending, 0, estimatedEligible),
                        {
                            mode: activeMode,
                            pending: estimatedPending,
                            eligible: estimatedEligible,
                            request_page: requestPage,
                            status_page: statusPage,
                            status_fresh: statusFresh,
                            status_params_aligned: statusParamsAligned,
                            age_ms: ageMs,
                            estimated: true
                        }
                    );
                }
                return show("Preparing spectrograms for this page...", {
                    mode: activeMode,
                    request_page: requestPage,
                    status_page: statusPage,
                    status_fresh: statusFresh,
                    status_params_aligned: statusParamsAligned,
                    age_ms: ageMs
                });
            } catch (error) {
                var message = (error && error.message) ? error.message : String(error);
                var overlayEl = document.getElementById("specgen-page-loading-overlay");
                if (overlayEl) {
                    overlayEl.style.display = "none";
                }
                window.__specgenOverlayPreflight = null;
                window.__specgenOverlayLast = "error:" + message;
                window.__specgenOverlayLastMeta = {message: message};
                console.error("[specgen-overlay] clientside error", error);
                return [{display: "none"}, noUpdate, noUpdate, noUpdate, noUpdate, noUpdate];
            }
        }
        """,
        Output("specgen-page-loading-overlay", "style"),
        Output("specgen-load-title", "children"),
        Output("specgen-load-subtitle", "children"),
        Output("specgen-load-progress-text", "children"),
        Output("specgen-load-progress-fill", "style"),
        Output("specgen-load-progress-fill", "className"),
        Input("specgen-overlay-request-store", "data"),
        Input("specgen-overlay-preview-store", "data"),
        Input("specgen-overlay-poll", "n_intervals"),
        Input("mode-tabs", "data"),
        Input("label-page-specgen-store", "data"),
        Input("verify-page-specgen-store", "data"),
        Input("explore-page-specgen-store", "data"),
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(overlayStyle, request) {
            var dc = (window.dash_clientside || {});
            if (!request || typeof request !== "object") {
                return dc.no_update;
            }
            if (!overlayStyle || typeof overlayStyle !== "object") {
                return dc.no_update;
            }
            if (String(overlayStyle.display || "") !== "none") {
                return dc.no_update;
            }
            return null;
        }
        """,
        Output("specgen-overlay-request-store", "data", allow_duplicate=True),
        Input("specgen-page-loading-overlay", "style"),
        State("specgen-overlay-request-store", "data"),
        prevent_initial_call=True,
    )
