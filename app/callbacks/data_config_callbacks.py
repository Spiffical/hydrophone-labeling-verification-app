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
        Input("folder-browser-confirm", "n_clicks"),
        Input("data-config-cancel", "n_clicks"),
        Input("data-config-close", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        prevent_initial_call=True,
    )
    def open_data_config(confirm_clicks, cancel_clicks, close_clicks, selected_path, browse_target):
        """Open data config modal after folder selection."""
        triggered = ctx.triggered_id
        
        if triggered in ["data-config-cancel", "data-config-close"]:
            return False, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        
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
        predictions_info = _create_predictions_info(bool(discovery.get("predictions_file")))
        
        return (
            True,  # Open modal
            discovery,  # Store discovery results
            structure_type,
            discovery.get("message", ""),
            discovery.get("spectrogram_folder") or "",
            discovery.get("audio_folder") or "",
            discovery.get("predictions_file") or "",
            spec_info,
            audio_info,
            predictions_info,
        )
    
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
        Output("label-output-input", "value"),
        Output("data-load-trigger-store", "data"),
        Input("data-config-load", "n_clicks"),
        State("data-discovery-store", "data"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("data-config-predictions-file", "value"),
        State("folder-browser-selected-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def load_data_from_config(load_clicks, discovery, spec_folder, audio_folder, predictions_file, base_path, config):
        """Load data based on configuration panel settings."""
        if not load_clicks:
            raise PreventUpdate
        
        # Update config with paths
        if "data" not in config:
            config["data"] = {}
        
        config["data"]["data_dir"] = base_path
        config["data"]["spectrogram_folder"] = spec_folder or None
        config["data"]["audio_folder"] = audio_folder or None
        config["data"]["predictions_file"] = predictions_file or None
        config["data"]["structure_type"] = discovery.get("structure_type") if discovery else "flat"
        
        structure_type = discovery.get("structure_type") if discovery else "flat"
        
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
            date_value = dates[0] if dates else None  # Default to first specific date
            device_value = devices[0] if devices else None  # Default to first specific device
        elif structure_type == "device_only":
            devices = discovery.get("devices", [])
            # Add "All" option for devices
            device_options = [{"label": "All Devices", "value": "__all__"}] + [{"label": d, "value": d} for d in devices]
            device_value = devices[0] if devices else None
        else:
            # Flat or unknown - use special marker to indicate direct loading
            date_options = [{"label": "(Direct)", "value": "__flat__"}]
            date_value = "__flat__"
        
        display_path = base_path if base_path else "Not selected"
        
        # Prepare Label tab display values  
        spec_display = spec_folder or base_path or "Not set"
        audio_display = audio_folder or "Not set"
        # For label mode output, use labels.json in the data folder, NOT predictions.json
        if spec_folder:
            output_display = os.path.join(spec_folder, "labels.json")
        elif base_path:
            output_display = os.path.join(base_path, "labels.json")
        else:
            output_display = "Not set"
        
        # Create a trigger value (timestamp) to signal that config is updated and data should be loaded
        import time
        trigger_value = time.time()
        
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
    
    @app.callback(
        Output("verify-predictions-warning", "is_open"),
        Input("mode-tabs", "value"),
        Input("data-store", "data"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def show_predictions_warning(mode, loaded_data, config):
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
        Output("mode-tabs", "value", allow_duplicate=True),
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
        prevent_initial_call=True,
    )
    def update_path_from_browser(confirm_clicks, selected_path, browse_target, current_spec, current_audio, current_predictions, config_modal_open, current_labels):
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
        
        if target == "spectrogram":
            spec_count, spec_exts = count_spectrograms(selected_path)
            spec_info = _create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = _create_info_badge(count_audio(current_audio) > 0, count_audio(current_audio))
            pred_info = _create_predictions_info(current_predictions and os.path.isfile(current_predictions))
            return selected_path, current_audio, current_predictions, spec_info, audio_info, pred_info, True, False, no_update
        
        elif target == "audio":
            audio_count = count_audio(selected_path)
            spec_count, spec_exts = count_spectrograms(current_spec)
            spec_info = _create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = _create_info_badge(audio_count > 0, audio_count)
            pred_info = _create_predictions_info(current_predictions and os.path.isfile(current_predictions))
            return current_spec, selected_path, current_predictions, spec_info, audio_info, pred_info, True, False, no_update
        
        elif target == "predictions":
            # For predictions, check if it's a directory with predictions.json
            pred_path = selected_path
            if os.path.isdir(selected_path):
                pred_file = os.path.join(selected_path, "predictions.json")
                if os.path.exists(pred_file):
                    pred_path = pred_file
            
            spec_count, spec_exts = count_spectrograms(current_spec)
            spec_info = _create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = _create_info_badge(count_audio(current_audio) > 0, count_audio(current_audio))
            pred_info = _create_predictions_info(os.path.isfile(pred_path))
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


def _create_info_badge(found: bool, count: int = 0, ext_info: str = "") -> html.Div:
    """Create an info badge showing what was found."""
    if found and count > 0:
        return html.Div([
            dbc.Badge("✓ Found", color="success", className="me-2"),
            html.Small(f"{count} files" + (f" ({ext_info})" if ext_info else ""), className="text-muted"),
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


def _create_predictions_info(found: bool) -> html.Div:
    """Create info badge for predictions file."""
    if found:
        return html.Div([
            dbc.Badge("✓ Found", color="success"),
        ])
    else:
        return html.Div([
            dbc.Badge("Not found", color="warning", className="me-2"),
            html.Small("Required for Verify mode", className="text-muted text-warning"),
        ])
