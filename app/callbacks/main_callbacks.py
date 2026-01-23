import os
from datetime import datetime
from dash import Input, Output, State, callback, ctx, no_update, ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html

from app.components.spectrogram_card import create_spectrogram_card
from app.components.hierarchical_selector import create_hierarchical_selector
from app.components.audio_player import create_audio_player, create_modal_audio_player
from app.utils.data_loading import load_dataset
from app.utils.image_utils import get_item_image_src
from app.utils.image_processing import load_spectrogram_cached, create_spectrogram_figure
from app.utils.persistence import save_label_mode, save_verify_mode


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


def register_callbacks(app, config):
    @app.callback(
        Output("data-store", "data"),
        Input("mode-tabs", "value"),
        Input("label-reload", "n_clicks"),
        Input("verify-reload", "n_clicks"),
        Input("global-load-btn", "n_clicks"),
        Input("explore-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        State("global-date-selector", "value"),
        State("global-device-selector", "value"),
        State("config-store", "data"),
        prevent_initial_call=False,
    )
    def load_data(mode, label_clicks, verify_clicks, global_load_clicks, explore_clicks, config_load_trigger, date_val, device_val, cfg):
        if not mode:
            raise PreventUpdate

        triggered = ctx.triggered_id
        if triggered is None:
            triggered = "mode-tabs"

        try:
            data = load_dataset(cfg, mode, date_str=date_val, hydrophone=device_val)
            from app.main import set_audio_roots
            set_audio_roots(data.get("audio_roots", []))
            return data
        except Exception as e:
            print(f"Error loading dataset: {e}")
            return {"items": [], "summary": {"total_items": 0, "error": str(e)}}

    @app.callback(
        Output("label-summary", "children"),
        Output("label-grid", "children"),
        Output("label-page-info", "children"),
        Output("label-page-input", "max"),
        Output("label-spec-folder-display", "children", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Input("data-store", "data"),
        Input("label-colormap-toggle", "value"),
        Input("label-yaxis-toggle", "value"),
        Input("label-current-page", "data"),
        State("mode-tabs", "value"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def render_label(data, use_hydrophone_colormap, use_log_y_axis, current_page, mode, cfg):
        if mode != "label":
            return no_update, no_update, no_update, no_update, no_update, no_update

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
        
        # Update folder display if available in summary
        folder_display = summary.get("spectrogram_folder") or no_update
        labels_file_display = summary.get("labels_file") or no_update
        
        return summary_block, grid, page_info, total_pages, folder_display, labels_file_display

    @app.callback(
        Output("verify-summary", "children"),
        Output("verify-grid", "children"),
        Output("verify-spec-folder-display", "children"),
        Output("verify-audio-folder-display", "children"),
        Output("verify-predictions-display", "children"),
        Output("verify-data-root-display", "children"),
        Input("data-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "value"),
        State("mode-tabs", "value"),
        State("config-store", "data"),
    )
    def render_verify(data, thresholds, class_filter, mode, cfg):
        if mode != "verify":
            return no_update, no_update, no_update, no_update, no_update, no_update

        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])
        thresholds = thresholds or {"__global__": 0.5}
        class_filter = class_filter or "all"
        current_threshold = float(thresholds.get(class_filter, thresholds.get("__global__", 0.5)))

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

        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Visible: {len(filtered_items)}", className="fw-semibold"),
            html.Span(f"Total: {summary.get('total_items', len(items))}", className="ms-3 text-muted"),
            html.Span(f"Verified: {summary.get('verified', 0)}", className="ms-3 text-muted"),
            html.Span(f"Threshold: {current_threshold*100:.0f}%", className="ms-3 text-muted"),
            html.Span(f"Filter: {class_filter}", className="ms-3 text-muted"),
        ], className="summary-info")

        grid = _build_grid(filtered_items, "verify", cfg.get("display", {}).get("colormap", "default"),
                           cfg.get("display", {}).get("y_axis_scale", "linear"), items_per_page)
        
        data_root = summary.get("data_root") or "Not set"
        
        return summary_block, grid, spec_folder, audio_folder, predictions_file, data_root

    @app.callback(
        Output("verify-class-filter", "options"),
        Output("verify-class-filter", "value"),
        Input("data-store", "data"),
        State("mode-tabs", "value"),
        State("verify-class-filter", "value"),
        prevent_initial_call=False,
    )
    def update_verify_class_filter(data, mode, current_value):
        if mode != "verify":
            return no_update, no_update

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
        if class_filter == "all":
            thresholds["__global__"] = value
        else:
            thresholds[class_filter] = value
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
        return float(thresholds.get(class_filter, thresholds.get("__global__", 0.5)))

    @app.callback(
        Output("explore-summary", "children"),
        Output("explore-grid", "children"),
        Input("data-store", "data"),
        State("mode-tabs", "value"),
        State("config-store", "data"),
    )
    def render_explore(data, mode, cfg):
        if mode != "explore":
            return no_update, no_update

        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])

        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Items: {summary.get('total_items', len(items))}", className="fw-semibold"),
        ])

        grid = _build_grid(items, "explore", cfg.get("display", {}).get("colormap", "default"),
                           cfg.get("display", {}).get("y_axis_scale", "linear"), items_per_page)
        return summary_block, grid

    @app.callback(
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Input("mode-tabs", "value"),
        prevent_initial_call=True,
    )
    def close_editor_on_tab_switch(_mode):
        return False, [], None

    @app.callback(
        Output("label-editor-modal", "is_open"),
        Output("label-editor-body", "children"),
        Output("active-item-store", "data"),
        Output("label-editor-clicks", "data"),
        Input({"type": "edit-btn", "item_id": ALL}, "n_clicks"),
        Input("label-editor-cancel", "n_clicks"),
        State("label-editor-clicks", "data"),
        State({"type": "edit-btn", "item_id": ALL}, "id"),
        State("data-store", "data"),
        State("mode-tabs", "value"),
        prevent_initial_call=True,
    )
    def open_label_editor(n_clicks_list, cancel_clicks, click_store, edit_ids, data, mode):
        triggered = ctx.triggered_id
        if triggered == "label-editor-cancel":
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
        for item in items:
            if item.get("item_id") == chosen_item_id:
                annotations = item.get("annotations") or {}
                predicted = item.get("predictions", {}) if isinstance(item.get("predictions"), dict) else {}
                selected_labels = annotations.get("labels") or predicted.get("labels") or []
                break

        selector = create_hierarchical_selector(chosen_item_id, selected_labels)
        return True, selector, chosen_item_id, updated_store

    @app.callback(
        Output("data-store", "data", allow_duplicate=True),
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Input("label-editor-save", "n_clicks"),
        State("active-item-store", "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "id"),
        State("data-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "value"),
        State("config-store", "data"),
        State("label-output-input", "value"),
        prevent_initial_call=True,
    )
    def save_label_editor(save_clicks, active_item_id, labels_list, labels_ids, data, profile, mode, cfg, label_output_path):
        if not save_clicks or not active_item_id:
            raise PreventUpdate

        selected_labels = []
        for i, label_id in enumerate(labels_ids or []):
            if label_id.get("filename") == active_item_id:
                selected_labels = labels_list[i] or []
                break

        profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
        profile_role = (profile or {}).get("role") if isinstance(profile, dict) else None
        updated = _update_item_labels(data or {}, active_item_id, selected_labels, mode, user_name=profile_name)

        if mode == "label":
            # Priority: user input > data summary > config
            labels_file = label_output_path or (data or {}).get("summary", {}).get("labels_file") or cfg.get("label", {}).get("output_file")
            save_label_mode(labels_file, active_item_id, selected_labels)
        elif mode == "verify":
            source = (updated or {}).get("source", {}).get("data_source", {})
            date_str = source.get("date") or cfg.get("verify", {}).get("date")
            hydrophone = source.get("hydrophone") or cfg.get("verify", {}).get("hydrophone")
            dashboard_root = cfg.get("data", {}).get("data_dir") or cfg.get("verify", {}).get("dashboard_root")
            save_verify_mode(dashboard_root, date_str, hydrophone,
                            active_item_id, selected_labels, username=profile_name, role=profile_role)

        return updated, False, []

    @app.callback(
        Output("data-store", "data", allow_duplicate=True),
        Input({"type": "confirm-btn", "item_id": ALL}, "n_clicks"),
        State("data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "value"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_verification(n_clicks_list, data, thresholds, profile, mode, cfg):
        if mode != "verify":
            raise PreventUpdate

        if not n_clicks_list or not any(n_clicks_list):
            raise PreventUpdate

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or "item_id" not in triggered:
            raise PreventUpdate

        item_id = triggered["item_id"]
        items = (data or {}).get("items", [])
        labels_to_confirm = []
        thresholds = thresholds or {"__global__": 0.5}
        for item in items:
            if item.get("item_id") == item_id:
                annotations = item.get("annotations") or {}
                labels_to_confirm = annotations.get("labels") or []
                if not labels_to_confirm:
                    predictions = item.get("predictions") or {}
                    labels_to_confirm = _filter_predictions(predictions, thresholds)
                break

        profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
        profile_role = (profile or {}).get("role") if isinstance(profile, dict) else None
        updated = _update_item_labels(data or {}, item_id, labels_to_confirm, mode="verify", user_name=profile_name, is_reverification=True)
        source = (updated or {}).get("source", {}).get("data_source", {})
        date_str = source.get("date") or cfg.get("verify", {}).get("date")
        hydrophone = source.get("hydrophone") or cfg.get("verify", {}).get("hydrophone")
        save_verify_mode(cfg.get("verify", {}).get("dashboard_root"), date_str, hydrophone,
                        item_id, labels_to_confirm, username=profile_name, role=profile_role)
        return updated

    @app.callback(
        Output("profile-modal", "is_open"),
        Output("profile-name", "value"),
        Output("profile-role", "value"),
        Input("profile-btn", "n_clicks"),
        Input("profile-cancel", "n_clicks"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_profile_modal(open_clicks, cancel_clicks, profile):
        triggered = ctx.triggered_id
        if triggered == "profile-btn":
            profile = profile or {}
            return True, profile.get("name", ""), profile.get("role", "")
        if triggered == "profile-cancel":
            return False, no_update, no_update
        raise PreventUpdate

    @app.callback(
        Output("user-profile-store", "data"),
        Output("profile-modal", "is_open", allow_duplicate=True),
        Input("profile-save", "n_clicks"),
        State("profile-name", "value"),
        State("profile-role", "value"),
        prevent_initial_call=True,
    )
    def save_profile(n_clicks, name, role):
        if not n_clicks:
            raise PreventUpdate
        return {"name": name or "", "role": role or ""}, False

    @app.callback(
        Output("theme-store", "data"),
        Input("theme-toggle", "value"),
        prevent_initial_call=True,
    )
    def update_theme_store(is_dark):
        return "dark" if is_dark else "light"

    @app.callback(
        Output("theme-toggle", "value"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def sync_theme_toggle(theme):
        return theme == "dark"

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

    @app.callback(
        Output("image-modal", "is_open"),
        Output("current-filename", "data"),
        Output("modal-image-graph", "figure"),
        Output("modal-header", "children"),
        Output("modal-audio-player", "children"),
        Input({"type": "spectrogram-image", "item_id": ALL}, "n_clicks"),
        Input("close-modal", "n_clicks"),
        State("data-store", "data"),
        State("modal-colormap-toggle", "value"),
        State("modal-y-axis-toggle", "value"),
        prevent_initial_call=True,
    )
    def handle_modal_trigger(image_clicks_list, close_clicks, data, colormap, y_axis_scale):
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
        State("data-store", "data"),
        prevent_initial_call=True,
    )
    def update_modal_view(colormap, y_axis_scale, item_id, data):
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
        Output("dummy-output", "children"),
        [Input("label-grid", "children"), 
         Input("verify-grid", "children"), 
         Input("modal-audio-player", "children")],
        prevent_initial_call=True
    )



    # Data Discovery Callbacks
    @app.callback(
        Output("global-date-selector", "options", allow_duplicate=True),
        Output("global-date-selector", "value", allow_duplicate=True),
        Input("mode-tabs", "value"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def discover_dates(mode, cfg):
        # Always discover if data_dir is present
        data_dir = cfg.get("data", {}).get("data_dir") or cfg.get("verify", {}).get("dashboard_root")
        if not data_dir or not os.path.exists(data_dir):
            return [], None
            
        # Dates are folders like YYYY-MM-DD
        try:
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
                
            return options, default_val
        except Exception:
            return [], None

    @app.callback(
        Output("global-device-selector", "options"),
        Output("global-device-selector", "value"),
        Input("global-date-selector", "value"),
        State("config-store", "data"),
    )
    def discover_devices(selected_date, cfg):
        if not selected_date:
            return [], None
        
        # Skip discovery for flat structures
        if selected_date == "__flat__":
            return [], None
            
        data_dir = cfg.get("data", {}).get("data_dir") or cfg.get("verify", {}).get("dashboard_root")
        if not data_dir:
            return [], None
        
        try:
            devices = set()
            
            # If "All Dates" is selected, find all devices across all dates
            if selected_date == "__all__":
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
        Input("data-store", "data"),
    )
    def update_active_selection_display(data):
        if not data:
            return "No data loaded"
        
        summary = data.get("summary", {})
        date_str = summary.get("active_date")
        device = summary.get("active_hydrophone")
        
        if date_str and device:
            return f"{date_str} / {device}"
        return "Not selected"
