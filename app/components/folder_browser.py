"""
Server-side folder browser component.
Allows users to navigate the local file system and select a data directory.
"""
import os
from dash import html, dcc
import dash_bootstrap_components as dbc


def get_directory_contents(path: str, show_files: bool = False) -> list:
    """
    Get the contents of a directory.
    Returns folders by default, optionally including JSON files if show_files=True.
    Returns a list of dicts with name, path, is_dir, and has_data.
    """
    try:
        if not os.path.exists(path):
            return []
        
        # Skip slow data structure checks on mounted drives (network filesystems)
        # These checks involve multiple stat() calls per folder which are slow on network drives
        skip_data_check = _is_slow_filesystem(path)
        
        items = []
        for name in sorted(os.listdir(path)):
            full_path = os.path.join(path, name)
            
            # Skip hidden files/folders
            if name.startswith('.'):
                continue
            
            try:
                if os.path.isdir(full_path):
                    # Check if this looks like a data directory (skip for slow filesystems)
                    has_data = False if skip_data_check else _check_for_data_structure(full_path)
                    items.append({
                        "name": name,
                        "path": full_path,
                        "is_dir": True,
                        "has_data": has_data,
                    })
                elif show_files and name.lower().endswith('.json'):
                    # Include JSON files when in file selection mode
                    # Only mark predictions.json specially, not labels.json
                    is_predictions = "predictions" in name.lower()
                    items.append({
                        "name": name,
                        "path": full_path,
                        "is_dir": False,
                        "is_file": True,
                        "has_data": is_predictions,
                    })
            except (PermissionError, OSError):
                # Skip individual items we can't access
                continue
        return items
    except PermissionError:
        return []
    except Exception:
        return []


def _is_slow_filesystem(path: str) -> bool:
    """Check if a path is on a potentially slow filesystem (mounted drives, network shares)."""
    slow_prefixes = [
        '/mnt/',      # WSL mounted Windows drives and Linux mounts
        '/Volumes/',  # macOS mounted drives
        '/media/',    # Linux removable media
        '/run/user/', # Linux user mounts (gvfs etc.)
    ]
    return any(path.startswith(prefix) for prefix in slow_prefixes)


def _check_for_data_structure(path: str) -> bool:
    """Check if a directory contains the expected DATE/DEVICE data structure."""
    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                # Check if it looks like a date folder (YYYY-MM-DD)
                if len(item) == 10 and item[4] == '-' and item[7] == '-':
                    return True
                # Or check if it contains predictions.json
                if os.path.exists(os.path.join(item_path, "predictions.json")):
                    return True
        # Also check current directory for predictions.json
        if os.path.exists(os.path.join(path, "predictions.json")):
            return True
    except Exception:
        pass
    return False


def create_folder_item(item: dict, level: int = 0) -> html.Div:
    """Create a single folder item in the browser."""
    indent = level * 20
    
    icon = "📁" if not item.get("has_data") else "📂"
    badge = None
    if item.get("has_data"):
        badge = dbc.Badge("Data", color="success", className="ms-2", style={"fontSize": "10px"})
    
    return html.Div([
        html.Div([
            html.Span(icon, className="me-2"),
            html.Span(item["name"], className="folder-name"),
            badge,
        ], className="folder-item-content"),
        dbc.Button(
            "Select",
            id={"type": "select-folder-btn", "path": item["path"]},
            size="sm",
            color="primary",
            outline=True,
            className="folder-select-btn",
        ),
    ], className="folder-item d-flex justify-content-between align-items-center",
       style={"paddingLeft": f"{indent + 10}px"})


def create_folder_browser_modal() -> dbc.Modal:
    """Create the folder browser modal component."""
    home_dir = os.path.expanduser("~")
    
    return dbc.Modal([
        dbc.ModalHeader([
            dbc.ModalTitle("Select Data Directory", id="folder-browser-title"),
            dbc.Button("×", id="folder-browser-close", className="btn-close ms-auto"),
        ], close_button=False),
        dbc.ModalBody([
            # Current path display
            html.Div([
                html.Label("Current Location:", className="text-muted small"),
                html.Div([
                    dbc.Button(
                        "⬆ Up",
                        id="folder-browser-up",
                        size="sm",
                        color="secondary",
                        outline=True,
                        className="me-2",
                    ),
                    html.Span(id="folder-browser-current-path", className="mono-muted"),
                ], className="d-flex align-items-center"),
            ], className="mb-3"),
            
            # Quick access buttons
            html.Div([
                html.Label("Quick Access:", className="text-muted small mb-2 d-block"),
                dbc.ButtonGroup([
                    dbc.Button("🏠 Home", id="folder-browser-home", size="sm", outline=True, color="secondary"),
                    dbc.Button("📁 Root", id="folder-browser-root", size="sm", outline=True, color="secondary"),
                    dbc.Button("💾 Drives", id="folder-browser-drives", size="sm", outline=True, color="secondary"),
                ], className="mb-3"),
            ]),
            
            # Folder list
            html.Div([
                html.Label("Folders:", id="folder-browser-list-label", className="text-muted small mb-2 d-block"),
                dcc.Loading(
                    html.Div(id="folder-browser-list", className="folder-list"),
                    type="circle",
                ),
            ]),
        ], className="folder-browser-body"),
        dbc.ModalFooter([
            html.Div([
                html.Label("Selected:", className="text-muted small me-2"),
                html.Span(id="folder-browser-selected", className="fw-semibold"),
            ], className="me-auto"),
            dbc.Button("Cancel", id="folder-browser-cancel", color="secondary", outline=True),
            dbc.Button("Load Directory", id="folder-browser-confirm", color="primary", disabled=True),
        ]),
    ], id="folder-browser-modal", size="lg", is_open=False, centered=True)


def create_browse_button() -> dbc.Button:
    """Create the button that opens the folder browser."""
    return dbc.Button(
        [html.I(className="bi bi-folder2-open me-2"), "Browse"],
        id="open-folder-browser",
        color="secondary",
        outline=True,
        size="sm",
        className="browse-folder-btn",
    )
