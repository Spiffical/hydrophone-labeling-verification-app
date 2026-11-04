"""Verify class-tree parsing/building/filter helpers."""

from app.services.annotations import ordered_unique_labels, split_hierarchy_label
from taxonomy.hierarchical_labels import canonicalize_prediction_label


def extract_verify_leaf_classes(items):
    classes = set()

    def _add_canonical(label):
        canonical = canonicalize_prediction_label(label)
        if canonical:
            classes.add(canonical)

    for item in items or []:
        if not isinstance(item, dict):
            continue
        for label in extract_item_review_filter_classes(item) + extract_item_review_filter_labels(item):
            _add_canonical(label)
        predictions = item.get("predictions") or {}

        model_outputs = predictions.get("model_outputs")
        if isinstance(model_outputs, list):
            for output in model_outputs:
                if not isinstance(output, dict):
                    continue
                _add_canonical(output.get("class_hierarchy"))
            # Unified prediction files define classes in model_outputs. Do not
            # mix in derived display labels or legacy confidence keys.
            continue

        probs = predictions.get("confidence") or {}
        if isinstance(probs, dict):
            for label in probs.keys():
                _add_canonical(label)
            if probs:
                continue

        labels = predictions.get("labels") or []
        if isinstance(labels, list):
            for label in labels:
                _add_canonical(label)
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


def _is_within(path, ancestor):
    return path == ancestor or path.startswith(f"{ancestor} > ")


def toggle_class_selection(selected_paths, path):
    """Turn one class on or off, returning None once nothing is left selected.

    Selecting a class replaces any selection above or below it, so picking a class
    inside a selected category narrows to that class, and picking a category widens
    back out. Paths are whole branches: a model label sitting on a branch ("Vessel")
    matches it, and its subclasses can be chosen without losing that label.
    """
    selected = normalize_verify_class_filter(selected_paths) or []
    if path in selected:
        remaining = [value for value in selected if value != path]
    else:
        remaining = [
            value
            for value in selected
            if not _is_within(value, path) and not _is_within(path, value)
        ]
        remaining.append(path)
    return remaining or None


def class_selection_state(selected_paths, path):
    """Return how a class relates to the selection: on, implied, partial or off."""
    selected = normalize_verify_class_filter(selected_paths) or []
    if path in selected:
        return "on"
    if any(_is_within(path, value) for value in selected):
        return "implied"
    if any(_is_within(value, path) for value in selected):
        return "partial"
    return "off"


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


def extract_item_review_filter_classes(item):
    if not isinstance(item, dict):
        return []
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    configured = metadata.get("review_filter_classes")
    if not isinstance(configured, list):
        configured = item.get("review_filter_classes")
    if not isinstance(configured, list):
        return []
    return ordered_unique_labels(configured)

def extract_item_review_filter_labels(item):
    if not isinstance(item, dict):
        return []
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    assigned = metadata.get("review_filter_labels")
    if not isinstance(assigned, list):
        assigned = item.get("review_filter_labels")
    if not isinstance(assigned, list):
        return []
    return ordered_unique_labels(assigned)
