"""Modal view callbacks: figure refresh, display ranges, and actions panel refresh."""

import time
from math import log10

from dash import ClientsideFunction, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from app.callbacks.common.debug import perf_debug
from app.callbacks.modal.display_helpers import (
    build_modal_colorbar_ui,
    build_modal_contrast_ui,
    resolve_mode_value,
    resolve_mode_y_axis_limits,
)
from app.services.modal_boxes import reference_box_extents
from app.services.spectrogram_ranges import (
    config_for_spectrogram_range,
    format_frequency_range,
    normalize_spectrogram_range_state,
    resolve_visible_spectrogram_ranges,
    resolve_active_spectrogram_range,
)
from app.components.range_panels import panel_controls
from app.utils.image_processing import create_item_spectrogram_figure, spectrogram_time_span
from app.utils.image_utils import (
    build_modal_image_request_src,
    resolve_modal_image_target,
    use_full_resolution_modal_image,
)


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


def _round_color_input_value(value):
    return round(float(value), 1)


def _preview_modal_color_manual_values(drag_value, slider_value, slider_min, slider_max):
    active_range = _active_slider_range(drag_value, slider_value)
    lower, upper = _commit_modal_color_slider(active_range, slider_min, slider_max)
    if lower is None or upper is None:
        return no_update, no_update
    return _round_color_input_value(lower), _round_color_input_value(upper)


def _coerce_manual_bounds(lower, upper, *, minimum, maximum):
    lower_value = _coerce_float(lower)
    upper_value = _coerce_float(upper)
    if lower_value is None and upper_value is None:
        return None, None

    if lower_value is not None:
        lower_value = max(minimum, min(maximum, lower_value))
    if upper_value is not None:
        upper_value = max(minimum, min(maximum, upper_value))

    if lower_value is not None and upper_value is not None and upper_value <= lower_value:
        return None

    return (
        round(lower_value, 6) if lower_value is not None else None,
        round(upper_value, 6) if upper_value is not None else None,
    )


def _modal_color_slider_pair_from_manual_bounds(lower, upper, *, slider_min, slider_max, defaults):
    minimum = float(slider_min)
    maximum = float(slider_max)
    result = _coerce_manual_bounds(lower, upper, minimum=minimum, maximum=maximum)
    if result is None:
        return None
    if result[0] is None and result[1] is None:
        default_range = (defaults or {}).get("colorbar")
        if isinstance(default_range, (list, tuple)) and len(default_range) == 2:
            return [float(default_range[0]), float(default_range[1])]
        return [minimum, maximum]
    lower_value = minimum if result[0] is None else float(result[0])
    upper_value = maximum if result[1] is None else float(result[1])
    return [round(lower_value, 6), round(upper_value, 6)]


