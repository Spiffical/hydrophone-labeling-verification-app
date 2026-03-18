"""Modal view callbacks: figure refresh and actions panel refresh."""

import time

from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from app.callbacks.common.debug import perf_debug
from app.utils.image_processing import create_spectrogram_figure, resolve_item_spectrogram


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
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        State("modal-item-store", "data"),
        State("modal-bbox-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def update_modal_view(colormap, y_axis_scale, modal_item, bbox_store, cfg):
        if not isinstance(modal_item, dict):
            raise PreventUpdate
        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate

        start = time.perf_counter()
        spectrogram = resolve_item_spectrogram(modal_item, cfg)
        fig = create_spectrogram_figure(spectrogram, colormap, y_axis_scale)
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        else:
            boxes = _build_modal_boxes_from_item(modal_item)
        updated = _apply_modal_boxes_to_figure(fig, boxes)
        perf_debug(
            "modal_view_refresh",
            item_id=item_id,
            y_axis_scale=y_axis_scale,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            matrix_shape=(
                list(spectrogram.get("psd").shape)
                if isinstance(spectrogram, dict) and hasattr(spectrogram.get("psd"), "shape")
                else None
            ),
        )
        return updated, False

    @app.callback(
        Output("modal-item-actions", "children", allow_duplicate=True),
        Input("modal-item-store", "data"),
        Input("mode-tabs", "data"),
        Input("verify-thresholds-store", "data"),
        Input("modal-bbox-store", "data"),
        Input("modal-active-box-label", "data"),
        prevent_initial_call=True,
    )
    def refresh_modal_item_actions(
        modal_item,
        mode,
        thresholds,
        bbox_store,
        active_box_label,
    ):
        if not isinstance(modal_item, dict):
            raise PreventUpdate
        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate
        boxes = []
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        return _build_modal_item_actions(
            modal_item,
            mode,
            thresholds or {"__global__": 0.5},
            boxes=boxes,
            active_box_label=active_box_label,
        )
