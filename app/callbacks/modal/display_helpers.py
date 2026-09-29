"""Small UI display helpers for modal and cards."""

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


def resolve_mode_value(mode, *, label, verify, explore):
    """Return the display-control value for the currently active page mode."""
    if mode == "verify":
        return verify
    if mode == "explore":
        return explore
    return label


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


def _format_db(value):
    return f"{float(value):.1f} dB/Hz"


def _round_color_input_value(value):
    return round(float(value), 1)


def _linear_marks(min_value, max_value):
    span = max_value - min_value
    if span <= 0:
        return {round(min_value, 2): f"{min_value:.1f}"}
    steps = 4
    return {
        round(min_value + (span * idx / steps), 2): f"{min_value + (span * idx / steps):.1f}"
        for idx in range(steps + 1)
    }


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


def build_modal_contrast_ui(
    fig,
    *,
    modal_color_min,
    modal_color_max,
    inherited_color_min=None,
    inherited_color_max=None,
):
    """Slider bounds, value and readout for the modal's contrast control."""
    meta = _figure_meta(fig)

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
    inherited_color_min = _coerce_float(inherited_color_min)
    inherited_color_max = _coerce_float(inherited_color_max)
    current_display_color_min = float(_coerce_float(meta.get("display_color_min")) or auto_color_min)
    current_display_color_max = float(_coerce_float(meta.get("display_color_max")) or auto_color_max)

    if meta.get("uses_page_color_range"):
        inherited_color_min = _coerce_float(
            meta.get("page_display_color_min", current_display_color_min)
        )
        inherited_color_max = _coerce_float(
            meta.get("page_display_color_max", current_display_color_max)
        )

    color_slider_min = min(
        value
        for value in (color_data_min, current_display_color_min, inherited_color_min, modal_color_min)
        if value is not None
    )
    color_slider_max = max(
        value
        for value in (color_data_max, current_display_color_max, inherited_color_max, modal_color_max)
        if value is not None
    )

    if inherited_color_min is None and inherited_color_max is None:
        default_color_value = [round(auto_color_min, 2), round(auto_color_max, 2)]
    else:
        inherited_display_color_min, inherited_display_color_max = _normalize_range(
            inherited_color_min if inherited_color_min is not None else current_display_color_min,
            inherited_color_max if inherited_color_max is not None else current_display_color_max,
            minimum=color_slider_min,
            maximum=color_slider_max,
        )
        default_color_value = [
            round(inherited_display_color_min, 2),
            round(inherited_display_color_max, 2),
        ]
    if modal_color_min is None and modal_color_max is None:
        color_slider_value = list(default_color_value)
        if inherited_color_min is None and inherited_color_max is None:
            color_readout = "Auto contrast"
        else:
            color_readout = (
                f"Using page contrast: {_format_db(current_display_color_min)} "
                f"to {_format_db(current_display_color_max)}"
            )
    else:
        display_color_min, display_color_max = _normalize_range(
            current_display_color_min,
            current_display_color_max,
            minimum=color_slider_min,
            maximum=color_slider_max,
        )
        color_slider_value = [round(display_color_min, 2), round(display_color_max, 2)]
        color_readout = f"{_format_db(display_color_min)} to {_format_db(display_color_max)}"

    return {
        "color_slider_min": round(color_slider_min, 2),
        "color_slider_max": round(color_slider_max, 2),
        "color_slider_marks": _linear_marks(color_slider_min, color_slider_max),
        "color_slider_value": color_slider_value,
        "color_readout": color_readout,
        "color_default": default_color_value,
        "color_manual_min": _round_color_input_value(color_slider_value[0]),
        "color_manual_max": _round_color_input_value(color_slider_value[1]),
    }
