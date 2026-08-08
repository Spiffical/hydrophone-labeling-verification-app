from dash import dcc, html
import dash_bootstrap_components as dbc
import os

from app.components.modal import create_spectrogram_modal
from app.components.folder_browser import create_folder_browser_modal
from app.layouts.label_mode import create_label_layout
from app.layouts.verify_mode import (
    create_verify_data_menu,
    create_verify_layout,
    create_verify_result_controls,
    create_verify_review_menu,
)
from app.layouts.explore_mode import create_explore_layout
from app.layouts.display_controls import create_display_range_bar
from app.layouts.data_config_panel import create_data_config_modal, create_predictions_warning


def create_main_layout(config: dict) -> html.Div:
    initial_mode = config.get("mode") or config.get("data", {}).get("mode") or "label"
    data_cfg = config.get("data", {}) if isinstance(config.get("data"), dict) else {}
    label_cfg = config.get("label", {}) if isinstance(config.get("label"), dict) else {}
    verify_cfg = config.get("verify", {}) if isinstance(config.get("verify"), dict) else {}
    initial_data_root = data_cfg.get("data_dir")
    if not initial_data_root and initial_mode == "label":
        initial_data_root = data_cfg.get("spectrogram_folder") or label_cfg.get("folder")
    if not initial_data_root and initial_mode in {"verify", "explore"}:
        initial_data_root = verify_cfg.get("dashboard_root")
    initial_data_dir = initial_data_root or os.path.expanduser("~")
    has_data_root = bool(initial_data_root)
    initial_load_trigger = (
        {
            "timestamp": 0,
            "mode": initial_mode,
            "source": "startup",
            "config": config,
            "date_value": verify_cfg.get("date") if initial_mode == "verify" else None,
            "device_value": verify_cfg.get("hydrophone") if initial_mode == "verify" else None,
        }
        if has_data_root
        else None
    )

    initial_theme = str(os.getenv("HYDROPHONE_UI_THEME", "light")).strip().lower()
    if initial_theme not in {"light", "dark"}:
        initial_theme = "light"

    return html.Div([
        # ── Stores ──────────────────────────────────────────────────
        dcc.Store(id="config-store", data=config),
        dcc.Store(id="label-data-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-data-store", data=None, storage_type="memory"),
        dcc.Store(id="explore-data-store", data=None, storage_type="memory"),
        dcc.Store(id="active-item-store", data=None, storage_type="memory"),
        dcc.Store(id="label-editor-clicks", data={}, storage_type="memory"),
        dcc.Store(id="user-profile-store", data={"name": "", "email": ""}, storage_type="local"),
        dcc.Store(id="profile-reset-applied-store", data=False, storage_type="session"),
        dcc.Store(id="theme-store", data=initial_theme, storage_type="local"),
        dcc.Store(id="verify-thresholds-store", data={"__global__": 0.5}, storage_type="memory"),
        dcc.Store(id="verify-class-filter", data=None, storage_type="memory"),
        dcc.Store(id="verify-class-filter-options", data=[], storage_type="memory"),
        dcc.Store(id="verify-class-filter-expanded", data=[], storage_type="memory"),
        dcc.Store(
            id="tab-filter-state-store",
            data={
                "label": {"date": None, "device": None},
                "verify": {"date": None, "device": None},
                "explore": {"date": None, "device": None},
            },
            storage_type="session",
        ),
        dcc.Store(id="folder-browser-path-store", data=initial_data_dir, storage_type="memory"),
        dcc.Store(id="folder-browser-selected-store", data=None, storage_type="memory"),
        dcc.Store(id="path-browse-target-store", data=None, storage_type="memory"),
        dcc.Store(id="data-root-path-store", data=initial_data_root, storage_type="memory"),
        dcc.Store(id="predictions-files-store", data=None, storage_type="memory"),
        dcc.Store(id="data-discovery-store", data=None, storage_type="memory"),
        dcc.Store(id="data-load-trigger-store", data=initial_load_trigger, storage_type="memory"),
        dcc.Store(id="label-ui-ready-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-ui-ready-store", data=None, storage_type="memory"),
        dcc.Store(id="explore-ui-ready-store", data=None, storage_type="memory"),
        dcc.Store(id="label-page-specgen-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-page-specgen-store", data=None, storage_type="memory"),
        dcc.Store(id="explore-page-specgen-store", data=None, storage_type="memory"),
        dcc.Store(id="specgen-overlay-preview-store", data=None, storage_type="memory"),
        dcc.Store(id="specgen-overlay-request-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-all-dates-request-store", data=None, storage_type="memory"),
        dcc.Store(id="verify-all-dates-ready-store", data=None, storage_type="memory"),
        dcc.Interval(id="specgen-overlay-poll", interval=1000, n_intervals=0, disabled=True, max_intervals=-1),
        dcc.Interval(id="verify-all-dates-poll", interval=1500, n_intervals=0, disabled=True, max_intervals=-1),
        html.Button("", id="specgen-overlay-dom-ready-signal", n_clicks=0, style={"display": "none"}),
        dcc.Store(id="verify-badge-event-store", data={"last_key": ""}, storage_type="memory"),
        dcc.Store(id="modal-image-clicks", data=0),
        dcc.Store(
            id="modal-audio-settings-store",
            data={
                "pitch": 1.0,
                "eq_20": 0.0,
                "eq_40": 0.0,
                "eq_80": 0.0,
                "eq_160": 0.0,
                "eq_315": 0.0,
                "eq_630": 0.0,
                "eq_1250": 0.0,
                "eq_2500": 0.0,
                "eq_5000": 0.0,
                "eq_10000": 0.0,
                "eq_16000": 0.0,
                "gain": 1.0,
                "visible_filter": False,
            },
            storage_type="local",
        ),

        # Active tab store (replaces dcc.Tabs value)
        dcc.Store(id="mode-tabs", data=initial_mode, storage_type="memory"),

        # Dummy elements for clientside callbacks
        dcc.Store(id="dummy-output", data=None, storage_type="memory"),
        html.Div(id="dummy-output-audio", style={"display": "none"}),

        dbc.Container([
            # ── Compact workspace command bar ──────────────────────
            html.Header(
                [
                    html.Div(
                        [
                            html.I(className="bi bi-soundwave command-brand-icon"),
                            html.Span("Unified Labeling Tool", className="command-brand-title"),
                        ],
                        className="command-brand",
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Label",
                                id="tab-btn-label",
                                className=(
                                    "mode-tab mode-tab--active"
                                    if initial_mode == "label"
                                    else "mode-tab"
                                ),
                            ),
                            html.Button(
                                "Verify",
                                id="tab-btn-verify",
                                className=(
                                    "mode-tab mode-tab--active"
                                    if initial_mode == "verify"
                                    else "mode-tab"
                                ),
                            ),
                            html.Button(
                                "Explore",
                                id="tab-btn-explore",
                                className=(
                                    "mode-tab mode-tab--active"
                                    if initial_mode == "explore"
                                    else "mode-tab"
                                ),
                            ),
                        ],
                        className="tab-buttons command-mode-tabs",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.I(className="bi bi-calendar3 command-select-icon"),
                                    dcc.Dropdown(
                                        id="global-date-selector",
                                        placeholder="Date",
                                        className="control-dropdown command-dropdown",
                                    ),
                                ],
                                className="command-select command-select--date",
                            ),
                            html.Div(
                                [
                                    html.I(className="bi bi-broadcast-pin command-select-icon"),
                                    dcc.Dropdown(
                                        id="global-device-selector",
                                        placeholder="Device",
                                        className="control-dropdown command-dropdown",
                                    ),
                                ],
                                className="command-select command-select--device",
                            ),
                        ],
                        id="global-selector-container",
                        className="command-source-selectors",
                    ),
                    create_verify_review_menu(),
                    create_display_range_bar(
                        "verify",
                        display_cfg=config.get("display", {}),
                        compact=True,
                        config=config,
                    ),
                    create_verify_data_menu(config),
                    create_verify_result_controls(),
                    html.Div(
                        [
                            html.Button(
                                html.I(className="bi bi-gear"),
                                id="app-config-btn",
                                className="icon-btn",
                                n_clicks=0,
                                type="button",
                                title="Application settings",
                                **{"aria-label": "Application settings"},
                            ),
                            html.Button(
                                html.I(className="bi bi-moon-stars"),
                                id="theme-toggle",
                                className="icon-btn theme-btn",
                                n_clicks=0,
                                type="button",
                                title="Toggle dark mode",
                                **{"aria-label": "Toggle dark mode"},
                            ),
                            html.Button(
                                [
                                    html.I(className="bi bi-person-circle"),
                                    html.Div(
                                        [
                                            html.Span(
                                                "Anonymous",
                                                id="profile-name-display",
                                                className="profile-name",
                                            ),
                                            html.Span(
                                                "email not set",
                                                id="profile-email-display",
                                                className="profile-email",
                                            ),
                                        ],
                                        className="profile-text",
                                    ),
                                ],
                                id="profile-btn",
                                className="profile-summary",
                                n_clicks=0,
                                type="button",
                                title="Profile",
                            ),
                        ],
                        className="header-actions command-account-actions",
                    ),
                ],
                id="app-command-bar",
                className=(
                    "app-command-bar app-command-bar--verify"
                    if initial_mode == "verify"
                    else "app-command-bar"
                ),
            ),

            html.Div(id="profile-required-banner", className="profile-required-banner", style={"display": "none"}),

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
            create_spectrogram_modal(config),
            create_folder_browser_modal(),
            create_data_config_modal(),
            create_predictions_warning(),

            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Add/Edit Label(s)")),
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
                        dbc.Input(id="profile-name", type="text", placeholder="Your name", required=True),
                        dbc.Label("Email", html_for="profile-email", className="small fw-semibold mt-3"),
                        dbc.Input(id="profile-email", type="email", placeholder="name@example.com", required=True),
                        html.Div(
                            "Name and a valid email are required for labeling and verification.",
                            id="profile-required-message",
                            className="profile-required-message mt-2",
                        ),
                    ])
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="profile-cancel", color="secondary"),
                    dbc.Button("Save", id="profile-save", color="primary"),
                ]),
            ], id="profile-modal", is_open=False),

            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Unsaved Changes"), close_button=False),
                    dbc.ModalBody(id="mode-switch-unsaved-message"),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Stay",
                            id="mode-switch-unsaved-stay",
                            color="primary",
                            n_clicks=0,
                        )
                    ),
                ],
                id="mode-switch-unsaved-modal",
                is_open=False,
                centered=True,
                backdrop="static",
                keyboard=False,
            ),

            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Application settings")),
                dbc.ModalBody([
                    dbc.Form([
                        dbc.Label("Spectrograms per page", html_for="app-config-items-per-page", className="small fw-semibold"),
                        dbc.Input(
                            id="app-config-items-per-page",
                            type="number",
                            min=1,
                            step=1,
                        ),
                        dbc.FormText("Controls how many spectrograms are shown per page."),
                        dbc.Label("Spectrogram cache size", html_for="app-config-cache-size", className="small fw-semibold mt-3"),
                        dbc.Input(
                            id="app-config-cache-size",
                            type="number",
                            min=1,
                            step=1,
                        ),
                        dbc.FormText("Higher values keep more spectrograms cached in memory."),
                    ])
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="app-config-cancel", color="secondary", outline=True),
                    dbc.Button("Save", id="app-config-save", color="primary"),
                ]),
            ], id="app-config-modal", is_open=False),

            html.Div(
                [
                    html.Div(
                        [
                            dbc.Spinner(color="primary", size="lg"),
                            html.Div("Loading...", id="data-load-title", className="data-load-title"),
                            html.Div(
                                "Preparing workspace.",
                                id="data-load-subtitle",
                                className="data-load-subtitle",
                            ),
                        ],
                        className="data-load-card",
                        role="status",
                        **{"aria-live": "polite"},
                    )
                ],
                id="data-config-loading-overlay",
                className="data-load-overlay",
                style={"display": "none"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Loading spectrograms", id="specgen-load-title", className="specgen-load-title"),
                            html.Div(
                                "Preparing current page.",
                                id="specgen-load-subtitle",
                                className="specgen-load-subtitle",
                            ),
                            html.Div(
                                html.Div(id="specgen-load-progress-fill", className="specgen-load-progress-fill"),
                                id="specgen-load-progress-track",
                                className="specgen-load-progress-track",
                                role="progressbar",
                                **{"aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "0"},
                            ),
                            html.Div(
                                "Preparing page",
                                id="specgen-load-progress-text",
                                className="specgen-load-progress-text",
                            ),
                        ],
                        className="specgen-load-card",
                        role="status",
                        **{"aria-live": "polite"},
                    )
                ],
                id="specgen-page-loading-overlay",
                className="specgen-page-overlay",
                style={"display": "none"},
            ),
        ], fluid=True, className="app-inner"),
    ], id="app-shell", className=f"app-shell theme-{initial_theme}")
