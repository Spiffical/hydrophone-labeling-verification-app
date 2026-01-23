from dash import html, dcc
import dash_bootstrap_components as dbc


def create_label_layout(config: dict) -> html.Div:
    label_cfg = config.get("label", {})
    display_cfg = config.get("display", {})

    return html.Div([
        html.Div([
            html.H2("Label Mode", className="section-title"),
            html.P("Manual labeling of MAT spectrograms", className="section-subtitle"),
        ], className="section-header"),

        html.Div([
            html.Div([
                html.Div([
                    html.Small("Spectrogram folder", className="text-muted"),
                    html.Div(
                        label_cfg.get("folder") or "Not set",
                        id="label-spec-folder-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Audio folder", className="text-muted"),
                    html.Div(
                        label_cfg.get("audio_folder") or "Not set",
                        id="label-audio-folder-display",
                        className="mono-muted",
                        style={"maxHeight": "40px", "overflowY": "auto"}
                    ),
                ], className="info-line"),
                html.Div([
                    html.Small("Output labels", className="text-muted"),
                    html.Div([
                        dbc.Input(
                            id="label-output-input",
                            value=label_cfg.get("output_file") or "",
                            placeholder="labels.json path...",
                            type="text",
                            size="sm",
                            className="me-2",
                            style={"flex": "1", "fontFamily": "monospace", "fontSize": "0.85rem"}
                        ),
                        dbc.Button(
                            "Browse",
                            id="label-output-browse-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ], id="label-output-display", className="d-flex align-items-center", style={"gap": "0.5rem"}),
                ], className="info-line"),
            ], className="info-grid", style={"maxHeight": "200px", "overflowY": "auto"}),

            # Pagination controls
            html.Div([
                dbc.Button("← Previous", id="label-prev-page", n_clicks=0, color="primary", size="sm", className="me-2"),
                dbc.Button("Next →", id="label-next-page", n_clicks=0, color="primary", size="sm", className="me-3"),
                html.Div([
                    html.Label("Go to page:", className="me-2", style={'font-weight': '500'}),
                    dbc.Input(
                        id="label-page-input",
                        type="number",
                        min=1,
                        step=1,
                        value=1,
                        className="me-2",
                        style={'width': '80px', 'display': 'inline-block'}
                    ),
                    dbc.Button("Go", id="label-goto-page", n_clicks=0, color="secondary", size="sm"),
                ], style={'display': 'inline-flex', 'align-items': 'center'}),
                html.Span(id="label-page-info", className="ms-3", style={'font-weight': '500', 'color': '#667eea'}),
            ], className="mb-3", style={'display': 'flex', 'align-items': 'center'}),

            html.Div([
                dbc.Switch(
                    id="label-colormap-toggle",
                    label="Hydrophone colormap",
                    value=display_cfg.get("colormap") == "hydrophone",
                    className="control-switch",
                ),
                dbc.Switch(
                    id="label-yaxis-toggle",
                    label="Log y-axis",
                    value=display_cfg.get("y_axis_scale") == "log",
                    className="control-switch",
                ),
                dbc.Button("Reload data", id="label-reload", color="primary", className="primary-btn"),
            ], className="control-row"),
        ], className="panel-card"),

        html.Div(id="label-summary", className="summary-bar"),
        dcc.Store(id="label-current-page", data=0, storage_type="session"),
        dcc.Loading(html.Div(id="label-grid", className="grid-shell"), type="circle"),
    ])
