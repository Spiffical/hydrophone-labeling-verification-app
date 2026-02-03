from dash import html, dcc
import dash_bootstrap_components as dbc


def create_verify_layout(config: dict) -> html.Div:
    verify_cfg = config.get("verify", {})

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
                        config.get("data", {}).get("data_dir") or verify_cfg.get("dashboard_root") or "Not set",
                        id="verify-data-root-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Spectrogram folder", className="text-muted"),
                    html.Div(
                        "Not set",
                        id="verify-spec-folder-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Audio folder", className="text-muted"),
                    html.Div(
                        "Not set",
                        id="verify-audio-folder-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Predictions file", className="text-muted"),
                    html.Div(
                        "Not set",
                        id="verify-predictions-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
            ], className="info-grid", style={"maxHeight": "200px", "overflowY": "auto"}),

            # Pagination controls
            html.Div([
                dbc.Button("← Previous", id="verify-prev-page", n_clicks=0, color="primary", size="sm", className="me-2"),
                dbc.Button("Next →", id="verify-next-page", n_clicks=0, color="primary", size="sm", className="me-3"),
                html.Div([
                    html.Label("Go to page:", className="me-2", style={'font-weight': '500'}),
                    dbc.Input(
                        id="verify-page-input",
                        type="number",
                        min=1,
                        step=1,
                        value=1,
                        className="me-2",
                        style={'width': '80px', 'display': 'inline-block'}
                    ),
                    dbc.Button("Go", id="verify-goto-page", n_clicks=0, color="secondary", size="sm"),
                ], style={'display': 'inline-flex', 'align-items': 'center'}),
                html.Span(id="verify-page-info", className="ms-3", style={'font-weight': '500', 'color': '#667eea'}),
            ], className="mb-3", style={'display': 'flex', 'align-items': 'center'}),

            html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Button("Reload dataset", id="verify-reload", color="primary", className="w-100"),
                    ], md=2, sm=4, xs=12),
                    dbc.Col([
                        html.Div([
                            html.Small("Filter by Class", className="text-muted d-block mb-1"),
                            dcc.Dropdown(
                                id="verify-class-filter",
                                options=[{"label": "All classes", "value": "all"}],
                                value="all",
                                clearable=False,
                                className="control-dropdown",
                            ),
                        ]),
                    ], md=4, sm=8, xs=12),
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
                    ], md=6, sm=12, xs=12),
                ], className="align-items-end g-4"),
            ]),
        ], className="panel-card"),

        html.Div(id="verify-summary", className="summary-bar"),
        dcc.Store(id="verify-current-page", data=0, storage_type="session"),
        dcc.Loading(html.Div(id="verify-grid", className="grid-shell"), type="circle"),
    ])
