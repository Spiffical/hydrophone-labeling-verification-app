import dash_bootstrap_components as dbc
from dash import dcc, html


def create_spectrogram_modal():
    """
    Create a large modal for zoomed-in spectrogram view with Plotly interactivity.
    """
    main_modal = dbc.Modal(
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
                close_button=False,
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
                    ]),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Div(
                                        [
                                            html.Label("Frequency window (Hz)", className="display-range-label"),
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Using page range",
                                                        id="modal-yaxis-readout",
                                                        className="display-range-readout",
                                                    ),
                                                    dbc.Button(
                                                        "Use page range",
                                                        id="modal-yaxis-reset-btn",
                                                        color="secondary",
                                                        outline=True,
                                                        size="sm",
                                                        n_clicks=0,
                                                        className="display-range-reset",
                                                    ),
                                                ],
                                                className="display-range-actions",
                                            ),
                                        ],
                                        className="display-range-group-header",
                                    ),
                                    html.Div(
                                        dcc.RangeSlider(
                                            id="modal-yaxis-slider",
                                            min=0.0,
                                            max=2.0,
                                            value=[0.0, 2.0],
                                            marks={0.0: "1 Hz", 1.0: "10 Hz", 2.0: "100 Hz"},
                                            step=0.005,
                                            allowCross=False,
                                            updatemode="mouseup",
                                            tooltip={
                                                "placement": "bottom",
                                                "always_visible": False,
                                                "transform": "formatLogFrequencyHz",
                                            },
                                            className="control-slider display-range-slider",
                                        ),
                                        className="display-range-slider-shell",
                                    ),
                                    dbc.FormText(
                                        "Log-scaled slider. Reset returns to the current page range.",
                                        id="modal-yaxis-hint",
                                    ),
                                    dcc.Input(id="modal-yaxis-min-input", type="hidden"),
                                    dcc.Input(id="modal-yaxis-max-input", type="hidden"),
                                ],
                                md=6,
                                xs=12,
                                className="display-range-group",
                            ),
                            dbc.Col(
                                [
                                    html.Div(
                                        [
                                            html.Label("Contrast (dB/Hz)", className="display-range-label"),
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Auto contrast",
                                                        id="modal-colorbar-readout",
                                                        className="display-range-readout",
                                                    ),
                                                    dbc.Button(
                                                        "Auto contrast",
                                                        id="modal-colorbar-reset-btn",
                                                        color="secondary",
                                                        outline=True,
                                                        size="sm",
                                                        n_clicks=0,
                                                        className="display-range-reset",
                                                    ),
                                                ],
                                                className="display-range-actions",
                                            ),
                                        ],
                                        className="display-range-group-header",
                                    ),
                                    html.Div(
                                        dcc.RangeSlider(
                                            id="modal-colorbar-slider",
                                            min=-120.0,
                                            max=0.0,
                                            value=[-90.0, -10.0],
                                            marks={-120.0: "-120", -80.0: "-80", -40.0: "-40", 0.0: "0"},
                                            step=0.1,
                                            allowCross=False,
                                            updatemode="mouseup",
                                            tooltip={
                                                "placement": "bottom",
                                                "always_visible": False,
                                                "transform": "formatDecibelRange",
                                            },
                                            className="control-slider display-range-slider",
                                        ),
                                        className="display-range-slider-shell",
                                    ),
                                    dbc.FormText(
                                        "Reset returns to automatic contrast for the current spectrogram.",
                                        id="modal-colorbar-hint",
                                    ),
                                    dcc.Input(id="modal-colorbar-min-input", type="hidden"),
                                    dcc.Input(id="modal-colorbar-max-input", type="hidden"),
                                ],
                                md=6,
                                xs=12,
                                className="display-range-group",
                            ),
                        ],
                        className="g-3 mt-1",
                    ),
                    dcc.Store(
                        id="modal-display-range-defaults-store",
                        data={
                            "yaxis": [0.0, 2.0],
                            "yaxis_readout": "Using page range",
                            "colorbar": [-90.0, -10.0],
                            "colorbar_readout": "Auto contrast",
                        },
                    ),
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
                                'modeBarButtonsToAdd': ['drawrect', 'eraseshape'],
                                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                                # Keep shape editing enabled, but disable text/title editing.
                                'editable': False,
                                'edits': {
                                    'shapePosition': True,
                                    'annotationText': False,
                                    'annotationPosition': False,
                                    'titleText': False,
                                },
                            }
                        )
                    ], className="p-0")
                ], className="spectrogram-zoom-card mb-4"),

                html.Div(
                    "Use the BBox + button to draw a box for a label. Click + again to add another box for the same label. Delete boxes from the red × on each box.",
                    className="modal-bbox-hint mb-2",
                ),

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
                dcc.Store(id='current-filename', data=None),
                dcc.Store(id='modal-item-store', data=None),
                dcc.Store(id='modal-bbox-store', data={"item_id": None, "boxes": []}),
                dcc.Store(id='modal-active-box-label', data=None),
                dcc.Store(id='modal-unsaved-store', data={"dirty": False}),
                dcc.Store(id='modal-snapshot-store', data=None),
                dcc.Store(id='modal-pending-action-store', data=None),
                dcc.Store(id='modal-force-action-store', data=None),
                dcc.Store(id='modal-busy-store', data=False, storage_type='memory'),
            ], className="p-4"),

            dbc.ModalFooter([
                dbc.Button(
                    "Close",
                    id='close-modal',
                    color="secondary",
                    className="px-4"
                )
            ]),
            html.Div(
                html.Div("Updating modal...", className="modal-busy-indicator"),
                id="modal-busy-overlay",
                className="modal-busy-overlay",
                style={"display": "none"},
            ),
        ],
        id='image-modal',
        size='xl',
        is_open=False,
        backdrop='static',
        keyboard=False,
        className="spectrogram-zoom-modal"
    )

    unsaved_changes_modal = dbc.Modal(
        [
            dbc.ModalHeader("Unsaved Changes"),
            dbc.ModalBody(
                "You made label or bounding box edits that are not confirmed yet. "
                "Stay to confirm/save, or exit without saving."
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "Stay",
                        id="unsaved-stay-btn",
                        color="secondary",
                        className="me-2",
                        n_clicks=0,
                    ),
                    dbc.Button(
                        "Save & Exit",
                        id="unsaved-save-btn",
                        color="success",
                        className="me-2",
                        n_clicks=0,
                    ),
                    dbc.Button(
                        "Exit Without Saving",
                        id="unsaved-discard-btn",
                        color="danger",
                        n_clicks=0,
                    ),
                ]
            ),
        ],
        id="unsaved-changes-modal",
        is_open=False,
        centered=True,
        backdrop="static",
        keyboard=False,
    )

    return html.Div([main_modal, unsaved_changes_modal])
