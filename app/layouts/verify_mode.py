from dash import dcc, html
import dash_bootstrap_components as dbc

from app.components.folder_browser import create_browse_button
from app.layouts.review_dashboard import create_review_dashboard
from app.services.spectrogram_grid import (
    normalize_spectrogram_grid,
    spectrogram_grid_class,
)


def _create_spectrogram_grid_placeholder(config=None) -> html.Div:
    layout = normalize_spectrogram_grid(config)
    return html.Div(
        [
            html.Div(
                [
                    html.Div(className="spec-card-skeleton-title"),
                    html.Div("Preparing spectrogram cards...", className="spec-card-skeleton-image"),
                    html.Div(className="spec-card-skeleton-line"),
                    html.Div(className="spec-card-skeleton-line spec-card-skeleton-line--short"),
                ],
                className="spec-card-skeleton",
            )
            for _ in range(layout["items_per_page"])
        ],
        className=f"spec-grid-placeholder {spectrogram_grid_class(layout['columns'])}",
        style={"--spectrogram-grid-columns": str(layout["columns"])},
    )


def create_verify_data_menu(config: dict) -> html.Details:
    data_cfg = config.get("data", {})
    verify_cfg = config.get("verify", {})
    nested_verify_cfg = (
        data_cfg.get("verify", {}) if isinstance(data_cfg.get("verify"), dict) else {}
    )

    return html.Details(
        [
            html.Summary(
                [
                    html.I(className="bi bi-database"),
                    html.Span("Data"),
                    html.I(className="bi bi-chevron-down command-panel-caret"),
                ],
                className="command-tool-trigger",
                title="Data source",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Data source", className="command-popover-title"),
                            html.Div(
                                [
                                    create_browse_button(),
                                ],
                                className="command-data-actions",
                            ),
                        ],
                        className="command-popover-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Small("Data root", className="command-data-label"),
                                    html.Div(
                                        data_cfg.get("data_dir")
                                        or verify_cfg.get("dashboard_root")
                                        or nested_verify_cfg.get("dashboard_root")
                                        or "Not set",
                                        id="verify-data-root-display",
                                        className="command-data-value",
                                    ),
                                ],
                                className="command-data-row command-data-row--wide",
                            ),
                            html.Div(
                                [
                                    html.Small(
                                        "Spectrogram folder",
                                        className="command-data-label",
                                    ),
                                    html.Div(
                                        data_cfg.get("spectrogram_folder")
                                        or html.Span(
                                            "Loading spectrogram folder...",
                                            className="loading-path-text",
                                        ),
                                        id="verify-spec-folder-display",
                                        className="command-data-value",
                                    ),
                                ],
                                className="command-data-row",
                            ),
                            html.Div(
                                [
                                    html.Small("Audio folder", className="command-data-label"),
                                    html.Div(
                                        data_cfg.get("audio_folder")
                                        or html.Span(
                                            "Loading audio folder...",
                                            className="loading-path-text",
                                        ),
                                        id="verify-audio-folder-display",
                                        className="command-data-value",
                                    ),
                                ],
                                className="command-data-row",
                            ),
                            html.Div(
                                [
                                    html.Small(
                                        "Predictions file",
                                        className="command-data-label",
                                    ),
                                    html.Div(
                                        data_cfg.get("predictions_file")
                                        or nested_verify_cfg.get("predictions_json")
                                        or html.Span(
                                            "Loading predictions file...",
                                            className="loading-path-text",
                                        ),
                                        id="verify-predictions-display",
                                        className="command-data-value",
                                    ),
                                ],
                                className="command-data-row",
                            ),
                        ],
                        className="command-data-grid",
                    ),
                    html.Div(
                        [
                            html.Span("Data: ", className="command-data-label"),
                            html.Span(
                                id="global-data-dir-display",
                                className="command-data-value",
                                children=data_cfg.get("data_dir") or "Not selected",
                            ),
                            html.Span("Active: ", className="command-data-label"),
                            html.Span(
                                id="global-active-selection",
                                className="command-data-value",
                            ),
                        ],
                        className="command-active-source",
                    ),
                    dbc.Button(
                        "Load",
                        id="global-load-btn",
                        n_clicks=0,
                        style={"display": "none"},
                    ),
                    dbc.Button(
                        "Reload dataset",
                        id="verify-reload",
                        n_clicks=0,
                        style={"display": "none"},
                    ),
                ],
                className="command-popover command-popover--data",
            ),
        ],
        className="command-tool command-tool--data",
        **{"data-command-panel": "data"},
    )


