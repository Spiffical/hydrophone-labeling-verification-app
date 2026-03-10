"""Data-config load/overlay/warning callbacks."""

import os

from dash import ALL, Input, Output, State, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.data.config_load_helpers import (
    apply_config_data_section,
    build_load_trigger_value,
    compute_global_filter_options,
    compute_label_tab_displays,
)
from app.utils.data_discovery import detect_data_structure


def register_data_config_load_callbacks(app, *, tab_iso_debug):
    """Register callbacks that apply selected config and trigger data load."""

    @app.callback(
        Output("data-config-modal", "is_open", allow_duplicate=True),
        Output("config-store", "data", allow_duplicate=True),
        Output("global-data-dir-display", "children", allow_duplicate=True),
        Output("global-date-selector", "options", allow_duplicate=True),
        Output("global-date-selector", "value", allow_duplicate=True),
        Output("global-device-selector", "options", allow_duplicate=True),
        Output("global-device-selector", "value", allow_duplicate=True),
        Output("label-spec-folder-display", "children"),
        Output("label-audio-folder-display", "children"),
        Output("label-output-input", "value", allow_duplicate=True),
        Output("data-load-trigger-store", "data"),
        Input("data-config-load", "n_clicks"),
        State("data-discovery-store", "data"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("data-config-predictions-file", "value"),
        State("predictions-files-store", "data"),
        State({"type": "predictions-file-input", "index": ALL}, "value"),
        State({"type": "predictions-file-input", "index": ALL}, "id"),
        State("data-root-path-store", "data"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("global-date-selector", "value"),
        State("global-device-selector", "value"),
        prevent_initial_call=True,
    )
    def load_data_from_config(
        load_clicks,
        discovery,
        spec_folder,
        audio_folder,
        predictions_file,
        predictions_entries,
        predictions_values,
        predictions_ids,
        base_path,
        config,
        current_mode,
        current_date_value,
        current_device_value,
    ):
        if not load_clicks:
            raise PreventUpdate

        if not base_path:
            base_path = (config or {}).get("data", {}).get("data_dir")

        config, structure_type = apply_config_data_section(
            config=config,
            discovery=discovery,
            base_path=base_path,
            spec_folder=spec_folder,
            audio_folder=audio_folder,
            predictions_file=predictions_file,
            predictions_entries=predictions_entries,
            predictions_values=predictions_values,
            predictions_ids=predictions_ids,
        )

        date_options, date_value, device_options, device_value = compute_global_filter_options(
            structure_type=structure_type,
            discovery=discovery,
            base_path=base_path,
            current_date_value=current_date_value,
            current_device_value=current_device_value,
        )

        display_path = base_path if base_path else "Not selected"
        spec_display, audio_display, output_display = compute_label_tab_displays(
            current_mode=current_mode,
            structure_type=structure_type,
            discovery=discovery,
            base_path=base_path,
            spec_folder=spec_folder,
            audio_folder=audio_folder,
        )

        trigger_value = build_load_trigger_value(
            current_mode=current_mode,
            config=config,
            date_value=date_value,
            device_value=device_value,
        )
        tab_iso_debug(
            "data_config_load_trigger",
            current_mode=current_mode,
            base_path=base_path,
            structure_type=structure_type,
            spec_folder=spec_folder,
            audio_folder=audio_folder,
            predictions_file=predictions_file,
            date_value=date_value,
            device_value=device_value,
            config_data_dir=(config.get("data", {}) or {}).get("data_dir") if isinstance(config, dict) else None,
            config_predictions_file=(config.get("data", {}) or {}).get("predictions_file") if isinstance(config, dict) else None,
            trigger_timestamp=trigger_value.get("timestamp"),
        )

        return (
            True,
            config,
            display_path,
            date_options,
            date_value,
            device_options,
            device_value,
            spec_display,
            audio_display,
            output_display,
            trigger_value,
        )

    app.clientside_callback(
        """
        function(loadClicks, mode) {
            var dc = (window.dash_clientside || {});
            if (!loadClicks) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            var title = "Loading dataset...";
            var subtitle = "Applying configuration and preparing your workspace.";
            if (mode === "verify") {
                subtitle = "Applying configuration and loading predictions.";
            } else if (mode === "label") {
                subtitle = "Applying configuration and loading items.";
            } else if (mode === "explore") {
                subtitle = "Applying configuration and loading items for exploration.";
            }
            return [{display: "flex"}, title, subtitle];
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Output("data-load-title", "children", allow_duplicate=True),
        Output("data-load-subtitle", "children", allow_duplicate=True),
        Input("data-config-load", "n_clicks"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        Input("data-load-trigger-store", "data"),
        prevent_initial_call=True,
    )
    def hide_loading_overlay_on_data_load(label_ready, verify_ready, explore_ready, load_trigger):
        trigger_ts = load_trigger.get("timestamp") if isinstance(load_trigger, dict) else None

        def _is_ready_match(ready_payload):
            if not isinstance(ready_payload, dict):
                return False
            if trigger_ts is None:
                return True
            payload_ts = ready_payload.get("load_timestamp")
            if payload_ts is None:
                payload_ts = ready_payload.get("timestamp")
            return payload_ts == trigger_ts

        if _is_ready_match(label_ready) or _is_ready_match(verify_ready) or _is_ready_match(explore_ready):
            return {"display": "none"}
        raise PreventUpdate

    @app.callback(
        Output("data-config-modal", "is_open", allow_duplicate=True),
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        State("data-load-trigger-store", "data"),
        State("data-config-modal", "is_open"),
        prevent_initial_call=True,
    )
    def close_data_config_on_data_load(label_ready, verify_ready, explore_ready, load_trigger, is_open):
        if not is_open or not isinstance(load_trigger, dict):
            raise PreventUpdate

        trigger_ts = load_trigger.get("timestamp")
        if trigger_ts is None:
            if label_ready or verify_ready or explore_ready:
                return False
            raise PreventUpdate

        if (label_ready or {}).get("load_timestamp") == trigger_ts or (label_ready or {}).get("timestamp") == trigger_ts:
            return False
        if (verify_ready or {}).get("load_timestamp") == trigger_ts or (verify_ready or {}).get("timestamp") == trigger_ts:
            return False
        if (explore_ready or {}).get("load_timestamp") == trigger_ts or (explore_ready or {}).get("timestamp") == trigger_ts:
            return False

        raise PreventUpdate

    @app.callback(
        Output("verify-predictions-warning", "is_open"),
        Input("mode-tabs", "data"),
        Input("verify-data-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def show_predictions_warning(mode, verify_data, config):
        loaded_data = verify_data
        if mode != "verify":
            return False

        if loaded_data and loaded_data.get("items"):
            for item in loaded_data["items"]:
                if item.get("predictions") and item["predictions"].get("model_outputs"):
                    return False
                if item.get("predictions") and item["predictions"].get("labels"):
                    return False

        predictions_file = config.get("data", {}).get("predictions_file")
        if predictions_file and os.path.exists(predictions_file):
            return False

        data_dir = config.get("data", {}).get("data_dir")
        if data_dir:
            discovery = detect_data_structure(data_dir)
            if discovery.get("predictions_file"):
                return False
            if discovery.get("root_predictions_file"):
                return False
            if int(discovery.get("subfolder_predictions_count") or 0) > 0:
                return False

        return True

    @app.callback(
        Output("mode-tabs", "data", allow_duplicate=True),
        Input("verify-continue-label-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def switch_to_label_mode(n_clicks):
        if n_clicks:
            return "label"
        raise PreventUpdate
