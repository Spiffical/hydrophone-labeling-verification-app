"""Modal view callbacks: figure refresh, display ranges, and actions panel refresh."""

import time

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.common.debug import perf_debug
from app.callbacks.modal.display_helpers import (
    build_modal_colorbar_ui,
    build_modal_display_range_ui,
    resolve_mode_y_axis_limits,
)
from app.utils.image_processing import create_spectrogram_figure, resolve_item_spectrogram


def _coerce_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_range(lower, upper, *, minimum, maximum):
    lower = minimum if lower is None else float(lower)
    upper = maximum if upper is None else float(upper)
    lower = max(minimum, min(maximum, lower))
    upper = max(minimum, min(maximum, upper))
    if upper <= lower:
        return float(minimum), float(maximum)
    return float(lower), float(upper)


def _format_hz(value):
    value = float(value)
    if value >= 1000.0:
        return f"{value / 1000.0:.2f} kHz"
    if value >= 100.0:
        return f"{value:.0f} Hz"
    if value >= 10.0:
        return f"{value:.1f} Hz"
    return f"{value:.2f} Hz"


def _ranges_match(left, right, *, tolerance=1e-6):
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
        return False
    if len(left) != 2 or len(right) != 2:
        return False
    return abs(float(left[0]) - float(right[0])) <= tolerance and abs(float(left[1]) - float(right[1])) <= tolerance


def _active_slider_range(drag_value, slider_value):
    if isinstance(drag_value, (list, tuple)) and len(drag_value) == 2:
        return drag_value
    return slider_value


def _commit_modal_frequency_slider(slider_value, slider_min, slider_max):
    if not isinstance(slider_value, (list, tuple)) or len(slider_value) != 2:
        return None, None
    lower_value, upper_value = _normalize_range(
        slider_value[0],
        slider_value[1],
        minimum=slider_min,
        maximum=slider_max,
    )
    return round(10 ** lower_value, 6), round(10 ** upper_value, 6)


def _commit_modal_color_slider(slider_value, slider_min, slider_max):
    if not isinstance(slider_value, (list, tuple)) or len(slider_value) != 2:
        return None, None
    lower_value, upper_value = _normalize_range(
        slider_value[0],
        slider_value[1],
        minimum=slider_min,
        maximum=slider_max,
    )
    return round(lower_value, 6), round(upper_value, 6)


def _preview_modal_frequency_readout(
    drag_value,
    slider_value,
    slider_min,
    slider_max,
    defaults,
    current_modal_y_axis_min_hz,
    current_modal_y_axis_max_hz,
):
    active_range = _active_slider_range(drag_value, slider_value)
    default_range = (defaults or {}).get("yaxis")
    default_readout = (defaults or {}).get("yaxis_readout") or "Using page range"
    if (
        _coerce_float(current_modal_y_axis_min_hz) is None
        and _coerce_float(current_modal_y_axis_max_hz) is None
        and _ranges_match(active_range, default_range)
    ):
        return default_readout
    lower_hz, upper_hz = _commit_modal_frequency_slider(
        active_range,
        slider_min,
        slider_max,
    )
    if lower_hz is None or upper_hz is None:
        return default_readout
    return f"{_format_hz(lower_hz)} to {_format_hz(upper_hz)}"


