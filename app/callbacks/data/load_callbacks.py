"""Dataset loading callback orchestration."""

import time

from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from app.callbacks.data.load_explore_callbacks import register_explore_data_loading_callback
from app.callbacks.data.load_label_callbacks import register_label_data_loading_callback
from app.callbacks.data.load_verify_callbacks import register_verify_data_loading_callback


def register_global_load_trigger_callback(app, *, tab_iso_debug, config_default_data_dir):
    """Register top-level Load button callback that emits a load trigger payload."""

    @app.callback(
        Output("data-load-trigger-store", "data", allow_duplicate=True),
        Input("global-load-btn", "n_clicks"),
        State("mode-tabs", "data"),
        State("config-store", "data"),
        State("global-date-selector", "value"),
        State("global-device-selector", "value"),
        prevent_initial_call=True,
    )
    def trigger_global_load(n_clicks, mode, cfg, date_value, device_value):
        if not n_clicks:
            raise PreventUpdate
        active_mode = mode or "label"
        payload = {
            "timestamp": time.time(),
            "mode": active_mode,
            "source": "global-load",
            "config": cfg or {},
            "date_value": date_value,
            "device_value": device_value,
        }
        tab_iso_debug(
            "global_load_trigger",
            n_clicks=n_clicks,
            active_mode=active_mode,
            date_value=date_value,
            device_value=device_value,
            cfg_data_dir=config_default_data_dir(cfg or {}),
        )
        return payload


def register_data_loading_callbacks(
    app,
    *,
    load_dataset,
    _resolve_tab_data_dir,
    _config_default_data_dir,
    _tab_iso_debug,
    _tab_data_snapshot,
):
    """Register label/verify/explore data loading callbacks."""

    register_label_data_loading_callback(
        app,
        load_dataset=load_dataset,
        resolve_tab_data_dir=_resolve_tab_data_dir,
        config_default_data_dir=_config_default_data_dir,
        tab_iso_debug=_tab_iso_debug,
        tab_data_snapshot=_tab_data_snapshot,
    )
    register_verify_data_loading_callback(
        app,
        load_dataset=load_dataset,
        resolve_tab_data_dir=_resolve_tab_data_dir,
        config_default_data_dir=_config_default_data_dir,
        tab_iso_debug=_tab_iso_debug,
        tab_data_snapshot=_tab_data_snapshot,
    )
    register_explore_data_loading_callback(
        app,
        load_dataset=load_dataset,
        resolve_tab_data_dir=_resolve_tab_data_dir,
        config_default_data_dir=_config_default_data_dir,
        tab_iso_debug=_tab_iso_debug,
        tab_data_snapshot=_tab_data_snapshot,
    )

