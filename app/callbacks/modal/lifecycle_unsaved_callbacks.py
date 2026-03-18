"""Modal lifecycle callback for resolving unsaved-changes prompt actions."""

import time
from copy import deepcopy

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate


def register_modal_lifecycle_unsaved_callbacks(
    app,
    *,
    _persist_modal_item_before_exit,
    _replace_item_in_data,
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
        Input("unsaved-stay-btn", "n_clicks"),
        Input("unsaved-save-btn", "n_clicks"),
        Input("unsaved-discard-btn", "n_clicks"),
        State("modal-pending-action-store", "data"),
        State("modal-snapshot-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("current-filename", "data"),
        State("verify-thresholds-store", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("label-output-input", "value"),
        State("config-store", "data"),
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
        verify_data,
        explore_data,
        current_item_id,
        thresholds,
        bbox_store,
        profile,
        label_output_path,
        cfg,
    ):
        triggered = ctx.triggered_id
        if triggered == "unsaved-stay-btn":
            if not stay_clicks:
                raise PreventUpdate
            return False, None, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        force_payload = no_update
        if isinstance(pending_action, dict) and pending_action.get("kind") in {"close", "open"}:
            force_payload = {
                "action": pending_action,
                "ts": time.time_ns(),
            }

        if triggered == "unsaved-save-btn":
            if not save_clicks:
                raise PreventUpdate
            next_label_data, next_verify_data, next_explore_data = _persist_modal_item_before_exit(
                mode=mode,
                item_id=current_item_id,
                label_data=label_data,
                verify_data=verify_data,
                explore_data=explore_data,
                thresholds=thresholds,
                profile=profile,
                bbox_store=bbox_store,
                label_output_path=label_output_path,
                cfg=cfg,
            )
            dirty_update = {"dirty": False, "item_id": current_item_id}
            return (
                False,
                None,
                force_payload,
                dirty_update,
                no_update,
                next_label_data,
                next_verify_data,
                next_explore_data,
                no_update,
            )

        if triggered != "unsaved-discard-btn" or not discard_clicks:
            raise PreventUpdate

        restored_label_data = no_update
        restored_verify_data = no_update
        restored_explore_data = no_update
        restored_modal_item = no_update
        restored_bbox_store = no_update
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
                restored_verify_data = _replace_item_in_data(verify_data, snap_item_id, snap_item)
            elif snap_mode == "explore":
                restored_explore_data = _replace_item_in_data(explore_data, snap_item_id, snap_item)
            restored_bbox_store = {
                "item_id": snap_item_id,
                "boxes": deepcopy(snap_boxes) if isinstance(snap_boxes, list) else [],
            }
            restored_modal_item = snap_item
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
        )
