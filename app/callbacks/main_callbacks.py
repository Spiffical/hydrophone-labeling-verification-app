import os
import time
from datetime import datetime
from dash import Input, Output, State, callback, ctx, no_update, ALL, dcc
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html

from app.components.spectrogram_card import create_spectrogram_card
from app.components.hierarchical_selector import create_hierarchical_selector
from app.components.audio_player import create_audio_player, create_modal_audio_player
from app.utils.data_loading import load_dataset
from app.utils.image_utils import get_item_image_src
from app.utils.image_processing import load_spectrogram_cached, create_spectrogram_figure, set_cache_sizes
from app.utils.persistence import save_label_mode, save_verify_predictions


def _update_item_labels(data, item_id, labels, mode, user_name=None, is_reverification=False):
    if not data or not item_id:
        return data
    items = data.get("items", [])
    for item in items:
        if not item:
            continue
        if item.get("item_id") == item_id:
            annotations = item.get("annotations") or {
                "labels": [],
                "annotated_by": None,
                "annotated_at": None,
                "verified": False,
                "notes": "",
            }
            annotations["labels"] = labels
            annotations["annotated_at"] = datetime.now().isoformat()
            
            if mode == "verify":
                if is_reverification:
                    # User clicked Re-verify - mark as verified and clear the flag
                    annotations["verified"] = True
                    annotations["verified_at"] = datetime.now().isoformat()
                    annotations["needs_reverify"] = False
                else:
                    # User edited labels - if already verified, needs re-verification
                    if annotations.get("verified"):
                        annotations["needs_reverify"] = True
            
            if user_name:
                annotations["annotated_by"] = user_name
                if mode == "verify" and is_reverification:
                    annotations["verified_by"] = user_name
            item["annotations"] = annotations
            break

    summary = data.get("summary", {})
    summary["annotated"] = sum(1 for item in items if item and (item.get("annotations") or {}).get("labels"))
    summary["verified"] = sum(1 for item in items if item and (item.get("annotations") or {}).get("verified"))
    data["summary"] = summary
    return data


def _update_item_notes(data, item_id, notes, user_name=None):
    if not data or not item_id:
        return data
    items = data.get("items", [])
    for item in items:
        if not item:
            continue
        if item.get("item_id") == item_id:
            annotations = item.get("annotations") or {
                "labels": [],
                "annotated_by": None,
                "annotated_at": None,
                "verified": False,
                "notes": "",
            }
            annotations["notes"] = notes or ""
            annotations["annotated_at"] = datetime.now().isoformat()
            if user_name:
                annotations["annotated_by"] = user_name
            item["annotations"] = annotations
            break
    return data


def _filter_predictions(predictions, thresholds):
    if not predictions:
        return []
    
    thresholds = thresholds or {}
    global_threshold = float(thresholds.get("__global__", 0.5))
    filtered = []

    # Handle unified v2.0 model_outputs
    model_outputs = predictions.get("model_outputs")
    if model_outputs and isinstance(model_outputs, list):
        for out in model_outputs:
            label = out.get("class_hierarchy")
            score = out.get("score", 0)
            if label:
                label_threshold = float(thresholds.get(label, global_threshold))
                if score >= label_threshold:
                    filtered.append(label)
        return filtered

    # Fallback to legacy confidence/labels
    probs = predictions.get("confidence") or {}
    labels = predictions.get("labels") or []
    if not probs:
        return labels

    for label, prob in probs.items():
        label_threshold = float(thresholds.get(label, global_threshold))
        if prob >= label_threshold:
            filtered.append(label)
    return filtered


def _build_grid(items, mode, colormap, y_axis_scale, items_per_page):
    if not items:
        return [html.Div("No items loaded.", className="text-muted text-center p-4")]

    grid = []
    limit = min(items_per_page, len(items))
    for item in items[:limit]:
        image_src = get_item_image_src(item, colormap=colormap, y_axis_scale=y_axis_scale)
        card = create_spectrogram_card(item, image_src=image_src, mode=mode)
        grid.append(dbc.Col(card, md=3, sm=6, xs=12, className="mb-3"))

    return dbc.Row(grid)


def _create_folder_display(display_text, folders_list, data_root, popover_id):
    """Create a folder display — hoverable popover if multiple folders, plain text if single."""
    if folders_list and len(folders_list) > 1:
        relative_paths = []
        for f in folders_list:
            if data_root and f.startswith(data_root):
                relative_paths.append(f[len(data_root):].lstrip("/"))
            else:
                relative_paths.append(f)
        folder_items = [html.Div(p, className="mono-muted small") for p in relative_paths]
        return html.Div([
            html.Span(
                display_text,
                id=popover_id,
                style={"cursor": "pointer", "textDecoration": "underline", "color": "var(--link)"}
            ),
            dbc.Popover(
                dbc.PopoverBody(
                    html.Div(folder_items, style={"maxHeight": "200px", "overflowY": "auto"})
                ),
                target=popover_id,
                trigger="hover",
                placement="bottom",
            ),
        ])
    return display_text


