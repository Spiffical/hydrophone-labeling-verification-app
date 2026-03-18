"""Callbacks for opening and saving the hierarchical label editor modal."""

import time

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.common.debug import perf_debug
from app.services.annotations import ordered_unique_labels


def _resolve_selected_labels(item, mode, thresholds, _filter_predictions):
    if not isinstance(item, dict):
        return [], ""
    annotations = item.get("annotations") or {}
    predicted = item.get("predictions", {}) if isinstance(item.get("predictions"), dict) else {}
    selected_labels = annotations.get("labels") or predicted.get("labels") or []
    existing_note = annotations.get("notes", "") if isinstance(annotations, dict) else ""
    if not selected_labels and mode == "verify":
        selected_labels = _filter_predictions(predicted, thresholds or {"__global__": 0.5})
    return ordered_unique_labels(selected_labels), existing_note


def _build_editor_body(item, mode, thresholds, _filter_predictions, create_hierarchical_selector):
    item_id = (item.get("item_id") or "").strip() if isinstance(item, dict) else ""
    if not item_id:
        return None, None
    selected_labels, existing_note = _resolve_selected_labels(
        item,
        mode,
        thresholds,
        _filter_predictions,
    )
    selector = create_hierarchical_selector(item_id, selected_labels)
    note_section = html.Details(
        [
            html.Summary("Note", style={"cursor": "pointer", "fontWeight": "600"}),
            dcc.Textarea(
                id={"type": "note-editor-text", "filename": item_id},
                value=existing_note,
                placeholder="Add a note for this spectrogram...",
                style={"width": "100%", "minHeight": "140px", "marginTop": "8px"},
            ),
        ],
        open=bool(existing_note),
        style={"marginTop": "12px"},
    )
    return item_id, html.Div([selector, note_section])