def create_verify_result_controls() -> html.Div:
    return html.Div(
        [
            html.Div(id="verify-summary", className="command-result-summary"),
            html.Div(
                [
                    dbc.Button(
                        html.I(className="bi bi-chevron-left"),
                        id="verify-prev-page",
                        n_clicks=0,
                        color="secondary",
                        outline=True,
                        size="sm",
                        className="command-page-btn",
                        title="Previous page",
                    ),
                    html.Details(
                        [
                            html.Summary(
                                html.Span(
                                    id="verify-page-info",
                                    className="command-page-info",
                                ),
                                className="command-page-jump-trigger",
                                title="Go to page",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Go to page",
                                        className="command-control-label",
                                    ),
                                    html.Div(
                                        [
                                            dbc.Input(
                                                id="verify-page-input",
                                                type="number",
                                                min=1,
                                                step=1,
                                                value=1,
                                                className="pagination-page-input",
                                            ),
                                            dbc.Button(
                                                "Go",
                                                id="verify-goto-page",
                                                n_clicks=0,
                                                color="primary",
                                                size="sm",
                                            ),
                                        ],
                                        className="command-page-jump-form",
                                    ),
                                ],
                                className="command-popover command-popover--page",
                            ),
                        ],
                        className="command-page-jump",
                        **{"data-command-panel": "page"},
                    ),
                    dbc.Button(
                        html.I(className="bi bi-chevron-right"),
                        id="verify-next-page",
                        n_clicks=0,
                        color="secondary",
                        outline=True,
                        size="sm",
                        className="command-page-btn",
                        title="Next page",
                    ),
                ],
                className="command-pagination",
            ),
        ],
        className="verify-result-controls",
    )


def create_verify_layout(config: dict) -> html.Div:
    return html.Div(
        [
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Unsaved Verification Changes")),
                    dbc.ModalBody(
                        "You have unsaved verification label changes on this page set. "
                        "Save all changes before moving to another page?"
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Stay",
                                id="verify-unsaved-page-stay",
                                color="secondary",
                                className="me-2",
                                n_clicks=0,
                            ),
                            dbc.Button(
                                "Save All & Continue",
                                id="verify-unsaved-page-save",
                                color="success",
                                n_clicks=0,
                            ),
                        ]
                    ),
                ],
                id="verify-unsaved-page-modal",
                is_open=False,
                centered=True,
                backdrop="static",
                keyboard=False,
            ),
            dcc.Store(id="verify-current-page", data=0, storage_type="session"),
            dcc.Store(id="verify-pending-page-store", data=None, storage_type="memory"),
            dcc.Store(id="verify-visible-item-ids-store", data=[], storage_type="memory"),
            dcc.Store(id="verify-data-cache-key-store", data=None, storage_type="memory"),
            dcc.Store(id="verify-data-cache-revision-store", data=0, storage_type="memory"),
            dcc.Store(
                id="verify-modal-synced-item-ids-store",
                data=[],
                storage_type="memory",
            ),
            create_review_dashboard(),
            create_verify_result_controls(),
            html.Div(
                _create_spectrogram_grid_placeholder(config),
                id="verify-grid",
                className="grid-shell",
            ),
        ],
        className="verify-workspace",
    )
