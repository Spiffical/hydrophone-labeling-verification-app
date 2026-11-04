"""Display mode and progress callbacks for the review page."""

from dash import Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from app.components.review_progress import create_progress_chart, create_progress_total
from app.services.review_view import (
    ORDER_PRECISION,
    ORDER_SHUFFLE,
    active_class_filter,
    normalize_review_view,
)
from app.services.verify_modal_cache import get_verify_progress


def next_review_view(view, *, triggered, exclude_ambient):
    """Apply one control's change to the page's view settings."""
    updated = normalize_review_view(view)
    if triggered == "verify-exclude-ambient":
        updated["exclude_ambient"] = bool(exclude_ambient)
    elif triggered == "verify-order-precision":
        updated["order"] = ORDER_PRECISION
    elif triggered == "verify-order-shuffle":
        # Shuffling again deals a new order, so a click always does something.
        updated["order"] = ORDER_SHUFFLE
        updated["seed"] += 1
    return updated


def register_review_view_callbacks(app):
    @app.callback(
        Output("verify-view-store", "data"),
        Output("verify-current-page", "data", allow_duplicate=True),
        Input("verify-exclude-ambient", "value"),
        Input("verify-order-precision", "n_clicks"),
        Input("verify-order-shuffle", "n_clicks"),
        State("verify-view-store", "data"),
        prevent_initial_call=True,
    )
    def update_review_view(exclude_ambient, precision_clicks, shuffle_clicks, view):
        _ = precision_clicks, shuffle_clicks
        updated = next_review_view(view, triggered=ctx.triggered_id, exclude_ambient=exclude_ambient)
        # Restoring a reviewer's settings also moves the switch.
        if updated == view:
            raise PreventUpdate
        return updated, 0

    @app.callback(
        Output("verify-order-precision", "className"),
        Output("verify-order-shuffle", "className"),
        Input("verify-view-store", "data"),
    )
    def render_review_order(view):
        order = normalize_review_view(view)["order"]
        return tuple(
            "review-order-btn review-order-btn--active" if order == value else "review-order-btn"
            for value in (ORDER_PRECISION, ORDER_SHUFFLE)
        )

    @app.callback(
        Output("verify-progress-chart", "children"),
        Output("verify-progress-total", "children"),
        Input("verify-data-cache-key-store", "data"),
        Input("verify-data-cache-revision-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-view-store", "data"),
        Input("verify-progress-all-categories", "value"),
    )
    def render_progress(cache_key, cache_revision, class_filter, view, all_categories):
        _ = cache_revision
        selected = None if all_categories else active_class_filter(class_filter)
        progress = get_verify_progress(
            cache_key,
            selected,
            exclude_ambient=normalize_review_view(view)["exclude_ambient"],
        )
        return create_progress_chart(progress), create_progress_total(progress, scoped=selected is not None)
