"""Reviewer-specific label shortcuts stored in the browser, separate from annotations."""

from taxonomy.hierarchical_labels import HIERARCHICAL_LABELS


def _valid_label(label):
    if not isinstance(label, str):
        return False
    node = HIERARCHICAL_LABELS
    for part in label.split(' > '):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def reviewer_key(profile):
    return str((profile or {}).get('email') or '').strip().lower() or '__local__'


def favorite_labels(store, profile):
    stored = store.get(reviewer_key(profile), []) if isinstance(store, dict) else []
    if not isinstance(stored, list):
        return []
    return list(dict.fromkeys(label for label in stored if _valid_label(label)))


def toggle_favorite(store, profile, label):
    result = dict(store) if isinstance(store, dict) else {}
    if not _valid_label(label):
        return result
    labels = favorite_labels(result, profile)
    result[reviewer_key(profile)] = (
        [existing for existing in labels if existing != label]
        if label in labels else labels + [label]
    )
    return result
