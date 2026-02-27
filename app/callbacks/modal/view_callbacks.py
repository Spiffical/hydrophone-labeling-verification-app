"""Modal view callbacks: figure refresh and actions panel refresh."""

from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from app.utils.image_processing import create_spectrogram_figure, load_spectrogram_cached


def register_modal_view_callbacks(
    app,
    *,
    _get_mode_data,
    _build_modal_boxes_from_item,
    _apply_modal_boxes_to_figure,
    _build_modal_item_actions,
):
    @app.callback(
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        State("current-filename", "data"),
        State("modal-bbox-store", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def update_modal_view(colormap, y_axis_scale, item_id, bbox_store, label_data, verify_data, explore_data, mode):
        # Select the appropriate data store based on mode
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        if not item_id or not data:
            raise PreventUpdate

        items = data.get("items", [])
        active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate

        mat_path = active_item.get("mat_path")
        spectrogram = load_spectrogram_cached(mat_path)
        fig = create_spectrogram_figure(spectrogram, colormap, y_axis_scale)
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        else:
            boxes = _build_modal_boxes_from_item(active_item)
        return _apply_modal_boxes_to_figure(fig, boxes)

    @app.callback(
        Output("modal-item-actions", "children", allow_duplicate=True),
        Input("current-filename", "data"),
        Input("label-data-store", "data"),
        Input("verify-data-store", "data"),
        Input("explore-data-store", "data"),
        Input("mode-tabs", "data"),
        Input("verify-thresholds-store", "data"),
        Input("modal-bbox-store", "data"),
        Input("modal-active-box-label", "data"),
        prevent_initial_call=True,
    )
    def refresh_modal_item_actions(
        item_id,
        label_data,
        verify_data,
        explore_data,
        mode,
        thresholds,
        bbox_store,
        active_box_label,
    ):
        if not item_id:
            raise PreventUpdate
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        items = (data or {}).get("items", [])
        active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate
        boxes = []
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        return _build_modal_item_actions(
            active_item,
            mode,
            thresholds or {"__global__": 0.5},
            boxes=boxes,
            active_box_label=active_box_label,
        )
