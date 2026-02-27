"""Pagination callbacks for label/explore modes."""

from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from app.callbacks.verify.pagination_callbacks import register_verify_pagination_callbacks
from app.services.verify_pagination import (
    any_pending_verify_changes,
    compute_target_page,
    save_all_pending_verify_changes,
)


def register_pagination_callbacks(app):
    """Register callbacks for pagination controls."""
    
    @app.callback(
        Output("label-current-page", "data"),
        Input("label-prev-page", "n_clicks"),
        Input("label-next-page", "n_clicks"),
        Input("label-goto-page", "n_clicks"),
        State("label-current-page", "data"),
        State("label-page-input", "value"),
        State("label-page-input", "max"),
        prevent_initial_call=True
    )
    def handle_pagination(prev_clicks, next_clicks, goto_clicks, current_page, goto_page, max_pages):
        """Handle pagination button clicks."""
        from dash import callback_context
        
        if not callback_context.triggered:
            raise PreventUpdate
        
        button_id = callback_context.triggered[0]["prop_id"].split(".")[0]
        current_page = current_page or 0
        max_pages = max_pages or 1
        
        if button_id == "label-prev-page":
            return max(0, current_page - 1)
        elif button_id == "label-next-page":
            return min(max_pages - 1, current_page + 1)
        elif button_id == "label-goto-page" and goto_page:
            # goto_page is 1-indexed, current_page is 0-indexed
            return max(0, min(int(goto_page) - 1, max_pages - 1))
        
        return current_page
    
    @app.callback(
        Output("label-page-input", "value"),
        Input("label-current-page", "data"),
    )
    def sync_page_input(current_page):
        """Sync page input with current page."""
        return (current_page or 0) + 1  # Convert 0-indexed to 1-indexed

    register_verify_pagination_callbacks(
        app,
        any_pending_verify_changes=any_pending_verify_changes,
        compute_target_page=compute_target_page,
        save_all_pending_verify_changes=save_all_pending_verify_changes,
    )

    @app.callback(
        Output("explore-current-page", "data"),
        Input("explore-prev-page", "n_clicks"),
        Input("explore-next-page", "n_clicks"),
        Input("explore-goto-page", "n_clicks"),
        State("explore-current-page", "data"),
        State("explore-page-input", "value"),
        State("explore-page-input", "max"),
        prevent_initial_call=True
    )
    def handle_explore_pagination(prev_clicks, next_clicks, goto_clicks, current_page, goto_page, max_pages):
        """Handle pagination button clicks in explore mode."""
        from dash import callback_context

        if not callback_context.triggered:
            raise PreventUpdate

        button_id = callback_context.triggered[0]["prop_id"].split(".")[0]
        current_page = current_page or 0
        max_pages = max_pages or 1

        if button_id == "explore-prev-page":
            return max(0, current_page - 1)
        elif button_id == "explore-next-page":
            return min(max_pages - 1, current_page + 1)
        elif button_id == "explore-goto-page" and goto_page:
            return max(0, min(int(goto_page) - 1, max_pages - 1))

        return current_page

    @app.callback(
        Output("explore-page-input", "value"),
        Input("explore-current-page", "data"),
    )
    def sync_explore_page_input(current_page):
        """Sync explore page input with current page."""
        return (current_page or 0) + 1
