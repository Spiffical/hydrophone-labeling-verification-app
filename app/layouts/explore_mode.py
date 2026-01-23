from dash import html, dcc
import dash_bootstrap_components as dbc


def create_explore_layout(config: dict) -> html.Div:
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
        ], className="panel-card"),

        html.Div(id="explore-summary", className="summary-bar"),
        dcc.Loading(html.Div(id="explore-grid", className="grid-shell"), type="circle"),
    ])
