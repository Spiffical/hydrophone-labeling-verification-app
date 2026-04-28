"""Helpers for staging note edits in label mode."""

from app.services.annotations import ordered_unique_labels
from app.services.verification import (
    update_item_labels,
    update_item_notes,
)


def stage_label_note_edit(data, item_id, note_text, *, user_name=None):
    """Stage a label-mode note edit while preserving the item's active labels."""
    if not isinstance(data, dict) or not item_id:
        return data, False

    items = data.get("items")
    if not isinstance(items, list):
        return data, False

    active_item = next(
        (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
        None,
    )
    if not isinstance(active_item, dict):
        return data, False

    annotations = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
    normalized_note = note_text if isinstance(note_text, str) else ""
    existing_note = annotations.get("notes", "") if isinstance(annotations.get("notes"), str) else ""
    if normalized_note == existing_note:
        return data, False

    annotations_labels = annotations.get("labels") if isinstance(annotations.get("labels"), list) else []
    predictions = active_item.get("predictions") if isinstance(active_item.get("predictions"), dict) else {}
    predicted_labels = predictions.get("labels") if isinstance(predictions.get("labels"), list) else []
    active_labels = ordered_unique_labels(annotations_labels or predicted_labels)

    updated = update_item_labels(
        data,
        item_id,
        active_labels,
        mode="label",
        user_name=user_name,
    )
    updated = update_item_notes(updated or {}, item_id, normalized_note, user_name=user_name)
    return updated, True
