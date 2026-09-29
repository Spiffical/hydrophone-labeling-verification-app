"""Callbacks for the unified spectrogram settings panel."""

from math import isfinite

from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from app.services.spectrogram_presets import (
    apply_spectrogram_preset,
    find_matching_spectrogram_preset,
    get_spectrogram_presets,
)
from app.services.spectrogram_ranges import (
    add_custom_spectrogram_range,
    config_for_spectrogram_range,
    format_frequency_range,
    normalize_spectrogram_range_state,
    remove_custom_spectrogram_range,
    update_spectrogram_range_visibility,
)


def _config_for_active_visible_range(cfg, state):
    normalized = normalize_spectrogram_range_state(state, cfg)
    active_range_id = normalized.get("active_range_id")
    if active_range_id in normalized["preset_ids"]:
        return apply_spectrogram_preset(cfg, active_range_id) or cfg
    custom_range = next(
        (
            candidate
            for candidate in normalized["custom_ranges"]
            if candidate["id"] == active_range_id and candidate.get("visible")
        ),
        None,
    )
    if custom_range:
        return config_for_spectrogram_range(cfg, custom_range)
    return cfg


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


def register_spectrogram_preset_callbacks(app):
    def register_visible_ranges(prefix, *, modal=False):
        # The spectrogram modal has the same range controls as each mode's
        # Spectrogram menu, without a source switch or a mode of its own.
        if not modal:
            app.clientside_callback(
                "function(source) { return {display: source === 'audio_generated' ? 'block' : 'none'}; }",
                Output(f"{prefix}-spectrogram-range-controls", "style"),
                Input(f"{prefix}-spectrogram-source", "value"),
            )

        @app.callback(
            Output(f"{prefix}-spectrogram-extra-presets", "options"),
            Output(f"{prefix}-spectrogram-extra-presets", "value"),
            Output(f"{prefix}-spectrogram-custom-visible", "options"),
            Output(f"{prefix}-spectrogram-custom-visible", "value"),
            Output(f"{prefix}-spectrogram-custom-delete-list", "children"),
            Input("spectrogram-ranges-store", "data"),
            Input("config-store", "data"),
        )
        def sync_companion_range_controls(state, cfg):
            normalized = normalize_spectrogram_range_state(state, cfg)
            preset_options = [
                {"label": preset["label"], "value": preset["id"]}
                for preset in get_spectrogram_presets(cfg)
            ]
            custom_options = [
                {
                    "label": (
                        f"{candidate['label']} | "
                        f"{format_frequency_range(candidate['freq_min_hz'], candidate['freq_max_hz'])}"
                    ),
                    "value": candidate["id"],
                }
                for candidate in normalized["custom_ranges"]
            ]
            visible_custom = [
                candidate["id"]
                for candidate in normalized["custom_ranges"]
                if candidate.get("visible")
            ]
            delete_controls = [
                html.Button(
                    [
                        html.I(className="bi bi-trash3", **{"aria-hidden": "true"}),
                        html.Span(candidate["label"], className="spectrogram-custom-delete-label"),
                    ],
                    id={
                        "type": "spectrogram-custom-range-delete",
                        "prefix": prefix,
                        "range_id": candidate["id"],
                    },
                    n_clicks=0,
                    type="button",
                    className="spectrogram-custom-delete-btn",
                    title=f"Remove {candidate['label']}",
                    **{"aria-label": f"Remove {candidate['label']}"},
                )
                for candidate in normalized["custom_ranges"]
            ]
            return (
                preset_options,
                normalized["preset_ids"],
                custom_options,
                visible_custom,
                delete_controls,
            )

        @app.callback(
            Output("spectrogram-ranges-store", "data", allow_duplicate=True),
            Output("config-store", "data", allow_duplicate=True),
            Input(f"{prefix}-spectrogram-apply-ranges", "n_clicks"),
            State(f"{prefix}-spectrogram-extra-presets", "value"),
            State(f"{prefix}-spectrogram-custom-visible", "value"),
            State("spectrogram-ranges-store", "data"),
            State("config-store", "data"),
            State("mode-tabs", "data"),
            prevent_initial_call=True,
        )
        def apply_visible_range_selection(
            apply_clicks,
            preset_ids,
            visible_custom_ids,
            state,
            cfg,
            active_mode,
        ):
            if not modal and str(active_mode or "").strip().lower() != prefix:
                raise PreventUpdate
            if not apply_clicks:
                raise PreventUpdate
            current = normalize_spectrogram_range_state(state, cfg)
            updated = update_spectrogram_range_visibility(
                current,
                cfg,
                preset_ids=preset_ids or [],
                visible_custom_ids=visible_custom_ids or [],
            )
            if updated == current:
                raise PreventUpdate
            updated_cfg = _config_for_active_visible_range(cfg, updated)
            return updated, updated_cfg if updated_cfg != (cfg or {}) else no_update

        @app.callback(
            Output(f"{prefix}-spectrogram-custom-collapse", "is_open"),
            Output("spectrogram-ranges-store", "data", allow_duplicate=True),
            Output(f"{prefix}-spectrogram-custom-error", "children"),
            Output(f"{prefix}-spectrogram-custom-label", "value"),
            Output(f"{prefix}-spectrogram-custom-min", "value"),
            Output(f"{prefix}-spectrogram-custom-max", "value"),
            Input(f"{prefix}-spectrogram-add-range-btn", "n_clicks"),
            Input(f"{prefix}-spectrogram-custom-cancel", "n_clicks"),
            Input(f"{prefix}-spectrogram-custom-submit", "n_clicks"),
            State(f"{prefix}-spectrogram-custom-collapse", "is_open"),
            State(f"{prefix}-spectrogram-custom-label", "value"),
            State(f"{prefix}-spectrogram-custom-min", "value"),
            State(f"{prefix}-spectrogram-custom-max", "value"),
            State("spectrogram-ranges-store", "data"),
            State("config-store", "data"),
            prevent_initial_call=True,
        )
        def edit_custom_companion_range(
            add_clicks,
            cancel_clicks,
            submit_clicks,
            is_open,
            label,
            freq_min_hz,
            freq_max_hz,
            state,
            cfg,
        ):
            triggered = ctx.triggered_id
            if triggered == f"{prefix}-spectrogram-add-range-btn":
                return True, no_update, "", no_update, no_update, no_update
            if triggered == f"{prefix}-spectrogram-custom-cancel":
                return False, no_update, "", None, None, None
            if triggered != f"{prefix}-spectrogram-custom-submit" or not submit_clicks:
                raise PreventUpdate
            updated, error = add_custom_spectrogram_range(
                state,
                cfg,
                label=label,
                freq_min_hz=freq_min_hz,
                freq_max_hz=freq_max_hz,
            )
            if error:
                return True, no_update, error, no_update, no_update, no_update
            return False, updated, "", None, None, None

        @app.callback(
            Output("spectrogram-ranges-store", "data", allow_duplicate=True),
            Output("config-store", "data", allow_duplicate=True),
            Input(
                {
                    "type": "spectrogram-custom-range-delete",
                    "prefix": prefix,
                    "range_id": ALL,
                },
                "n_clicks",
            ),
            State(
                {
                    "type": "spectrogram-custom-range-delete",
                    "prefix": prefix,
                    "range_id": ALL,
                },
                "id",
            ),
            State("spectrogram-ranges-store", "data"),
            State("config-store", "data"),
            prevent_initial_call=True,
        )
        def delete_custom_visible_range(clicks, ids, state, cfg):
            triggered = ctx.triggered_id
            if not isinstance(triggered, dict):
                raise PreventUpdate
            range_id = triggered.get("range_id")
            click_count = 0
            for candidate_id, candidate_clicks in zip(ids or [], clicks or []):
                if candidate_id == triggered:
                    click_count = int(candidate_clicks or 0)
                    break
            if not range_id or click_count <= 0:
                raise PreventUpdate
            current = normalize_spectrogram_range_state(state, cfg)
            updated = remove_custom_spectrogram_range(current, cfg, range_id)
            if updated == current:
                raise PreventUpdate
            updated_cfg = _config_for_active_visible_range(cfg, updated)
            return updated, updated_cfg if updated_cfg != (cfg or {}) else no_update

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
            if not 0.001 <= normalized_window <= 30.0:
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
                    normalizedWindow >= 0.001 &&
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
        register_render_settings(mode_prefix)
        register_visible_ranges(mode_prefix)
    register_visible_ranges("modal", modal=True)

    # The × on a spectrogram in the modal hides that range; the last one stays.
    @app.callback(
        Output("spectrogram-ranges-store", "data", allow_duplicate=True),
        Output("config-store", "data", allow_duplicate=True),
        Input({"type": "modal-range-remove", "range": ALL}, "n_clicks"),
        Input("modal-active-range-remove", "n_clicks"),
        State("spectrogram-ranges-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def remove_modal_range(companion_clicks, active_clicks, state, cfg):
        current = normalize_spectrogram_range_state(state, cfg)
        triggered = ctx.triggered_id
        clicked = next(
            (entry.get("value") for entry in (ctx.triggered or []) if entry.get("value")),
            None,
        )
        if not clicked:
            raise PreventUpdate  # buttons appearing with a new render, not a click
        if triggered == "modal-active-range-remove":
            target = current.get("active_range_id")
        elif isinstance(triggered, dict) and triggered.get("type") == "modal-range-remove":
            target = triggered.get("range")
        else:
            raise PreventUpdate
        visible_custom = [
            candidate["id"] for candidate in current["custom_ranges"] if candidate.get("visible")
        ]
        if target not in current["preset_ids"] + visible_custom or len(current["preset_ids"]) + len(visible_custom) <= 1:
            raise PreventUpdate
        updated = update_spectrogram_range_visibility(
            current,
            cfg,
            preset_ids=[preset_id for preset_id in current["preset_ids"] if preset_id != target],
            visible_custom_ids=[range_id for range_id in visible_custom if range_id != target],
        )
        if updated == current:
            raise PreventUpdate
        updated_cfg = _config_for_active_visible_range(cfg, updated)
        return updated, updated_cfg if updated_cfg != (cfg or {}) else no_update
