from dash import html, dcc
import dash_bootstrap_components as dbc

from app.layouts.display_controls import create_display_range_bar


def create_explore_layout(config: dict) -> html.Div:
    display_cfg = config.get("display", {})

    return html.Div([
        html.Div([
            html.H2("Explore Mode", className="section-title"),
            html.P("Browse previously labeled datasets", className="section-subtitle"),
        ], className="section-header"),

        html.Div([
            dbc.Row([
                dbc.Col([
                    dbc.Button("Reload dataset", id="explore-reload", color="primary", className="w-100"),
                ], md=2, sm=4, xs=12),
                dbc.Col([
                    html.Div("Export and summary controls will appear here.", className="text-muted small"),
                ], md=10, sm=8, xs=12),
            ], className="align-items-center g-3"),
            html.Div([
                dbc.Switch(
                    id="explore-colormap-toggle",
                    label="Hydrophone colormap",
                    value=display_cfg.get("colormap") == "hydrophone",
                    className="control-switch",
                ),
                dbc.Switch(
                    id="explore-yaxis-toggle",
                    label="Log y-axis",
                    value=display_cfg.get("y_axis_scale") == "log",
                    className="control-switch",
                ),
            ], className="control-row mt-3"),
        ], className="panel-card"),

        html.Div([
            html.Div("Page Navigation", className="pagination-sticky-title"),
            html.Div([
                dbc.Button("← Previous", id="explore-prev-page", n_clicks=0, color="primary", size="sm"),
                dbc.Button("Next →", id="explore-next-page", n_clicks=0, color="primary", size="sm"),
                html.Div([
                    html.Label("Go to page:", className="pagination-goto-label"),
                    dbc.Input(
                        id="explore-page-input",
                        type="number",
                        min=1,
                        step=1,
                        value=1,
                        className="pagination-page-input",
                    ),
                    dbc.Button("Go", id="explore-goto-page", n_clicks=0, color="secondary", size="sm"),
                ], className="pagination-goto-group"),
                html.Span(id="explore-page-info", className="pagination-page-info"),
            ], className="pagination-controls"),
        ], className="pagination-sticky-bar"),
        create_display_range_bar("explore", display_cfg=display_cfg),

        html.Div(id="explore-summary", className="summary-bar"),
        dcc.Store(id="explore-current-page", data=0, storage_type="session"),
        dcc.Loading(
            children=html.Div(id="explore-grid", className="grid-shell"),
            id="explore-grid-loading",
            type="default",
            delay_show=250,
            color="#58a6ff",
            className="specgen-loading",
            parent_className="specgen-loading-wrap",
        ),
    ])
