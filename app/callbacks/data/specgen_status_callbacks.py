"""Track per-page spectrogram-generation workload for UI loading overlays."""

from dash import Input, Output


def _slice_page(items, current_page, items_per_page):
    total_items = len(items)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    page_index = max(0, min(current_page or 0, total_pages - 1))
    start_idx = page_index * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx], page_index, total_pages


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
        Output("label-page-specgen-store", "data"),
        Input("label-data-store", "data"),
        Input("label-colormap-toggle", "value"),
        Input("label-yaxis-toggle", "value"),
        Input("label-current-page", "data"),
        Input("config-store", "data"),
    )
    def compute_label_status(data, use_hydrophone_colormap, use_log_y_axis, current_page, cfg):
        cfg = cfg or {}
        data = data or {"items": []}
        items = data.get("items", []) or []
        display_cfg = cfg.get("display", {})
        colormap = "hydrophone" if use_hydrophone_colormap else display_cfg.get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
        items_per_page = display_cfg.get("items_per_page", 25)
        page_items, page_index, total_pages = _slice_page(items, current_page, items_per_page)
        status = _estimate_page_audio_generation_work(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        status.update(
            {
                "mode": "label",
                "page_index": int(page_index),
                "total_pages": int(total_pages),
                "items_per_page": int(items_per_page),
            }
        )
        return status

    @app.callback(
        Output("verify-page-specgen-store", "data"),
        Input("verify-data-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-current-page", "data"),
        Input("verify-colormap-toggle", "value"),
        Input("verify-yaxis-toggle", "value"),
        Input("config-store", "data"),
    )
    def compute_verify_status(
        data,
        thresholds,
        class_filter,
        current_page,
        use_hydrophone_colormap,
        use_log_y_axis,
        cfg,
    ):
        cfg = cfg or {}
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
        page_items, page_index, total_pages = _slice_page(filtered_items, current_page, items_per_page)

        status = _estimate_page_audio_generation_work(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        status.update(
            {
                "mode": "verify",
                "page_index": int(page_index),
                "total_pages": int(total_pages),
                "items_per_page": int(items_per_page),
            }
        )
        return status

    @app.callback(
        Output("explore-page-specgen-store", "data"),
        Input("explore-data-store", "data"),
        Input("explore-current-page", "data"),
        Input("explore-colormap-toggle", "value"),
        Input("explore-yaxis-toggle", "value"),
        Input("config-store", "data"),
    )
    def compute_explore_status(data, current_page, use_hydrophone_colormap, use_log_y_axis, cfg):
        cfg = cfg or {}
        data = data or {"items": []}
        items = data.get("items", []) or []
        display_cfg = cfg.get("display", {})
        colormap = "hydrophone" if use_hydrophone_colormap else display_cfg.get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else display_cfg.get("y_axis_scale", "linear")
        items_per_page = display_cfg.get("items_per_page", 25)
        page_items, page_index, total_pages = _slice_page(items, current_page, items_per_page)
        status = _estimate_page_audio_generation_work(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        status.update(
            {
                "mode": "explore",
                "page_index": int(page_index),
                "total_pages": int(total_pages),
                "items_per_page": int(items_per_page),
            }
        )
        return status
