"""Threshold callbacks for verify mode."""

from dash import Input, Output, State


def register_verify_threshold_callbacks(app):
    """Register threshold store <-> slider synchronization callbacks."""

    @app.callback(
        Output("verify-thresholds-store", "data"),
        Input("verify-threshold-slider", "value"),
        State("verify-class-filter", "data"),
        State("verify-thresholds-store", "data"),
        prevent_initial_call=True,
    )
    def update_thresholds_store(slider_value, class_filter, thresholds):
        thresholds = thresholds or {"__global__": 0.5}
        class_filter = class_filter or "all"
        if slider_value is None:
            return thresholds

        value = float(slider_value)
        thresholds["__global__"] = value
        return thresholds

    @app.callback(
        Output("verify-threshold-slider", "value"),
        Input("verify-class-filter", "data"),
        State("verify-thresholds-store", "data"),
        prevent_initial_call=True,
    )
    def sync_threshold_slider(class_filter, thresholds):
        thresholds = thresholds or {"__global__": 0.5}
        class_filter = class_filter or "all"
        return float(thresholds.get("__global__", 0.5))
