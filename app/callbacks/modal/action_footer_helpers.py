"""Helpers for modal actions status text and action buttons."""

import dash_bootstrap_components as dbc


def build_status_and_actions(*, mode, is_verified, has_pending_edits, predicted_labels, active_labels):
    action_buttons = []
    status_note = None

    if mode == "verify":
        if is_verified:
            status_note = "Verified" if not has_pending_edits else "Verified, unsaved label edits"
        else:
            status_note = "Unverified" if not has_pending_edits else "Unverified, unsaved label edits"
        action_buttons = [
            dbc.Button(
                "Save",
                id={"type": "modal-action-confirm", "scope": "modal"},
                color="success" if has_pending_edits else "secondary",
                size="sm",
                disabled=not has_pending_edits,
                outline=not has_pending_edits,
                className="me-2",
            ),
            dbc.Button(
                "Edit",
                id={"type": "modal-action-edit", "scope": "modal"},
                color="secondary",
                size="sm",
            ),
        ]
    elif mode == "label":
        status_note = "Unsaved label edits" if has_pending_edits else "All changes saved"
        action_buttons = [
            dbc.Button(
                "Save",
                id={"type": "modal-label-save", "scope": "modal"},
                color="success" if has_pending_edits else "secondary",
                disabled=not has_pending_edits,
                outline=not has_pending_edits,
                size="sm",
                className="me-2",
            ),
            dbc.Button(
                "Edit Labels",
                id={"type": "modal-action-edit", "scope": "modal"},
                color="secondary",
                size="sm",
            ),
        ]
    else:
        status_note = "Explore mode is read-only."

    if mode == "verify":
        verify_meta = f"Predicted: {len(predicted_labels)} | Current: {len(active_labels)}"
        status_note = f"{verify_meta} | {status_note}" if status_note else verify_meta

    return status_note, action_buttons
