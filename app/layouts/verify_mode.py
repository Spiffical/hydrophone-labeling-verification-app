from dash import html, dcc
import dash_bootstrap_components as dbc

from app.layouts.display_controls import create_display_range_bar


def _create_spectrogram_grid_placeholder() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(className="spec-card-skeleton-title"),
                    html.Div("Preparing spectrogram cards...", className="spec-card-skeleton-image"),
                    html.Div(className="spec-card-skeleton-line"),
                    html.Div(className="spec-card-skeleton-line spec-card-skeleton-line--short"),
                ],
                className="spec-card-skeleton",
            )
            for _ in range(6)
        ],
        className="spec-grid-placeholder",
    )


def create_verify_layout(config: dict) -> html.Div:
    data_cfg = config.get("data", {})
    verify_cfg = config.get("verify", {})
    nested_verify_cfg = data_cfg.get("verify", {}) if isinstance(data_cfg.get("verify"), dict) else {}
    display_cfg = config.get("display", {})

    return html.Div([
        html.Div([
            html.Div([
                html.H2("Verify Mode", className="section-title"),
                html.P("Review ML predictions and record verification", className="section-subtitle"),
            ], className="section-header"),
        ], className="section-header-wrap"),

        html.Div([
            html.Div([
                html.Div([
                    html.Small("Data Root", className="text-muted"),
                    html.Div(
                        data_cfg.get("data_dir") or verify_cfg.get("dashboard_root") or nested_verify_cfg.get("dashboard_root") or "Not set",
                        id="verify-data-root-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Spectrogram folder", className="text-muted"),
                    html.Div(
                        data_cfg.get("spectrogram_folder")
                        or html.Span("Loading spectrogram folder...", className="loading-path-text"),
                        id="verify-spec-folder-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Audio folder", className="text-muted"),
                    html.Div(
                        data_cfg.get("audio_folder")
                        or html.Span("Loading audio folder...", className="loading-path-text"),
                        id="verify-audio-folder-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Predictions file", className="text-muted"),
                    html.Div(
                        data_cfg.get("predictions_file")
                        or nested_verify_cfg.get("predictions_json")
                        or html.Span("Loading predictions file...", className="loading-path-text"),
                        id="verify-predictions-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
            ], className="info-grid", style={"maxHeight": "200px", "overflowY": "auto"}),

            html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Button("Reload dataset", id="verify-reload", color="primary", className="w-100"),
                    ], md=2, sm=4, xs=12),
                    dbc.Col([
                        html.Div([
                            html.Small("Filter by Class", className="text-muted d-block mb-1"),
                            html.Div([
                                dbc.Button(
                                    [
                                        html.Span("All classes selected", className="verify-class-filter-toggle-label"),
                                        html.Span("▾", className="verify-class-filter-toggle-caret"),
                                    ],
                                    id="verify-class-filter-toggle",
                                    color="secondary",
                                    outline=True,
                                    n_clicks=0,
                                    className="w-100 text-start verify-class-filter-toggle",
                                ),
                                dbc.Collapse(
                                    html.Div([
                                        html.Div([
                                            dbc.Checkbox(
                                                id="verify-class-filter-select-all",
                                                label="Select all / deselect all",
                                                value=True,
                                                className="verify-class-filter-select-all mb-0",
                                            ),
                                            dbc.Button(
                                                "Done",
                                                id="verify-class-filter-done",
                                                color="link",
                                                size="sm",
                                                className="verify-class-filter-done-btn",
                                            ),
                                        ], className="verify-class-filter-menu-header"),
                                        html.Div(
                                            id="verify-class-filter-tree",
                                            className="verify-class-filter-tree",
                                        ),
                                    ], className="verify-class-filter-menu"),
                                    id="verify-class-filter-collapse",
                                    is_open=False,
                                    className="verify-class-filter-collapse",
                                ),
                            ]),
                        ], className="verify-class-filter-panel verify-class-filter-dropdown"),
                    ], md=5, sm=8, xs=12),
                    dbc.Col([
                        html.Div([
                            html.Small("Confidence Threshold", className="text-muted d-block mb-1"),
                            dcc.Slider(
                                id="verify-threshold-slider",
                                min=0, max=1, value=0.5, step=0.01,
                                marks={0: "0%", 0.5: "50%", 1: "100%"},
                                tooltip={"placement": "top", "always_visible": True},
                                className="control-slider",
                            ),
                        ]),
                    ], md=5, sm=12, xs=12),
                ], className="align-items-end g-4"),
            ]),
        ], className="panel-card"),
        html.Div(
            id="verify-class-filter-dismiss-overlay",
            n_clicks=0,
            className="verify-class-filter-dismiss-overlay",
            style={"display": "none"},
        ),

        html.Div([
            html.Div("Page Navigation", className="pagination-sticky-title"),
            html.Div([
                dbc.Button("← Previous", id="verify-prev-page", n_clicks=0, color="primary", size="sm"),
                dbc.Button("Next →", id="verify-next-page", n_clicks=0, color="primary", size="sm"),
                html.Div([
                    html.Label("Go to page:", className="pagination-goto-label"),
                    dbc.Input(
                        id="verify-page-input",
                        type="number",
                        min=1,
                        step=1,
                        value=1,
                        className="pagination-page-input",
                    ),
                    dbc.Button("Go", id="verify-goto-page", n_clicks=0, color="secondary", size="sm"),
                ], className="pagination-goto-group"),
                html.Span(id="verify-page-info", className="pagination-page-info"),
            ], className="pagination-controls"),
        ], className="pagination-sticky-bar"),
        create_display_range_bar("verify", display_cfg=display_cfg),

        html.Div(id="verify-summary", className="summary-bar"),
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Unsaved Verification Changes")),
                dbc.ModalBody(
                    "You have unsaved verification label changes on this page set. "
                    "Save all changes before moving to another page?"
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button(
                            "Stay",
                            id="verify-unsaved-page-stay",
                            color="secondary",
                            className="me-2",
                            n_clicks=0,
                        ),
                        dbc.Button(
                            "Save All & Continue",
                            id="verify-unsaved-page-save",
                            color="success",
                            n_clicks=0,
                        ),
                    ]
                ),
            ],
            id="verify-unsaved-page-modal",
            is_open=False,
            centered=True,
            backdrop="static",
            keyboard=False,
        ),
        dcc.Store(id="verify-current-page", data=0, storage_type="session"),
        dcc.Store(id="verify-pending-page-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-visible-item-ids-store", data=[], storage_type="memory"),
        dcc.Store(id="verify-data-cache-key-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-modal-synced-item-ids-store", data=[], storage_type="memory"),
        html.Div(
            _create_spectrogram_grid_placeholder(),
            id="verify-grid",
            className="grid-shell",
        ),
    ])
