"""Helpers for building modal action table rows."""

from dash import html
import dash_bootstrap_components as dbc

from app.services.modal_boxes import parse_active_box_target


def build_bbox_control(label, *, active_label, mode):
    add_btn_color = "primary" if active_label == label else "outline-primary"
    return html.Div(
        [
            dbc.Button(
                html.I(className="fas fa-plus"),
                id={"type": "modal-label-add-box", "label": label},
                color=add_btn_color,
                size="sm",
                disabled=(mode == "explore"),
                className="modal-label-icon-btn modal-label-add-box-btn",
                title=f"Add bounding box for: {label}",
                n_clicks=0,
            ),
        ],
        className="modal-label-bbox-col",
    )


def build_accepted_rows(*, active_labels, active_box_label, mode):
    accepted_rows = []
    active_label, _ = parse_active_box_target(active_box_label)
    for label in active_labels:
        delete_button = None
        if mode != "explore":
            delete_button = dbc.Button(
                html.Span("×", className="modal-label-inline-delete-glyph"),
                id={"type": "modal-label-delete-btn", "label": label},
                color="link",
                size="sm",
                className="modal-label-inline-delete",
                title=f"Delete label: {label}",
                n_clicks=0,
            )
        accepted_rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(label, className="modal-label-text"),
                            delete_button if delete_button else None,
                        ],
                        className="modal-label-pill",
                    ),
                    build_bbox_control(label, active_label=active_label, mode=mode),
                ],
                className="modal-label-row",
            )
        )
    return accepted_rows


def build_verify_rows(
    *,
    predicted_labels,
    active_labels,
    rejected_set,
    is_verified,
    has_pending_edits,
    active_box_label,
    mode,
):
    verify_rows = []
    predicted_set = set(predicted_labels)
    accepted_set = set(active_labels)
    active_label, _ = parse_active_box_target(active_box_label)

    badge_models = []
    for label in predicted_labels:
        state = "model-unreviewed"
        if label in rejected_set:
            state = "model-rejected"
        elif label in accepted_set or (is_verified and not has_pending_edits and label not in rejected_set):
            state = "model-accepted"
        badge_models.append(
            {
                "label": label,
                "source": "model",
                "state": state,
                "actions": "accept_reject",
            }
        )
    for label in active_labels:
        if label in predicted_set:
            continue
        badge_models.append(
            {
                "label": label,
                "source": "human",
                "state": "human-added",
                "actions": "delete",
            }
        )

    for model in badge_models:
        label = model.get("label")
        if not isinstance(label, str):
            continue
        source = model.get("source")
        state = model.get("state") or "model-unreviewed"
        is_model = source == "model"
        state_text = {
            "model-unreviewed": "unverified",
            "model-accepted": "accepted",
            "model-rejected": "rejected",
            "human-added": "",
        }.get(state, "")
        icon = (
            html.I(className="bi bi-robot verify-label-source-icon", title="Model-derived label")
            if is_model
            else html.I(className="bi bi-person-fill verify-label-source-icon", title="Human-added label")
        )

        action_controls = None
        if model.get("actions") == "accept_reject":
            accept_disabled = state == "model-accepted"
            reject_disabled = state == "model-rejected"
            action_controls = html.Div(
                [
                    html.Button(
                        "✓",
                        id={"type": "modal-verify-label-accept", "target": label},
                        className="verify-inline-action verify-inline-action--accept",
                        title=f"Accept: {label}",
                        n_clicks=0,
                        disabled=accept_disabled,
                    ),
                    html.Button(
                        "×",
                        id={"type": "modal-verify-label-reject", "target": label},
                        className="verify-inline-action verify-inline-action--reject",
                        title=f"Reject: {label}",
                        n_clicks=0,
                        disabled=reject_disabled,
                    ),
                ],
                className="verify-inline-actions",
            )
        elif model.get("actions") == "delete":
            action_controls = html.Div(
                [
                    html.Button(
                        "×",
                        id={"type": "modal-verify-label-delete", "target": label},
                        className="verify-inline-action verify-inline-action--reject",
                        title=f"Delete: {label}",
                        n_clicks=0,
                    ),
                ],
                className="verify-inline-actions",
            )

        if label in accepted_set:
            bbox_control = build_bbox_control(label, active_label=active_label, mode=mode)
        else:
            bbox_control = html.Div([], className="modal-label-bbox-col")

        verify_rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            icon,
                                            html.Span(state_text, className="verify-label-state")
                                            if state_text
                                            else None,
                                        ],
                                        className="verify-label-row-meta",
                                    ),
                                    action_controls,
                                ],
                                className="verify-label-row-header",
                            ),
                            html.Span(label, className="verify-label-text verify-label-text--multiline"),
                        ],
                        className=f"verify-label-badge verify-label-badge--{state} verify-label-badge--row",
                    ),
                    bbox_control,
                ],
                className="modal-label-row modal-label-row--verify",
            )
        )

    return verify_rows
