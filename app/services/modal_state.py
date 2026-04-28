"""Modal snapshot/dirty/data replacement and persistence helpers."""

import hashlib
from copy import deepcopy
from datetime import datetime

from dash import no_update

from app.services.annotations import (
    clean_annotation_extent,
    extract_label_extent_list_map_from_boxes,
    extract_label_extent_map_from_boxes,
    ordered_unique_labels,
)
from app.services.verification import (
    filter_predictions,
    get_item_rejected_labels,
    get_modal_label_sets,
    update_item_labels,
    update_item_notes,
)
from app.services.verify_filter_tree import (
    build_verify_filter_paths,
    extract_verify_leaf_classes,
    normalize_verify_class_filter,
    predicted_labels_match_filter,
)
from app.utils.persistence import save_label_mode, save_verify_predictions


def item_action_key(item):
    if not isinstance(item, dict):
        return ""
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    parts = [
        item.get("item_id"),
        item.get("mat_path"),
        item.get("spectrogram_path"),
        item.get("audio_path"),
        metadata.get("predictions_path"),
        metadata.get("date"),
        metadata.get("hydrophone"),
        item.get("device_code"),
    ]
    raw = "|".join("" if value is None else str(value) for value in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def get_mode_data(mode, label_data, verify_data, explore_data):
    return {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}


def replace_item_in_data(data, item_id, replacement_item):
    if not isinstance(data, dict) or not item_id:
        return data
    updated = deepcopy(data)
    items = updated.get("items")
    if not isinstance(items, list):
        return updated
    replaced = False
    for idx, item in enumerate(items):
        if isinstance(item, dict) and item.get("item_id") == item_id:
            items[idx] = deepcopy(replacement_item) if isinstance(replacement_item, dict) else replacement_item
            replaced = True
            break
    if not replaced:
        return updated

    summary = updated.get("summary")
    if isinstance(summary, dict):
        summary["annotated"] = sum(
            1
            for item in items
            if isinstance(item, dict) and ((item.get("annotations") or {}).get("labels") or [])
        )
        summary["verified"] = sum(
            1
            for item in items
            if isinstance(item, dict) and bool((item.get("annotations") or {}).get("verified"))
        )
        updated["summary"] = summary
    return updated


def modal_snapshot_payload(mode, item_id, item, boxes):
    if not item_id or not isinstance(item, dict):
        return None
    return {
        "mode": mode or "label",
        "item_id": item_id,
        "item": deepcopy(item),
        "boxes": deepcopy(boxes) if isinstance(boxes, list) else [],
    }


def is_modal_dirty(unsaved_store, current_item_id=None):
    if not isinstance(unsaved_store, dict):
        return False
    if not bool(unsaved_store.get("dirty")):
        return False
    dirty_item = unsaved_store.get("item_id")
    if current_item_id and dirty_item and dirty_item != current_item_id:
        return False
    return True


def get_modal_navigation_items(
    mode,
    label_data,
    verify_data,
    explore_data,
    thresholds,
    class_filter,
):
    mode = mode or "label"

    if mode == "verify":
        data = verify_data or {}
        items = data.get("items", [])
        thresholds = thresholds or {"__global__": 0.5}
        available_values = set(build_verify_filter_paths(extract_verify_leaf_classes(items)))
        selected_filters = normalize_verify_class_filter(class_filter)
        if not available_values:
            selected_filters = None
        if selected_filters is not None:
            selected_filters = [value for value in selected_filters if value in available_values]
        filtered_items = []
        for item in items:
            if not item:
                continue
            annotations = (item.get("annotations") or {})
            is_verified = bool(annotations.get("verified"))
            predictions = item.get("predictions") or {}
            predicted_labels = filter_predictions(predictions, thresholds)
            if not is_verified and not predicted_labels:
                continue
            if not predicted_labels_match_filter(predicted_labels, selected_filters):
                continue
            display_item = dict(item)
            display_predictions = dict(predictions)
            display_predictions["labels"] = predicted_labels
            display_item["predictions"] = display_predictions
            display_item["ui_rejected_labels"] = get_item_rejected_labels(item)
            filtered_items.append(display_item)
        return filtered_items

    if mode == "explore":
        data = explore_data or {}
        return data.get("items", [])

    data = label_data or {}
    return data.get("items", [])


def persist_modal_item_before_exit(
    mode,
    item_id,
    label_data,
    verify_data,
    explore_data,
    thresholds,
    profile,
    bbox_store,
    label_output_path,
    cfg,
    *,
    require_complete_profile,
    profile_actor,
):
    """Persist modal edits for the active item, then allow pending modal action."""
    mode = (mode or "label").strip()
    if not item_id:
        return no_update, no_update, no_update
    require_complete_profile(profile, "persist_modal_item_before_exit")

    profile_name = profile_actor(profile)

    if mode == "label":
        data = deepcopy(label_data or {})
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return no_update, no_update, no_update
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            return no_update, no_update, no_update

        _, _, active_labels = get_modal_label_sets(active_item, "label", thresholds or {"__global__": 0.5})
        labels_to_save = ordered_unique_labels(active_labels)
        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        note_text = annotations_obj.get("notes", "") if isinstance(annotations_obj.get("notes"), str) else ""

        label_extents = {}
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            label_extents = extract_label_extent_map_from_boxes(bbox_store.get("boxes") or [])
        else:
            existing_extents = annotations_obj.get("label_extents")
            if isinstance(existing_extents, dict):
                for label, extent in existing_extents.items():
                    if not isinstance(label, str):
                        continue
                    normalized_label = label.strip()
                    if not normalized_label:
                        continue
                    cleaned_extent = clean_annotation_extent(extent)
                    if cleaned_extent:
                        label_extents[normalized_label] = cleaned_extent

        updated = update_item_labels(
            data,
            item_id,
            labels_to_save,
            mode="label",
            user_name=profile_name,
            label_extents=label_extents or None,
        )
        updated = update_item_notes(updated or {}, item_id, note_text, user_name=profile_name)

        labels_file = (
            label_output_path
            or (updated or {}).get("summary", {}).get("labels_file")
            or ((cfg or {}).get("label", {}).get("output_file"))
        )
        save_label_mode(
            labels_file,
            item_id,
            labels_to_save,
            annotated_by=profile_name,
            notes=note_text,
            label_extents=label_extents or None,
        )
        updated = update_item_labels(
            updated or {},
            item_id,
            labels_to_save,
            mode="label",
            user_name=profile_name,
            is_reverification=True,
            label_extents=label_extents or None,
        )
        return updated, no_update, no_update

    if mode == "verify":
        thresholds = thresholds or {"__global__": 0.5}
        data = deepcopy(verify_data or {})
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return no_update, no_update, no_update
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            return no_update, no_update, no_update

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        predictions = active_item.get("predictions") if isinstance(active_item.get("predictions"), dict) else {}

        _, _, active_labels = get_modal_label_sets(active_item, "verify", thresholds)
        labels_to_confirm = ordered_unique_labels(active_labels)
        labels_set = set(labels_to_confirm)
        predicted_labels = ordered_unique_labels(filter_predictions(predictions, thresholds))
        predicted_set = set(predicted_labels)

        model_extent_map = {}
        model_scores = {}
        model_outputs = predictions.get("model_outputs")
        if isinstance(model_outputs, list):
            for output in model_outputs:
                if not isinstance(output, dict):
                    continue
                label = output.get("class_hierarchy")
                if not isinstance(label, str) or not label.strip():
                    continue
                label = label.strip()
                score = output.get("score")
                if isinstance(score, (int, float)):
                    model_scores[label] = float(score)
                cleaned_extent = clean_annotation_extent(output.get("annotation_extent"))
                if cleaned_extent:
                    model_extent_map[label] = cleaned_extent
        else:
            confidence = predictions.get("confidence") if isinstance(predictions.get("confidence"), dict) else {}
            for label, score in confidence.items():
                if isinstance(label, str) and isinstance(score, (int, float)):
                    model_scores[label.strip()] = float(score)

        box_extent_map = {}
        box_extent_lists = {}
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            modal_boxes = bbox_store.get("boxes") or []
            box_extent_map = extract_label_extent_map_from_boxes(modal_boxes)
            box_extent_lists = extract_label_extent_list_map_from_boxes(modal_boxes)
        else:
            existing_extents = annotations_obj.get("label_extents")
            if isinstance(existing_extents, dict):
                for label, extent in existing_extents.items():
                    if not isinstance(label, str) or not label.strip():
                        continue
                    cleaned_extent = clean_annotation_extent(extent)
                    if not cleaned_extent:
                        continue
                    label = label.strip()
                    box_extent_map[label] = cleaned_extent
                    box_extent_lists[label] = [cleaned_extent]

        threshold_used = float(thresholds.get("__global__", 0.5))
        rejected_labels = set(ordered_unique_labels(annotations_obj.get("rejected_labels") or []))
        for label in predicted_labels:
            if label not in labels_set:
                rejected_labels.add(label)
        for label in labels_to_confirm:
            rejected_labels.discard(label)

        label_decisions = []
        for label in labels_to_confirm:
            decision = "accepted" if label in predicted_set else "added"
            entry = {
                "label": label,
                "decision": decision,
                "threshold_used": threshold_used,
            }
            label_extents = box_extent_lists.get(label) or []
            extent = (label_extents[0] if label_extents else None) or model_extent_map.get(label)
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)
            for extra_extent in label_extents[1:]:
                if not isinstance(extra_extent, dict):
                    continue
                label_decisions.append(
                    {
                        "label": label,
                        "decision": decision,
                        "threshold_used": threshold_used,
                        "annotation_extent": extra_extent,
                    }
                )

        for label in sorted(rejected_labels - labels_set):
            entry = {
                "label": label,
                "decision": "rejected",
                "threshold_used": threshold_used,
            }
            label_extents = box_extent_lists.get(label) or []
            extent = model_extent_map.get(label) or (label_extents[0] if label_extents else box_extent_map.get(label))
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)

        note_text = annotations_obj.get("notes", "") if isinstance(annotations_obj.get("notes"), str) else ""
        verification = {
            "verified_at": datetime.now().isoformat(),
            "verified_by": profile_name or "anonymous",
            "label_decisions": label_decisions,
            "verification_status": "verified",
            "notes": note_text,
        }
        scope_date = active_item.get("date") or (active_item.get("metadata") or {}).get("date")
        scope_device = (
            active_item.get("device_code")
            or (active_item.get("metadata") or {}).get("hydrophone")
            or (active_item.get("metadata") or {}).get("device")
        )
        if scope_date:
            verification["date"] = scope_date
        if scope_device:
            verification["hydrophone"] = scope_device
            verification["device_code"] = scope_device

        predictions_path = (active_item.get("metadata") or {}).get("predictions_path")
        if not predictions_path:
            summary_pred = (data or {}).get("summary", {}).get("predictions_file")
            if isinstance(summary_pred, str) and summary_pred.endswith(".json"):
                predictions_path = summary_pred

        updated = update_item_labels(
            data,
            item_id,
            labels_to_confirm,
            mode="verify",
            user_name=profile_name,
            is_reverification=True,
            label_extents=box_extent_map or None,
        )
        for item in (updated or {}).get("items", []):
            if not isinstance(item, dict) or item.get("item_id") != item_id:
                continue
            item_annotations = item.get("annotations") or {}
            item_annotations["rejected_labels"] = sorted(rejected_labels)
            item["annotations"] = item_annotations
            break

        stored_verification = save_verify_predictions(
            predictions_path,
            item_id,
            verification,
            source_item=active_item,
        )
        if stored_verification:
            for item in (updated or {}).get("items", []):
                if item.get("item_id") != item_id:
                    continue
                verifications = item.get("verifications")
                if not isinstance(verifications, list):
                    verifications = []
                verifications.append(stored_verification)
                item["verifications"] = verifications
                break

        return no_update, updated, no_update

    return no_update, no_update, no_update
