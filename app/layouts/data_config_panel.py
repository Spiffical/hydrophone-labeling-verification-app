"""
Data configuration panel component.
Shows detected data structure and allows manual override of paths.
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_data_config_modal() -> dbc.Modal:
    """Create the data configuration modal."""
    return dbc.Modal([
        dbc.ModalHeader([
            dbc.ModalTitle("Data Configuration"),
            dbc.Button("×", id="data-config-close", className="btn-close ms-auto"),
        ], close_button=False),
        dbc.ModalBody([
            # Structure info
            html.Div([
                html.Div([
                    html.Span("Structure: ", className="text-muted"),
                    html.Span(id="data-config-structure-type", className="fw-semibold"),
                ]),
                html.Small(id="data-config-structure-message", className="text-muted"),
            ], className="mb-4 p-3 bg-light rounded"),
            
            # Spectrogram folder
            html.Div([
                html.Label("Spectrogram Folder", className="fw-semibold mb-1"),
                dbc.InputGroup([
                    dbc.Input(
                        id="data-config-spec-folder",
                        type="text",
                        placeholder="Path to spectrogram files",
                        className="mono-muted",
                    ),
                    dbc.Button(
                        html.I(className="bi bi-folder2-open"),
                        id="data-config-spec-browse",
                        color="secondary",
                        outline=True,
                    ),
                ]),
                html.Div(id="data-config-spec-info", className="mt-1"),
            ], className="mb-3"),
            
            # Audio folder
            html.Div([
                html.Label("Audio Folder", className="fw-semibold mb-1"),
                dbc.InputGroup([
                    dbc.Input(
                        id="data-config-audio-folder",
                        type="text",
                        placeholder="Path to audio files (optional)",
                        className="mono-muted",
                    ),
                    dbc.Button(
                        html.I(className="bi bi-folder2-open"),
                        id="data-config-audio-browse",
                        color="secondary",
                        outline=True,
                    ),
                ]),
                html.Div(id="data-config-audio-info", className="mt-1"),
            ], className="mb-3"),
            
            # Predictions file
            html.Div([
                html.Label("Predictions File", className="fw-semibold mb-1"),
                dbc.InputGroup([
                    dbc.Input(
                        id="data-config-predictions-file",
                        type="text",
                        placeholder="Path to predictions.json (optional for Label mode)",
                        className="mono-muted",
                    ),
                    dbc.Button(
                        html.I(className="bi bi-file-earmark"),
                        id="data-config-predictions-browse",
                        color="secondary",
                        outline=True,
                    ),
                ]),
                html.Div(id="data-config-predictions-info", className="mt-1"),
            ], className="mb-3"),
        ], className="data-config-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="data-config-cancel", color="secondary", outline=True),
            dbc.Button("Load Data", id="data-config-load", color="primary"),
        ]),
    ], id="data-config-modal", size="lg", is_open=False, centered=True)


def create_config_info_badge(found: bool, count: int = 0, ext_info: str = "") -> html.Div:
    """Create an info badge showing what was found."""
    if found and count > 0:
        return html.Div([
            dbc.Badge("✓ Found", color="success", className="me-2"),
            html.Small(f"{count} files" + (f" ({ext_info})" if ext_info else ""), className="text-muted"),
        ])
    elif found:
        return html.Div([
            dbc.Badge("✓ Found", color="success"),
        ])
    else:
        return html.Div([
            dbc.Badge("Not found", color="warning", className="me-2"),
            html.Small("Optional - click Browse to select", className="text-muted"),
        ])


def create_predictions_warning() -> dbc.Alert:
    """Create a warning banner for missing predictions."""
    return dbc.Alert([
        html.H5([
            html.I(className="bi bi-exclamation-triangle-fill me-2"),
            "No Predictions File Found"
        ], className="alert-heading"),
        html.P([
            "Verify mode requires ML predictions to compare with expert labels. ",
            "You can still use Label mode to annotate spectrograms manually."
        ]),
        html.Hr(),
        html.Div([
            dbc.Button(
                [html.I(className="bi bi-file-earmark-plus me-2"), "Select Predictions File"],
                id="verify-select-predictions-btn",
                color="warning",
                className="me-2",
            ),
            dbc.Button(
                "Continue in Label Mode",
                id="verify-continue-label-btn",
                color="secondary",
                outline=True,
            ),
        ]),
    ], id="verify-predictions-warning", color="warning", is_open=False, dismissable=True)
