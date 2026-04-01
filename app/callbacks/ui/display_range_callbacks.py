"""Page-level slider controls for preview frequency and contrast ranges."""

from math import log10

from dash import Input, Output, State, ctx, no_update

from app.utils.image_processing import (
    get_spectrogram_render_settings,
    resolve_item_spectrogram,
    summarize_spectrogram_display_ranges,
)


def _coerce_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _slice_page(items, current_page, items_per_page):
    items = items if isinstance(items, list) else []
    total_items = len(items)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    page_index = max(0, min(int(current_page or 0), total_pages - 1))
    start_idx = page_index * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx]


def _format_hz(value):
    value = float(value)
    if value >= 1000.0:
        return f"{value / 1000.0:.2f} kHz"
    if value >= 100.0:
        return f"{value:.0f} Hz"
    if value >= 10.0:
        return f"{value:.1f} Hz"
    return f"{value:.2f} Hz"


def _format_db(value):
    return f"{float(value):.1f} dB/Hz"


def _format_hz_mark(value):
    value = float(value)
    if value >= 1000.0:
        scaled = value / 1000.0
        if scaled >= 10.0 or abs(scaled - round(scaled)) < 0.05:
            return f"{scaled:.0f}k"
        return f"{scaled:.1f}k"
    if value >= 100.0:
        return f"{value:.0f}"
    if value >= 10.0:
        if abs(value - round(value)) < 0.05:
            return f"{value:.0f}"
        return f"{value:.1f}"
    if value >= 1.0:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _select_frequency_mark_values(min_hz, max_hz, *, limit=5):
    reference = [
        0.1,
        0.2,
        0.5,
        1.0,
        2.0,
        5.0,
        10.0,
        20.0,
        50.0,
        100.0,
        200.0,
        500.0,
        1000.0,
        2000.0,
        5000.0,
        10000.0,
        20000.0,
        50000.0,
        100000.0,
        200000.0,
    ]
    candidates = [
        round(float(candidate), 6)
        for candidate in reference
        if float(min_hz) <= float(candidate) <= float(max_hz)
    ]
    if len(candidates) < 2:
        return sorted({round(float(min_hz), 6), round(float(max_hz), 6)})
    if len(candidates) <= limit:
        return candidates

    log_min = log10(min_hz)
    log_max = log10(max_hz)
    targets = [log_min + (log_max - log_min) * idx / (limit - 1) for idx in range(limit)]
    selected = []
    used = set()
    for target in targets:
        choice = min(
            candidates,
            key=lambda value: (
                abs(log10(value) - target),
                abs(value - (10 ** target)),
            ),
        )
        if choice in used:
            continue
        selected.append(choice)
        used.add(choice)

    return sorted({round(float(value), 6) for value in selected})


def _frequency_marks(min_hz, max_hz):
    return {
        round(log10(value), 6): _format_hz_mark(value)
        for value in _select_frequency_mark_values(min_hz, max_hz)
    }


def _linear_marks(min_value, max_value):
    span = max_value - min_value
    if span <= 0:
        return {round(min_value, 2): f"{min_value:.1f}"}
    steps = 4
    marks = {}
    for idx in range(steps + 1):
        point = min_value + (span * idx / steps)
        marks[round(point, 2)] = f"{point:.1f}"
    return marks


def _normalize_range(lower, upper, *, minimum, maximum):
    lower = minimum if lower is None else float(lower)
    upper = maximum if upper is None else float(upper)
    lower = max(minimum, min(maximum, lower))
    upper = max(minimum, min(maximum, upper))
    if upper <= lower:
        return float(minimum), float(maximum)
    return float(lower), float(upper)


