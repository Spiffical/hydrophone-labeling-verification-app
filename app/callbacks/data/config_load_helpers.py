"""Helper functions for data-config load callbacks."""

import os
import time

from dash import no_update


def apply_config_data_section(
    *,
    config,
    discovery,
    base_path,
    spec_folder,
    audio_folder,
    predictions_file,
    predictions_entries,
    predictions_values,
    predictions_ids,
):
    cfg = config if isinstance(config, dict) else {}
    if "data" not in cfg:
        cfg["data"] = {}

    structure_type = discovery.get("structure_type") if discovery else "flat"
    cfg["data"]["data_dir"] = base_path
    cfg["data"]["structure_type"] = structure_type

    if structure_type in ("hierarchical", "device_only"):
        cfg["data"]["spectrogram_folder"] = None
        cfg["data"]["audio_folder"] = None
        cfg["data"]["predictions_file"] = predictions_file or None
    else:
        cfg["data"]["spectrogram_folder"] = spec_folder or None
        cfg["data"]["audio_folder"] = audio_folder or None
        cfg["data"]["predictions_file"] = predictions_file or None

    predictions_overrides = []
    if predictions_entries and predictions_ids:
        entry_map = {entry.get("index"): entry for entry in predictions_entries}
        for entry_id, value in zip(predictions_ids, predictions_values or []):
            index = entry_id.get("index") if isinstance(entry_id, dict) else None
            entry = entry_map.get(index)
            if not entry or not value:
                continue
            scope = entry.get("scope") or {}
            predictions_overrides.append(
                {
                    "date": scope.get("date"),
                    "device": scope.get("device"),
                    "path": value,
                }
            )
    cfg["data"]["predictions_overrides"] = predictions_overrides or None
    return cfg, structure_type


def compute_global_filter_options(
    *,
    structure_type,
    discovery,
    base_path,
    current_date_value,
    current_device_value,
):
    date_options = []
    date_value = None
    device_options = []
    device_value = None

    if structure_type == "hierarchical":
        dates = discovery.get("dates", [])
        devices = discovery.get("devices", [])
        date_options = [{"label": "All Dates", "value": "__all__"}] + [
            {"label": d, "value": d} for d in dates
        ]
        device_options = [{"label": "All Devices", "value": "__all__"}] + [
            {"label": d, "value": d} for d in devices
        ]
        if current_date_value in dates:
            date_value = current_date_value
        elif len(dates) == 1:
            date_value = dates[0]
        else:
            date_value = "__all__"

        if current_device_value in devices:
            device_value = current_device_value
        elif len(devices) == 1:
            device_value = devices[0]
        else:
            device_value = "__all__"
    elif structure_type == "device_only":
        devices = discovery.get("devices", [])
        device_options = [{"label": "All Devices", "value": "__all__"}] + [
            {"label": d, "value": d} for d in devices
        ]
        if current_device_value in devices:
            device_value = current_device_value
        elif len(devices) == 1:
            device_value = devices[0]
        else:
            device_value = "__all__"

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
    elif discovery and (discovery.get("dates") or discovery.get("devices")):
        dates = discovery.get("dates", [])
        devices = discovery.get("devices", [])
        date_options = [{"label": "All Dates", "value": "__all__"}] + [
            {"label": d, "value": d} for d in dates
        ]
        device_options = [{"label": "All Devices", "value": "__all__"}] + [
            {"label": d, "value": d} for d in devices
        ]
        if current_date_value in dates:
            date_value = current_date_value
        else:
            date_value = "__all__" if dates else "__flat__"
        if current_device_value in devices:
            device_value = current_device_value
        else:
            device_value = "__all__" if devices else None
    else:
        date_options = [{"label": "(Direct)", "value": "__flat__"}]
        date_value = "__flat__"

    return date_options, date_value, device_options, device_value


def compute_label_tab_displays(*, current_mode, structure_type, discovery, base_path, spec_folder, audio_folder):
    if current_mode != "label":
        return no_update, no_update, no_update

    spec_display = spec_folder or base_path or "Not set"
    audio_display = audio_folder or "Not set"

    if structure_type in ("hierarchical", "device_only"):
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
    return spec_display, audio_display, output_display


def build_load_trigger_value(*, current_mode, config, date_value, device_value):
    return {
        "timestamp": time.time(),
        "mode": current_mode,
        "source": "data-config-load",
        "config": config,
        "date_value": date_value,
        "device_value": device_value,
    }
