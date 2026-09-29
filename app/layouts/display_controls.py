from typing import Optional

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services.spectrogram_presets import (
    get_spectrogram_presets,
)
from app.services.spectrogram_ranges import uses_visible_ranges
from app.services.spectrogram_grid import (
    MAX_GRID_COLUMNS,
    MAX_GRID_ROWS,
    normalize_spectrogram_grid,
)


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
    input_unit: Optional[str] = None,
    min_value=None,
    max_value=None,
    group_id: Optional[str] = None,
    hidden: bool = False,
) -> html.Div:
    def manual_input(component_id: str):
        field = dcc.Input(
            id=component_id,
            type="number",
            debounce=True,
            inputMode="decimal",
            step="any",
            className="display-range-manual-input",
        )
        if not input_unit:
            return field
        return html.Div(
            [field, html.Span(input_unit, className="display-range-input-unit")],
            className="display-range-input-with-unit",
        )

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
                    manual_input(manual_min_id),
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
                            className="control-slider display-range-slider",
                        ),
                        className="display-range-slider-shell",
                    ),
                    manual_input(manual_max_id),
                ],
                className="display-range-slider-row",
            ),
            dbc.FormText(help_text, id=help_id, className="display-range-help"),
            dcc.Input(id=min_id, type="hidden", value=min_value),
            dcc.Input(id=max_id, type="hidden", value=max_value),
        ],
        className="display-range-group",
        hidden=hidden,
        **({"id": group_id} if group_id else {}),
    )


