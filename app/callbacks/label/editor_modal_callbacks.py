"""Callbacks for opening and saving the hierarchical label editor modal."""

import time

from dash import ALL, Input, Output, Patch, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.common.debug import perf_debug
from app.callbacks.verify.ui_update_helpers import build_verify_card_ui_updates
from app.services.annotations import extract_box_annotations_from_boxes, ordered_unique_labels
from app.services.verification import get_modal_label_sets
from app.services.verify_modal_cache import (
    get_verify_modal_item,
    get_verify_modal_item_index,
    get_verify_modal_summary,
    update_verify_modal_item,
)
from app.services.verify_pagination import save_single_verify_item_change


def _resolve_selected_labels(item, mode, thresholds, _filter_predictions):
    if not isinstance(item, dict):
        return [], ""
    annotations = item.get("annotations") or {}
    predicted = item.get("predictions", {}) if isinstance(item.get("predictions"), dict) else {}
    existing_note = annotations.get("notes", "") if isinstance(annotations, dict) else ""
    if mode in {"label", "verify"}:
        _, _, selected_labels = get_modal_label_sets(item, mode, thresholds or {"__global__": 0.5})
    else:
        selected_labels = annotations.get("labels") or predicted.get("labels") or []
    return ordered_unique_labels(selected_labels), existing_note


