"""Helpers for building modal action table rows."""

from dash import dcc, html
import dash_bootstrap_components as dbc

from app.services.bbox_tags import get_bbox_tag_options
from app.services.modal_boxes import leaf_label_text
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
    verified_labels,
    active_labels,
    rejected_set,
    is_verified,
    explicit_review,
    has_pending_edits,
    active_box_label,
    mode,
):
    verify_rows = []
    predicted_set = set(predicted_labels)
    verified_set = set(verified_labels)
    accepted_set = set(active_labels)
    active_label, _ = parse_active_box_target(active_box_label)

    badge_models = []
    for label in predicted_labels:
        state = "model-unreviewed"
        if label in rejected_set:
            state = "model-rejected"
        elif (
            (explicit_review and label in verified_set)
            or (is_verified and not has_pending_edits and label not in rejected_set)
        ):
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
                                            html.Span(
                                                state_text,
                                                id={"type": "modal-verify-label-state", "target": label},
                                                className="verify-label-state",
                                            ),
                                        ],
                                        className="verify-label-row-meta",
                                    ),
                                    action_controls,
                                ],
                                className="verify-label-row-header",
                            ),
                            html.Span(label, className="verify-label-text verify-label-text--multiline"),
                        ],
                        id={"type": "modal-verify-label-badge", "target": label},
                        className=f"verify-label-badge verify-label-badge--{state} verify-label-badge--row",
                    ),
                    bbox_control,
                ],
                id={"type": "modal-verify-label-row", "target": label},
                className=f"modal-label-row modal-label-row--verify modal-label-row--{state}",
            )
        )

    return verify_rows


def _format_box_extent(extent):
    if not isinstance(extent, dict):
        return "bounds unavailable"
    time_start = extent.get("time_start_sec")
    time_end = extent.get("time_end_sec")
    freq_min = extent.get("freq_min_hz")
    freq_max = extent.get("freq_max_hz")

    pieces = []
    if time_start is not None and time_end is not None:
        pieces.append(f"{float(time_start):.3g}-{float(time_end):.3g}s")
    if freq_min is not None and freq_max is not None:
        pieces.append(f"{float(freq_min):.3g}-{float(freq_max):.3g}Hz")
    return " | ".join(pieces) if pieces else extent.get("type", "bounds unavailable")


def build_bbox_rows(*, boxes, config=None, mode="label"):
    tag_options = get_bbox_tag_options(config)
    if not boxes:
        return html.Div("No boxes assigned", className="modal-bbox-empty")

    rows = []
    for idx, box in enumerate(boxes or []):
        if not isinstance(box, dict):
            continue
        label = (box.get("label") or "").strip()
        extent = box.get("annotation_extent") if isinstance(box.get("annotation_extent"), dict) else {}
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f"Box {idx + 1}", className="modal-bbox-index"),
                            html.Span(leaf_label_text(label), className="modal-bbox-label", title=label),
                            html.Span(_format_box_extent(extent), className="modal-bbox-bounds"),
                        ],
                        className="modal-bbox-summary",
                    ),
                    dcc.Dropdown(
                        id={"type": "modal-bbox-tag-dropdown", "index": idx},
                        options=tag_options,
                        value=box.get("tag") or None,
                        clearable=True,
                        searchable=False,
                        placeholder="Tag",
                        disabled=(mode == "explore"),
                        className="modal-bbox-tag-dropdown control-dropdown",
                    ),
                    dbc.Button(
                        html.I(className="bi bi-pencil-square"),
                        id={"type": "modal-bbox-edit-btn", "index": idx},
                        color="secondary",
                        outline=True,
                        size="sm",
                        disabled=(mode == "explore"),
                        className="modal-bbox-edit-btn",
                        title=f"Edit box {idx + 1}",
                        n_clicks=0,
                    ),
                ],
                className="modal-bbox-row",
            )
        )

    if not rows:
        return html.Div("No boxes assigned", className="modal-bbox-empty")
    return html.Div(rows, className="modal-bbox-list")