def create_display_range_bar(
    prefix: str,
    display_cfg: Optional[dict] = None,
    compact: bool = False,
    config: Optional[dict] = None,
) -> html.Div:
    display_cfg = display_cfg or {}
    summary_title = "Spectrogram" if compact else "Spectrogram settings"
    details_class = "display-range-bar display-settings-details"
    if compact:
        details_class += " display-range-bar--compact command-tool verify-only"

    frequency_group = _slider_group(
        label="Frequency window",
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
        help_text="Available frequency range for the current page.",
        input_unit="Hz",
        min_value=display_cfg.get("y_axis_min_hz"),
        max_value=display_cfg.get("y_axis_max_hz"),
        # Visible ranges set each spectrogram's band; the window only applies
        # to spectrogram files made beforehand (display_range_callbacks.py).
        group_id=f"{prefix}-frequency-window-group",
        hidden=uses_visible_ranges(config),
    )
    contrast_group = _slider_group(
        label="Contrast",
        slider_id=f"{prefix}-colorbar-slider",
        readout_id=f"{prefix}-colorbar-readout",
        help_id=f"{prefix}-colorbar-help",
        min_id=f"{prefix}-colorbar-min-input",
        max_id=f"{prefix}-colorbar-max-input",
        manual_min_id=f"{prefix}-colorbar-manual-min-input",
        manual_max_id=f"{prefix}-colorbar-manual-max-input",
        reset_id=f"{prefix}-colorbar-reset-btn",
        reset_label="Auto",
        slider_min=-120.0,
        slider_max=0.0,
        slider_value=[-90.0, -10.0],
        slider_marks={-120.0: "-120", -80.0: "-80", -40.0: "-40", 0.0: "0"},
        slider_step=0.1,
        help_text="Automatic contrast range for the current page.",
        min_value=display_cfg.get("colorbar_min"),
        max_value=display_cfg.get("colorbar_max"),
    )

    content_children = []
    if compact:
        content_children.append(
            html.Div(
                [
                    html.Span("Spectrogram settings", className="spectrogram-settings-popover-title"),
                    html.Button(
                        html.I(className="bi bi-x-lg"),
                        type="button",
                        className="spectrogram-settings-close",
                        title="Close spectrogram settings",
                        **{
                            "aria-label": "Close spectrogram settings",
                            "data-command-panel-close": "display",
                        },
                    ),
                ],
                className="spectrogram-settings-popover-header",
            )
        )
    content_children.extend(
        [
            html.Section(
                [
                    html.Div("Source & generation", className="spectrogram-settings-section-title"),
                    create_spectrogram_source_controls(prefix, config=config),
                ],
                className="spectrogram-settings-section spectrogram-settings-section--source",
            ),
            html.Section(
                [
                    html.Div("Frequency", className="spectrogram-settings-section-title"),
                    create_spectrogram_range_controls(prefix, config=config),
                    frequency_group,
                ],
                className="spectrogram-settings-section spectrogram-settings-section--frequency",
            ),
            html.Section(
                [
                    html.Div("Appearance", className="spectrogram-settings-section-title"),
                    html.Div(
                        [
                            dbc.Switch(
                                id=f"{prefix}-colormap-toggle",
                                label="O3.0 colormap",
                                value=display_cfg.get("colormap") == "hydrophone",
                                className="control-switch",
                            ),
                            dbc.Switch(
                                id=f"{prefix}-yaxis-toggle",
                                label="Log frequency axis",
                                value=display_cfg.get("y_axis_scale") == "log",
                                className="control-switch",
                            ),
                        ],
                        className="display-settings-toggle-row",
                    ),
                    contrast_group,
                ],
                className="spectrogram-settings-section spectrogram-settings-section--appearance",
            ),
        ]
    )

    return html.Details(
        [
            html.Summary(
                [
                    html.Span(
                        [
                            html.I(className="bi bi-soundwave me-2") if compact else None,
                            summary_title,
                        ],
                        className="display-range-title",
                    ),
                    html.Span(
                        [
                            html.Span("Show controls", className="display-range-summary-closed"),
                            html.Span("Hide controls", className="display-range-summary-open"),
                        ],
                        className="display-range-summary-hint",
                    ),
                    html.I(className="bi bi-chevron-down command-panel-caret") if compact else None,
                ],
                id=f"{prefix}-display-settings-summary",
                n_clicks=0,
                className="display-range-summary",
            ),
            html.Div(
                content_children,
                className="display-range-content",
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
        id=f"{prefix}-display-settings-details",
        open=False,
        className=details_class,
        **({"data-command-panel": "display"} if compact else {}),
    )


def create_spectrogram_grid_controls(config: Optional[dict] = None) -> html.Div:
    """Create the grid-density fields shown in Application settings."""
    layout = normalize_spectrogram_grid(config)
    return html.Div(
        [
            html.Div(
                [
                    html.Label(
                        "Rows",
                        htmlFor="spectrogram-grid-rows",
                        className="display-grid-label",
                    ),
                    dbc.Select(
                        id="spectrogram-grid-rows",
                        value=layout["rows"],
                        options=[
                            {"label": str(value), "value": value}
                            for value in range(1, MAX_GRID_ROWS + 1)
                        ],
                        className="display-grid-select",
                    ),
                ],
                className="display-grid-field",
            ),
            html.Div(
                [
                    html.Label(
                        "Columns",
                        htmlFor="spectrogram-grid-columns",
                        className="display-grid-label",
                    ),
                    dbc.Select(
                        id="spectrogram-grid-columns",
                        value=layout["columns"],
                        options=[
                            {"label": str(value), "value": value}
                            for value in range(1, MAX_GRID_COLUMNS + 1)
                        ],
                        className="display-grid-select",
                    ),
                ],
                className="display-grid-field",
            ),
            html.Div(
                f"{layout['items_per_page']} spectrograms per page",
                id="spectrogram-grid-layout-summary",
                className="display-grid-summary",
            ),
        ],
        className="display-grid-controls app-config-grid-controls",
    )


def create_spectrogram_range_controls(prefix: str, config: Optional[dict] = None) -> html.Div:
    options = [
        {"label": preset["label"], "value": preset["id"]}
        for preset in get_spectrogram_presets(config)
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Visible ranges", className="spectrogram-preset-title"),
                    html.Button(
                        html.I(className="bi bi-plus-lg", **{"aria-hidden": "true"}),
                        id=f"{prefix}-spectrogram-add-range-btn",
                        n_clicks=0,
                        type="button",
                        className="spectrogram-range-add-btn",
                        title="Add a custom frequency range",
                        **{"aria-label": "Add a custom frequency range"},
                    ),
                ],
                className="spectrogram-companion-heading",
            ),
            dbc.Checklist(
                id=f"{prefix}-spectrogram-extra-presets",
                options=options,
                value=[],
                class_name="spectrogram-companion-options",
                input_class_name="btn-check",
                label_class_name="spectrogram-companion-option",
                label_checked_class_name="spectrogram-companion-option--active",
            ),
            dbc.Checklist(
                id=f"{prefix}-spectrogram-custom-visible",
                options=[],
                value=[],
                class_name="spectrogram-companion-options spectrogram-custom-options",
                input_class_name="btn-check",
                label_class_name="spectrogram-companion-option spectrogram-companion-option--custom",
                label_checked_class_name="spectrogram-companion-option--active",
            ),
            html.Div(
                [
                    html.Span(
                        "Select up to five ranges, then apply.",
                        className="spectrogram-visible-range-hint",
                    ),
                    dbc.Button(
                        "Apply ranges",
                        id=f"{prefix}-spectrogram-apply-ranges",
                        n_clicks=0,
                        color="primary",
                        size="sm",
                    ),
                ],
                className="spectrogram-visible-range-actions",
            ),
            html.Div(
                id=f"{prefix}-spectrogram-custom-delete-list",
                className="spectrogram-custom-delete-list",
            ),
            dbc.Collapse(
                html.Div(
                    [
                        dbc.Input(
                            id=f"{prefix}-spectrogram-custom-label",
                            type="text",
                            placeholder="Range name",
                            maxLength=40,
                            className="spectrogram-custom-range-name",
                        ),
                        html.Div(
                            [
                                dbc.Input(
                                    id=f"{prefix}-spectrogram-custom-min",
                                    type="number",
                                    min=0,
                                    max=200000,
                                    step="any",
                                    placeholder="Min Hz",
                                ),
                                html.Span("to", className="spectrogram-custom-range-separator"),
                                dbc.Input(
                                    id=f"{prefix}-spectrogram-custom-max",
                                    type="number",
                                    min=0.01,
                                    max=200000,
                                    step="any",
                                    placeholder="Max Hz",
                                ),
                            ],
                            className="spectrogram-custom-range-bounds",
                        ),
                        html.Div(
                            [
                                dbc.Button(
                                    "Cancel",
                                    id=f"{prefix}-spectrogram-custom-cancel",
                                    n_clicks=0,
                                    color="secondary",
                                    outline=True,
                                    size="sm",
                                ),
                                dbc.Button(
                                    "Add range",
                                    id=f"{prefix}-spectrogram-custom-submit",
                                    n_clicks=0,
                                    color="primary",
                                    size="sm",
                                ),
                            ],
                            className="spectrogram-custom-range-actions",
                        ),
                        html.Div(
                            id=f"{prefix}-spectrogram-custom-error",
                            className="spectrogram-custom-range-error",
                            role="alert",
                        ),
                    ],
                    className="spectrogram-custom-range-form",
                ),
                id=f"{prefix}-spectrogram-custom-collapse",
                is_open=False,
            ),
        ],
        id=f"{prefix}-spectrogram-range-controls",
        style={"display": "block" if (config or {}).get("spectrogram_render", {}).get("source") == "audio_generated" else "none"},
        className="spectrogram-companion-controls spectrogram-visible-range-controls",
    )


def create_companion_range_controls(prefix: str, config: Optional[dict] = None) -> html.Div:
    """Compatibility alias for older imports."""
    return create_spectrogram_range_controls(prefix, config=config)


def create_spectrogram_source_controls(prefix: str, config: Optional[dict] = None) -> html.Div:
    render_cfg = (config or {}).get("spectrogram_render", {})
    if not isinstance(render_cfg, dict):
        render_cfg = {}
    source = str(render_cfg.get("source") or "existing")
    if source not in {"existing", "audio_generated"}:
        source = "existing"

    return html.Div(
        [
            html.Div(
                [
                    html.Span("Source", className="spectrogram-preset-title"),
                    dbc.RadioItems(
                        id=f"{prefix}-spectrogram-source",
                        options=[
                            {"label": "Existing files", "value": "existing"},
                            {"label": "Generate from audio", "value": "audio_generated"},
                        ],
                        value=source,
                        class_name="spectrogram-preset-options spectrogram-source-options",
                        input_class_name="btn-check",
                        label_class_name="spectrogram-preset-option",
                        label_checked_class_name="spectrogram-preset-option--active",
                    ),
                ],
                className="spectrogram-source-group",
            ),
            dbc.Collapse(
                html.Div(
                    [
                        html.Span("FFT parameters", className="spectrogram-preset-title"),
                        html.Div(
                            [
                                html.Label(
                                    [
                                        html.Span("Window", className="spectrogram-generation-label"),
                                        dbc.Input(
                                            id=f"{prefix}-spec-win-dur",
                                            type="number",
                                            min=0.001,
                                            max=30.0,
                                            step=0.01,
                                            value=render_cfg.get("win_dur_s", 1.0),
                                            debounce=True,
                                            className="spectrogram-generation-input",
                                        ),
                                        html.Span("s", className="spectrogram-generation-unit"),
                                    ],
                                    className="spectrogram-generation-field",
                                ),
                                html.Label(
                                    [
                                        html.Span("Overlap", className="spectrogram-generation-label"),
                                        dbc.Input(
                                            id=f"{prefix}-spec-overlap",
                                            type="number",
                                            min=0.0,
                                            max=0.99,
                                            step=0.01,
                                            value=render_cfg.get("overlap", 0.5),
                                            debounce=True,
                                            className="spectrogram-generation-input",
                                        ),
                                    ],
                                    className="spectrogram-generation-field",
                                ),
                            ],
                            className="spectrogram-generation-fields",
                        ),
                        html.Button(
                            [
                                html.I(
                                    id=f"{prefix}-generate-spectrograms-icon",
                                    className="bi bi-play-fill",
                                    **{"aria-hidden": "true"},
                                ),
                                html.Span(
                                    "Generate spectrograms",
                                    id=f"{prefix}-generate-spectrograms-label",
                                ),
                            ],
                            id=f"{prefix}-generate-spectrograms-btn",
                            n_clicks=0,
                            disabled=source != "audio_generated",
                            type="button",
                            className="btn btn-primary spectrogram-generate-btn",
                            **{"aria-busy": "false"},
                        ),
                    ],
                    className="spectrogram-fft-tray",
                ),
                id=f"{prefix}-fft-parameters-collapse",
                is_open=source == "audio_generated",
                class_name="spectrogram-fft-collapse",
            ),
        ],
        id=f"{prefix}-spectrogram-source-controls",
        className="spectrogram-source-controls",
        style={} if config else {"display": "none"},
    )
