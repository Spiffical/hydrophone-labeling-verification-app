"""Callbacks for switching configurable spectrogram rendering presets."""

from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate

from app.services.spectrogram_presets import (
    apply_spectrogram_preset,
    find_matching_spectrogram_preset,
)


def register_spectrogram_preset_callbacks(app):
    @app.callback(
        Output("config-store", "data", allow_duplicate=True),
        Input("verify-spectrogram-preset", "value"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def apply_verify_spectrogram_preset(preset_id, cfg):
        if not preset_id:
            raise PreventUpdate
        updated_cfg = apply_spectrogram_preset(cfg, preset_id)
        if updated_cfg is None or updated_cfg == (cfg or {}):
            raise PreventUpdate
        return updated_cfg

    @app.callback(
        Output("verify-spectrogram-preset", "value"),
        Input("config-store", "data"),
        State("verify-spectrogram-preset", "value"),
        prevent_initial_call=True,
    )
    def sync_verify_spectrogram_preset(cfg, current_value):
        matching = find_matching_spectrogram_preset(cfg)
        if matching == current_value:
            return no_update
        return matching
