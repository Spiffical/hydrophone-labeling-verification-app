import glob
import os
from typing import Dict, Optional

from app.utils.audio_matching import find_matching_audio_files, get_representative_audio_file
from app.utils.file_io import read_json
from app.utils.format_converters import (
    convert_hydrophonedashboard_to_unified,
    convert_legacy_labeling_to_unified,
    convert_whale_predictions_to_unified,
)
from app.utils.unified_format_converter import is_unified_v2_format, convert_unified_v2_to_internal


def _find_latest_date(dashboard_root: str) -> Optional[str]:
    if not dashboard_root or not os.path.exists(dashboard_root):
        return None
    candidates = [d for d in os.listdir(dashboard_root) if len(d) == 10]
    return sorted(candidates, reverse=True)[0] if candidates else None


def _find_first_hydrophone(dashboard_root: str, date_str: str) -> Optional[str]:
    if not dashboard_root or not date_str:
        return None
    date_dir = os.path.join(dashboard_root, date_str)
    if not os.path.exists(date_dir):
        return None
    hydrophones = [d for d in os.listdir(date_dir) if os.path.isdir(os.path.join(date_dir, d))]
    return sorted(hydrophones)[0] if hydrophones else None


def _get_spectrogram_folder(base_path: str, folder_names: list = None) -> Optional[str]:
    """Find the spectrogram folder within a device directory.
    
    Args:
        base_path: The base directory to search within.
        folder_names: List of folder names to search for (in priority order).
                      Defaults to ["spectrograms", "onc_spectrograms", "mat_files"].
    """
    if folder_names is None:
        folder_names = ["spectrograms", "onc_spectrograms", "mat_files"]
    
    for spec_dirname in folder_names:
        candidate = os.path.join(base_path, spec_dirname)
        if os.path.exists(candidate):
            return candidate
    # Fallback to base path if it contains spectrograms directly
    if os.path.exists(base_path):
        return base_path
    return None


def _attach_predictions_path(items: list, predictions_path: Optional[str]) -> None:
    if not predictions_path:
        return
    for item in items:
        if not item:
            continue
        metadata = item.get("metadata") or {}
        metadata["predictions_path"] = predictions_path
        item["metadata"] = metadata


def _normalize_item_key(key: Optional[str]) -> Optional[str]:
    if not key:
        return key
    lower_key = key.lower()
    for ext in (".mat", ".npy", ".png", ".jpg", ".jpeg", ".wav", ".flac", ".mp3"):
        if lower_key.endswith(ext):
            return key[: -len(ext)]
    return key


def _extract_labels_map(labels_json: dict) -> Dict[str, dict]:
    labels_map: Dict[str, dict] = {}
    if not isinstance(labels_json, dict):
        return labels_map

    if isinstance(labels_json.get("items"), list):
        for item in labels_json.get("items", []):
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id")

            # Prefer verifications (unified format)
            verifications = item.get("verifications")
            if verifications and isinstance(verifications, list):
                latest = verifications[-1]
                label_decisions = latest.get("label_decisions", [])
                labels = [
                    ld["label"] for ld in label_decisions
                    if ld.get("decision") in ("accepted", "added")
                ]
                entry = {
                    "labels": labels,
                    "notes": latest.get("notes", "") or "",
                    "annotated_by": latest.get("verified_by"),
                    "annotated_at": latest.get("verified_at"),
                    "verified": True,
                }
            else:
                # Fallback to legacy annotations
                annotations = item.get("annotations") or {}
                entry = {
                    "labels": annotations.get("labels", []) or [],
                    "notes": annotations.get("notes", "") or "",
                    "annotated_by": annotations.get("annotated_by"),
                    "annotated_at": annotations.get("annotated_at"),
                    "verified": bool(annotations.get("verified")),
                }
            for key in {item_id, _normalize_item_key(item_id)}:
                if key:
                    labels_map[key] = entry
        return labels_map

    for raw_key, entry in labels_json.items():
        labels = []
        notes = ""
        annotated_by = None
        annotated_at = None
        verified = False

        if isinstance(entry, list):
            labels = entry
        elif isinstance(entry, dict):
            labels = (
                entry.get("verified_labels")
                or entry.get("labels")
                or (entry.get("annotations") or {}).get("labels")
                or entry.get("predicted_labels")
                or []
            )
            notes = entry.get("notes") or (entry.get("annotations") or {}).get("notes", "")
            annotated_by = entry.get("annotated_by") or entry.get("verified_by")
            annotated_at = entry.get("annotated_at") or entry.get("verified_at")
            verified = bool(entry.get("verified")) or entry.get("verified_labels") is not None

        mapped = {
            "labels": labels if isinstance(labels, list) else [],
            "notes": notes or "",
            "annotated_by": annotated_by,
            "annotated_at": annotated_at,
            "verified": verified,
        }
        for key in {raw_key, _normalize_item_key(raw_key)}:
            if key:
                labels_map[key] = mapped

    return labels_map


