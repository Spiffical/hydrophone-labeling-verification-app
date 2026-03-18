"""Modal audio display and persistence callbacks."""

from dash import ALL, Input, Output, State
from dash.exceptions import PreventUpdate


def register_modal_audio_callbacks(app):
    """Register modal audio UI callbacks."""

    app.clientside_callback(
        """
        function(trigger) {
            if (window.dash_clientside && window.dash_clientside.namespace) {
                setTimeout(function() {
                    window.dash_clientside.namespace.initializeAudioPlayers();
                }, 150);
            }
            return '';
        }
        """,
        Output("dummy-output-audio", "children"),
        [Input("label-grid", "children"),
         Input("verify-grid", "children"),
         Input("modal-audio-player", "children")],
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(prevClicks, nextClicks, confirmClicks, editClicks, isOpen, modalItem) {
            if (!isOpen) {
                return false;
            }
            if (!modalItem || !modalItem.item_id) {
                return false;
            }
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || {};
            var triggered = Array.isArray(ctx.triggered) && ctx.triggered.length ? ctx.triggered[0] : null;
            var propId = triggered && triggered.prop_id ? triggered.prop_id : '';
            if (!propId) {
                return false;
            }
            if (propId === 'modal-nav-prev.n_clicks') {
                return typeof prevClicks === 'number' && prevClicks > 0;
            }
            if (propId === 'modal-nav-next.n_clicks') {
                return typeof nextClicks === 'number' && nextClicks > 0;
            }
            if (propId.indexOf('modal-action-confirm') !== -1) {
                return Array.isArray(confirmClicks) && confirmClicks.some(function(value) {
                    return typeof value === 'number' && value > 0;
                });
            }
            if (propId.indexOf('modal-action-edit') !== -1) {
                return Array.isArray(editClicks) && editClicks.some(function(value) {
                    return typeof value === 'number' && value > 0;
                });
            }
            return false;
        }
        """,
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input("modal-nav-prev", "n_clicks"),
        Input("modal-nav-next", "n_clicks"),
        Input({"type": "modal-action-confirm", "scope": ALL}, "n_clicks"),
        Input({"type": "modal-action-edit", "scope": ALL}, "n_clicks"),
        State("image-modal", "is_open"),
        State("modal-item-store", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(isBusy) {
            return isBusy ? {display: 'flex'} : {display: 'none'};
        }
        """,
        Output("modal-busy-overlay", "style"),
        Input("modal-busy-store", "data"),
    )

    @app.callback(
        Output("modal-player-pitch-display", "children"),
        Input("modal-player-pitch-slider", "value"),
        prevent_initial_call=True,
    )
    def update_modal_pitch_display(value):
        if value is None:
            raise PreventUpdate
        try:
            return f"{float(value):.2f}x"
        except (TypeError, ValueError):
            return "1.00x"

    @app.callback(
        Output("modal-player-eq-display", "children"),
        Input("modal-player-eq-20-slider", "value"),
        Input("modal-player-eq-40-slider", "value"),
        Input("modal-player-eq-80-slider", "value"),
        Input("modal-player-eq-160-slider", "value"),
        Input("modal-player-eq-315-slider", "value"),
        Input("modal-player-eq-630-slider", "value"),
        Input("modal-player-eq-1250-slider", "value"),
        Input("modal-player-eq-2500-slider", "value"),
        Input("modal-player-eq-5000-slider", "value"),
        Input("modal-player-eq-10000-slider", "value"),
        Input("modal-player-eq-16000-slider", "value"),
        prevent_initial_call=True,
    )
    def update_modal_eq_display(
        eq_20,
        eq_40,
        eq_80,
        eq_160,
        eq_315,
        eq_630,
        eq_1250,
        eq_2500,
        eq_5000,
        eq_10000,
        eq_16000,
    ):
        return "Full-range EQ: 20 Hz to 16 kHz"

    @app.callback(
        Output("modal-player-gain-display", "children"),
        Input("modal-player-gain-slider", "value"),
        prevent_initial_call=True,
    )
    def update_modal_gain_display(value):
        if value is None:
            raise PreventUpdate
        try:
            return f"{float(value):.1f}x"
        except (TypeError, ValueError):
            return "1.0x"

    @app.callback(
        Output("modal-audio-settings-store", "data"),
        Input("modal-player-pitch-slider", "value"),
        Input("modal-player-eq-20-slider", "value"),
        Input("modal-player-eq-40-slider", "value"),
        Input("modal-player-eq-80-slider", "value"),
        Input("modal-player-eq-160-slider", "value"),
        Input("modal-player-eq-315-slider", "value"),
        Input("modal-player-eq-630-slider", "value"),
        Input("modal-player-eq-1250-slider", "value"),
        Input("modal-player-eq-2500-slider", "value"),
        Input("modal-player-eq-5000-slider", "value"),
        Input("modal-player-eq-10000-slider", "value"),
        Input("modal-player-eq-16000-slider", "value"),
        Input("modal-player-gain-slider", "value"),
        State("modal-audio-settings-store", "data"),
        prevent_initial_call=True,
    )
    def persist_modal_audio_settings(
        pitch,
        eq_20,
        eq_40,
        eq_80,
        eq_160,
        eq_315,
        eq_630,
        eq_1250,
        eq_2500,
        eq_5000,
        eq_10000,
        eq_16000,
        gain,
        current_settings,
    ):
        current_settings = current_settings or {
            "pitch": 1.0,
            "eq_20": 0.0,
            "eq_40": 0.0,
            "eq_80": 0.0,
            "eq_160": 0.0,
            "eq_315": 0.0,
            "eq_630": 0.0,
            "eq_1250": 0.0,
            "eq_2500": 0.0,
            "eq_5000": 0.0,
            "eq_10000": 0.0,
            "eq_16000": 0.0,
            "gain": 1.0,
        }
        updated = dict(current_settings)
        changed = False

        if pitch is not None:
            try:
                pitch_value = float(pitch)
                if updated.get("pitch") != pitch_value:
                    updated["pitch"] = pitch_value
                    changed = True
            except (TypeError, ValueError):
                pass

        eq_inputs = {
            "eq_20": eq_20,
            "eq_40": eq_40,
            "eq_80": eq_80,
            "eq_160": eq_160,
            "eq_315": eq_315,
            "eq_630": eq_630,
            "eq_1250": eq_1250,
            "eq_2500": eq_2500,
            "eq_5000": eq_5000,
            "eq_10000": eq_10000,
            "eq_16000": eq_16000,
        }
        for eq_key, eq_input in eq_inputs.items():
            if eq_input is None:
                continue
            try:
                eq_value = max(-24.0, min(24.0, float(eq_input)))
                if updated.get(eq_key) != eq_value:
                    updated[eq_key] = eq_value
                    changed = True
            except (TypeError, ValueError):
                continue

        if gain is not None:
            try:
                gain_value = float(gain)
                if updated.get("gain") != gain_value:
                    updated["gain"] = gain_value
                    changed = True
            except (TypeError, ValueError):
                pass

        if not changed:
            raise PreventUpdate
        return updated

    app.clientside_callback(
        """
        function(is_open) {
            if (is_open === false || is_open === null) {
                document.querySelectorAll('audio[id$="-audio"]').forEach(function(audio) {
                    audio.pause();
                });
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("dummy-output", "data", allow_duplicate=True),
        Input("image-modal", "is_open"),
        prevent_initial_call=True,
    )
