"""Render callbacks for label/verify/explore grids and summaries."""

from dash import Input, Output, State, html, no_update


def register_render_callbacks(
    app,
    *,
    _build_grid,
    _create_folder_display,
    _filter_predictions,
    _predicted_labels_match_filter,
    _extract_verify_leaf_classes,
    _build_verify_filter_paths,
    _normalize_verify_class_filter,
):
    @app.callback(
        Output("label-summary", "children"),
        Output("label-grid", "children"),
        Output("label-page-info", "children"),
        Output("label-page-input", "max"),
        Output("label-spec-folder-display", "children", allow_duplicate=True),
        Output("label-audio-folder-display", "children", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Output("label-ui-ready-store", "data"),
        Input("label-data-store", "data"),
        Input("label-colormap-toggle", "value"),
        Input("label-yaxis-toggle", "value"),
        Input("label-current-page", "data"),
        Input("config-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def render_label(data, use_hydrophone_colormap, use_log_y_axis, current_page, cfg, mode):
        # Render even if not in label mode (to maintain state when switching back)
        pass

        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        
        # Calculate pagination
        total_items = len(items)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))
        
        # Slice items for current page
        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = items[start_idx:end_idx]

        summary_block = html.Div([
            html.Span(f"Items: {summary.get('total_items', len(items))}", className="fw-semibold"),
            html.Span(f"Annotated: {summary.get('annotated', 0)}", className="ms-3 text-muted"),
        ])
        
        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "label", colormap, y_axis_scale, items_per_page, cfg)
        
        # Update folder displays with popover support for multiple folders
        data_root = summary.get("data_root", "")
        folder_display = _create_folder_display(
            summary.get("spectrogram_folder") or "Not set",
            summary.get("spectrogram_folders_list", []),
            data_root, "label-spec-popover"
        )
        audio_folder_display = _create_folder_display(
            summary.get("audio_folder") or "Not set",
            summary.get("audio_folders_list", []),
            data_root, "label-audio-popover"
        )
        labels_file_display = summary.get("labels_file") or no_update

        ui_ready = no_update
        if (data or {}).get("load_timestamp"):
            ui_ready = {"timestamp": data.get("load_timestamp")}

        return (
            summary_block,
            grid,
            page_info,
            total_pages,
            folder_display,
            audio_folder_display,
            labels_file_display,
            ui_ready,
        )

    @app.callback(
        Output("verify-summary", "children"),
        Output("verify-grid", "children"),
        Output("verify-page-info", "children"),
        Output("verify-page-input", "max"),
        Output("verify-spec-folder-display", "children"),
        Output("verify-audio-folder-display", "children"),
        Output("verify-predictions-display", "children"),
        Output("verify-data-root-display", "children"),
        Output("verify-ui-ready-store", "data"),
        Input("verify-data-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-current-page", "data"),
        Input("verify-colormap-toggle", "value"),
        Input("verify-yaxis-toggle", "value"),
        Input("config-store", "data"),
        State("mode-tabs", "data"),
    )
    def render_verify(data, thresholds, class_filter, current_page, use_hydrophone_colormap, use_log_y_axis, cfg, mode):
        # Render even if not in verify mode (to maintain state when switching back)
        pass

        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])
        thresholds = thresholds or {"__global__": 0.5}
        available_values = _build_verify_filter_paths(_extract_verify_leaf_classes(items))
        available_value_set = set(available_values)
        selected_filters = _normalize_verify_class_filter(class_filter)
        if not available_values:
            selected_filters = None
        if selected_filters is not None:
            selected_filters = [value for value in selected_filters if value in available_value_set]
        current_threshold = float(thresholds.get("__global__", 0.5))

        # Get folder display info from summary
        spec_folder = summary.get("spectrogram_folder") or "Not set"
        audio_folder = summary.get("audio_folder") or "Not set"
        predictions_file = summary.get("predictions_file") or "Not set"

        filtered_items = []
        for item in items:
            if not item:
                continue
            annotations = (item.get("annotations") or {})
            is_verified = bool(annotations.get("verified"))
            predictions = item.get("predictions") or {}
            predicted_labels = _filter_predictions(predictions, thresholds)

            if not is_verified and not predicted_labels:
                continue

            if not _predicted_labels_match_filter(predicted_labels, selected_filters):
                continue

            display_item = dict(item)
            display_predictions = dict(predictions)
            display_predictions["labels"] = predicted_labels
            display_item["predictions"] = display_predictions
            filtered_items.append(display_item)

        if selected_filters is None:
            filter_text = "All selected"
        elif not selected_filters:
            filter_text = "None selected"
        elif available_values and len(selected_filters) == len(available_values):
            filter_text = "All selected"
        else:
            filter_text = f"{len(selected_filters)} selected"

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Visible: {len(filtered_items)}", className="fw-semibold"),
            html.Span(f"Total: {summary.get('total_items', len(items))}", className="ms-3 text-muted"),
            html.Span(f"Verified: {summary.get('verified', 0)}", className="ms-3 text-muted"),
            html.Span(f"Threshold: {current_threshold*100:.0f}%", className="ms-3 text-muted"),
            html.Span(f"Filter: {filter_text}", className="ms-3 text-muted"),
        ], className="summary-info")

        total_items = len(filtered_items)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))

        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = filtered_items[start_idx:end_idx]

        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "verify", colormap, y_axis_scale, items_per_page, cfg)
        
        data_root = summary.get("data_root") or "Not set"

        spec_folder_display = _create_folder_display(
            summary.get("spectrogram_folder") or "Not set",
            summary.get("spectrogram_folders_list", []),
            summary.get("data_root", ""), "spec-folder-popover-trigger"
        )
        audio_folder_display = _create_folder_display(
            summary.get("audio_folder") or "Not set",
            summary.get("audio_folders_list", []),
            summary.get("data_root", ""), "audio-folder-popover-trigger"
        )
        pred_file_display = _create_folder_display(
            summary.get("predictions_file") or "Not set",
            summary.get("predictions_files_list", []),
            summary.get("data_root", ""), "pred-file-popover-trigger"
        )

        ui_ready = no_update
        if (data or {}).get("load_timestamp"):
            ui_ready = {"timestamp": data.get("load_timestamp")}

        return (
            summary_block,
            grid,
            page_info,
            total_pages,
            spec_folder_display,
            audio_folder_display,
            pred_file_display,
            data_root,
            ui_ready,
        )
    @app.callback(
        Output("explore-summary", "children"),
        Output("explore-grid", "children"),
        Output("explore-page-info", "children"),
        Output("explore-page-input", "max"),
        Output("explore-ui-ready-store", "data"),
        Input("explore-data-store", "data"),
        Input("explore-current-page", "data"),
        Input("explore-colormap-toggle", "value"),
        Input("explore-yaxis-toggle", "value"),
        Input("config-store", "data"),
    )
    def render_explore(data, current_page, use_hydrophone_colormap, use_log_y_axis, cfg):
        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Items: {summary.get('total_items', len(items))}", className="fw-semibold"),
        ])

        total_items = len(items)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))
        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = items[start_idx:end_idx]
        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "explore", colormap, y_axis_scale, items_per_page, cfg)
        ui_ready = no_update
        if (data or {}).get("load_timestamp"):
            ui_ready = {"timestamp": data.get("load_timestamp")}
        return summary_block, grid, page_info, total_pages, ui_ready
