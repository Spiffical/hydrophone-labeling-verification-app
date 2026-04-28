from datetime import datetime
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

    selected_paths = _normalize_selected_paths(selected_labels)
    initial_expanded_paths = sorted(_selected_ancestor_paths(selected_paths))

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
            children=build_tree_children(
                filename,
                selected_paths,
                expanded_paths=initial_expanded_paths,
                read_only=read_only,
            ),
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
        dcc.Store(
            id={"type": "tree-expanded-store", "filename": filename},
            data=initial_expanded_paths,
        ),
        dcc.Store(
            id={"type": "verify-actions-store", "filename": filename},
            data=[],
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


def _normalize_selected_paths(selected_labels):
    selected_paths = []
    seen = set()
    for label in selected_labels or []:
        if isinstance(label, str) and " > " in label:
            normalized = tuple(part.strip() for part in label.split(" > ") if part.strip())
        elif isinstance(label, (list, tuple)):
            normalized = tuple(str(part).strip() for part in label if str(part).strip())
        else:
            label_text = str(label).strip()
            normalized = (label_text,) if label_text else ()
        if not normalized or normalized in seen:
            continue
        selected_paths.append(normalized)
        seen.add(normalized)
    return selected_paths


def _selected_ancestor_paths(selected_paths):
    expanded_paths = set()
    for path in selected_paths or []:
        for depth in range(1, len(path)):
            expanded_paths.add(path_to_string(path[:depth]))
    return expanded_paths


def _has_selected_descendant(path_tuple, selected_paths):
    return any(
        len(selected_path) > len(path_tuple)
        and selected_path[: len(path_tuple)] == path_tuple
        for selected_path in selected_paths or []
    )


def build_tree_children(filename, selected_paths, expanded_paths=None, search_value=None, read_only=False):
    expanded_path_set = set(expanded_paths or [])

    hierarchy = HIERARCHICAL_LABELS
    normalized_search = (search_value or "").strip().lower()
    if len(normalized_search) >= 3:
        hierarchy, search_expanded_paths = filter_hierarchy_by_search(
            HIERARCHICAL_LABELS,
            normalized_search,
            selected_paths,
        )
        expanded_path_set.update(search_expanded_paths)

    return create_tree_structure(
        hierarchy,
        filename,
        selected_paths,
        expanded_paths=expanded_path_set,
        read_only=read_only,
    )


def create_tree_structure(
    hierarchy,
    filename,
    selected_paths,
    expanded_paths=None,
    current_path=None,
    level=0,
    read_only=False,
):
    if current_path is None:
        current_path = []

    expanded_path_set = set(expanded_paths or [])
    tree_items = []
    for key, value in hierarchy.items():
        new_path = current_path + [key]
        path_tuple = tuple(new_path)
        path_string = path_to_string(path_tuple)
        is_selected = path_tuple in selected_paths
        has_children = isinstance(value, dict) and value
        should_expand = has_children and path_string in expanded_path_set
        has_selected_descendant = _has_selected_descendant(path_tuple, selected_paths)

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

        if has_selected_descendant and not is_selected:
            node_content.append(html.Span(
                "selected below",
                title="This branch contains a selected label",
                style={
                    "margin-left": "8px",
                    "padding": "1px 6px",
                    "border-radius": "999px",
                    "background": "rgba(13, 110, 253, 0.08)",
                    "color": "#0d6efd",
                    "font-size": "0.68em",
                    "font-weight": "600",
                    "letter-spacing": "0.01em",
                    "white-space": "nowrap",
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
                    "background": "#f8f9fa" if is_selected else ("rgba(13, 110, 253, 0.03)" if has_selected_descendant else "transparent"),
                    "border-radius": "4px",
                    "padding-left": "6px" if (is_selected or has_selected_descendant) else "0",
                },
            ),
            html.Div(
                id={"type": "children-container", "filename": filename, "path": path_string},
                children=(
                    create_tree_structure(
                        value,
                        filename,
                        selected_paths,
                        expanded_paths=expanded_path_set,
                        current_path=new_path,
                        level=level + 1,
                        read_only=read_only,
                    )
                    if should_expand
                    else []
                ) if has_children else [],
                style={"display": "block" if should_expand else "none"} if has_children else {},
            ),
        ]))

    return tree_items


@callback(
    Output({"type": "tree-expanded-store", "filename": MATCH}, "data"),
    Input({"type": "expand-btn", "filename": MATCH, "path": ALL}, "n_clicks"),
    State({"type": "expand-btn", "filename": MATCH, "path": ALL}, "id"),
    State({"type": "tree-expanded-store", "filename": MATCH}, "data"),
    prevent_initial_call=True,
)
def toggle_tree_node(_n_clicks, expand_ids, expanded_paths):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        raise dash.exceptions.PreventUpdate

    path_string = triggered.get("path")
    if not path_string:
        raise dash.exceptions.PreventUpdate

    expanded_set = set(expanded_paths or [])
    if path_string in expanded_set:
        expanded_set.remove(path_string)
    else:
        expanded_set.add(path_string)
    _ = expand_ids
    return sorted(expanded_set)