def register_callbacks(app, config):
    set_cache_sizes((config or {}).get("cache", {}).get("max_size", 400))

    # ── Tab switching: buttons → store ─────────────────────────
    app.clientside_callback(
        """
        function(labelClicks, verifyClicks, exploreClicks) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (ctx && ctx.triggered && ctx.triggered.length > 0) {
                var id = ctx.triggered[0].prop_id.split('.')[0];
                if (id === 'tab-btn-label') return 'label';
                if (id === 'tab-btn-verify') return 'verify';
                if (id === 'tab-btn-explore') return 'explore';
                return dc.no_update;
            }
            var lc = labelClicks || 0;
            var vc = verifyClicks || 0;
            var ec = exploreClicks || 0;
            var max = Math.max(lc, vc, ec);
            if (max === 0) return dc.no_update;
            if (max === lc) return 'label';
            if (max === vc) return 'verify';
            return 'explore';
        }
        """,
        Output("mode-tabs", "data"),
        [Input("tab-btn-label", "n_clicks"),
         Input("tab-btn-verify", "n_clicks"),
         Input("tab-btn-explore", "n_clicks")],
        prevent_initial_call=True,
    )

    # ── Tab switching: store → update UI ────────────────────────
    app.clientside_callback(
        """
        function(mode) {
            var labelStyle = {display: mode === 'label' ? 'block' : 'none'};
            var verifyStyle = {display: mode === 'verify' ? 'block' : 'none'};
            var exploreStyle = {display: mode === 'explore' ? 'block' : 'none'};
            var labelClass = 'mode-tab' + (mode === 'label' ? ' mode-tab--active' : '');
            var verifyClass = 'mode-tab' + (mode === 'verify' ? ' mode-tab--active' : '');
            var exploreClass = 'mode-tab' + (mode === 'explore' ? ' mode-tab--active' : '');
            return [labelStyle, verifyStyle, exploreStyle, labelClass, verifyClass, exploreClass];
        }
        """,
        [Output("label-tab-content", "style"),
         Output("verify-tab-content", "style"),
         Output("explore-tab-content", "style"),
         Output("tab-btn-label", "className"),
         Output("tab-btn-verify", "className"),
         Output("tab-btn-explore", "className")],
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("label-data-store", "data"),
        Input("label-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
    )
    def load_label_data(reload_clicks, config_load_trigger, date_val, device_val, cfg, mode, current_label_data):
        """Load data specifically for Label mode."""
        # Check all triggered inputs (not just triggered_id) since multiple may change at once
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        # Get the mode that triggered the data load (if any)
        trigger_mode = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")

        # Only process if in label mode
        if mode != "label":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Label data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in label mode (already checked above)
        # Note: We check for source_data_dir rather than config matching because config-store
        # gets overwritten when loading data in other tabs (e.g., verify), so it won't match
        # the label data's source after switching tabs.
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = current_label_data and current_label_data.get("source_data_dir")

        # Load on: reload button, config load (for label mode only), or filter change (only if label data exists)
        # Note: trigger_mode == "label" means data-load-trigger-store was set for label mode,
        # even if ctx.triggered_id reports a different input (due to simultaneous updates)
        should_load = (
            "label-reload" in triggered_props or
            trigger_mode == "label" or
            (filter_triggered and has_source)
        )

        if should_load:
            try:
                # Use the current tab's own source_data_dir if available, 
                # to avoid pollution from global config overwritten by other tabs
                effective_cfg = cfg.copy() if cfg else {}
                source_data_dir = current_label_data.get("source_data_dir") if current_label_data else None
                
                # If we're reloading due to filter changes, prioritize the known data source
                if filter_triggered and source_data_dir:
                    if "data" not in effective_cfg:
                        effective_cfg["data"] = {}
                    effective_cfg["data"] = dict(effective_cfg.get("data", {}))
                    effective_cfg["data"]["data_dir"] = source_data_dir

                data = load_dataset(effective_cfg, "label", date_str=date_val, hydrophone=device_val)

                # Preserve manual labels path if it exists in current data
                # This prevents filter changes or tab switches from resetting a manually entered path
                if current_label_data and isinstance(current_label_data, dict):
                    old_summary = current_label_data.get("summary", {})
                    if old_summary.get("labels_file"):
                        data["summary"]["labels_file"] = old_summary["labels_file"]

                if trigger_mode == "label" and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                else:
                    data["load_timestamp"] = time.time()

                # Store the source data_dir so we can maintain context on filter changes
                data["source_data_dir"] = source_data_dir or effective_cfg.get("data", {}).get("data_dir")
                from app.main import set_audio_roots
                set_audio_roots(data.get("audio_roots", []))
                return data
            except Exception as e:
                print(f"Error loading label dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate

    @app.callback(
        Output("verify-data-store", "data"),
        Input("verify-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("verify-data-store", "data"),
    )
    def load_verify_data(reload_clicks, config_load_trigger, date_val, device_val, cfg, mode, current_verify_data):
        """Load data specifically for Verify mode."""
        # Check all triggered inputs (not just triggered_id) since multiple may change at once
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        # Get the mode that triggered the data load (if any)
        trigger_mode = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")

        # Only process if in verify mode
        if mode != "verify":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Verify data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in verify mode (already checked above)
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = current_verify_data and current_verify_data.get("source_data_dir")

        # Load on: reload button, config load (for verify mode only), or filter change (only if verify data exists)
        should_load = (
            "verify-reload" in triggered_props or
            trigger_mode == "verify" or
            (filter_triggered and has_source)
        )

        if should_load:
            try:
                # Use the current tab's own source_data_dir if available
                effective_cfg = cfg.copy() if cfg else {}
                source_data_dir = current_verify_data.get("source_data_dir") if current_verify_data else None
                
                if filter_triggered and source_data_dir:
                    if "data" not in effective_cfg:
                        effective_cfg["data"] = {}
                    effective_cfg["data"] = dict(effective_cfg.get("data", {}))
                    effective_cfg["data"]["data_dir"] = source_data_dir

                data = load_dataset(effective_cfg, "verify", date_str=date_val, hydrophone=device_val)

                # Preserve manual predictions path if it exists in current data
                if current_verify_data and isinstance(current_verify_data, dict):
                    old_summary = current_verify_data.get("summary", {})
                    if old_summary.get("predictions_file"):
                        data["summary"]["predictions_file"] = old_summary["predictions_file"]

                if trigger_mode == "verify" and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                else:
                    data["load_timestamp"] = time.time()

                data["source_data_dir"] = source_data_dir or effective_cfg.get("data", {}).get("data_dir")
                from app.main import set_audio_roots
                set_audio_roots(data.get("audio_roots", []))
                return data
            except Exception as e:
                print(f"Error loading verify dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate

    @app.callback(
        Output("explore-data-store", "data"),
        Input("explore-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("explore-data-store", "data"),
    )
    def load_explore_data(reload_clicks, config_load_trigger, date_val, device_val, cfg, mode, current_explore_data):
        """Load data specifically for Explore mode."""
        # Check all triggered inputs (not just triggered_id) since multiple may change at once
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        # Get the mode that triggered the data load (if any)
        trigger_mode = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")

        # Only process if in explore mode
        if mode != "explore":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Explore data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in explore mode (already checked above)
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = current_explore_data and current_explore_data.get("source_data_dir")

        # Load on: reload button, config load (for explore mode only), or filter change (only if explore data exists)
        should_load = (
            "explore-reload" in triggered_props or
            trigger_mode == "explore" or
            (filter_triggered and has_source)
        )

        if should_load:
            try:
                # Use the current tab's own source_data_dir if available
                effective_cfg = cfg.copy() if cfg else {}
                source_data_dir = current_explore_data.get("source_data_dir") if current_explore_data else None
                
                if filter_triggered and source_data_dir:
                    if "data" not in effective_cfg:
                        effective_cfg["data"] = {}
                    effective_cfg["data"] = dict(effective_cfg.get("data", {}))
                    effective_cfg["data"]["data_dir"] = source_data_dir

                data = load_dataset(effective_cfg, "explore", date_str=date_val, hydrophone=device_val)
                if trigger_mode == "explore" and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                else:
                    data["load_timestamp"] = time.time()
                data["source_data_dir"] = source_data_dir or effective_cfg.get("data", {}).get("data_dir")
                from app.main import set_audio_roots
                set_audio_roots(data.get("audio_roots", []))
                return data
            except Exception as e:
                print(f"Error loading explore dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate

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

        grid = _build_grid(page_items, "label", colormap, y_axis_scale, items_per_page)
        
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
        Input("verify-class-filter", "value"),
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
        class_filter = class_filter or "all"
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

            # Apply class filter - skip if a specific class is selected and item doesn't have it
            if class_filter != "all":
                if class_filter not in predicted_labels:
                    continue

            display_item = dict(item)
            display_predictions = dict(predictions)
            display_predictions["labels"] = predicted_labels
            display_item["predictions"] = display_predictions
            filtered_items.append(display_item)

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Visible: {len(filtered_items)}", className="fw-semibold"),
            html.Span(f"Total: {summary.get('total_items', len(items))}", className="ms-3 text-muted"),
            html.Span(f"Verified: {summary.get('verified', 0)}", className="ms-3 text-muted"),
            html.Span(f"Threshold: {current_threshold*100:.0f}%", className="ms-3 text-muted"),
            html.Span(f"Filter: {class_filter}", className="ms-3 text-muted"),
        ], className="summary-info")

        total_items = len(filtered_items)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))

        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = filtered_items[start_idx:end_idx]

        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "verify", colormap, y_axis_scale, items_per_page)
        
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
        Output("verify-class-filter", "options"),
        Output("verify-class-filter", "value"),
        Input("verify-data-store", "data"),
        State("verify-class-filter", "value"),
        prevent_initial_call=False,
    )
    def update_verify_class_filter(data, current_value):
        items = (data or {}).get("items", [])
        classes = set()
        for item in items:
            predictions = item.get("predictions") or {}
            
            # Unified v2.0
            model_outputs = predictions.get("model_outputs")
            if model_outputs and isinstance(model_outputs, list):
                for out in model_outputs:
                    if out.get("class_hierarchy"):
                        classes.add(out.get("class_hierarchy"))
            
            # Legacy
            probs = predictions.get("confidence") or {}
            labels = predictions.get("labels") or []
            classes.update(list(probs.keys()) + list(labels))

        options = [{"label": "All classes", "value": "all"}] + [
            {"label": label, "value": label} for label in sorted(classes)
        ]
        if current_value and any(opt["value"] == current_value for opt in options):
            return options, current_value
        return options, "all"

    @app.callback(
        Output("verify-thresholds-store", "data"),
        Input("verify-threshold-slider", "value"),
        State("verify-class-filter", "value"),
        State("verify-thresholds-store", "data"),
        prevent_initial_call=True,
    )
    def update_thresholds_store(slider_value, class_filter, thresholds):
        thresholds = thresholds or {"__global__": 0.5}
        class_filter = class_filter or "all"
        if slider_value is None:
            return thresholds

        value = float(slider_value)
        thresholds["__global__"] = value
        return thresholds

    @app.callback(
        Output("verify-threshold-slider", "value"),
        Input("verify-class-filter", "value"),
        State("verify-thresholds-store", "data"),
        prevent_initial_call=True,
    )
    def sync_threshold_slider(class_filter, thresholds):
        thresholds = thresholds or {"__global__": 0.5}
        class_filter = class_filter or "all"
        return float(thresholds.get("__global__", 0.5))

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

        grid = _build_grid(page_items, "explore", colormap, y_axis_scale, items_per_page)
        ui_ready = no_update
        if (data or {}).get("load_timestamp"):
            ui_ready = {"timestamp": data.get("load_timestamp")}
        return summary_block, grid, page_info, total_pages, ui_ready

    @app.callback(
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def close_editor_on_tab_switch(_mode):
        return False, [], None

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Input("label-output-input", "value"),
        State("label-data-store", "data"),
        prevent_initial_call=True
    )
    def sync_label_output_path_to_store(path_value, label_data):
        """Sync manual edits to the labels output path back to the data store."""
        if not label_data or path_value is None:
            raise PreventUpdate
        
        # Avoid unnecessary updates if the value matches
        summary = label_data.get("summary", {})
        if summary.get("labels_file") == path_value:
            raise PreventUpdate
            
        # Update the store with the new path
        new_data = dict(label_data)
        new_data["summary"] = dict(summary)
        new_data["summary"]["labels_file"] = path_value
        return new_data

    @app.callback(
        Output("label-spec-folder-display", "children", allow_duplicate=True),
        Output("label-audio-folder-display", "children", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Input("mode-tabs", "data"),
        State("label-data-store", "data"),
        prevent_initial_call=True,
    )
    def reset_label_displays_on_tab_switch(mode, label_data):
        """Restore Label tab folder displays when switching to Label tab.

        When switching tabs, date/device selectors get cleared which can trigger
        update_dynamic_path_displays and reset folder paths. This callback
        restores correct values from the label data store.
        """
        if mode != "label":
            raise PreventUpdate

        if not label_data or not label_data.get("items"):
            # No label data loaded - show clean slate
            return "Not set", "Not set", ""

        # Restore folder displays from label data summary
        summary = label_data.get("summary", {})
        data_root = summary.get("data_root", "")
        spec_display = _create_folder_display(
            summary.get("spectrogram_folder") or "Not set",
            summary.get("spectrogram_folders_list", []),
            data_root, "label-spec-popover-tab"
        )
        audio_display = _create_folder_display(
            summary.get("audio_folder") or "Not set",
            summary.get("audio_folders_list", []),
            data_root, "label-audio-popover-tab"
        )
        labels_file = summary.get("labels_file") or ""
        return spec_display, audio_display, labels_file

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
        prevent_initial_call=True,
    )
    def open_label_editor(n_clicks_list, cancel_clicks, click_store, edit_ids, label_data, verify_data,
                          explore_data, active_item_id, thresholds, mode):
        # Select the appropriate data store based on mode
        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}
        triggered = ctx.triggered_id
        if triggered == "label-editor-cancel":
            return False, no_update, None, click_store or {}
        if mode == "explore":
            return False, no_update, None, click_store or {}

        click_store = click_store or {}

        if not n_clicks_list or not edit_ids:
            return no_update, no_update, no_update, click_store

        chosen_item_id = None
        updated_store = dict(click_store)

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
        selected_labels = []
        existing_note = ""
        for item in items:
            if item.get("item_id") == chosen_item_id:
                annotations = item.get("annotations") or {}
                predicted = item.get("predictions", {}) if isinstance(item.get("predictions"), dict) else {}
                selected_labels = annotations.get("labels") or predicted.get("labels") or []
                existing_note = annotations.get("notes", "") if isinstance(annotations, dict) else ""
                if not selected_labels and mode == "verify":
                    selected_labels = _filter_predictions(predicted, thresholds or {"__global__": 0.5})
                break

        selector = create_hierarchical_selector(chosen_item_id, selected_labels)
        note_section = html.Details(
            [
                html.Summary("Note", style={"cursor": "pointer", "fontWeight": "600"}),
                dcc.Textarea(
                    id={"type": "note-editor-text", "filename": chosen_item_id},
                    value=existing_note,
                    placeholder="Add a note for this spectrogram...",
                    style={"width": "100%", "minHeight": "140px", "marginTop": "8px"},
                ),
            ],
            open=bool(existing_note),
            style={"marginTop": "12px"},
        )
        return True, html.Div([selector, note_section]), chosen_item_id, updated_store

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
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
        prevent_initial_call=True,
    )
    def save_label_editor(save_clicks, active_item_id, labels_list, labels_ids,
                          note_values, note_ids, label_data, verify_data, explore_data,
                          profile, mode, cfg, label_output_path):
        if not save_clicks or not active_item_id:
            raise PreventUpdate
        if mode == "explore":
            return no_update, no_update, no_update, False, []

        # Select the appropriate data store based on mode
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

        profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
        updated = _update_item_labels(data or {}, active_item_id, selected_labels, mode, user_name=profile_name)
        if note_text is not None:
            updated = _update_item_notes(updated or {}, active_item_id, note_text, user_name=profile_name)

        if mode == "label":
            # Priority: user input > data summary > config
            labels_file = label_output_path or (data or {}).get("summary", {}).get("labels_file") or cfg.get("label", {}).get("output_file")
            save_label_mode(labels_file, active_item_id, selected_labels, annotated_by=profile_name, notes=note_text)
        elif mode == "verify":
            # Verify mode persists only on Confirm/Re-verify.
            pass

        # Return updated data to the appropriate store, no_update for others
        if mode == "label":
            return updated, no_update, no_update, False, []
        elif mode == "verify":
            return no_update, updated, no_update, False, []
        else:
            return no_update, no_update, updated, False, []

    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Input({"type": "confirm-btn", "item_id": ALL}, "n_clicks"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "id"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_verification(n_clicks_list, data, thresholds, actions_list, actions_ids, profile):

        if not n_clicks_list or not any(n_clicks_list):
            raise PreventUpdate

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or "item_id" not in triggered:
            raise PreventUpdate

        item_id = triggered["item_id"]
        items = (data or {}).get("items", [])
        labels_to_confirm = []
        predictions = {}
        predictions_path = None
        annotations = {}
        thresholds = thresholds or {"__global__": 0.5}
        threshold_used = float(thresholds.get("__global__", 0.5))
        for item in items:
            if item.get("item_id") == item_id:
                annotations = item.get("annotations") or {}
                predictions = item.get("predictions") or {}
                predictions_path = (item.get("metadata") or {}).get("predictions_path")
                labels_to_confirm = annotations.get("labels") or []
                if not labels_to_confirm:
                    labels_to_confirm = _filter_predictions(predictions, {"__global__": threshold_used})
                break

        if not predictions_path:
            summary_pred = (data or {}).get("summary", {}).get("predictions_file")
            if isinstance(summary_pred, str) and summary_pred.endswith(".json"):
                predictions_path = summary_pred

        predicted_labels = _filter_predictions(predictions, {"__global__": threshold_used})
        predicted_set = set(predicted_labels)
        labels_set = set(labels_to_confirm)

        model_scores = {}
        model_outputs = predictions.get("model_outputs")
        if model_outputs and isinstance(model_outputs, list):
            for out in model_outputs:
                label = out.get("class_hierarchy")
                score = out.get("score")
                if label and isinstance(score, (int, float)):
                    model_scores[label] = score
        else:
            probs = predictions.get("confidence") or {}
            for label, score in probs.items():
                if isinstance(score, (int, float)):
                    model_scores[label] = score

        item_actions = []
        for i, action_id in enumerate(actions_ids or []):
            if action_id.get("filename") == item_id:
                item_actions = (actions_list or [])[i] or []
                break
        last_add_threshold = {}
        last_remove_threshold = {}
        for action in item_actions:
            label = action.get("label")
            threshold_value = action.get("threshold_used")
            if not label or threshold_value is None:
                continue
            if action.get("action") == "add":
                last_add_threshold[label] = threshold_value
            elif action.get("action") == "remove":
                last_remove_threshold[label] = threshold_value

        rejected_labels = set()
        for label in predicted_labels:
            if label not in labels_set:
                rejected_labels.add(label)
        for label, removed_threshold in last_remove_threshold.items():
            score = model_scores.get(label)
            if score is not None and score >= float(removed_threshold):
                rejected_labels.add(label)

        added_labels = {label for label in labels_set if label not in predicted_set}

        label_decisions = []
        for label in labels_to_confirm:
            if label in predicted_set:
                decision = "accepted"
            else:
                decision = "added"
            label_decisions.append({
                "label": label,
                "decision": decision,
                "threshold_used": float(last_add_threshold.get(label, threshold_used)),
            })
        for label in sorted(rejected_labels - labels_set):
            label_decisions.append({
                "label": label,
                "decision": "rejected",
                "threshold_used": float(last_remove_threshold.get(label, threshold_used)),
            })

        profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
        note_text = annotations.get("notes", "") if isinstance(annotations, dict) else ""
        verification = {
            "verified_at": datetime.now().isoformat(),
            "verified_by": profile_name or "anonymous",
            "labels": labels_to_confirm,
            "threshold_used": threshold_used,
            "rejected_labels": sorted(rejected_labels),
            "added_labels": sorted(added_labels),
            "label_decisions": label_decisions,
            "verification_status": "verified",
            "notes": note_text,
        }

        updated = _update_item_labels(
            data or {},
            item_id,
            labels_to_confirm,
            mode="verify",
            user_name=profile_name,
            is_reverification=True,
        )

        stored_verification = save_verify_predictions(predictions_path, item_id, verification)
        if stored_verification:
            for item in (updated or {}).get("items", []):
                if item.get("item_id") == item_id:
                    verifications = item.get("verifications")
                    if not isinstance(verifications, list):
                        verifications = []
                    verifications.append(stored_verification)
                    item["verifications"] = verifications
                    break
        return updated

    @app.callback(
        Output("profile-modal", "is_open"),
        Output("profile-name", "value"),
        Output("profile-email", "value"),
        Input("profile-btn", "n_clicks"),
        Input("profile-cancel", "n_clicks"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_profile_modal(open_clicks, cancel_clicks, profile):
        triggered = ctx.triggered_id
        if triggered == "profile-btn":
            profile = profile or {}
            return True, profile.get("name", ""), profile.get("email", "")
        if triggered == "profile-cancel":
            return False, no_update, no_update
        raise PreventUpdate

    @app.callback(
        Output("user-profile-store", "data"),
        Output("profile-modal", "is_open", allow_duplicate=True),
        Input("profile-save", "n_clicks"),
        State("profile-name", "value"),
        State("profile-email", "value"),
        prevent_initial_call=True,
    )
    def save_profile(n_clicks, name, email):
        if not n_clicks:
            raise PreventUpdate
        return {"name": name or "", "email": email or ""}, False

    @app.callback(
        Output("profile-name-display", "children"),
        Output("profile-email-display", "children"),
        Input("user-profile-store", "data"),
        prevent_initial_call=False,
    )
    def update_profile_display(profile):
        profile = profile or {}
        name = profile.get("name") or "Anonymous"
        email = profile.get("email") or "email not set"
        return name, email

    def _coerce_positive_int(value, fallback):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    @app.callback(
        Output("app-config-modal", "is_open"),
        Output("app-config-items-per-page", "value"),
        Output("app-config-cache-size", "value"),
        Output("config-store", "data", allow_duplicate=True),
        Input("app-config-btn", "n_clicks"),
        Input("app-config-cancel", "n_clicks"),
        Input("app-config-save", "n_clicks"),
        State("config-store", "data"),
        State("app-config-items-per-page", "value"),
        State("app-config-cache-size", "value"),
        prevent_initial_call=True,
    )
    def handle_app_config(open_clicks, cancel_clicks, save_clicks, cfg, items_per_page, cache_size):
        triggered = ctx.triggered_id
        cfg = cfg or {}
        display_cfg = cfg.get("display", {}) or {}
        cache_cfg = cfg.get("cache", {}) or {}

        if triggered == "app-config-btn":
            return (
                True,
                display_cfg.get("items_per_page", 25),
                cache_cfg.get("max_size", 400),
                no_update,
            )

        if triggered == "app-config-cancel":
            return False, no_update, no_update, no_update

        if triggered != "app-config-save":
            raise PreventUpdate

        new_items_per_page = _coerce_positive_int(items_per_page, display_cfg.get("items_per_page", 25))
        new_cache_size = _coerce_positive_int(cache_size, cache_cfg.get("max_size", 400))

        updated_cfg = dict(cfg)
        updated_cfg["display"] = dict(display_cfg)
        updated_cfg["display"]["items_per_page"] = new_items_per_page
        updated_cfg["cache"] = dict(cache_cfg)
        updated_cfg["cache"]["max_size"] = new_cache_size

        set_cache_sizes(new_cache_size)

        return False, new_items_per_page, new_cache_size, updated_cfg

    @app.callback(
        Output("theme-store", "data"),
        Input("theme-toggle", "n_clicks"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_theme_store(n_clicks, theme):
        if not n_clicks:
            raise PreventUpdate
        theme = theme or "light"
        return "dark" if theme == "light" else "light"

    @app.callback(
        Output("theme-toggle", "children"),
        Output("theme-toggle", "className"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def sync_theme_toggle(theme):
        theme = theme or "light"
        is_dark = theme == "dark"
        icon_class = "bi bi-sun" if is_dark else "bi bi-moon-stars"
        btn_class = "icon-btn theme-btn"
        if is_dark:
            btn_class += " icon-btn--active"
        return html.I(className=icon_class), btn_class

    @app.callback(
        Output("app-shell", "className"),
        Output("app-shell", "style"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def apply_theme(theme):
        theme = theme or "light"
        # Return className and empty style (CSS handles theming via classes now)
        return f"app-shell theme-{theme}", {}

    # Clientside callback to apply theme to body element (for modals)
    app.clientside_callback(
        """
        function(theme) {
            theme = theme || 'light';
            document.body.classList.remove('theme-light', 'theme-dark');
            document.body.classList.add('theme-' + theme);
            return '';
        }
        """,
        Output("dummy-output", "data"),
        Input("theme-store", "data"),
        prevent_initial_call=False
    )

    @app.callback(
        Output("image-modal", "is_open"),
        Output("current-filename", "data"),
        Output("modal-image-graph", "figure"),
        Output("modal-header", "children"),
        Output("modal-audio-player", "children"),
        Input({"type": "spectrogram-image", "item_id": ALL}, "n_clicks"),
        Input("close-modal", "n_clicks"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("mode-tabs", "data"),
        State("modal-colormap-toggle", "value"),
        State("modal-y-axis-toggle", "value"),
        prevent_initial_call=True,
    )
    def handle_modal_trigger(image_clicks_list, close_clicks, label_data, verify_data, explore_data, mode, colormap, y_axis_scale):
        # Select the appropriate data store based on mode
        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}
        triggered = ctx.triggered_id
        if triggered == "close-modal":
            return False, no_update, no_update, no_update, no_update

        if not isinstance(triggered, dict) or triggered.get("type") != "spectrogram-image":
            raise PreventUpdate

        # Find the item for the clicked image
        item_id = triggered.get("item_id")
        if not item_id:
            raise PreventUpdate

        # Verify it was an actual click
        if not any(image_clicks_list):
             raise PreventUpdate

        items = (data or {}).get("items", [])
        active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate

        # Load spectrogram and create figure
        mat_path = active_item.get("mat_path")
        spectrogram = load_spectrogram_cached(mat_path)
        fig = create_spectrogram_figure(spectrogram, colormap, y_axis_scale)

        # Create enhanced audio player for modal with pitch shift
        audio_path = active_item.get("audio_path")
        modal_audio = create_modal_audio_player(
            audio_path, item_id, player_id=f"modal-{hash(item_id) % 10000}"
        ) if audio_path else html.P("No audio available for this segment.", className="text-muted italic")

        return True, item_id, fig, f"Spectrogram: {item_id}", modal_audio

    @app.callback(
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        State("current-filename", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def update_modal_view(colormap, y_axis_scale, item_id, label_data, verify_data, explore_data, mode):
        # Select the appropriate data store based on mode
        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}
        if not item_id or not data:
            raise PreventUpdate

        items = data.get("items", [])
        active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate

        mat_path = active_item.get("mat_path")
        spectrogram = load_spectrogram_cached(mat_path)
        return create_spectrogram_figure(spectrogram, colormap, y_axis_scale)

    # Initialize audio players when page content or modal changes
    app.clientside_callback(
        """
        function(trigger) {
            if (window.dash_clientside && window.dash_clientside.namespace) {
                setTimeout(function() {
                    window.dash_clientside.namespace.initializeAudioPlayers();
                }, 150);
            }
            return '';
        }
        """,
        Output("dummy-output-audio", "children"),
        [Input("label-grid", "children"), 
         Input("verify-grid", "children"), 
         Input("modal-audio-player", "children")],
        prevent_initial_call=True
    )



    # Data Discovery Callbacks
    app.clientside_callback(
        """
        function(loadTrigger, labelReload, verifyReload, exploreReload, dateVal, deviceVal, mode, labelData, verifyData, exploreData) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (!ctx || !ctx.triggered || ctx.triggered.length === 0) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }

            var triggered = ctx.triggered[0];
            var triggerId = triggered.prop_id.split('.')[0];
            var triggerVal = triggered.value;

            function show(title, subtitle) {
                return [{display: "flex"}, title, subtitle];
            }

            if (triggerId === "data-load-trigger-store" && loadTrigger && loadTrigger.mode) {
                var title = "Loading dataset...";
                var subtitle = "Applying configuration and preparing your workspace.";
                if (loadTrigger.mode === "verify") {
                    subtitle = "Applying configuration and loading predictions.";
                } else if (loadTrigger.mode === "label") {
                    subtitle = "Applying configuration and loading items.";
                } else if (loadTrigger.mode === "explore") {
                    subtitle = "Applying configuration and loading items for exploration.";
                }
                return show(title, subtitle);
            }

            if (!triggerVal) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }

            if (triggerId === "label-reload" && mode === "label") {
                return show("Loading dataset...", "Reloading items.");
            }
            if (triggerId === "verify-reload" && mode === "verify") {
                return show("Loading dataset...", "Reloading predictions.");
            }
            if (triggerId === "explore-reload" && mode === "explore") {
                return show("Loading dataset...", "Reloading items for exploration.");
            }

            if (triggerId === "global-date-selector" || triggerId === "global-device-selector") {
                var tabData = mode === "label" ? labelData : (mode === "verify" ? verifyData : exploreData);
                var hasSource = tabData && tabData.source_data_dir;
                if (!hasSource) {
                    return [dc.no_update, dc.no_update, dc.no_update];
                }
                var title2 = "Updating filters...";
                var subtitle2 = "Loading data for the selected date/device.";
                if (mode === "verify") {
                    subtitle2 = "Loading predictions for the selected date/device.";
                } else if (mode === "explore") {
                    subtitle2 = "Loading items for exploration.";
                }
                return show(title2, subtitle2);
            }

            return [dc.no_update, dc.no_update, dc.no_update];
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Output("data-load-title", "children", allow_duplicate=True),
        Output("data-load-subtitle", "children", allow_duplicate=True),
        Input("data-load-trigger-store", "data"),
        Input("label-reload", "n_clicks"),
        Input("verify-reload", "n_clicks"),
        Input("explore-reload", "n_clicks"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("global-date-selector", "options", allow_duplicate=True),
        Output("global-date-selector", "value", allow_duplicate=True),
        Input("mode-tabs", "data"),
        State("config-store", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def discover_dates(mode, cfg, label_data, verify_data, explore_data):
        # Use the tab's own source_data_dir (not the global config which may have been overwritten)
        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        data_dir = tab_data.get("source_data_dir") if tab_data else None
        if not data_dir:
            data_dir = cfg.get("data", {}).get("data_dir") or cfg.get("verify", {}).get("dashboard_root")
        if not data_dir or not os.path.exists(data_dir):
            return [], None

        # Dates are folders like YYYY-MM-DD
        try:
            base_name = os.path.basename(data_dir.rstrip(os.sep))
            if len(base_name) == 10 and base_name[4] == '-' and base_name[7] == '-':
                return [{"label": base_name, "value": base_name}], base_name

            dates = [d for d in os.listdir(data_dir) if len(d) == 10 and os.path.isdir(os.path.join(data_dir, d))]
            dates.sort(reverse=True)

            options = [{"label": "All Dates", "value": "__all__"}] + [
                {"label": d, "value": d} for d in dates
            ]
            default_val = dates[0] if dates else None

            # Override with config if present
            config_date = cfg.get("verify", {}).get("date")
            if config_date in dates:
                default_val = config_date

            if dates:
                return options, default_val

            # Device-only root (no date folders) - keep date selector meaningful
            devices = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
            if devices:
                return [{"label": "Device folders", "value": "__device_only__"}], "__device_only__"

            return [], None
        except Exception:
            return [], None

    @app.callback(
        Output("global-device-selector", "options"),
        Output("global-device-selector", "value"),
        Input("global-date-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
    )
    def discover_devices(selected_date, cfg, mode, label_data, verify_data, explore_data):
        if not selected_date:
            return [], None

        # Skip discovery for flat structures
        if selected_date == "__flat__":
            return [], None

        # Use the current tab's source_data_dir to avoid cross-tab pollution
        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        data_dir = (tab_data.get("source_data_dir") if tab_data else None) or cfg.get("data", {}).get("data_dir") or cfg.get("verify", {}).get("dashboard_root")
        if not data_dir:
            return [], None
        
        try:
            devices = set()
            base_name = os.path.basename(data_dir.rstrip(os.sep))
            is_base_date = len(base_name) == 10 and base_name[4] == '-' and base_name[7] == '-'

            if selected_date == "__device_only__" or (is_base_date and selected_date in {base_name, "__all__"}):
                devices = {d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))}
            # If "All Dates" is selected, find all devices across all dates
            elif selected_date == "__all__":
                for date_folder in os.listdir(data_dir):
                    date_path = os.path.join(data_dir, date_folder)
                    # Check for date-like folder (YYYY-MM-DD format)
                    if os.path.isdir(date_path) and len(date_folder) == 10 and date_folder[4] == '-':
                        for d in os.listdir(date_path):
                            if os.path.isdir(os.path.join(date_path, d)):
                                devices.add(d)
            else:
                # Single date selected
                date_path = os.path.join(data_dir, selected_date)
                if os.path.exists(date_path):
                    devices = {d for d in os.listdir(date_path) if os.path.isdir(os.path.join(date_path, d))}

            devices = sorted(devices)
            
            # Add "All Devices" option at the beginning
            options = [{"label": "All Devices", "value": "__all__"}] + [
                {"label": d, "value": d} for d in devices
            ]
            default_val = devices[0] if devices else None
            
            # Override with config if present
            config_dev = cfg.get("verify", {}).get("hydrophone")
            if config_dev in devices:
                default_val = config_dev
                
            return options, default_val
        except Exception:
            return [], None

    @app.callback(
        Output("global-active-selection", "children"),
        Output("global-data-dir-display", "children", allow_duplicate=True),
        Input("label-data-store", "data"),
        Input("verify-data-store", "data"),
        Input("explore-data-store", "data"),
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def update_active_selection_display(label_data, verify_data, explore_data, mode):
        # Select the appropriate data store based on mode
        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}

        # Show the current tab's data directory
        data_dir = data.get("source_data_dir") if data else None
        data_dir_display = data_dir or "Not selected"

        if not data:
            return "No data loaded", data_dir_display

        summary = data.get("summary", {})
        date_str = summary.get("active_date")
        device = summary.get("active_hydrophone")

        if date_str and device:
            return f"{date_str} / {device}", data_dir_display
        return "Not selected", data_dir_display
