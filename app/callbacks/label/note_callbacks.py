"""Callbacks for label-mode note editing from cards and the spectrogram modal."""

from dash import ALL, Input, Output, State, ctx
from dash.exceptions import PreventUpdate


def _resolve_card_note_value(item_id, note_values, note_ids):
    for index, note_id in enumerate(note_ids or []):
        if not isinstance(note_id, dict):
            continue
        if (note_id.get("item_id") or "").strip() != item_id:
            continue
        return (note_values or [None])[index]
    return None


def register_label_note_callbacks(
    app,
    *,
    _require_complete_profile,
    _profile_actor,
    _stage_label_note_edit,
):
    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Input({"type": "card-note-apply", "item_id": ALL}, "n_clicks"),
        State({"type": "card-note-text", "item_id": ALL}, "value"),
        State({"type": "card-note-text", "item_id": ALL}, "id"),
        State("label-data-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def apply_card_note(
        note_apply_clicks,
        note_values,
        note_ids,
        label_data,
        profile,
        mode,
    ):
        if mode != "label":
            raise PreventUpdate
        if not note_apply_clicks or not any(note_apply_clicks):
            raise PreventUpdate

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate

        item_id = (triggered.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate

        note_value = _resolve_card_note_value(item_id, note_values, note_ids)
        if note_value is None:
            raise PreventUpdate

        _require_complete_profile(profile, "apply_card_note")
        updated, changed = _stage_label_note_edit(
            label_data or {},
            item_id,
            note_value,
            user_name=_profile_actor(profile),
        )
        if not changed:
            raise PreventUpdate
        return updated

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input("modal-note-apply", "n_clicks"),
        State("modal-note-text", "value"),
        State("modal-item-store", "data"),
        State("label-data-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def apply_modal_note(
        modal_note_apply_clicks,
        modal_note_text,
        modal_item,
        label_data,
        profile,
        mode,
    ):
        if mode != "label":
            raise PreventUpdate
        if not modal_note_apply_clicks:
            raise PreventUpdate
        if not isinstance(modal_item, dict):
            raise PreventUpdate

        item_id = (modal_item.get("item_id") or "").strip()
        if not item_id:
            raise PreventUpdate

        _require_complete_profile(profile, "apply_modal_note")
        updated, changed = _stage_label_note_edit(
            label_data or {},
            item_id,
            modal_note_text,
            user_name=_profile_actor(profile),
        )
        if not changed:
            raise PreventUpdate

        updated_item = next(
            (
                item
                for item in (updated or {}).get("items", [])
                if isinstance(item, dict) and item.get("item_id") == item_id
            ),
            None,
        )
        if not isinstance(updated_item, dict):
            raise PreventUpdate

        return updated, updated_item, {"dirty": True, "item_id": item_id}
