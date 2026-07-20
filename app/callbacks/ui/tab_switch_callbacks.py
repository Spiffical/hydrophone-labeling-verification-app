"""Tab mode switching callbacks."""

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.services.verification import has_pending_label_edits
from app.services.verify_modal_cache import has_pending_verify_modal_changes


def _has_pending_label_changes(label_data):
    if not isinstance(label_data, dict):
        return False
    return any(
        isinstance(item, dict) and has_pending_label_edits(item.get("annotations"))
        for item in (label_data.get("items") or [])
    )


def register_mode_tab_callbacks(app):
    """Register callbacks that synchronize tab buttons and active mode store."""

    @app.callback(
        Output("mode-tabs", "data"),
        Output("mode-switch-unsaved-modal", "is_open"),
        Output("mode-switch-unsaved-message", "children"),
        Input("tab-btn-label", "n_clicks"),
        Input("tab-btn-verify", "n_clicks"),
        Input("tab-btn-explore", "n_clicks"),
        Input("mode-switch-unsaved-stay", "n_clicks"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-cache-key-store", "data"),
        prevent_initial_call=True,
    )
    def switch_mode(
        label_clicks,
        verify_clicks,
        explore_clicks,
        stay_clicks,
        current_mode,
        label_data,
        verify_cache_key,
    ):
        _ = label_clicks, verify_clicks, explore_clicks, stay_clicks
        triggered = ctx.triggered_id
        if triggered == "mode-switch-unsaved-stay":
            return no_update, False, no_update

        requested_mode = {
            "tab-btn-label": "label",
            "tab-btn-verify": "verify",
            "tab-btn-explore": "explore",
        }.get(triggered)
        if not requested_mode:
            raise PreventUpdate
        if requested_mode == current_mode:
            return no_update, False, no_update

        has_pending = False
        pending_message = ""
        if current_mode == "verify" and has_pending_verify_modal_changes(verify_cache_key):
            has_pending = True
            pending_message = (
                "You have unsaved verification changes. Stay here and save the pending cards "
                "before switching modes."
            )
        elif current_mode == "label" and _has_pending_label_changes(label_data):
            has_pending = True
            pending_message = (
                "You have unsaved label changes. Stay here and confirm the pending cards "
                "before switching modes."
            )

        if has_pending:
            return no_update, True, pending_message
        return requested_mode, False, no_update

    app.clientside_callback(
        """
        function(mode) {
            var labelStyle = {display: mode === 'label' ? 'block' : 'none'};
            var verifyStyle = {display: mode === 'verify' ? 'block' : 'none'};
            var exploreStyle = {display: mode === 'explore' ? 'block' : 'none'};
            var labelClass = 'mode-tab' + (mode === 'label' ? ' mode-tab--active' : '');
            var verifyClass = 'mode-tab' + (mode === 'verify' ? ' mode-tab--active' : '');
            var exploreClass = 'mode-tab' + (mode === 'explore' ? ' mode-tab--active' : '');
            return [labelStyle, verifyStyle, exploreStyle, labelClass, verifyClass, exploreClass];
        }
        """,
        [Output("label-tab-content", "style"),
         Output("verify-tab-content", "style"),
         Output("explore-tab-content", "style"),
         Output("tab-btn-label", "className"),
         Output("tab-btn-verify", "className"),
         Output("tab-btn-explore", "className")],
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )
