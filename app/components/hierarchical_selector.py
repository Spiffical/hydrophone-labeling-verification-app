import dash
from dash import html, dcc, Input, Output, State, callback, ALL, MATCH
import dash_bootstrap_components as dbc

from taxonomy.hierarchical_labels import (
    HIERARCHICAL_LABELS,
    get_label_display_name,
    path_to_string,
)


def create_hierarchical_selector(filename, selected_labels=None, read_only=False):
    if selected_labels is None:
        selected_labels = []

    selected_paths = []
    for label in selected_labels:
        if isinstance(label, str) and " > " in label:
            selected_paths.append(tuple(label.split(" > ")))
        elif isinstance(label, (list, tuple)):
            selected_paths.append(tuple(label))
        else:
            selected_paths.append((str(label),))

    return html.Div([
        dbc.InputGroup([
            dbc.Input(
                id={"type": "label-search", "filename": filename},
                type="text",
                placeholder="Search labels...",
                persistence=True,
                persistence_type="memory",
                disabled=read_only,
            ),
            dbc.Button(
                "Clear",
                id={"type": "clear-search", "filename": filename},
                color="outline-secondary",
                disabled=read_only,
            ),
        ], className="mb-2"),

        html.Div(
            id={"type": "selected-labels-display", "filename": filename},
            children=create_selected_labels_display(selected_paths, filename),
            className="mb-2",
        ),

        html.Div(
            id={"type": "hierarchical-tree", "filename": filename},
            children=create_tree_structure(HIERARCHICAL_LABELS, filename, selected_paths, read_only=read_only),
            style={
                "maxHeight": "320px",
                "overflowY": "auto",
                "border": "1px solid #e9ecef",
                "borderRadius": "8px",
                "padding": "8px",
                "background": "#fdfdfd",
            },
        ),

        dcc.Store(
            id={"type": "selected-labels-store", "filename": filename},
            data=[path_to_string(path) for path in selected_paths],
        ),
        dcc.Interval(
            id={"type": "search-debounce-timer", "filename": filename},
            interval=300,
            max_intervals=1,
            disabled=True,
        ),
    ], style={"padding": "8px"})


def create_selected_labels_display(selected_paths, filename):
    if not selected_paths:
        return html.Div(
            "No labels selected",
            style={"color": "#6c757d", "font-style": "italic", "font-size": "0.9em"},
        )

    badges = []
    for i, path in enumerate(selected_paths):
        display_name = get_label_display_name(path)
        badge = dbc.Badge([
            display_name,
            html.Span(
                "×",
                style={"margin-left": "8px", "cursor": "pointer", "font-weight": "bold"},
                id={"type": "remove-label", "filename": filename, "index": i},
            ),
        ], color="primary", className="me-2 mb-1", style={"font-size": "0.8em"})
        badges.append(badge)

    return html.Div(badges, style={"display": "flex", "flex-wrap": "wrap", "gap": "4px"})


def create_tree_structure(hierarchy, filename, selected_paths, current_path=None, level=0, read_only=False):
    if current_path is None:
        current_path = []

    tree_items = []
    for key, value in hierarchy.items():
        new_path = current_path + [key]
        path_tuple = tuple(new_path)
        path_string = path_to_string(path_tuple)
        is_selected = path_tuple in selected_paths
        has_children = isinstance(value, dict) and value

        node_content = []
        if has_children:
            node_content.append(html.Span(
                "▶",
                id={"type": "expand-btn", "filename": filename, "path": path_string},
                style={
                    "cursor": "pointer",
                    "margin-right": "6px",
                    "color": "#6c757d",
                    "font-size": "0.8em",
                },
            ))
        else:
            node_content.append(html.Span(style={"width": "16px", "display": "inline-block"}))

        node_content.append(dbc.Checkbox(
            id={"type": "hierarchical-checkbox", "filename": filename, "path": path_string},
            value=is_selected,
            disabled=read_only,
            style={"margin-right": "8px", "margin-top": "2px"},
        ))

        node_content.append(html.Span(
            key,
            style={
                "font-size": "0.9em",
                "color": "#495057" if not is_selected else "#0d6efd",
                "font-weight": "500" if is_selected else "400",
                "cursor": "pointer",
            },
        ))

        tree_items.append(html.Div([
            html.Div(
                node_content,
                style={
                    "display": "flex",
                    "align-items": "center",
                    "padding": "2px 0",
                    "margin-left": f"{level * 20}px",
                    "background": "#f8f9fa" if is_selected else "transparent",
                    "border-radius": "4px",
                    "padding-left": "6px" if is_selected else "0",
                },
            ),
            html.Div(
                id={"type": "children-container", "filename": filename, "path": path_string},
                children=create_tree_structure(value, filename, selected_paths, new_path, level + 1, read_only=read_only)
                if has_children else [],
                style={"display": "none"} if has_children else {},
            ),
        ]))

    return tree_items


@callback(
    Output({"type": "children-container", "filename": MATCH, "path": MATCH}, "style"),
    Output({"type": "expand-btn", "filename": MATCH, "path": MATCH}, "style"),
    Input({"type": "expand-btn", "filename": MATCH, "path": MATCH}, "n_clicks"),
    State({"type": "children-container", "filename": MATCH, "path": MATCH}, "style"),
    prevent_initial_call=True,
)
def toggle_tree_node(n_clicks, current_style):
    if not n_clicks:
        return current_style, {"cursor": "pointer", "margin-right": "6px", "color": "#6c757d", "font-size": "0.8em"}

    is_hidden = current_style.get("display") == "none"
    return (
        {"display": "block"} if is_hidden else {"display": "none"},
        {
            "cursor": "pointer",
            "margin-right": "6px",
            "color": "#6c757d",
            "font-size": "0.8em",
            "transform": "rotate(90deg)" if is_hidden else "rotate(0deg)",
            "transition": "transform 0.2s",
        },
    )


@callback(
    Output({"type": "selected-labels-store", "filename": MATCH}, "data"),
    Output({"type": "selected-labels-display", "filename": MATCH}, "children"),
    Input({"type": "hierarchical-checkbox", "filename": MATCH, "path": ALL}, "value"),
    State({"type": "hierarchical-checkbox", "filename": MATCH, "path": ALL}, "id"),
    prevent_initial_call=True,
)
def update_selected_labels(checkbox_values, checkbox_ids):
    if not checkbox_values or not checkbox_ids:
        return [], create_selected_labels_display([], checkbox_ids[0]["filename"] if checkbox_ids else "")

    filename = checkbox_ids[0]["filename"]
    selected_paths = []
    for i, is_checked in enumerate(checkbox_values):
        if is_checked:
            path_string = checkbox_ids[i]["path"]
            selected_paths.append(tuple(path_string.split(" > ")))

    display = create_selected_labels_display(selected_paths, filename)
    selected_strings = [path_to_string(path) for path in selected_paths]
    return selected_strings, display


@callback(
    Output({"type": "selected-labels-store", "filename": MATCH}, "data", allow_duplicate=True),
    Output({"type": "selected-labels-display", "filename": MATCH}, "children", allow_duplicate=True),
    Output({"type": "hierarchical-tree", "filename": MATCH}, "children", allow_duplicate=True),
    Input({"type": "remove-label", "filename": MATCH, "index": ALL}, "n_clicks"),
    State({"type": "remove-label", "filename": MATCH, "index": ALL}, "id"),
    State({"type": "selected-labels-store", "filename": MATCH}, "data"),
    prevent_initial_call=True,
)
def remove_label(n_clicks_list, remove_ids, current_labels):
    if not n_clicks_list or not any(n_clicks_list):
        return current_labels, dash.no_update, dash.no_update

    ctx = dash.callback_context
    if not ctx.triggered:
        return current_labels, dash.no_update, dash.no_update

    filename = None
    remove_index = None
    for i, n_clicks in enumerate(n_clicks_list):
        if n_clicks and n_clicks > 0:
            if i < len(remove_ids):
                remove_index = remove_ids[i]["index"]
                filename = remove_ids[i]["filename"]
                break

    if remove_index is None or filename is None:
        return current_labels, dash.no_update, dash.no_update

    updated_labels = [label for i, label in enumerate(current_labels) if i != remove_index]
    selected_paths = [tuple(label.split(" > ")) for label in updated_labels]

    display = create_selected_labels_display(selected_paths, filename)
    tree_structure = create_tree_structure(HIERARCHICAL_LABELS, filename, selected_paths)

    return updated_labels, display, tree_structure


