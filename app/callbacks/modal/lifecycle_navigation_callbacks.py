"""Modal lifecycle callback for open/close/navigation actions."""

import time

from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.common.debug import perf_debug
from app.components.audio_player import (
    EQ_BAND_FREQUENCIES,
    EQ_LOW_FOCUS_MAX_HZ,
    create_modal_audio_player,
)
from app.services.verify_modal_cache import get_verify_modal_item
from app.utils.image_processing import create_spectrogram_figure, resolve_item_spectrogram


def register_modal_lifecycle_navigation_callbacks(
    app,
    *,
    _get_mode_data,
    _get_modal_navigation_items,
    _is_modal_dirty,
    _modal_snapshot_payload,
    _build_modal_boxes_from_item,
    _apply_modal_boxes_to_figure,
    _build_modal_item_actions,
):
    @app.callback(
        Output("image-modal", "is_open"),
        Output("current-filename", "data"),
        Output("modal-item-store", "data"),
        Output("modal-image-graph", "figure"),
        Output("modal-bbox-store", "data"),
        Output("modal-active-box-label", "data"),
        Output("modal-header", "children"),
        Output("modal-audio-player", "children"),
        Output("modal-item-actions", "children"),
        Output("modal-nav-prev", "disabled"),
        Output("modal-nav-next", "disabled"),
        Output("modal-nav-position", "children"),
        Output("modal-snapshot-store", "data"),
        Output("modal-unsaved-store", "data"),
        Output("unsaved-changes-modal", "is_open"),
        Output("modal-pending-action-store", "data"),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input({"type": "spectrogram-image", "item_id": ALL}, "n_clicks"),
        Input("modal-nav-prev", "n_clicks"),
        Input("modal-nav-next", "n_clicks"),
        Input("close-modal", "n_clicks"),
        Input("modal-force-action-store", "data"),
        State("label-data-store", "data"),
        State("explore-data-store", "data"),
        State("verify-visible-item-ids-store", "data"),
        State("verify-data-cache-key-store", "data"),
        State("mode-tabs", "data"),
        State("verify-thresholds-store", "data"),
        State("modal-audio-settings-store", "data"),
        State("current-filename", "data"),
        State("modal-colormap-toggle", "value"),
        State("modal-y-axis-toggle", "value"),
        State("modal-unsaved-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def handle_modal_trigger(
        image_clicks_list,
        prev_clicks,
        next_clicks,
        close_clicks,
        force_action,
        label_data,
        explore_data,
        verify_visible_item_ids,
        verify_data_cache_key,
        mode,
        thresholds,
        audio_settings,
        current_item_id,
        colormap,
        y_axis_scale,
        unsaved_store,
        cfg,
    ):
        start = time.perf_counter()
        _ = prev_clicks, next_clicks, close_clicks
        mode = mode or "label"
        data = _get_mode_data(mode, label_data, None, explore_data)
        triggered = ctx.triggered_id

        page_items = []
        if mode == "verify":
            page_item_ids = [
                item_id.strip()
                for item_id in (verify_visible_item_ids or [])
                if isinstance(item_id, str) and item_id.strip()
            ]
        else:
            page_items = _get_modal_navigation_items(
                mode,
                label_data,
                None,
                explore_data,
                thresholds,
                None,
            )
            page_item_ids = [item.get("item_id") for item in page_items if item and item.get("item_id")]

        is_forced = triggered == "modal-force-action-store"
        action = None
        if is_forced:
            if not isinstance(force_action, dict):
                raise PreventUpdate
            candidate = force_action.get("action")
            if isinstance(candidate, dict) and candidate.get("kind") in {"close", "open"}:
                action = candidate
        elif triggered == "close-modal":
            action = {"kind": "close"}
        elif isinstance(triggered, dict) and triggered.get("type") == "spectrogram-image":
            if not any(image_clicks_list):
                raise PreventUpdate
            clicked_item_id = (triggered.get("item_id") or "").strip()
            if clicked_item_id:
                action = {"kind": "open", "item_id": clicked_item_id}
        elif triggered in {"modal-nav-prev", "modal-nav-next"}:
            if not current_item_id or not page_item_ids:
                raise PreventUpdate
            if current_item_id not in page_item_ids:
                action = {"kind": "open", "item_id": page_item_ids[0]}
            else:
                current_index = page_item_ids.index(current_item_id)
                if triggered == "modal-nav-prev":
                    target_item_id = page_item_ids[max(0, current_index - 1)]
                else:
                    target_item_id = page_item_ids[min(len(page_item_ids) - 1, current_index + 1)]
                action = {"kind": "open", "item_id": target_item_id}
        if not isinstance(action, dict):
            raise PreventUpdate

        is_dirty = _is_modal_dirty(unsaved_store, current_item_id=current_item_id)
        if not is_forced and is_dirty:
            if action.get("kind") == "close":
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    action,
                    False,
                )
            pending_item_id = (action.get("item_id") or "").strip() if action.get("kind") == "open" else ""
            if pending_item_id and pending_item_id != current_item_id:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    action,
                    False,
                )

        if action.get("kind") == "close":
            return (
                False,
                None,
                None,
                no_update,
                {"item_id": None, "boxes": []},
                None,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                None,
                {"dirty": False, "item_id": None},
                False,
                None,
                False,
            )

        item_id = (action.get("item_id") or "").strip()

        if not item_id:
            raise PreventUpdate
        if item_id == current_item_id and not is_forced:
            raise PreventUpdate

        if mode == "verify":
            source_item = get_verify_modal_item(verify_data_cache_key, item_id)
            active_item = source_item
        else:
            active_item = next((i for i in page_items if i.get("item_id") == item_id), None)
            if not active_item:
                items = (data or {}).get("items", [])
                active_item = next((i for i in items if i.get("item_id") == item_id), None)
            if not active_item:
                raise PreventUpdate
            source_items = (data or {}).get("items", [])
            source_item = next(
                (item for item in source_items if isinstance(item, dict) and item.get("item_id") == item_id),
                active_item,
            )
        if not isinstance(source_item, dict):
            raise PreventUpdate

        spectrogram = resolve_item_spectrogram(source_item, cfg)
        fig = create_spectrogram_figure(spectrogram, colormap, y_axis_scale, cfg=cfg)
        modal_boxes = _build_modal_boxes_from_item(source_item)
        fig = _apply_modal_boxes_to_figure(fig, modal_boxes)
        default_box_label = None

        settings = audio_settings or {}
        pitch_value = settings.get("pitch", 1.0)
        legacy_bass = settings.get("bass", 0.0)
        eq_values = {}
        for frequency in EQ_BAND_FREQUENCIES:
            eq_key = f"eq_{frequency}"
            if eq_key in settings:
                raw_eq_value = settings.get(eq_key)
            elif frequency <= EQ_LOW_FOCUS_MAX_HZ:
                raw_eq_value = legacy_bass
            else:
                raw_eq_value = 0.0
            try:
                eq_values[eq_key] = max(-24.0, min(24.0, float(raw_eq_value)))
            except (TypeError, ValueError):
                eq_values[eq_key] = 0.0
        gain_value = settings.get("gain", 1.0)

        audio_path = source_item.get("audio_path")
        modal_audio = (
            create_modal_audio_player(
                audio_path,
                item_id,
                player_id="modal-player",
                pitch_value=pitch_value,
                eq_values=eq_values,
                gain_value=gain_value,
            )
            if audio_path
            else html.P("No audio available for this item.", className="text-muted italic")
        )

        modal_actions = _build_modal_item_actions(
            source_item,
            mode,
            thresholds or {"__global__": 0.5},
            boxes=modal_boxes,
            active_box_label=default_box_label,
        )

        if not page_item_ids:
            prev_disabled = True
            next_disabled = True
            position = "1 / 1"
        else:
            current_index = page_item_ids.index(item_id) if item_id in page_item_ids else 0
            prev_disabled = current_index <= 0
            next_disabled = current_index >= len(page_item_ids) - 1
            position = f"{current_index + 1} / {len(page_item_ids)}"

        snapshot_payload = _modal_snapshot_payload(mode, item_id, source_item, modal_boxes)
        perf_debug(
            "modal_nav",
            triggered=str(triggered),
            mode=mode,
            item_id=item_id,
            visible_items=len(page_item_ids),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )

        return (
            True,
            item_id,
            source_item,
            fig,
            {"item_id": item_id, "boxes": modal_boxes},
            default_box_label,
            f"Spectrogram: {item_id}",
            modal_audio,
            modal_actions,
            prev_disabled,
            next_disabled,
            position,
            snapshot_payload,
            {"dirty": False, "item_id": item_id},
            False,
            None,
            False,
        )
