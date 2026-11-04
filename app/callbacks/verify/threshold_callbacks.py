"""Confidence range callbacks for verify mode."""

from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from app.services.review_view import thresholds_for_range


def register_verify_threshold_callbacks(app):
    """Register the confidence range slider's store update."""

    @app.callback(
        Output("verify-thresholds-store", "data"),
        Output("verify-current-page", "data", allow_duplicate=True),
        Input("verify-threshold-slider", "value"),
        State("verify-thresholds-store", "data"),
        prevent_initial_call=True,
    )
    def update_thresholds_store(slider_value, thresholds):
        if not isinstance(slider_value, (list, tuple)) or len(slider_value) != 2:
            raise PreventUpdate
        lower, upper = sorted(float(value) / 100 for value in slider_value)
        updated = thresholds_for_range(thresholds, lower, upper)
        # Restoring a reviewer's settings also moves the slider.
        if updated == thresholds:
            raise PreventUpdate
        return updated, 0