def _merge_display_summary(aggregate, summary):
    if not aggregate:
        return dict(summary)
    return {
        "freq_data_min_hz": min(aggregate["freq_data_min_hz"], summary["freq_data_min_hz"]),
        "freq_data_max_hz": max(aggregate["freq_data_max_hz"], summary["freq_data_max_hz"]),
        "freq_positive_min_hz": min(aggregate["freq_positive_min_hz"], summary["freq_positive_min_hz"]),
        "color_data_min": min(aggregate["color_data_min"], summary["color_data_min"]),
        "color_data_max": max(aggregate["color_data_max"], summary["color_data_max"]),
        "color_auto_min": min(aggregate["color_auto_min"], summary["color_auto_min"]),
        "color_auto_max": max(aggregate["color_auto_max"], summary["color_auto_max"]),
    }


def _fallback_display_summary(cfg):
    render_cfg = get_spectrogram_render_settings(cfg)
    freq_max_hz = max(1.0, float(render_cfg.get("freq_max_hz", 100.0)))
    configured_min_hz = _coerce_float(render_cfg.get("freq_min_hz"))
    if configured_min_hz is None or configured_min_hz <= 0:
        freq_min_hz = 0.1 if freq_max_hz <= 100.0 else 1.0
    else:
        freq_min_hz = configured_min_hz
    freq_max_hz = max(freq_min_hz * 10.0, freq_max_hz)
    return {
        "freq_data_min_hz": float(freq_min_hz),
        "freq_data_max_hz": float(freq_max_hz),
        "freq_positive_min_hz": float(freq_min_hz),
        "color_data_min": -120.0,
        "color_data_max": 0.0,
        "color_auto_min": -90.0,
        "color_auto_max": -10.0,
    }


def _page_display_summary(page_items, cfg):
    summary = None
    for item in page_items or []:
        if not isinstance(item, dict):
            continue
        spectrogram = resolve_item_spectrogram(item, cfg)
        current = summarize_spectrogram_display_ranges(spectrogram)
        if current:
            summary = _merge_display_summary(summary, current)
    return summary or _fallback_display_summary(cfg)


def _frequency_slider_state(prefix, summary, current_min, current_max, triggered_id):
    bound_min_hz = max(0.001, float(summary.get("freq_positive_min_hz") or 0.1))
    bound_max_hz = max(bound_min_hz * 10.0, float(summary.get("freq_data_max_hz") or bound_min_hz * 10.0))
    slider_min = round(log10(bound_min_hz), 6)
    slider_max = round(log10(bound_max_hz), 6)
    marks = _frequency_marks(bound_min_hz, bound_max_hz)
    default_slider_value = [slider_min, slider_max]

    current_min = _coerce_float(current_min)
    current_max = _coerce_float(current_max)

    if triggered_id == f"{prefix}-yaxis-reset-btn":
        return (
            slider_min,
            slider_max,
            marks,
            default_slider_value,
            "Full available range",
            f"Available on this page: {_format_hz(bound_min_hz)} to {_format_hz(bound_max_hz)}.",
            None,
            None,
            default_slider_value,
        )

    if current_min is None and current_max is None:
        readout = "Full available range"
        actual_lower = None
        actual_upper = None
        slider_pair = default_slider_value
    else:
        display_lower, display_upper = _normalize_range(
            current_min,
            current_max,
            minimum=bound_min_hz,
            maximum=bound_max_hz,
        )
        slider_pair = [round(log10(display_lower), 6), round(log10(display_upper), 6)]
        actual_lower = round(display_lower, 6) if current_min is not None else None
        actual_upper = round(display_upper, 6) if current_max is not None else None
        if current_min is None:
            readout = f"Up to {_format_hz(display_upper)}"
        elif current_max is None:
            readout = f"{_format_hz(display_lower)} and up"
        else:
            readout = f"{_format_hz(display_lower)} to {_format_hz(display_upper)}"

    return (
        slider_min,
        slider_max,
        marks,
        slider_pair,
        readout,
        f"Available on this page: {_format_hz(bound_min_hz)} to {_format_hz(bound_max_hz)}.",
        actual_lower,
        actual_upper,
        default_slider_value,
    )