def register_label_editor_modal_callbacks(
    app,
    *,
    _get_mode_data,
    _require_complete_profile,
    _filter_predictions,
    create_hierarchical_selector,
    _extract_label_extent_map_from_boxes,
    _profile_actor,
    _update_item_labels,
    _update_item_notes,
    save_label_mode,
    _build_modal_boxes_from_item,
    _modal_snapshot_payload,
):
    @app.callback(
        Output("label-editor-modal", "is_open"),
        Output("label-editor-body", "children"),
        Output("active-item-store", "data"),
        Output("label-editor-clicks", "data"),
        Input({"type": "edit-btn", "item_id": ALL}, "n_clicks"),
        Input("label-editor-cancel", "n_clicks"),
        State("label-editor-clicks", "data"),
        State({"type": "edit-btn", "item_id": ALL}, "id"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("active-item-store", "data"),
        State("verify-thresholds-store", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def open_label_editor(
        n_clicks_list,
        cancel_clicks,
        click_store,
        edit_ids,
        label_data,
        verify_data,
        explore_data,
        active_item_id,
        thresholds,
        mode,
        profile,
    ):
        start = time.perf_counter()
        _ = cancel_clicks, active_item_id
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        triggered = ctx.triggered_id
        if triggered == "label-editor-cancel":
            return False, no_update, None, click_store or {}
        if mode == "explore":
            return False, no_update, None, click_store or {}
        _require_complete_profile(profile, "open_label_editor")

        click_store = click_store or {}
        updated_store = dict(click_store)
        chosen_item_id = None

        if not n_clicks_list or not edit_ids:
            return no_update, no_update, no_update, click_store

        for i, id_dict in enumerate(edit_ids):
            item_id = id_dict.get("item_id")
            if not item_id:
                continue
            current_clicks = n_clicks_list[i] or 0
            previous_clicks = click_store.get(item_id, 0)
            updated_store[item_id] = current_clicks
            if current_clicks > previous_clicks:
                chosen_item_id = item_id

        if not chosen_item_id:
            return no_update, no_update, no_update, updated_store

        items = (data or {}).get("items", [])
        chosen_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == chosen_item_id),
            None,
        )
        item_id, body = _build_editor_body(
            chosen_item,
            mode,
            thresholds,
            _filter_predictions,
            create_hierarchical_selector,
        )
        if not item_id or body is None:
            return no_update, no_update, no_update, updated_store
        perf_debug(
            "label_editor_open_grid",
            item_id=item_id,
            mode=mode,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return True, body, item_id, updated_store

    @app.callback(
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Output("label-editor-clicks", "data", allow_duplicate=True),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input({"type": "modal-action-edit", "scope": ALL}, "n_clicks"),
        State("modal-item-store", "data"),
        State("label-editor-clicks", "data"),
        State("verify-thresholds-store", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def open_label_editor_from_modal(
        modal_edit_clicks_list,
        modal_item,
        click_store,
        thresholds,
        mode,
        profile,
    ):
        start = time.perf_counter()
        if not modal_edit_clicks_list or not any(modal_edit_clicks_list):
            raise PreventUpdate
        if mode == "explore":
            raise PreventUpdate
        _require_complete_profile(profile, "open_label_editor_from_modal")
        item_id, body = _build_editor_body(
            modal_item,
            mode,
            thresholds,
            _filter_predictions,
            create_hierarchical_selector,
        )
        if not item_id or body is None:
            raise PreventUpdate
        updated_store = dict(click_store or {})
        updated_store[item_id] = (updated_store.get(item_id, 0) or 0) + 1
        perf_debug(
            "label_editor_open_modal",
            item_id=item_id,
            mode=mode,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return True, body, item_id, updated_store, False

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Input("label-editor-save", "n_clicks"),
        State("active-item-store", "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "id"),
        State({"type": "note-editor-text", "filename": ALL}, "value"),
        State({"type": "note-editor-text", "filename": ALL}, "id"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        State("config-store", "data"),
        State("label-output-input", "value"),
        State("modal-bbox-store", "data"),
        State("current-filename", "data"),
        prevent_initial_call=True,
    )
    def save_label_editor(
        save_clicks,
        active_item_id,
        labels_list,
        labels_ids,
        note_values,
        note_ids,
        label_data,
        verify_data,
        explore_data,
        profile,
        mode,
        cfg,
        label_output_path,
        modal_bbox_store,
        current_modal_item_id,
    ):
        if not save_clicks or not active_item_id:
            raise PreventUpdate
        if mode == "explore":
            return no_update, no_update, no_update, False, [], no_update, no_update, no_update
        _require_complete_profile(profile, "save_label_editor")

        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}

        selected_labels = []
        for i, label_id in enumerate(labels_ids or []):
            if label_id.get("filename") == active_item_id:
                selected_labels = labels_list[i] or []
                break

        note_text = None
        for i, note_id in enumerate(note_ids or []):
            if note_id.get("filename") == active_item_id:
                note_text = note_values[i] if note_values else None
                break

        label_extents = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == active_item_id:
            label_extents = _extract_label_extent_map_from_boxes(
                modal_bbox_store.get("boxes") or []
            )

        if label_extents:
            merged = list(selected_labels or [])
            existing = set(merged)
            for label in label_extents.keys():
                if label not in existing:
                    merged.append(label)
                    existing.add(label)
            selected_labels = merged

        profile_name = _profile_actor(profile)
        updated = _update_item_labels(
            data or {},
            active_item_id,
            selected_labels,
            mode,
            user_name=profile_name,
            label_extents=label_extents or None,
        )
        if note_text is not None:
            updated = _update_item_notes(
                updated or {}, active_item_id, note_text, user_name=profile_name
            )

        if mode == "verify":
            pass
        elif mode == "label":
            cfg = cfg or {}
            labels_file = (
                label_output_path
                or (
                    updated.get("summary", {})
                    if isinstance(updated.get("summary"), dict)
                    else {}
                ).get("labels_file")
                or (cfg.get("label", {}) if isinstance(cfg.get("label"), dict) else {}).get(
                    "output_file"
                )
            )
            save_label_mode(
                labels_file,
                active_item_id,
                selected_labels,
                annotated_by=profile_name,
                notes=(note_text or ""),
                label_extents=label_extents or None,
            )
            updated = _update_item_labels(
                updated or {},
                active_item_id,
                selected_labels,
                mode="label",
                user_name=profile_name,
                is_reverification=True,
                label_extents=label_extents or None,
            )

        dirty_update = no_update
        snapshot_update = no_update
        updated_item = None
        if active_item_id and active_item_id == current_modal_item_id:
            updated_item = next(
                (
                    item
                    for item in (updated or {}).get("items", [])
                    if isinstance(item, dict) and item.get("item_id") == active_item_id
                ),
                None,
            )
            if isinstance(updated_item, dict):
                if (
                    isinstance(modal_bbox_store, dict)
                    and modal_bbox_store.get("item_id") == active_item_id
                ):
                    snapshot_boxes = modal_bbox_store.get("boxes") or []
                else:
                    snapshot_boxes = _build_modal_boxes_from_item(updated_item)
                if mode == "verify":
                    dirty_update = {"dirty": True, "item_id": active_item_id}
                else:
                    dirty_update = {"dirty": False, "item_id": active_item_id}
                    snapshot_update = _modal_snapshot_payload(
                        "label", active_item_id, updated_item, snapshot_boxes
                    )

        if mode == "label":
            return updated, no_update, no_update, False, [], dirty_update, snapshot_update, updated_item if active_item_id == current_modal_item_id else no_update
        if mode == "verify":
            return no_update, updated, no_update, False, [], dirty_update, snapshot_update, updated_item if active_item_id == current_modal_item_id else no_update
        return no_update, no_update, updated, False, [], dirty_update, snapshot_update, updated_item if active_item_id == current_modal_item_id else no_update