@callback(
    Output({"type": "label-search", "filename": MATCH}, "value"),
    Input({"type": "clear-search", "filename": MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def clear_search_input(clear_clicks):
    if clear_clicks:
        return ""
    return dash.no_update


@callback(
    Output({"type": "search-debounce-timer", "filename": MATCH}, "n_intervals"),
    Output({"type": "search-debounce-timer", "filename": MATCH}, "disabled"),
    Input({"type": "label-search", "filename": MATCH}, "value"),
    prevent_initial_call=True,
)
def reset_search_timer(_search_value):
    return 0, False


@callback(
    Output({"type": "hierarchical-tree", "filename": MATCH}, "children"),
    Input({"type": "search-debounce-timer", "filename": MATCH}, "n_intervals"),
    Input({"type": "clear-search", "filename": MATCH}, "n_clicks"),
    State({"type": "label-search", "filename": MATCH}, "value"),
    State({"type": "selected-labels-store", "filename": MATCH}, "data"),
    State({"type": "label-search", "filename": MATCH}, "id"),
    prevent_initial_call=True,
)
def filter_tree(timer_intervals, clear_clicks, search_value, selected_labels, search_id):
    filename = search_id["filename"]

    selected_paths = []
    if selected_labels:
        for label in selected_labels:
            if isinstance(label, str) and label.strip():
                selected_paths.append(tuple(label.split(" > ")))

    if timer_intervals is None or timer_intervals < 1:
        return dash.no_update

    if search_value is None:
        return dash.no_update

    if not search_value or search_value.strip() == "":
        return create_tree_structure(HIERARCHICAL_LABELS, filename, selected_paths)

    search_term = search_value.strip().lower()
    if len(search_term) < 3:
        return create_tree_structure(HIERARCHICAL_LABELS, filename, selected_paths)

    filtered_hierarchy, expanded_paths = filter_hierarchy_by_search(HIERARCHICAL_LABELS, search_term, selected_paths)
    return create_tree_structure_with_expansion(filtered_hierarchy, filename, selected_paths, expanded_paths)


def filter_hierarchy_by_search(hierarchy, search_term, selected_paths, current_path=None):
    if current_path is None:
        current_path = []

    filtered = {}
    paths_to_expand = set()

    for key, value in hierarchy.items():
        new_path = current_path + [key]
        path_tuple = tuple(new_path)

        key_matches = search_term in key.lower()
        is_selected = path_tuple in selected_paths

        children_match = False
        filtered_children = {}
        child_expand_paths = set()

        if isinstance(value, dict) and value:
            if key_matches:
                filtered_children = value
                children_match = True
                for i in range(1, len(new_path) + 1):
                    parent_path = tuple(new_path[:i])
                    paths_to_expand.add(path_to_string(parent_path))
            else:
                filtered_children, child_expand_paths = filter_hierarchy_by_search(
                    value, search_term, selected_paths, new_path
                )
                children_match = bool(filtered_children)
                paths_to_expand.update(child_expand_paths)

        if key_matches or children_match or is_selected:
            filtered[key] = filtered_children if filtered_children else value
            for i in range(1, len(new_path) + 1):
                parent_path = tuple(new_path[:i])
                paths_to_expand.add(path_to_string(parent_path))

    return filtered, paths_to_expand


def create_tree_structure_with_expansion(hierarchy, filename, selected_paths, expanded_paths, current_path=None, level=0):
    if current_path is None:
        current_path = []

    tree_items = []
    for key, value in hierarchy.items():
        new_path = current_path + [key]
        path_tuple = tuple(new_path)
        path_string = path_to_string(path_tuple)
        is_selected = path_tuple in selected_paths
        has_children = isinstance(value, dict) and value

        should_expand = path_string in expanded_paths

        node_content = []
        if has_children:
            node_content.append(html.Span(
                "▶",
                id={"type": "expand-btn", "filename": filename, "path": path_string},
                style={
                    "cursor": "pointer",
                    "margin-right": "6px",
                    "color": "#6c757d",
                    "font-size": "0.8em",
                    "transform": "rotate(90deg)" if should_expand else "rotate(0deg)",
                    "transition": "transform 0.2s",
                },
            ))
        else:
            node_content.append(html.Span(style={"width": "16px", "display": "inline-block"}))

        node_content.append(dbc.Checkbox(
            id={"type": "hierarchical-checkbox", "filename": filename, "path": path_string},
            value=is_selected,
            style={"margin-right": "8px", "margin-top": "2px"},
        ))

        node_content.append(html.Span(
            key,
            style={
                "font-size": "0.9em",
                "color": "#495057" if not is_selected else "#0d6efd",
                "font-weight": "500" if is_selected else "400",
                "cursor": "pointer",
            },
        ))

        tree_items.append(html.Div([
            html.Div(
                node_content,
                style={
                    "display": "flex",
                    "align-items": "center",
                    "padding": "2px 0",
                    "margin-left": f"{level * 20}px",
                    "background": "#f8f9fa" if is_selected else "transparent",
                    "border-radius": "4px",
                    "padding-left": "6px" if is_selected else "0",
                },
            ),
            html.Div(
                id={"type": "children-container", "filename": filename, "path": path_string},
                children=create_tree_structure_with_expansion(
                    value, filename, selected_paths, expanded_paths, new_path, level + 1
                ) if has_children else [],
                style={"display": "block" if should_expand else "none"} if has_children else {},
            ),
        ]))

    return tree_items