def _collect_hierarchical_labels_map(
    data_dir: str,
    date_str: Optional[str],
    hydrophone: Optional[str],
) -> Dict[str, dict]:
    if not data_dir or not os.path.exists(data_dir):
        return {}

    all_dates, all_devices = _discover_dates_and_devices(data_dir)
    if date_str and date_str != "__all__":
        dates_to_check = [date_str]
    else:
        dates_to_check = all_dates

    if hydrophone and hydrophone != "__all__":
        devices_to_check = [hydrophone]
    else:
        devices_to_check = all_devices

    labels_map: Dict[str, dict] = {}

    root_labels = os.path.join(data_dir, "labels.json")
    if os.path.exists(root_labels):
        labels_map.update(_extract_labels_map(read_json(root_labels) or {}))

    for date in dates_to_check:
        if not date:
            continue
        date_labels = os.path.join(data_dir, date, "labels.json")
        if os.path.exists(date_labels):
            labels_map.update(_extract_labels_map(read_json(date_labels) or {}))

        for device in devices_to_check:
            if not device:
                continue
            device_labels = os.path.join(data_dir, date, device, "labels.json")
            if os.path.exists(device_labels):
                labels_map.update(_extract_labels_map(read_json(device_labels) or {}))

    return labels_map


def _load_items_from_folder(folder: str, audio_folder: Optional[str], labels_file: Optional[str], 
                             hydrophone: Optional[str], date_str: Optional[str] = None) -> list:
    """Load spectrogram items from a single folder."""
    if not folder or not os.path.exists(folder):
        return []
    
    existing_labels = {}
    if labels_file and os.path.exists(labels_file):
        existing_labels = _extract_labels_map(read_json(labels_file) or {})
    
    mat_files = sorted(glob.glob(os.path.join(folder, "*.mat")))
    npy_files = sorted(glob.glob(os.path.join(folder, "*.npy")))
    png_files = sorted(glob.glob(os.path.join(folder, "*.png")))
    all_files = mat_files + npy_files + png_files
    
    items = []
    for fpath in all_files:
        filename = os.path.basename(fpath)
        item_id = os.path.splitext(filename)[0]
        
        label_entry = existing_labels.get(filename) or existing_labels.get(item_id)
        if isinstance(label_entry, dict):
            file_labels = label_entry.get("labels", [])
            notes = label_entry.get("notes", "") or ""
            annotated_by = label_entry.get("annotated_by")
            annotated_at = label_entry.get("annotated_at")
            verified = bool(label_entry.get("verified"))
        else:
            file_labels = label_entry or []
            notes = ""
            annotated_by = None
            annotated_at = None
            verified = False
        
        item = {
            "item_id": item_id,
            "spectrogram_path": fpath if fpath.endswith(('.png', '.jpg')) else None,
            "mat_path": fpath if fpath.endswith(('.mat', '.npy')) else None,
            "audio_path": None,
            "timestamps": {"start": None, "end": None},
            "device_code": hydrophone,
            "date": date_str,
            "predictions": None,
            "annotations": {
                "labels": file_labels,
                "annotated_by": annotated_by,
                "annotated_at": annotated_at,
                "verified": verified,
                "notes": notes,
            },
            "metadata": {"source_folder": folder},
        }
        
        if audio_folder and os.path.exists(audio_folder):
            matches = find_matching_audio_files(filename, audio_folder)
            if matches:
                item["audio_path"] = get_representative_audio_file(matches)
        
        items.append(item)
    
    return items


def _discover_dates_and_devices(data_dir: str) -> tuple:
    """Discover all dates and devices in a hierarchical data directory."""
    dates = []
    devices = set()
    
    if not data_dir or not os.path.exists(data_dir):
        return dates, list(devices)
    
    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)
        if os.path.isdir(item_path) and len(item) == 10 and item[4] == '-':
            dates.append(item)
            # Find devices within this date folder
            for device in os.listdir(item_path):
                device_path = os.path.join(item_path, device)
                if os.path.isdir(device_path):
                    devices.add(device)
    
    return sorted(dates, reverse=True), sorted(list(devices))


