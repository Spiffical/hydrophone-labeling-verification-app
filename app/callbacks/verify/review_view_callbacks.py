"""Display mode and progress callbacks for the review page."""

from dash import ALL, ClientsideFunction, Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from app.components.review_progress import create_progress_chart, create_progress_total
from app.services.review_view import (
    ORDER_PRECISION,
    ORDER_SHUFFLE,
    active_class_filter,
    normalize_review_view,
    toggle_progress_segment,
)
from app.services.verify_modal_cache import get_verify_progress


def next_review_view(view, *, triggered, exclude_ambient):
    """Apply one control's change to the page's view settings."""
    updated = normalize_review_view(view)
    if triggered == "verify-exclude-ambient":
        # Ambient moves clips between bars, so a picked segment no longer stands.
        if updated["exclude_ambient"] != bool(exclude_ambient):
            updated["segment"] = None
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
        if updated == normalize_review_view(view):
            raise PreventUpdate
        return updated, 0

    @app.callback(
        Output("verify-view-store", "data", allow_duplicate=True),
        Output("verify-threshold-slider", "value", allow_duplicate=True),
        Output("verify-status-filter", "value", allow_duplicate=True),
        Output("verify-current-page", "data", allow_duplicate=True),
        Input({"type": "verify-progress-segment", "bin": ALL, "category": ALL, "state": ALL}, "n_clicks"),
        Input({"type": "verify-segment-clear", "chart": ALL}, "n_clicks"),
        State("verify-view-store", "data"),
        State("verify-threshold-slider", "value"),
        State("verify-status-filter", "value"),
        State("verify-class-filter", "data"),
        State("verify-progress-all-categories", "value"),
        prevent_initial_call=True,
    )
    def pick_progress_segment(segment_clicks, clear_clicks, view, confidence_slider, status, class_filter, all_categories):
        _ = segment_clicks, clear_clicks
        # Redrawing the chart brings new buttons with no clicks.
        if not ctx.triggered or not ctx.triggered[0].get("value"):
            raise PreventUpdate
        picked = ctx.triggered_id if ctx.triggered_id["type"] == "verify-progress-segment" else None
        scope = None if all_categories else active_class_filter(class_filter)
        return (*toggle_progress_segment(view, picked, confidence_slider, status, scope), 0)

    app.clientside_callback(
        ClientsideFunction(namespace="progressSegment", function_name="release"),
        Output("verify-view-store", "data", allow_duplicate=True),
        Input("verify-threshold-slider", "value"),
        Input("verify-status-filter", "value"),
        Input("verify-class-filter", "data"),
        Input("verify-progress-all-categories", "value"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("verify-view-store", "data"),
        prevent_initial_call=True,
    )

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
        view = normalize_review_view(view)
        progress = get_verify_progress(cache_key, selected, exclude_ambient=view["exclude_ambient"])
        return (
            create_progress_chart(progress, view["segment"]),
            create_progress_total(progress, scoped=selected is not None),
        )
