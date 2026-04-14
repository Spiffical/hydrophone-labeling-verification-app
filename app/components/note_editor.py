"""Reusable expandable note editor for label-mode card and modal UIs."""

import dash_bootstrap_components as dbc
from dash import dcc, html


def create_note_editor(
    note_text,
    *,
    textarea_id,
    button_id,
    placeholder="Add a note for this clip...",
    scope="card",
):
    normalized_note = note_text if isinstance(note_text, str) else ""
    return html.Details(
        [
            html.Summary("Note", className="note-editor-summary"),
            html.Div(
                [
                    dcc.Textarea(
                        id=textarea_id,
                        value=normalized_note,
                        placeholder=placeholder,
                        className="note-editor-textarea",
                        persistence=True,
                        persistence_type="memory",
                    ),
                    html.Div(
                        [
                            html.Span(
                                "Use Update note to stage note-only edits before saving.",
                                className="note-editor-hint",
                            ),
                            dbc.Button(
                                "Update note",
                                id=button_id,
                                size="sm",
                                color="secondary",
                                outline=True,
                                className="note-editor-apply",
                            ),
                        ],
                        className="note-editor-actions",
                    ),
                ],
                className="note-editor-body",
            ),
        ],
        open=bool(normalized_note),
        className=f"note-editor note-editor--{scope}",
    )
