from dash import html, dcc
import dash_bootstrap_components as dbc


def create_verify_layout(config: dict) -> html.Div:
    verify_cfg = config.get("verify", {})

    return html.Div([
        html.Div([
            html.H2("Verify Mode", className="section-title"),
            html.P("Review ML predictions and record verification", className="section-subtitle"),
        ], className="section-header"),

        html.Div([
            html.Div([
                html.Div([
                    html.Small("Dashboard root", className="text-muted"),
                    html.Div(verify_cfg.get("dashboard_root") or "Not set", className="mono-muted"),
                ], className="info-line"),
                html.Div([
                    html.Small("Default date", className="text-muted"),
                    html.Div(verify_cfg.get("date") or "Not set", className="mono-muted"),
                ], className="info-line"),
                html.Div([
                    html.Small("Hydrophone", className="text-muted"),
                    html.Div(verify_cfg.get("hydrophone") or "Not set", className="mono-muted"),
                ], className="info-line"),
            ], className="info-grid"),

            html.Div([
                dbc.Button("Reload data", id="verify-reload", color="primary", className="primary-btn"),
                html.Div([
                    html.Label("Thresholds", className="small fw-semibold"),
                    html.Div([
                        html.Div([
                            html.Small("Class", className="text-muted"),
                            dcc.Dropdown(
                                id="verify-class-filter",
                                options=[{"label": "All classes", "value": "all"}],
                                value="all",
                                clearable=False,
                                placeholder="Select class",
                                className="control-dropdown",
                            ),
                        ], className="threshold-field"),
                        html.Div([
                            html.Small("Value", className="text-muted"),
                            dcc.Slider(
                                id="verify-threshold-slider",
                                min=0,
                                max=1,
                                value=0.5,
                                step=0.01,
                                marks=None,
                                tooltip={"placement": "top", "always_visible": True},
                                className="control-slider",
                            ),
                        ], className="threshold-field"),
                    ], className="threshold-row"),
                ], className="threshold-block"),
            ], className="control-row control-row--wide"),
        ], className="panel-card"),

        html.Div(id="verify-summary", className="summary-bar"),
        dcc.Loading(html.Div(id="verify-grid", className="grid-shell"), type="circle"),
    ])
