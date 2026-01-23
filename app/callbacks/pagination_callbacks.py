"""Pagination callbacks for label mode."""
from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate


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
