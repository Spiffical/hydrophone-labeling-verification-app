"""Small UI display helpers for modal and cards."""

from dash import html
import dash_bootstrap_components as dbc


def create_folder_display(display_text, folders_list, data_root, popover_id):
    """Create a folder display — hoverable popover if multiple folders, plain text if single."""
    if folders_list and len(folders_list) > 1:
        relative_paths = []
        for folder in folders_list:
            if data_root and folder.startswith(data_root):
                relative_paths.append(folder[len(data_root):].lstrip("/"))
            else:
                relative_paths.append(folder)
        folder_items = [html.Div(path, className="mono-muted small") for path in relative_paths]
        return html.Div(
            [
                html.Span(
                    display_text,
                    id=popover_id,
                    style={"cursor": "pointer", "textDecoration": "underline", "color": "var(--link)"},
                ),
                dbc.Popover(
                    dbc.PopoverBody(
                        html.Div(folder_items, style={"maxHeight": "200px", "overflowY": "auto"})
                    ),
                    target=popover_id,
                    trigger="hover",
                    placement="bottom",
                ),
            ]
        )
    return display_text

