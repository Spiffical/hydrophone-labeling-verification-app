from dash import html, dcc
import dash_bootstrap_components as dbc

from app.layouts.display_controls import create_display_range_bar


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

            html.Div([
                dbc.Button("Reload data", id="label-reload", color="primary", className="primary-btn"),
            ], className="control-row"),
        ], className="panel-card"),

        html.Div([
            html.Div("Page Navigation", className="pagination-sticky-title"),
            html.Div([
                dbc.Button("← Previous", id="label-prev-page", n_clicks=0, color="primary", size="sm"),
                dbc.Button("Next →", id="label-next-page", n_clicks=0, color="primary", size="sm"),
                html.Div([
                    html.Label("Go to page:", className="pagination-goto-label"),
                    dbc.Input(
                        id="label-page-input",
                        type="number",
                        min=1,
                        step=1,
                        value=1,
                        className="pagination-page-input",
                    ),
                    dbc.Button("Go", id="label-goto-page", n_clicks=0, color="secondary", size="sm"),
                ], className="pagination-goto-group"),
                html.Span(id="label-page-info", className="pagination-page-info"),
            ], className="pagination-controls"),
        ], className="pagination-sticky-bar"),
        create_display_range_bar("label", display_cfg=display_cfg),

        html.Div(id="label-summary", className="summary-bar"),
        dcc.Store(id="label-current-page", data=0, storage_type="session"),
        dcc.Loading(
            children=html.Div(id="label-grid", className="grid-shell"),
            id="label-grid-loading",
            type="default",
            delay_show=250,
            color="#58a6ff",
            className="specgen-loading",
            parent_className="specgen-loading-wrap",
        ),
    ])
