"""Modal bbox callbacks for inline delete button clicks on graph."""

import time
from copy import deepcopy

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate


def register_modal_bbox_inline_delete_callbacks(
    app,
    *,
    _apply_modal_boxes_to_figure,
    _require_complete_profile,
    _bbox_debug,
    _bbox_debug_box_summary,
    _BBOX_DELETE_TRACE_NAME,
):
    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input("modal-image-graph", "clickData"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def delete_modal_box_from_graph_click(
        click_data, bbox_store, figure, current_item_id, mode, profile
    ):
        if not current_item_id:
            raise PreventUpdate
        if mode == "explore":
            raise PreventUpdate
        _require_complete_profile(profile, "delete_modal_box_from_graph_click")

        def _coerce_int(value):
            if isinstance(value, bool) or value is None:
                return None
            if isinstance(value, (int, float)):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return None
                try:
                    return int(float(text))
                except (TypeError, ValueError):
                    return None
            return None

        points = click_data.get("points") if isinstance(click_data, dict) else None
        point = points[0] if isinstance(points, list) and points and isinstance(points[0], dict) else None
        curve_number = _coerce_int(point.get("curveNumber")) if isinstance(point, dict) else None
        custom_data = point.get("customdata") if isinstance(point, dict) else None
        _bbox_debug(
            "inline_delete_start",
            triggered=ctx.triggered_id,
            current_item_id=current_item_id,
            click_data=click_data,
            curve_number=curve_number,
            custom_data=custom_data,
        )
        if curve_number is None:
            raise PreventUpdate

        fig_data = figure.get("data") if isinstance(figure, dict) else None
        if not isinstance(fig_data, list) or curve_number < 0 or curve_number >= len(fig_data):
            raise PreventUpdate
        clicked_trace = fig_data[curve_number]
        if not isinstance(clicked_trace, dict) or clicked_trace.get("name") != _BBOX_DELETE_TRACE_NAME:
            raise PreventUpdate

        box_index = None
        if isinstance(custom_data, (int, float, str)):
            box_index = _coerce_int(custom_data)
        elif isinstance(custom_data, list) and custom_data:
            box_index = _coerce_int(custom_data[0])
        if box_index is None:
            _bbox_debug("inline_delete_missing_index", custom_data=custom_data)
            raise PreventUpdate

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {}
        if store.get("item_id") != current_item_id:
            raise PreventUpdate
        boxes = deepcopy(store.get("boxes") or [])
        if not boxes:
            raise PreventUpdate

        if not isinstance(box_index, int) or box_index < 0 or box_index >= len(boxes):
            _bbox_debug("inline_delete_stale_index_resync", box_index=box_index, total_boxes=len(boxes))
            updated_fig = _apply_modal_boxes_to_figure(
                deepcopy(figure) if isinstance(figure, dict) else {},
                boxes,
                revision_bump=time.time_ns(),
            )
            return store, updated_fig, no_update, no_update

        _bbox_debug("inline_delete_remove_index", box_index=box_index, box=boxes[box_index])
        boxes.pop(box_index)

        store["item_id"] = current_item_id
        store["boxes"] = boxes
        updated_fig = _apply_modal_boxes_to_figure(
            deepcopy(figure) if isinstance(figure, dict) else {}, boxes
        )
        if isinstance(updated_fig, dict):
            layout = updated_fig.get("layout")
            if not isinstance(layout, dict):
                layout = {}
            layout["dragmode"] = "pan"
            updated_fig["layout"] = layout
        _bbox_debug("inline_delete_return", boxes_after=_bbox_debug_box_summary(boxes))
        return store, updated_fig, no_update, {"dirty": True, "item_id": current_item_id}
