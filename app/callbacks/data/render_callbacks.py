"""Render callbacks for label/verify/explore grids and summaries."""

import os
import time

from dash import Input, Output, State, ctx, html, no_update, set_props
from dash.exceptions import PreventUpdate

from app.defaults import DEFAULT_CACHE_MAX_SIZE
from app.services.grid_updates import grid_render_state, incremental_grid
from app.services.spectrogram_grid import (
    normalize_spectrogram_grid,
    spectrogram_grid_class,
)
from app.services.spectrogram_ranges import uses_visible_ranges
from app.services.verify_modal_cache import (
    ensure_verify_modal_items,
    get_filtered_verify_items_page,
    get_verify_filter_leaf_classes,
    get_verify_modal_summary,
    has_verify_modal_items,
)
from app.utils.image_processing import (
    SPECTROGRAM_SOURCE_AUDIO_GENERATED,
    get_spectrogram_render_settings,
    is_modal_prefetch_enabled,
)

_SPECGEN_DEBUG = os.getenv("HYDRO_SPECGEN_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _page_frequency_window(prefix, cfg, y_axis_min_hz, y_axis_max_hz, triggered_prop_ids):
    """The page's frequency window, when it applies to the grid.

    With visible ranges each card is drawn in its range's band, so the window
    is ignored, and a change to nothing but the window does not redraw the grid.
    """
    if not uses_visible_ranges(cfg):
        return y_axis_min_hz, y_axis_max_hz
    window_props = {f"{prefix}-yaxis-min-input.value", f"{prefix}-yaxis-max-input.value"}
    triggered = set(triggered_prop_ids or ())
    if triggered and triggered <= window_props:
        raise PreventUpdate
    return None, None


def _empty_all_dates_preview_ready_payload(summary, cache_key):
    """Signal that an empty preview rendered so its full index may start loading."""
    summary = summary if isinstance(summary, dict) else {}
    return {
        "load_timestamp": cache_key,
        "active_date": summary.get("active_date"),
        "active_hydrophone": summary.get("active_hydrophone"),
        "page": 0,
        "rendered_at": time.time(),
        "item_count": 0,
        "item_ids": [],
        "all_dates_request_id": summary.get("all_dates_request_id"),
    }


def _verify_page_info(current_page, items_per_page, filtered_total, *, index_available=True):
    if not index_available:
        return "Indexing..."
    if filtered_total <= 0:
        return "Page 0 of 0"
    total_pages = max(1, (filtered_total + items_per_page - 1) // items_per_page)
    return f"Page {current_page + 1} of {total_pages}"


def _prefetch_enabled(cfg):
    cache_cfg = (cfg or {}).get("cache", {}) or {}
    configured = cache_cfg.get("prefetch_enabled", cache_cfg.get("prefetch"))
    if configured is not None:
        return str(configured).strip().lower() not in {"0", "false", "no", "off"}

    # Existing MAT-backed images are requested lazily by the browser. Prefetching
    # them can leave stale modal/future-page renders ahead of a newly filtered
    # first page because matplotlib rendering is serialized.
    return (
        get_spectrogram_render_settings(cfg).get("source")
        == SPECTROGRAM_SOURCE_AUDIO_GENERATED
    )


def _modal_prefetch_enabled(cfg):
    return is_modal_prefetch_enabled(cfg)


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

    explicit_pages = cache_cfg.get("prefetch_pages")
    if explicit_pages is not None:
        try:
            desired_pages = max(0, int(explicit_pages))
        except (TypeError, ValueError):
            desired_pages = pages_by_capacity
        return min(desired_pages, pages_by_capacity)

    if get_spectrogram_render_settings(cfg).get("source") == SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        return min(1, pages_by_capacity)
    return pages_by_capacity


def _collect_verify_future_page_items(
    cache_key,
    thresholds,
    selected_filters,
    status_filter,
    *,
    current_page,
    total_pages,
    items_per_page,
    pages_ahead,
):
    future_items = []
    last_page = min(int(total_pages) - 1, int(current_page) + int(pages_ahead))
    for page_index in range(int(current_page) + 1, last_page + 1):
        filtered_page = get_filtered_verify_items_page(
            cache_key,
            thresholds,
            selected_filters,
            page_index,
            items_per_page,
            status_filter,
        )
        if filtered_page.get("page_index") != page_index:
            break
        future_items.extend(filtered_page.get("items") or [])
    return future_items


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
    def _loading_path(text):
        return html.Span(text, className="loading-path-text")

    def _path_value(value, loading_text, is_loading):
        if value:
            return value
        if is_loading:
            return _loading_path(loading_text)
        return "Not set"

    def _spectrogram_grid_placeholder(cfg=None, text="Preparing spectrogram cards..."):
        layout = normalize_spectrogram_grid(cfg)
        return html.Div(
            [
                html.Div(
                    [
                        html.Div(className="spec-card-skeleton-title"),
                        html.Div(text, className="spec-card-skeleton-image"),
                        html.Div(className="spec-card-skeleton-line"),
                        html.Div(className="spec-card-skeleton-line spec-card-skeleton-line--short"),
                    ],
                    className="spec-card-skeleton",
                )
                for _ in range(layout["items_per_page"])
            ],
            className=f"spec-grid-placeholder {spectrogram_grid_class(layout['columns'])}",
            style={"--spectrogram-grid-columns": str(layout["columns"])},
        )

    def _ui_ready_payload(data, page_items, current_page, extra=None):
        item_ids = [
            item.get("item_id") or os.path.basename(item.get("spectrogram_path", ""))
            for item in (page_items or [])
        ]
        summary = data.get("summary") if isinstance(data, dict) and isinstance(data.get("summary"), dict) else {}
        payload = {
            "load_timestamp": data.get("load_timestamp") if isinstance(data, dict) else None,
            "active_date": summary.get("active_date"),
            "active_hydrophone": summary.get("active_hydrophone"),
            "page": int(current_page),
            "rendered_at": time.time(),
            "item_count": len(item_ids),
            "item_ids": item_ids,
        }
        if isinstance(extra, dict):
            payload.update(extra)
        return payload

    def _verify_filter_state(thresholds, selected_filters, status_filter):
        try:
            threshold = float((thresholds or {}).get("__global__", 0.5))
        except (TypeError, ValueError):
            threshold = 0.5
        return {
            "threshold": threshold,
            "class_filter": sorted(str(value) for value in selected_filters)
            if selected_filters is not None
            else None,
            "status_filter": str(status_filter or "all"),
        }

    def _verify_status_filter_text(status_filter):
        labels = {
            "all": "All statuses",
            "unverified": "Unverified only",
            "accepted_only": "Accepted only",
            "rejected_only": "Rejected only",
            "mixed": "Mixed",
            "contains_accepted": "Contains accepted",
            "contains_rejected": "Contains rejected",
            "verified": "Verified only",
        }
        return labels.get(str(status_filter or "all"), "All statuses")

    @app.callback(
        Output("verify-data-cache-key-store", "data"),
        Output("verify-data-cache-revision-store", "data"),
        Input("verify-data-store", "data"),
        State("verify-data-cache-revision-store", "data"),
        prevent_initial_call=False,
    )
    def sync_verify_data_cache(data, current_revision):
        if not isinstance(data, dict) or not data.get("load_timestamp"):
            return None, current_revision or 0
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        indexed_cache_key = summary.get("verify_modal_cache_key")
        cache_key = (
            indexed_cache_key
            if indexed_cache_key and has_verify_modal_items(indexed_cache_key)
            else ensure_verify_modal_items(data)
        )
        try:
            revision = int(current_revision or 0) + 1
        except (TypeError, ValueError):
            revision = 1
        return cache_key, revision

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
        Input("label-yaxis-min-input", "value"),
        Input("label-yaxis-max-input", "value"),
        Input("label-colorbar-min-input", "value"),
        Input("label-colorbar-max-input", "value"),
        Input("label-current-page", "data"),
        Input("config-store", "data"),
        Input("spectrogram-ranges-store", "data"),
        State("mode-tabs", "data"),
        State("label-ui-ready-store", "data"),
        prevent_initial_call=True,
    )
    def render_label(
        data,
        use_hydrophone_colormap,
        use_log_y_axis,
        y_axis_min_hz,
        y_axis_max_hz,
        color_min,
        color_max,
        current_page,
        cfg,
        spectrogram_ranges,
        mode,
        previous_ui_ready,
    ):
        # Render even if not in label mode (to maintain state when switching back)
        pass

        cfg = cfg or {}
        y_axis_min_hz, y_axis_max_hz = _page_frequency_window(
            "label", cfg, y_axis_min_hz, y_axis_max_hz, ctx.triggered_prop_ids
        )
        is_loading_dataset = not isinstance(data, dict) or not data.get("load_timestamp")
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

        render_state = grid_render_state(page_items, {
            "load_timestamp": data.get("load_timestamp"), "page": current_page,
            "colormap": colormap, "y_axis_scale": y_axis_scale,
            "y_min": y_axis_min_hz, "y_max": y_axis_max_hz,
            "color_min": color_min, "color_max": color_max, "config": cfg,
            "spectrogram_ranges": spectrogram_ranges,
        })

        def build_page_grid(items):
            return _build_grid(
                items, "label", colormap, y_axis_scale, y_axis_min_hz,
                y_axis_max_hz, color_min, color_max, items_per_page, cfg, spectrogram_ranges,
            )

        grid = incremental_grid(
            (previous_ui_ready or {}).get("grid_render_state"), render_state,
            lambda: build_page_grid(page_items),
            lambda index: build_page_grid([page_items[index]]).children[0],
            update_card=lambda column: set_props(column.id, {"children": column.children}),
        )
        prefetch_enabled = _prefetch_enabled(cfg)
        modal_prefetch_enabled = _modal_prefetch_enabled(cfg)
        current_page_submitted = 0
        current_page_modal_submitted = 0
        if prefetch_enabled:
            current_page_submitted = _schedule_specgen_prefetch_for_current_page_images(
                page_items,
                cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
                color_min=color_min,
                color_max=color_max,
            )
        if modal_prefetch_enabled:
            current_page_modal_submitted = _schedule_modal_prefetch_for_current_page_spectrograms(
                page_items,
                cfg,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
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
        prefetch_pages = _compute_prefetch_pages_ahead(cfg, items_per_page) if prefetch_enabled else 0
        if prefetch_pages > 0:
            submitted = _schedule_specgen_prefetch_for_future_pages(
                items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
                color_min=color_min,
                color_max=color_max,
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
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
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

        ui_ready = _ui_ready_payload(data, page_items, current_page, {"grid_render_state": render_state})
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
        Input("verify-data-cache-key-store", "data"),
        Input("verify-data-cache-revision-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-status-filter", "value"),
        Input("verify-current-page", "data"),
        Input("verify-colormap-toggle", "value"),
        Input("verify-yaxis-toggle", "value"),
        Input("verify-yaxis-min-input", "value"),
        Input("verify-yaxis-max-input", "value"),
        Input("verify-colorbar-min-input", "value"),
        Input("verify-colorbar-max-input", "value"),
        Input("config-store", "data"),
        Input("spectrogram-ranges-store", "data"),
        State("mode-tabs", "data"),
    )
    def render_verify(
        verify_cache_key,
        verify_cache_revision,
        thresholds,
        class_filter,
        status_filter,
        current_page,
        use_hydrophone_colormap,
        use_log_y_axis,
        y_axis_min_hz,
        y_axis_max_hz,
        color_min,
        color_max,
        cfg,
        spectrogram_ranges,
        mode,
    ):
        # Render even if not in verify mode (to maintain state when switching back)
        pass

        cfg = cfg or {}
        y_axis_min_hz, y_axis_max_hz = _page_frequency_window(
            "verify", cfg, y_axis_min_hz, y_axis_max_hz, ctx.triggered_prop_ids
        )
        _ = verify_cache_revision
        summary = get_verify_modal_summary(verify_cache_key) or {}
        is_loading_dataset = not verify_cache_key or not has_verify_modal_items(verify_cache_key)
        is_empty_all_dates_preview = bool(
            summary.get("all_dates_loading")
            and summary.get("all_dates_preview")
            and int(summary.get("total_items") or 0) <= 0
        )
        cfg_data = cfg.get("data", {}) if isinstance(cfg.get("data"), dict) else {}
        if is_loading_dataset or is_empty_all_dates_preview:
            data_root = summary.get("data_root") or cfg_data.get("data_dir") or "Loading data root..."
            nested_verify_cfg = cfg_data.get("verify", {}) if isinstance(cfg_data.get("verify"), dict) else {}
            spec_folder_display = _path_value(
                summary.get("spectrogram_folder") or cfg_data.get("spectrogram_folder"),
                "Loading spectrogram folder...",
                True,
            )
            audio_folder_display = _path_value(
                summary.get("audio_folder") or cfg_data.get("audio_folder"),
                "Loading audio folder...",
                True,
            )
            pred_file_display = _path_value(
                summary.get("predictions_file")
                or cfg_data.get("predictions_file")
                or nested_verify_cfg.get("predictions_json"),
                "Loading predictions file...",
                True,
            )
            loading_ui_ready = (
                _empty_all_dates_preview_ready_payload(summary, verify_cache_key)
                if is_empty_all_dates_preview
                else no_update
            )
            return (
                html.Div(
                    [
                        html.Span("Loading...", className="command-match-count"),
                        html.Div(
                            "Preparing predictions and spectrogram cards",
                            className="command-filter-context",
                        ),
                    ],
                    className="summary-info",
                ),
                _spectrogram_grid_placeholder(cfg),
                "Preparing page...",
                1,
                spec_folder_display,
                audio_folder_display,
                pred_file_display,
                data_root,
                loading_ui_ready,
                [],
            )
        thresholds = thresholds or {"__global__": 0.5}
        leaf_class_values = get_verify_filter_leaf_classes(verify_cache_key)
        available_values = _build_verify_filter_paths(leaf_class_values)
        available_value_set = set(available_values)
        selected_filters = _normalize_verify_class_filter(class_filter)
        if not available_values:
            selected_filters = None
        if selected_filters is not None:
            selected_filters = [value for value in selected_filters if value in available_value_set]
        current_threshold = float(thresholds.get("__global__", 0.5))

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
        filtered_page = get_filtered_verify_items_page(
            verify_cache_key,
            thresholds,
            selected_filters,
            current_page,
            items_per_page,
            status_filter,
        )
        filtered_total = filtered_page["total_items"]
        total_pages = filtered_page["total_pages"]
        if (current_page or 0) != filtered_page["page_index"]:
            set_props("verify-current-page", {"data": filtered_page["page_index"]})
        current_page = filtered_page["page_index"]
        page_items = filtered_page["items"]
        visible_item_ids = filtered_page["visible_item_ids"]
        remaining_count = filtered_page["remaining_items"]
        remaining_noun = "clip" if remaining_count == 1 else "clips"
        matching_noun = "clip" if filtered_total == 1 else "clips"
        is_partial_selection = bool(summary.get("all_dates_loading"))
        index_available = not bool(
            summary.get("active_date") == "All"
            and is_partial_selection
            and not summary.get("all_dates_index_available")
        )
        if index_available:
            match_summary = html.Span(
                f"{remaining_count:,} {remaining_noun} left to verify",
                className="command-match-count",
            )
            context_children = [
                html.Span(f"{filtered_total:,} {matching_noun} matching current filters", className="command-filter-detail"),
                html.Span(
                    f"{int(summary.get('total_items', filtered_total)):,} recordings",
                    className="command-filter-detail",
                ),
                html.Span(
                    f"{int(summary.get('verified', 0)):,} verified",
                    className="command-filter-detail",
                ),
            ]
        else:
            match_summary = html.Span(
                "Counting...",
                className="command-match-count",
            )
            context_children = [
                html.Span(
                    "Counting recordings",
                    className="command-filter-detail",
                ),
            ]
        context_children.extend(
            [
                html.Span(
                    f"Threshold {current_threshold*100:.0f}%",
                    className="command-filter-detail",
                ),
                html.Span(
                    [
                        html.Span("Class", className="command-filter-label"),
                        html.Span(filter_text, className="command-filter-value"),
                    ],
                    className="command-filter-detail",
                ),
                html.Span(
                    [
                        html.Span("Status", className="command-filter-label"),
                        html.Span(
                            _verify_status_filter_text(status_filter),
                            className="command-filter-value",
                        ),
                    ],
                    className="command-filter-detail",
                ),
            ]
        )
        if is_partial_selection:
            context_children.append(
                html.Span(
                    "Updating...",
                    className="command-filter-detail command-filter-updating",
                )
            )
        summary_block = html.Div(
            [
                match_summary,
                html.Div(context_children, className="command-filter-context"),
            ],
            className="summary-info",
        )

        page_info = _verify_page_info(
            current_page,
            int(items_per_page or 25),
            filtered_total,
            index_available=index_available,
        )

        grid = _build_grid(
            page_items,
            "verify",
            colormap,
            y_axis_scale,
            y_axis_min_hz,
            y_axis_max_hz,
            color_min,
            color_max,
            items_per_page,
            cfg,
            spectrogram_ranges,
            empty_message="No items match the current filters.",
        )
        prefetch_enabled = _prefetch_enabled(cfg)
        modal_prefetch_enabled = _modal_prefetch_enabled(cfg)
        current_page_submitted = 0
        current_page_modal_submitted = 0
        if prefetch_enabled:
            current_page_submitted = _schedule_specgen_prefetch_for_current_page_images(
                page_items,
                cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
                color_min=color_min,
                color_max=color_max,
            )
        if modal_prefetch_enabled:
            current_page_modal_submitted = _schedule_modal_prefetch_for_current_page_spectrograms(
                page_items,
                cfg,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
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
        prefetch_pages = _compute_prefetch_pages_ahead(cfg, items_per_page) if prefetch_enabled else 0
        if prefetch_pages > 0:
            future_page_items = _collect_verify_future_page_items(
                verify_cache_key,
                thresholds,
                selected_filters,
                status_filter,
                current_page=current_page,
                total_pages=total_pages,
                items_per_page=items_per_page,
                pages_ahead=prefetch_pages,
            )
            submitted = _schedule_specgen_prefetch_for_current_page_images(
                future_page_items,
                cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
                color_min=color_min,
                color_max=color_max,
            )
            if _SPECGEN_DEBUG and submitted:
                print(
                    f"[specgen-prefetch] mode=verify from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={submitted}",
                    flush=True,
                )
            modal_submitted = _schedule_modal_prefetch_for_current_page_spectrograms(
                future_page_items,
                cfg,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
            )
            if _SPECGEN_DEBUG and modal_submitted:
                print(
                    f"[modal-prefetch] mode=verify from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={modal_submitted}",
                    flush=True,
                )
        
        data_root = (
            summary.get("data_root")
            or cfg_data.get("data_dir")
            or ("Loading data root..." if is_loading_dataset else "Not set")
        )
        spec_folder_value = _path_value(
            summary.get("spectrogram_folder") or cfg_data.get("spectrogram_folder"),
            "Loading spectrogram folder...",
            is_loading_dataset,
        )
        audio_folder_value = _path_value(
            summary.get("audio_folder") or cfg_data.get("audio_folder"),
            "Loading audio folder...",
            is_loading_dataset,
        )
        nested_verify_cfg = cfg_data.get("verify", {}) if isinstance(cfg_data.get("verify"), dict) else {}
        predictions_file_value = _path_value(
            summary.get("predictions_file")
            or cfg_data.get("predictions_file")
            or nested_verify_cfg.get("predictions_json"),
            "Loading predictions file...",
            is_loading_dataset,
        )

        spec_folder_display = _create_folder_display(
            spec_folder_value,
            summary.get("spectrogram_folders_list", []),
            summary.get("data_root", ""), "spec-folder-popover-trigger"
        )
        audio_folder_display = _create_folder_display(
            audio_folder_value,
            summary.get("audio_folders_list", []),
            summary.get("data_root", ""), "audio-folder-popover-trigger"
        )
        pred_file_display = _create_folder_display(
            predictions_file_value,
            summary.get("predictions_files_list", []),
            summary.get("data_root", ""), "pred-file-popover-trigger"
        )

        ui_ready = _ui_ready_payload(
            {"load_timestamp": verify_cache_key, "summary": summary},
            page_items,
            current_page,
            {
                "verify_filter_state": _verify_filter_state(thresholds, selected_filters, status_filter),
                "all_dates_request_id": summary.get("all_dates_request_id"),
            },
        )
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
        Input("explore-yaxis-min-input", "value"),
        Input("explore-yaxis-max-input", "value"),
        Input("explore-colorbar-min-input", "value"),
        Input("explore-colorbar-max-input", "value"),
        Input("config-store", "data"),
        Input("spectrogram-ranges-store", "data"),
    )
    def render_explore(
        data,
        current_page,
        use_hydrophone_colormap,
        use_log_y_axis,
        y_axis_min_hz,
        y_axis_max_hz,
        color_min,
        color_max,
        cfg,
        spectrogram_ranges,
    ):
        cfg = cfg or {}
        y_axis_min_hz, y_axis_max_hz = _page_frequency_window(
            "explore", cfg, y_axis_min_hz, y_axis_max_hz, ctx.triggered_prop_ids
        )
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

        grid = _build_grid(
            page_items,
            "explore",
            colormap,
            y_axis_scale,
            y_axis_min_hz,
            y_axis_max_hz,
            color_min,
            color_max,
            items_per_page,
            cfg,
            spectrogram_ranges,
        )
        prefetch_enabled = _prefetch_enabled(cfg)
        modal_prefetch_enabled = _modal_prefetch_enabled(cfg)
        current_page_submitted = 0
        current_page_modal_submitted = 0
        if prefetch_enabled:
            current_page_submitted = _schedule_specgen_prefetch_for_current_page_images(
                page_items,
                cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
                color_min=color_min,
                color_max=color_max,
            )
        if modal_prefetch_enabled:
            current_page_modal_submitted = _schedule_modal_prefetch_for_current_page_spectrograms(
                page_items,
                cfg,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
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
        prefetch_pages = _compute_prefetch_pages_ahead(cfg, items_per_page) if prefetch_enabled else 0
        if prefetch_pages > 0:
            submitted = _schedule_specgen_prefetch_for_future_pages(
                items,
                current_page=current_page,
                items_per_page=items_per_page,
                cfg=cfg,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
                color_min=color_min,
                color_max=color_max,
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
                y_axis_min_hz=y_axis_min_hz,
                y_axis_max_hz=y_axis_max_hz,
                pages_ahead=prefetch_pages,
            )
            if _SPECGEN_DEBUG and modal_submitted:
                print(
                    f"[modal-prefetch] mode=explore from_page={current_page} "
                    f"pages_ahead={prefetch_pages} submitted={modal_submitted}",
                    flush=True,
                )
        ui_ready = _ui_ready_payload(data, page_items, current_page)
        if _SPECGEN_DEBUG:
            print(
                f"[render-ready] mode=explore page={current_page} total_pages={total_pages} "
                f"items={len(page_items)} rendered_at={ui_ready['rendered_at']:.6f}",
                flush=True,
            )
        return summary_block, grid, page_info, total_pages, ui_ready
