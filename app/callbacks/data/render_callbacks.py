"""Render callbacks for label/verify/explore grids and summaries."""

import os
import time

from dash import Input, Output, State, html, no_update

from app.defaults import DEFAULT_CACHE_MAX_SIZE
from app.services.verify_modal_cache import register_verify_modal_items

_SPECGEN_DEBUG = os.getenv("HYDRO_SPECGEN_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


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
    _schedule_specgen_prefetch_for_current_page_images,
    _schedule_specgen_prefetch_for_future_pages,
    _schedule_modal_prefetch_for_current_page_spectrograms,
    _schedule_modal_prefetch_for_future_pages,
):
    def _compute_prefetch_pages_ahead(cfg, items_per_page):
        cfg = cfg or {}
        cache_cfg = cfg.get("cache", {}) or {}
        try:
            cache_max = int(cache_cfg.get("max_size", DEFAULT_CACHE_MAX_SIZE))
        except (TypeError, ValueError):
            cache_max = DEFAULT_CACHE_MAX_SIZE
        cache_max = max(1, cache_max)
        per_page = max(1, int(items_per_page or 1))
        pages_by_capacity = (cache_max // per_page) - 1
        if pages_by_capacity <= 0:
            return 0

        # Advanced configs may still provide an explicit prefetch window, but the
        # default behavior should scale directly with the cache size setting.
        explicit_pages = cache_cfg.get("prefetch_pages")
        if explicit_pages is not None:
            try:
                desired_pages = max(0, int(explicit_pages))
            except (TypeError, ValueError):
                desired_pages = pages_by_capacity
            return min(desired_pages, pages_by_capacity)

        return pages_by_capacity

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

        cfg = cfg or {}
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
        current_page_submitted = _schedule_specgen_prefetch_for_current_page_images(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        current_page_modal_submitted = _schedule_modal_prefetch_for_current_page_spectrograms(
            page_items,
            cfg,
        )
        if _SPECGEN_DEBUG and current_page_submitted:
            print(
                f"[specgen-prefetch] mode=label current_page={current_page} "
                f"current_submitted={current_page_submitted}",
                flush=True,
            )
        if _SPECGEN_DEBUG and current_page_modal_submitted:
            print(
                f"[modal-prefetch] mode=label current_page={current_page} "
                f"current_submitted={current_page_modal_submitted}",
                flush=True,
            )
        prefetch_pages = _compute_prefetch_pages_ahead(cfg, items_per_page)
        if prefetch_pages > 0:
            submitted = _schedule_specgen_prefetch_for_future_pages(
                items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                pages_ahead=prefetch_pages,
            )
            if _SPECGEN_DEBUG and submitted:
                print(
                    f"[specgen-prefetch] mode=label from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={submitted}",
                    flush=True,
                )
            modal_submitted = _schedule_modal_prefetch_for_future_pages(
                items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                pages_ahead=prefetch_pages,
            )
            if _SPECGEN_DEBUG and modal_submitted:
                print(
                    f"[modal-prefetch] mode=label from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={modal_submitted}",
                    flush=True,
                )
        
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

        ui_ready = {
            "load_timestamp": data.get("load_timestamp"),
            "page": int(current_page),
            "rendered_at": time.time(),
        }
        if _SPECGEN_DEBUG:
            print(
                f"[render-ready] mode=label page={current_page} total_pages={total_pages} "
                f"items={len(page_items)} rendered_at={ui_ready['rendered_at']:.6f}",
                flush=True,
            )

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
        Output("verify-visible-item-ids-store", "data"),
        Output("verify-data-cache-key-store", "data"),
        Input("verify-data-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-current-page", "data"),
        Input("verify-colormap-toggle", "value"),
        Input("verify-yaxis-toggle", "value"),
        Input("config-store", "data"),
        State("mode-tabs", "data"),
    )
    def render_verify(
        data,
        thresholds,
        class_filter,
        current_page,
        use_hydrophone_colormap,
        use_log_y_axis,
        cfg,
        mode,
    ):
        # Render even if not in verify mode (to maintain state when switching back)
        pass

        cfg = cfg or {}
        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])
        verify_cache_key = register_verify_modal_items(data)
        thresholds = thresholds or {"__global__": 0.5}
        leaf_class_values = _extract_verify_leaf_classes(items)
        available_values = _build_verify_filter_paths(leaf_class_values)
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
        elif leaf_class_values and len(selected_filters) == len(leaf_class_values):
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
        visible_item_ids = [
            item.get("item_id")
            for item in filtered_items
            if isinstance(item, dict) and item.get("item_id")
        ]
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))

        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = filtered_items[start_idx:end_idx]

        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "verify", colormap, y_axis_scale, items_per_page, cfg)
        current_page_submitted = _schedule_specgen_prefetch_for_current_page_images(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        current_page_modal_submitted = _schedule_modal_prefetch_for_current_page_spectrograms(
            page_items,
            cfg,
        )
        if _SPECGEN_DEBUG and current_page_submitted:
            print(
                f"[specgen-prefetch] mode=verify current_page={current_page} "
                f"current_submitted={current_page_submitted}",
                flush=True,
            )
        if _SPECGEN_DEBUG and current_page_modal_submitted:
            print(
                f"[modal-prefetch] mode=verify current_page={current_page} "
                f"current_submitted={current_page_modal_submitted}",
                flush=True,
            )
        prefetch_pages = _compute_prefetch_pages_ahead(cfg, items_per_page)
        if prefetch_pages > 0:
            submitted = _schedule_specgen_prefetch_for_future_pages(
                filtered_items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                pages_ahead=prefetch_pages,
            )
            if _SPECGEN_DEBUG and submitted:
                print(
                    f"[specgen-prefetch] mode=verify from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={submitted}",
                    flush=True,
                )
            modal_submitted = _schedule_modal_prefetch_for_future_pages(
                filtered_items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                pages_ahead=prefetch_pages,
            )
            if _SPECGEN_DEBUG and modal_submitted:
                print(
                    f"[modal-prefetch] mode=verify from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={modal_submitted}",
                    flush=True,
                )
        
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

        ui_ready = {
            "load_timestamp": data.get("load_timestamp"),
            "page": int(current_page),
            "rendered_at": time.time(),
        }
        if _SPECGEN_DEBUG:
            print(
                f"[render-ready] mode=verify page={current_page} total_pages={total_pages} "
                f"items={len(page_items)} rendered_at={ui_ready['rendered_at']:.6f}",
                flush=True,
            )

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
            visible_item_ids,
            verify_cache_key,
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
        cfg = cfg or {}
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
        current_page_submitted = _schedule_specgen_prefetch_for_current_page_images(
            page_items,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        current_page_modal_submitted = _schedule_modal_prefetch_for_current_page_spectrograms(
            page_items,
            cfg,
        )
        if _SPECGEN_DEBUG and current_page_submitted:
            print(
                f"[specgen-prefetch] mode=explore current_page={current_page} "
                f"current_submitted={current_page_submitted}",
                flush=True,
            )
        if _SPECGEN_DEBUG and current_page_modal_submitted:
            print(
                f"[modal-prefetch] mode=explore current_page={current_page} "
                f"current_submitted={current_page_modal_submitted}",
                flush=True,
            )
        prefetch_pages = _compute_prefetch_pages_ahead(cfg, items_per_page)
        if prefetch_pages > 0:
            submitted = _schedule_specgen_prefetch_for_future_pages(
                items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                pages_ahead=prefetch_pages,
            )
            if _SPECGEN_DEBUG and submitted:
                print(
                    f"[specgen-prefetch] mode=explore from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={submitted}",
                    flush=True,
                )
            modal_submitted = _schedule_modal_prefetch_for_future_pages(
                items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                pages_ahead=prefetch_pages,
            )
            if _SPECGEN_DEBUG and modal_submitted:
                print(
                    f"[modal-prefetch] mode=explore from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={modal_submitted}",
                    flush=True,
                )
        ui_ready = {
            "load_timestamp": data.get("load_timestamp"),
            "page": int(current_page),
            "rendered_at": time.time(),
        }
        if _SPECGEN_DEBUG:
            print(
                f"[render-ready] mode=explore page={current_page} total_pages={total_pages} "
                f"items={len(page_items)} rendered_at={ui_ready['rendered_at']:.6f}",
                flush=True,
            )
        return summary_block, grid, page_info, total_pages, ui_ready
