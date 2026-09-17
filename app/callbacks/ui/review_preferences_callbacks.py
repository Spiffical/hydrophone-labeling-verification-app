"""Restore browser-local review settings before date/device discovery starts."""

from dash import ClientsideFunction, Input, Output, State


def register_review_preferences_callbacks(app):
    app.clientside_callback(
        ClientsideFunction(namespace="reviewPreferences", function_name="restore"),
        Output("tab-filter-state-store", "data", allow_duplicate=True),
        Output("verify-thresholds-store", "data", allow_duplicate=True),
        Output("verify-class-filter", "data", allow_duplicate=True),
        Output("verify-status-filter", "value"),
        Output("verify-threshold-slider", "value", allow_duplicate=True),
        Output("review-preferences-owner-store", "data"),
        Input("user-profile-store", "data"),
        State("review-preferences-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    app.clientside_callback(
        ClientsideFunction(namespace="reviewPreferences", function_name="remember"),
        Output("review-preferences-store", "data"),
        Input("tab-filter-state-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-status-filter", "value"),
        State("user-profile-store", "data"),
        State("review-preferences-owner-store", "data"),
        State("review-preferences-store", "data"),
        prevent_initial_call=True,
    )
