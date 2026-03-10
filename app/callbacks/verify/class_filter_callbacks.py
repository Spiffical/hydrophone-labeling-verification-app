"""Verify mode class filter and threshold callbacks."""

from dash import ALL, Input, Output, State, ctx, html
from dash.exceptions import PreventUpdate


def register_verify_filter_callbacks(
    app,
    *,
    extract_verify_leaf_classes,
    build_verify_filter_paths,
    build_verify_leaf_paths,
    expand_verify_filter_selection,
    ordered_unique_labels,
    split_hierarchy_label,
    build_verify_filter_tree_rows,
    toggle_verify_filter_selection,
):
    """Register verify class-filter tree callbacks."""

    @app.callback(
        Output("verify-class-filter-options", "data"),
        Output("verify-class-filter", "data"),
        Output("verify-class-filter-expanded", "data"),
        Input("verify-data-store", "data"),
        State("verify-class-filter", "data"),
        State("verify-class-filter-expanded", "data"),
        prevent_initial_call=False,
    )
    def sync_verify_class_filter_state(data, current_value, expanded_value):
        items = (data or {}).get("items", [])
        classes = extract_verify_leaf_classes(items)
        option_values = build_verify_filter_paths(classes)
        selected_values = expand_verify_filter_selection(option_values, current_value)

        normalized_expanded = ordered_unique_labels(expanded_value or [])
        if not option_values:
            return [], [], []

        valid_paths = set()
        for path in option_values:
            parts = split_hierarchy_label(path)
            for depth in range(1, len(parts) + 1):
                valid_paths.add(" > ".join(parts[:depth]))
        expanded_paths = [path for path in normalized_expanded if path in valid_paths]

        if not expanded_paths:
            roots = []
            seen = set()
            for path in option_values:
                parts = split_hierarchy_label(path)
                if not parts:
                    continue
                root = parts[0]
                if root in seen:
                    continue
                roots.append(root)
                seen.add(root)
            expanded_paths = roots

        return option_values, selected_values, expanded_paths

    @app.callback(
        Output("verify-class-filter-tree", "children"),
        Output("verify-class-filter-toggle", "children"),
        Output("verify-class-filter-select-all", "value"),
        Input("verify-class-filter-options", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-class-filter-expanded", "data"),
        prevent_initial_call=False,
    )
    def render_verify_class_filter_tree(option_values, selected_values, expanded_values):
        option_values = ordered_unique_labels(option_values or [])
        if not option_values:
            return (
                html.Div("No classes available", className="text-muted small"),
                [
                    html.Span("No classes available", className="verify-class-filter-toggle-label"),
                    html.Span("▾", className="verify-class-filter-toggle-caret"),
                ],
                False,
            )

        leaf_values = build_verify_leaf_paths(option_values)
        normalized_selected = expand_verify_filter_selection(option_values, selected_values)

        tree_rows = build_verify_filter_tree_rows(option_values, normalized_selected, expanded_values or [])
        if len(normalized_selected) == len(leaf_values):
            toggle_label = "All classes selected"
            select_all_value = True
        elif not normalized_selected:
            toggle_label = "No classes selected"
            select_all_value = False
        elif len(normalized_selected) == 1:
            toggle_label = normalized_selected[0]
            select_all_value = False
        else:
            toggle_label = f"{len(normalized_selected)} classes selected"
            select_all_value = False

        return (
            html.Div(tree_rows),
            [
                html.Span(toggle_label, className="verify-class-filter-toggle-label"),
                html.Span("▾", className="verify-class-filter-toggle-caret"),
            ],
            select_all_value,
        )

    @app.callback(
        Output("verify-class-filter-collapse", "is_open"),
        Output("verify-class-filter-toggle", "className"),
        Output("verify-class-filter-dismiss-overlay", "style"),
        Input("verify-class-filter-toggle", "n_clicks"),
        Input("verify-class-filter-done", "n_clicks"),
        Input("verify-class-filter-dismiss-overlay", "n_clicks"),
        State("verify-class-filter-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_verify_class_filter_dropdown(toggle_clicks, done_clicks, dismiss_clicks, is_open):
        triggered = ctx.triggered_id
        if triggered not in {
            "verify-class-filter-toggle",
            "verify-class-filter-done",
            "verify-class-filter-dismiss-overlay",
        }:
            raise PreventUpdate

        is_currently_open = bool(is_open)
        if triggered == "verify-class-filter-toggle":
            if not toggle_clicks:
                raise PreventUpdate
            next_open = not is_currently_open
        elif triggered == "verify-class-filter-done":
            if not done_clicks or not is_currently_open:
                raise PreventUpdate
            next_open = False
        else:
            if not dismiss_clicks or not is_currently_open:
                raise PreventUpdate
            next_open = False

        base_class = "w-100 text-start verify-class-filter-toggle"
        overlay_style = {"display": "block"} if next_open else {"display": "none"}
        return (
            next_open,
            (f"{base_class} verify-class-filter-toggle--open" if next_open else base_class),
            overlay_style,
        )

    @app.callback(
        Output("verify-class-filter-expanded", "data", allow_duplicate=True),
        Input({"type": "verify-filter-expand", "path": ALL}, "n_clicks"),
        State("verify-class-filter-expanded", "data"),
        prevent_initial_call=True,
    )
    def toggle_verify_filter_expand(expand_clicks, expanded_paths):
        if not ctx.triggered:
            raise PreventUpdate
        if (ctx.triggered[0].get("value") or 0) <= 0:
            raise PreventUpdate

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        path = (triggered.get("path") or "").strip()
        if not path:
            raise PreventUpdate

        next_paths = set(ordered_unique_labels(expanded_paths or []))
        if path in next_paths:
            next_paths.remove(path)
        else:
            next_paths.add(path)
        return sorted(next_paths, key=lambda text: text.lower())

    @app.callback(
        Output("verify-class-filter", "data", allow_duplicate=True),
        Input({"type": "verify-filter-checkbox", "path": ALL}, "value"),
        Input("verify-class-filter-select-all", "value"),
        State({"type": "verify-filter-checkbox", "path": ALL}, "id"),
        State("verify-class-filter-options", "data"),
        State("verify-class-filter", "data"),
        prevent_initial_call=True,
    )
    def update_verify_filter_selection(
        checkbox_values,
        select_all_checked,
        checkbox_ids,
        option_values,
        current_values,
    ):
        option_values = ordered_unique_labels(option_values or [])
        leaf_values = build_verify_leaf_paths(option_values)
        if not leaf_values:
            raise PreventUpdate

        selected_values = expand_verify_filter_selection(option_values, current_values)

        triggered = ctx.triggered_id

        if triggered == "verify-class-filter-select-all":
            is_all_selected = len(selected_values) == len(leaf_values)
            if bool(select_all_checked):
                if is_all_selected:
                    raise PreventUpdate
                return leaf_values
            if selected_values:
                return []
            raise PreventUpdate

        if not (isinstance(triggered, dict) and triggered.get("type") == "verify-filter-checkbox"):
            raise PreventUpdate

        path = (triggered.get("path") or "").strip()
        if not path:
            raise PreventUpdate

        is_checked = None
        for checkbox_value, checkbox_id in zip(checkbox_values or [], checkbox_ids or []):
            if not isinstance(checkbox_id, dict):
                continue
            if (checkbox_id.get("path") or "").strip() != path:
                continue
            is_checked = bool(checkbox_value)
            break

        if is_checked is None:
            raise PreventUpdate

        next_selected = toggle_verify_filter_selection(option_values, selected_values, path, is_checked)
        if next_selected == selected_values:
            raise PreventUpdate
        return next_selected
