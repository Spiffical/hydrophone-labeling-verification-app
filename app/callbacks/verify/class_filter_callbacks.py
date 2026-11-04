"""Class selection: the category pills and the class menus beneath them."""

from dash import ALL, Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from app.services.annotations import split_hierarchy_label
from app.services.review_view import active_class_filter
from app.services.verify_filter_tree import class_selection_state, toggle_class_selection


def selection_summary(selected):
    """Say briefly what the selection covers."""
    if not selected:
        return "All classes"
    if len(selected) == 1:
        return split_hierarchy_label(selected[0])[-1]
    return f"{len(selected)} selected"


def register_verify_filter_callbacks(app):
    """Register category pill and class menu callbacks."""

    @app.callback(
        Output("verify-class-filter", "data", allow_duplicate=True),
        Output("verify-current-page", "data", allow_duplicate=True),
        Input({"type": "verify-category-toggle", "category": ALL}, "n_clicks"),
        Input({"type": "verify-filter-node", "path": ALL}, "n_clicks"),
        Input("verify-selection-clear", "n_clicks"),
        State("verify-class-filter", "data"),
        prevent_initial_call=True,
    )
    def update_class_selection(category_clicks, node_clicks, clear_clicks, selected):
        _ = category_clicks, node_clicks, clear_clicks
        if not ctx.triggered or not ctx.triggered[0].get("value"):
            raise PreventUpdate
        triggered = ctx.triggered_id
        if triggered == "verify-selection-clear":
            return None, 0
        path = (triggered.get("path") or triggered.get("category")) if isinstance(triggered, dict) else None
        if not path:
            raise PreventUpdate
        return toggle_class_selection(selected, path), 0

    @app.callback(
        Output({"type": "verify-category-toggle", "category": ALL}, "className"),
        Output({"type": "verify-filter-node", "path": ALL}, "className"),
        Output("verify-selection-summary", "children"),
        Output("verify-selection-clear", "style"),
        Input("verify-class-filter", "data"),
        State({"type": "verify-category-toggle", "category": ALL}, "id"),
        State({"type": "verify-filter-node", "path": ALL}, "id"),
    )
    def render_class_selection(class_filter, category_ids, node_ids):
        selected = active_class_filter(class_filter)
        return (
            [
                "review-category-toggle review-category-toggle--"
                + class_selection_state(selected, entry["category"])
                for entry in category_ids
            ],
            [
                "review-tree-node review-tree-node--" + class_selection_state(selected, entry["path"])
                for entry in node_ids
            ],
            selection_summary(selected),
            {} if selected else {"display": "none"},
        )
