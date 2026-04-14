"""Callbacks for label quick-save actions from cards and modal."""

from copy import deepcopy

from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate


def register_label_save_callbacks(
    app,
    *,
    _require_complete_profile,
    _extract_label_extent_map_from_boxes,
    _profile_actor,
    _update_item_labels,
    _update_item_notes,
    save_label_mode,
    _build_modal_boxes_from_item,
    _modal_snapshot_payload,
    _parse_verify_target,
    _get_modal_label_sets,
    _ordered_unique_labels,
    _clean_annotation_extent,
    _has_pending_label_edits,
    _stage_label_note_edit,
):
    def _resolve_card_note_value(item_id, note_values, note_ids):
        for index, note_id in enumerate(note_ids or []):
            if not isinstance(note_id, dict):
                continue
            if (note_id.get("item_id") or "").strip() != item_id:
                continue
            return (note_values or [None])[index]
        return None

    def quick_delete_label_mode(delete_timestamps, label_data, modal_item_id, modal_bbox_store, profile):
        if not ctx.triggered:
            raise PreventUpdate
        if (ctx.triggered[0].get("value") or 0) <= 0:
            raise PreventUpdate
        _ = delete_timestamps
        _require_complete_profile(profile, "quick_delete_label_mode")

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate

        item_key, item_id, label = _parse_verify_target((triggered.get("target") or "").strip())
        _ = item_key  # label-mode delete currently resolves by item_id.
        if not item_id:
            item_id = (triggered.get("item_id") or "").strip()
        if not label:
            label = (triggered.get("label") or "").strip()
        if not item_id or not label:
            raise PreventUpdate

        data = deepcopy(label_data or {})
        items = data.get("items") or []
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            raise PreventUpdate

        _, _, active_labels = _get_modal_label_sets(active_item, "label", {"__global__": 0.5})
        updated_labels = [
            existing
            for existing in _ordered_unique_labels(active_labels)
            if existing != label
        ]
        if len(updated_labels) == len(_ordered_unique_labels(active_labels)):
            raise PreventUpdate

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        label_extents = {}
        raw_label_extents = annotations_obj.get("label_extents") if isinstance(annotations_obj, dict) else None
        if isinstance(raw_label_extents, dict):
            for extent_label, extent in raw_label_extents.items():
                if not isinstance(extent_label, str):
                    continue
                normalized = extent_label.strip()
                if not normalized or normalized == label:
                    continue
                cleaned_extent = _clean_annotation_extent(extent)
                if cleaned_extent:
                    label_extents[normalized] = cleaned_extent

        next_bbox_store = no_update
        unsaved_update = no_update
        if item_id == (modal_item_id or ""):
            unsaved_update = {"dirty": True, "item_id": item_id}
            if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
                filtered_boxes = [
                    box
                    for box in (modal_bbox_store.get("boxes") or [])
                    if isinstance(box, dict) and (box.get("label") or "").strip() != label
                ]
                next_bbox_store = {"item_id": item_id, "boxes": filtered_boxes}
                label_extents = _extract_label_extent_map_from_boxes(filtered_boxes)

        profile_name = _profile_actor(profile)
        updated_data = _update_item_labels(
            data,
            item_id,
            updated_labels,
            mode="label",
            user_name=profile_name,
            label_extents=label_extents or None,
        )
        return updated_data, next_bbox_store, unsaved_update

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input({"type": "label-label-delete", "target": ALL}, "n_clicks"),
        State("label-data-store", "data"),
        State("current-filename", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def delete_label_from_card(delete_clicks, label_data, modal_item_id, modal_bbox_store, profile, mode):
        if mode != "label":
            raise PreventUpdate
        return quick_delete_label_mode(
            delete_clicks,
            label_data,
            modal_item_id,
            modal_bbox_store,
            profile,
        )

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Input({"type": "label-save-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-label-save", "scope": ALL}, "n_clicks"),
        State("current-filename", "data"),
        State("label-data-store", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("config-store", "data"),
        State("label-output-input", "value"),
        State({"type": "card-note-text", "item_id": ALL}, "value"),
        State({"type": "card-note-text", "item_id": ALL}, "id"),
        State("modal-note-text", "value"),
        prevent_initial_call=True,
    )
    def save_label_changes(
        card_save_clicks,
        modal_save_clicks,
        modal_item_id,
        label_data,
        modal_bbox_store,
        profile,
        cfg,
        label_output_path,
        card_note_values,
        card_note_ids,
        modal_note_text,
    ):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate

        if triggered.get("type") == "modal-label-save":
            if not modal_save_clicks or not any(modal_save_clicks) or not modal_item_id:
                raise PreventUpdate
            item_id = modal_item_id
        elif triggered.get("type") == "label-save-btn":
            if not card_save_clicks or not any(card_save_clicks):
                raise PreventUpdate
            item_id = (triggered.get("item_id") or "").strip()
        else:
            raise PreventUpdate

        if not item_id:
            raise PreventUpdate
        _require_complete_profile(profile, "save_label_changes")
        profile_name = _profile_actor(profile)

        data = deepcopy(label_data or {})
        items = data.get("items") or []
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            raise PreventUpdate

        live_note_text = None
        if triggered.get("type") == "modal-label-save":
            live_note_text = modal_note_text
        elif triggered.get("type") == "label-save-btn":
            live_note_text = _resolve_card_note_value(item_id, card_note_values, card_note_ids)

        if live_note_text is not None:
            data, _ = _stage_label_note_edit(
                data,
                item_id,
                live_note_text,
                user_name=profile_name,
            )
            items = data.get("items") or []
            active_item = next(
                (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
                None,
            )
            if not isinstance(active_item, dict):
                raise PreventUpdate

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        if not _has_pending_label_edits(annotations_obj):
            raise PreventUpdate

        labels_to_save = _ordered_unique_labels(annotations_obj.get("labels") or [])
        note_text = annotations_obj.get("notes", "") if isinstance(annotations_obj.get("notes"), str) else ""

        label_extents = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
            label_extents = _extract_label_extent_map_from_boxes(modal_bbox_store.get("boxes") or [])
        else:
            raw_label_extents = annotations_obj.get("label_extents")
            if isinstance(raw_label_extents, dict):
                for extent_label, extent in raw_label_extents.items():
                    if not isinstance(extent_label, str):
                        continue
                    normalized = extent_label.strip()
                    if not normalized:
                        continue
                    cleaned_extent = _clean_annotation_extent(extent)
                    if cleaned_extent:
                        label_extents[normalized] = cleaned_extent

        if label_extents:
            merged = list(labels_to_save)
            seen = set(merged)
            for label in label_extents.keys():
                if label not in seen:
                    merged.append(label)
                    seen.add(label)
            labels_to_save = merged

        cfg = cfg or {}
        labels_file = (
            label_output_path
            or (data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}).get("labels_file")
            or (cfg.get("label", {}) if isinstance(cfg.get("label"), dict) else {}).get("output_file")
        )

        save_label_mode(
            labels_file,
            item_id,
            labels_to_save,
            annotated_by=profile_name,
            notes=note_text,
            label_extents=label_extents or None,
        )

        updated = _update_item_labels(
            data,
            item_id,
            labels_to_save,
            mode="label",
            user_name=profile_name,
            is_reverification=True,
            label_extents=label_extents or None,
        )
        updated = _update_item_notes(updated or {}, item_id, note_text, user_name=profile_name)

        dirty_update = no_update
        snapshot_update = no_update
        modal_item_update = no_update
        if item_id == (modal_item_id or ""):
            dirty_update = {"dirty": False, "item_id": item_id}
            updated_item = next(
                (
                    item
                    for item in (updated or {}).get("items", [])
                    if isinstance(item, dict) and item.get("item_id") == item_id
                ),
                None,
            )
            if isinstance(updated_item, dict):
                modal_item_update = updated_item
                if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
                    snapshot_boxes = modal_bbox_store.get("boxes") or []
                else:
                    snapshot_boxes = _build_modal_boxes_from_item(updated_item)
                snapshot_update = _modal_snapshot_payload("label", item_id, updated_item, snapshot_boxes)

        return updated, dirty_update, snapshot_update, modal_item_update
