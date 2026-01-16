from dash import html, dcc
import dash_bootstrap_components as dbc


def create_explore_layout(config: dict) -> html.Div:
    return html.Div([
        html.Div([
            html.H2("Explore Mode", className="section-title"),
            html.P("Browse previously labeled datasets", className="section-subtitle"),
        ], className="section-header"),

        html.Div([
            html.Div([
                dbc.Button("Reload data", id="explore-reload", color="primary", className="primary-btn"),
                html.Div("Export and summary controls will appear here.", className="text-muted"),
            ], className="control-row"),
        ], className="panel-card"),

        html.Div(id="explore-summary", className="summary-bar"),
        dcc.Loading(html.Div(id="explore-grid", className="grid-shell"), type="circle"),
    ])
