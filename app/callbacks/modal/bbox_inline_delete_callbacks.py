"""Modal bbox callbacks for inline delete button clicks on graph."""

from dash import ClientsideFunction, Input, Output, State


def register_modal_bbox_inline_delete_callbacks(
    app,
    *,
    _apply_modal_boxes_to_figure,
    _require_complete_profile,
    _bbox_debug,
    _bbox_debug_box_summary,
    _BBOX_DELETE_TRACE_NAME,
):
    _ = (
        _apply_modal_boxes_to_figure,
        _require_complete_profile,
        _bbox_debug,
        _bbox_debug_box_summary,
        _BBOX_DELETE_TRACE_NAME,
    )
    app.clientside_callback(
        ClientsideFunction(namespace="bboxInteractions", function_name="deleteBox"),
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
