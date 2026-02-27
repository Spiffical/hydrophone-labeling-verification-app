import os
from dash import html
import dash_bootstrap_components as dbc
from app.components.audio_player import create_audio_player


def _label_badges(labels, color="primary"):
    if not labels:
        return html.Div("No labels", className="text-muted small")
    return html.Div([
        dbc.Badge(label, color=color, className="me-1 mb-1", style={"font-size": "0.7em"})
        for label in labels
    ], style={"display": "flex", "flex-wrap": "wrap"})


def _ordered_unique_labels(labels):
    ordered = []
    seen = set()
    for label in labels or []:
        if not isinstance(label, str):
            continue
        normalized = label.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def _has_pending_label_edits(annotations_data):
    if not isinstance(annotations_data, dict):
        return False
    return bool(annotations_data.get("pending_save") or annotations_data.get("needs_reverify"))


def _render_label_badges_with_delete(item_id, labels):
    labels = _ordered_unique_labels(labels or [])
    if not labels:
        return html.Div("No labels", className="text-muted small")

    badges = []
    for label in labels:
        target = f"{item_id}||{label}"
        badges.append(
            html.Div(
                [
                    html.Span(label, className="verify-label-text"),
                    html.Div(
                        [
                            html.Button(
                                "×",
                                id={"type": "label-label-delete", "target": target},
                                className="verify-inline-action verify-inline-action--reject",
                                title=f"Delete: {label}",
                                n_clicks=0,
                            ),
                        ],
                        className="verify-inline-actions",
                    ),
                ],
                className="verify-label-badge verify-label-badge--human-added",
            )
        )
    return html.Div(badges, className="verify-badge-list")


def _render_label_badges_readonly(labels):
    labels = _ordered_unique_labels(labels or [])
    if not labels:
        return html.Div("No labels", className="text-muted small")

    badges = []
    for label in labels:
        badges.append(
            html.Div(
                [
                    html.Span(label, className="verify-label-text"),
                ],
                className="verify-label-badge verify-label-badge--human-added",
            )
        )
    return html.Div(badges, className="verify-badge-list")


def _verify_badge_models(predicted_labels, accepted_labels, rejected_labels, assume_verified=False):
    models = []
    predicted = _ordered_unique_labels(predicted_labels or [])
    accepted = _ordered_unique_labels(accepted_labels or [])
    rejected = _ordered_unique_labels(rejected_labels or [])
    accepted_set = set(accepted)
    rejected_set = set(rejected)
    predicted_set = set(predicted)

    for label in predicted:
        state = "model-unreviewed"
        if label in rejected_set:
            state = "model-rejected"
        elif label in accepted_set or (assume_verified and label not in rejected_set):
            state = "model-accepted"
        models.append(
            {
                "label": label,
                "source": "model",
                "state": state,
                "actions": "accept_reject",
            }
        )

    for label in accepted:
        if label in predicted_set:
            continue
        models.append(
            {
                "label": label,
                "source": "human",
                "state": "human-added",
                "actions": "delete",
            }
        )
    return models


def _render_verify_badges(item_id, predicted_labels, accepted_labels, rejected_labels, assume_verified=False):
    models = _verify_badge_models(predicted_labels, accepted_labels, rejected_labels, assume_verified=assume_verified)
    if not models:
        return html.Div("No labels", className="text-muted small")

    badges = []
    for model in models:
        label = model["label"]
        source = model["source"]
        state = model["state"]
        is_model = source == "model"

        icon = (
            html.I(className="bi bi-robot verify-label-source-icon", title="Model-derived label")
            if is_model
            else html.I(className="bi bi-person-fill verify-label-source-icon", title="Human-added label")
        )
        state_text = {
            "model-unreviewed": "unverified",
            "model-accepted": "accepted",
            "model-rejected": "rejected",
            "human-added": "",
        }.get(state, "")

        action_controls = None
        target = f"{item_id}||{label}"
        if model.get("actions") == "accept_reject":
            accept_disabled = state == "model-accepted"
            reject_disabled = state == "model-rejected"
            action_controls = html.Div(
                [
                    html.Button(
                        "✓",
                        id={"type": "verify-label-accept", "target": target},
                        className="verify-inline-action verify-inline-action--accept",
                        title=f"Accept: {label}",
                        n_clicks=0,
                        disabled=accept_disabled,
                    ),
                    html.Button(
                        "×",
                        id={"type": "verify-label-reject", "target": target},
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
                        id={"type": "verify-label-delete", "target": target},
                        className="verify-inline-action verify-inline-action--reject",
                        title=f"Delete: {label}",
                        n_clicks=0,
                    ),
                ],
                className="verify-inline-actions",
            )

        badges.append(
            html.Div(
                [
                    icon,
                    html.Span(label, className="verify-label-text"),
                    html.Span(state_text, className="verify-label-state") if state_text else None,
                    action_controls,
                ],
                className=f"verify-label-badge verify-label-badge--{state}",
            )
        )
    return html.Div(badges, className="verify-badge-list")


