"""
Callbacks for the data configuration panel.
Handles data structure detection, manual path overrides, and loading.
"""
import os
import re
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
        Output("predictions-files-store", "data"),
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
            return (
                False,
                no_update,  # data-discovery-store
                no_update,  # structure type
                no_update,  # structure message
                no_update,  # spec folder
                no_update,  # audio folder
                no_update,  # predictions file
                no_update,  # predictions-files-store
                no_update,  # spec info
                no_update,  # audio info
                no_update,  # predictions info
                no_update,  # predictions label
                no_update,  # hierarchy detail
                no_update,  # hierarchy toggle
                no_update,  # labels recommendation
                no_update,  # spec multi
                no_update,  # audio multi
                no_update,  # spec single container
                no_update,  # audio single container
                no_update,  # predictions multi
                no_update,  # predictions single container
                {"display": "none"},
            )

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
        if not is_label_mode and not discovery.get("predictions_file"):
            subfolder_predictions_count = discovery.get("subfolder_predictions_count", 0)
            if subfolder_predictions_count > 0:
                file_word = "file" if subfolder_predictions_count == 1 else "files"
                predictions_info = html.Div([
                    dbc.Badge("Found in subfolders", color="info", className="me-2"),
                    html.Small(f"{subfolder_predictions_count} predictions.json {file_word} detected", className="text-muted"),
                ])

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

        # Create multi-predictions display if subfolder files found
        predictions_locations = discovery.get("subfolder_predictions_locations", [])
        if is_label_mode:
            predictions_locations = discovery.get("subfolder_labels_locations", [])

        has_subfolder_predictions = len(predictions_locations) > 0
        predictions_entries = []
        predictions_multi = html.Div()
        if has_subfolder_predictions:
            file_type = "labels" if is_label_mode else "predictions"
            if is_label_mode:
                predictions_multi = create_multi_file_display(predictions_locations, selected_path, file_type)
                predictions_label = "Labels Files"
            else:
                predictions_entries = _build_predictions_entries(predictions_locations, selected_path)
                predictions_multi = create_multi_file_display(
                    predictions_entries, selected_path, file_type, editable=True
                )
                predictions_label = "Predictions Files"

        # Show/hide single input vs multi-folder display
        show_single = {"display": "block"} if not is_hierarchical else {"display": "none"}
        hide_single = {"display": "none"} if is_hierarchical else {"display": "block"}
        
        # Hide global override when subfolder predictions are present
        show_predictions_single = {"display": "none"} if (has_subfolder_predictions and not is_label_mode) else {"display": "block"}

        return (
            True,  # Open modal
            discovery,  # Store discovery results
            structure_type,
            discovery.get("message", ""),
            discovery.get("spectrogram_folder") or "",
            discovery.get("audio_folder") or "",
            predictions_file_value,
            predictions_entries,
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

    @app.callback(
        Output("data-root-path-store", "data"),
        Input("folder-browser-confirm", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        prevent_initial_call=True,
    )
    def update_data_root_path(confirm_clicks, selected_path, browse_target):
        """Persist the base data directory without being overridden by file selection."""
        if not confirm_clicks or not selected_path:
            raise PreventUpdate
        if browse_target and browse_target.get("target"):
            raise PreventUpdate
        return selected_path

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
        State("predictions-files-store", "data"),
        State({"type": "predictions-file-input", "index": ALL}, "value"),
        State({"type": "predictions-file-input", "index": ALL}, "id"),
        State("data-root-path-store", "data"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def load_data_from_config(
        load_clicks,
        discovery,
        spec_folder,
        audio_folder,
        predictions_file,
        predictions_entries,
        predictions_values,
        predictions_ids,
        base_path,
        config,
        current_mode,
    ):
        """Load data based on configuration panel settings."""
        if not load_clicks:
            raise PreventUpdate

        if not base_path:
            base_path = (config or {}).get("data", {}).get("data_dir")
        
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

        predictions_overrides = []
        if predictions_entries and predictions_ids:
            entry_map = {entry.get("index"): entry for entry in predictions_entries}
            for entry_id, value in zip(predictions_ids, predictions_values or []):
                index = entry_id.get("index") if isinstance(entry_id, dict) else None
                entry = entry_map.get(index)
                if not entry or not value:
                    continue
                scope = entry.get("scope") or {}
                predictions_overrides.append({
                    "date": scope.get("date"),
                    "device": scope.get("device"),
                    "path": value,
                })

        config["data"]["predictions_overrides"] = predictions_overrides or None
        
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
            True,  # Keep modal open until data finishes loading
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
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        State("data-load-trigger-store", "data"),
        prevent_initial_call=True,
    )
    def hide_loading_overlay_on_data_load(label_ready, verify_ready, explore_ready, load_trigger):
        """Hide the loading overlay once the UI has rendered for the triggered load."""
        trigger_ts = load_trigger.get("timestamp") if isinstance(load_trigger, dict) else None
        if trigger_ts:
            if (label_ready or {}).get("timestamp") == trigger_ts:
                return {"display": "none"}
            if (verify_ready or {}).get("timestamp") == trigger_ts:
                return {"display": "none"}
            if (explore_ready or {}).get("timestamp") == trigger_ts:
                return {"display": "none"}
            raise PreventUpdate
        if label_ready or verify_ready or explore_ready:
            return {"display": "none"}
        raise PreventUpdate

    @app.callback(
        Output("data-config-modal", "is_open", allow_duplicate=True),
        Input("label-ui-ready-store", "data"),
        Input("verify-ui-ready-store", "data"),
        Input("explore-ui-ready-store", "data"),
        State("data-load-trigger-store", "data"),
        State("data-config-modal", "is_open"),
        prevent_initial_call=True,
    )
    def close_data_config_on_data_load(label_ready, verify_ready, explore_ready, load_trigger, is_open):
        """Close the data config modal once the UI finishes rendering for the triggered load."""
        if not is_open or not isinstance(load_trigger, dict):
            raise PreventUpdate

        trigger_ts = load_trigger.get("timestamp")
        if (label_ready or {}).get("timestamp") == trigger_ts:
            return False
        if (verify_ready or {}).get("timestamp") == trigger_ts:
            return False
        if (explore_ready or {}).get("timestamp") == trigger_ts:
            return False

        raise PreventUpdate
    
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
        Input({"type": "predictions-file-browse", "index": ALL}, "n_clicks"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("label-output-input", "value"),
        State("data-root-path-store", "data"),
        State("predictions-files-store", "data"),
        prevent_initial_call=True,
    )
    def open_path_browser(
        spec_clicks,
        audio_clicks,
        predictions_clicks,
        labels_clicks,
        predictions_multi_clicks,
        spec_folder,
        audio_folder,
        labels_path,
        base_path,
        predictions_entries,
    ):
        """Open folder browser for path selection."""
        triggered = ctx.triggered_id
        if not ctx.triggered:
            raise PreventUpdate

        triggered_value = ctx.triggered[0].get("value")
        if isinstance(triggered_value, list):
            if not any(v for v in triggered_value):
                raise PreventUpdate
        elif not triggered_value:
            raise PreventUpdate
        
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
        elif isinstance(triggered, dict) and triggered.get("type") == "predictions-file-browse":
            index = triggered.get("index")
            start_path = base_path or os.path.expanduser("~")
            if predictions_entries:
                for entry in predictions_entries:
                    if entry.get("index") == index and entry.get("path"):
                        start_path = os.path.dirname(entry["path"])
                        break
            return True, start_path, {"target": "predictions", "type": "file", "index": index}
        
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
        Output({"type": "predictions-file-input", "index": ALL}, "value"),
        Input("folder-browser-confirm", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("data-config-predictions-file", "value"),
        State("data-config-modal", "is_open"),
        State("label-output-input", "value"),
        State("mode-tabs", "data"),
        State({"type": "predictions-file-input", "index": ALL}, "value"),
        State({"type": "predictions-file-input", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def update_path_from_browser(
        confirm_clicks,
        selected_path,
        browse_target,
        current_spec,
        current_audio,
        current_predictions,
        config_modal_open,
        current_labels,
        current_mode,
        current_pred_values,
        current_pred_ids,
    ):
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
            return selected_path, current_audio, current_predictions, spec_info, audio_info, pred_info, True, False, no_update, no_update

        elif target == "audio":
            audio_count = count_audio(selected_path)
            spec_count, spec_exts = count_spectrograms(current_spec)
            spec_info = _create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = _create_info_badge(audio_count > 0, audio_count)
            pred_info = _create_predictions_info(current_predictions and os.path.isfile(current_predictions), is_label_mode)
            return current_spec, selected_path, current_predictions, spec_info, audio_info, pred_info, True, False, no_update, no_update

        elif target == "predictions":
            if browse_target and browse_target.get("index") is not None:
                updated_values = list(current_pred_values or [])
                updated_ids = list(current_pred_ids or [])
                for i, item_id in enumerate(updated_ids):
                    if item_id.get("index") == browse_target.get("index"):
                        if i < len(updated_values):
                            updated_values[i] = selected_path
                        else:
                            updated_values.append(selected_path)
                        break
                return (
                    current_spec,
                    current_audio,
                    current_predictions,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    False,
                    no_update,
                    updated_values,
                )
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
            return current_spec, current_audio, pred_path, spec_info, audio_info, pred_info, True, False, no_update, no_update
        
        elif target == "labels":
            # For labels, check if it's a directory with labels.json
            labels_path = selected_path
            if os.path.isdir(selected_path):
                labels_file = os.path.join(selected_path, "labels.json")
                labels_path = labels_file
            
            # Return with no_update for data config fields since we're only updating labels
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, False, labels_path, no_update
        
        raise PreventUpdate

    # Note: Dynamic path displays for the label tab are now handled by
    # render_label() and reset_label_displays_on_tab_switch() in main_callbacks.py,
    # which read folder info directly from the label data store's summary.
    # The previous update_dynamic_path_displays callback was removed because it
    # used generic path-building logic that conflicted with the multi-folder
    # popover displays and caused stale values on tab switch.


def _build_predictions_entries(predictions_locations: list, base_path: str) -> list:
    """Build editable entries for predictions files in subfolders."""
    entries = []
    if not predictions_locations:
        return entries

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for idx, file_path in enumerate(predictions_locations):
        rel_path = file_path
        if base_path:
            try:
                rel_path = os.path.relpath(file_path, base_path)
            except ValueError:
                rel_path = file_path

        scope = {"date": None, "device": None}
        label = rel_path

        if not os.path.isabs(rel_path) and not rel_path.startswith(".."):
            parts = rel_path.split(os.sep)
            if parts and date_pattern.match(parts[0]):
                scope["date"] = parts[0]
                if len(parts) > 2:
                    scope["device"] = parts[1]
            elif parts:
                scope["device"] = parts[0]

            if scope["date"] and scope["device"]:
                label = f"{scope['date']} / {scope['device']}"
            elif scope["date"]:
                label = scope["date"]
            elif scope["device"]:
                label = scope["device"]

        entries.append({
            "index": idx,
            "path": file_path,
            "relative_path": rel_path,
            "scope": scope,
            "label": label,
        })

    return entries


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
