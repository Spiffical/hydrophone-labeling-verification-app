"""Tab-specific filter-state persistence callbacks."""

from dash import ClientsideFunction, Input, Output, State


def register_filter_state_callbacks(app, *, tab_iso_debug):
    """Update the active reviewer's in-memory tab snapshot without a server race."""
    app.clientside_callback(
        ClientsideFunction(namespace="reviewPreferences", function_name="persistTabs"),
        Output("tab-filter-state-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("mode-tabs", "data"),
        State("tab-filter-state-store", "data"),
        State("user-profile-store", "data"),
        State("review-preferences-owner-store", "data"),
        State("global-date-selector", "options"),
        State("global-device-selector", "options"),
        prevent_initial_call=True,
    )
