from typing import Optional

import dash_bootstrap_components as dbc
from dash import dcc, html


def _slider_group(
    *,
    label: str,
    slider_id: str,
    readout_id: str,
    help_id: str,
    min_id: str,
    max_id: str,
    manual_min_id: str,
    manual_max_id: str,
    reset_id: str,
    reset_label: str,
    slider_min,
    slider_max,
    slider_value,
    slider_marks,
    slider_step,
    help_text: str,
    min_value=None,
    max_value=None,
) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Label(label, className="display-range-label"),
                    html.Div(
                        [
                            html.Span("Auto", id=readout_id, className="display-range-readout"),
                            dbc.Button(
                                reset_label,
                                id=reset_id,
                                color="secondary",
                                outline=True,
                                size="sm",
                                n_clicks=0,
                                className="display-range-reset",
                            ),
                        ],
                        className="display-range-actions",
                    ),
                ],
                className="display-range-group-header",
            ),
            html.Div(
                [
                    dcc.Input(
                        id=manual_min_id,
                        type="number",
                        debounce=True,
                        inputMode="decimal",
                        step="any",
                        className="display-range-manual-input",
                    ),
                    html.Div(
                        dcc.RangeSlider(
                            id=slider_id,
                            min=slider_min,
                            max=slider_max,
                            value=slider_value,
                            marks=slider_marks,
                            step=slider_step,
                            allowCross=False,
                            updatemode="mouseup",
                            tooltip={
                                "placement": "bottom",
                                "always_visible": False,
                                "transform": "formatLogFrequencyHz" if "yaxis" in slider_id else "formatDecibelRange",
                            },
                            className="control-slider display-range-slider",
                        ),
                        className="display-range-slider-shell",
                    ),
                    dcc.Input(
                        id=manual_max_id,
                        type="number",
                        debounce=True,
                        inputMode="decimal",
                        step="any",
                        className="display-range-manual-input",
                    ),
                ],
                className="display-range-slider-row",
            ),
            dbc.FormText(help_text, id=help_id, className="display-range-help"),
            dcc.Input(id=min_id, type="hidden", value=min_value),
            dcc.Input(id=max_id, type="hidden", value=max_value),
        ],
        className="display-range-group",
    )


def create_display_range_bar(prefix: str, display_cfg: Optional[dict] = None) -> html.Div:
    display_cfg = display_cfg or {}

    return html.Div(
        [
            html.Div(
                [
                    html.Span("Display ranges", className="display-range-title"),
                    html.Span(
                        "Adjust preview frequency and contrast without changing the underlying data.",
                        className="display-range-subtitle",
                    ),
                ],
                className="display-range-header",
            ),
            html.Div(
                [
                    _slider_group(
                        label="Frequency window (Hz)",
                        slider_id=f"{prefix}-yaxis-slider",
                        readout_id=f"{prefix}-yaxis-readout",
                        help_id=f"{prefix}-yaxis-help",
                        min_id=f"{prefix}-yaxis-min-input",
                        max_id=f"{prefix}-yaxis-max-input",
                        manual_min_id=f"{prefix}-yaxis-manual-min-input",
                        manual_max_id=f"{prefix}-yaxis-manual-max-input",
                        reset_id=f"{prefix}-yaxis-reset-btn",
                        reset_label="Full range",
                        slider_min=0.0,
                        slider_max=2.0,
                        slider_value=[0.0, 2.0],
                        slider_marks={0.0: "1 Hz", 1.0: "10 Hz", 2.0: "100 Hz"},
                        slider_step=0.005,
                        help_text="Log-scaled slider. Reset returns to the full available frequency range.",
                        min_value=display_cfg.get("y_axis_min_hz"),
                        max_value=display_cfg.get("y_axis_max_hz"),
                    ),
                    _slider_group(
                        label="Preview contrast (dB/Hz)",
                        slider_id=f"{prefix}-colorbar-slider",
                        readout_id=f"{prefix}-colorbar-readout",
                        help_id=f"{prefix}-colorbar-help",
                        min_id=f"{prefix}-colorbar-min-input",
                        max_id=f"{prefix}-colorbar-max-input",
                        manual_min_id=f"{prefix}-colorbar-manual-min-input",
                        manual_max_id=f"{prefix}-colorbar-manual-max-input",
                        reset_id=f"{prefix}-colorbar-reset-btn",
                        reset_label="Auto contrast",
                        slider_min=-120.0,
                        slider_max=0.0,
                        slider_value=[-90.0, -10.0],
                        slider_marks={-120.0: "-120", -80.0: "-80", -40.0: "-40", 0.0: "0"},
                        slider_step=0.1,
                        help_text="Applies a shared contrast range to page previews. Reset returns to per-spectrogram auto contrast.",
                        min_value=display_cfg.get("colorbar_min"),
                        max_value=display_cfg.get("colorbar_max"),
                    ),
                ],
                className="display-range-groups",
            ),
            dcc.Store(
                id=f"{prefix}-display-range-defaults-store",
                data={
                    "yaxis": [0.0, 2.0],
                    "yaxis_readout": "Full available range",
                    "colorbar": [-90.0, -10.0],
                    "colorbar_readout": "Auto contrast",
                },
            ),
        ],
        className="display-range-bar",
    )