def _color_slider_state(prefix, summary, current_min, current_max, triggered_id):
    bound_min = float(summary.get("color_data_min", -120.0))
    bound_max = float(summary.get("color_data_max", 0.0))
    if bound_max <= bound_min:
        midpoint = bound_min
        bound_min = midpoint - 0.5
        bound_max = midpoint + 0.5
    auto_min, auto_max = _normalize_range(
        summary.get("color_auto_min"),
        summary.get("color_auto_max"),
        minimum=bound_min,
        maximum=bound_max,
    )
    marks = _linear_marks(bound_min, bound_max)
    default_slider_value = [round(auto_min, 2), round(auto_max, 2)]

    current_min = _coerce_float(current_min)
    current_max = _coerce_float(current_max)

    if triggered_id == f"{prefix}-colorbar-reset-btn":
        return (
            round(bound_min, 2),
            round(bound_max, 2),
            marks,
            default_slider_value,
            "Auto contrast",
            (
                f"Page sample span: {_format_db(bound_min)} to {_format_db(bound_max)}. "
                f"Reset keeps per-spectrogram auto contrast active."
            ),
            None,
            None,
            default_slider_value,
        )

    if current_min is None and current_max is None:
        readout = "Auto contrast"
        actual_lower = None
        actual_upper = None
        slider_pair = default_slider_value
    else:
        display_lower, display_upper = _normalize_range(
            current_min,
            current_max,
            minimum=bound_min,
            maximum=bound_max,
        )
        slider_pair = [round(display_lower, 2), round(display_upper, 2)]
        actual_lower = round(display_lower, 6) if current_min is not None else None
        actual_upper = round(display_upper, 6) if current_max is not None else None
        if current_min is None:
            readout = f"Up to {_format_db(display_upper)}"
        elif current_max is None:
            readout = f"{_format_db(display_lower)} and up"
        else:
            readout = f"{_format_db(display_lower)} to {_format_db(display_upper)}"

    return (
        round(bound_min, 2),
        round(bound_max, 2),
        marks,
        slider_pair,
        readout,
        (
            f"Page sample auto: {_format_db(auto_min)} to {_format_db(auto_max)}. "
            f"Reset keeps per-spectrogram auto contrast active."
        ),
        actual_lower,
        actual_upper,
        default_slider_value,
    )


def _build_display_range_outputs(prefix, page_items, cfg, current_y_min, current_y_max, current_color_min, current_color_max):
    summary = _page_display_summary(page_items, cfg)
    triggered_id = ctx.triggered_id
    y_state = _frequency_slider_state(
        prefix,
        summary,
        current_y_min,
        current_y_max,
        triggered_id,
    )
    color_state = _color_slider_state(
        prefix,
        summary,
        current_color_min,
        current_color_max,
        triggered_id,
    )
    return (
        y_state[0],
        y_state[1],
        y_state[2],
        y_state[3],
        y_state[4],
        y_state[5],
        y_state[6],
        y_state[7],
        color_state[0],
        color_state[1],
        color_state[2],
        color_state[3],
        color_state[4],
        color_state[5],
        color_state[6],
        color_state[7],
        {
            "yaxis": y_state[8],
            "yaxis_readout": y_state[4],
            "colorbar": color_state[8],
            "colorbar_readout": color_state[4],
        },
    )


def _commit_frequency_slider(slider_value, slider_min, slider_max):
    if not isinstance(slider_value, (list, tuple)) or len(slider_value) != 2:
        return None, None, "Full available range"
    slider_lower, slider_upper = _normalize_range(
        slider_value[0],
        slider_value[1],
        minimum=slider_min,
        maximum=slider_max,
    )
    actual_lower = round(10 ** slider_lower, 6)
    actual_upper = round(10 ** slider_upper, 6)
    return actual_lower, actual_upper, f"{_format_hz(actual_lower)} to {_format_hz(actual_upper)}"


