"""Verification confirm/save callback registration."""

from datetime import datetime

from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.utils.persistence import save_verify_predictions


def register_verify_confirm_callbacks(
    app,
    *,
    _require_complete_profile,
    _filter_predictions,
    _clean_annotation_extent,
    _extract_label_extent_list_map_from_boxes,
    _extract_label_extent_map_from_boxes,
    _get_modal_label_sets,
    _profile_actor,
    _update_item_labels,
    _build_modal_boxes_from_item,
    _modal_snapshot_payload,
):
    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Input({"type": "confirm-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-action-confirm", "scope": ALL}, "n_clicks"),
        State("current-filename", "data"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "id"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_verification(
        n_clicks_list,
        modal_confirm_clicks_list,
        modal_item_id,
        data,
        thresholds,
        actions_list,
        actions_ids,
        modal_bbox_store,
        profile,
    ):
        _require_complete_profile(profile, "confirm_verification")

        triggered = ctx.triggered_id
        if isinstance(triggered, dict) and triggered.get("type") == "modal-action-confirm":
            if not modal_confirm_clicks_list or not any(modal_confirm_clicks_list) or not modal_item_id:
                raise PreventUpdate
            item_id = modal_item_id
        else:
            if not n_clicks_list or not any(n_clicks_list):
                raise PreventUpdate
            if not isinstance(triggered, dict) or "item_id" not in triggered:
                raise PreventUpdate
            item_id = triggered["item_id"]

        items = (data or {}).get("items", [])
        labels_to_confirm = []
        predictions = {}
        predictions_path = None
        annotations = {}
        thresholds = thresholds or {"__global__": 0.5}
        threshold_used = float(thresholds.get("__global__", 0.5))
        for item in items:
            if item.get("item_id") == item_id:
                annotations = item.get("annotations") or {}
                predictions = item.get("predictions") or {}
                predictions_path = (item.get("metadata") or {}).get("predictions_path")
                _, _, active_labels = _get_modal_label_sets(item, "verify", thresholds)
                labels_to_confirm = list(active_labels or [])
                break

        box_extent_map = {}
        box_extent_lists = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
            modal_boxes = modal_bbox_store.get("boxes") or []
            box_extent_map = _extract_label_extent_map_from_boxes(modal_boxes)
            box_extent_lists = _extract_label_extent_list_map_from_boxes(modal_boxes)

        if box_extent_lists:
            ordered = list(labels_to_confirm or [])
            seen = set(ordered)
            for label in box_extent_lists.keys():
                if label not in seen:
                    ordered.append(label)
                    seen.add(label)
            labels_to_confirm = ordered

        if not predictions_path:
            summary_pred = (data or {}).get("summary", {}).get("predictions_file")
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

        rejected_labels = set()
        for label in predicted_labels:
            if label not in labels_set:
                rejected_labels.add(label)
        for label, removed_threshold in last_remove_threshold.items():
            score = model_scores.get(label)
            if score is not None and score >= float(removed_threshold):
                rejected_labels.add(label)

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
                        "threshold_used": threshold_for_label,
                        "annotation_extent": extra_extent,
                    }
                )
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
            data or {},
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
            annotations_obj = item.get("annotations") or {}
            annotations_obj["rejected_labels"] = sorted(rejected_labels)
            item["annotations"] = annotations_obj
            break

        stored_verification = save_verify_predictions(predictions_path, item_id, verification)
        if stored_verification:
            for item in (updated or {}).get("items", []):
                if item.get("item_id") == item_id:
                    verifications = item.get("verifications")
                    if not isinstance(verifications, list):
                        verifications = []
                    verifications.append(stored_verification)
                    item["verifications"] = verifications
                    break
        dirty_update = no_update
        snapshot_update = no_update
        if modal_item_id and modal_item_id == item_id:
            dirty_update = {"dirty": False, "item_id": item_id}
            updated_item = next(
                (item for item in (updated or {}).get("items", []) if isinstance(item, dict) and item.get("item_id") == item_id),
                None,
            )
            if isinstance(updated_item, dict):
                if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
                    snapshot_boxes = modal_bbox_store.get("boxes") or []
                else:
                    snapshot_boxes = _build_modal_boxes_from_item(updated_item)
                snapshot_update = _modal_snapshot_payload("verify", item_id, updated_item, snapshot_boxes)

        return updated, dirty_update, snapshot_update