def load_label_mode(config: Dict, date_str: Optional[str] = None, hydrophone: Optional[str] = None) -> Dict:
    from app.utils.label_operations import get_default_labels_path
    
    label_cfg = config.get("label", {})
    data_cfg = config.get("data", {})
    structure_type = data_cfg.get("structure_type", "flat")
    
    # Get configurable folder names
    spec_folder_names = data_cfg.get("spectrogram_folder_names", ["spectrograms", "onc_spectrograms", "mat_files"])
    audio_folder_names = data_cfg.get("audio_folder_names", ["audio"])
    
    data_dir = data_cfg.get("data_dir") or label_cfg.get("folder")
    folder = data_cfg.get("spectrogram_folder")
    labels_file = data_cfg.get("labels_file") or label_cfg.get("output_file")
    audio_folder = data_cfg.get("audio_folder") or label_cfg.get("audio_folder")
    
    data = {
        "items": [],
        "summary": {"total_items": 0, "annotated": 0, "verified": 0},
        "metadata": {"format_version": "2.0"}
    }
    
    audio_roots = []
    
    # Handle "__all__" selections for hierarchical structures
    if structure_type == "hierarchical" and data_dir:
        all_dates, all_devices = _discover_dates_and_devices(data_dir)
        
        # Determine which dates to load
        dates_to_load = all_dates if date_str == "__all__" else [date_str] if date_str and date_str != "__flat__" else all_dates[:1]
        
        # Determine which devices to load
        devices_to_load = all_devices if hydrophone == "__all__" else [hydrophone] if hydrophone else all_devices[:1]
        
        all_items = []
        folders_loaded = []
        
        for d in dates_to_load:
            for dev in devices_to_load:
                base_device_path = os.path.join(data_dir, d, dev)
                if not os.path.exists(base_device_path):
                    continue
                
                spec_folder = _get_spectrogram_folder(base_device_path, spec_folder_names)
                
                # Find audio folder using configurable names
                device_audio_folder = None
                for audio_name in audio_folder_names:
                    candidate = os.path.join(base_device_path, audio_name)
                    if os.path.exists(candidate):
                        device_audio_folder = candidate
                        break
                
                device_labels_file = os.path.join(base_device_path, "labels.json")
                
                if device_audio_folder and os.path.exists(device_audio_folder):
                    audio_roots.append(device_audio_folder)

                items = _load_items_from_folder(
                    spec_folder,
                    device_audio_folder if device_audio_folder and os.path.exists(device_audio_folder) else None,
                    device_labels_file if os.path.exists(device_labels_file) else None,
                    dev,
                    d
                )
                all_items.extend(items)
                if spec_folder:
                    folders_loaded.append(spec_folder)

        data["items"] = all_items
        data["_spec_folders_loaded"] = folders_loaded
        data["_audio_folders_loaded"] = [r for r in audio_roots]
        folder = ", ".join(folders_loaded[:3]) + ("..." if len(folders_loaded) > 3 else "") if folders_loaded else None
        
        # Overlay labels from root/date/device labels.json (if present).
        labels_map = {}
        if labels_file and os.path.exists(labels_file):
            labels_map = _extract_labels_map(read_json(labels_file) or {})
        else:
            labels_map = _collect_hierarchical_labels_map(data_dir, date_str, hydrophone)
            root_labels = os.path.join(data_dir, "labels.json")
            if not labels_file and os.path.exists(root_labels):
                labels_file = root_labels

        if labels_map and data["items"]:
            for item in data["items"]:
                item_id = item.get("item_id")
                match = labels_map.get(item_id) or labels_map.get(_normalize_item_key(item_id))
                if not match:
                    continue
                annotations = item.get("annotations") or {
                    "labels": [],
                    "annotated_by": None,
                    "annotated_at": None,
                    "verified": False,
                    "notes": "",
                }
                annotations["labels"] = match.get("labels", [])
                annotations["notes"] = match.get("notes", "") or ""
                annotations["annotated_by"] = match.get("annotated_by")
                annotations["annotated_at"] = match.get("annotated_at")
                annotations["verified"] = bool(match.get("verified"))
                item["annotations"] = annotations

    elif not folder:
        # Flat structure - load directly from data_dir
        folder = data_dir
        if folder and os.path.exists(folder):
            if not labels_file:
                labels_file = get_default_labels_path(folder)
            items = _load_items_from_folder(folder, audio_folder, labels_file, hydrophone, date_str)
            data["items"] = items
            if audio_folder:
                audio_roots.append(audio_folder)
    else:
        # Manual folder override
        if not labels_file:
            labels_file = get_default_labels_path(folder)
        items = _load_items_from_folder(folder, audio_folder, labels_file, hydrophone, date_str)
        data["items"] = items
        if audio_folder:
            audio_roots.append(audio_folder)
    
    # Calculate summary
    data["summary"]["total_items"] = len(data["items"])
    data["summary"]["annotated"] = sum(1 for item in data["items"] if item.get("annotations", {}).get("labels"))
    data["summary"]["verified"] = sum(1 for item in data["items"] if item.get("annotations", {}).get("verified"))
    
    # Store active paths for UI updates
    data["summary"]["active_date"] = "All" if date_str == "__all__" else date_str
    data["summary"]["active_hydrophone"] = "All" if hydrophone == "__all__" else hydrophone
    data["summary"]["labels_file"] = labels_file
    data["summary"]["data_root"] = data_dir

    # Build multi-folder summary (same pattern as verify mode)
    spec_folders_loaded = data.pop("_spec_folders_loaded", [])
    audio_folders_loaded = data.pop("_audio_folders_loaded", [])
    unique_spec_folders = list(dict.fromkeys(spec_folders_loaded)) if spec_folders_loaded else []
    unique_audio_folders = list(dict.fromkeys(audio_folders_loaded)) if audio_folders_loaded else []

    data["summary"]["spectrogram_folders_list"] = unique_spec_folders
    data["summary"]["audio_folders_list"] = unique_audio_folders

    is_multi_selection = date_str == "__all__" or hydrophone == "__all__"

    if len(unique_spec_folders) > 1 and is_multi_selection:
        word = "folder" if len(unique_spec_folders) == 1 else "folders"
        data["summary"]["spectrogram_folder"] = f"{len(unique_spec_folders)} {word}"
    else:
        data["summary"]["spectrogram_folder"] = folder

    if len(unique_audio_folders) > 1 and is_multi_selection:
        word = "folder" if len(unique_audio_folders) == 1 else "folders"
        data["summary"]["audio_folder"] = f"{len(unique_audio_folders)} {word}"
    else:
        data["summary"]["audio_folder"] = audio_folder or (audio_roots[0] if audio_roots else None)

    data["audio_roots"] = list(set(audio_roots))
    return data


