"""Modal actions panel rendering helpers."""

from dash import html

from app.services.annotations import ordered_unique_labels
from app.callbacks.modal.action_footer_helpers import build_status_and_actions
from app.callbacks.modal.action_rows_helpers import (
    build_accepted_rows,
    build_verify_rows,
)
from app.services.verification import (
    get_item_rejected_labels,
    get_modal_label_sets,
    has_pending_label_edits,
)


def build_modal_item_actions(item, mode, thresholds, boxes=None, active_box_label=None):
    _ = boxes
    if not item:
        return html.Div("No item selected.", className="text-muted small")

    annotations = item.get("annotations") or {}
    predicted_labels, _verified_labels, active_labels = get_modal_label_sets(item, mode, thresholds)
    active_labels = ordered_unique_labels(active_labels)
    rejected_labels = get_item_rejected_labels(item) if mode == "verify" else []
    accepted_set = set(active_labels)
    rejected_labels = [label for label in ordered_unique_labels(rejected_labels) if label not in accepted_set]
    rejected_set = set(rejected_labels)
    is_verified = bool(annotations.get("verified"))
    has_pending_edits = has_pending_label_edits(annotations)

    accepted_rows = build_accepted_rows(
        active_labels=active_labels,
        active_box_label=active_box_label,
        mode=mode,
    )
    verify_rows = []
    if mode == "verify":
        verify_rows = build_verify_rows(
            predicted_labels=predicted_labels,
            active_labels=active_labels,
            rejected_set=rejected_set,
            is_verified=is_verified,
            has_pending_edits=has_pending_edits,
            active_box_label=active_box_label,
            mode=mode,
        )

    status_note, action_buttons = build_status_and_actions(
        mode=mode,
        is_verified=is_verified,
        has_pending_edits=has_pending_edits,
        predicted_labels=predicted_labels,
        active_labels=active_labels,
    )

    if mode == "verify":
        return html.Div(
            [
                html.Div("Labels", className="small fw-semibold text-muted mb-2"),
                (
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Label", className="modal-label-col-title"),
                                    html.Span("BBox", className="modal-bbox-col-title"),
                                ],
                                className="modal-label-table-header",
                            ),
                            html.Div(verify_rows, className="modal-label-list"),
                        ],
                        className="modal-label-table mb-3",
                    )
                    if verify_rows
                    else html.Div("No labels", className="text-muted small mb-3")
                ),
                html.Div(status_note, className="modal-status-note") if status_note else None,
                html.Div(action_buttons, className="modal-action-buttons") if action_buttons else None,
            ],
            className="modal-item-actions-card",
        )

    return html.Div(
        [
            html.Div("Labels", className="small fw-semibold text-muted mb-2"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Label", className="modal-label-col-title"),
                            html.Span("BBox", className="modal-bbox-col-title"),
                        ],
                        className="modal-label-table-header",
                    ),
                    html.Div(accepted_rows, className="modal-label-list"),
                ],
                className="modal-label-table",
            )
            if accepted_rows
            else html.Div("No labels", className="text-muted small"),
            html.Div(status_note, className="modal-status-note") if status_note else None,
            html.Div(action_buttons, className="modal-action-buttons") if action_buttons else None,
        ],
        className="modal-item-actions-card",
    )