def register_modal_view_callbacks(
    app,
    *,
    _get_mode_data,
    _build_modal_boxes_from_item,
    _apply_modal_boxes_to_figure,
    _build_modal_item_actions,
):
    @app.callback(
        Output("modal-active-range-title", "children"),
        Output("modal-active-range-readout", "children"),
        Output("modal-visible-ranges-above", "children"),
        Output("modal-visible-ranges-below", "children"),
        Output("modal-active-range-section", "className"),
        Output("modal-active-range-remove", "disabled"),
        Input("modal-item-store", "data"),
        Input("spectrogram-ranges-store", "data"),
        Input("config-store", "data"),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        Input("modal-display-meta-store", "data"),
        Input("modal-figure-context-store", "data"),
        Input("modal-colorbar-min-input", "value"),
        Input("modal-colorbar-max-input", "value"),
        State("modal-viewport-store", "data"),
    )
    def render_modal_visible_ranges(
        modal_item,
        ranges_state,
        cfg,
        colormap,
        y_axis_scale,
        display_meta,
        active_figure,
        color_min,
        color_max,
        modal_viewport,
    ):
        base_section_class = (
            "spectrogram-range-section spectrogram-range-section--visible "
            "spectrogram-modal-plot-section"
        )
        if not isinstance(modal_item, dict) or not modal_item.get("item_id"):
            return "", "", [], [], f"{base_section_class} spectrogram-range-section--single", True
        cfg = cfg or {}
        display_meta = display_meta if isinstance(display_meta, dict) else {}
        normalized_state = normalize_spectrogram_range_state(ranges_state, cfg)
        visible_ranges = resolve_visible_spectrogram_ranges(modal_item, cfg, ranges_state)
        active_range_id = normalized_state.get("active_range_id")
        active_index = next(
            (
                index
                for index, candidate in enumerate(visible_ranges)
                if candidate.get("selection_id") == active_range_id
            ),
            0,
        )
        active_range = visible_ranges[active_index] if visible_ranges else None
        if active_range is None:
            return "", "", [], [], f"{base_section_class} spectrogram-range-section--single", True

        width, _height = resolve_modal_image_target(modal_viewport)
        panel_width = min(width or 1200, 1400)
        active_layout = (
            active_figure.get("layout", {}) if isinstance(active_figure, dict) else {}
        )
        active_xaxis = (
            active_layout.get("xaxis", {}) if isinstance(active_layout, dict) else {}
        )
        active_meta = active_layout.get("meta", {}) if isinstance(active_layout, dict) else {}
        active_meta = active_meta if isinstance(active_meta, dict) else {}

        def valid_range(value):
            return (
                isinstance(value, (list, tuple))
                and len(value) == 2
                and all(isinstance(bound, (int, float)) for bound in value)
                and value[1] > value[0]
            )

        # The whole clip on the main plot's time axis, and the part it shows.
        # The panels follow the main plot's time window and margins
        # (modal_range_panels.js), so the same moment lines up in every panel.
        view_range = active_xaxis.get("range") if isinstance(active_xaxis, dict) else None
        clip_range = [active_meta.get("x_min"), active_meta.get("x_max")]
        if not valid_range(clip_range):
            clip_range = view_range if valid_range(view_range) else [0.0, 1.0]
        x_min, x_max = float(clip_range[0]), float(clip_range[1])
        view_range = [float(bound) for bound in view_range] if valid_range(view_range) else [x_min, x_max]
        x_to_seconds = active_meta.get("x_to_seconds")
        x_to_seconds = float(x_to_seconds) if isinstance(x_to_seconds, (int, float)) and x_to_seconds > 0 else 1.0
        x_origin_seconds = active_meta.get("x_origin_seconds")
        x_tickformat = active_xaxis.get("tickformat") if isinstance(active_xaxis, dict) else None

        only_range = len(visible_ranges) <= 1

        def build_plot_panel(range_spec, index):
            range_cfg = (
                cfg
                if range_spec["id"] == "configured-range"
                else config_for_spectrogram_range(cfg, range_spec)
            )
            image_src = build_modal_image_request_src(
                modal_item,
                cfg=range_cfg,
                colormap=colormap or "default",
                y_axis_scale=y_axis_scale or "linear",
                y_axis_min_hz=range_spec["freq_min_hz"],
                y_axis_max_hz=range_spec["freq_max_hz"],
                color_min=color_min,
                color_max=color_max,
                max_width=panel_width,
                max_height=520,
            )
            freq_min_hz = float(range_spec["freq_min_hz"])
            freq_max_hz = float(range_spec["freq_max_hz"])
            # Each plot's time axis starts at its own first frame, half a window
            # into the clip, so place this range's image where its frames are
            # on the main plot's axis. Without that origin, fill the clip.
            image_x = [x_min, x_max]
            if isinstance(x_origin_seconds, (int, float)):
                span = spectrogram_time_span(
                    modal_item,
                    range_cfg,
                    y_axis_min_hz=range_spec["freq_min_hz"],
                    y_axis_max_hz=range_spec["freq_max_hz"],
                )
                if span and span[1] > span[0]:
                    image_x = [
                        (span[0] - x_origin_seconds) / x_to_seconds,
                        (span[1] - x_origin_seconds) / x_to_seconds,
                    ]
            figure = go.Figure()
            figure.add_trace(
                go.Scatter(
                    x=[x_min, x_max],
                    y=[freq_min_hz, freq_max_hz],
                    mode="markers",
                    marker={"opacity": 0.0, "size": 1},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            figure.add_layout_image(
                {
                    "source": image_src,
                    "xref": "x",
                    "yref": "paper",
                    "x": image_x[0],
                    "y": 1,
                    "sizex": max(1e-9, image_x[1] - image_x[0]),
                    "sizey": 1,
                    "xanchor": "left",
                    "yanchor": "top",
                    "sizing": "stretch",
                    "opacity": 1.0,
                    "layer": "below",
                }
            )
            # No fixed height: the panel shares the plot column with the main
            # plot (zz_workbench.css) and Plotly fills whatever it is given.
            # Margins and time window follow the main plot, so neither axis
            # zooms on its own and Plotly must not move the margins.
            figure.update_layout(
                autosize=True,
                # The main plot names the axes; these panels keep their ticks.
                margin={"l": 70, "r": 36, "t": 12, "b": 26},
                template="plotly_white",
                dragmode=False,
                meta={
                    "range_id": range_spec["selection_id"],
                    "freq_min_hz": freq_min_hz,
                    "freq_max_hz": freq_max_hz,
                    "x_min": x_min,
                    "x_max": x_max,
                    "x_to_seconds": x_to_seconds,
                },
                xaxis={
                    "title": None,
                    "range": view_range,
                    "showgrid": False,
                    "tickformat": x_tickformat,
                    "fixedrange": True,
                    "automargin": False,
                },
                yaxis={
                    "title": "Hz",
                    "type": "log" if (y_axis_scale or "linear") == "log" else "linear",
                    "range": (
                        [log10(max(freq_min_hz, 1e-9)), log10(freq_max_hz)]
                        if (y_axis_scale or "linear") == "log"
                        else [freq_min_hz, freq_max_hz]
                    ),
                    "showgrid": False,
                    "fixedrange": True,
                    "automargin": False,
                },
            )
            return html.Section(
                [
                    html.Div(
                        [
                            html.Span(
                                range_spec["label"],
                                className="spectrogram-range-title",
                            ),
                            html.Span(
                                format_frequency_range(
                                    range_spec["freq_min_hz"],
                                    range_spec["freq_max_hz"],
                                ),
                                className="spectrogram-range-frequency",
                            ),
                            panel_controls(
                                range_spec["label"],
                                {"type": "modal-range-remove", "range": range_spec["selection_id"]},
                                remove_disabled=only_range,
                            ),
                        ],
                        className="spectrogram-range-header",
                    ),
                    dcc.Graph(
                        figure=figure,
                        config={
                            "displayModeBar": False,
                            "displaylogo": False,
                            "responsive": True,
                        },
                        className="spectrogram-modal-range-graph",
                    ),
                ],
                className=(
                    "spectrogram-range-section spectrogram-range-section--visible "
                    f"spectrogram-range-accent-{index % 5} spectrogram-modal-plot-section"
                ),
                **{"data-range-key": range_spec["selection_id"]},
            )

        def splitter():
            # Drag to share height between the panels either side (modal_range_layout.js).
            return html.Div(
                className="spectrogram-panel-splitter",
                role="separator",
                tabIndex=0,
                title="Drag to resize; double-click to share evenly",
                **{"aria-orientation": "horizontal", "aria-label": "Resize spectrograms"},
            )

        # A splitter between every two panels: after each panel above the main
        # plot, and before each one below it.
        above = []
        for index, range_spec in enumerate(visible_ranges[:active_index]):
            above += [build_plot_panel(range_spec, index), splitter()]
        below = []
        for index, range_spec in enumerate(visible_ranges[active_index + 1 :], start=active_index + 1):
            below += [splitter(), build_plot_panel(range_spec, index)]
        return (
            active_range["label"],
            format_frequency_range(
                active_range["freq_min_hz"],
                active_range["freq_max_hz"],
            ),
            above,
            below,
            f"{base_section_class} spectrogram-range-accent-{active_index % 5}",
            len(visible_ranges) <= 1,
        )

    app.clientside_callback(
        ClientsideFunction(namespace="modalPerformance", function_name="figureContext"),
        Output("modal-figure-context-store", "data"),
        Output("modal-figure-meta-store", "data"),
        Input("modal-image-graph", "figure"),
        Input("current-filename", "data"),
        State("modal-figure-context-store", "data"),
        State("modal-figure-meta-store", "data"),
    )

    app.clientside_callback(
        ClientsideFunction(namespace="modalDisplay", function_name="startViewRefresh"),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Output("modal-render-ready-store", "data", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(namespace="modalDisplay", function_name="updateCommitted"),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        Input("modal-colorbar-min-input", "value"),
        Input("modal-colorbar-max-input", "value"),
        Input("label-yaxis-min-input", "value"),
        Input("label-yaxis-max-input", "value"),
        Input("verify-yaxis-min-input", "value"),
        Input("verify-yaxis-max-input", "value"),
        Input("explore-yaxis-min-input", "value"),
        Input("explore-yaxis-max-input", "value"),
        Input("label-colorbar-min-input", "value"),
        Input("label-colorbar-max-input", "value"),
        Input("verify-colorbar-min-input", "value"),
        Input("verify-colorbar-max-input", "value"),
        Input("explore-colorbar-min-input", "value"),
        Input("explore-colorbar-max-input", "value"),
        State("mode-tabs", "data"),
        State("modal-image-graph", "figure"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(namespace="modalDisplay", function_name="previewContrast"),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input("modal-colorbar-slider", "drag_value"),
        State("modal-y-axis-toggle", "value"),
        State("modal-image-graph", "figure"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(namespace="modalDisplay", function_name="commitRasterPreview"),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input("modal-colorbar-slider", "value"),
        State("modal-colormap-toggle", "value"),
        State("modal-y-axis-toggle", "value"),
        State("modal-image-graph", "figure"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(namespace="modalDisplay", function_name="extractDisplayMeta"),
        Output("modal-display-meta-store", "data"),
        Input("modal-image-graph", "figure"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Output("modal-colorbar-min-input", "placeholder", allow_duplicate=True),
        Output("modal-colorbar-max-input", "placeholder", allow_duplicate=True),
        Output("modal-colorbar-hint", "children", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        Input("modal-colorbar-min-input", "value"),
        Input("modal-colorbar-max-input", "value"),
        Input("label-yaxis-min-input", "value"),
        Input("label-yaxis-max-input", "value"),
        Input("verify-yaxis-min-input", "value"),
        Input("verify-yaxis-max-input", "value"),
        Input("explore-yaxis-min-input", "value"),
        Input("explore-yaxis-max-input", "value"),
        Input("label-colorbar-min-input", "value"),
        Input("label-colorbar-max-input", "value"),
        Input("verify-colorbar-min-input", "value"),
        Input("verify-colorbar-max-input", "value"),
        Input("explore-colorbar-min-input", "value"),
        Input("explore-colorbar-max-input", "value"),
        State("mode-tabs", "data"),
        State("modal-item-store", "data"),
        State("modal-bbox-store", "data"),
        State("config-store", "data"),
        State("modal-display-meta-store", "data"),
        State("modal-viewport-store", "data"),
        State("spectrogram-ranges-store", "data"),
        prevent_initial_call=True,
    )
    def update_modal_view(
        colormap,
        y_axis_scale,
        color_min,
        color_max,
        label_y_axis_min_hz,
        label_y_axis_max_hz,
        verify_y_axis_min_hz,
        verify_y_axis_max_hz,
        explore_y_axis_min_hz,
        explore_y_axis_max_hz,
        label_color_min,
        label_color_max,
        verify_color_min,
        verify_color_max,
        explore_color_min,
        explore_color_max,
        mode,
        modal_item,
        bbox_store,
        cfg,
        current_meta,
        modal_viewport,
        ranges_state,
    ):
        if not isinstance(modal_item, dict):
            raise PreventUpdate
        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate

        active_range = resolve_active_spectrogram_range(modal_item, cfg, ranges_state)
        if active_range:
            cfg = config_for_spectrogram_range(cfg, active_range)
        current_meta = current_meta if isinstance(current_meta, dict) else {}
        current_transport = current_meta.get("transport_mode")
        current_scale = current_meta.get("display_y_axis_scale") or "linear"
        if (
            ctx.triggered_id not in {"modal-colormap-toggle", "modal-y-axis-toggle"}
            and current_scale == y_axis_scale
            and current_transport in {"full_resolution_lossless_png", "float32", "float64"}
        ):
            raise PreventUpdate

        start = time.perf_counter()
        inherited_y_axis_min_hz, inherited_y_axis_max_hz = resolve_mode_y_axis_limits(
            mode,
            label_min=label_y_axis_min_hz,
            label_max=label_y_axis_max_hz,
            verify_min=verify_y_axis_min_hz,
            verify_max=verify_y_axis_max_hz,
            explore_min=explore_y_axis_min_hz,
            explore_max=explore_y_axis_max_hz,
        )
        page_y_axis_min_hz = current_meta.get("page_display_y_min_hz")
        page_y_axis_max_hz = current_meta.get("page_display_y_max_hz")
        if _coerce_float(page_y_axis_min_hz) is None:
            page_y_axis_min_hz = inherited_y_axis_min_hz
        if _coerce_float(page_y_axis_max_hz) is None:
            page_y_axis_max_hz = inherited_y_axis_max_hz
        inherited_color_min = resolve_mode_value(
            mode,
            label=label_color_min,
            verify=verify_color_min,
            explore=explore_color_min,
        )
        inherited_color_max = resolve_mode_value(
            mode,
            label=label_color_max,
            verify=verify_color_max,
            explore=explore_color_max,
        )
        page_color_min = current_meta.get("page_display_color_min")
        page_color_max = current_meta.get("page_display_color_max")
        if _coerce_float(page_color_min) is None:
            page_color_min = inherited_color_min
        if _coerce_float(page_color_max) is None:
            page_color_max = inherited_color_max
        use_page_color_range = (
            _coerce_float(color_min) is None and _coerce_float(color_max) is None
        )
        effective_color_min = page_color_min if use_page_color_range else color_min
        effective_color_max = page_color_max if use_page_color_range else color_max
        modal_image_width, modal_image_height = resolve_modal_image_target(modal_viewport)
        modal_image_source = None
        if use_full_resolution_modal_image(cfg, y_axis_scale):
            modal_image_source = build_modal_image_request_src(
                modal_item,
                cfg=cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=page_y_axis_min_hz,
                y_axis_max_hz=page_y_axis_max_hz,
                color_min=effective_color_min,
                color_max=effective_color_max,
                max_width=modal_image_width,
                max_height=modal_image_height,
            )
        fig, spectrogram = create_item_spectrogram_figure(
            modal_item,
            cfg,
            colormap,
            y_axis_scale,
            y_axis_min_hz=page_y_axis_min_hz,
            y_axis_max_hz=page_y_axis_max_hz,
            color_min=effective_color_min,
            color_max=effective_color_max,
            image_source=modal_image_source,
            image_target_width=modal_image_width,
            image_target_height=modal_image_height,
        )
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        else:
            boxes = _build_modal_boxes_from_item(modal_item)
        updated_meta = dict(fig.layout.meta or {})
        updated_meta.update(
            {
                "uses_page_color_range": use_page_color_range,
                "modal_item_id": item_id,
                "display_colormap": colormap,
                "page_display_y_min_hz": page_y_axis_min_hz,
                "page_display_y_max_hz": page_y_axis_max_hz,
                "page_display_color_min": page_color_min,
                "page_display_color_max": page_color_max,
                # Drawn dashed beside the boxes (apply_modal_boxes_to_figure).
                "reference_boxes": reference_box_extents(modal_item),
            }
        )
        fig.update_layout(meta=updated_meta)
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
        Output("modal-colorbar-slider", "min"),
        Output("modal-colorbar-slider", "max"),
        Output("modal-colorbar-slider", "marks"),
        Output("modal-colorbar-slider", "value"),
        Output("modal-colorbar-readout", "children"),
        Output("modal-colorbar-manual-min-input", "value"),
        Output("modal-colorbar-manual-max-input", "value"),
        Output("modal-display-range-defaults-store", "data"),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input("modal-display-meta-store", "data"),
        State("modal-colorbar-min-input", "value"),
        State("modal-colorbar-max-input", "value"),
        State("mode-tabs", "data"),
        State("label-colorbar-min-input", "value"),
        State("label-colorbar-max-input", "value"),
        State("verify-colorbar-min-input", "value"),
        State("verify-colorbar-max-input", "value"),
        State("explore-colorbar-min-input", "value"),
        State("explore-colorbar-max-input", "value"),
        State("modal-display-range-defaults-store", "data"),
        prevent_initial_call=True,
    )
    def sync_modal_contrast_controls(
        figure_meta,
        modal_color_min,
        modal_color_max,
        mode,
        label_color_min,
        label_color_max,
        verify_color_min,
        verify_color_max,
        explore_color_min,
        explore_color_max,
        current_defaults,
    ):
        if not isinstance(figure_meta, dict) or not figure_meta:
            raise PreventUpdate
        figure = {"layout": {"meta": figure_meta}}
        controls_match_item = (
            isinstance(current_defaults, dict)
            and current_defaults.get("item_id")
            and current_defaults.get("item_id") == figure_meta.get("modal_item_id")
        )
        if figure_meta.get("local_display_update_sequence") and controls_match_item:
            raise PreventUpdate
        ui = build_modal_contrast_ui(
            figure,
            modal_color_min=modal_color_min,
            modal_color_max=modal_color_max,
            inherited_color_min=resolve_mode_value(
                mode,
                label=label_color_min,
                verify=verify_color_min,
                explore=explore_color_min,
            ),
            inherited_color_max=resolve_mode_value(
                mode,
                label=label_color_max,
                verify=verify_color_max,
                explore=explore_color_max,
            ),
        )
        return (
            ui["color_slider_min"],
            ui["color_slider_max"],
            ui["color_slider_marks"],
            ui["color_slider_value"],
            ui["color_readout"],
            ui["color_manual_min"],
            ui["color_manual_max"],
            {
                "colorbar": ui["color_default"],
                "colorbar_readout": ui["color_readout"],
                "item_id": figure_meta.get("modal_item_id"),
            },
            False,
        )

    @app.callback(
        Output("modal-colorbar-readout", "children", allow_duplicate=True),
        Input("modal-colorbar-slider", "drag_value"),
        Input("modal-colorbar-slider", "value"),
        State("modal-colorbar-slider", "min"),
        State("modal-colorbar-slider", "max"),
        State("modal-display-range-defaults-store", "data"),
        State("modal-colorbar-min-input", "value"),
        State("modal-colorbar-max-input", "value"),
        prevent_initial_call=True,
    )
    def preview_modal_contrast_readout(
        drag_value,
        slider_value,
        slider_min,
        slider_max,
        defaults,
        current_color_min,
        current_color_max,
    ):
        return _preview_modal_color_readout(
            drag_value,
            slider_value,
            slider_min,
            slider_max,
            defaults,
            current_color_min,
            current_color_max,
        )

    @app.callback(
        Output("modal-colorbar-manual-min-input", "value", allow_duplicate=True),
        Output("modal-colorbar-manual-max-input", "value", allow_duplicate=True),
        Input("modal-colorbar-slider", "value"),
        State("modal-colorbar-slider", "min"),
        State("modal-colorbar-slider", "max"),
        prevent_initial_call=True,
    )
    def sync_modal_contrast_inputs_from_slider(slider_value, slider_min, slider_max):
        return _preview_modal_color_manual_values(None, slider_value, slider_min, slider_max)

    @app.callback(
        Output("modal-colorbar-min-input", "value", allow_duplicate=True),
        Output("modal-colorbar-max-input", "value", allow_duplicate=True),
        Input("modal-colorbar-slider", "value"),
        State("modal-colorbar-slider", "min"),
        State("modal-colorbar-slider", "max"),
        State("modal-display-range-defaults-store", "data"),
        State("modal-colorbar-min-input", "value"),
        State("modal-colorbar-max-input", "value"),
        prevent_initial_call=True,
    )
    def commit_modal_contrast(
        slider_value,
        slider_min,
        slider_max,
        defaults,
        current_color_min,
        current_color_max,
    ):
        if (
            _coerce_float(current_color_min) is None
            and _coerce_float(current_color_max) is None
            and _ranges_match(slider_value, (defaults or {}).get("colorbar"), tolerance=1e-3)
        ):
            return no_update, no_update
        return _commit_modal_color_slider(slider_value, slider_min, slider_max)

    @app.callback(
        Output("modal-colorbar-slider", "value", allow_duplicate=True),
        Input("modal-colorbar-manual-min-input", "n_blur"),
        Input("modal-colorbar-manual-min-input", "n_submit"),
        Input("modal-colorbar-manual-max-input", "n_blur"),
        Input("modal-colorbar-manual-max-input", "n_submit"),
        State("modal-colorbar-manual-min-input", "value"),
        State("modal-colorbar-manual-max-input", "value"),
        State("modal-colorbar-slider", "min"),
        State("modal-colorbar-slider", "max"),
        State("modal-display-range-defaults-store", "data"),
        prevent_initial_call=True,
    )
    def commit_modal_manual_contrast(
        manual_min_blur,
        manual_min_submit,
        manual_max_blur,
        manual_max_submit,
        manual_min,
        manual_max,
        slider_min,
        slider_max,
        defaults,
    ):
        _ = manual_min_blur, manual_min_submit, manual_max_blur, manual_max_submit
        slider_pair = _modal_color_slider_pair_from_manual_bounds(
            manual_min,
            manual_max,
            slider_min=slider_min,
            slider_max=slider_max,
            defaults=defaults,
        )
        return no_update if slider_pair is None else slider_pair

    @app.callback(
        Output("modal-colorbar-min-input", "value", allow_duplicate=True),
        Output("modal-colorbar-max-input", "value", allow_duplicate=True),
        Input("modal-colorbar-reset-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_modal_contrast(reset_clicks):
        if not reset_clicks:
            raise PreventUpdate
        return None, None

    # Box edits reach this panel through modal-item-store (the bbox sync
    # callback); the box list itself is rendered separately by bbox_list.js.
    @app.callback(
        Output("modal-item-actions", "children", allow_duplicate=True),
        Input("modal-item-store", "data"),
        Input("mode-tabs", "data"),
        Input("verify-thresholds-store", "data"),
        Input("modal-active-box-label", "data"),
        prevent_initial_call=True,
    )
    def refresh_modal_item_actions(
        modal_item,
        mode,
        thresholds,
        active_box_label,
    ):
        if not isinstance(modal_item, dict):
            raise PreventUpdate
        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate
        return _build_modal_item_actions(
            modal_item,
            mode,
            thresholds or {"__global__": 0.5},
            active_box_label=active_box_label,
        )
