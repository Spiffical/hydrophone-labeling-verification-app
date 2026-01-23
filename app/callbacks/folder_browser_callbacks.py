"""
Callbacks for the folder browser component.
Handles folder navigation, selection, and loading of data directories.
"""
import os
from dash import Input, Output, State, callback, ctx, no_update, ALL, MATCH
from dash.exceptions import PreventUpdate
from dash import html
import dash_bootstrap_components as dbc

from app.components.folder_browser import get_directory_contents, create_folder_item


def register_folder_browser_callbacks(app):
    """Register all folder browser related callbacks."""
    
    @app.callback(
        Output("folder-browser-modal", "is_open"),
        Output("folder-browser-path-store", "data", allow_duplicate=True),
        Output("path-browse-target-store", "data", allow_duplicate=True),
        Output("folder-browser-selected-store", "data", allow_duplicate=True),
        Input("open-folder-browser", "n_clicks"),
        Input("folder-browser-cancel", "n_clicks"),
        Input("folder-browser-close", "n_clicks"),
        Input("folder-browser-confirm", "n_clicks"),
        State("folder-browser-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_folder_browser(open_clicks, cancel_clicks, close_clicks, confirm_clicks, is_open):
        """Open or close the folder browser modal."""
        triggered = ctx.triggered_id
        if triggered == "open-folder-browser":
            # Reset to home directory and clear target when opening from main Browse button
            return True, os.path.expanduser("~"), None, None
        if triggered in ["folder-browser-cancel", "folder-browser-close", "folder-browser-confirm"]:
            return False, no_update, no_update, no_update
        return is_open, no_update, no_update, no_update

    @app.callback(
        Output("folder-browser-list", "children"),
        Output("folder-browser-current-path", "children"),
        Input("folder-browser-modal", "is_open"),
        Input("folder-browser-path-store", "data"),
        State("path-browse-target-store", "data"),
        prevent_initial_call=False,
    )
    def update_folder_list(is_open, current_path, browse_target):
        """Update the folder list when path changes."""
        if not is_open:
            return no_update, no_update
        
        path = current_path or os.path.expanduser("~")
        
        # Check if we should show files (for predictions file selection)
        show_files = browse_target and browse_target.get("type") == "file"
        
        # Get folder contents
        items = get_directory_contents(path, show_files=show_files)
        
        if not items:
            folder_list = [html.Div("No folders found or permission denied", className="text-muted p-3")]
        else:
            folder_list = []
            for item in items:
                is_file = item.get("is_file", False)
                
                if is_file:
                    # File item (for predictions.json selection)
                    icon = "📄" if item.get("has_data") else "📋"
                    folder_div = html.Div([
                        html.Div([
                            html.Span(icon, className="me-2"),
                            html.Span(item["name"], className="text-primary fw-semibold" if item.get("has_data") else ""),
                            dbc.Badge("Predictions", color="success", className="ms-2", style={"fontSize": "9px"}) if item.get("has_data") else None,
                        ], className="flex-grow-1"),
                        dbc.Button(
                            "Select",
                            id={"type": "folder-select-btn", "path": item["path"]},
                            size="sm",
                            color="success" if item.get("has_data") else "primary",
                        ),
                    ], className="folder-item d-flex justify-content-between align-items-center py-2 px-3 border-bottom bg-light")
                else:
                    # Folder item
                    folder_div = html.Div([
                        html.Div([
                            dbc.Button(
                                [
                                    html.Span("📂" if item.get("has_data") else "📁", className="me-2"),
                                    html.Span(item["name"]),
                                    dbc.Badge("Data", color="success", className="ms-2", style={"fontSize": "9px"}) if item.get("has_data") else None,
                                ],
                                id={"type": "folder-navigate-btn", "path": item["path"]},
                                color="link",
                                className="folder-nav-btn text-start p-0",
                            ),
                        ], className="flex-grow-1"),
                        dbc.Button(
                            "Select",
                            id={"type": "folder-select-btn", "path": item["path"]},
                            size="sm",
                            color="primary" if item.get("has_data") else "secondary",
                            outline=True,
                        ),
                    ], className="folder-item d-flex justify-content-between align-items-center py-2 px-3 border-bottom")
                
                folder_list.append(folder_div)
        
        return folder_list, path

    @app.callback(
        Output("folder-browser-path-store", "data"),
        Input({"type": "folder-navigate-btn", "path": ALL}, "n_clicks"),
        Input("folder-browser-up", "n_clicks"),
        Input("folder-browser-home", "n_clicks"),
        Input("folder-browser-root", "n_clicks"),
        Input("folder-browser-drives", "n_clicks"),
        State("folder-browser-path-store", "data"),
        prevent_initial_call=True,
    )
    def update_browser_path(nav_clicks, up_clicks, home_clicks, root_clicks, drives_clicks, current_path):
        """Update the current browser path."""
        triggered = ctx.triggered_id
        path = current_path or os.path.expanduser("~")
        
        if triggered == "folder-browser-home":
            return os.path.expanduser("~")
        elif triggered == "folder-browser-root":
            return "/"
        elif triggered == "folder-browser-drives":
            # Cross-platform drive/mount detection
            # WSL: /mnt contains Windows drives
            if os.path.exists("/mnt/c"):
                return "/mnt"
            # macOS: /Volumes contains mounted drives
            elif os.path.exists("/Volumes"):
                return "/Volumes"
            # Linux: /media or /mnt for mounted drives
            elif os.path.exists("/media"):
                return "/media"
            elif os.path.exists("/mnt"):
                return "/mnt"
            # Fallback to root
            return "/"
        elif triggered == "folder-browser-up":
            parent = os.path.dirname(path)
            return parent if parent and parent != path else path
        elif isinstance(triggered, dict) and triggered.get("type") == "folder-navigate-btn":
            return triggered.get("path", path)
        
        return path

    @app.callback(
        Output("folder-browser-selected-store", "data"),
        Output("folder-browser-selected", "children"),
        Output("folder-browser-confirm", "disabled"),
        Input({"type": "folder-select-btn", "path": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def select_folder(n_clicks_list):
        """Handle folder selection."""
        if not n_clicks_list or not any(n_clicks_list):
            raise PreventUpdate
        
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or "path" not in triggered:
            raise PreventUpdate
        
        selected_path = triggered["path"]
        # Show just the last part of the path for display
        display_name = os.path.basename(selected_path) or selected_path
        return selected_path, display_name, False

    # Note: The actual loading is handled by data_config_callbacks.py
    # which opens a configuration modal after folder selection