def load_verify_mode(
    config: Dict,
    date_str: Optional[str] = None,
    hydrophone: Optional[str] = None,
    allow_unlabeled: bool = False,
) -> Dict:
    verify_cfg = config.get("verify", {})
    data_cfg = config.get("data", {})
    dashboard_root = data_cfg.get("data_dir") or verify_cfg.get("dashboard_root")
    structure_type = data_cfg.get("structure_type", "hierarchical")
    
    # Get configurable folder names
    spec_folder_names = data_cfg.get("spectrogram_folder_names", ["spectrograms", "onc_spectrograms", "mat_files"])
    audio_folder_names = data_cfg.get("audio_folder_names", ["audio"])
    
    # Check if we have manual overrides from the config panel
    spec_folder_override = data_cfg.get("spectrogram_folder")
    audio_folder_override = data_cfg.get("audio_folder")
    predictions_file_override = data_cfg.get("predictions_file")
    
    data = {"items": [], "summary": {"total_items": 0}}
    predictions_path = None
    mat_dir = None
    audio_dir = None
    
    # Track all folders when loading from multiple sources
    mat_dirs_loaded = []
    audio_folders_loaded = []
    predictions_paths_loaded = []
    
    # Detect flat mode from structure_type or special markers
    is_flat = (structure_type == "flat" or 
               date_str == "__flat__" or 
               (spec_folder_override and not hydrophone))
    
    if is_flat:
        # Flat folder - load spectrograms directly from the folder
        mat_dir = spec_folder_override or dashboard_root
        audio_dir = audio_folder_override
        predictions_path = predictions_file_override
        
        # If we have predictions, load them
        if predictions_path and os.path.exists(predictions_path):
            whale_config = {"whale": {"predictions_json": predictions_path}}
            data = load_whale_mode(whale_config)
            _attach_predictions_path(data.get("items", []), predictions_path)
        
        # Add items from mat files if no predictions or to supplement
        if mat_dir and os.path.exists(mat_dir):
            existing_ids = {item["item_id"] for item in data.get("items", [])}
            mat_files = sorted(glob.glob(os.path.join(mat_dir, "*.mat")))
            npy_files = sorted(glob.glob(os.path.join(mat_dir, "*.npy")))
            png_files = sorted(glob.glob(os.path.join(mat_dir, "*.png")))
            
            all_files = mat_files + npy_files + png_files
            
            for fpath in all_files:
                filename = os.path.basename(fpath)
                item_id = os.path.splitext(filename)[0]
                
                if item_id in existing_ids or filename in existing_ids:
                    # Update existing item with mat_path
                    for item in data["items"]:
                        if item.get("item_id") in [item_id, filename]:
                            item["mat_path"] = fpath
                            break
                else:
                    # Create new item
                    audio_path = None
                    if audio_dir:
                        for ext in ['.flac', '.wav', '.mp3']:
                            candidate = os.path.join(audio_dir, item_id + ext)
                            if os.path.exists(candidate):
                                audio_path = candidate
                                break
                    
                    data["items"].append({
                        "item_id": item_id,
                        "spectrogram_path": fpath if fpath.endswith(('.png', '.jpg')) else None,
                        "mat_path": fpath if fpath.endswith(('.mat', '.npy')) else None,
                        "audio_path": audio_path,
                        "timestamps": {"start": None, "end": None},
                        "device_code": None,
                        "predictions": {},
                        "annotations": {
                            "labels": [],
                            "annotated_by": None,
                            "annotated_at": None,
                            "verified": False,
                            "notes": "",
                        },
                        "metadata": {},
                    })
            
            data["summary"]["total_items"] = len(data["items"])
    
    elif dashboard_root:
        # Hierarchical structure - use DATE/DEVICE paths
        # Handle "__all__" selections
        all_dates, all_devices = _discover_dates_and_devices(dashboard_root)
        
        # Determine which dates to load
        if date_str == "__all__":
            dates_to_load = all_dates
        elif date_str and date_str != "__flat__":
            dates_to_load = [date_str]
        else:
            fallback_date = verify_cfg.get("date") or _find_latest_date(dashboard_root)
            dates_to_load = [fallback_date] if fallback_date else all_dates[:1]
        
        # Determine which devices to load
        if hydrophone == "__all__":
            devices_to_load = all_devices
        elif hydrophone:
            devices_to_load = [hydrophone]
        else:
            # Try to get first hydrophone from the first date we're loading
            fallback_device = verify_cfg.get("hydrophone")
            if not fallback_device and dates_to_load:
                fallback_device = _find_first_hydrophone(dashboard_root, dates_to_load[0])
            devices_to_load = [fallback_device] if fallback_device else all_devices[:1]
        
        all_items = []
        audio_roots = []
        
        # CASCADING PREDICTIONS DISCOVERY:
        # Check root level first - if found, use for all items
        root_predictions_path = None
        root_labels_path = None
        
        if not predictions_file_override:
            # Check for predictions.json at the root
            root_pred_candidate = os.path.join(dashboard_root, "predictions.json")
            if os.path.exists(root_pred_candidate):
                root_predictions_path = root_pred_candidate
            else:
                # Check for labels.json at the root (legacy)
                root_labels_candidate = os.path.join(dashboard_root, "labels.json")
                if os.path.exists(root_labels_candidate):
                    root_labels_path = root_labels_candidate
        
        # If we found root-level predictions, load them once
        root_data = None
        if predictions_file_override and os.path.exists(predictions_file_override):
            whale_config = {"whale": {"predictions_json": predictions_file_override}}
            root_data = load_whale_mode(whale_config)
            predictions_path = predictions_file_override
            predictions_paths_loaded.append(predictions_file_override)
            _attach_predictions_path(root_data.get("items", []), predictions_path)
        elif root_predictions_path:
            whale_config = {"whale": {"predictions_json": root_predictions_path}}
            root_data = load_whale_mode(whale_config)
            predictions_path = root_predictions_path
            predictions_paths_loaded.append(root_predictions_path)
            _attach_predictions_path(root_data.get("items", []), predictions_path)
        
        for active_date in dates_to_load:
            if not active_date:
                continue
            
            # Check for date-level predictions (e.g., root/2024-01-15/predictions.json)
            date_predictions_path = None
            date_labels_path = None
            date_data = None
            
            if not root_data and not predictions_file_override:
                date_path = os.path.join(dashboard_root, active_date)
                date_pred_candidate = os.path.join(date_path, "predictions.json")
                if os.path.exists(date_pred_candidate):
                    date_predictions_path = date_pred_candidate
                    whale_config = {"whale": {"predictions_json": date_predictions_path}}
                    date_data = load_whale_mode(whale_config)
                    predictions_paths_loaded.append(date_predictions_path)
                    _attach_predictions_path(date_data.get("items", []), date_predictions_path)
                else:
                    date_labels_candidate = os.path.join(date_path, "labels.json")
                    if os.path.exists(date_labels_candidate):
                        date_labels_path = date_labels_candidate
            
            for active_device in devices_to_load:
                if not active_device:
                    continue
                    
                base_path = os.path.join(dashboard_root, active_date, active_device)
                if not os.path.exists(base_path):
                    continue
                
                # Try common spectrogram folder names if no override
                if spec_folder_override:
                    local_mat_dir = spec_folder_override
                else:
                    local_mat_dir = _get_spectrogram_folder(base_path, spec_folder_names)
                
                # Find audio folder using configurable names
                if audio_folder_override:
                    local_audio_dir = audio_folder_override
                else:
                    local_audio_dir = None
                    for audio_name in audio_folder_names:
                        candidate = os.path.join(base_path, audio_name)
                        if os.path.exists(candidate):
                            local_audio_dir = candidate
                            break
                
                # Load predictions using cascading discovery:
                # Priority: root > date > device
                folder_data = {"items": [], "summary": {}}
                
                if root_data:
                    # Use root-level predictions - filter items relevant to this device/date
                    # The items should match based on item_id or mat file matching
                    folder_data = {"items": list(root_data.get("items", [])), "summary": {}}
                elif date_data:
                    # Use date-level predictions
                    folder_data = {"items": list(date_data.get("items", [])), "summary": {}}
                else:
                    # Check device-level predictions
                    local_predictions_path = os.path.join(base_path, "predictions.json")
                    if os.path.exists(local_predictions_path):
                        whale_config = {"whale": {"predictions_json": local_predictions_path}}
                        folder_data = load_whale_mode(whale_config)
                        predictions_paths_loaded.append(local_predictions_path)
                        _attach_predictions_path(folder_data.get("items", []), local_predictions_path)
                    else:
                        # Fallback to legacy labels.json if it exists
                        labels_path = os.path.join(base_path, "labels.json")
                        labels_json = read_json(labels_path) if os.path.exists(labels_path) else {}
                        image_dir = os.path.join(base_path, "images")
                        folder_data = convert_hydrophonedashboard_to_unified(labels_json, active_date, active_device, image_dir)
                
                # Enrich items with spectrogram/mat file paths
                spec_files = []
                mat_files_map = {}
                npy_files_map = {}
                image_files_map = {}
                if local_mat_dir and os.path.exists(local_mat_dir):
                    mat_files = sorted(glob.glob(os.path.join(local_mat_dir, "*.mat")))
                    npy_files = sorted(glob.glob(os.path.join(local_mat_dir, "*.npy")))
                    png_files = sorted(glob.glob(os.path.join(local_mat_dir, "*.png")))
                    jpg_files = sorted(glob.glob(os.path.join(local_mat_dir, "*.jpg")))
                    jpeg_files = sorted(glob.glob(os.path.join(local_mat_dir, "*.jpeg")))
                    image_files = png_files + jpg_files + jpeg_files
                    spec_files = mat_files + npy_files + image_files

                    mat_files_map = {os.path.basename(f): f for f in mat_files}
                    npy_files_map = {os.path.basename(f): f for f in npy_files}
                    image_files_map = {os.path.basename(f): f for f in image_files}
                    all_specs_map = {**mat_files_map, **npy_files_map}

                    for item in folder_data.get("items", []):
                        item_id = item.get("item_id")
                        if not item_id:
                            continue
                        if item_id in all_specs_map:
                            item["mat_path"] = all_specs_map[item_id]
                        elif f"{item_id}.mat" in all_specs_map:
                            item["mat_path"] = all_specs_map[f"{item_id}.mat"]
                        elif f"{item_id}.npy" in all_specs_map:
                            item["mat_path"] = all_specs_map[f"{item_id}.npy"]

                        if not item.get("spectrogram_path"):
                            if item_id in image_files_map:
                                item["spectrogram_path"] = image_files_map[item_id]
                            elif f"{item_id}.png" in image_files_map:
                                item["spectrogram_path"] = image_files_map[f"{item_id}.png"]
                            elif f"{item_id}.jpg" in image_files_map:
                                item["spectrogram_path"] = image_files_map[f"{item_id}.jpg"]
                            elif f"{item_id}.jpeg" in image_files_map:
                                item["spectrogram_path"] = image_files_map[f"{item_id}.jpeg"]

                    mat_dirs_loaded.append(local_mat_dir)

                # In explore mode, include unlabeled items from spectrogram folders
                if allow_unlabeled and spec_files:
                    existing_ids = set()
                    for item in folder_data.get("items", []):
                        item_id = item.get("item_id")
                        if item_id:
                            existing_ids.add(item_id)

                    for fpath in spec_files:
                        filename = os.path.basename(fpath)
                        item_id = os.path.splitext(filename)[0]
                        if item_id in existing_ids or filename in existing_ids:
                            continue

                        audio_path = None
                        if local_audio_dir:
                            for ext in [".flac", ".wav", ".mp3"]:
                                candidate = os.path.join(local_audio_dir, item_id + ext)
                                if os.path.exists(candidate):
                                    audio_path = candidate
                                    break

                        is_image = fpath.lower().endswith((".png", ".jpg", ".jpeg"))
                        is_mat = fpath.lower().endswith((".mat", ".npy"))

                        folder_data["items"].append({
                            "item_id": item_id,
                            "spectrogram_path": fpath if is_image else None,
                            "mat_path": fpath if is_mat else None,
                            "audio_path": audio_path,
                            "timestamps": {"start": None, "end": None},
                            "device_code": active_device,
                            "predictions": {},
                            "annotations": {
                                "labels": [],
                                "annotated_by": None,
                                "annotated_at": None,
                                "verified": False,
                                "notes": "",
                            },
                            "metadata": {"date": active_date, "hydrophone": active_device},
                        })
                        existing_ids.add(item_id)
                        existing_ids.add(filename)
                
                if local_audio_dir and os.path.exists(local_audio_dir):
                    audio_roots.append(local_audio_dir)
                    audio_folders_loaded.append(local_audio_dir)
                
                all_items.extend(folder_data.get("items", []))
        
        data["items"] = all_items
        data["summary"]["total_items"] = len(all_items)
        data["summary"]["active_date"] = "All" if date_str == "__all__" else (dates_to_load[0] if dates_to_load else None)
        data["summary"]["active_hydrophone"] = "All" if hydrophone == "__all__" else (devices_to_load[0] if devices_to_load else None)
        data["audio_roots"] = list(set(audio_roots))
        
        # When showing summary, use the actual folders based on selection
        # If a specific device is selected, show that device's folders (not first loaded)
        if len(dates_to_load) == 1 and len(devices_to_load) == 1:
            # Single date and device selected - show exact paths
            single_base = os.path.join(dashboard_root, dates_to_load[0], devices_to_load[0])
            mat_dir = _get_spectrogram_folder(single_base, spec_folder_names) if os.path.exists(single_base) else None
            audio_dir = None
            for audio_name in audio_folder_names:
                candidate = os.path.join(single_base, audio_name)
                if os.path.exists(candidate):
                    audio_dir = candidate
                    break
            # Use device-specific predictions if not using root-level
            if predictions_file_override:
                predictions_path = predictions_file_override
            elif root_predictions_path:
                predictions_path = root_predictions_path
            else:
                device_pred = os.path.join(single_base, "predictions.json")
                if os.path.exists(device_pred):
                    predictions_path = device_pred
                else:
                    predictions_path = predictions_paths_loaded[0] if predictions_paths_loaded else None
        else:
            # Multiple selections - use first loaded or summary
            mat_dir = mat_dirs_loaded[0] if mat_dirs_loaded else None
            audio_dir = audio_roots[0] if audio_roots else None
            predictions_path = predictions_paths_loaded[0] if predictions_paths_loaded else None

    # Enrich with mat files if they exist
    if mat_dir and os.path.exists(mat_dir) and data["items"]:
        mat_files = {os.path.basename(f): f for f in glob.glob(os.path.join(mat_dir, "*.mat"))}
        npy_files = {os.path.basename(f): f for f in glob.glob(os.path.join(mat_dir, "*.npy"))}
        all_specs = {**mat_files, **npy_files}
        
        for item in data["items"]:
            item_id = item.get("item_id")
            if item_id in all_specs:
                item["mat_path"] = all_specs[item_id]
            elif f"{item_id}.mat" in all_specs:
                item["mat_path"] = all_specs[f"{item_id}.mat"]
            elif f"{item_id}.npy" in all_specs:
                item["mat_path"] = all_specs[f"{item_id}.npy"]

    # Ensure audio roots are set for the serve_audio route
    if audio_dir and os.path.exists(audio_dir):
        data["audio_roots"] = [audio_dir]
    else:
        data.setdefault("audio_roots", [])

    # Add folder paths to summary for display in UI
    data["summary"]["data_root"] = dashboard_root
    
    # Show appropriate folder information based on selection type
    # When "All" is selected for date or device, show counts; otherwise show exact path
    is_multi_selection = date_str == "__all__" or hydrophone == "__all__"
    
    unique_spec_folders = list(dict.fromkeys(mat_dirs_loaded)) if mat_dirs_loaded else []
    unique_audio_folders = list(dict.fromkeys(audio_folders_loaded)) if audio_folders_loaded else []
    unique_pred_files = list(dict.fromkeys(predictions_paths_loaded)) if predictions_paths_loaded else []
    
    # Store the actual paths list for UI popover/tooltip display
    data["summary"]["spectrogram_folders_list"] = unique_spec_folders
    data["summary"]["audio_folders_list"] = unique_audio_folders
    data["summary"]["predictions_files_list"] = unique_pred_files
    
    print(f"DEBUG summary: mat_dirs_loaded={len(mat_dirs_loaded)}, unique={len(unique_spec_folders)}, is_multi={is_multi_selection}")
    
    if len(unique_spec_folders) > 1 and is_multi_selection:
        folder_word = "folder" if len(unique_spec_folders) == 1 else "folders"
        data["summary"]["spectrogram_folder"] = f"{len(unique_spec_folders)} {folder_word}"
    else:
        data["summary"]["spectrogram_folder"] = mat_dir
    
    if len(unique_audio_folders) > 1 and is_multi_selection:
        folder_word = "folder" if len(unique_audio_folders) == 1 else "folders"
        data["summary"]["audio_folder"] = f"{len(unique_audio_folders)} {folder_word}"
    else:
        data["summary"]["audio_folder"] = audio_dir or (data.get("audio_roots", [None])[0] if data.get("audio_roots") else None)
    
    if len(unique_pred_files) > 1 and is_multi_selection:
        file_word = "file" if len(unique_pred_files) == 1 else "files"
        data["summary"]["predictions_file"] = f"{len(unique_pred_files)} {file_word}"
    else:
        data["summary"]["predictions_file"] = predictions_path

    # Diagnostic print
    print(f"DEBUG: Loaded {len(data['items'])} items, active: {data['summary'].get('active_date')}/{data['summary'].get('active_hydrophone')}")

    return data


