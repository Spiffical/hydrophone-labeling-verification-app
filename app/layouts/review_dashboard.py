"""Progress, class selection and display controls above the review grid."""

import dash_bootstrap_components as dbc
from dash import dcc, html

from taxonomy.hierarchical_labels import HIERARCHICAL_LABELS

# As laid out in the Selection panel, read down each column.
_SELECTION_COLUMNS = (
    ("Biophony", "Geophony", "Other"),
    ("Anthropophony", "Instrumentation"),
)

STATUS_OPTIONS = (
    ("unverified", "Unverified only"),
    ("all", "All statuses"),
    ("verified", "Verified only"),
    ("accepted_only", "Accepted only"),
    ("rejected_only", "Rejected only"),
    ("mixed", "Mixed accepted/rejected"),
    ("contains_accepted", "Contains accepted"),
    ("contains_rejected", "Contains rejected"),
)


def status_filter_options(counts=None):
    """Return the status menu, counting the clips under each status when known."""
    return [
        {
            "label": label if counts is None else f"{label} ({counts.get(value, 0):,})",
            "value": value,
        }
        for value, label in STATUS_OPTIONS
    ]


def _tree_node(path_parts, children):
    path = " > ".join(path_parts)
    node = html.Button(
        [
            html.I(className="bi bi-check-lg review-tree-check", **{"aria-hidden": "true"}),
            html.Span(path_parts[-1]),
        ],
        id={"type": "verify-filter-node", "path": path},
        n_clicks=0,
        type="button",
        className="review-tree-node",
        title=path,
    )
    if not children:
        return html.Div(node, className="review-tree-leaf")
    return html.Details(
        [
            html.Summary(
                [
                    html.I(className="bi bi-chevron-right review-tree-caret", **{"aria-hidden": "true"}),
                    node,
                ],
            ),
            html.Div(
                [_tree_node(path_parts + [name], grandchildren) for name, grandchildren in children.items()],
                className="review-tree-children",
            ),
        ],
        className="review-tree-branch",
    )


def _category_control(category):
    children = HIERARCHICAL_LABELS.get(category) or {}
    return html.Div(
        [
            html.Button(
                [html.Span(className="review-category-dot"), html.Span(category)],
                id={"type": "verify-category-toggle", "category": category},
                n_clicks=0,
                type="button",
                className="review-category-toggle",
                title=f"Show {category} clips",
            ),
            html.Details(
                [
                    html.Summary(
                        html.I(className="bi bi-chevron-down command-panel-caret", **{"aria-hidden": "true"}),
                        title=f"Choose classes within {category}",
                        **{"aria-label": f"Choose classes within {category}"},
                    ),
                    html.Div(
                        [_tree_node([category, name], grandchildren) for name, grandchildren in children.items()],
                        className="review-tree",
                    ),
                ],
                className="review-category-menu",
                **{"data-command-panel": f"category-{category.lower()}"},
            ),
        ],
        className=f"review-category review-category--{category.lower()}",
    )


def _progress_panel():
    return html.Section(
        [
            html.Div(
                [
                    html.H2("Progress", className="review-panel-title"),
                    dbc.Switch(
                        id="verify-progress-all-categories",
                        label="All categories",
                        value=True,
                        className="review-switch",
                    ),
                ],
                className="review-panel-header",
            ),
            html.Div(
                [
                    html.Div(id="verify-progress-chart", className="review-chart"),
                    html.Div(id="verify-progress-total", className="review-total"),
                ],
                className="review-progress-body",
            ),
        ],
        className="review-progress",
        **{"aria-label": "Review progress by model confidence"},
    )


def _selection_panel():
    return html.Section(
        [
            html.Div(
                [
                    html.H2("Selection", className="review-panel-title"),
                    html.Span(id="verify-selection-summary", className="review-selection-summary"),
                    html.Button(
                        "Clear",
                        id="verify-selection-clear",
                        n_clicks=0,
                        type="button",
                        className="review-selection-clear",
                        style={"display": "none"},
                    ),
                ],
                className="review-panel-header",
            ),
            html.Div(
                [
                    html.Div([_category_control(category) for category in column], className="review-category-column")
                    for column in _SELECTION_COLUMNS
                ],
                className="review-categories",
            ),
        ],
        className="review-selection",
        **{"aria-label": "Classes to review"},
    )


def _display_mode_panel():
    return html.Section(
        [
            html.H2("Display Mode", className="review-panel-title"),
            html.Div(
                [
                    dbc.Select(
                        id="verify-status-filter",
                        value="unverified",
                        options=status_filter_options(),
                        className="review-status-select",
                    ),
                    html.I(className="bi bi-chevron-down review-status-caret", **{"aria-hidden": "true"}),
                ],
                className="review-status",
            ),
            html.Div(
                [
                    html.Button(
                        "Precision",
                        id="verify-order-precision",
                        n_clicks=0,
                        type="button",
                        className="review-order-btn",
                        title="Highest confidence first",
                    ),
                    html.Button(
                        [html.I(className="bi bi-dice-5-fill", **{"aria-hidden": "true"}), html.Span("Shuffle")],
                        id="verify-order-shuffle",
                        n_clicks=0,
                        type="button",
                        className="review-order-btn",
                        title="Random order; click again to reshuffle",
                    ),
                ],
                className="review-order",
            ),
            html.Div(
                [
                    html.Span("0%", className="review-range-end"),
                    html.Div(
                        dcc.RangeSlider(
                            id="verify-threshold-slider",
                            min=0,
                            max=100,
                            step=1,
                            value=[50, 100],
                            marks=None,
                            allowCross=False,
                            updatemode="mouseup",
                            tooltip={"placement": "top", "always_visible": True},
                            className="review-range-slider",
                        ),
                        className="review-range-track",
                    ),
                    html.Span("100%", className="review-range-end"),
                ],
                className="review-range",
                title="Model confidence of the clips to show",
            ),
            dbc.Switch(
                id="verify-exclude-ambient",
                label="Exclude ambient noise",
                value=True,
                className="review-switch",
            ),
        ],
        className="review-panel review-display",
        **{"aria-label": "Display mode"},
    )


def create_review_dashboard() -> html.Div:
    return html.Div(
        [
            html.Div(
                [_progress_panel(), _selection_panel()],
                className="review-panel review-overview",
            ),
            _display_mode_panel(),
        ],
        className="review-dashboard",
    )
