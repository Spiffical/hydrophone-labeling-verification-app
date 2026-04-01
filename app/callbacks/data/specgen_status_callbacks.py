"""Track per-page spectrogram-generation workload for UI loading overlays."""

import os
import time

from dash import Input, Output, State, ctx
from dash.exceptions import PreventUpdate


_SPECGEN_DEBUG = os.getenv("HYDRO_SPECGEN_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _slice_page(items, current_page, items_per_page):
    total_items = len(items)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    page_index = max(0, min(current_page or 0, total_pages - 1))
    start_idx = page_index * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx], page_index, total_pages


def _coerce_page_index(page):
    try:
        return int(page or 0)
    except (TypeError, ValueError):
        return 0


def _debug_status(mode, status):
    if not _SPECGEN_DEBUG:
        return
    if not isinstance(status, dict):
        print(f"[specgen-status] mode={mode} status=<invalid>", flush=True)
        return
    params = status.get("params") or {}
    print(
        "[specgen-status] "
        f"mode={mode} page={status.get('page_index')}/{status.get('total_pages')} "
        f"source={status.get('source')} eligible={status.get('eligible')} pending={status.get('pending')} "
        f"win={params.get('win_dur_s')} ov={params.get('overlap')} "
        f"fmin={params.get('freq_min_hz')} fmax={params.get('freq_max_hz')} "
        f"t={status.get('computed_at')}",
        flush=True,
    )


