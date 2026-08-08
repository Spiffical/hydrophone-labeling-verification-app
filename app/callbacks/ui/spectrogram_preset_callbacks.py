"""Callbacks for the unified spectrogram settings panel."""

from copy import deepcopy
from math import isfinite

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.services.spectrogram_presets import (
    apply_spectrogram_preset,
    find_matching_spectrogram_preset,
    get_spectrogram_presets,
)
from app.services.verify_modal_cache import has_verify_spectrogram_recommendations


def _generation_frequency_bounds(current_min, current_max, defaults):
    default_range = (defaults or {}).get("yaxis")
    if not isinstance(default_range, (list, tuple)) or len(default_range) != 2:
        return None
    try:
        default_min = 10 ** float(default_range[0])
        default_max = 10 ** float(default_range[1])
        lower = default_min if current_min in (None, "") else float(current_min)
        upper = default_max if current_max in (None, "") else float(current_max)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(isfinite(value) for value in (lower, upper)):
        return None
    lower = max(0.0, lower)
    if upper <= lower:
        return None
    return round(lower, 6), round(upper, 6)


def _preset_options(cfg, cache_key):
    options = []
    availability = {}
    for preset in get_spectrogram_presets(cfg):
        available = True
        if preset.get("scope") == "item":
            available = has_verify_spectrogram_recommendations(
                cache_key,
                metadata_key=preset.get("metadata_key"),
            )
        availability[preset["id"]] = available
        option = {
            "label": preset["label"],
            "value": preset["id"],
        }
        if not available:
            option["disabled"] = True
        options.append(option)
    options.append({"label": "Custom", "value": "custom"})
    availability["custom"] = True
    return options, availability


def _selected_preset_value(cfg, availability, current_min, current_max):
    if current_min not in (None, "") or current_max not in (None, ""):
        return "custom"
    matching = find_matching_spectrogram_preset(cfg)
    return matching if matching and availability.get(matching, False) else "custom"