def load_explore_mode(config: Dict, date_str: Optional[str] = None, hydrophone: Optional[str] = None) -> Dict:
    # If we are browsing a data directory, use the verify mode loading logic
    # which knows how to handle the DATE/DEVICE structure.
    if config.get("data", {}).get("data_dir"):
        data_dir = config.get("data", {}).get("data_dir")
        data = load_verify_mode(config, date_str, hydrophone, allow_unlabeled=True)
        labels_map = _collect_hierarchical_labels_map(data_dir, date_str, hydrophone)
        if labels_map and data.get("items"):
            for item in data.get("items", []):
                item_id = item.get("item_id")
                match = labels_map.get(item_id) or labels_map.get(_normalize_item_key(item_id))
                if not match:
                    continue
                annotations = item.get("annotations") or {
                    "labels": [],
                    "annotated_by": None,
                    "annotated_at": None,
                    "verified": False,
                    "notes": "",
                }
                annotations["labels"] = match.get("labels", [])
                annotations["notes"] = match.get("notes", "") or ""
                annotations["annotated_by"] = match.get("annotated_by")
                annotations["annotated_at"] = match.get("annotated_at")
                annotations["verified"] = bool(match.get("verified"))
                item["annotations"] = annotations

            summary = data.get("summary", {})
            summary["annotated"] = sum(
                1 for item in data.get("items", []) if (item.get("annotations") or {}).get("labels")
            )
            summary["verified"] = sum(
                1 for item in data.get("items", []) if (item.get("annotations") or {}).get("verified")
            )
            data["summary"] = summary
        return data
    
    # Otherwise fallback to standard label mode (configured folders)
    return load_label_mode(config)


