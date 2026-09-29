"""Species-label call-type attribute editing callbacks."""

from copy import deepcopy
from datetime import datetime, timezone

from dash import ALL, Input, Output, Patch, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.modal.actions_helpers import build_modal_item_actions
from app.callbacks.verify.ui_update_helpers import _replace_matching_id
from app.components.spectrogram_card import (
    create_label_label_block_children,
    create_verify_label_block_children,
)
from app.services.label_attributes import (
    replace_human_call_type_attributes,
    selected_human_attribute_values,
    supports_call_type_attributes,
)
from app.services.verification import get_modal_label_sets
from app.services.verify_modal_cache import (
    get_verify_modal_item_index,
    get_verify_modal_summary,
    update_verify_modal_item,
)


def _replace_all(ids, value):
    if not ids:
        return []
    return [value] * len(ids)


def _replace_matching_or_empty(ids, item_id, value):
    if not ids:
        return []
    return _replace_matching_id(ids, item_id, value)


def register_modal_label_attribute_callbacks(
    app,
    *,
    require_complete_profile,
    profile_actor,
    config,
):
    @app.callback(
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("label-data-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-item-actions", "children", allow_duplicate=True),
        Output({"type": "verify-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "label-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Output({"type": "label-save-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "label-save-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "label-save-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Output({"type": "modal-action-confirm", "scope": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "modal-action-confirm", "scope": ALL}, "color", allow_duplicate=True),
        Output({"type": "modal-action-confirm", "scope": ALL}, "outline", allow_duplicate=True),
        Output({"type": "modal-label-save", "scope": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "modal-label-save", "scope": ALL}, "color", allow_duplicate=True),
        Output({"type": "modal-label-save", "scope": ALL}, "outline", allow_duplicate=True),
        Input({"type": "modal-label-call-types", "item_id": ALL, "label": ALL}, "value"),
        State({"type": "modal-label-call-types", "item_id": ALL, "label": ALL}, "id"),
        State("modal-item-store", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State("label-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("modal-bbox-store", "data"),
        State("modal-active-box-label", "data"),
        State({"type": "verify-label-block", "item_id": ALL}, "id"),
        State({"type": "label-label-block", "item_id": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        State({"type": "label-save-btn", "item_id": ALL}, "id"),
        State({"type": "modal-action-confirm", "scope": ALL}, "id"),
        State({"type": "modal-label-save", "scope": ALL}, "id"),
        prevent_initial_call=True,
    )
    def update_label_call_types(
        selected_values,
        control_ids,
        modal_item,
        mode,
        profile,
        verify_cache_key,
        label_data,
        thresholds,
        bbox_store,
        active_box_label,
        verify_label_block_ids,
        label_label_block_ids,
        verify_save_ids,
        label_save_ids,
        modal_verify_save_ids,
        modal_label_save_ids,
    ):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or triggered.get("type") != "modal-label-call-types":
            raise PreventUpdate
        if mode not in {"verify", "label"} or not isinstance(modal_item, dict):
            raise PreventUpdate

        item_id = (triggered.get("item_id") or "").strip()
        taxonomy_label = (triggered.get("label") or "").strip()
        if item_id != (modal_item.get("item_id") or "").strip():
            raise PreventUpdate
        if not supports_call_type_attributes(taxonomy_label):
            raise PreventUpdate

        selected = []
        for index, control_id in enumerate(control_ids or []):
            if control_id == triggered:
                selected = (selected_values or [])[index] or []
                break
        if list(selected_human_attribute_values(modal_item, taxonomy_label)) == list(selected):
            raise PreventUpdate

        thresholds = thresholds or {"__global__": 0.5}
        predicted_labels, _, active_labels = get_modal_label_sets(modal_item, mode, thresholds)
        if taxonomy_label not in set(active_labels):
            raise PreventUpdate

        require_complete_profile(profile, "update_label_call_types")
        actor = profile_actor(profile)
        now = datetime.now(timezone.utc).isoformat()
        updated_item = deepcopy(modal_item)
        annotations = updated_item.get("annotations")
        annotations = deepcopy(annotations) if isinstance(annotations, dict) else {}
        annotations["label_attributes"] = replace_human_call_type_attributes(
            annotations.get("label_attributes"),
            taxonomy_label,
            selected,
            active_labels=active_labels,
            annotated_by=actor,
            annotated_at=now,
        )
        annotations["annotated_at"] = now
        annotations["has_manual_review"] = True
        annotations["pending_save"] = True
        if annotations.get("verified"):
            annotations["needs_reverify"] = True
        if actor:
            annotations["annotated_by"] = actor
        updated_item["annotations"] = annotations

        verify_update = no_update
        label_update = no_update
        if mode == "verify":
            item_index = get_verify_modal_item_index(verify_cache_key, item_id)
            if item_index is None:
                raise PreventUpdate
            update_verify_modal_item(verify_cache_key, updated_item)
            verify_patch = Patch()
            verify_patch["items"][item_index] = updated_item
            summary = get_verify_modal_summary(verify_cache_key)
            if isinstance(summary, dict):
                verify_patch["summary"] = summary
            verify_update = verify_patch
        else:
            items = (label_data or {}).get("items")
            if not isinstance(items, list):
                raise PreventUpdate
            item_index = next(
                (
                    index
                    for index, item in enumerate(items)
                    if isinstance(item, dict) and item.get("item_id") == item_id
                ),
                None,
            )
            if item_index is None:
                raise PreventUpdate
            label_patch = Patch()
            label_patch["items"][item_index] = updated_item
            label_update = label_patch

        boxes = (
            bbox_store.get("boxes") or []
            if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id
            else []
        )
        modal_actions = build_modal_item_actions(
            updated_item,
            mode,
            thresholds,
            boxes=boxes,
            active_box_label=active_box_label,
            config=config,
        )
        return (
            updated_item,
            verify_update,
            label_update,
            {"dirty": True, "item_id": item_id},
            modal_actions,
            _replace_matching_or_empty(
                verify_label_block_ids,
                item_id,
                create_verify_label_block_children(
                    item_id,
                    updated_item,
                    predicted_labels=predicted_labels,
                ),
            ),
            _replace_matching_or_empty(
                label_label_block_ids,
                item_id,
                create_label_label_block_children(item_id, updated_item, active_labels),
            ),
            _replace_matching_or_empty(verify_save_ids, item_id, False),
            _replace_matching_or_empty(verify_save_ids, item_id, "success"),
            _replace_matching_or_empty(verify_save_ids, item_id, False),
            _replace_matching_or_empty(label_save_ids, item_id, False),
            _replace_matching_or_empty(label_save_ids, item_id, "success"),
            _replace_matching_or_empty(label_save_ids, item_id, False),
            _replace_all(modal_verify_save_ids, False),
            _replace_all(modal_verify_save_ids, "success"),
            _replace_all(modal_verify_save_ids, False),
            _replace_all(modal_label_save_ids, False),
            _replace_all(modal_label_save_ids, "success"),
            _replace_all(modal_label_save_ids, False),
        )
