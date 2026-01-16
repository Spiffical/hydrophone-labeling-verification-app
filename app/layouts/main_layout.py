from dash import dcc, html
import dash_bootstrap_components as dbc

from app.components.modal import create_spectrogram_modal
from app.layouts.label_mode import create_label_layout
from app.layouts.verify_mode import create_verify_layout
from app.layouts.explore_mode import create_explore_layout


def create_main_layout(config: dict) -> html.Div:
    return html.Div([
        dcc.Store(id="config-store", data=config),
        dcc.Store(id="data-store", data=None, storage_type="memory"),
        dcc.Store(id="active-item-store", data=None, storage_type="memory"),
        dcc.Store(id="label-editor-clicks", data={}, storage_type="memory"),
        dcc.Store(id="user-profile-store", data={"name": "", "role": ""}, storage_type="local"),
        dcc.Store(id="theme-store", data="light", storage_type="local"),
        dcc.Store(id="verify-thresholds-store", data={"__global__": 0.5}, storage_type="memory"),
        
        # New stores for modal state
        dcc.Store(id="modal-image-clicks", data=0),
        
        # Dummy element for clientside callbacks
        html.Div(id="dummy-output", style={"display": "none"}),

        dbc.Container([
            html.Div([
                html.Div([
                    html.Span("Hydrophone Acoustic Review Suite", className="brand-kicker"),
                    html.H1("Unified Labeling & Verification Tool", className="brand-title"),
                    html.P(
                        "Label, verify, and explore spectrogram datasets from a single interface.",
                        className="brand-subtitle",
                    ),
                ], className="brand-block"),
                html.Div([
                    dbc.Switch(
                        id="theme-toggle",
                        label="Dark mode",
                        value=False,
                        className="theme-toggle",
                    ),
                    dbc.Button(
                        "Profile",
                        id="profile-btn",
                        color="light",
                        className="profile-btn",
                    ),
                ], className="header-actions"),
            ], className="app-header"),

            dcc.Tabs(
                id="mode-tabs",
                value=config.get("mode", "label"),
                className="mode-tabs",
                parent_className="mode-tabs-wrap",
                children=[
                    dcc.Tab(
                        label="Label",
                        value="label",
                        className="mode-tab",
                        selected_className="mode-tab--active",
                        children=create_label_layout(config),
                    ),
                    dcc.Tab(
                        label="Verify",
                        value="verify",
                        className="mode-tab",
                        selected_className="mode-tab--active",
                        children=create_verify_layout(config),
                    ),
                    dcc.Tab(
                        label="Explore",
                        value="explore",
                        className="mode-tab",
                        selected_className="mode-tab--active",
                        children=create_explore_layout(config),
                    ),
                ],
            ),

            # Modals
            create_spectrogram_modal(),
            
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Edit Labels")),
                dbc.ModalBody(html.Div(id="label-editor-body")),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="label-editor-cancel", color="secondary"),
                    dbc.Button("Save Labels", id="label-editor-save", color="primary"),
                ]),
            ], id="label-editor-modal", is_open=False, size="lg"),

            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Profile")),
                dbc.ModalBody([
                    dbc.Form([
                        dbc.Label("Name", html_for="profile-name", className="small fw-semibold"),
                        dbc.Input(id="profile-name", type="text", placeholder="Your name"),
                        dbc.Label("Role", html_for="profile-role", className="small fw-semibold mt-3"),
                        dbc.Input(id="profile-role", type="text", placeholder="e.g. verifier, labeler"),
                    ])
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="profile-cancel", color="secondary"),
                    dbc.Button("Save", id="profile-save", color="primary"),
                ]),
            ], id="profile-modal", is_open=False),
        ], fluid=True, className="app-inner"),
    ], id="app-shell", className="app-shell theme-light")
