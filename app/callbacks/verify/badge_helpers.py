"""Helpers for verify badge accept/reject/delete callback logic."""

import json
from copy import deepcopy


def flatten_callback_inputs(inputs_list):
    """Flatten Dash ctx.inputs_list into a list of dict entries."""
    entries = []
    for group in (inputs_list or []):
        if isinstance(group, list):
            entries.extend(group)
        elif isinstance(group, dict):
            entries.append(group)
    return entries


def timestamp_summary(*, card_accept_ts, card_reject_ts, card_delete_ts, card_accept_ts_legacy, card_reject_ts_legacy, card_delete_ts_legacy, modal_accept_ts, modal_reject_ts, modal_delete_ts, modal_accept_ts_legacy, modal_reject_ts_legacy, modal_delete_ts_legacy):
    def _max_or_default(values):
        if not values:
            return -1
        return max((v or -1) for v in values)

    return {
        "card_accept_target": _max_or_default(card_accept_ts),
        "card_reject_target": _max_or_default(card_reject_ts),
        "card_delete_target": _max_or_default(card_delete_ts),
        "card_accept_legacy": _max_or_default(card_accept_ts_legacy),
        "card_reject_legacy": _max_or_default(card_reject_ts_legacy),
        "card_delete_legacy": _max_or_default(card_delete_ts_legacy),
        "modal_accept_target": _max_or_default(modal_accept_ts),
        "modal_reject_target": _max_or_default(modal_reject_ts),
        "modal_delete_target": _max_or_default(modal_delete_ts),
        "modal_accept_legacy": _max_or_default(modal_accept_ts_legacy),
        "modal_reject_legacy": _max_or_default(modal_reject_ts_legacy),
        "modal_delete_legacy": _max_or_default(modal_delete_ts_legacy),
    }


def resolve_trigger_timestamp(*, input_entries, triggered):
    """Return max n_clicks_timestamp for the triggered dict id."""
    triggered_key_json = json.dumps(triggered, sort_keys=True, ensure_ascii=True)
    matching_timestamps = []
    for entry in input_entries:
        if not isinstance(entry, dict):
            continue
        event_id = entry.get("id")
        if not isinstance(event_id, dict):
            continue
        if json.dumps(event_id, sort_keys=True, ensure_ascii=True) != triggered_key_json:
            continue
        ts_val = entry.get("value")
        if isinstance(ts_val, (int, float)) and ts_val > 0:
            matching_timestamps.append(int(ts_val))
    if not matching_timestamps:
        return None
    return max(matching_timestamps)


def resolve_trigger_payload(*, triggered, action_type, modal_item_id, parse_verify_target):
    """Resolve item_id/label/item_key from triggered action metadata."""
    label = ""
    item_id = ""
    item_key = ""
    target = (triggered.get("target") or "").strip()

    if action_type in {"verify-label-accept", "verify-label-reject", "verify-label-delete"}:
        parsed_key, parsed_item_id, parsed_label = parse_verify_target(target)
        item_key = parsed_key
        item_id = parsed_item_id or (triggered.get("item_id") or "").strip()
        label = parsed_label or (triggered.get("label") or target).strip()
    elif action_type in {"modal-verify-label-accept", "modal-verify-label-reject", "modal-verify-label-delete"}:
        item_id = (modal_item_id or "").strip()
        label = (triggered.get("label") or target).strip()

    return item_key, item_id, label, target


def action_from_action_type(action_type):
    if action_type.endswith("accept"):
        return "accept"
    if action_type.endswith("reject"):
        return "reject"
    return "delete"


def find_active_item(*, items, item_key, item_id, item_action_key):
    """Find active verify item by stable item key first, then by item_id."""
    active_item = None
    active_item_index = -1
    if item_key:
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if item_action_key(item) == item_key:
                active_item = item
                active_item_index = idx
                break
    if active_item is None:
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if item.get("item_id") == item_id:
                active_item = item
                active_item_index = idx
                break
    return active_item, active_item_index


def apply_action_to_labels(*, action, label, updated_labels, predicted_set, rejected_set):
    if action == "accept":
        if label not in updated_labels:
            updated_labels.append(label)
        rejected_set.discard(label)
    elif action == "reject":
        updated_labels[:] = [existing for existing in updated_labels if existing != label]
        if label in predicted_set:
            rejected_set.add(label)
        else:
            rejected_set.discard(label)
    else:
        updated_labels[:] = [existing for existing in updated_labels if existing != label]
        rejected_set.discard(label)
    return updated_labels, rejected_set


def clean_label_extents_from_annotations(*, annotations_obj, clean_annotation_extent):
    label_extents = {}
    raw_label_extents = annotations_obj.get("label_extents") if isinstance(annotations_obj, dict) else None
    if isinstance(raw_label_extents, dict):
        for extent_label, extent in raw_label_extents.items():
            if not isinstance(extent_label, str):
                continue
            normalized_label = extent_label.strip()
            if not normalized_label:
                continue
            cleaned_extent = clean_annotation_extent(extent)
            if cleaned_extent:
                label_extents[normalized_label] = cleaned_extent
    return label_extents


def update_boxes_and_extents_for_action(
    *,
    action,
    label,
    item_id,
    modal_item_id,
    modal_bbox_store,
    active_item,
    build_modal_boxes_from_item,
    extract_label_extent_map_from_boxes,
    label_extents,
):
    next_bbox_store = None
    is_modal_target = item_id == (modal_item_id or "")
    if is_modal_target:
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
            boxes = deepcopy(modal_bbox_store.get("boxes") or [])
        else:
            boxes = build_modal_boxes_from_item(active_item)
        if action in {"reject", "delete"}:
            boxes = [
                box
                for box in boxes
                if not (isinstance(box, dict) and (box.get("label") or "").strip() == label)
            ]
        next_bbox_store = {"item_id": item_id, "boxes": boxes}
        label_extents = extract_label_extent_map_from_boxes(boxes)
    elif action in {"reject", "delete"}:
        label_extents.pop(label, None)
    return next_bbox_store, label_extents