def _commit_color_slider(slider_value, slider_min, slider_max):
    if not isinstance(slider_value, (list, tuple)) or len(slider_value) != 2:
        return None, None, "Auto contrast"
    actual_lower, actual_upper = _normalize_range(
        slider_value[0],
        slider_value[1],
        minimum=slider_min,
        maximum=slider_max,
    )
    actual_lower = round(actual_lower, 6)
    actual_upper = round(actual_upper, 6)
    return actual_lower, actual_upper, f"{_format_db(actual_lower)} to {_format_db(actual_upper)}"


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


def _preview_frequency_readout(drag_value, slider_value, slider_min, slider_max, defaults, current_min, current_max):
    active_range = _active_slider_range(drag_value, slider_value)
    default_range = (defaults or {}).get("yaxis")
    default_readout = (defaults or {}).get("yaxis_readout") or "Full available range"
    if (
        _coerce_float(current_min) is None
        and _coerce_float(current_max) is None
        and _ranges_match(active_range, default_range)
    ):
        return default_readout
    _, _, readout = _commit_frequency_slider(active_range, slider_min, slider_max)
    return readout


def _preview_color_readout(drag_value, slider_value, slider_min, slider_max, defaults, current_min, current_max):
    active_range = _active_slider_range(drag_value, slider_value)
    default_range = (defaults or {}).get("colorbar")
    default_readout = (defaults or {}).get("colorbar_readout") or "Auto contrast"
    if (
        _coerce_float(current_min) is None
        and _coerce_float(current_max) is None
        and _ranges_match(active_range, default_range, tolerance=1e-3)
    ):
        return default_readout
    _, _, readout = _commit_color_slider(active_range, slider_min, slider_max)
    return readout


