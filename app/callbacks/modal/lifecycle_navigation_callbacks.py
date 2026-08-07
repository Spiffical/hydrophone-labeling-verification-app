"""Modal lifecycle callback for open/close/navigation actions."""

import time

from dash import ALL, ClientsideFunction, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.common.debug import perf_debug
from app.callbacks.modal.display_helpers import (
    build_modal_colorbar_ui,
    resolve_mode_value,
    resolve_mode_y_axis_limits,
)
from app.components.audio_player import (
    EQ_BAND_FREQUENCIES,
    EQ_LOW_FOCUS_MAX_HZ,
    create_modal_audio_player,
)
from app.services.verify_modal_cache import get_verify_modal_item
from app.utils.audio_settings import get_modal_amplification
from app.utils.audio_transport import prewarm_audio_delivery_paths
from app.utils.image_processing import (
    create_item_spectrogram_figure,
    is_modal_prefetch_enabled,
    prefetch_modal_images_in_background,
    prefetch_page_modal_spectrograms_in_background,
)
from app.utils.image_utils import build_modal_image_request_src, use_full_resolution_modal_image


MODAL_PREFETCH_NEXT_ITEMS = 6
MODAL_PREFETCH_PREVIOUS_ITEMS = 2


def _coerce_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_modal_prefetch_neighbors(
    mode,
    item_id,
    item_ids,
    source_items,
    verify_data_cache_key,
):
    if not item_id or item_id not in item_ids:
        return []

    current_index = item_ids.index(item_id)
    candidate_indices = [
        current_index + offset
        for offset in range(1, MODAL_PREFETCH_NEXT_ITEMS + 1)
    ]
    candidate_indices.extend(
        current_index - offset
        for offset in range(1, MODAL_PREFETCH_PREVIOUS_ITEMS + 1)
    )

    source_by_id = {
        item.get("item_id"): item
        for item in source_items
        if isinstance(item, dict) and item.get("item_id")
    }
    neighbors = []
    for candidate_index in candidate_indices:
        if candidate_index < 0 or candidate_index >= len(item_ids):
            continue
        candidate_id = item_ids[candidate_index]
        if mode == "verify":
            candidate = get_verify_modal_item(verify_data_cache_key, candidate_id)
        else:
            candidate = source_by_id.get(candidate_id)
        if isinstance(candidate, dict):
            neighbors.append(candidate)
    return neighbors


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
    app.clientside_callback(
        ClientsideFunction(
            namespace="modalLifecycle",
            function_name="openImmediately",
        ),
        Output("image-modal", "is_open", allow_duplicate=True),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Output("modal-open-request-store", "data"),
        Input({"type": "spectrogram-image", "item_id": ALL}, "n_clicks"),
        State("modal-unsaved-store", "data"),
        State("current-filename", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(
            namespace="modalLifecycle",
            function_name="closeImmediately",
        ),
        Output("image-modal", "is_open", allow_duplicate=True),
        Output("current-filename", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("unsaved-changes-modal", "is_open", allow_duplicate=True),
        Output("modal-pending-action-store", "data", allow_duplicate=True),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input("close-modal", "n_clicks"),
        Input("close-modal-header", "n_clicks"),
        State("modal-unsaved-store", "data"),
        State("current-filename", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(
            namespace="modalLifecycle",
            function_name="applyForcedAction",
        ),
        Output("image-modal", "is_open", allow_duplicate=True),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input("modal-force-action-store", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(
            namespace="modalLifecycle",
            function_name="finishLoading",
        ),
        Output("modal-busy-store", "data", allow_duplicate=True),
        Input("modal-item-store", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(
            namespace="modalLifecycle",
            function_name="prefetchImages",
        ),
        Output("modal-image-prefetch-store", "data"),
        Input("modal-image-graph", "figure"),
        prevent_initial_call=True,
    )

    @app.callback(
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
        Output("modal-colorbar-min-input", "placeholder", allow_duplicate=True),
        Output("modal-colorbar-max-input", "placeholder", allow_duplicate=True),
        Output("modal-colorbar-hint", "children", allow_duplicate=True),
        Output("modal-colormap-toggle", "value", allow_duplicate=True),
        Output("modal-y-axis-toggle", "value", allow_duplicate=True),
        Output("modal-yaxis-min-input", "value", allow_duplicate=True),
        Output("modal-yaxis-max-input", "value", allow_duplicate=True),
        Output("modal-colorbar-min-input", "value", allow_duplicate=True),
        Output("modal-colorbar-max-input", "value", allow_duplicate=True),
        Input("modal-open-request-store", "data"),
        Input("modal-nav-prev", "n_clicks"),
        Input("modal-nav-next", "n_clicks"),
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
        State("modal-yaxis-min-input", "value"),
        State("modal-yaxis-max-input", "value"),
        State("modal-colorbar-min-input", "value"),
        State("modal-colorbar-max-input", "value"),
        State("label-yaxis-min-input", "value"),
        State("label-yaxis-max-input", "value"),
        State("verify-yaxis-min-input", "value"),
        State("verify-yaxis-max-input", "value"),
        State("explore-yaxis-min-input", "value"),
        State("explore-yaxis-max-input", "value"),
        State("label-colormap-toggle", "value"),
        State("verify-colormap-toggle", "value"),
        State("explore-colormap-toggle", "value"),
        State("label-yaxis-toggle", "value"),
        State("verify-yaxis-toggle", "value"),
        State("explore-yaxis-toggle", "value"),
        State("label-colorbar-min-input", "value"),
        State("label-colorbar-max-input", "value"),
        State("verify-colorbar-min-input", "value"),
        State("verify-colorbar-max-input", "value"),
        State("explore-colorbar-min-input", "value"),
        State("explore-colorbar-max-input", "value"),
        State("modal-unsaved-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def handle_modal_trigger(
        open_request,
        prev_clicks,
        next_clicks,
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
        modal_y_axis_min_hz,
        modal_y_axis_max_hz,
        color_min,
        color_max,
        label_y_axis_min_hz,
        label_y_axis_max_hz,
        verify_y_axis_min_hz,
        verify_y_axis_max_hz,
        explore_y_axis_min_hz,
        explore_y_axis_max_hz,
        label_use_hydrophone_colormap,
        verify_use_hydrophone_colormap,
        explore_use_hydrophone_colormap,
        label_use_log_y_axis,
        verify_use_log_y_axis,
        explore_use_log_y_axis,
        label_color_min,
        label_color_max,
        verify_color_min,
        verify_color_max,
        explore_color_min,
        explore_color_max,
        unsaved_store,
        cfg,
    ):
        start = time.perf_counter()
        _ = prev_clicks, next_clicks
        mode = mode or "label"
        data = _get_mode_data(mode, label_data, None, explore_data)
        source_items = (data or {}).get("items", []) if isinstance(data, dict) else []
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
        elif triggered == "modal-open-request-store":
            if not isinstance(open_request, dict):
                raise PreventUpdate
            clicked_item_id = (open_request.get("item_id") or "").strip()
            if clicked_item_id:
                action = {
                    "kind": "open",
                    "item_id": clicked_item_id,
                    "inherit_page_display": True,
                }
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
                    True,
                    action,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
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
                    True,
                    action,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                )

        if action.get("kind") == "close":
            return (
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
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
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
            active_item = next(
                (i for i in page_items if isinstance(i, dict) and i.get("item_id") == item_id),
                None,
            )
            if not active_item:
                active_item = next(
                    (i for i in source_items if isinstance(i, dict) and i.get("item_id") == item_id),
                    None,
                )
            if not active_item:
                raise PreventUpdate
            source_item = next(
                (item for item in source_items if isinstance(item, dict) and item.get("item_id") == item_id),
                active_item,
            )
        if not isinstance(source_item, dict):
            raise PreventUpdate

        y_axis_min_hz, y_axis_max_hz = resolve_mode_y_axis_limits(
            mode,
            label_min=label_y_axis_min_hz,
            label_max=label_y_axis_max_hz,
            verify_min=verify_y_axis_min_hz,
            verify_max=verify_y_axis_max_hz,
            explore_min=explore_y_axis_min_hz,
            explore_max=explore_y_axis_max_hz,
        )
        page_use_hydrophone_colormap = resolve_mode_value(
            mode,
            label=label_use_hydrophone_colormap,
            verify=verify_use_hydrophone_colormap,
            explore=explore_use_hydrophone_colormap,
        )
        page_use_log_y_axis = resolve_mode_value(
            mode,
            label=label_use_log_y_axis,
            verify=verify_use_log_y_axis,
            explore=explore_use_log_y_axis,
        )
        page_color_min = resolve_mode_value(
            mode,
            label=label_color_min,
            verify=verify_color_min,
            explore=explore_color_min,
        )
        page_color_max = resolve_mode_value(
            mode,
            label=label_color_max,
            verify=verify_color_max,
            explore=explore_color_max,
        )
        page_y_axis_min_hz = y_axis_min_hz
        page_y_axis_max_hz = y_axis_max_hz
        page_display_color_min = page_color_min
        page_display_color_max = page_color_max
        display_cfg = (cfg or {}).get("display", {})
        page_colormap = (
            "hydrophone"
            if page_use_hydrophone_colormap
            else display_cfg.get("colormap", "default")
        )
        page_y_axis_scale = (
            "log" if page_use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
        )
        inherit_page_display = bool(action.get("inherit_page_display"))
        if inherit_page_display:
            colormap = page_colormap
            y_axis_scale = page_y_axis_scale
            modal_y_axis_min_hz = None
            modal_y_axis_max_hz = None
            color_min = None
            color_max = None
        effective_y_axis_min_hz = (
            modal_y_axis_min_hz
            if _coerce_float(modal_y_axis_min_hz) is not None
            else page_y_axis_min_hz
        )
        effective_y_axis_max_hz = (
            modal_y_axis_max_hz
            if _coerce_float(modal_y_axis_max_hz) is not None
            else page_y_axis_max_hz
        )
        use_page_y_range = (
            _coerce_float(modal_y_axis_min_hz) is None
            and _coerce_float(modal_y_axis_max_hz) is None
        )
        use_page_color_range = (
            _coerce_float(color_min) is None and _coerce_float(color_max) is None
        )
        effective_color_min = page_display_color_min if use_page_color_range else color_min
        effective_color_max = page_display_color_max if use_page_color_range else color_max
        modal_image_source = None
        if use_full_resolution_modal_image(cfg, y_axis_scale):
            modal_image_source = build_modal_image_request_src(
                source_item,
                cfg=cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=effective_y_axis_min_hz,
                y_axis_max_hz=effective_y_axis_max_hz,
                color_min=effective_color_min,
                color_max=effective_color_max,
            )
        fig, spectrogram = create_item_spectrogram_figure(
            source_item,
            cfg,
            colormap,
            y_axis_scale,
            y_axis_min_hz=effective_y_axis_min_hz,
            y_axis_max_hz=effective_y_axis_max_hz,
            color_min=effective_color_min,
            color_max=effective_color_max,
            image_source=modal_image_source,
        )
        figure_meta = dict(fig.layout.meta or {})
        figure_meta.update(
            {
                "uses_page_y_range": use_page_y_range,
                "uses_page_color_range": use_page_color_range,
                "modal_item_id": item_id,
                "display_colormap": colormap,
                "page_display_y_min_hz": page_y_axis_min_hz,
                "page_display_y_max_hz": page_y_axis_max_hz,
                "page_display_color_min": page_display_color_min,
                "page_display_color_max": page_display_color_max,
            }
        )
        fig.update_layout(meta=figure_meta)
        modal_neighbors = []
        if is_modal_prefetch_enabled(cfg):
            modal_neighbors = _collect_modal_prefetch_neighbors(
                mode,
                item_id,
                page_item_ids,
                source_items,
                verify_data_cache_key,
            )
            prefetch_page_modal_spectrograms_in_background(modal_neighbors, cfg)
            if modal_image_source:
                prefetch_modal_images_in_background(
                    modal_neighbors,
                    cfg,
                    colormap=colormap,
                    y_axis_scale=y_axis_scale,
                    y_axis_min_hz=effective_y_axis_min_hz,
                    y_axis_max_hz=effective_y_axis_max_hz,
                    color_min=effective_color_min,
                    color_max=effective_color_max,
                )
        if modal_image_source and modal_neighbors:
            prefetch_urls = [
                build_modal_image_request_src(
                    neighbor,
                    cfg=cfg,
                    colormap=colormap,
                    y_axis_scale=y_axis_scale,
                    y_axis_min_hz=effective_y_axis_min_hz,
                    y_axis_max_hz=effective_y_axis_max_hz,
                    color_min=effective_color_min,
                    color_max=effective_color_max,
                )
                for neighbor in modal_neighbors
            ]
            figure_meta = dict(fig.layout.meta or {})
            figure_meta["prefetch_image_urls"] = prefetch_urls
            fig.update_layout(meta=figure_meta)
        modal_boxes = _build_modal_boxes_from_item(source_item)
        fig = _apply_modal_boxes_to_figure(fig, modal_boxes)
        placeholder_min, placeholder_max, colorbar_hint = build_modal_colorbar_ui(fig)
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
        gain_value = get_modal_amplification(settings)
        visible_filter_enabled = bool(settings.get("visible_filter", False))
        audio_cfg = (cfg or {}).get("audio", {}) if isinstance(cfg, dict) else {}
        audio_transport = audio_cfg.get("transport", "direct")
        audio_mp3_bitrate = audio_cfg.get("mp3_bitrate")
        audio_cache_dir = audio_cfg.get("cache_dir")

        audio_path = source_item.get("audio_path")
        modal_audio = (
            create_modal_audio_player(
                audio_path,
                item_id,
                player_id="modal-player",
                pitch_value=pitch_value,
                eq_values=eq_values,
                gain_value=gain_value,
                visible_filter_enabled=visible_filter_enabled,
                transport=audio_transport,
                mp3_bitrate=audio_mp3_bitrate,
            )
            if audio_path
            else html.P("No audio available for this item.", className="text-muted italic")
        )

        # Warm the current item plus one neighbor on each side without slowing the modal render.
        candidate_items = []
        if item_id in page_item_ids:
            current_index = page_item_ids.index(item_id)
            nearby_ids = page_item_ids[max(0, current_index - 1) : min(len(page_item_ids), current_index + 2)]
        else:
            nearby_ids = [item_id]

        for candidate_id in nearby_ids:
            if candidate_id == item_id:
                candidate_item = source_item
            elif mode == "verify":
                candidate_item = get_verify_modal_item(verify_data_cache_key, candidate_id)
            else:
                candidate_item = next(
                    (i for i in page_items if isinstance(i, dict) and i.get("item_id") == candidate_id),
                    None,
                )
                if not candidate_item:
                    candidate_item = next(
                        (
                            i
                            for i in source_items
                            if isinstance(i, dict) and i.get("item_id") == candidate_id
                        ),
                        None,
                    )
            if isinstance(candidate_item, dict):
                candidate_items.append(candidate_item)

        prewarm_audio_delivery_paths(
            (candidate.get("audio_path") for candidate in candidate_items),
            transport=audio_transport,
            mp3_bitrate=audio_mp3_bitrate,
            cache_dir=audio_cache_dir,
        )

        modal_actions = _build_modal_item_actions(
            source_item,
            mode,
            thresholds or {"__global__": 0.5},
            boxes=modal_boxes,
            active_box_label=default_box_label,
            config=cfg,
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
            placeholder_min,
            placeholder_max,
            colorbar_hint,
            colormap if inherit_page_display else no_update,
            y_axis_scale if inherit_page_display else no_update,
            None if inherit_page_display else no_update,
            None if inherit_page_display else no_update,
            None if inherit_page_display else no_update,
            None if inherit_page_display else no_update,
        )
