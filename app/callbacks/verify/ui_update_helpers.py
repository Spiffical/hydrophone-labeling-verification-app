"""Small UI patch helpers for verify card label/save controls."""

from dash import no_update

from app.components.spectrogram_card import create_verify_label_block_children


def _replace_matching_id(ids, item_id, value):
    if not ids:
        return no_update
    updates = [no_update] * len(ids)
    matched = False
    for index, id_obj in enumerate(ids or []):
        if isinstance(id_obj, dict) and id_obj.get("item_id") == item_id:
            updates[index] = value
            matched = True
    return updates if matched else no_update


def build_verify_card_ui_updates(
    item_id,
    item,
    label_block_ids,
    save_button_ids,
    *,
    predicted_labels,
    pending,
):
    """Return ALL-pattern updates for one verify card's label block and Save button."""
    label_children = create_verify_label_block_children(
        item_id,
        item,
        predicted_labels=predicted_labels,
    )
    disabled = not bool(pending)
    color = "success" if pending else "secondary"
    outline = not bool(pending)
    return (
        _replace_matching_id(label_block_ids, item_id, label_children),
        _replace_matching_id(save_button_ids, item_id, disabled),
        _replace_matching_id(save_button_ids, item_id, color),
        _replace_matching_id(save_button_ids, item_id, outline),
    )