def register_specgen_status_callbacks(
    app,
    *,
    _estimate_page_audio_generation_work,
    _filter_predictions,
    _predicted_labels_match_filter,
    _extract_verify_leaf_classes,
    _build_verify_filter_paths,
    _normalize_verify_class_filter,
):
    @app.callback(
        Output("specgen-overlay-preview-store", "data"),
        Input("specgen-overlay-request-store", "data"),
        State("label-data-store", "data"),
        State("label-colormap-toggle", "value"),
        State("label-yaxis-toggle", "value"),
        State("label-yaxis-min-input", "value"),
        State("label-yaxis-max-input", "value"),
        State("label-colorbar-min-input", "value"),
        State("label-colorbar-max-input", "value"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("verify-class-filter", "data"),
        State("verify-colormap-toggle", "value"),
        State("verify-yaxis-toggle", "value"),
        State("verify-yaxis-min-input", "value"),
        State("verify-yaxis-max-input", "value"),
        State("verify-colorbar-min-input", "value"),
        State("verify-colorbar-max-input", "value"),
        State("explore-data-store", "data"),
        State("explore-colormap-toggle", "value"),
        State("explore-yaxis-toggle", "value"),
        State("explore-yaxis-min-input", "value"),
        State("explore-yaxis-max-input", "value"),
        State("explore-colorbar-min-input", "value"),
        State("explore-colorbar-max-input", "value"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def compute_request_preview(
        specgen_request,
        label_data,
        label_use_hydrophone_colormap,
        label_use_log_y_axis,
        label_y_axis_min_hz,
        label_y_axis_max_hz,
        label_color_min,
        label_color_max,
        verify_data,
        verify_thresholds,
        verify_class_filter,
        verify_use_hydrophone_colormap,
        verify_use_log_y_axis,
        verify_y_axis_min_hz,
        verify_y_axis_max_hz,
        verify_color_min,
        verify_color_max,
        explore_data,
        explore_use_hydrophone_colormap,
        explore_use_log_y_axis,
        explore_y_axis_min_hz,
        explore_y_axis_max_hz,
        explore_color_min,
        explore_color_max,
        cfg,
    ):
        cfg = cfg or {}
        if not isinstance(specgen_request, dict):
            return None

        request_mode = str(specgen_request.get("mode") or "label")
        request_page = _coerce_page_index(specgen_request.get("page"))
        source = str(((cfg.get("spectrogram_render", {}) or {}).get("source", "existing")))
        if source != "audio_generated":
            return None

        display_cfg = cfg.get("display", {})
        items_per_page = display_cfg.get("items_per_page", 25)
        items = []
        colormap = display_cfg.get("colormap", "default")
        y_axis_scale = display_cfg.get("y_axis_scale", "linear")
        y_axis_min_hz = None
        y_axis_max_hz = None
        color_min = None
        color_max = None

        if request_mode == "verify":
            verify_data = verify_data or {"items": []}
            items = verify_data.get("items", []) or []
            verify_thresholds = verify_thresholds or {"__global__": 0.5}
            available_values = _build_verify_filter_paths(_extract_verify_leaf_classes(items))
            available_value_set = set(available_values)
            selected_filters = _normalize_verify_class_filter(verify_class_filter)
            if not available_values:
                selected_filters = None
            if selected_filters is not None:
                selected_filters = [value for value in selected_filters if value in available_value_set]

            filtered_items = []
            for item in items:
                if not item:
                    continue
                annotations = item.get("annotations") or {}
                is_verified = bool(annotations.get("verified"))
                predictions = item.get("predictions") or {}
                predicted_labels = _filter_predictions(predictions, verify_thresholds)
                if not is_verified and not predicted_labels:
                    continue
                if not _predicted_labels_match_filter(predicted_labels, selected_filters):
                    continue
                filtered_items.append(item)

            items = filtered_items
            colormap = "hydrophone" if verify_use_hydrophone_colormap else display_cfg.get("colormap", "default")
            y_axis_scale = "log" if verify_use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
            y_axis_min_hz = verify_y_axis_min_hz
            y_axis_max_hz = verify_y_axis_max_hz
            color_min = verify_color_min
            color_max = verify_color_max
        elif request_mode == "explore":
            explore_data = explore_data or {"items": []}
            items = explore_data.get("items", []) or []
            colormap = "hydrophone" if explore_use_hydrophone_colormap else display_cfg.get("colormap", "default")
            y_axis_scale = "log" if explore_use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
            y_axis_min_hz = explore_y_axis_min_hz
            y_axis_max_hz = explore_y_axis_max_hz
            color_min = explore_color_min
            color_max = explore_color_max
        else:
            label_data = label_data or {"items": []}
            items = label_data.get("items", []) or []
            colormap = "hydrophone" if label_use_hydrophone_colormap else display_cfg.get("colormap", "default")
            y_axis_scale = "log" if label_use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
            y_axis_min_hz = label_y_axis_min_hz
            y_axis_max_hz = label_y_axis_max_hz
            color_min = label_color_min
            color_max = label_color_max

        page_items, page_index, total_pages = _slice_page(items, request_page, items_per_page)
        status = _estimate_page_audio_generation_work(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )
        status.update(
            {
                "mode": request_mode,
                "page_index": int(page_index),
                "total_pages": int(total_pages),
                "items_per_page": int(items_per_page),
                "computed_at": time.time(),
                "request_preview": True,
            }
        )
        _debug_status(f"{request_mode}-preview", status)
        return status

    @app.callback(
        Output("label-page-specgen-store", "data"),
        Input("label-data-store", "data"),
        Input("label-colormap-toggle", "value"),
        Input("label-yaxis-toggle", "value"),
        Input("label-yaxis-min-input", "value"),
        Input("label-yaxis-max-input", "value"),
        Input("label-colorbar-min-input", "value"),
        Input("label-colorbar-max-input", "value"),
        Input("label-current-page", "data"),
        Input("config-store", "data"),
        Input("mode-tabs", "data"),
        Input("specgen-overlay-request-store", "data"),
        Input("specgen-overlay-poll", "n_intervals"),
    )
    def compute_label_status(
        data,
        use_hydrophone_colormap,
        use_log_y_axis,
        y_axis_min_hz,
        y_axis_max_hz,
        color_min,
        color_max,
        current_page,
        cfg,
        mode_tabs,
        specgen_request,
        poll_tick,
    ):
        cfg = cfg or {}
        _ = poll_tick
        triggered_id = ctx.triggered_id
        request_mode = (specgen_request or {}).get("mode") if isinstance(specgen_request, dict) else None
        request_page = (specgen_request or {}).get("page") if isinstance(specgen_request, dict) else None
        active_mode = str(mode_tabs or "label")
        source = str(((cfg.get("spectrogram_render", {}) or {}).get("source", "existing")))
        if triggered_id == "specgen-overlay-request-store" and request_mode and request_mode != "label":
            raise PreventUpdate
        if triggered_id == "specgen-overlay-poll" and (active_mode != "label" or source != "audio_generated"):
            raise PreventUpdate
        data = data or {"items": []}
        items = data.get("items", []) or []
        display_cfg = cfg.get("display", {})
        colormap = "hydrophone" if use_hydrophone_colormap else display_cfg.get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
        items_per_page = display_cfg.get("items_per_page", 25)
        effective_page = _coerce_page_index(current_page)
        if request_mode == "label" and request_page is not None and triggered_id in {"specgen-overlay-request-store", "specgen-overlay-poll"}:
            effective_page = _coerce_page_index(request_page)
        page_items, page_index, total_pages = _slice_page(items, effective_page, items_per_page)
        status = _estimate_page_audio_generation_work(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )
        status.update(
            {
                "mode": "label",
                "page_index": int(page_index),
                "total_pages": int(total_pages),
                "items_per_page": int(items_per_page),
                "computed_at": time.time(),
            }
        )
        _debug_status("label", status)
        return status

    @app.callback(
        Output("verify-page-specgen-store", "data"),
        Input("verify-data-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-current-page", "data"),
        Input("verify-colormap-toggle", "value"),
        Input("verify-yaxis-toggle", "value"),
        Input("verify-yaxis-min-input", "value"),
        Input("verify-yaxis-max-input", "value"),
        Input("verify-colorbar-min-input", "value"),
        Input("verify-colorbar-max-input", "value"),
        Input("config-store", "data"),
        Input("mode-tabs", "data"),
        Input("specgen-overlay-request-store", "data"),
        Input("specgen-overlay-poll", "n_intervals"),
    )
    def compute_verify_status(
        data,
        thresholds,
        class_filter,
        current_page,
        use_hydrophone_colormap,
        use_log_y_axis,
        y_axis_min_hz,
        y_axis_max_hz,
        color_min,
        color_max,
        cfg,
        mode_tabs,
        specgen_request,
        poll_tick,
    ):
        cfg = cfg or {}
        _ = poll_tick
        triggered_id = ctx.triggered_id
        request_mode = (specgen_request or {}).get("mode") if isinstance(specgen_request, dict) else None
        request_page = (specgen_request or {}).get("page") if isinstance(specgen_request, dict) else None
        active_mode = str(mode_tabs or "label")
        source = str(((cfg.get("spectrogram_render", {}) or {}).get("source", "existing")))
        if triggered_id == "specgen-overlay-request-store" and request_mode and request_mode != "verify":
            raise PreventUpdate
        if triggered_id == "specgen-overlay-poll" and (active_mode != "verify" or source != "audio_generated"):
            raise PreventUpdate
        data = data or {"items": []}
        items = data.get("items", []) or []
        thresholds = thresholds or {"__global__": 0.5}

        available_values = _build_verify_filter_paths(_extract_verify_leaf_classes(items))
        available_value_set = set(available_values)
        selected_filters = _normalize_verify_class_filter(class_filter)
        if not available_values:
            selected_filters = None
        if selected_filters is not None:
            selected_filters = [value for value in selected_filters if value in available_value_set]

        filtered_items = []
        for item in items:
            if not item:
                continue
            annotations = item.get("annotations") or {}
            is_verified = bool(annotations.get("verified"))
            predictions = item.get("predictions") or {}
            predicted_labels = _filter_predictions(predictions, thresholds)
            if not is_verified and not predicted_labels:
                continue
            if not _predicted_labels_match_filter(predicted_labels, selected_filters):
                continue
            filtered_items.append(item)

        display_cfg = cfg.get("display", {})
        colormap = "hydrophone" if use_hydrophone_colormap else display_cfg.get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
        items_per_page = display_cfg.get("items_per_page", 25)
        effective_page = _coerce_page_index(current_page)
        if request_mode == "verify" and request_page is not None and triggered_id in {"specgen-overlay-request-store", "specgen-overlay-poll"}:
            effective_page = _coerce_page_index(request_page)
        page_items, page_index, total_pages = _slice_page(filtered_items, effective_page, items_per_page)

        status = _estimate_page_audio_generation_work(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )
        status.update(
            {
                "mode": "verify",
                "page_index": int(page_index),
                "total_pages": int(total_pages),
                "items_per_page": int(items_per_page),
                "computed_at": time.time(),
            }
        )
        _debug_status("verify", status)
        return status

    @app.callback(
        Output("explore-page-specgen-store", "data"),
        Input("explore-data-store", "data"),
        Input("explore-current-page", "data"),
        Input("explore-colormap-toggle", "value"),
        Input("explore-yaxis-toggle", "value"),
        Input("explore-yaxis-min-input", "value"),
        Input("explore-yaxis-max-input", "value"),
        Input("explore-colorbar-min-input", "value"),
        Input("explore-colorbar-max-input", "value"),
        Input("config-store", "data"),
        Input("mode-tabs", "data"),
        Input("specgen-overlay-request-store", "data"),
        Input("specgen-overlay-poll", "n_intervals"),
    )
    def compute_explore_status(
        data,
        current_page,
        use_hydrophone_colormap,
        use_log_y_axis,
        y_axis_min_hz,
        y_axis_max_hz,
        color_min,
        color_max,
        cfg,
        mode_tabs,
        specgen_request,
        poll_tick,
    ):
        cfg = cfg or {}
        _ = poll_tick
        triggered_id = ctx.triggered_id
        request_mode = (specgen_request or {}).get("mode") if isinstance(specgen_request, dict) else None
        request_page = (specgen_request or {}).get("page") if isinstance(specgen_request, dict) else None
        active_mode = str(mode_tabs or "label")
        source = str(((cfg.get("spectrogram_render", {}) or {}).get("source", "existing")))
        if triggered_id == "specgen-overlay-request-store" and request_mode and request_mode != "explore":
            raise PreventUpdate
        if triggered_id == "specgen-overlay-poll" and (active_mode != "explore" or source != "audio_generated"):
            raise PreventUpdate
        data = data or {"items": []}
        items = data.get("items", []) or []
        display_cfg = cfg.get("display", {})
        colormap = "hydrophone" if use_hydrophone_colormap else display_cfg.get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
        items_per_page = display_cfg.get("items_per_page", 25)
        effective_page = _coerce_page_index(current_page)
        if request_mode == "explore" and request_page is not None and triggered_id in {"specgen-overlay-request-store", "specgen-overlay-poll"}:
            effective_page = _coerce_page_index(request_page)
        page_items, page_index, total_pages = _slice_page(items, effective_page, items_per_page)
        status = _estimate_page_audio_generation_work(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )
        status.update(
            {
                "mode": "explore",
                "page_index": int(page_index),
                "total_pages": int(total_pages),
                "items_per_page": int(items_per_page),
                "computed_at": time.time(),
            }
        )
        _debug_status("explore", status)
        return status