@callback(
    Output({"type": "selected-labels-store", "filename": MATCH}, "data"),
    Output({"type": "selected-labels-display", "filename": MATCH}, "children"),
    Output({"type": "verify-actions-store", "filename": MATCH}, "data", allow_duplicate=True),
    Input({"type": "hierarchical-checkbox", "filename": MATCH, "path": ALL}, "value"),
    State({"type": "hierarchical-checkbox", "filename": MATCH, "path": ALL}, "id"),
    State({"type": "selected-labels-store", "filename": MATCH}, "data"),
    State({"type": "verify-actions-store", "filename": MATCH}, "data"),
    State("verify-thresholds-store", "data"),
    State("mode-tabs", "data"),
    prevent_initial_call=True,
)
def update_selected_labels(checkbox_values, checkbox_ids, current_labels, actions_store, thresholds, mode):
    if not checkbox_values or not checkbox_ids:
        filename = checkbox_ids[0]["filename"] if checkbox_ids else ""
        selected_paths = _normalize_selected_paths(current_labels)
        return list(current_labels or []), create_selected_labels_display(selected_paths, filename), dash.no_update

    filename = checkbox_ids[0]["filename"]
    visible_paths = [
        tuple(str(checkbox_id.get("path", "")).split(" > "))
        for checkbox_id in checkbox_ids
        if isinstance(checkbox_id, dict) and checkbox_id.get("path")
    ]
    visible_path_set = set(visible_paths)
    selected_paths = [
        path
        for path in _normalize_selected_paths(current_labels)
        if path not in visible_path_set
    ]
    for i, is_checked in enumerate(checkbox_values):
        if is_checked:
            path_string = checkbox_ids[i]["path"]
            selected_paths.append(tuple(path_string.split(" > ")))

    selected_paths = _normalize_selected_paths(selected_paths)
    display = create_selected_labels_display(selected_paths, filename)
    selected_strings = [path_to_string(path) for path in selected_paths]
    actions_store = actions_store or {}
    if mode != "verify":
        return selected_strings, display, dash.no_update

    previous_labels = current_labels or []
    previous_set = set(previous_labels)
    new_set = set(selected_strings)
    added = list(new_set - previous_set)
    removed = list(previous_set - new_set)
    if added or removed:
        threshold_used = float((thresholds or {}).get("__global__", 0.5))
        item_actions = actions_store.get(filename, [])
        timestamp = datetime.now().isoformat()
        for label in added:
            item_actions.append({
                "label": label,
                "action": "add",
                "threshold_used": threshold_used,
                "timestamp": timestamp,
            })
        for label in removed:
            item_actions.append({
                "label": label,
                "action": "remove",
                "threshold_used": threshold_used,
                "timestamp": timestamp,
            })
        actions_store[filename] = item_actions

    return selected_strings, display, actions_store


@callback(
    Output({"type": "selected-labels-store", "filename": MATCH}, "data", allow_duplicate=True),
    Output({"type": "selected-labels-display", "filename": MATCH}, "children", allow_duplicate=True),
    Output({"type": "verify-actions-store", "filename": MATCH}, "data", allow_duplicate=True),
    Input({"type": "remove-label", "filename": MATCH, "index": ALL}, "n_clicks"),
    State({"type": "remove-label", "filename": MATCH, "index": ALL}, "id"),
    State({"type": "selected-labels-store", "filename": MATCH}, "data"),
    State({"type": "verify-actions-store", "filename": MATCH}, "data"),
    State("verify-thresholds-store", "data"),
    State("mode-tabs", "data"),
    prevent_initial_call=True,
)
def remove_label(n_clicks_list, remove_ids, current_labels, actions_store, thresholds, mode):
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
    removed_label = current_labels[remove_index] if remove_index < len(current_labels) else None
    selected_paths = [tuple(label.split(" > ")) for label in updated_labels]

    display = create_selected_labels_display(selected_paths, filename)

    actions_store = actions_store or {}
    if mode == "verify" and removed_label:
        threshold_used = float((thresholds or {}).get("__global__", 0.5))
        item_actions = actions_store.get(filename, [])
        item_actions.append({
            "label": removed_label,
            "action": "remove",
            "threshold_used": threshold_used,
            "timestamp": datetime.now().isoformat(),
        })
        actions_store[filename] = item_actions
        return updated_labels, display, actions_store

    return updated_labels, display, dash.no_update


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
    Input({"type": "tree-expanded-store", "filename": MATCH}, "data"),
    Input({"type": "selected-labels-store", "filename": MATCH}, "data"),
    Input({"type": "search-debounce-timer", "filename": MATCH}, "n_intervals"),
    State({"type": "label-search", "filename": MATCH}, "value"),
    State({"type": "selected-labels-store", "filename": MATCH}, "data"),
    State({"type": "label-search", "filename": MATCH}, "id"),
    prevent_initial_call=True,
)
def filter_tree(expanded_paths, selected_labels, timer_intervals, search_value, _selected_state, search_id):
    _ = timer_intervals, _selected_state
    filename = search_id["filename"]
    selected_paths = _normalize_selected_paths(selected_labels)
    return build_tree_children(
        filename,
        selected_paths,
        expanded_paths=expanded_paths,
        search_value=search_value,
    )


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