def load_whale_mode(config: Dict) -> Dict:
    # Check multiple locations for predictions path (legacy whale section or verify section)
    whale_cfg = config.get("whale", {})
    verify_cfg = config.get("verify", {})
    predictions_path = whale_cfg.get("predictions_json") or verify_cfg.get("predictions_json")
    predictions_json = read_json(predictions_path) if predictions_path else {}

    # Get base path for resolving relative paths in predictions
    base_path = os.path.dirname(predictions_path) if predictions_path else None

    # Detect format and convert appropriately
    if is_unified_v2_format(predictions_json):
        data = convert_unified_v2_to_internal(predictions_json, base_path=base_path)
    else:
        # Legacy format
        data = convert_whale_predictions_to_unified(predictions_json)

    audio_roots = []
    if predictions_json:
        audio_roots.append(os.path.dirname(predictions_path))
    data["audio_roots"] = audio_roots
    return data


def load_dataset(config: Dict, mode: str, date_str: Optional[str] = None, hydrophone: Optional[str] = None) -> Dict:
    if mode == "label":
        return load_label_mode(config, date_str, hydrophone)
    if mode == "verify":
        return load_verify_mode(config, date_str, hydrophone)
    if mode == "explore":
        return load_explore_mode(config, date_str, hydrophone)
    if mode == "whale":
        return load_whale_mode(config)
    return {"items": [], "summary": {"total_items": 0}}
