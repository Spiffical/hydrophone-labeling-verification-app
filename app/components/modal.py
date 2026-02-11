import dash_bootstrap_components as dbc
from dash import dcc, html

def create_spectrogram_modal():
    """
    Create a large modal for zoomed-in spectrogram view with Plotly interactivity.
    """
    return dbc.Modal(
        [
            dbc.ModalHeader(
                html.Div(
                    [
                        html.H4(id='modal-header', className="modal-title-text"),
                        html.Div(
                            [
                                dbc.Button(
                                    html.Span("←", className="modal-nav-arrow"),
                                    id="modal-nav-prev",
                                    color="light",
                                    size="sm",
                                    n_clicks=0,
                                    className="modal-nav-btn",
                                    title="Previous spectrogram",
                                ),
                                html.Span("1 / 1", id="modal-nav-position", className="modal-nav-position"),
                                dbc.Button(
                                    html.Span("→", className="modal-nav-arrow"),
                                    id="modal-nav-next",
                                    color="light",
                                    size="sm",
                                    n_clicks=0,
                                    className="modal-nav-btn",
                                    title="Next spectrogram",
                                ),
                            ],
                            className="modal-nav-controls",
                        ),
                    ],
                    className="modal-header-row",
                ),
                className="spectrogram-modal-header",
                close_button=True,
            ),
            dbc.ModalBody([
                # Control panel for modal settings
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.Label("Colormap", className="small fw-semibold text-muted mb-2"),
                            dcc.RadioItems(
                                id='modal-colormap-toggle',
                                options=[
                                    {'label': ' Default', 'value': 'default'},
                                    {'label': ' Hydrophone', 'value': 'hydrophone'},
                                ],
                                value='default',
                                className="custom-radio-group",
                                labelStyle={
                                    'display': 'inline-flex',
                                    'align-items': 'center',
                                    'margin-right': '20px',
                                    'cursor': 'pointer'
                                },
                                inputStyle={'margin-right': '6px'}
                            )
                        ], width=6),
                        dbc.Col([
                            html.Label("Y-Axis Scale", className="small fw-semibold text-muted mb-2"),
                            dcc.RadioItems(
                                id='modal-y-axis-toggle',
                                options=[
                                    {'label': ' Linear', 'value': 'linear'},
                                    {'label': ' Logarithmic', 'value': 'log'},
                                ],
                                value='linear',
                                className="custom-radio-group",
                                labelStyle={
                                    'display': 'inline-flex',
                                    'align-items': 'center',
                                    'margin-right': '20px',
                                    'cursor': 'pointer'
                                },
                                inputStyle={'margin-right': '6px'}
                            )
                        ], width=6),
                    ])
                ], className="modal-controls-card mb-4"),
                
                # Interactive Plotly Graph
                dbc.Card([
                    dbc.CardBody([
                        dcc.Graph(
                            id='modal-image-graph',
                            style={'height': '500px'},
                            config={
                                'displayModeBar': True, 
                                'displaylogo': False,
                                'modeBarButtonsToRemove': ['lasso2d', 'select2d']
                            }
                        )
                    ], className="p-0")
                ], className="spectrogram-zoom-card mb-4"),

                # Bottom split layout: labels/actions + audio controls
                html.Div(
                    [
                        html.Div(
                            id="modal-item-actions",
                            className="modal-item-actions modal-bottom-pane",
                        ),
                        html.Div(
                            id='modal-audio-player',
                            className="modal-audio-section modal-bottom-pane",
                        ),
                    ],
                    className="modal-bottom-layout",
                ),
                
                # Current filename store
                dcc.Store(id='current-filename', data=None)
            ], className="p-4"),
            
            dbc.ModalFooter([
                dbc.Button(
                    "Close", 
                    id='close-modal', 
                    color="secondary",
                    className="px-4"
                )
            ]),
        ],
        id='image-modal',
        size='xl',
        is_open=False,
        backdrop='static',
        className="spectrogram-zoom-modal"
    )
