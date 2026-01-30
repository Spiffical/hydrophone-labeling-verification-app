from dash import dcc, html
import dash_bootstrap_components as dbc
import os

from app.components.modal import create_spectrogram_modal
from app.components.folder_browser import create_folder_browser_modal, create_browse_button
from app.layouts.label_mode import create_label_layout
from app.layouts.verify_mode import create_verify_layout
from app.layouts.explore_mode import create_explore_layout
from app.layouts.data_config_panel import create_data_config_modal, create_predictions_warning


def create_main_layout(config: dict) -> html.Div:
    # Determine initial data directory
    initial_data_dir = config.get("data", {}).get("data_dir") or os.path.expanduser("~")
    initial_mode = config.get("mode", "label")

    return html.Div([
        # ── Stores ──────────────────────────────────────────────────
        dcc.Store(id="config-store", data=config),
        dcc.Store(id="label-data-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-data-store", data=None, storage_type="memory"),
        dcc.Store(id="explore-data-store", data=None, storage_type="memory"),
        dcc.Store(id="active-item-store", data=None, storage_type="memory"),
        dcc.Store(id="label-editor-clicks", data={}, storage_type="memory"),
        dcc.Store(id="user-profile-store", data={"name": "", "role": ""}, storage_type="local"),
        dcc.Store(id="theme-store", data="light", storage_type="local"),
        dcc.Store(id="verify-thresholds-store", data={"__global__": 0.5}, storage_type="memory"),
        dcc.Store(id="folder-browser-path-store", data=initial_data_dir, storage_type="memory"),
        dcc.Store(id="folder-browser-selected-store", data=None, storage_type="memory"),
        dcc.Store(id="path-browse-target-store", data=None, storage_type="memory"),
        dcc.Store(id="data-discovery-store", data=None, storage_type="memory"),
        dcc.Store(id="data-load-trigger-store", data=0, storage_type="memory"),
        dcc.Store(id="modal-image-clicks", data=0),

        # Active tab store (replaces dcc.Tabs value)
        dcc.Store(id="mode-tabs", data=initial_mode, storage_type="memory"),

        # Dummy element for clientside callbacks
        html.Div(id="dummy-output", style={"display": "none"}),

        dbc.Container([
            # ── Header ──────────────────────────────────────────────
            html.Div([
                html.Div([
                    html.Span("Hydrophone Acoustic Review Suite", className="brand-kicker"),
                    html.H1("Unified labeling Tool", className="brand-title"),
                ], className="brand-block"),

                html.Div([
                    dbc.Switch(
                        id="theme-toggle",
                        label="Dark",
                        value=False,
                        className="theme-toggle",
                    ),
                    dbc.Button(
                        "Profile",
                        id="profile-btn",
                        color="light",
                        className="profile-btn ms-2",
                    ),
                ], className="header-actions"),
            ], className="app-header"),

            # ── Tab buttons ─────────────────────────────────────────
            html.Div([
                html.Button("Label", id="tab-btn-label",
                            className="mode-tab mode-tab--active" if initial_mode == "label" else "mode-tab"),
                html.Button("Verify", id="tab-btn-verify",
                            className="mode-tab mode-tab--active" if initial_mode == "verify" else "mode-tab"),
                html.Button("Explore", id="tab-btn-explore",
                            className="mode-tab mode-tab--active" if initial_mode == "explore" else "mode-tab"),
            ], className="tab-buttons"),

            # ── Data selection bar ──────────────────────────────────
            html.Div([
                dbc.Row([
                    dbc.Col([
                        create_browse_button(),
                    ], width="auto"),
                    dbc.Col([
                        dcc.Dropdown(
                            id="global-date-selector",
                            placeholder="Date",
                            className="control-dropdown"
                        ),
                    ], width=4),
                    dbc.Col([
                        dcc.Dropdown(
                            id="global-device-selector",
                            placeholder="Device",
                            className="control-dropdown"
                        ),
                    ], width=4),
                    dbc.Col([
                        dbc.Button("Load", id="global-load-btn", color="success", className="w-100"),
                    ], width=2),
                ], className="g-2 align-items-center"),
                html.Div([
                    html.Small("Data: ", className="text-muted small"),
                    html.Span(id="global-data-dir-display", className="mono-muted small me-3",
                              children=config.get("data", {}).get("data_dir") or "Not selected"),
                    html.Small("Active: ", className="text-muted small"),
                    html.Span(id="global-active-selection", className="mono-muted small"),
                ], className="mt-1 text-end", style={"min-height": "1.5em"}),
            ], id="global-selector-container", className="data-selection-bar"),

            # ── Tab content panels ──────────────────────────────────
            html.Div(
                create_label_layout(config),
                id="label-tab-content",
                style={"display": "block"} if initial_mode == "label" else {"display": "none"},
            ),
            html.Div(
                create_verify_layout(config),
                id="verify-tab-content",
                style={"display": "block"} if initial_mode == "verify" else {"display": "none"},
            ),
            html.Div(
                create_explore_layout(config),
                id="explore-tab-content",
                style={"display": "block"} if initial_mode == "explore" else {"display": "none"},
            ),

            # ── Modals ─────────────────────────────────────────────
            create_spectrogram_modal(),
            create_folder_browser_modal(),
            create_data_config_modal(),
            create_predictions_warning(),

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
