"""Pagination callbacks for verify mode."""

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate


def register_verify_pagination_callbacks(
    app,
    *,
    any_pending_verify_changes,
    compute_target_page,
    save_all_pending_verify_changes,
):
    """Register verify pagination controls + unsaved-changes guard."""

    @app.callback(
        Output("verify-current-page", "data"),
        Output("verify-unsaved-page-modal", "is_open"),
        Output("verify-pending-page-store", "data"),
        Output("verify-data-store", "data", allow_duplicate=True),
        Input("verify-prev-page", "n_clicks"),
        Input("verify-next-page", "n_clicks"),
        Input("verify-goto-page", "n_clicks"),
        Input("verify-unsaved-page-stay", "n_clicks"),
        Input("verify-unsaved-page-save", "n_clicks"),
        State("verify-current-page", "data"),
        State("verify-page-input", "value"),
        State("verify-page-input", "max"),
        State("verify-pending-page-store", "data"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def handle_verify_pagination(
        prev_clicks,
        next_clicks,
        goto_clicks,
        stay_clicks,
        save_all_clicks,
        current_page,
        goto_page,
        max_pages,
        pending_page,
        verify_data,
        thresholds,
        profile,
    ):
        _ = prev_clicks, next_clicks, goto_clicks
        triggered_id = ctx.triggered_id
        current_page = current_page or 0
        max_pages = max_pages or 1

        if triggered_id in {"verify-prev-page", "verify-next-page", "verify-goto-page"}:
            target_page = compute_target_page(triggered_id, current_page, goto_page, max_pages)
            if target_page == current_page:
                raise PreventUpdate

            if any_pending_verify_changes(verify_data):
                return no_update, True, target_page, no_update

            return target_page, False, None, no_update

        if triggered_id == "verify-unsaved-page-stay":
            if not stay_clicks:
                raise PreventUpdate
            return no_update, False, None, no_update

        if triggered_id == "verify-unsaved-page-save":
            if not save_all_clicks:
                raise PreventUpdate
            target_page = pending_page if isinstance(pending_page, int) else current_page
            target_page = max(0, min(max_pages - 1, target_page))
            updated_data, saved_count = save_all_pending_verify_changes(verify_data, thresholds, profile)
            verify_data_update = updated_data if saved_count > 0 else no_update
            return target_page, False, None, verify_data_update

        raise PreventUpdate

    @app.callback(
        Output("verify-page-input", "value"),
        Input("verify-current-page", "data"),
    )
    def sync_verify_page_input(current_page):
        return (current_page or 0) + 1
