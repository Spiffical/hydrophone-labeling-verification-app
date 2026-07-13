"""Modal lifecycle callback for resolving unsaved-changes prompt actions."""

import time
from copy import deepcopy

from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.common.profile_guard import profile_actor
from app.callbacks.verify.ui_update_helpers import build_verify_card_ui_updates
from app.services.verify_modal_cache import (
    get_verify_modal_item,
    get_verify_modal_summary,
    update_verify_modal_item,
)
from app.services.verify_pagination import save_single_verify_item_change


def register_modal_lifecycle_unsaved_callbacks(
    app,
    *,
    _persist_modal_item_before_exit,
    _replace_item_in_data,
    _build_modal_item_actions,
    _filter_predictions,
):
    @app.callback(
        Output("unsaved-changes-modal", "is_open", allow_duplicate=True),
        Output("modal-pending-action-store", "data", allow_duplicate=True),
        Output("modal-force-action-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-item-actions", "children", allow_duplicate=True),
        Output({"type": "verify-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Input("unsaved-stay-btn", "n_clicks"),
        Input("unsaved-save-btn", "n_clicks"),
        Input("unsaved-discard-btn", "n_clicks"),
        State("modal-pending-action-store", "data"),
        State("modal-snapshot-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("explore-data-store", "data"),
        State("current-filename", "data"),
        State("modal-item-store", "data"),
        State("verify-thresholds-store", "data"),
        State("modal-bbox-store", "data"),
        State("modal-active-box-label", "data"),
        State("user-profile-store", "data"),
        State("label-output-input", "value"),
        State("config-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State({"type": "verify-label-block", "item_id": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        prevent_initial_call=True,
    )
    def resolve_unsaved_modal_action(
        stay_clicks,
        save_clicks,
        discard_clicks,
        pending_action,
        snapshot_store,
        mode,
        label_data,
        explore_data,
        current_item_id,
        modal_item,
        thresholds,
        bbox_store,
        active_box_label,
        profile,
        label_output_path,
        cfg,
        verify_data_cache_key,
        label_block_ids,
        save_button_ids,
    ):
        triggered = ctx.triggered_id
        if triggered == "unsaved-stay-btn":
            if not stay_clicks:
                raise PreventUpdate
            return (
                False,
                None,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )

        force_payload = no_update
        if isinstance(pending_action, dict) and pending_action.get("kind") in {"close", "open"}:
            force_payload = {
                "action": pending_action,
                "ts": time.time_ns(),
            }

        if triggered == "unsaved-save-btn":
            if not save_clicks:
                raise PreventUpdate
            dirty_update = {"dirty": False, "item_id": current_item_id}
            next_label_data = no_update
            next_verify_data = no_update
            next_explore_data = no_update
            updated_modal_item = no_update
            modal_actions_update = no_update
            direct_ui_updates = (no_update, no_update, no_update, no_update)

            if (mode or "").strip() == "verify":
                active_item = modal_item if isinstance(modal_item, dict) else None
                if not isinstance(active_item, dict) or active_item.get("item_id") != current_item_id:
                    active_item = get_verify_modal_item(verify_data_cache_key, current_item_id)
                if isinstance(active_item, dict):
                    summary = get_verify_modal_summary(verify_data_cache_key) or {}
                    updated_item, _ = save_single_verify_item_change(
                        active_item,
                        summary.get("predictions_file") if isinstance(summary, dict) else None,
                        thresholds or {"__global__": 0.5},
                        profile_actor(profile),
                    )
                    if isinstance(updated_item, dict):
                        update_verify_modal_item(verify_data_cache_key, updated_item)
                        updated_modal_item = updated_item
                        modal_actions_update = _build_modal_item_actions(
                            updated_item,
                            "verify",
                            thresholds or {"__global__": 0.5},
                            boxes=(bbox_store or {}).get("boxes") if isinstance(bbox_store, dict) else [],
                            active_box_label=active_box_label,
                            config=cfg,
                        )
                        direct_ui_updates = build_verify_card_ui_updates(
                            current_item_id,
                            updated_item,
                            label_block_ids,
                            save_button_ids,
                            predicted_labels=_filter_predictions(updated_item.get("predictions") or {}, thresholds),
                            pending=False,
                        )
            else:
                next_label_data, next_verify_data, next_explore_data = _persist_modal_item_before_exit(
                    mode=mode,
                    item_id=current_item_id,
                    label_data=label_data,
                    verify_data=None,
                    explore_data=explore_data,
                    thresholds=thresholds,
                    profile=profile,
                    bbox_store=bbox_store,
                    label_output_path=label_output_path,
                    cfg=cfg,
                )
            return (
                False,
                None,
                force_payload,
                dirty_update,
                updated_modal_item,
                next_label_data,
                next_verify_data,
                next_explore_data,
                no_update,
                modal_actions_update,
                *direct_ui_updates,
            )

        if triggered != "unsaved-discard-btn" or not discard_clicks:
            raise PreventUpdate

        restored_label_data = no_update
        restored_verify_data = no_update
        restored_explore_data = no_update
        restored_modal_item = no_update
        restored_bbox_store = no_update
        restored_modal_actions = no_update
        direct_ui_updates = (no_update, no_update, no_update, no_update)
        dirty_update = {"dirty": False, "item_id": current_item_id}

        snap = snapshot_store if isinstance(snapshot_store, dict) else {}
        snap_item_id = (snap.get("item_id") or "").strip()
        snap_item = snap.get("item")
        snap_boxes = snap.get("boxes")
        snap_mode = (snap.get("mode") or mode or "label").strip()

        if snap_item_id and isinstance(snap_item, dict):
            if snap_mode == "label":
                restored_label_data = _replace_item_in_data(label_data, snap_item_id, snap_item)
            elif snap_mode == "verify":
                update_verify_modal_item(verify_data_cache_key, snap_item)
                direct_ui_updates = build_verify_card_ui_updates(
                    snap_item_id,
                    snap_item,
                    label_block_ids,
                    save_button_ids,
                    predicted_labels=_filter_predictions(snap_item.get("predictions") or {}, thresholds),
                    pending=False,
                )
            elif snap_mode == "explore":
                restored_explore_data = _replace_item_in_data(explore_data, snap_item_id, snap_item)
            restored_bbox_store = {
                "item_id": snap_item_id,
                "boxes": deepcopy(snap_boxes) if isinstance(snap_boxes, list) else [],
            }
            restored_modal_item = snap_item
            restored_modal_actions = _build_modal_item_actions(
                snap_item,
                snap_mode,
                thresholds or {"__global__": 0.5},
                boxes=restored_bbox_store["boxes"],
                active_box_label=active_box_label,
                config=cfg,
            )
            dirty_update = {"dirty": False, "item_id": snap_item_id}

        return (
            False,
            None,
            force_payload,
            dirty_update,
            restored_modal_item,
            restored_label_data,
            restored_verify_data,
            restored_explore_data,
            restored_bbox_store,
            restored_modal_actions,
            *direct_ui_updates,
        )
