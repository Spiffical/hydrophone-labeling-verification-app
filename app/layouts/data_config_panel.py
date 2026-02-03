"""
Data configuration panel component.
Shows detected data structure and allows manual override of paths.
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_data_config_modal() -> dbc.Modal:
    """Create the data configuration modal."""
    return dbc.Modal([
        dbc.ModalHeader([
            dbc.ModalTitle("Data Configuration"),
            dbc.Button("×", id="data-config-close", className="btn-close ms-auto"),
        ], close_button=False),
        dbc.ModalBody([
            # Structure info with expandable hierarchy detail
            html.Div([
                html.Div([
                    html.Span("Structure: ", className="text-muted"),
                    html.Span(id="data-config-structure-type", className="fw-semibold"),
                ]),
                html.Small(id="data-config-structure-message", className="text-muted"),

                # Collapsible hierarchy detail section
                html.Div([
                    dbc.Button(
                        [html.I(className="bi bi-chevron-down me-1", id="hierarchy-toggle-icon"),
                         "Show Details"],
                        id="data-config-hierarchy-toggle",
                        color="link",
                        size="sm",
                        className="p-0 mt-2",
                    ),
                    dbc.Collapse(
                        html.Div(id="data-config-hierarchy-detail", className="hierarchy-scroll-container mt-2"),
                        id="data-config-hierarchy-collapse",
                        is_open=False,
                    ),
                ], id="hierarchy-toggle-container", style={"display": "none"}),
            ], className="mb-3 p-3 bg-light rounded structure-info-section"),

            # Labels/Predictions location recommendation
            html.Div(id="data-config-labels-recommendation", className="mb-3"),

            # Spectrogram folder section
            html.Div([
                html.Label("Spectrogram Folders", className="fw-semibold mb-1"),
                # Multi-folder summary (shown for hierarchical structures)
                html.Div(id="data-config-spec-multi", className="multi-folder-summary"),
                # Single folder input (hidden for hierarchical, shown for flat)
                html.Div([
                    dbc.InputGroup([
                        dbc.Input(
                            id="data-config-spec-folder",
                            type="text",
                            placeholder="Path to spectrogram files",
                            className="mono-muted",
                        ),
                        dbc.Button(
                            html.I(className="bi bi-folder2-open"),
                            id="data-config-spec-browse",
                            color="secondary",
                            outline=True,
                        ),
                    ]),
                ], id="data-config-spec-single-container"),
                html.Div(id="data-config-spec-info", className="mt-1"),
            ], className="mb-3"),

            # Audio folder section
            html.Div([
                html.Label("Audio Folders", className="fw-semibold mb-1"),
                # Multi-folder summary (shown for hierarchical structures)
                html.Div(id="data-config-audio-multi", className="multi-folder-summary"),
                # Single folder input (hidden for hierarchical, shown for flat)
                html.Div([
                    dbc.InputGroup([
                        dbc.Input(
                            id="data-config-audio-folder",
                            type="text",
                            placeholder="Path to audio files (optional)",
                            className="mono-muted",
                        ),
                        dbc.Button(
                            html.I(className="bi bi-folder2-open"),
                            id="data-config-audio-browse",
                            color="secondary",
                            outline=True,
                        ),
                    ]),
                ], id="data-config-audio-single-container"),
                html.Div(id="data-config-audio-info", className="mt-1"),
            ], className="mb-3"),
            
            # Predictions/Labels file (label changes based on mode)
            html.Div([
                html.Label(id="data-config-predictions-label", className="fw-semibold mb-1"),
                # Multi-file summary (shown when multiple predictions files found)
                html.Div(id="data-config-predictions-multi", className="multi-folder-summary"),
                # Single file input (hidden when multiple files are shown in multi display)
                html.Div([
                    dbc.InputGroup([
                        dbc.Input(
                            id="data-config-predictions-file",
                            type="text",
                            placeholder="Path to predictions.json or labels.json",
                            className="mono-muted",
                        ),
                        dbc.Button(
                            html.I(className="bi bi-file-earmark"),
                            id="data-config-predictions-browse",
                            color="secondary",
                            outline=True,
                        ),
                    ]),
                ], id="data-config-predictions-single-container"),
                html.Div(id="data-config-predictions-info", className="mt-1"),
            ], className="mb-3"),
        ], className="data-config-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="data-config-cancel", color="secondary", outline=True),
            dbc.Button("Load Data", id="data-config-load", color="primary"),
        ]),
    ], id="data-config-modal", size="lg", is_open=False, centered=True)


def create_config_info_badge(found: bool, count: int = 0, ext_info: str = "") -> html.Div:
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
            html.Small("Optional - click Browse to select", className="text-muted"),
        ])


def create_predictions_warning() -> dbc.Alert:
    """Create a warning banner for missing predictions."""
    return dbc.Alert([
        html.H5([
            html.I(className="bi bi-exclamation-triangle-fill me-2"),
            "No Predictions File Found"
        ], className="alert-heading"),
        html.P([
            "Verify mode requires ML predictions to compare with expert labels. ",
            "You can still use Label mode to annotate spectrograms manually."
        ]),
        html.Hr(),
        html.Div([
            dbc.Button(
                [html.I(className="bi bi-file-earmark-plus me-2"), "Select Predictions File"],
                id="verify-select-predictions-btn",
                color="warning",
                className="me-2",
            ),
            dbc.Button(
                "Continue in Label Mode",
                id="verify-continue-label-btn",
                color="secondary",
                outline=True,
            ),
        ]),
    ], id="verify-predictions-warning", color="warning", is_open=False, dismissable=True)


def create_hierarchy_tree(discovery: dict) -> html.Div:
    """
    Create a tree view of the data hierarchy.

    Args:
        discovery: Discovery result dict with hierarchy_detail or device_detail

    Returns:
        html.Div with the hierarchy tree
    """
    structure_type = discovery.get("structure_type", "unknown")
    children = []

    if structure_type == "hierarchical":
        hierarchy_detail = discovery.get("hierarchy_detail", {})
        total_specs = 0

        for date in sorted(hierarchy_detail.keys(), reverse=True):
            date_children = []
            date_spec_count = 0

            for device, info in sorted(hierarchy_detail[date].items()):
                spec_count = info.get("spectrogram_count", 0)
                audio_count = info.get("audio_count", 0)
                has_labels = info.get("has_labels_json", False)
                has_predictions = info.get("has_predictions_json", False)

                date_spec_count += spec_count
                total_specs += spec_count

                # Build device info line with proper singular/plural
                spec_word = "spectrogram" if spec_count == 1 else "spectrograms"
                info_parts = [f"{spec_count} {spec_word}"]
                if audio_count > 0:
                    audio_word = "audio file" if audio_count == 1 else "audio files"
                    info_parts.append(f"{audio_count} {audio_word}")

                badges = []
                if has_labels:
                    badges.append(dbc.Badge("labels.json", color="success", className="ms-1 badge-sm"))
                if has_predictions:
                    badges.append(dbc.Badge("predictions.json", color="info", className="ms-1 badge-sm"))

                date_children.append(
                    html.Div([
                        html.I(className="bi bi-hdd me-1 text-muted"),
                        html.Span(device, className="hierarchy-device-name"),
                        html.Span(f": {', '.join(info_parts)}", className="hierarchy-device-info text-muted ms-1"),
                        *badges,
                    ], className="hierarchy-device")
                )

            children.append(
                html.Div([
                    html.Div([
                        html.I(className="bi bi-calendar3 me-1"),
                        html.Span(date, className="hierarchy-date-name fw-semibold"),
                        html.Span(f" ({date_spec_count} total)", className="text-muted ms-1"),
                    ], className="hierarchy-date"),
                    html.Div(date_children, className="hierarchy-devices ms-3"),
                ], className="hierarchy-date-section mb-2")
            )

    elif structure_type == "device_only":
        device_detail = discovery.get("device_detail", {})
        total_specs = 0

        for device, info in sorted(device_detail.items()):
            spec_count = info.get("spectrogram_count", 0)
            audio_count = info.get("audio_count", 0)
            has_labels = info.get("has_labels_json", False)
            has_predictions = info.get("has_predictions_json", False)

            total_specs += spec_count

            # Use proper singular/plural
            spec_word = "spectrogram" if spec_count == 1 else "spectrograms"
            info_parts = [f"{spec_count} {spec_word}"]
            if audio_count > 0:
                audio_word = "audio file" if audio_count == 1 else "audio files"
                info_parts.append(f"{audio_count} {audio_word}")

            badges = []
            if has_labels:
                badges.append(dbc.Badge("labels.json", color="success", className="ms-1 badge-sm"))
            if has_predictions:
                badges.append(dbc.Badge("predictions.json", color="info", className="ms-1 badge-sm"))

            children.append(
                html.Div([
                    html.I(className="bi bi-hdd me-1"),
                    html.Span(device, className="hierarchy-device-name fw-semibold"),
                    html.Span(f": {', '.join(info_parts)}", className="hierarchy-device-info text-muted ms-1"),
                    *badges,
                ], className="hierarchy-device mb-1")
            )

    if not children:
        return html.Div([
            html.Small("No detailed structure information available", className="text-muted")
        ])

    return html.Div(children, className="hierarchy-tree")


def create_multi_folder_display(folders: list, folder_type: str = "spectrogram") -> html.Div:
    """
    Create a display showing multiple folders found.

    Args:
        folders: List of dicts with 'path', 'count', and optionally 'date'/'device'
        folder_type: "spectrogram" or "audio"

    Returns:
        html.Div with folder summary and scrollable list
    """
    if not folders:
        return html.Div()

    total_count = sum(f.get("count", 0) for f in folders)
    folder_count = len(folders)

    icon = "bi-images" if folder_type == "spectrogram" else "bi-music-note-list"
    
    # Use proper singular/plural
    folder_word = "folder" if folder_count == 1 else "folders"
    file_word = "file" if total_count == 1 else "files"

    # Create folder list items
    folder_items = []
    for f in folders:
        path_display = f.get("relative_path", f.get("path", ""))
        count = f.get("count", 0)
        item_file_word = "file" if count == 1 else "files"

        folder_items.append(
            html.Div([
                html.I(className="bi bi-folder2 me-2 text-muted"),
                html.Span(path_display, className="mono-muted folder-path"),
                html.Span(f" ({count} {item_file_word})", className="text-muted ms-1"),
            ], className="multi-folder-item")
        )

    return html.Div([
        # Summary header
        html.Div([
            dbc.Badge(f"{folder_count} {folder_word}", color="info", className="me-2"),
            html.I(className=f"bi {icon} me-1"),
            html.Span(f"{total_count} total {folder_type} {file_word}", className="text-muted"),
        ], className="multi-folder-header mb-2"),
        # Scrollable folder list
        html.Div(folder_items, className="multi-folder-list"),
    ], className="multi-folder-container")


def create_multi_file_display(
    files: list,
    base_path: str = "",
    file_type: str = "predictions",
    editable: bool = False,
) -> html.Div:
    """
    Create a display showing multiple files found (e.g., predictions.json files).

    Args:
        files: List of absolute file paths
        base_path: Base path to calculate relative paths from
        file_type: "predictions" or "labels"

    Returns:
        html.Div with file summary and scrollable list
    """
    import os
    
    if not files:
        return html.Div()

    file_count = len(files)
    icon = "bi-file-earmark-text" if file_type == "predictions" else "bi-file-earmark-check"
    
    # Use proper singular/plural
    file_word = "file" if file_count == 1 else "files"

    # Create file list items
    file_items = []
    if editable and file_type == "predictions":
        for entry in files:
            rel_path = entry.get("relative_path") or entry.get("path", "")
            label = entry.get("label") or rel_path
            index = entry.get("index")
            file_items.append(
                html.Div([
                    html.Div([
                        html.Span(label, className="fw-semibold"),
                        html.Small(rel_path, className="text-muted d-block mono-muted"),
                    ], className="multi-file-editor-label"),
                    dbc.InputGroup([
                        dbc.Input(
                            id={"type": "predictions-file-input", "index": index},
                            type="text",
                            value=entry.get("path") or "",
                            placeholder="Path to predictions.json",
                            className="mono-muted",
                        ),
                        dbc.Button(
                            html.I(className="bi bi-file-earmark"),
                            id={"type": "predictions-file-browse", "index": index},
                            color="secondary",
                            outline=True,
                        ),
                    ], className="mt-1"),
                ], className="multi-file-editor-item")
            )
    else:
        for file_path in files:
            # Show relative path if possible
            if base_path:
                try:
                    rel_path = os.path.relpath(file_path, base_path)
                except ValueError:
                    rel_path = file_path
            else:
                rel_path = file_path

            file_items.append(
                html.Div([
                    html.I(className=f"bi {icon} me-2 text-muted"),
                    html.Span(rel_path, className="mono-muted folder-path"),
                ], className="multi-folder-item")
            )

    return html.Div([
        # Summary header
        html.Div([
            dbc.Badge(f"{file_count} {file_word}", color="info", className="me-2"),
            html.I(className=f"bi {icon} me-1"),
            html.Span(f"{file_type}.json {file_word} found", className="text-muted"),
        ], className="multi-folder-header mb-2"),
        # Scrollable file list
        html.Div(file_items, className="multi-folder-list"),
    ], className="multi-folder-container")


def create_labels_recommendation(discovery: dict, is_label_mode: bool = True) -> html.Div:
    """
    Create a recommendation section for labels.json location.

    Args:
        discovery: Discovery result dict
        is_label_mode: True if in Label mode, False if in Verify mode

    Returns:
        html.Div with the recommendation (or empty div if not applicable)
    """
    structure_type = discovery.get("structure_type", "unknown")

    # Only show for hierarchical or device_only structures
    if structure_type not in ("hierarchical", "device_only"):
        return html.Div()

    root_labels = discovery.get("root_labels_file")
    root_predictions = discovery.get("root_predictions_file")
    subfolder_labels_count = discovery.get("subfolder_labels_count", 0)
    subfolder_predictions_count = discovery.get("subfolder_predictions_count", 0)

    file_type = "labels" if is_label_mode else "predictions"
    root_file = root_labels if is_label_mode else root_predictions
    subfolder_count = subfolder_labels_count if is_label_mode else subfolder_predictions_count

    # Determine recommendation
    if root_file:
        # Root file exists - good
        return html.Div([
            html.Div([
                html.I(className="bi bi-check-circle-fill text-success me-2"),
                html.Span(f"Using root-level {file_type}.json", className="fw-semibold"),
            ]),
            html.Small(root_file, className="text-muted mono-muted d-block mt-1"),
        ], className="labels-recommendation info p-2 rounded")
    elif subfolder_count > 0:
        # Subfolder files exist but no root file
        file_word = "file" if subfolder_count == 1 else "files"
        return html.Div([
            html.Div([
                html.I(className="bi bi-exclamation-triangle-fill text-warning me-2"),
                html.Span(f"Found {subfolder_count} {file_type}.json {file_word} in subfolders", className="fw-semibold"),
            ]),
            html.Small([
                "For consistency across all data, consider using a single root-level file. ",
                "You can change the output location below.",
            ], className="text-muted d-block mt-1"),
        ], className="labels-recommendation warning p-2 rounded")
    else:
        # No existing files
        if is_label_mode:
            return html.Div([
                html.Div([
                    html.I(className="bi bi-info-circle-fill text-info me-2"),
                    html.Span("No existing labels.json found", className="fw-semibold"),
                ]),
                html.Small([
                    "Labels will be saved to the root folder by default. ",
                    "You can change the output location below.",
                ], className="text-muted d-block mt-1"),
            ], className="labels-recommendation info p-2 rounded")
        else:
            return html.Div()  # For verify mode, the predictions info badge handles this
