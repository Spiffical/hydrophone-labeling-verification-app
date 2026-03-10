"""Verify-mode data loading callback registration."""

import time

from dash import Input, Output, State, ctx
from dash.exceptions import PreventUpdate


def register_verify_data_loading_callback(
    app,
    *,
    load_dataset,
    resolve_tab_data_dir,
    config_default_data_dir,
    tab_iso_debug,
    tab_data_snapshot,
):
    @app.callback(
        Output("verify-data-store", "data"),
        Input("verify-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("verify-data-store", "data"),
    )
    def load_verify_data(reload_clicks, config_load_trigger, date_val, device_val, cfg, mode, current_verify_data):
        """Load data specifically for Verify mode."""
        _ = reload_clicks
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        trigger_mode = None
        trigger_source = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")
            trigger_source = config_load_trigger.get("source")

        trigger_cfg_snapshot = (
            config_load_trigger.get("config")
            if isinstance(config_load_trigger, dict) and isinstance(config_load_trigger.get("config"), dict)
            else None
        )
        tab_iso_debug(
            "load_verify_start",
            mode=mode,
            trigger_mode=trigger_mode,
            trigger_source=trigger_source,
            triggered_props=sorted(triggered_props),
            date_val=date_val,
            device_val=device_val,
            cfg_data_dir=config_default_data_dir(cfg or {}),
            trigger_cfg_data_dir=config_default_data_dir(trigger_cfg_snapshot),
            current_verify_snapshot=tab_data_snapshot(current_verify_data),
        )

        if mode != "verify":
            raise PreventUpdate

        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = bool(current_verify_data and current_verify_data.get("source_data_dir"))

        config_panel_trigger = "data-load-trigger-store" in triggered_props and trigger_source == "data-config-load"
        should_load = (
            "verify-reload" in triggered_props
            or trigger_mode == "verify"
            or config_panel_trigger
            or (filter_triggered and has_source)
        )
        tab_iso_debug(
            "load_verify_decision",
            filter_triggered=bool(filter_triggered),
            has_source=bool(has_source),
            config_panel_trigger=config_panel_trigger,
            should_load=should_load,
        )

        if should_load:
            try:
                trigger_cfg = None
                requested_date = date_val
                requested_device = device_val
                if isinstance(config_load_trigger, dict) and "data-load-trigger-store" in triggered_props:
                    trigger_cfg = config_load_trigger.get("config")
                    requested_date = config_load_trigger.get("date_value", requested_date)
                    requested_device = config_load_trigger.get("device_value", requested_device)

                effective_cfg = trigger_cfg.copy() if trigger_cfg else (cfg.copy() if cfg else {})
                data_cfg = dict(effective_cfg.get("data", {}))
                active_data_dir = resolve_tab_data_dir(
                    cfg,
                    current_tab_data=current_verify_data,
                    trigger_cfg=trigger_cfg,
                    trigger_source=trigger_source,
                )
                tab_iso_debug(
                    "load_verify_resolved_root",
                    active_data_dir=active_data_dir,
                    cfg_data_dir=config_default_data_dir(cfg or {}),
                    trigger_cfg_data_dir=config_default_data_dir(trigger_cfg or {}),
                    current_source_data_dir=(current_verify_data or {}).get("source_data_dir")
                    if isinstance(current_verify_data, dict)
                    else None,
                )
                if active_data_dir:
                    data_cfg["data_dir"] = active_data_dir

                effective_cfg["data"] = data_cfg

                data = load_dataset(effective_cfg, "verify", date_str=requested_date, hydrophone=requested_device)

                if "data-load-trigger-store" in triggered_props and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                elif filter_triggered:
                    data["load_timestamp"] = time.time()
                else:
                    data["load_timestamp"] = time.time()

                data["source_data_dir"] = active_data_dir
                from app.main import set_audio_roots

                set_audio_roots(data.get("audio_roots", []))
                tab_iso_debug(
                    "load_verify_success",
                    requested_date=requested_date,
                    requested_device=requested_device,
                    effective_predictions_file=(effective_cfg.get("data") or {}).get("predictions_file"),
                    loaded_verify_snapshot=tab_data_snapshot(data),
                )
                return data
            except Exception as e:
                tab_iso_debug("load_verify_error", error=str(e))
                print(f"Error loading verify dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate
