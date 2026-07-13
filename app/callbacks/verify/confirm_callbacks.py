"""Verification confirm/save callback registration."""

from datetime import datetime

from dash import ALL, Input, Output, Patch, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.verify.ui_update_helpers import build_verify_card_ui_updates
from app.services.verify_modal_cache import (
    get_verify_modal_item,
    get_verify_modal_item_index,
    get_verify_modal_summary,
    update_verify_modal_item,
)
from app.services.annotations import extract_box_annotation_list_map_from_boxes
from app.utils.persistence import save_verify_predictions


def _attach_box_metadata(entry, *, box_annotations, label_extents, model_extent_map):
    first_box = box_annotations[0] if box_annotations else None
    extent = (
        (first_box or {}).get("annotation_extent")
        or (label_extents[0] if label_extents else None)
        or model_extent_map.get(entry.get("label"))
    )
    if extent:
        entry["annotation_extent"] = extent
    if isinstance(first_box, dict) and first_box.get("tag"):
        entry["tag"] = first_box["tag"]
    return entry


def register_verify_confirm_callbacks(
    app,
    *,
    _require_complete_profile,
    _filter_predictions,
    _clean_annotation_extent,
    _extract_label_extent_list_map_from_boxes,
    _extract_label_extent_map_from_boxes,
    _get_modal_label_sets,
    _get_item_rejected_labels,
    _profile_actor,
    _update_item_labels,
    _build_modal_boxes_from_item,
    _build_modal_item_actions,
    _modal_snapshot_payload,
):
    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output({"type": "verify-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Input({"type": "confirm-btn", "item_id": ALL}, "n_clicks"),
        State("verify-thresholds-store", "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "id"),
        State("user-profile-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State({"type": "verify-label-block", "item_id": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        prevent_initial_call=True,
    )
    def confirm_verification(
        n_clicks_list,
        thresholds,
        actions_list,
        actions_ids,
        profile,
        verify_data_cache_key,
        label_block_ids,
        save_button_ids,
    ):
        triggered = ctx.triggered_id
        if not n_clicks_list or not any(n_clicks_list):
            raise PreventUpdate
        if not isinstance(triggered, dict) or "item_id" not in triggered:
            raise PreventUpdate
        item_id = triggered["item_id"]

        _require_complete_profile(profile, "confirm_verification")

        labels_to_confirm = []
        predictions = {}
        predictions_path = None
        annotations = {}
        active_item = get_verify_modal_item(verify_data_cache_key, item_id)
        active_item_index = get_verify_modal_item_index(verify_data_cache_key, item_id)
        if not isinstance(active_item, dict) or active_item_index is None:
            raise PreventUpdate
        summary = get_verify_modal_summary(verify_data_cache_key) or {}
        thresholds = thresholds or {"__global__": 0.5}
        threshold_used = float(thresholds.get("__global__", 0.5))
        annotations = active_item.get("annotations") or {}
        predictions = active_item.get("predictions") or {}
        predictions_path = (active_item.get("metadata") or {}).get("predictions_path")
        _, _, active_labels = _get_modal_label_sets(active_item, "verify", thresholds)
        labels_to_confirm = list(active_labels or [])

        box_extent_map = {}
        box_extent_lists = {}
        box_annotation_lists = {}
        modal_boxes = _build_modal_boxes_from_item(active_item)
        if modal_boxes:
            box_extent_map = _extract_label_extent_map_from_boxes(modal_boxes)
            box_extent_lists = _extract_label_extent_list_map_from_boxes(modal_boxes)
            box_annotation_lists = extract_box_annotation_list_map_from_boxes(modal_boxes)

        if box_extent_lists:
            ordered = list(labels_to_confirm or [])
            seen = set(ordered)
            for label in box_extent_lists.keys():
                if label not in seen:
                    ordered.append(label)
                    seen.add(label)
            labels_to_confirm = ordered

        if not predictions_path:
            summary_pred = summary.get("predictions_file") if isinstance(summary, dict) else None
            if isinstance(summary_pred, str) and summary_pred.endswith(".json"):
                predictions_path = summary_pred

        predicted_labels = _filter_predictions(predictions, thresholds)
        predicted_set = set(predicted_labels)
        labels_set = set(labels_to_confirm)

        model_scores = {}
        model_extent_map = {}
        model_outputs = predictions.get("model_outputs")
        if model_outputs and isinstance(model_outputs, list):
            for out in model_outputs:
                label = out.get("class_hierarchy")
                score = out.get("score")
                if label and isinstance(score, (int, float)):
                    model_scores[label] = score
                if label:
                    cleaned_extent = _clean_annotation_extent(out.get("annotation_extent"))
                    if cleaned_extent:
                        model_extent_map[label] = cleaned_extent
        else:
            probs = predictions.get("confidence") or {}
            for label, score in probs.items():
                if isinstance(score, (int, float)):
                    model_scores[label] = score

        item_actions = []
        for i, action_id in enumerate(actions_ids or []):
            if action_id.get("filename") == item_id:
                item_actions = (actions_list or [])[i] or []
                break
        last_add_threshold = {}
        last_remove_threshold = {}
        for action in item_actions:
            label = action.get("label")
            threshold_value = action.get("threshold_used")
            if not label or threshold_value is None:
                continue
            if action.get("action") == "add":
                last_add_threshold[label] = threshold_value
            elif action.get("action") == "remove":
                last_remove_threshold[label] = threshold_value

        rejected_labels = set(_get_item_rejected_labels(active_item))
        for label in predicted_labels:
            if label not in labels_set:
                rejected_labels.add(label)
        for label, removed_threshold in last_remove_threshold.items():
            score = model_scores.get(label)
            if score is not None and score >= float(removed_threshold):
                rejected_labels.add(label)
        for label in labels_to_confirm:
            rejected_labels.discard(label)

        label_decisions = []
        for label in labels_to_confirm:
            if label in predicted_set:
                decision = "accepted"
            else:
                decision = "added"
            threshold_for_label = float(last_add_threshold.get(label, threshold_used))
            entry = {
                "label": label,
                "decision": decision,
                "threshold_used": threshold_for_label,
            }
            box_annotations = box_annotation_lists.get(label) or []
            label_extents = box_extent_lists.get(label) or []
            _attach_box_metadata(
                entry,
                box_annotations=box_annotations,
                label_extents=label_extents,
                model_extent_map=model_extent_map,
            )
            label_decisions.append(entry)
            for idx, extra_extent in enumerate(label_extents[1:], start=1):
                if not isinstance(extra_extent, dict):
                    continue
                extra_entry = {
                    "label": label,
                    "decision": decision,
                    "threshold_used": threshold_for_label,
                    "annotation_extent": extra_extent,
                }
                extra_box = box_annotations[idx] if idx < len(box_annotations) else None
                if isinstance(extra_box, dict) and extra_box.get("tag"):
                    extra_entry["tag"] = extra_box["tag"]
                label_decisions.append(extra_entry)
        for label in sorted(rejected_labels - labels_set):
            entry = {
                "label": label,
                "decision": "rejected",
                "threshold_used": float(last_remove_threshold.get(label, threshold_used)),
            }
            label_extents = box_extent_lists.get(label) or []
            extent = model_extent_map.get(label) or (label_extents[0] if label_extents else box_extent_map.get(label))
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)

        profile_name = _profile_actor(profile)
        note_text = annotations.get("notes", "") if isinstance(annotations, dict) else ""
        verification = {
            "verified_at": datetime.now().isoformat(),
            "verified_by": profile_name or "anonymous",
            "label_decisions": label_decisions,
            "verification_status": "verified",
            "notes": note_text,
        }

        updated = _update_item_labels(
            {"items": [active_item], "summary": summary},
            item_id,
            labels_to_confirm,
            mode="verify",
            user_name=profile_name,
            is_reverification=True,
            label_extents=box_extent_map or None,
            bbox_annotations=[
                annotation
                for annotations_for_label in box_annotation_lists.values()
                for annotation in annotations_for_label
            ],
        )
        updated_item = next(
            (
                item
                for item in (updated or {}).get("items", [])
                if isinstance(item, dict) and item.get("item_id") == item_id
            ),
            None,
        )
        if not isinstance(updated_item, dict):
            raise PreventUpdate
        annotations_obj = updated_item.get("annotations") or {}
        annotations_obj["rejected_labels"] = sorted(rejected_labels)
        updated_item["annotations"] = annotations_obj

        stored_verification = save_verify_predictions(
            predictions_path,
            item_id,
            verification,
            source_item=active_item,
        )
        if stored_verification:
            verifications = updated_item.get("verifications")
            if not isinstance(verifications, list):
                verifications = []
            verifications.append(stored_verification)
            updated_item["verifications"] = verifications

        update_verify_modal_item(verify_data_cache_key, updated_item)
        patch = Patch()
        patch["items"][active_item_index] = updated_item
        next_summary = get_verify_modal_summary(verify_data_cache_key)
        if isinstance(next_summary, dict):
            patch["summary"] = next_summary
        direct_ui_updates = build_verify_card_ui_updates(
            item_id,
            updated_item,
            label_block_ids,
            save_button_ids,
            predicted_labels=predicted_labels,
            pending=False,
        )
        return patch, no_update, no_update, no_update, *direct_ui_updates

    @app.callback(
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-item-actions", "children", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("verify-modal-synced-item-ids-store", "data", allow_duplicate=True),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Output({"type": "verify-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Input({"type": "modal-action-confirm", "scope": ALL}, "n_clicks"),
        State("modal-item-store", "data"),
        State("verify-thresholds-store", "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "id"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State("verify-modal-synced-item-ids-store", "data"),
        State("modal-active-box-label", "data"),
        State({"type": "verify-label-block", "item_id": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        prevent_initial_call=True,
    )
    def confirm_modal_verification(
        modal_confirm_clicks_list,
        modal_item,
        thresholds,
        actions_list,
        actions_ids,
        modal_bbox_store,
        profile,
        verify_data_cache_key,
        pending_sync_item_ids,
        active_box_label,
        label_block_ids,
        save_button_ids,
    ):
        if not modal_confirm_clicks_list or not any(modal_confirm_clicks_list):
            raise PreventUpdate
        if not isinstance(modal_item, dict):
            raise PreventUpdate

        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate

        _require_complete_profile(profile, "confirm_verification")

        item = modal_item
        predictions = item.get("predictions") or {}
        annotations = item.get("annotations") or {}
        thresholds = thresholds or {"__global__": 0.5}
        threshold_used = float(thresholds.get("__global__", 0.5))
        _, _, active_labels = _get_modal_label_sets(item, "verify", thresholds)
        labels_to_confirm = list(active_labels or [])

        box_extent_map = {}
        box_extent_lists = {}
        box_annotation_lists = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
            modal_boxes = modal_bbox_store.get("boxes") or []
            box_extent_map = _extract_label_extent_map_from_boxes(modal_boxes)
            box_extent_lists = _extract_label_extent_list_map_from_boxes(modal_boxes)
            box_annotation_lists = extract_box_annotation_list_map_from_boxes(modal_boxes)
        else:
            modal_boxes = _build_modal_boxes_from_item(item)
            box_extent_map = _extract_label_extent_map_from_boxes(modal_boxes)
            box_extent_lists = _extract_label_extent_list_map_from_boxes(modal_boxes)
            box_annotation_lists = extract_box_annotation_list_map_from_boxes(modal_boxes)

        if box_extent_lists:
            ordered = list(labels_to_confirm or [])
            seen = set(ordered)
            for label in box_extent_lists.keys():
                if label not in seen:
                    ordered.append(label)
                    seen.add(label)
            labels_to_confirm = ordered

        predictions_path = (item.get("metadata") or {}).get("predictions_path")
        if not predictions_path:
            predictions_path = ((item.get("metadata") or {}).get("predictions_file") or "").strip()

        predicted_labels = _filter_predictions(predictions, thresholds)
        predicted_set = set(predicted_labels)
        labels_set = set(labels_to_confirm)

        model_scores = {}
        model_extent_map = {}
        model_outputs = predictions.get("model_outputs")
        if model_outputs and isinstance(model_outputs, list):
            for out in model_outputs:
                label = out.get("class_hierarchy")
                score = out.get("score")
                if label and isinstance(score, (int, float)):
                    model_scores[label] = score
                if label:
                    cleaned_extent = _clean_annotation_extent(out.get("annotation_extent"))
                    if cleaned_extent:
                        model_extent_map[label] = cleaned_extent
        else:
            probs = predictions.get("confidence") or {}
            for label, score in probs.items():
                if isinstance(score, (int, float)):
                    model_scores[label] = score

        item_actions = []
        for i, action_id in enumerate(actions_ids or []):
            if action_id.get("filename") == item_id:
                item_actions = (actions_list or [])[i] or []
                break
        last_add_threshold = {}
        last_remove_threshold = {}
        for action in item_actions:
            label = action.get("label")
            threshold_value = action.get("threshold_used")
            if not label or threshold_value is None:
                continue
            if action.get("action") == "add":
                last_add_threshold[label] = threshold_value
            elif action.get("action") == "remove":
                last_remove_threshold[label] = threshold_value

        rejected_labels = set(_get_item_rejected_labels(item))
        for label in predicted_labels:
            if label not in labels_set:
                rejected_labels.add(label)
        for label, removed_threshold in last_remove_threshold.items():
            score = model_scores.get(label)
            if score is not None and score >= float(removed_threshold):
                rejected_labels.add(label)
        for label in labels_to_confirm:
            rejected_labels.discard(label)

        label_decisions = []
        for label in labels_to_confirm:
            decision = "accepted" if label in predicted_set else "added"
            threshold_for_label = float(last_add_threshold.get(label, threshold_used))
            entry = {
                "label": label,
                "decision": decision,
                "threshold_used": threshold_for_label,
            }
            box_annotations = box_annotation_lists.get(label) or []
            label_extents = box_extent_lists.get(label) or []
            _attach_box_metadata(
                entry,
                box_annotations=box_annotations,
                label_extents=label_extents,
                model_extent_map=model_extent_map,
            )
            label_decisions.append(entry)
            for idx, extra_extent in enumerate(label_extents[1:], start=1):
                if not isinstance(extra_extent, dict):
                    continue
                extra_entry = {
                    "label": label,
                    "decision": decision,
                    "threshold_used": threshold_for_label,
                    "annotation_extent": extra_extent,
                }
                extra_box = box_annotations[idx] if idx < len(box_annotations) else None
                if isinstance(extra_box, dict) and extra_box.get("tag"):
                    extra_entry["tag"] = extra_box["tag"]
                label_decisions.append(extra_entry)
        for label in sorted(rejected_labels - labels_set):
            entry = {
                "label": label,
                "decision": "rejected",
                "threshold_used": float(last_remove_threshold.get(label, threshold_used)),
            }
            label_extents = box_extent_lists.get(label) or []
            extent = model_extent_map.get(label) or (label_extents[0] if label_extents else box_extent_map.get(label))
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)

        profile_name = _profile_actor(profile)
        note_text = annotations.get("notes", "") if isinstance(annotations, dict) else ""
        verification = {
            "verified_at": datetime.now().isoformat(),
            "verified_by": profile_name or "anonymous",
            "label_decisions": label_decisions,
            "verification_status": "verified",
            "notes": note_text,
        }

        updated_item = _update_item_labels(
            {"items": [item]},
            item_id,
            labels_to_confirm,
            mode="verify",
            user_name=profile_name,
            is_reverification=True,
            label_extents=box_extent_map or None,
            bbox_annotations=[
                annotation
                for annotations_for_label in box_annotation_lists.values()
                for annotation in annotations_for_label
            ],
        )
        updated_item = next(
            (
                entry
                for entry in (updated_item or {}).get("items", [])
                if isinstance(entry, dict) and entry.get("item_id") == item_id
            ),
            None,
        )
        if not isinstance(updated_item, dict):
            raise PreventUpdate

        annotations_obj = updated_item.get("annotations") or {}
        annotations_obj["rejected_labels"] = sorted(rejected_labels)
        updated_item["annotations"] = annotations_obj

        stored_verification = save_verify_predictions(
            predictions_path,
            item_id,
            verification,
            source_item=item,
        )
        if stored_verification:
            verifications = updated_item.get("verifications")
            if not isinstance(verifications, list):
                verifications = []
            verifications.append(stored_verification)
            updated_item["verifications"] = verifications

        active_item_index = update_verify_modal_item(verify_data_cache_key, updated_item)
        verify_store_update = no_update

        snapshot_boxes = modal_boxes if modal_boxes else _build_modal_boxes_from_item(updated_item)
        next_pending_ids = [value for value in (pending_sync_item_ids or []) if isinstance(value, str) and value]
        if active_item_index is not None:
            next_pending_ids = [value for value in next_pending_ids if value != item_id]
        elif item_id not in next_pending_ids:
            next_pending_ids.append(item_id)
        direct_ui_updates = build_verify_card_ui_updates(
            item_id,
            updated_item,
            label_block_ids,
            save_button_ids,
            predicted_labels=predicted_labels,
            pending=False,
        )
        modal_actions_update = _build_modal_item_actions(
            updated_item,
            "verify",
            thresholds,
            boxes=snapshot_boxes,
            active_box_label=active_box_label,
        )

        return (
            {"dirty": False, "item_id": item_id},
            _modal_snapshot_payload("verify", item_id, updated_item, snapshot_boxes),
            updated_item,
            modal_actions_update,
            verify_store_update,
            next_pending_ids,
            False,
            *direct_ui_updates,
        )

    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("verify-modal-synced-item-ids-store", "data", allow_duplicate=True),
        Input("image-modal", "is_open"),
        State("verify-modal-synced-item-ids-store", "data"),
        State("verify-data-cache-key-store", "data"),
        prevent_initial_call=True,
    )
    def sync_saved_modal_items_to_verify_store(is_open, pending_sync_item_ids, verify_data_cache_key):
        if is_open:
            raise PreventUpdate
        pending_ids = [item_id for item_id in (pending_sync_item_ids or []) if isinstance(item_id, str) and item_id]
        if not pending_ids:
            raise PreventUpdate

        patch = Patch()
        any_updated = False
        for item_id in pending_ids:
            item_index = get_verify_modal_item_index(verify_data_cache_key, item_id)
            updated_item = get_verify_modal_item(verify_data_cache_key, item_id)
            if item_index is None or not isinstance(updated_item, dict):
                continue
            patch["items"][item_index] = updated_item
            any_updated = True

        summary = get_verify_modal_summary(verify_data_cache_key)
        if isinstance(summary, dict):
            patch["summary"] = summary
            any_updated = True

        if not any_updated:
            raise PreventUpdate
        return patch, []