def _preview_modal_color_readout(
    drag_value,
    slider_value,
    slider_min,
    slider_max,
    defaults,
    current_modal_color_min,
    current_modal_color_max,
):
    active_range = _active_slider_range(drag_value, slider_value)
    default_range = (defaults or {}).get("colorbar")
    default_readout = (defaults or {}).get("colorbar_readout") or "Auto contrast"
    if (
        _coerce_float(current_modal_color_min) is None
        and _coerce_float(current_modal_color_max) is None
        and _ranges_match(active_range, default_range, tolerance=1e-3)
    ):
        return default_readout
    color_min, color_max = _commit_modal_color_slider(
        active_range,
        slider_min,
        slider_max,
    )
    if color_min is None or color_max is None:
        return default_readout
    return f"{color_min:.1f} dB/Hz to {color_max:.1f} dB/Hz"


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
        Output("modal-colorbar-min-input", "placeholder", allow_duplicate=True),
        Output("modal-colorbar-max-input", "placeholder", allow_duplicate=True),
        Output("modal-colorbar-hint", "children", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        Input("modal-yaxis-min-input", "value"),
        Input("modal-yaxis-max-input", "value"),
        Input("modal-colorbar-min-input", "value"),
        Input("modal-colorbar-max-input", "value"),
        Input("label-yaxis-min-input", "value"),
        Input("label-yaxis-max-input", "value"),
        Input("verify-yaxis-min-input", "value"),
        Input("verify-yaxis-max-input", "value"),
        Input("explore-yaxis-min-input", "value"),
        Input("explore-yaxis-max-input", "value"),
        State("mode-tabs", "data"),
        State("modal-item-store", "data"),
        State("modal-bbox-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def update_modal_view(
        colormap,
        y_axis_scale,
        modal_y_axis_min_hz,
        modal_y_axis_max_hz,
        color_min,
        color_max,
        label_y_axis_min_hz,
        label_y_axis_max_hz,
        verify_y_axis_min_hz,
        verify_y_axis_max_hz,
        explore_y_axis_min_hz,
        explore_y_axis_max_hz,
        mode,
        modal_item,
        bbox_store,
        cfg,
    ):
        if not isinstance(modal_item, dict):
            raise PreventUpdate
        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate

        start = time.perf_counter()
        spectrogram = resolve_item_spectrogram(modal_item, cfg)
        inherited_y_axis_min_hz, inherited_y_axis_max_hz = resolve_mode_y_axis_limits(
            mode,
            label_min=label_y_axis_min_hz,
            label_max=label_y_axis_max_hz,
            verify_min=verify_y_axis_min_hz,
            verify_max=verify_y_axis_max_hz,
            explore_min=explore_y_axis_min_hz,
            explore_max=explore_y_axis_max_hz,
        )
        effective_y_axis_min_hz = (
            modal_y_axis_min_hz if _coerce_float(modal_y_axis_min_hz) is not None else inherited_y_axis_min_hz
        )
        effective_y_axis_max_hz = (
            modal_y_axis_max_hz if _coerce_float(modal_y_axis_max_hz) is not None else inherited_y_axis_max_hz
        )
        fig = create_spectrogram_figure(
            spectrogram,
            colormap,
            y_axis_scale,
            cfg=cfg,
            y_axis_min_hz=effective_y_axis_min_hz,
            y_axis_max_hz=effective_y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        else:
            boxes = _build_modal_boxes_from_item(modal_item)
        updated = _apply_modal_boxes_to_figure(fig, boxes)
        placeholder_min, placeholder_max, colorbar_hint = build_modal_colorbar_ui(updated)
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
        return updated, False, placeholder_min, placeholder_max, colorbar_hint

    @app.callback(
        Output("modal-yaxis-slider", "min"),
        Output("modal-yaxis-slider", "max"),
        Output("modal-yaxis-slider", "marks"),
        Output("modal-yaxis-slider", "value"),
        Output("modal-yaxis-readout", "children"),
        Output("modal-yaxis-hint", "children"),
        Output("modal-colorbar-slider", "min"),
        Output("modal-colorbar-slider", "max"),
        Output("modal-colorbar-slider", "marks"),
        Output("modal-colorbar-slider", "value"),
        Output("modal-colorbar-readout", "children"),
        Output("modal-display-range-defaults-store", "data"),
        Input("modal-image-graph", "figure"),
        State("modal-yaxis-min-input", "value"),
        State("modal-yaxis-max-input", "value"),
        State("modal-colorbar-min-input", "value"),
        State("modal-colorbar-max-input", "value"),
        State("mode-tabs", "data"),
        State("label-yaxis-min-input", "value"),
        State("label-yaxis-max-input", "value"),
        State("verify-yaxis-min-input", "value"),
        State("verify-yaxis-max-input", "value"),
        State("explore-yaxis-min-input", "value"),
        State("explore-yaxis-max-input", "value"),
        prevent_initial_call=True,
    )
    def sync_modal_display_ranges(
        figure,
        modal_y_axis_min_hz,
        modal_y_axis_max_hz,
        modal_color_min,
        modal_color_max,
        mode,
        label_y_axis_min_hz,
        label_y_axis_max_hz,
        verify_y_axis_min_hz,
        verify_y_axis_max_hz,
        explore_y_axis_min_hz,
        explore_y_axis_max_hz,
    ):
        if not figure:
            raise PreventUpdate
        inherited_y_axis_min_hz, inherited_y_axis_max_hz = resolve_mode_y_axis_limits(
            mode,
            label_min=label_y_axis_min_hz,
            label_max=label_y_axis_max_hz,
            verify_min=verify_y_axis_min_hz,
            verify_max=verify_y_axis_max_hz,
            explore_min=explore_y_axis_min_hz,
            explore_max=explore_y_axis_max_hz,
        )
        ui = build_modal_display_range_ui(
            figure,
            modal_y_min=modal_y_axis_min_hz,
            modal_y_max=modal_y_axis_max_hz,
            inherited_y_min=inherited_y_axis_min_hz,
            inherited_y_max=inherited_y_axis_max_hz,
            modal_color_min=modal_color_min,
            modal_color_max=modal_color_max,
        )
        return (
            ui["y_slider_min"],
            ui["y_slider_max"],
            ui["y_slider_marks"],
            ui["y_slider_value"],
            ui["y_readout"],
            ui["y_hint"],
            ui["color_slider_min"],
            ui["color_slider_max"],
            ui["color_slider_marks"],
            ui["color_slider_value"],
            ui["color_readout"],
            {
                "yaxis": ui["y_default"],
                "yaxis_readout": ui["y_readout"],
                "colorbar": ui["color_default"],
                "colorbar_readout": ui["color_readout"],
            },
        )

    @app.callback(
        Output("modal-yaxis-readout", "children", allow_duplicate=True),
        Output("modal-colorbar-readout", "children", allow_duplicate=True),
        Input("modal-yaxis-slider", "drag_value"),
        Input("modal-yaxis-slider", "value"),
        Input("modal-colorbar-slider", "drag_value"),
        Input("modal-colorbar-slider", "value"),
        State("modal-yaxis-slider", "min"),
        State("modal-yaxis-slider", "max"),
        State("modal-colorbar-slider", "min"),
        State("modal-colorbar-slider", "max"),
        State("modal-display-range-defaults-store", "data"),
        State("modal-yaxis-min-input", "value"),
        State("modal-yaxis-max-input", "value"),
        State("modal-colorbar-min-input", "value"),
        State("modal-colorbar-max-input", "value"),
        prevent_initial_call=True,
    )
    def preview_modal_display_range_readouts(
        modal_y_axis_drag_value,
        modal_y_axis_slider_value,
        modal_colorbar_drag_value,
        modal_colorbar_slider_value,
        modal_y_axis_slider_min,
        modal_y_axis_slider_max,
        modal_colorbar_slider_min,
        modal_colorbar_slider_max,
        defaults,
        current_modal_y_axis_min_hz,
        current_modal_y_axis_max_hz,
        current_modal_color_min,
        current_modal_color_max,
    ):
        return (
            _preview_modal_frequency_readout(
                modal_y_axis_drag_value,
                modal_y_axis_slider_value,
                modal_y_axis_slider_min,
                modal_y_axis_slider_max,
                defaults,
                current_modal_y_axis_min_hz,
                current_modal_y_axis_max_hz,
            ),
            _preview_modal_color_readout(
                modal_colorbar_drag_value,
                modal_colorbar_slider_value,
                modal_colorbar_slider_min,
                modal_colorbar_slider_max,
                defaults,
                current_modal_color_min,
                current_modal_color_max,
            ),
        )

    @app.callback(
        Output("modal-yaxis-min-input", "value", allow_duplicate=True),
        Output("modal-yaxis-max-input", "value", allow_duplicate=True),
        Output("modal-colorbar-min-input", "value", allow_duplicate=True),
        Output("modal-colorbar-max-input", "value", allow_duplicate=True),
        Input("modal-yaxis-slider", "value"),
        Input("modal-colorbar-slider", "value"),
        State("modal-yaxis-slider", "min"),
        State("modal-yaxis-slider", "max"),
        State("modal-colorbar-slider", "min"),
        State("modal-colorbar-slider", "max"),
        State("modal-display-range-defaults-store", "data"),
        State("modal-yaxis-min-input", "value"),
        State("modal-yaxis-max-input", "value"),
        State("modal-colorbar-min-input", "value"),
        State("modal-colorbar-max-input", "value"),
        prevent_initial_call=True,
    )
    def commit_modal_display_range_values(
        modal_y_axis_slider_value,
        modal_colorbar_slider_value,
        modal_y_axis_slider_min,
        modal_y_axis_slider_max,
        modal_colorbar_slider_min,
        modal_colorbar_slider_max,
        defaults,
        current_modal_y_axis_min_hz,
        current_modal_y_axis_max_hz,
        current_modal_color_min,
        current_modal_color_max,
    ):
        triggered_id = ctx.triggered_id
        defaults = defaults or {}
        if triggered_id == "modal-yaxis-slider":
            if (
                _coerce_float(current_modal_y_axis_min_hz) is None
                and _coerce_float(current_modal_y_axis_max_hz) is None
                and _ranges_match(modal_y_axis_slider_value, defaults.get("yaxis"))
            ):
                return no_update, no_update, no_update, no_update
            y_min_hz, y_max_hz = _commit_modal_frequency_slider(
                modal_y_axis_slider_value,
                modal_y_axis_slider_min,
                modal_y_axis_slider_max,
            )
            return y_min_hz, y_max_hz, no_update, no_update

        if (
            _coerce_float(current_modal_color_min) is None
            and _coerce_float(current_modal_color_max) is None
            and _ranges_match(modal_colorbar_slider_value, defaults.get("colorbar"), tolerance=1e-3)
        ):
            return no_update, no_update, no_update, no_update
        color_min, color_max = _commit_modal_color_slider(
            modal_colorbar_slider_value,
            modal_colorbar_slider_min,
            modal_colorbar_slider_max,
        )
        return no_update, no_update, color_min, color_max

    @app.callback(
        Output("modal-yaxis-min-input", "value", allow_duplicate=True),
        Output("modal-yaxis-max-input", "value", allow_duplicate=True),
        Output("modal-colorbar-min-input", "value", allow_duplicate=True),
        Output("modal-colorbar-max-input", "value", allow_duplicate=True),
        Input("modal-yaxis-reset-btn", "n_clicks"),
        Input("modal-colorbar-reset-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_modal_display_ranges(y_axis_reset_clicks, colorbar_reset_clicks):
        _ = y_axis_reset_clicks, colorbar_reset_clicks
        triggered_id = ctx.triggered_id
        if triggered_id == "modal-yaxis-reset-btn":
            return None, None, no_update, no_update
        if triggered_id == "modal-colorbar-reset-btn":
            return no_update, no_update, None, None
        raise PreventUpdate

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
