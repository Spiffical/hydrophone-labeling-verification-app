"""
Callbacks for the data configuration panel.
Handles data structure detection, manual path overrides, and loading.
"""
import os
from dash import Input, Output, State, callback, ctx, no_update, ALL
from dash.exceptions import PreventUpdate
from dash import html
import dash_bootstrap_components as dbc

from app.utils.data_discovery import detect_data_structure, discover_items_from_folder
from app.layouts.data_config_panel import create_hierarchy_tree, create_labels_recommendation, create_multi_folder_display, create_multi_file_display
from app.utils.label_operations import get_path_for_filter, get_smart_labels_path


def register_data_config_callbacks(app):
    """Register all data configuration related callbacks."""

    @app.callback(
        Output("data-config-modal", "is_open"),
        Output("data-discovery-store", "data"),
        Output("data-config-structure-type", "children"),
        Output("data-config-structure-message", "children"),
        Output("data-config-spec-folder", "value"),
        Output("data-config-audio-folder", "value"),
        Output("data-config-predictions-file", "value"),
        Output("data-config-spec-info", "children"),
        Output("data-config-audio-info", "children"),
        Output("data-config-predictions-info", "children"),
        Output("data-config-predictions-label", "children"),
        Output("data-config-hierarchy-detail", "children"),
        Output("hierarchy-toggle-container", "style"),
        Output("data-config-labels-recommendation", "children"),
        Output("data-config-spec-multi", "children"),
        Output("data-config-audio-multi", "children"),
        Output("data-config-spec-single-container", "style"),
        Output("data-config-audio-single-container", "style"),
        Output("data-config-predictions-multi", "children"),
        Output("data-config-predictions-single-container", "style"),
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Input("folder-browser-confirm", "n_clicks"),
        Input("data-config-cancel", "n_clicks"),
        Input("data-config-close", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def open_data_config(confirm_clicks, cancel_clicks, close_clicks, selected_path, browse_target, current_mode):
        """Open data config modal after folder selection."""
        triggered = ctx.triggered_id

        if triggered in ["data-config-cancel", "data-config-close"]:
            return (False, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update, {"display": "none"})

        if triggered != "folder-browser-confirm" or not selected_path:
            raise PreventUpdate

        # If a specific browse target is set, don't open data config modal
        # This means we're doing a sub-browse for a specific field (labels, predictions, etc.)
        if browse_target and browse_target.get("target"):
            raise PreventUpdate

        # Detect data structure
        discovery = detect_data_structure(selected_path)

        # Structure type display
        structure_labels = {
            "hierarchical": "Hierarchical (Date/Device)",
            "device_only": "Device Folders",
            "flat": "Flat Spectrograms",
            "unknown": "Unknown Structure",
        }
        structure_type = structure_labels.get(discovery["structure_type"], "Unknown")

        # Create info badges
        spec_info = _create_info_badge(
            bool(discovery.get("spectrogram_folder")),
            discovery.get("spectrogram_count", 0),
            ", ".join(discovery.get("spectrogram_extensions", []))
        )
        audio_info = _create_info_badge(
            bool(discovery.get("audio_folder")),
            discovery.get("audio_count", 0)
        )

        # Determine label and info based on mode
        is_label_mode = current_mode == "label"
        predictions_label = "Labels File" if is_label_mode else "Predictions File"
        predictions_info = _create_predictions_info(bool(discovery.get("predictions_file")), is_label_mode)

        # Create hierarchy detail tree (for hierarchical and device_only structures)
        hierarchy_tree = create_hierarchy_tree(discovery)
        show_hierarchy_toggle = {"display": "block"} if discovery["structure_type"] in ("hierarchical", "device_only") else {"display": "none"}

        # Create labels recommendation
        labels_recommendation = create_labels_recommendation(discovery, is_label_mode)

        # Determine smart default for predictions/labels file path
        predictions_file_value = discovery.get("predictions_file") or ""
        if is_label_mode and not predictions_file_value:
            # For label mode, default to root-level labels.json if hierarchical
            root_labels = discovery.get("root_labels_file")
            if root_labels:
                predictions_file_value = root_labels
            elif discovery["structure_type"] in ("hierarchical", "device_only"):
                # Default to root-level labels.json for new hierarchical data
                predictions_file_value = os.path.join(selected_path, "labels.json")

        # Build multi-folder displays for hierarchical structures
        spec_folders = []
        audio_folders = []
        is_hierarchical = discovery["structure_type"] in ("hierarchical", "device_only")

        if discovery["structure_type"] == "hierarchical":
            hierarchy_detail = discovery.get("hierarchy_detail", {})
            for date in sorted(hierarchy_detail.keys()):
                for device, info in sorted(hierarchy_detail[date].items()):
                    spec_count = info.get("spectrogram_count", 0)
                    audio_count = info.get("audio_count", 0)
                    spec_folder_path = info.get("spectrogram_folder")
                    audio_folder_path = info.get("audio_folder")
                    if spec_count > 0 and spec_folder_path:
                        # Get relative path from the base path
                        rel_path = os.path.relpath(spec_folder_path, selected_path)
                        spec_folders.append({
                            "relative_path": rel_path,
                            "path": spec_folder_path,
                            "count": spec_count,
                        })
                    if audio_count > 0 and audio_folder_path:
                        rel_path = os.path.relpath(audio_folder_path, selected_path)
                        audio_folders.append({
                            "relative_path": rel_path,
                            "path": audio_folder_path,
                            "count": audio_count,
                        })
        elif discovery["structure_type"] == "device_only":
            device_detail = discovery.get("device_detail", {})
            for device, info in sorted(device_detail.items()):
                spec_count = info.get("spectrogram_count", 0)
                audio_count = info.get("audio_count", 0)
                spec_folder_path = info.get("spectrogram_folder")
                audio_folder_path = info.get("audio_folder")
                if spec_count > 0 and spec_folder_path:
                    rel_path = os.path.relpath(spec_folder_path, selected_path)
                    spec_folders.append({
                        "relative_path": rel_path,
                        "path": spec_folder_path,
                        "count": spec_count,
                    })
                if audio_count > 0 and audio_folder_path:
                    rel_path = os.path.relpath(audio_folder_path, selected_path)
                    audio_folders.append({
                        "relative_path": rel_path,
                        "path": audio_folder_path,
                        "count": audio_count,
                    })

        # Create multi-folder displays
        spec_multi = create_multi_folder_display(spec_folders, "spectrogram") if spec_folders else html.Div()
        audio_multi = create_multi_folder_display(audio_folders, "audio") if audio_folders else html.Div()

        # Create multi-predictions display if multiple files found
        predictions_locations = discovery.get("subfolder_predictions_locations", [])
        if is_label_mode:
            predictions_locations = discovery.get("subfolder_labels_locations", [])
        
        has_multiple_predictions = len(predictions_locations) > 1
        predictions_multi = html.Div()
        if has_multiple_predictions:
            file_type = "labels" if is_label_mode else "predictions"
            predictions_multi = create_multi_file_display(predictions_locations, selected_path, file_type)
            # Update label to use plural form
            predictions_label = "Labels Files" if is_label_mode else "Predictions Files"

        # Show/hide single input vs multi-folder display
        show_single = {"display": "block"} if not is_hierarchical else {"display": "none"}
        hide_single = {"display": "none"} if is_hierarchical else {"display": "block"}
        
        # For predictions: hide the single input when multiple files are shown in multi-display
        show_predictions_single = {"display": "none"} if has_multiple_predictions else {"display": "block"}

        return (
            True,  # Open modal
            discovery,  # Store discovery results
            structure_type,
            discovery.get("message", ""),
            discovery.get("spectrogram_folder") or "",
            discovery.get("audio_folder") or "",
            predictions_file_value,
            spec_info,
            audio_info,
            predictions_info,
            predictions_label,
            hierarchy_tree,
            show_hierarchy_toggle,
            labels_recommendation,
            spec_multi,
            audio_multi,
            hide_single,  # Hide single spec input for hierarchical
            hide_single,  # Hide single audio input for hierarchical
            predictions_multi,  # Multi-predictions display
            show_predictions_single,  # Always show predictions input
            {"display": "none"},
        )

    app.clientside_callback(
        """
        function(confirmClicks, browseTarget, selectedPath) {
            var dc = (window.dash_clientside || {});
            if (!confirmClicks) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            if (browseTarget && browseTarget.target) {
                return [{display: "none"}, dc.no_update, dc.no_update];
            }
            if (!selectedPath) {
                return [{display: "none"}, dc.no_update, dc.no_update];
            }
            return [
                {display: "flex"},
                "Analyzing data folder...",
                "Detecting structure and files. This can take a moment on mounted drives."
            ];
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Output("data-load-title", "children", allow_duplicate=True),
        Output("data-load-subtitle", "children", allow_duplicate=True),
        Input("folder-browser-confirm", "n_clicks"),
        State("path-browse-target-store", "data"),
        State("folder-browser-selected-store", "data"),
        prevent_initial_call=True,
    )

    # Toggle hierarchy collapse
    @app.callback(
        Output("data-config-hierarchy-collapse", "is_open"),
        Output("hierarchy-toggle-icon", "className"),
        Output("data-config-hierarchy-toggle", "children"),
        Input("data-config-hierarchy-toggle", "n_clicks"),
        State("data-config-hierarchy-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_hierarchy_collapse(n_clicks, is_open):
        """Toggle the hierarchy detail collapse."""
        if n_clicks:
            new_is_open = not is_open
            icon_class = "bi bi-chevron-up me-1" if new_is_open else "bi bi-chevron-down me-1"
            button_text = "Hide Details" if new_is_open else "Show Details"
            return new_is_open, icon_class, [html.I(className=icon_class, id="hierarchy-toggle-icon"), button_text]
        raise PreventUpdate
    
    @app.callback(
        Output("data-config-modal", "is_open", allow_duplicate=True),
        Output("config-store", "data", allow_duplicate=True),
        Output("global-data-dir-display", "children", allow_duplicate=True),
        Output("global-date-selector", "options", allow_duplicate=True),
        Output("global-date-selector", "value", allow_duplicate=True),
        Output("global-device-selector", "options", allow_duplicate=True),
        Output("global-device-selector", "value", allow_duplicate=True),
        Output("label-spec-folder-display", "children"),
        Output("label-audio-folder-display", "children"),
        Output("label-output-input", "value", allow_duplicate=True),
        Output("data-load-trigger-store", "data"),
        Input("data-config-load", "n_clicks"),
        State("data-discovery-store", "data"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("data-config-predictions-file", "value"),
        State("folder-browser-selected-store", "data"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def load_data_from_config(load_clicks, discovery, spec_folder, audio_folder, predictions_file, base_path, config, current_mode):
        """Load data based on configuration panel settings."""
        if not load_clicks:
            raise PreventUpdate
        
        # Update config with paths
        if "data" not in config:
            config["data"] = {}
        
        config["data"]["data_dir"] = base_path
        
        structure_type = discovery.get("structure_type") if discovery else "flat"
        config["data"]["structure_type"] = structure_type
        
        # For hierarchical structures, DON'T store folder overrides - let them be discovered dynamically
        # Only store folder paths for flat structures where there's a single folder
        if structure_type in ("hierarchical", "device_only"):
            # Clear any previous folder overrides so loading discovers paths dynamically
            config["data"]["spectrogram_folder"] = None
            config["data"]["audio_folder"] = None
            config["data"]["predictions_file"] = predictions_file or None
        else:
            # Flat structure - use the specified folders
            config["data"]["spectrogram_folder"] = spec_folder or None
            config["data"]["audio_folder"] = audio_folder or None
            config["data"]["predictions_file"] = predictions_file or None
        
        # Prepare date/device options based on structure
        date_options = []
        date_value = None
        device_options = []
        device_value = None
        
        if structure_type == "hierarchical":
            dates = discovery.get("dates", [])
            devices = discovery.get("devices", [])
            # Add "All" option at the beginning
            date_options = [{"label": "All Dates", "value": "__all__"}] + [{"label": d, "value": d} for d in dates]
            device_options = [{"label": "All Devices", "value": "__all__"}] + [{"label": d, "value": d} for d in devices]
            date_value = "__all__"  # Default to all dates (no filter)
            device_value = "__all__"  # Default to all devices (no filter)
        elif structure_type == "device_only":
            devices = discovery.get("devices", [])
            # Add "All" option for devices
            device_options = [{"label": "All Devices", "value": "__all__"}] + [{"label": d, "value": d} for d in devices]
            device_value = "__all__"  # Default to all devices (no filter)
            # If the selected root is itself a date folder, show it in the date selector
            base_label = None
            if base_path:
                base_name = os.path.basename(base_path.rstrip(os.sep))
                if len(base_name) == 10 and base_name[4] == "-" and base_name[7] == "-":
                    base_label = base_name
            if base_label:
                date_options = [{"label": base_label, "value": base_label}]
                date_value = base_label
            else:
                date_options = [{"label": "Device folders", "value": "__device_only__"}]
                date_value = "__device_only__"
        else:
            # Flat or unknown - use special marker to indicate direct loading
            date_options = [{"label": "(Direct)", "value": "__flat__"}]
            date_value = "__flat__"
        
        display_path = base_path if base_path else "Not selected"

        # Only prepare Label tab display values when in Label mode
        # This prevents cross-tab pollution where Verify data shows in Label tab
        if current_mode == "label":
            spec_display = spec_folder or base_path or "Not set"
            audio_display = audio_folder or "Not set"

            # For label mode output, use smart labels path
            # Priority: root-level labels.json for hierarchical, otherwise in spec_folder/base_path
            if structure_type in ("hierarchical", "device_only"):
                # Check if root labels.json exists or use it as default
                root_labels = discovery.get("root_labels_file") if discovery else None
                if root_labels:
                    output_display = root_labels
                elif base_path:
                    output_display = os.path.join(base_path, "labels.json")
                else:
                    output_display = "Not set"
            elif spec_folder:
                output_display = os.path.join(spec_folder, "labels.json")
            elif base_path:
                output_display = os.path.join(base_path, "labels.json")
            else:
                output_display = "Not set"
        else:
            # Not in label mode - don't update label displays
            spec_display = no_update
            audio_display = no_update
            output_display = no_update

        # Create a trigger value that includes the current mode so only that mode loads data
        import time
        trigger_value = {"timestamp": time.time(), "mode": current_mode}

        return (
            False,  # Close modal
            config,
            display_path,
            date_options,
            date_value,
            device_options,
            device_value,
            spec_display,
            audio_display,
            output_display,
            trigger_value,  # Trigger data reload
        )

    app.clientside_callback(
        """
        function(loadClicks, mode) {
            var dc = (window.dash_clientside || {});
            if (!loadClicks) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            var title = "Loading dataset...";
            var subtitle = "Applying configuration and preparing your workspace.";
            if (mode === "verify") {
                subtitle = "Applying configuration and loading predictions.";
            } else if (mode === "label") {
                subtitle = "Applying configuration and loading items.";
            } else if (mode === "explore") {
                subtitle = "Applying configuration and loading items for exploration.";
            }
            return [{display: "flex"}, title, subtitle];
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Output("data-load-title", "children", allow_duplicate=True),
        Output("data-load-subtitle", "children", allow_duplicate=True),
        Input("data-config-load", "n_clicks"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Input("label-data-store", "data"),
        Input("verify-data-store", "data"),
        Input("explore-data-store", "data"),
        prevent_initial_call=True,
    )
    def hide_loading_overlay_on_data_load(_label_data, _verify_data, _explore_data):
        """Hide the loading overlay once any dataset finishes loading."""
        return {"display": "none"}
    
    @app.callback(
        Output("verify-predictions-warning", "is_open"),
        Input("mode-tabs", "data"),
        Input("verify-data-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def show_predictions_warning(mode, verify_data, config):
        loaded_data = verify_data
        """Show warning when switching to Verify mode without predictions."""
        if mode != "verify":
            return False
        
        # Check if loaded data has items with predictions
        if loaded_data and loaded_data.get("items"):
            for item in loaded_data["items"]:
                if item.get("predictions") and item["predictions"].get("model_outputs"):
                    return False  # Found predictions in loaded data
                # Also check for legacy prediction format
                if item.get("predictions") and item["predictions"].get("labels"):
                    return False
        
        # Check if predictions file is configured
        predictions_file = config.get("data", {}).get("predictions_file")
        if predictions_file and os.path.exists(predictions_file):
            return False
        
        # Check if we have a data directory with predictions
        data_dir = config.get("data", {}).get("data_dir")
        if data_dir:
            # Try to find predictions in the data directory
            discovery = detect_data_structure(data_dir)
            if discovery.get("predictions_file"):
                return False
        
        # No predictions found - show warning
        return True
    
    @app.callback(
        Output("mode-tabs", "data", allow_duplicate=True),
        Input("verify-continue-label-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def switch_to_label_mode(n_clicks):
        """Switch to Label mode when user chooses to continue without predictions."""
        if n_clicks:
            return "label"
        raise PreventUpdate

    # Sub-browser for path selection within data config
    @app.callback(
        Output("folder-browser-modal", "is_open", allow_duplicate=True),
        Output("folder-browser-path-store", "data", allow_duplicate=True),
        Output("path-browse-target-store", "data"),
        Input("data-config-spec-browse", "n_clicks"),
        Input("data-config-audio-browse", "n_clicks"),
        Input("data-config-predictions-browse", "n_clicks"),
        Input("label-output-browse-btn", "n_clicks"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("label-output-input", "value"),
        State("folder-browser-selected-store", "data"),
        prevent_initial_call=True,
    )
    def open_path_browser(spec_clicks, audio_clicks, predictions_clicks, labels_clicks, spec_folder, audio_folder, labels_path, base_path):
        """Open folder browser for path selection."""
        triggered = ctx.triggered_id
        
        if triggered == "data-config-spec-browse":
            # Start from current spec folder or base path
            start_path = os.path.dirname(spec_folder) if spec_folder else (base_path or os.path.expanduser("~"))
            return True, start_path, {"target": "spectrogram", "type": "folder"}
        elif triggered == "data-config-audio-browse":
            start_path = os.path.dirname(audio_folder) if audio_folder else (base_path or os.path.expanduser("~"))
            return True, start_path, {"target": "audio", "type": "folder"}
        elif triggered == "data-config-predictions-browse":
            start_path = base_path or os.path.expanduser("~")
            return True, start_path, {"target": "predictions", "type": "file"}
        elif triggered == "label-output-browse-btn":
            # Start from current labels path or base path
            start_path = os.path.dirname(labels_path) if labels_path else (base_path or os.path.expanduser("~"))
            return True, start_path, {"target": "labels", "type": "file"}
        
        raise PreventUpdate

    @app.callback(
        Output("data-config-spec-folder", "value", allow_duplicate=True),
        Output("data-config-audio-folder", "value", allow_duplicate=True),
        Output("data-config-predictions-file", "value", allow_duplicate=True),
        Output("data-config-spec-info", "children", allow_duplicate=True),
        Output("data-config-audio-info", "children", allow_duplicate=True),
        Output("data-config-predictions-info", "children", allow_duplicate=True),
        Output("data-config-modal", "is_open", allow_duplicate=True),
        Output("folder-browser-modal", "is_open", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Input("folder-browser-confirm", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("data-config-predictions-file", "value"),
        State("data-config-modal", "is_open"),
        State("label-output-input", "value"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def update_path_from_browser(confirm_clicks, selected_path, browse_target, current_spec, current_audio, current_predictions, config_modal_open, current_labels, current_mode):
        """Update the appropriate path field after folder browser selection."""
        if not confirm_clicks or not selected_path:
            raise PreventUpdate
        
        # If we're not in path selection mode (no target), let other callback handle it
        if not browse_target or not browse_target.get("target"):
            raise PreventUpdate
        
        target = browse_target.get("target")
        
        # Helper to count spectrograms
        def count_spectrograms(folder):
            if not folder or not os.path.isdir(folder):
                return 0, []
            count = 0
            exts = set()
            try:
                for f in os.listdir(folder):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in {'.mat', '.npy', '.png', '.jpg'}:
                        count += 1
                        exts.add(ext)
            except Exception:
                pass
            return count, list(exts)
        
        # Helper to count audio
        def count_audio(folder):
            if not folder or not os.path.isdir(folder):
                return 0
            count = 0
            try:
                for f in os.listdir(folder):
                    if os.path.splitext(f)[1].lower() in {'.flac', '.wav', '.mp3'}:
                        count += 1
            except Exception:
                pass
            return count
        
        is_label_mode = current_mode == "label"

        if target == "spectrogram":
            spec_count, spec_exts = count_spectrograms(selected_path)
            spec_info = _create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = _create_info_badge(count_audio(current_audio) > 0, count_audio(current_audio))
            pred_info = _create_predictions_info(current_predictions and os.path.isfile(current_predictions), is_label_mode)
            return selected_path, current_audio, current_predictions, spec_info, audio_info, pred_info, True, False, no_update

        elif target == "audio":
            audio_count = count_audio(selected_path)
            spec_count, spec_exts = count_spectrograms(current_spec)
            spec_info = _create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = _create_info_badge(audio_count > 0, audio_count)
            pred_info = _create_predictions_info(current_predictions and os.path.isfile(current_predictions), is_label_mode)
            return current_spec, selected_path, current_predictions, spec_info, audio_info, pred_info, True, False, no_update

        elif target == "predictions":
            # For predictions/labels, check if it's a directory with the appropriate file
            pred_path = selected_path
            if os.path.isdir(selected_path):
                # Check for both predictions.json and labels.json
                pred_file = os.path.join(selected_path, "predictions.json")
                labels_file = os.path.join(selected_path, "labels.json")
                if is_label_mode and os.path.exists(labels_file):
                    pred_path = labels_file
                elif os.path.exists(pred_file):
                    pred_path = pred_file
                elif os.path.exists(labels_file):
                    pred_path = labels_file

            spec_count, spec_exts = count_spectrograms(current_spec)
            spec_info = _create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = _create_info_badge(count_audio(current_audio) > 0, count_audio(current_audio))
            pred_info = _create_predictions_info(os.path.isfile(pred_path), is_label_mode)
            return current_spec, current_audio, pred_path, spec_info, audio_info, pred_info, True, False, no_update
        
        elif target == "labels":
            # For labels, check if it's a directory with labels.json
            labels_path = selected_path
            if os.path.isdir(selected_path):
                labels_file = os.path.join(selected_path, "labels.json")
                labels_path = labels_file
            
            # Return with no_update for data config fields since we're only updating labels
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, False, labels_path
        
        raise PreventUpdate

    # Note: Dynamic path displays for the label tab are now handled by
    # render_label() and reset_label_displays_on_tab_switch() in main_callbacks.py,
    # which read folder info directly from the label data store's summary.
    # The previous update_dynamic_path_displays callback was removed because it
    # used generic path-building logic that conflicted with the multi-folder
    # popover displays and caused stale values on tab switch.


def _create_info_badge(found: bool, count: int = 0, ext_info: str = "") -> html.Div:
    """Create an info badge showing what was found."""
    if found and count > 0:
        file_word = "file" if count == 1 else "files"
        return html.Div([
            dbc.Badge("✓ Found", color="success", className="me-2"),
            html.Small(f"{count} {file_word}" + (f" ({ext_info})" if ext_info else ""), className="text-muted"),
        ])
    elif found:
        return html.Div([
            dbc.Badge("✓ Found", color="success"),
        ])
    else:
        return html.Div([
            dbc.Badge("Not found", color="warning", className="me-2"),
            html.Small("Optional - enter path or click Browse", className="text-muted"),
        ])


def _create_predictions_info(found: bool, is_label_mode: bool = False) -> html.Div:
    """Create info badge for predictions/labels file."""
    if found:
        return html.Div([
            dbc.Badge("✓ Found", color="success"),
        ])
    else:
        if is_label_mode:
            # In Label mode, the labels file is optional (will be created on save)
            return html.Div([
                dbc.Badge("Not found", color="info", className="me-2"),
                html.Small("Optional - will be created on save", className="text-muted"),
            ])
        else:
            # In Verify mode, predictions file is required
            return html.Div([
                dbc.Badge("Not found", color="warning", className="me-2"),
                html.Small("Required for Verify mode", className="text-muted text-warning"),
            ])