def register_display_range_callbacks(
    app,
    *,
    _filter_predictions,
    _predicted_labels_match_filter,
    _extract_verify_leaf_classes,
    _build_verify_filter_paths,
    _normalize_verify_class_filter,
):
    def _outputs(prefix):
        return (
            Output(f"{prefix}-yaxis-slider", "min"),
            Output(f"{prefix}-yaxis-slider", "max"),
            Output(f"{prefix}-yaxis-slider", "marks"),
            Output(f"{prefix}-yaxis-slider", "value"),
            Output(f"{prefix}-yaxis-readout", "children"),
            Output(f"{prefix}-yaxis-help", "children"),
            Output(f"{prefix}-yaxis-min-input", "value"),
            Output(f"{prefix}-yaxis-max-input", "value"),
            Output(f"{prefix}-colorbar-slider", "min"),
            Output(f"{prefix}-colorbar-slider", "max"),
            Output(f"{prefix}-colorbar-slider", "marks"),
            Output(f"{prefix}-colorbar-slider", "value"),
            Output(f"{prefix}-colorbar-readout", "children"),
            Output(f"{prefix}-colorbar-help", "children"),
            Output(f"{prefix}-colorbar-min-input", "value"),
            Output(f"{prefix}-colorbar-max-input", "value"),
            Output(f"{prefix}-display-range-defaults-store", "data"),
        )

    @app.callback(
        *_outputs("label"),
        Input("label-data-store", "data"),
        Input("label-current-page", "data"),
        Input("label-yaxis-reset-btn", "n_clicks"),
        Input("label-colorbar-reset-btn", "n_clicks"),
        Input("config-store", "data"),
        State("label-yaxis-min-input", "value"),
        State("label-yaxis-max-input", "value"),
        State("label-colorbar-min-input", "value"),
        State("label-colorbar-max-input", "value"),
    )
    def sync_label_display_ranges(
        data,
        current_page,
        y_reset_clicks,
        color_reset_clicks,
        cfg,
        current_y_min,
        current_y_max,
        current_color_min,
        current_color_max,
    ):
        _ = y_reset_clicks, color_reset_clicks
        cfg = cfg or {}
        items = ((data or {}).get("items") or []) if isinstance(data, dict) else []
        items_per_page = (cfg.get("display", {}) or {}).get("items_per_page", 25)
        page_items = _slice_page(items, current_page, items_per_page)
        return _build_display_range_outputs(
            "label",
            page_items,
            cfg,
            current_y_min,
            current_y_max,
            current_color_min,
            current_color_max,
        )

    @app.callback(
        *_outputs("verify"),
        Input("verify-data-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-current-page", "data"),
        Input("verify-yaxis-reset-btn", "n_clicks"),
        Input("verify-colorbar-reset-btn", "n_clicks"),
        Input("config-store", "data"),
        State("verify-yaxis-min-input", "value"),
        State("verify-yaxis-max-input", "value"),
        State("verify-colorbar-min-input", "value"),
        State("verify-colorbar-max-input", "value"),
    )
    def sync_verify_display_ranges(
        data,
        thresholds,
        class_filter,
        current_page,
        y_reset_clicks,
        color_reset_clicks,
        cfg,
        current_y_min,
        current_y_max,
        current_color_min,
        current_color_max,
    ):
        _ = y_reset_clicks, color_reset_clicks
        cfg = cfg or {}
        data = data or {"items": []}
        items = data.get("items", []) or []
        thresholds = thresholds or {"__global__": 0.5}
        available_values = _build_verify_filter_paths(_extract_verify_leaf_classes(items))
        available_value_set = set(available_values)
        selected_filters = _normalize_verify_class_filter(class_filter)
        if not available_values:
            selected_filters = None
        if selected_filters is not None:
            selected_filters = [value for value in selected_filters if value in available_value_set]

        filtered_items = []
        for item in items:
            if not item:
                continue
            annotations = item.get("annotations") or {}
            is_verified = bool(annotations.get("verified"))
            predictions = item.get("predictions") or {}
            predicted_labels = _filter_predictions(predictions, thresholds)
            if not is_verified and not predicted_labels:
                continue
            if not _predicted_labels_match_filter(predicted_labels, selected_filters):
                continue
            filtered_items.append(item)

        items_per_page = (cfg.get("display", {}) or {}).get("items_per_page", 25)
        page_items = _slice_page(filtered_items, current_page, items_per_page)
        return _build_display_range_outputs(
            "verify",
            page_items,
            cfg,
            current_y_min,
            current_y_max,
            current_color_min,
            current_color_max,
        )

    @app.callback(
        *_outputs("explore"),
        Input("explore-data-store", "data"),
        Input("explore-current-page", "data"),
        Input("explore-yaxis-reset-btn", "n_clicks"),
        Input("explore-colorbar-reset-btn", "n_clicks"),
        Input("config-store", "data"),
        State("explore-yaxis-min-input", "value"),
        State("explore-yaxis-max-input", "value"),
        State("explore-colorbar-min-input", "value"),
        State("explore-colorbar-max-input", "value"),
    )
    def sync_explore_display_ranges(
        data,
        current_page,
        y_reset_clicks,
        color_reset_clicks,
        cfg,
        current_y_min,
        current_y_max,
        current_color_min,
        current_color_max,
    ):
        _ = y_reset_clicks, color_reset_clicks
        cfg = cfg or {}
        items = ((data or {}).get("items") or []) if isinstance(data, dict) else []
        items_per_page = (cfg.get("display", {}) or {}).get("items_per_page", 25)
        page_items = _slice_page(items, current_page, items_per_page)
        return _build_display_range_outputs(
            "explore",
            page_items,
            cfg,
            current_y_min,
            current_y_max,
            current_color_min,
            current_color_max,
        )

    def _register_slider_commit(prefix):
        @app.callback(
            Output(f"{prefix}-yaxis-min-input", "value", allow_duplicate=True),
            Output(f"{prefix}-yaxis-max-input", "value", allow_duplicate=True),
            Output(f"{prefix}-colorbar-min-input", "value", allow_duplicate=True),
            Output(f"{prefix}-colorbar-max-input", "value", allow_duplicate=True),
            Input(f"{prefix}-yaxis-slider", "value"),
            Input(f"{prefix}-colorbar-slider", "value"),
            State(f"{prefix}-yaxis-slider", "min"),
            State(f"{prefix}-yaxis-slider", "max"),
            State(f"{prefix}-colorbar-slider", "min"),
            State(f"{prefix}-colorbar-slider", "max"),
            State(f"{prefix}-display-range-defaults-store", "data"),
            State(f"{prefix}-yaxis-min-input", "value"),
            State(f"{prefix}-yaxis-max-input", "value"),
            State(f"{prefix}-colorbar-min-input", "value"),
            State(f"{prefix}-colorbar-max-input", "value"),
            prevent_initial_call=True,
        )
        def commit_slider_values(
            y_slider_value,
            color_slider_value,
            y_slider_min,
            y_slider_max,
            color_slider_min,
            color_slider_max,
            defaults,
            current_y_min,
            current_y_max,
            current_color_min,
            current_color_max,
        ):
            triggered_id = ctx.triggered_id
            if triggered_id == f"{prefix}-yaxis-slider":
                if (
                    _coerce_float(current_y_min) is None
                    and _coerce_float(current_y_max) is None
                    and _ranges_match(y_slider_value, (defaults or {}).get("yaxis"))
                ):
                    return no_update, no_update, no_update, no_update
                y_min, y_max, _ = _commit_frequency_slider(
                    y_slider_value,
                    y_slider_min,
                    y_slider_max,
                )
                return y_min, y_max, no_update, no_update
            if (
                _coerce_float(current_color_min) is None
                and _coerce_float(current_color_max) is None
                and _ranges_match(color_slider_value, (defaults or {}).get("colorbar"), tolerance=1e-3)
            ):
                return no_update, no_update, no_update, no_update
            color_min, color_max, _ = _commit_color_slider(
                color_slider_value,
                color_slider_min,
                color_slider_max,
            )
            return no_update, no_update, color_min, color_max

    def _register_live_readout(prefix):
        @app.callback(
            Output(f"{prefix}-yaxis-readout", "children", allow_duplicate=True),
            Output(f"{prefix}-colorbar-readout", "children", allow_duplicate=True),
            Input(f"{prefix}-yaxis-slider", "drag_value"),
            Input(f"{prefix}-yaxis-slider", "value"),
            Input(f"{prefix}-colorbar-slider", "drag_value"),
            Input(f"{prefix}-colorbar-slider", "value"),
            State(f"{prefix}-yaxis-slider", "min"),
            State(f"{prefix}-yaxis-slider", "max"),
            State(f"{prefix}-colorbar-slider", "min"),
            State(f"{prefix}-colorbar-slider", "max"),
            State(f"{prefix}-display-range-defaults-store", "data"),
            State(f"{prefix}-yaxis-min-input", "value"),
            State(f"{prefix}-yaxis-max-input", "value"),
            State(f"{prefix}-colorbar-min-input", "value"),
            State(f"{prefix}-colorbar-max-input", "value"),
            prevent_initial_call=True,
        )
        def preview_slider_readouts(
            y_drag_value,
            y_slider_value,
            color_drag_value,
            color_slider_value,
            y_slider_min,
            y_slider_max,
            color_slider_min,
            color_slider_max,
            defaults,
            current_y_min,
            current_y_max,
            current_color_min,
            current_color_max,
        ):
            return (
                _preview_frequency_readout(
                    y_drag_value,
                    y_slider_value,
                    y_slider_min,
                    y_slider_max,
                    defaults,
                    current_y_min,
                    current_y_max,
                ),
                _preview_color_readout(
                    color_drag_value,
                    color_slider_value,
                    color_slider_min,
                    color_slider_max,
                    defaults,
                    current_color_min,
                    current_color_max,
                ),
            )

    _register_slider_commit("label")
    _register_slider_commit("verify")
    _register_slider_commit("explore")
    _register_live_readout("label")
    _register_live_readout("verify")
    _register_live_readout("explore")