def register_spectrogram_preset_callbacks(app):
    def register_preset_apply(prefix):
        @app.callback(
            Output("config-store", "data", allow_duplicate=True),
            Output(f"{prefix}-yaxis-min-input", "value", allow_duplicate=True),
            Output(f"{prefix}-yaxis-max-input", "value", allow_duplicate=True),
            Input(f"{prefix}-spectrogram-preset", "value"),
            State(f"{prefix}-spectrogram-preset", "options"),
            State("config-store", "data"),
            prevent_initial_call=True,
        )
        def apply_spectrogram_preset_selection(preset_id, options, cfg):
            if not preset_id:
                raise PreventUpdate
            selected = next(
                (option for option in (options or []) if option.get("value") == preset_id),
                None,
            )
            if not selected or selected.get("disabled"):
                raise PreventUpdate
            if preset_id == "custom":
                updated_cfg = deepcopy(cfg or {})
                spec_cfg = updated_cfg.get("spectrogram_render")
                spec_cfg = dict(spec_cfg) if isinstance(spec_cfg, dict) else {}
                spec_cfg["active_preset"] = "custom"
                updated_cfg["spectrogram_render"] = spec_cfg
                if updated_cfg == (cfg or {}):
                    raise PreventUpdate
                return updated_cfg, no_update, no_update
            updated_cfg = apply_spectrogram_preset(cfg, preset_id)
            if updated_cfg is None:
                raise PreventUpdate
            return updated_cfg, None, None

    def register_render_settings(prefix):
        @app.callback(
            Output("config-store", "data", allow_duplicate=True),
            Input(f"{prefix}-spectrogram-source", "value"),
            Input(f"{prefix}-spec-win-dur", "value"),
            Input(f"{prefix}-spec-overlap", "value"),
            Input(f"{prefix}-generate-spectrograms-btn", "n_clicks"),
            State("config-store", "data"),
            State("mode-tabs", "data"),
            State(f"{prefix}-display-range-defaults-store", "data"),
            State(f"{prefix}-yaxis-min-input", "value"),
            State(f"{prefix}-yaxis-max-input", "value"),
            prevent_initial_call=True,
        )
        def apply_render_settings(
            source,
            win_dur_s,
            overlap,
            generate_clicks,
            cfg,
            active_mode,
            display_range_defaults,
            current_y_min,
            current_y_max,
        ):
            if str(active_mode or "").strip().lower() != prefix:
                raise PreventUpdate
            triggered_id = ctx.triggered_id
            normalized_source = str(source or "existing").strip().lower()
            if normalized_source not in {"existing", "audio_generated"}:
                raise PreventUpdate

            cfg = cfg or {}
            spec_cfg = cfg.get("spectrogram_render", {})
            spec_cfg = dict(spec_cfg) if isinstance(spec_cfg, dict) else {}

            if triggered_id == f"{prefix}-spectrogram-source":
                if normalized_source == "audio_generated":
                    raise PreventUpdate
                updated_spec_cfg = dict(spec_cfg)
                updated_spec_cfg["source"] = "existing"
                if updated_spec_cfg == spec_cfg:
                    raise PreventUpdate
                updated_cfg = dict(cfg)
                updated_cfg["spectrogram_render"] = updated_spec_cfg
                return updated_cfg

            if triggered_id in {
                f"{prefix}-spec-win-dur",
                f"{prefix}-spec-overlap",
            }:
                raise PreventUpdate
            if triggered_id != f"{prefix}-generate-spectrograms-btn" or not generate_clicks:
                raise PreventUpdate
            if normalized_source != "audio_generated":
                raise PreventUpdate

            updated_spec_cfg = dict(spec_cfg)
            try:
                normalized_window = float(win_dur_s)
                normalized_overlap = float(overlap)
            except (TypeError, ValueError):
                raise PreventUpdate
            if not 0.05 <= normalized_window <= 30.0:
                raise PreventUpdate
            if not 0.0 <= normalized_overlap <= 0.99:
                raise PreventUpdate

            try:
                previous_window = float(spec_cfg.get("win_dur_s", 1.0))
                previous_overlap = float(spec_cfg.get("overlap", 0.5))
            except (TypeError, ValueError):
                previous_window = 1.0
                previous_overlap = 0.5
            generation_params_changed = (
                normalized_window != previous_window
                or normalized_overlap != previous_overlap
            )
            updated_spec_cfg["source"] = normalized_source
            updated_spec_cfg["win_dur_s"] = normalized_window
            updated_spec_cfg["overlap"] = normalized_overlap

            active_preset = (
                str(spec_cfg.get("active_preset") or "").strip()
                or find_matching_spectrogram_preset(cfg)
            )
            if not active_preset:
                frequency_bounds = _generation_frequency_bounds(
                    current_y_min,
                    current_y_max,
                    display_range_defaults,
                )
                if frequency_bounds:
                    updated_spec_cfg["freq_min_hz"] = frequency_bounds[0]
                    updated_spec_cfg["freq_max_hz"] = frequency_bounds[1]

            if generation_params_changed:
                custom_selected = str(spec_cfg.get("active_preset") or "").strip() == "custom"
                updated_spec_cfg.pop("active_preset", None)

                if custom_selected:
                    updated_spec_cfg["active_preset"] = "custom"
                else:
                    matching_cfg = dict(cfg)
                    matching_cfg["spectrogram_render"] = updated_spec_cfg
                    matching = find_matching_spectrogram_preset(matching_cfg)
                    if matching:
                        updated_spec_cfg["active_preset"] = matching

            if updated_spec_cfg == spec_cfg:
                raise PreventUpdate
            updated_cfg = dict(cfg)
            updated_cfg["spectrogram_render"] = updated_spec_cfg
            return updated_cfg

        @app.callback(
            Output(f"{prefix}-spectrogram-source", "value"),
            Output(f"{prefix}-spec-win-dur", "value"),
            Output(f"{prefix}-spec-overlap", "value"),
            Output(f"{prefix}-spec-win-dur", "disabled"),
            Output(f"{prefix}-spec-overlap", "disabled"),
            Input("config-store", "data"),
            State(f"{prefix}-spectrogram-source", "value"),
            State(f"{prefix}-spec-win-dur", "value"),
            State(f"{prefix}-spec-overlap", "value"),
        )
        def sync_render_settings(cfg, current_source, current_window, current_overlap):
            spec_cfg = (cfg or {}).get("spectrogram_render", {})
            if not isinstance(spec_cfg, dict):
                spec_cfg = {}
            source = str(spec_cfg.get("source") or "existing")
            source = source if source in {"existing", "audio_generated"} else "existing"
            pending_audio_settings = current_source == "audio_generated" and source == "existing"
            return (
                no_update if pending_audio_settings else source,
                no_update if pending_audio_settings else spec_cfg.get("win_dur_s", 1.0),
                no_update if pending_audio_settings else spec_cfg.get("overlap", 0.5),
                False,
                False,
            )

        @app.callback(
            Output(f"{prefix}-fft-parameters-collapse", "is_open"),
            Input(f"{prefix}-spectrogram-source", "value"),
        )
        def sync_fft_parameter_tray(source):
            return source == "audio_generated"

        app.clientside_callback(
            f"""
            function(clicks, request, overlayStyle, progressText, domReadyClicks, pollTick, source, winDur, overlap) {{
                var dc = window.dash_clientside || {{}};
                var context = dc.callback_context || {{}};
                var triggered = ((context.triggered || [{{}}])[0].prop_id || "").split(".")[0];
                var busyKey = "__spectrogramGenerateBusy_{prefix}";
                var expectedTrigger = "{prefix}-generate-spectrograms-btn";
                var requestMatches = String(((request || {{}}).trigger_id) || "") === expectedTrigger;
                var overlayVisible = String(((overlayStyle || {{}}).display) || "none") !== "none";

                if (triggered === expectedTrigger && Number(clicks || 0) > 0) {{
                    window[busyKey] = true;
                }}
                if (requestMatches && overlayVisible) {{
                    window[busyKey] = true;
                }}
                if (triggered === "specgen-page-loading-overlay" && !overlayVisible) {{
                    window[busyKey] = false;
                }}
                if (triggered === "specgen-overlay-dom-ready-signal") {{
                    window[busyKey] = false;
                }}
                if (triggered === "specgen-overlay-poll") {{
                    var overlayNode = document.getElementById("specgen-page-loading-overlay");
                    if (!overlayNode || window.getComputedStyle(overlayNode).display === "none") {{
                        window[busyKey] = false;
                    }}
                }}
                if (triggered === "specgen-overlay-request-store" && !requestMatches && !overlayVisible) {{
                    window[busyKey] = false;
                }}

                var isBusy = !!window[busyKey];
                var normalizedWindow = Number(winDur);
                var normalizedOverlap = Number(overlap);
                var isValid = (
                    String(source || "") === "audio_generated" &&
                    Number.isFinite(normalizedWindow) &&
                    normalizedWindow >= 0.05 &&
                    normalizedWindow <= 30.0 &&
                    Number.isFinite(normalizedOverlap) &&
                    normalizedOverlap >= 0.0 &&
                    normalizedOverlap <= 0.99
                );
                var progressMatch = String(progressText || "").match(/([0-9]+)[ ]+of[ ]+([0-9]+)[ ]+ready/i);
                var label = isBusy
                    ? (progressMatch ? "Generating " + progressMatch[1] + "/" + progressMatch[2] : "Generating...")
                    : "Generate spectrograms";
                return [
                    label,
                    isBusy ? "spectrogram-button-spinner" : "bi bi-play-fill",
                    isBusy || !isValid,
                    "btn btn-primary spectrogram-generate-btn" + (isBusy ? " spectrogram-generate-btn--busy" : ""),
                    isBusy ? "true" : "false"
                ];
            }}
            """,
            Output(f"{prefix}-generate-spectrograms-label", "children"),
            Output(f"{prefix}-generate-spectrograms-icon", "className"),
            Output(f"{prefix}-generate-spectrograms-btn", "disabled"),
            Output(f"{prefix}-generate-spectrograms-btn", "className"),
            Output(f"{prefix}-generate-spectrograms-btn", "aria-busy"),
            Input(f"{prefix}-generate-spectrograms-btn", "n_clicks"),
            Input("specgen-overlay-request-store", "data"),
            Input("specgen-page-loading-overlay", "style"),
            Input("specgen-load-progress-text", "children"),
            Input("specgen-overlay-dom-ready-signal", "n_clicks"),
            Input("specgen-overlay-poll", "n_intervals"),
            Input(f"{prefix}-spectrogram-source", "value"),
            Input(f"{prefix}-spec-win-dur", "value"),
            Input(f"{prefix}-spec-overlap", "value"),
        )

    for mode_prefix in ("label", "verify", "explore"):
        register_preset_apply(mode_prefix)
        register_render_settings(mode_prefix)

    @app.callback(
        Output("verify-spectrogram-preset", "options"),
        Output("verify-spectrogram-preset", "value"),
        Input("config-store", "data"),
        Input("verify-data-cache-key-store", "data"),
        Input("verify-yaxis-min-input", "value"),
        Input("verify-yaxis-max-input", "value"),
        State("verify-spectrogram-preset", "value"),
    )
    def sync_verify_spectrogram_presets(cfg, cache_key, current_min, current_max, current_value):
        options, availability = _preset_options(cfg, cache_key)
        value = _selected_preset_value(cfg, availability, current_min, current_max)
        if value == current_value:
            value = no_update
        return options, value

    def register_static_preset_sync(prefix):
        @app.callback(
            Output(f"{prefix}-spectrogram-preset", "options"),
            Output(f"{prefix}-spectrogram-preset", "value"),
            Input("config-store", "data"),
            Input(f"{prefix}-yaxis-min-input", "value"),
            Input(f"{prefix}-yaxis-max-input", "value"),
            State(f"{prefix}-spectrogram-preset", "value"),
        )
        def sync_spectrogram_presets(cfg, current_min, current_max, current_value):
            options, availability = _preset_options(cfg, None)
            value = _selected_preset_value(cfg, availability, current_min, current_max)
            if value == current_value:
                value = no_update
            return options, value

    register_static_preset_sync("label")
    register_static_preset_sync("explore")
