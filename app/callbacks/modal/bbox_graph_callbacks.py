"""Modal bbox callbacks for draw/edit events from graph relayout."""

import time
from copy import deepcopy

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.modal.bbox_graph_helpers import (
    extract_coord_updates,
    filter_payload_shapes,
    process_coord_updates,
    process_payload_shapes,
    resolve_add_mode,
)


def register_modal_bbox_graph_callbacks(
    app,
    *,
    _apply_modal_boxes_to_figure,
    _require_complete_profile,
    _parse_active_box_target,
    _bbox_debug,
    _bbox_debug_box_summary,
    _axis_meta_from_figure,
    _safe_float,
    _shape_to_extent,
    _extent_to_shape,
):
    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input("modal-image-graph", "relayoutData"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("modal-active-box-label", "data"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def update_modal_boxes_from_graph(
        relayout_data,
        bbox_store,
        figure,
        active_box_label,
        current_item_id,
        mode,
        profile,
    ):
        if not current_item_id or not relayout_data:
            raise PreventUpdate
        if mode == "explore":
            raise PreventUpdate
        _require_complete_profile(profile, "update_modal_boxes_from_graph")

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {}
        if store.get("item_id") != current_item_id:
            store = {"item_id": current_item_id, "boxes": []}
        boxes = deepcopy(store.get("boxes") or [])
        axis_meta = _axis_meta_from_figure(figure if isinstance(figure, dict) else {})

        chosen_label, allow_existing_label = _parse_active_box_target(active_box_label)
        _bbox_debug(
            "start",
            item_id=current_item_id,
            triggered=ctx.triggered_id,
            chosen_label=chosen_label,
            relayout_keys=sorted(relayout_data.keys()) if isinstance(relayout_data, dict) else [],
            relayout_data=relayout_data,
            boxes_before=_bbox_debug_box_summary(boxes),
        )

        if not isinstance(relayout_data, dict):
            raise PreventUpdate

        keys = set(relayout_data.keys())
        if keys and keys.issubset({"shapes[0].x0", "shapes[0].x1"}):
            _bbox_debug("ignore_playback_marker_update", keys=sorted(keys))
            raise PreventUpdate

        updated = False
        force_resync = False
        clear_active_label = False

        is_add_mode, existing_labels = resolve_add_mode(
            boxes=boxes,
            chosen_label=chosen_label,
            allow_existing_label=allow_existing_label,
        )

        _bbox_debug(
            "mode_decision",
            is_add_mode=is_add_mode,
            allow_existing_label=allow_existing_label,
            chosen_label=chosen_label,
            existing_labels=existing_labels,
        )

        payload_shapes = filter_payload_shapes(relayout_data)
        boxes, payload_updated, payload_resync, payload_clear_label = process_payload_shapes(
            payload_shapes=payload_shapes,
            boxes=boxes,
            is_add_mode=is_add_mode,
            chosen_label=chosen_label,
            axis_meta=axis_meta,
            safe_float=_safe_float,
            shape_to_extent=_shape_to_extent,
            extent_to_shape=_extent_to_shape,
            bbox_debug=_bbox_debug,
        )
        updated = updated or payload_updated
        force_resync = force_resync or payload_resync
        clear_active_label = clear_active_label or payload_clear_label

        coord_updates = extract_coord_updates(relayout_data=relayout_data, safe_float=_safe_float)
        boxes, coord_updated, coord_resync, coord_clear_label = process_coord_updates(
            coord_updates=coord_updates,
            boxes=boxes,
            is_add_mode=is_add_mode,
            chosen_label=chosen_label,
            axis_meta=axis_meta,
            extent_to_shape=_extent_to_shape,
            shape_to_extent=_shape_to_extent,
            bbox_debug=_bbox_debug,
        )
        updated = updated or coord_updated
        force_resync = force_resync or coord_resync
        clear_active_label = clear_active_label or coord_clear_label

        if not updated and not force_resync:
            _bbox_debug("no_update", boxes_after=_bbox_debug_box_summary(boxes))
            raise PreventUpdate

        store["item_id"] = current_item_id
        store["boxes"] = boxes
        updated_fig = _apply_modal_boxes_to_figure(
            deepcopy(figure) if isinstance(figure, dict) else {},
            boxes,
            revision_bump=(time.time_ns() if force_resync else None),
        )
        if clear_active_label and isinstance(updated_fig, dict):
            layout = updated_fig.get("layout")
            if not isinstance(layout, dict):
                layout = {}
            layout["dragmode"] = "pan"
            updated_fig["layout"] = layout

        if force_resync and not updated:
            _bbox_debug("return_resync_only", boxes_after=_bbox_debug_box_summary(boxes))

        _bbox_debug(
            "return_update",
            clear_active_label=clear_active_label,
            boxes_after=_bbox_debug_box_summary(boxes),
        )
        dirty_update = {"dirty": True, "item_id": current_item_id} if updated else no_update
        return store, updated_fig, (None if clear_active_label else no_update), dirty_update