def create_spectrogram_card(item: dict, image_src: str = None, mode: str = "label") -> dbc.Card:
    item_id = item.get("item_id") or os.path.basename(item.get("spectrogram_path", ""))
    audio_path = item.get("audio_path")

    predictions = item.get("predictions") or {}
    annotations_data = item.get("annotations") or {}
    predicted = _ordered_unique_labels(predictions.get("labels", []))
    annotations = _ordered_unique_labels(annotations_data.get("labels", []))
    rejected = _ordered_unique_labels((item.get("ui_rejected_labels") or annotations_data.get("rejected_labels") or []))
    has_pending_edits = _has_pending_label_edits(annotations_data)
    assume_verified = bool(annotations_data.get("verified")) and not has_pending_edits

    # Make image clickable for modal zoom
    image = html.Div([
        html.Img(
            src=image_src or "",
            id={"type": "spectrogram-image", "item_id": item_id},
            className="spectrogram-image",
            style={"width": "100%", "borderRadius": "10px", "cursor": "pointer"},
        ) if image_src else html.Div(
            "Image unavailable",
            className="text-muted text-center p-3",
            style={"background": "#f8f9fa", "borderRadius": "10px"},
        )
    ], className="spectrogram-image-container")

    # Add audio player
    audio_player = html.Div([
        html.Hr(className="my-3"),
        create_audio_player(audio_path, item_id, player_id=f"card-{hash(item_id) % 10000}")
    ]) if audio_path else None

    badges = []
    if mode == "verify":
        badges.append(html.Div([
            html.Small("Labels", className="text-muted mb-1 d-block"),
            _render_verify_badges(item_id, predicted, annotations, rejected, assume_verified=assume_verified),
        ]))
    elif mode == "label":
        label_display = annotations or predicted
        badges.append(html.Div([
            html.Small("Labels", className="text-muted mb-1 d-block"),
            _render_label_badges_with_delete(item_id, label_display),
        ]))
    else:
        label_display = annotations or predicted
        badges.append(html.Div([
            html.Small("Labels", className="text-muted mb-1 d-block"),
            _render_label_badges_readonly(label_display),
        ]))

    actions = []
    if mode == "verify":
        actions = [
            dbc.Button(
                "Save",
                id={"type": "confirm-btn", "item_id": item_id},
                size="sm",
                color="success" if has_pending_edits else "secondary",
                disabled=not has_pending_edits,
                outline=not has_pending_edits,
            ),
            dbc.Button(
                "Edit",
                id={"type": "edit-btn", "item_id": item_id},
                size="sm",
                color="secondary",
            ),
        ]
    elif mode == "label":
        actions = [
            dbc.Button(
                "Save",
                id={"type": "label-save-btn", "item_id": item_id},
                size="sm",
                color="success" if has_pending_edits else "secondary",
                disabled=not has_pending_edits,
                outline=not has_pending_edits,
            ),
            dbc.Button("Edit Labels", id={"type": "edit-btn", "item_id": item_id}, size="sm", color="secondary"),
        ]
    else:
        actions = []

    actions_block = html.Div(actions, className="mt-3 d-flex gap-2 flex-wrap") if actions else None

    return dbc.Card([
        dbc.CardHeader(html.Div([
            html.Span(item_id, className="fw-semibold small", style={"word-break": "break-all"}),
        ])),
        dbc.CardBody([
            image,
            audio_player,
            html.Div(badges, className="mt-3"),
            actions_block,
        ])
    ], className="spectrogram-card h-100")
