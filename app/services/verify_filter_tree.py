"""Verify class-tree parsing/building/filter helpers."""

import dash_bootstrap_components as dbc
from dash import html

from app.services.annotations import ordered_unique_labels, split_hierarchy_label


def extract_verify_leaf_classes(items):
    classes = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        predictions = item.get("predictions") or {}

        model_outputs = predictions.get("model_outputs")
        if isinstance(model_outputs, list):
            for output in model_outputs:
                if not isinstance(output, dict):
                    continue
                label = output.get("class_hierarchy")
                if isinstance(label, str) and label.strip():
                    classes.add(label.strip())

        probs = predictions.get("confidence") or {}
        if isinstance(probs, dict):
            for label in probs.keys():
                if isinstance(label, str) and label.strip():
                    classes.add(label.strip())

        labels = predictions.get("labels") or []
        if isinstance(labels, list):
            for label in labels:
                if isinstance(label, str) and label.strip():
                    classes.add(label.strip())
    return sorted(classes, key=lambda text: text.lower())


def build_verify_filter_paths(classes):
    tree = {}
    for label in classes or []:
        parts = split_hierarchy_label(label)
        if not parts:
            continue
        cursor = tree
        for part in parts:
            cursor = cursor.setdefault(part, {})

    ordered_paths = []

    def _walk(node, prefix):
        for part in sorted(node.keys(), key=lambda text: text.lower()):
            path_parts = prefix + [part]
            ordered_paths.append(path_parts)
            _walk(node[part], path_parts)

    _walk(tree, [])
    return [" > ".join(path_parts) for path_parts in ordered_paths]


def build_verify_filter_tree_rows(paths, selected_paths, expanded_paths):
    selected_set = set(ordered_unique_labels(selected_paths or []))
    expanded_set = set(ordered_unique_labels(expanded_paths or []))

    tree = {}
    for path in paths or []:
        parts = split_hierarchy_label(path)
        if not parts:
            continue
        cursor = tree
        for part in parts:
            cursor = cursor.setdefault(part, {})

    def _walk(node, prefix, level):
        rows = []
        for name in sorted(node.keys(), key=lambda text: text.lower()):
            path_parts = prefix + [name]
            path = " > ".join(path_parts)
            children = node[name]
            has_children = bool(children)
            is_expanded = path in expanded_set
            is_selected = path in selected_set

            rows.append(
                html.Div(
                    [
                        html.Div(
                            [
                                (
                                    html.Button(
                                        "▾" if is_expanded else "▸",
                                        id={"type": "verify-filter-expand", "path": path},
                                        n_clicks=0,
                                        className="verify-filter-expand-btn",
                                        title=("Collapse" if is_expanded else "Expand"),
                                        type="button",
                                    )
                                    if has_children
                                    else html.Span("", className="verify-filter-expand-spacer")
                                ),
                                dbc.Checkbox(
                                    id={"type": "verify-filter-checkbox", "path": path},
                                    value=is_selected,
                                    className="verify-filter-node-check",
                                ),
                                html.Span(
                                    name,
                                    className="verify-filter-node-label",
                                    title=path,
                                ),
                            ],
                            className="verify-filter-node-row",
                            style={"paddingLeft": f"{level * 16}px"},
                        ),
                        html.Div(
                            _walk(children, path_parts, level + 1),
                            className="verify-filter-children",
                            style={"display": "block" if (has_children and is_expanded) else "none"},
                        ),
                    ],
                    className="verify-filter-node-group",
                )
            )
        return rows

    return _walk(tree, [], 0)


def normalize_verify_class_filter(class_filter):
    if class_filter is None:
        return None
    if isinstance(class_filter, str):
        normalized = class_filter.strip()
        if not normalized or normalized.lower() == "all":
            return None
        return [normalized]
    if isinstance(class_filter, (list, tuple, set)):
        return ordered_unique_labels(class_filter)
    return None


def predicted_labels_match_filter(predicted_labels, selected_filter_paths):
    if selected_filter_paths is None:
        return True
    if not selected_filter_paths:
        return False
    selected = [path for path in selected_filter_paths if isinstance(path, str) and path.strip()]
    if not selected:
        return False
    for label in predicted_labels or []:
        if not isinstance(label, str):
            continue
        normalized_label = label.strip()
        if not normalized_label:
            continue
        for selected_path in selected:
            if normalized_label == selected_path or normalized_label.startswith(f"{selected_path} > "):
                return True
    return False