def _resolve_grid_editor_item_id(n_clicks_list, click_store, edit_ids, triggered_id):
    click_store = click_store or {}
    updated_store = dict(click_store)
    chosen_item_id = None

    if n_clicks_list and edit_ids:
        for i, id_dict in enumerate(edit_ids):
            if not isinstance(id_dict, dict):
                continue
            item_id = id_dict.get("item_id")
            if not item_id:
                continue
            current_clicks = n_clicks_list[i] or 0
            previous_clicks = click_store.get(item_id, 0)
            updated_store[item_id] = current_clicks
            if current_clicks > previous_clicks:
                chosen_item_id = item_id

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "edit-btn":
        triggered_item_id = (triggered_id.get("item_id") or "").strip()
        if triggered_item_id:
            for i, id_dict in enumerate(edit_ids or []):
                if not isinstance(id_dict, dict) or id_dict.get("item_id") != triggered_item_id:
                    continue
                current_clicks = (n_clicks_list or [])[i] if i < len(n_clicks_list or []) else 0
                if (current_clicks or 0) > 0:
                    chosen_item_id = triggered_item_id
                break

    return chosen_item_id, updated_store


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
    _build_modal_item_actions,
    _modal_snapshot_payload,
):
    app.clientside_callback(
        """
        function(cancelClicks) {
            var dc = (window.dash_clientside || {});
            if (!cancelClicks) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            return [false, [], null];
        }
        """,
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Input("label-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(editClicks, profile, mode) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (!ctx || !ctx.triggered || ctx.triggered.length === 0 || mode === "explore") {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            profile = profile || {};
            var name = String(profile.name || "").trim();
            var email = String(profile.email || "").trim();
            var triggered = ctx.triggered[0] || {};
            var hasClick = Array.isArray(editClicks) && editClicks.some(function(value) {
                return typeof value === "number" && value > 0;
            });
            if (!name || email.indexOf("@") === -1 || !hasClick || !triggered.value) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            return [true, "Loading label editor...", null];
        }
        """,
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Input({"type": "modal-action-edit", "scope": ALL}, "n_clicks"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(editClicks, editIds, profile, mode) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (!ctx || !ctx.triggered || ctx.triggered.length === 0) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            if (mode === "explore") {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            profile = profile || {};
            var name = String(profile.name || "").trim();
            var email = String(profile.email || "").trim();
            if (!name || email.indexOf("@") === -1) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            var triggered = ctx.triggered[0] || {};
            if (!triggered.value) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            return [true, "Loading label editor...", null];
        }
        """,
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Input({"type": "edit-btn", "item_id": ALL}, "n_clicks"),
        State({"type": "edit-btn", "item_id": ALL}, "id"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("label-editor-modal", "is_open"),
        Output("label-editor-body", "children"),
        Output("active-item-store", "data"),
        Output("label-editor-clicks", "data"),
        Input({"type": "edit-btn", "item_id": ALL}, "n_clicks"),
        State("label-editor-clicks", "data"),
        State({"type": "edit-btn", "item_id": ALL}, "id"),
        State("label-data-store", "data"),
        State("explore-data-store", "data"),
        State("active-item-store", "data"),
        State("verify-thresholds-store", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        State("verify-data-cache-key-store", "data"),
        prevent_initial_call=True,
    )
    def open_label_editor(
        n_clicks_list,
        click_store,
        edit_ids,
        label_data,
        explore_data,
        active_item_id,
        thresholds,
        mode,
        profile,
        verify_data_cache_key,
    ):
        start = time.perf_counter()
        _ = active_item_id
        triggered = ctx.triggered_id
        if mode == "explore":
            return False, no_update, None, click_store or {}

        if not n_clicks_list or not edit_ids:
            return no_update, no_update, no_update, click_store

        chosen_item_id, updated_store = _resolve_grid_editor_item_id(
            n_clicks_list,
            click_store,
            edit_ids,
            triggered,
        )
        if not chosen_item_id:
            return False, [], None, updated_store

        _require_complete_profile(profile, "open_label_editor")

        if mode == "verify":
            chosen_item = get_verify_modal_item(verify_data_cache_key, chosen_item_id)
        else:
            data = _get_mode_data(mode, label_data, None, explore_data)
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
            return False, [], None, updated_store
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
        perf_debug(
            "label_editor_open_modal",
            item_id=item_id,
            mode=mode,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return True, body, item_id, click_store or {}, False

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-item-actions", "children", allow_duplicate=True),
        Output({"type": "verify-label-block", "item_id": ALL}, "children", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Input("label-editor-save", "n_clicks"),
        State("active-item-store", "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "id"),
        State({"type": "note-editor-text", "filename": ALL}, "value"),
        State({"type": "note-editor-text", "filename": ALL}, "id"),
        State("label-data-store", "data"),
        State("explore-data-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        State("verify-thresholds-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State("config-store", "data"),
        State("label-output-input", "value"),
        State("modal-bbox-store", "data"),
        State("current-filename", "data"),
        State("modal-active-box-label", "data"),
        State({"type": "verify-label-block", "item_id": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        running=[
            (Output("label-editor-save", "disabled"), True, False),
            (Output("label-editor-save", "children"), "Saving...", "Save Labels"),
        ],
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
        explore_data,
        profile,
        mode,
        thresholds,
        verify_data_cache_key,
        cfg,
        label_output_path,
        modal_bbox_store,
        current_modal_item_id,
        active_box_label,
        label_block_ids,
        save_button_ids,
    ):
        if not save_clicks or not active_item_id:
            raise PreventUpdate
        if mode == "explore":
            return (
                no_update,
                no_update,
                no_update,
                False,
                [],
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        _require_complete_profile(profile, "save_label_editor")

        if mode == "verify":
            active_item = get_verify_modal_item(verify_data_cache_key, active_item_id)
            active_item_index = get_verify_modal_item_index(verify_data_cache_key, active_item_id)
            if not isinstance(active_item, dict) or active_item_index is None:
                raise PreventUpdate
            summary = get_verify_modal_summary(verify_data_cache_key) or {}
            data = {"items": [active_item], "summary": summary}
        else:
            data = {"label": label_data, "explore": explore_data}.get(mode) or {}

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
        bbox_annotations = []
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == active_item_id:
            modal_boxes = modal_bbox_store.get("boxes") or []
            label_extents = _extract_label_extent_map_from_boxes(modal_boxes)
            bbox_annotations = extract_box_annotations_from_boxes(modal_boxes)

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
            bbox_annotations=bbox_annotations,
        )
        if note_text is not None:
            updated = _update_item_notes(
                updated or {}, active_item_id, note_text, user_name=profile_name
            )

        if mode == "verify":
            updated_item = next(
                (
                    item
                    for item in (updated or {}).get("items", [])
                    if isinstance(item, dict) and item.get("item_id") == active_item_id
                ),
                None,
            )
            if not isinstance(updated_item, dict):
                raise PreventUpdate
            summary_predictions_file = (
                summary.get("predictions_file") if isinstance(summary, dict) else None
            )
            updated_item, _ = save_single_verify_item_change(
                updated_item,
                summary_predictions_file,
                thresholds or {"__global__": 0.5},
                profile_name,
            )
            if not isinstance(updated_item, dict):
                raise PreventUpdate
            update_verify_modal_item(verify_data_cache_key, updated_item)
            verify_patch = Patch()
            verify_patch["items"][active_item_index] = updated_item
            next_summary = get_verify_modal_summary(verify_data_cache_key)
            if isinstance(next_summary, dict):
                verify_patch["summary"] = next_summary
            updated = {"items": [updated_item], "summary": next_summary or summary}
            verify_store_update = no_update if active_item_id == current_modal_item_id else verify_patch
            direct_ui_updates = build_verify_card_ui_updates(
                active_item_id,
                updated_item,
                label_block_ids,
                save_button_ids,
                predicted_labels=_filter_predictions(updated_item.get("predictions") or {}, thresholds),
                pending=False,
            )
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
                bbox_annotations=bbox_annotations or None,
            )
            updated = _update_item_labels(
                updated or {},
                active_item_id,
                selected_labels,
                mode="label",
                user_name=profile_name,
                is_reverification=True,
                label_extents=label_extents or None,
                bbox_annotations=bbox_annotations,
            )

        dirty_update = no_update
        snapshot_update = no_update
        modal_actions_update = no_update
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
                modal_actions_update = _build_modal_item_actions(
                    updated_item,
                    mode,
                    thresholds or {"__global__": 0.5},
                    boxes=snapshot_boxes,
                    active_box_label=active_box_label,
                    config=cfg,
                )
                if mode == "verify":
                    dirty_update = {"dirty": False, "item_id": active_item_id}
                    snapshot_update = _modal_snapshot_payload(
                        "verify", active_item_id, updated_item, snapshot_boxes
                    )
                else:
                    dirty_update = {"dirty": False, "item_id": active_item_id}
                    snapshot_update = _modal_snapshot_payload(
                        "label", active_item_id, updated_item, snapshot_boxes
                    )

        if mode == "label":
            return (
                updated,
                no_update,
                no_update,
                False,
                [],
                dirty_update,
                snapshot_update,
                updated_item if active_item_id == current_modal_item_id else no_update,
                modal_actions_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        if mode == "verify":
            return (
                no_update,
                verify_store_update,
                no_update,
                False,
                [],
                dirty_update,
                snapshot_update,
                updated_item if active_item_id == current_modal_item_id else no_update,
                modal_actions_update,
                *direct_ui_updates,
            )
        return (
            no_update,
            no_update,
            updated,
            False,
            [],
            dirty_update,
            snapshot_update,
            updated_item if active_item_id == current_modal_item_id else no_update,
            modal_actions_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )
