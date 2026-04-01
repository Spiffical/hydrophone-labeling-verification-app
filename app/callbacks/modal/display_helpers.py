"""Small UI display helpers for modal and cards."""

from math import log10

from dash import html
import dash_bootstrap_components as dbc


def create_folder_display(display_text, folders_list, data_root, popover_id):
    """Create a folder display — hoverable popover if multiple folders, plain text if single."""
    if folders_list and len(folders_list) > 1:
        relative_paths = []
        for folder in folders_list:
            if data_root and folder.startswith(data_root):
                relative_paths.append(folder[len(data_root):].lstrip("/"))
            else:
                relative_paths.append(folder)
        folder_items = [html.Div(path, className="mono-muted small") for path in relative_paths]
        return html.Div(
            [
                html.Span(
                    display_text,
                    id=popover_id,
                    style={"cursor": "pointer", "textDecoration": "underline", "color": "var(--link)"},
                ),
                dbc.Popover(
                    dbc.PopoverBody(
                        html.Div(folder_items, style={"maxHeight": "200px", "overflowY": "auto"})
                    ),
                    target=popover_id,
                    trigger="hover",
                    placement="bottom",
                ),
            ]
        )
    return display_text


def resolve_mode_y_axis_limits(
    mode,
    *,
    label_min,
    label_max,
    verify_min,
    verify_max,
    explore_min,
    explore_max,
):
    if mode == "verify":
        return verify_min, verify_max
    if mode == "explore":
        return explore_min, explore_max
    return label_min, label_max


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


def _figure_meta(fig):
    if hasattr(fig, "to_plotly_json"):
        fig = fig.to_plotly_json()
    elif hasattr(fig, "to_dict"):
        fig = fig.to_dict()
    if not isinstance(fig, dict):
        return {}
    layout = fig.get("layout") or {}
    if hasattr(layout, "to_plotly_json"):
        layout = layout.to_plotly_json()
    if not isinstance(layout, dict):
        return {}
    meta = layout.get("meta") or {}
    return meta if isinstance(meta, dict) else {}


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


def _round_frequency_input_value(value):
    value = float(value)
    if value >= 1000.0:
        return round(value, 2)
    if value >= 100.0:
        return round(value, 1)
    return round(value, 2)


def _round_color_input_value(value):
    return round(float(value), 1)


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
        round(float(value), 6)
        for value in reference
        if float(min_hz) <= float(value) <= float(max_hz)
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
    return {
        round(min_value + (span * idx / steps), 2): f"{min_value + (span * idx / steps):.1f}"
        for idx in range(steps + 1)
    }


def _log_slider_pair(lower_hz, upper_hz, *, minimum_hz, maximum_hz):
    lower_hz, upper_hz = _normalize_range(
        lower_hz,
        upper_hz,
        minimum=minimum_hz,
        maximum=maximum_hz,
    )
    return [round(log10(lower_hz), 6), round(log10(upper_hz), 6)]


def build_modal_colorbar_ui(fig) -> tuple[str, str, str]:
    meta = _figure_meta(fig)

    auto_min = meta.get("auto_color_min")
    auto_max = meta.get("auto_color_max")
    data_min = meta.get("data_color_min")
    data_max = meta.get("data_color_max")

    def _fmt(value, fallback):
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return fallback

    placeholder_min = _fmt(auto_min, "Auto min")
    placeholder_max = _fmt(auto_max, "Auto max")

    if auto_min is None or auto_max is None:
        hint = "Reset returns to automatic contrast for the current spectrogram."
    else:
        hint = (
            f"Auto: {_fmt(auto_min, '?')} to {_fmt(auto_max, '?')} dB/Hz. "
            f"Data span: {_fmt(data_min, '?')} to {_fmt(data_max, '?')}."
        )

    return placeholder_min, placeholder_max, hint


def build_modal_display_range_ui(
    fig,
    *,
    modal_y_min,
    modal_y_max,
    inherited_y_min,
    inherited_y_max,
    modal_color_min,
    modal_color_max,
):
    meta = _figure_meta(fig)

    positive_y_min_hz = max(0.001, float(_coerce_float(meta.get("positive_y_min_hz")) or 0.1))
    data_y_max_hz = float(_coerce_float(meta.get("data_y_max_hz")) or max(positive_y_min_hz * 10.0, 100.0))
    if data_y_max_hz <= positive_y_min_hz:
        data_y_max_hz = positive_y_min_hz * 10.0

    current_display_y_min_hz = float(
        _coerce_float(meta.get("display_y_min_hz")) or positive_y_min_hz
    )
    current_display_y_max_hz = float(
        _coerce_float(meta.get("display_y_max_hz")) or data_y_max_hz
    )

    inherited_y_min = _coerce_float(inherited_y_min)
    inherited_y_max = _coerce_float(inherited_y_max)
    modal_y_min = _coerce_float(modal_y_min)
    modal_y_max = _coerce_float(modal_y_max)

    if inherited_y_min is None and inherited_y_max is None:
        default_y_value = [round(log10(positive_y_min_hz), 6), round(log10(data_y_max_hz), 6)]
    else:
        default_y_value = _log_slider_pair(
            inherited_y_min or current_display_y_min_hz,
            inherited_y_max or current_display_y_max_hz,
            minimum_hz=positive_y_min_hz,
            maximum_hz=data_y_max_hz,
        )

    if modal_y_min is None and modal_y_max is None:
        y_slider_value = list(default_y_value)
        if inherited_y_min is None and inherited_y_max is None:
            y_readout = "Full available range"
        else:
            y_readout = f"Using page range: {_format_hz(current_display_y_min_hz)} to {_format_hz(current_display_y_max_hz)}"
    else:
        y_slider_value = _log_slider_pair(
            current_display_y_min_hz,
            current_display_y_max_hz,
            minimum_hz=positive_y_min_hz,
            maximum_hz=data_y_max_hz,
        )
        y_readout = f"{_format_hz(current_display_y_min_hz)} to {_format_hz(current_display_y_max_hz)}"

    color_data_min = float(_coerce_float(meta.get("data_color_min")) or -120.0)
    color_data_max = float(_coerce_float(meta.get("data_color_max")) or 0.0)
    if color_data_max <= color_data_min:
        midpoint = color_data_min
        color_data_min = midpoint - 0.5
        color_data_max = midpoint + 0.5

    auto_color_min, auto_color_max = _normalize_range(
        meta.get("auto_color_min"),
        meta.get("auto_color_max"),
        minimum=color_data_min,
        maximum=color_data_max,
    )
    modal_color_min = _coerce_float(modal_color_min)
    modal_color_max = _coerce_float(modal_color_max)
    current_display_color_min = float(_coerce_float(meta.get("display_color_min")) or auto_color_min)
    current_display_color_max = float(_coerce_float(meta.get("display_color_max")) or auto_color_max)

    default_color_value = [round(auto_color_min, 2), round(auto_color_max, 2)]
    if modal_color_min is None and modal_color_max is None:
        color_slider_value = list(default_color_value)
        color_readout = "Auto contrast"
    else:
        display_color_min, display_color_max = _normalize_range(
            current_display_color_min,
            current_display_color_max,
            minimum=color_data_min,
            maximum=color_data_max,
        )
        color_slider_value = [round(display_color_min, 2), round(display_color_max, 2)]
        color_readout = f"{_format_db(display_color_min)} to {_format_db(display_color_max)}"

    return {
        "y_slider_min": round(log10(positive_y_min_hz), 6),
        "y_slider_max": round(log10(data_y_max_hz), 6),
        "y_slider_marks": _frequency_marks(positive_y_min_hz, data_y_max_hz),
        "y_slider_value": y_slider_value,
        "y_readout": y_readout,
        "y_hint": f"Available on this item: {_format_hz(positive_y_min_hz)} to {_format_hz(data_y_max_hz)}.",
        "y_default": default_y_value,
        "y_manual_min": _round_frequency_input_value(current_display_y_min_hz),
        "y_manual_max": _round_frequency_input_value(current_display_y_max_hz),
        "color_slider_min": round(color_data_min, 2),
        "color_slider_max": round(color_data_max, 2),
        "color_slider_marks": _linear_marks(color_data_min, color_data_max),
        "color_slider_value": color_slider_value,
        "color_readout": color_readout,
        "color_default": default_color_value,
        "color_manual_min": _round_color_input_value(current_display_color_min),
        "color_manual_max": _round_color_input_value(current_display_color_max),
    }
