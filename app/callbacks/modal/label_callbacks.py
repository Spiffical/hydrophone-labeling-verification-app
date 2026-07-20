"""Modal label callbacks: activate add-box target and delete label flows."""

from copy import deepcopy
from time import time_ns

from dash import ALL, ClientsideFunction, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.services.verify_modal_cache import get_verify_modal_item, get_verify_modal_summary


def _resolve_modal_delete_active_item(items, current_item_id, modal_item):
    active_item = next((item for item in items if item and item.get("item_id") == current_item_id), None)
    if not active_item:
        return None
    if isinstance(modal_item, dict) and modal_item.get("item_id") == current_item_id:
        active_item = deepcopy(modal_item)
        for index, item in enumerate(items):
            if isinstance(item, dict) and item.get("item_id") == current_item_id:
                items[index] = active_item
                break
    return active_item


def register_modal_label_callbacks(
    app,
    *,
    _require_complete_profile,
    _get_mode_data,
    _get_modal_label_sets,
    _profile_actor,
    _extract_box_annotations_from_boxes,
    _extract_label_extent_map_from_boxes,
    _update_item_labels,
    _get_item_rejected_labels,
    _apply_modal_boxes_to_figure,
):
    app.clientside_callback(
        ClientsideFunction(namespace="bboxInteractions", function_name="activateDraw"),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-bbox-interaction-store", "data", allow_duplicate=True),
        Input({"type": "modal-label-add-box", "label": ALL}, "n_clicks"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        State("current-filename", "data"),
        State("modal-bbox-store", "data"),
        State("modal-item-store", "data"),
        State("modal-unsaved-store", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input({"type": "modal-label-delete-btn", "label": ALL}, "n_clicks"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("explore-data-store", "data"),
        State("modal-item-store", "data"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("verify-thresholds-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def delete_modal_label(
        delete_clicks,
        current_item_id,
        mode,
        label_data,
        explore_data,
        modal_item,
        bbox_store,
        figure,
        thresholds,
        verify_data_cache_key,
        profile,
    ):
        if not delete_clicks or all((clicks or 0) <= 0 for clicks in delete_clicks):
            raise PreventUpdate
        if not ctx.triggered:
            raise PreventUpdate

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        if not current_item_id:
            raise PreventUpdate

        label_to_delete = (triggered.get("label") or "").strip()
        if not label_to_delete:
            raise PreventUpdate

        mode = mode or "label"
        if mode == "explore":
            raise PreventUpdate
        _require_complete_profile(profile, "delete_modal_label")

        if mode == "verify":
            source_item = modal_item if (
                isinstance(modal_item, dict)
                and modal_item.get("item_id") == current_item_id
            ) else get_verify_modal_item(verify_data_cache_key, current_item_id)
            if not isinstance(source_item, dict):
                raise PreventUpdate
            data = {
                "items": [deepcopy(source_item)],
                "summary": get_verify_modal_summary(verify_data_cache_key) or {},
            }
        else:
            data = deepcopy(_get_mode_data(mode, label_data, None, explore_data))
        if not data:
            raise PreventUpdate

        items = data.get("items", [])
        active_item = _resolve_modal_delete_active_item(items, current_item_id, modal_item)
        if not active_item:
            raise PreventUpdate

        _, _, active_labels = _get_modal_label_sets(active_item, mode, thresholds or {"__global__": 0.5})
        active_label_set = {(label or "").strip() for label in active_labels if isinstance(label, str)}
        if label_to_delete not in active_label_set:
            raise PreventUpdate
        updated_labels = [
            label for label in active_labels
            if isinstance(label, str) and (label or "").strip() != label_to_delete
        ]

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {"item_id": current_item_id, "boxes": []}
        existing_boxes = store.get("boxes") if isinstance(store.get("boxes"), list) else []
        filtered_boxes = [
            box for box in existing_boxes
            if isinstance(box, dict) and (box.get("label") or "").strip() != label_to_delete
        ]
        store["item_id"] = current_item_id
        store["boxes"] = filtered_boxes

        profile_name = _profile_actor(profile)
        label_extents = _extract_label_extent_map_from_boxes(filtered_boxes)
        bbox_annotations = _extract_box_annotations_from_boxes(filtered_boxes)
        updated_data = _update_item_labels(
            data,
            current_item_id,
            updated_labels,
            mode,
            user_name=profile_name,
            label_extents=label_extents,
            bbox_annotations=bbox_annotations,
        )
        if mode == "verify":
            current_rejected = set(_get_item_rejected_labels(active_item))
            current_rejected.add(label_to_delete)
            for entry in (updated_data or {}).get("items", []):
                if not isinstance(entry, dict) or entry.get("item_id") != current_item_id:
                    continue
                annotations_obj = entry.get("annotations") or {}
                annotations_obj["rejected_labels"] = sorted(current_rejected)
                entry["annotations"] = annotations_obj
                break

        updated_fig = _apply_modal_boxes_to_figure(
            deepcopy(figure) if isinstance(figure, dict) else {},
            filtered_boxes,
            revision_bump=time_ns(),
        )
        next_active_label = None
        unsaved_update = {"dirty": True, "item_id": current_item_id}
        updated_modal_item = None
        if isinstance(updated_data, dict):
            updated_modal_item = next(
                (
                    item
                    for item in (updated_data.get("items") or [])
                    if isinstance(item, dict) and item.get("item_id") == current_item_id
                ),
                None,
            )

        if mode == "label":
            return updated_data, no_update, no_update, updated_modal_item, store, updated_fig, next_active_label, unsaved_update
        if mode == "verify":
            return no_update, no_update, no_update, updated_modal_item, store, updated_fig, next_active_label, unsaved_update
        return no_update, no_update, updated_data, updated_modal_item, store, updated_fig, next_active_label, unsaved_update
