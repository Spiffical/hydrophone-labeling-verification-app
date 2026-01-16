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
                    html.Div(label_cfg.get("folder") or "Not set", className="mono-muted"),
                ], className="info-line"),
                html.Div([
                    html.Small("Audio folder", className="text-muted"),
                    html.Div(label_cfg.get("audio_folder") or "Not set", className="mono-muted"),
                ], className="info-line"),
                html.Div([
                    html.Small("Output labels", className="text-muted"),
                    html.Div(label_cfg.get("output_file") or "Not set", className="mono-muted"),
                ], className="info-line"),
            ], className="info-grid"),

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
        dcc.Loading(html.Div(id="label-grid", className="grid-shell"), type="circle"),
    ])
