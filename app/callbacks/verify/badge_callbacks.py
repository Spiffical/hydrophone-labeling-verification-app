"""Quick badge accept/reject/delete callback registration."""

import json
from copy import deepcopy
from datetime import datetime

from dash import ALL, Input, Output, Patch, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.verify.badge_helpers import (
    action_from_action_type,
    apply_action_to_labels,
    box_annotations_after_label_action,
    clean_label_extents_from_annotations,
    flatten_callback_inputs,
    resolve_trigger_payload,
    resolve_trigger_timestamp,
    review_states_match,
    timestamp_summary,
    update_boxes_and_extents_for_action,
)
from app.callbacks.verify.ui_update_helpers import build_verify_card_ui_updates
from app.services.verify_modal_cache import (
    get_verify_modal_baseline_item,
    get_verify_modal_item,
    get_verify_modal_item_index,
    get_verify_modal_summary,
    update_verify_modal_item,
)


def register_verify_badge_callbacks(
    app,
    *,
    _require_complete_profile,
    _filter_predictions,
    _clean_annotation_extent,
    _extract_label_extent_map_from_boxes,
    _get_modal_label_sets,
    _parse_verify_target,
    _profile_actor,
    _build_modal_boxes_from_item,
    _build_modal_item_actions,
    _get_item_rejected_labels,
    _item_action_key,
    _ordered_unique_labels,
    _verify_badge_debug,
):
    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("verify-badge-event-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-item-actions", "children", allow_duplicate=True),
        Output({"type": "verify-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Input({"type": "verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-accept", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        State("verify-thresholds-store", "data"),
        State("current-filename", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("verify-badge-event-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State("modal-active-box-label", "data"),
        State({"type": "verify-label-block", "item_id": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        prevent_initial_call=True,
    )
    def quick_update_verify_labels(
        card_accept_ts,
        card_reject_ts,
        card_delete_ts,
        card_accept_ts_legacy,
        card_reject_ts_legacy,
        card_delete_ts_legacy,
        thresholds,
        modal_item_id,
        modal_bbox_store,
        profile,
        badge_event_store,
        verify_data_cache_key,
        active_box_label,
        label_block_ids,
        save_button_ids,
    ):
        _verify_badge_debug(
            "start",
            triggered_id=ctx.triggered_id,
            triggered=ctx.triggered,
            modal_item_id=modal_item_id,
            verify_cache_key=verify_data_cache_key,
            modal_bbox_item_id=(modal_bbox_store or {}).get("item_id") if isinstance(modal_bbox_store, dict) else None,
            timestamp_summary=timestamp_summary(
                card_accept_ts=card_accept_ts,
                card_reject_ts=card_reject_ts,
                card_delete_ts=card_delete_ts,
                card_accept_ts_legacy=card_accept_ts_legacy,
                card_reject_ts_legacy=card_reject_ts_legacy,
                card_delete_ts_legacy=card_delete_ts_legacy,
                modal_accept_ts=[],
                modal_reject_ts=[],
                modal_delete_ts=[],
                modal_accept_ts_legacy=[],
                modal_reject_ts_legacy=[],
                modal_delete_ts_legacy=[],
            ),
            last_event_store=badge_event_store,
        )
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            _verify_badge_debug("prevent_missing_triggered_id", triggered_id=triggered)
            raise PreventUpdate

        action_type = (triggered.get("type") or "").strip()
        if action_type not in {
            "verify-label-accept",
            "verify-label-reject",
            "verify-label-delete",
            "modal-verify-label-accept",
            "modal-verify-label-reject",
            "modal-verify-label-delete",
        }:
            _verify_badge_debug("prevent_unknown_action_type", action_type=action_type, triggered=triggered)
            raise PreventUpdate

        input_entries = flatten_callback_inputs(ctx.inputs_list)
        triggered_key_json = json.dumps(triggered, sort_keys=True, ensure_ascii=True)
        triggered_value = resolve_trigger_timestamp(
            input_entries=input_entries,
            triggered=triggered,
        )
        if triggered_value is None:
            _verify_badge_debug(
                "prevent_no_timestamp_for_trigger",
                triggered=triggered,
                inputs_count=len(input_entries),
            )
            raise PreventUpdate

        selected_key = f"{triggered_value}|{triggered_key_json}"
        last_key = (badge_event_store or {}).get("last_key") if isinstance(badge_event_store, dict) else ""
        if selected_key == last_key:
            _verify_badge_debug("prevent_duplicate_event", selected_key=selected_key)
            raise PreventUpdate

        item_key, item_id, label, target = resolve_trigger_payload(
            triggered=triggered,
            action_type=action_type,
            modal_item_id=modal_item_id,
            parse_verify_target=_parse_verify_target,
        )
        _verify_badge_debug(
            "resolved_trigger_payload",
            action_type=action_type,
            target=target,
            triggered=triggered,
            triggered_value=triggered_value,
        )

        if not item_id:
            _verify_badge_debug("prevent_missing_item_id", action_type=action_type, target=target, triggered=triggered)
            raise PreventUpdate
        if not label:
            _verify_badge_debug("prevent_missing_label", action_type=action_type, target=target, triggered=triggered)
            raise PreventUpdate

        _require_complete_profile(profile, "quick_update_verify_labels")

        action = action_from_action_type(action_type)
        _verify_badge_debug("resolved_action", action=action, item_id=item_id, label=label, modal_item_id=modal_item_id)
        thresholds = thresholds or {"__global__": 0.5}
        active_item = get_verify_modal_item(verify_data_cache_key, item_id)
        baseline_item = get_verify_modal_baseline_item(verify_data_cache_key, item_id)
        active_item_index = get_verify_modal_item_index(verify_data_cache_key, item_id)
        if not isinstance(active_item, dict):
            _verify_badge_debug(
                "prevent_item_not_found",
                item_id=item_id,
                item_key=item_key,
                verify_cache_key=verify_data_cache_key,
            )
            raise PreventUpdate
        if active_item_index is None:
            _verify_badge_debug("prevent_item_index_not_found", item_id=item_id, verify_cache_key=verify_data_cache_key)
            raise PreventUpdate
        item_id = (active_item.get("item_id") or item_id).strip()
        if not item_id:
            _verify_badge_debug("prevent_active_item_missing_id", item_key=item_key)
            raise PreventUpdate

        predicted_labels = _filter_predictions(active_item.get("predictions") or {}, thresholds)
        predicted_set = set(predicted_labels)
        _, _, active_labels = _get_modal_label_sets(active_item, "verify", thresholds)
        updated_labels = _ordered_unique_labels(active_labels)
        rejected_set = set(_get_item_rejected_labels(active_item))
        _verify_badge_debug(
            "before_update",
            item_id=item_id,
            label=label,
            action=action,
            predicted_labels=sorted(predicted_set),
            active_labels=updated_labels,
            rejected_labels=sorted(rejected_set),
        )
        updated_labels, rejected_set = apply_action_to_labels(
            action=action,
            label=label,
            updated_labels=updated_labels,
            predicted_set=predicted_set,
            rejected_set=rejected_set,
        )

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        label_extents = clean_label_extents_from_annotations(
            annotations_obj=annotations_obj,
            clean_annotation_extent=_clean_annotation_extent,
        )
        next_bbox_store, label_extents = update_boxes_and_extents_for_action(
            action=action,
            label=label,
            item_id=item_id,
            modal_item_id=modal_item_id,
            modal_bbox_store=modal_bbox_store,
            active_item=active_item,
            build_modal_boxes_from_item=_build_modal_boxes_from_item,
            extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
            label_extents=label_extents,
        )

        profile_name = _profile_actor(profile)
        annotations_update = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {
            "labels": [],
            "annotated_by": None,
            "annotated_at": None,
            "verified": False,
            "notes": "",
        }
        box_annotations = box_annotations_after_label_action(
            action=action,
            label=label,
            annotations_obj=annotations_update,
            next_bbox_store=next_bbox_store,
        )
        annotations_update["labels"] = updated_labels
        annotations_update["label_extents"] = label_extents
        if box_annotations:
            annotations_update["box_annotations"] = box_annotations
        else:
            annotations_update.pop("box_annotations", None)
        annotations_update["rejected_labels"] = sorted(rejected_set)
        annotations_update["annotated_at"] = datetime.now().isoformat()
        annotations_update["has_manual_review"] = True
        if annotations_update.get("verified"):
            annotations_update["needs_reverify"] = True
        annotations_update["pending_save"] = True
        if profile_name:
            annotations_update["annotated_by"] = profile_name
        active_item["annotations"] = annotations_update
        reverted_to_baseline = review_states_match(active_item, baseline_item)
        if reverted_to_baseline:
            active_item = deepcopy(baseline_item)
            if item_id == (modal_item_id or ""):
                next_bbox_store = {
                    "item_id": item_id,
                    "boxes": _build_modal_boxes_from_item(active_item),
                }
        update_verify_modal_item(verify_data_cache_key, active_item)
        updated_data = Patch()
        updated_data["items"][active_item_index] = active_item
        summary_obj = get_verify_modal_summary(verify_data_cache_key)
        if isinstance(summary_obj, dict):
            updated_data["summary"] = summary_obj

        pending = not reverted_to_baseline
        unsaved_update = (
            {"dirty": pending, "item_id": item_id}
            if item_id == (modal_item_id or "")
            else no_update
        )
        _verify_badge_debug(
            "return_update",
            item_id=item_id,
            item_key=item_key,
            label=label,
            action=action,
            labels_after=updated_labels,
            rejected_after=sorted(rejected_set),
            next_bbox_store_item=(next_bbox_store or {}).get("item_id") if isinstance(next_bbox_store, dict) else None,
            unsaved_update=unsaved_update,
            event_key=selected_key,
        )
        updated_modal_item = active_item if item_id == (modal_item_id or "") else no_update
        modal_actions_update = no_update
        if item_id == (modal_item_id or ""):
            modal_actions_update = _build_modal_item_actions(
                active_item,
                "verify",
                thresholds,
                boxes=(next_bbox_store or {}).get("boxes") if isinstance(next_bbox_store, dict) else [],
                active_box_label=active_box_label,
            )
        direct_ui_updates = build_verify_card_ui_updates(
            item_id,
            active_item,
            label_block_ids,
            save_button_ids,
            predicted_labels=predicted_labels,
            pending=pending,
        )
        return (
            updated_data,
            next_bbox_store,
            unsaved_update,
            {"last_key": selected_key},
            updated_modal_item,
            modal_actions_update,
            *direct_ui_updates,
        )

    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("verify-badge-event-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-item-actions", "children", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output({"type": "verify-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Input({"type": "modal-verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "label": ALL}, "n_clicks_timestamp"),
        State("modal-item-store", "data"),
        State("verify-thresholds-store", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("verify-badge-event-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State("modal-active-box-label", "data"),
        State({"type": "verify-label-block", "item_id": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        prevent_initial_call=True,
    )
    def quick_update_modal_verify_labels(
        modal_accept_ts,
        modal_reject_ts,
        modal_delete_ts,
        modal_accept_ts_legacy,
        modal_reject_ts_legacy,
        modal_delete_ts_legacy,
        modal_item,
        thresholds,
        modal_bbox_store,
        profile,
        badge_event_store,
        verify_data_cache_key,
        active_box_label,
        label_block_ids,
        save_button_ids,
    ):
        _verify_badge_debug(
            "modal_start",
            triggered_id=ctx.triggered_id,
            triggered=ctx.triggered,
            modal_item_id=(modal_item or {}).get("item_id") if isinstance(modal_item, dict) else None,
            modal_bbox_item_id=(modal_bbox_store or {}).get("item_id") if isinstance(modal_bbox_store, dict) else None,
            timestamp_summary=timestamp_summary(
                card_accept_ts=[],
                card_reject_ts=[],
                card_delete_ts=[],
                card_accept_ts_legacy=[],
                card_reject_ts_legacy=[],
                card_delete_ts_legacy=[],
                modal_accept_ts=modal_accept_ts,
                modal_reject_ts=modal_reject_ts,
                modal_delete_ts=modal_delete_ts,
                modal_accept_ts_legacy=modal_accept_ts_legacy,
                modal_reject_ts_legacy=modal_reject_ts_legacy,
                modal_delete_ts_legacy=modal_delete_ts_legacy,
            ),
            last_event_store=badge_event_store,
        )
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate

        action_type = (triggered.get("type") or "").strip()
        if action_type not in {
            "modal-verify-label-accept",
            "modal-verify-label-reject",
            "modal-verify-label-delete",
        }:
            raise PreventUpdate

        if not isinstance(modal_item, dict):
            raise PreventUpdate
        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate

        input_entries = flatten_callback_inputs(ctx.inputs_list)
        triggered_key_json = json.dumps(triggered, sort_keys=True, ensure_ascii=True)
        triggered_value = resolve_trigger_timestamp(
            input_entries=input_entries,
            triggered=triggered,
        )
        if triggered_value is None:
            raise PreventUpdate

        selected_key = f"{triggered_value}|{triggered_key_json}"
        last_key = (badge_event_store or {}).get("last_key") if isinstance(badge_event_store, dict) else ""
        if selected_key == last_key:
            raise PreventUpdate

        _, _, label, target = resolve_trigger_payload(
            triggered=triggered,
            action_type=action_type,
            modal_item_id=item_id,
            parse_verify_target=_parse_verify_target,
        )
        if not label:
            _verify_badge_debug("modal_prevent_missing_label", action_type=action_type, target=target, triggered=triggered)
            raise PreventUpdate

        _require_complete_profile(profile, "quick_update_verify_labels")

        active_item = deepcopy(modal_item)
        baseline_item = get_verify_modal_baseline_item(verify_data_cache_key, item_id)
        thresholds = thresholds or {"__global__": 0.5}
        predicted_labels = _filter_predictions(active_item.get("predictions") or {}, thresholds)
        predicted_set = set(predicted_labels)
        _, _, active_labels = _get_modal_label_sets(active_item, "verify", thresholds)
        updated_labels = _ordered_unique_labels(active_labels)
        rejected_set = set(_get_item_rejected_labels(active_item))
        action = action_from_action_type(action_type)
        updated_labels, rejected_set = apply_action_to_labels(
            action=action,
            label=label,
            updated_labels=updated_labels,
            predicted_set=predicted_set,
            rejected_set=rejected_set,
        )

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        label_extents = clean_label_extents_from_annotations(
            annotations_obj=annotations_obj,
            clean_annotation_extent=_clean_annotation_extent,
        )
        next_bbox_store, label_extents = update_boxes_and_extents_for_action(
            action=action,
            label=label,
            item_id=item_id,
            modal_item_id=item_id,
            modal_bbox_store=modal_bbox_store,
            active_item=active_item,
            build_modal_boxes_from_item=_build_modal_boxes_from_item,
            extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
            label_extents=label_extents,
        )

        profile_name = _profile_actor(profile)
        annotations_update = deepcopy(annotations_obj) if isinstance(annotations_obj, dict) else {}
        box_annotations = box_annotations_after_label_action(
            action=action,
            label=label,
            annotations_obj=annotations_update,
            next_bbox_store=next_bbox_store,
        )
        annotations_update["labels"] = updated_labels
        annotations_update["label_extents"] = label_extents
        if box_annotations:
            annotations_update["box_annotations"] = box_annotations
        else:
            annotations_update.pop("box_annotations", None)
        annotations_update["rejected_labels"] = sorted(rejected_set)
        annotations_update["annotated_at"] = datetime.now().isoformat()
        annotations_update["has_manual_review"] = True
        annotations_update["pending_save"] = True
        if annotations_update.get("verified"):
            annotations_update["needs_reverify"] = True
        if profile_name:
            annotations_update["annotated_by"] = profile_name
        active_item["annotations"] = annotations_update

        reverted_to_baseline = review_states_match(active_item, baseline_item)
        if reverted_to_baseline:
            active_item = deepcopy(baseline_item)
            next_bbox_store = {
                "item_id": item_id,
                "boxes": _build_modal_boxes_from_item(active_item),
            }

        update_verify_modal_item(verify_data_cache_key, active_item)

        direct_ui_updates = build_verify_card_ui_updates(
            item_id,
            active_item,
            label_block_ids,
            save_button_ids,
            predicted_labels=predicted_labels,
            pending=not reverted_to_baseline,
        )
        modal_actions_update = _build_modal_item_actions(
            active_item,
            "verify",
            thresholds,
            boxes=(next_bbox_store or {}).get("boxes") if isinstance(next_bbox_store, dict) else [],
            active_box_label=active_box_label,
        )
        _verify_badge_debug(
            "modal_return_update",
            item_id=item_id,
            label=label,
            action=action,
            labels_after=updated_labels,
            rejected_after=sorted(rejected_set),
            next_bbox_store_item=(next_bbox_store or {}).get("item_id") if isinstance(next_bbox_store, dict) else None,
            event_key=selected_key,
        )
        return (
            next_bbox_store,
            {"dirty": not reverted_to_baseline, "item_id": item_id},
            {"last_key": selected_key},
            active_item,
            modal_actions_update,
            no_update,
            *direct_ui_updates,
        )
