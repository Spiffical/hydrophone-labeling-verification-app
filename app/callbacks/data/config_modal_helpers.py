"""Helpers for data-config modal discovery response building."""

import os

import dash_bootstrap_components as dbc
from dash import html

from app.layouts.data_config_panel import (
    create_hierarchy_tree,
    create_labels_recommendation,
    create_multi_file_display,
    create_multi_folder_display,
)


def _structure_type_label(structure_type):
    structure_labels = {
        "hierarchical": "Hierarchical (Date/Device)",
        "device_only": "Device Folders",
        "flat": "Flat Spectrograms",
        "unknown": "Unknown Structure",
    }
    return structure_labels.get(structure_type, "Unknown")


def _build_predictions_info(*, discovery, is_label_mode, create_predictions_info):
    predictions_info = create_predictions_info(bool(discovery.get("predictions_file")), is_label_mode)
    if not is_label_mode and not discovery.get("predictions_file"):
        subfolder_predictions_count = discovery.get("subfolder_predictions_count", 0)
        if subfolder_predictions_count > 0:
            file_word = "file" if subfolder_predictions_count == 1 else "files"
            predictions_info = html.Div(
                [
                    dbc.Badge("Found in subfolders", color="info", className="me-2"),
                    html.Small(
                        f"{subfolder_predictions_count} predictions.json {file_word} detected",
                        className="text-muted",
                    ),
                ]
            )
    return predictions_info


def _resolve_predictions_file_value(*, discovery, selected_path, is_label_mode):
    predictions_file_value = discovery.get("predictions_file") or ""
    if is_label_mode and not predictions_file_value:
        root_labels = discovery.get("root_labels_file")
        if root_labels:
            predictions_file_value = root_labels
        elif discovery.get("structure_type") in ("hierarchical", "device_only"):
            predictions_file_value = os.path.join(selected_path, "labels.json")
    return predictions_file_value


def _collect_multi_folders(*, discovery, selected_path):
    spec_folders = []
    audio_folders = []

    if discovery.get("structure_type") == "hierarchical":
        hierarchy_detail = discovery.get("hierarchy_detail", {})
        for date in sorted(hierarchy_detail.keys()):
            for _, info in sorted(hierarchy_detail[date].items()):
                spec_count = info.get("spectrogram_count", 0)
                audio_count = info.get("audio_count", 0)
                spec_folder_path = info.get("spectrogram_folder")
                audio_folder_path = info.get("audio_folder")
                if spec_count > 0 and spec_folder_path:
                    rel_path = os.path.relpath(spec_folder_path, selected_path)
                    spec_folders.append(
                        {"relative_path": rel_path, "path": spec_folder_path, "count": spec_count}
                    )
                if audio_count > 0 and audio_folder_path:
                    rel_path = os.path.relpath(audio_folder_path, selected_path)
                    audio_folders.append(
                        {"relative_path": rel_path, "path": audio_folder_path, "count": audio_count}
                    )
    elif discovery.get("structure_type") == "device_only":
        device_detail = discovery.get("device_detail", {})
        for _, info in sorted(device_detail.items()):
            spec_count = info.get("spectrogram_count", 0)
            audio_count = info.get("audio_count", 0)
            spec_folder_path = info.get("spectrogram_folder")
            audio_folder_path = info.get("audio_folder")
            if spec_count > 0 and spec_folder_path:
                rel_path = os.path.relpath(spec_folder_path, selected_path)
                spec_folders.append(
                    {"relative_path": rel_path, "path": spec_folder_path, "count": spec_count}
                )
            if audio_count > 0 and audio_folder_path:
                rel_path = os.path.relpath(audio_folder_path, selected_path)
                audio_folders.append(
                    {"relative_path": rel_path, "path": audio_folder_path, "count": audio_count}
                )
    return spec_folders, audio_folders


def _build_predictions_multi(
    *,
    discovery,
    selected_path,
    is_label_mode,
    build_predictions_entries,
):
    predictions_locations = discovery.get("subfolder_predictions_locations", [])
    if is_label_mode:
        predictions_locations = discovery.get("subfolder_labels_locations", [])

    has_subfolder_predictions = len(predictions_locations) > 0
    predictions_entries = []
    predictions_multi = html.Div()
    predictions_label = "Labels Files" if is_label_mode else "Predictions Files"
    if has_subfolder_predictions:
        file_type = "labels" if is_label_mode else "predictions"
        if is_label_mode:
            predictions_multi = create_multi_file_display(predictions_locations, selected_path, file_type)
        else:
            predictions_entries = build_predictions_entries(predictions_locations, selected_path)
            predictions_multi = create_multi_file_display(
                predictions_entries,
                selected_path,
                file_type,
                editable=True,
            )
    return has_subfolder_predictions, predictions_entries, predictions_multi, predictions_label


def build_modal_open_response(
    *,
    selected_path,
    discovery,
    current_mode,
    build_predictions_entries,
    create_info_badge,
    create_predictions_info,
):
    is_label_mode = current_mode == "label"
    structure_type = _structure_type_label(discovery.get("structure_type"))

    spec_info = create_info_badge(
        bool(discovery.get("spectrogram_folder")),
        discovery.get("spectrogram_count", 0),
        ", ".join(discovery.get("spectrogram_extensions", [])),
    )
    audio_info = create_info_badge(
        bool(discovery.get("audio_folder")),
        discovery.get("audio_count", 0),
    )
    predictions_info = _build_predictions_info(
        discovery=discovery,
        is_label_mode=is_label_mode,
        create_predictions_info=create_predictions_info,
    )

    hierarchy_tree = create_hierarchy_tree(discovery)
    show_hierarchy_toggle = (
        {"display": "block"}
        if discovery.get("structure_type") in ("hierarchical", "device_only")
        else {"display": "none"}
    )
    labels_recommendation = create_labels_recommendation(discovery, is_label_mode)
    predictions_file_value = _resolve_predictions_file_value(
        discovery=discovery,
        selected_path=selected_path,
        is_label_mode=is_label_mode,
    )

    spec_folders, audio_folders = _collect_multi_folders(
        discovery=discovery,
        selected_path=selected_path,
    )
    spec_multi = create_multi_folder_display(spec_folders, "spectrogram") if spec_folders else html.Div()
    audio_multi = create_multi_folder_display(audio_folders, "audio") if audio_folders else html.Div()

    has_subfolder_predictions, predictions_entries, predictions_multi, predictions_multi_label = _build_predictions_multi(
        discovery=discovery,
        selected_path=selected_path,
        is_label_mode=is_label_mode,
        build_predictions_entries=build_predictions_entries,
    )
    predictions_label = ("Labels File" if is_label_mode else "Predictions File")
    if has_subfolder_predictions:
        predictions_label = predictions_multi_label

    is_hierarchical = discovery.get("structure_type") in ("hierarchical", "device_only")
    hide_single = {"display": "none"} if is_hierarchical else {"display": "block"}
    show_predictions_single = (
        {"display": "none"} if (has_subfolder_predictions and not is_label_mode) else {"display": "block"}
    )

    return (
        discovery,
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
        hide_single,
        hide_single,
        predictions_multi,
        show_predictions_single,
    )
