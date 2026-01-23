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


def create_spectrogram_card(item: dict, image_src: str = None, mode: str = "label") -> dbc.Card:
    item_id = item.get("item_id") or os.path.basename(item.get("spectrogram_path", ""))
    audio_path = item.get("audio_path")

    predictions = item.get("predictions") or {}
    annotations_data = item.get("annotations") or {}
    predicted = predictions.get("labels", [])
    annotations = annotations_data.get("labels", [])
    is_verified = bool(annotations_data.get("verified"))
    needs_reverify = bool(annotations_data.get("needs_reverify"))

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
            html.Small("Predicted", className="text-muted mb-1 d-block"),
            _label_badges(predicted, color="primary"),
        ], className="mb-2"))
        badges.append(html.Div([
            html.Small("Verified", className="text-muted mb-1 d-block"),
            _label_badges(annotations, color="success"),
        ]))
    else:
        badges.append(html.Div([
            html.Small("Labels", className="text-muted mb-1 d-block"),
            _label_badges(annotations or predicted, color="primary"),
        ]))

    actions = []
    if mode == "verify":
        # For verified items: Re-verify button only enabled if labels were modified
        # For unverified items: Confirm button always enabled
        if is_verified:
            actions = [
                dbc.Button(
                    "Re-verify",
                    id={"type": "confirm-btn", "item_id": item_id},
                    size="sm",
                    color="success" if needs_reverify else "secondary",
                    disabled=not needs_reverify,
                    outline=not needs_reverify,
                ),
                dbc.Button(
                    "Revise",
                    id={"type": "edit-btn", "item_id": item_id},
                    size="sm",
                    color="primary",
                ),
            ]
        else:
            actions = [
                dbc.Button(
                    "Confirm",
                    id={"type": "confirm-btn", "item_id": item_id},
                    size="sm",
                    color="success",
                ),
                dbc.Button(
                    "Edit",
                    id={"type": "edit-btn", "item_id": item_id},
                    size="sm",
                    color="secondary",
                ),
            ]
    else:
        actions = [
            dbc.Button("Edit Labels", id={"type": "edit-btn", "item_id": item_id}, size="sm", color="primary"),
        ]

    return dbc.Card([
        dbc.CardHeader(html.Div([
            html.Span(item_id, className="fw-semibold small", style={"word-break": "break-all"}),
        ])),
        dbc.CardBody([
            image,
            audio_player,
            html.Div(badges, className="mt-3"),
            html.Div(actions, className="mt-3 d-flex gap-2 flex-wrap"),
        ])
    ], className="spectrogram-card h-100")
