"""
Data structure discovery utilities.
Automatically detects folder structure and discovers spectrograms, audio, and predictions.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re


# Supported file extensions
SPECTROGRAM_EXTENSIONS = {'.mat', '.npy', '.png', '.jpg', '.jpeg'}
AUDIO_EXTENSIONS = {'.flac', '.wav', '.mp3', '.ogg'}
PREDICTION_FILENAMES = {'predictions.json', 'labels.json', 'annotations.json'}


def detect_data_structure(path: str) -> Dict:
    """
    Analyze a directory and return its structure type and discovered paths.
    
    Returns:
        {
            "structure_type": "hierarchical" | "device_only" | "flat" | "predictions" | "unknown",
            "dates": ["2026-01-19", ...],
            "devices": ["ICLISTENHF1951", ...],
            "spectrogram_folder": "/path/to/spectrograms" or None,
            "audio_folder": "/path/to/audio" or None,
            "predictions_file": "/path/to/predictions.json" or None,
            "spectrogram_extensions": [".mat", ".npy"],
            "spectrogram_count": 42,
            "audio_count": 42,
            "message": "Human-readable description of what was found"
        }
    """
    if not path or not os.path.exists(path):
        return {
            "structure_type": "unknown",
            "dates": [],
            "devices": [],
            "spectrogram_folder": None,
            "audio_folder": None,
            "predictions_file": None,
            "spectrogram_extensions": [],
            "spectrogram_count": 0,
            "audio_count": 0,
            "message": "Path does not exist"
        }

    if os.path.isfile(path):
        return {
            "structure_type": "unknown",
            "dates": [],
            "devices": [],
            "spectrogram_folder": None,
            "audio_folder": None,
            "predictions_file": None,
            "spectrogram_extensions": [],
            "spectrogram_count": 0,
            "audio_count": 0,
            "message": "Path is a file; please select a directory",
        }
    
    # Check for different structures
    hierarchical = _check_hierarchical_structure(path)
    if hierarchical["found"]:
        return hierarchical["result"]
    
    device_only = _check_device_only_structure(path)
    if device_only["found"]:
        return device_only["result"]
    
    flat = _check_flat_structure(path)
    if flat["found"]:
        return flat["result"]
    
    # Unknown structure
    return {
        "structure_type": "unknown",
        "dates": [],
        "devices": [],
        "spectrogram_folder": None,
        "audio_folder": None,
        "predictions_file": None,
        "spectrogram_extensions": [],
        "spectrogram_count": 0,
        "audio_count": 0,
        "message": "Could not detect data structure"
    }


def _is_date_folder(name: str) -> bool:
    """Check if folder name looks like a date (YYYY-MM-DD)."""
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', name))


def _is_device_folder(name: str) -> bool:
    """Check if folder name looks like a device ID."""
    # Common patterns: ICLISTENHF1234, hydrophone_01, device_001
    if name.startswith('.'):
        return False
    if name.lower() in {'audio', 'spectrograms', 'onc_spectrograms', 'images', 'data'}:
        return False
    return bool(re.match(r'^[A-Za-z0-9_-]+$', name))


def _find_spectrograms(folder: str, recursive: bool = False) -> Tuple[List[str], Dict[str, int]]:
    """Find spectrogram files in a folder."""
    files = []
    extensions = {}
    
    if not os.path.exists(folder):
        return files, extensions
    
    if recursive:
        for root, _, filenames in os.walk(folder):
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in SPECTROGRAM_EXTENSIONS:
                    files.append(os.path.join(root, f))
                    extensions[ext] = extensions.get(ext, 0) + 1
    else:
        for f in os.listdir(folder):
            ext = os.path.splitext(f)[1].lower()
            if ext in SPECTROGRAM_EXTENSIONS:
                files.append(os.path.join(folder, f))
                extensions[ext] = extensions.get(ext, 0) + 1
    
    return files, extensions


def _find_audio_folder(base_path: str, spectrogram_folder: str = None) -> Optional[str]:
    """
    Find audio folder near the spectrogram folder.
    
    Search order:
    1. Same folder as spectrograms (matching filenames)
    2. 'audio' subfolder in base_path
    3. 'audio' folder at same level as spectrogram folder
    """
    # Check for audio folder in base path
    audio_candidates = ['audio', 'Audio', 'AUDIO', 'wav', 'flac']
    
    for candidate in audio_candidates:
        audio_path = os.path.join(base_path, candidate)
        if os.path.isdir(audio_path):
            # Verify it has audio files
            for f in os.listdir(audio_path)[:10]:  # Check first 10
                if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                    return audio_path
    
    # Check same level as spectrogram folder
    if spectrogram_folder:
        parent = os.path.dirname(spectrogram_folder)
        for candidate in audio_candidates:
            audio_path = os.path.join(parent, candidate)
            if os.path.isdir(audio_path):
                for f in os.listdir(audio_path)[:10]:
                    if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                        return audio_path
    
    # Check for audio files in same folder as spectrograms
    if spectrogram_folder and os.path.exists(spectrogram_folder):
        for f in os.listdir(spectrogram_folder)[:20]:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                return spectrogram_folder
    
    return None


def _find_predictions_file(base_path: str) -> Optional[str]:
    """Find a predictions/labels JSON file."""
    # Check direct files first
    for filename in PREDICTION_FILENAMES:
        candidate = os.path.join(base_path, filename)
        if os.path.isfile(candidate):
            return candidate
    
    # Check subdirectories (one level)
    try:
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                for filename in PREDICTION_FILENAMES:
                    candidate = os.path.join(item_path, filename)
                    if os.path.isfile(candidate):
                        return candidate
    except Exception:
        pass
    
    return None


def _count_audio_files(folder: str) -> int:
    """Count audio files in a folder."""
    if not folder or not os.path.exists(folder):
        return 0
    
    count = 0
    try:
        for f in os.listdir(folder):
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                count += 1
    except Exception:
        pass
    return count


def _find_spectrogram_subfolder(base_path: str) -> Optional[str]:
    """Find a spectrogram subfolder like 'spectrograms', 'images', etc."""
    candidates = ['spectrograms', 'onc_spectrograms', 'mat_files', 'images', 'data', 'Spectrograms']
    
    for candidate in candidates:
        subfolder = os.path.join(base_path, candidate)
        if os.path.isdir(subfolder):
            # Verify it has spectrogram files
            files, _ = _find_spectrograms(subfolder)
            if files:
                return subfolder
    
    return None


def _build_hierarchy_detail(path: str, dates: List[str], devices: set) -> Dict:
    """
    Build detailed info for each date/device combination.

    Returns:
        {
            "2026-01-19": {
                "ICLISTENHF1951": {
                    "spectrogram_count": 42,
                    "audio_count": 38,
                    "has_labels_json": True,
                    "has_predictions_json": False,
                    "spectrogram_folder": "/path/to/spectrograms",
                    "audio_folder": "/path/to/audio"
                }
            }
        }
    """
    detail = {}

    for date in dates:
        detail[date] = {}
        date_path = os.path.join(path, date)

        try:
            for item in os.listdir(date_path):
                item_path = os.path.join(date_path, item)
                if os.path.isdir(item_path) and item in devices:
                    # Find spectrogram folder
                    spec_folder = _find_spectrogram_subfolder(item_path) or item_path
                    spec_files, _ = _find_spectrograms(spec_folder)

                    # Find audio folder
                    audio_folder = _find_audio_folder(item_path, spec_folder)
                    audio_count = _count_audio_files(audio_folder)

                    # Check for labels.json and predictions.json
                    labels_path = os.path.join(item_path, "labels.json")
                    predictions_path = os.path.join(item_path, "predictions.json")

                    detail[date][item] = {
                        "spectrogram_count": len(spec_files),
                        "audio_count": audio_count,
                        "has_labels_json": os.path.isfile(labels_path),
                        "has_predictions_json": os.path.isfile(predictions_path),
                        "spectrogram_folder": spec_folder if spec_files else None,
                        "audio_folder": audio_folder,
                    }
        except Exception:
            pass

    return detail


def _find_root_level_files(path: str) -> Dict:
    """
    Find labels.json and predictions.json at the root level.
    Also count how many exist in subfolders.
    """
    result = {
        "root_labels_file": None,
        "root_predictions_file": None,
        "subfolder_labels_count": 0,
        "subfolder_predictions_count": 0,
        "subfolder_labels_locations": [],
        "subfolder_predictions_locations": [],
    }

    # Check root level
    for filename in ["labels.json", "annotations.json"]:
        candidate = os.path.join(path, filename)
        if os.path.isfile(candidate):
            result["root_labels_file"] = candidate
            break

    for filename in ["predictions.json"]:
        candidate = os.path.join(path, filename)
        if os.path.isfile(candidate):
            result["root_predictions_file"] = candidate
            break

    # Count subfolder files (up to 2 levels deep: date/device)
    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                # Check date-level
                labels_at_date = os.path.join(item_path, "labels.json")
                if os.path.isfile(labels_at_date):
                    result["subfolder_labels_count"] += 1
                    result["subfolder_labels_locations"].append(labels_at_date)

                predictions_at_date = os.path.join(item_path, "predictions.json")
                if os.path.isfile(predictions_at_date):
                    result["subfolder_predictions_count"] += 1
                    result["subfolder_predictions_locations"].append(predictions_at_date)

                # Check device-level (inside date folders)
                try:
                    for subitem in os.listdir(item_path):
                        subitem_path = os.path.join(item_path, subitem)
                        if os.path.isdir(subitem_path):
                            labels_at_device = os.path.join(subitem_path, "labels.json")
                            if os.path.isfile(labels_at_device):
                                result["subfolder_labels_count"] += 1
                                result["subfolder_labels_locations"].append(labels_at_device)

                            predictions_at_device = os.path.join(subitem_path, "predictions.json")
                            if os.path.isfile(predictions_at_device):
                                result["subfolder_predictions_count"] += 1
                                result["subfolder_predictions_locations"].append(predictions_at_device)
                except Exception:
                    pass
    except Exception:
        pass

    return result


def _check_hierarchical_structure(path: str) -> Dict:
    """Check for DATE/DEVICE hierarchy."""
    dates = []
    devices = set()

    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path) and _is_date_folder(item):
                dates.append(item)
                # Look for device folders inside date folder
                for subitem in os.listdir(item_path):
                    subitem_path = os.path.join(item_path, subitem)
                    if os.path.isdir(subitem_path) and _is_device_folder(subitem):
                        devices.add(subitem)
    except Exception:
        pass

    if dates and devices:
        sorted_dates = sorted(dates, reverse=True)
        sorted_devices = sorted(devices)

        # Found hierarchical structure - get info from first date/device
        first_date = sorted_dates[0]
        first_device = sorted_devices[0]
        sample_path = os.path.join(path, first_date, first_device)

        # Find spectrograms
        spec_folder = _find_spectrogram_subfolder(sample_path) or sample_path
        spec_files, spec_exts = _find_spectrograms(spec_folder)

        # Find audio
        audio_folder = _find_audio_folder(sample_path, spec_folder)
        audio_count = _count_audio_files(audio_folder)

        # Find predictions (check root first, then sample path)
        root_files = _find_root_level_files(path)
        predictions = root_files["root_predictions_file"] or _find_predictions_file(sample_path)

        # Build hierarchy detail
        hierarchy_detail = _build_hierarchy_detail(path, sorted_dates, devices)

        # Calculate total spectrogram count across all folders
        total_spec_count = sum(
            device_info.get("spectrogram_count", 0)
            for date_data in hierarchy_detail.values()
            for device_info in date_data.values()
        )

        return {
            "found": True,
            "result": {
                "structure_type": "hierarchical",
                "dates": sorted_dates,
                "devices": sorted_devices,
                "spectrogram_folder": spec_folder,
                "audio_folder": audio_folder,
                "predictions_file": predictions,
                "spectrogram_extensions": list(spec_exts.keys()),
                "spectrogram_count": total_spec_count or len(spec_files),
                "audio_count": audio_count,
                "message": f"Found {len(dates)} dates, {len(devices)} devices",
                # New fields for enhanced display
                "hierarchy_detail": hierarchy_detail,
                "root_labels_file": root_files["root_labels_file"],
                "root_predictions_file": root_files["root_predictions_file"],
                "subfolder_labels_count": root_files["subfolder_labels_count"],
                "subfolder_predictions_count": root_files["subfolder_predictions_count"],
                "subfolder_labels_locations": root_files["subfolder_labels_locations"],
                "subfolder_predictions_locations": root_files["subfolder_predictions_locations"],
            }
        }

    return {"found": False}


def _check_device_only_structure(path: str) -> Dict:
    """Check for DEVICE-only folders (no date hierarchy)."""
    devices = []

    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path) and _is_device_folder(item):
                # Check if it has spectrograms or predictions
                spec_folder = _find_spectrogram_subfolder(item_path)
                if spec_folder:
                    devices.append(item)
                    continue

                # Check for direct spectrogram files
                files, _ = _find_spectrograms(item_path)
                if files:
                    devices.append(item)
                    continue

                # Check for predictions
                if _find_predictions_file(item_path):
                    devices.append(item)
    except Exception:
        pass

    if devices:
        sorted_devices = sorted(devices)
        first_device = sorted_devices[0]
        sample_path = os.path.join(path, first_device)

        spec_folder = _find_spectrogram_subfolder(sample_path) or sample_path
        spec_files, spec_exts = _find_spectrograms(spec_folder)
        audio_folder = _find_audio_folder(sample_path, spec_folder)
        audio_count = _count_audio_files(audio_folder)

        # Find root-level files
        root_files = _find_root_level_files(path)
        predictions = root_files["root_predictions_file"] or _find_predictions_file(sample_path)

        # Build device detail (similar to hierarchy_detail but without dates)
        device_detail = {}
        total_spec_count = 0
        for device in sorted_devices:
            device_path = os.path.join(path, device)
            device_spec_folder = _find_spectrogram_subfolder(device_path) or device_path
            device_spec_files, _ = _find_spectrograms(device_spec_folder)
            device_audio_folder = _find_audio_folder(device_path, device_spec_folder)
            device_audio_count = _count_audio_files(device_audio_folder)

            labels_path = os.path.join(device_path, "labels.json")
            predictions_path = os.path.join(device_path, "predictions.json")

            device_detail[device] = {
                "spectrogram_count": len(device_spec_files),
                "audio_count": device_audio_count,
                "has_labels_json": os.path.isfile(labels_path),
                "has_predictions_json": os.path.isfile(predictions_path),
                "spectrogram_folder": device_spec_folder if device_spec_files else None,
                "audio_folder": device_audio_folder,
            }
            total_spec_count += len(device_spec_files)

        return {
            "found": True,
            "result": {
                "structure_type": "device_only",
                "dates": [],
                "devices": sorted_devices,
                "spectrogram_folder": spec_folder,
                "audio_folder": audio_folder,
                "predictions_file": predictions,
                "spectrogram_extensions": list(spec_exts.keys()),
                "spectrogram_count": total_spec_count or len(spec_files),
                "audio_count": audio_count,
                "message": f"Found {len(devices)} devices",
                # New fields for enhanced display
                "device_detail": device_detail,
                "root_labels_file": root_files["root_labels_file"],
                "root_predictions_file": root_files["root_predictions_file"],
                "subfolder_labels_count": root_files["subfolder_labels_count"],
                "subfolder_predictions_count": root_files["subfolder_predictions_count"],
                "subfolder_labels_locations": root_files["subfolder_labels_locations"],
                "subfolder_predictions_locations": root_files["subfolder_predictions_locations"],
            }
        }

    return {"found": False}


def _check_flat_structure(path: str) -> Dict:
    """Check for flat folder with spectrogram files directly."""
    # Check for spectrogram subfolder first
    spec_folder = _find_spectrogram_subfolder(path)

    if spec_folder:
        spec_files, spec_exts = _find_spectrograms(spec_folder)
    else:
        # Check for direct spectrogram files
        spec_files, spec_exts = _find_spectrograms(path)
        if spec_files:
            spec_folder = path

    if not spec_files:
        return {"found": False}

    audio_folder = _find_audio_folder(path, spec_folder)
    audio_count = _count_audio_files(audio_folder)
    predictions = _find_predictions_file(path)

    # Check for root-level labels/predictions files
    root_labels = None
    root_predictions = None
    for filename in ["labels.json", "annotations.json"]:
        candidate = os.path.join(path, filename)
        if os.path.isfile(candidate):
            root_labels = candidate
            break
    for filename in ["predictions.json"]:
        candidate = os.path.join(path, filename)
        if os.path.isfile(candidate):
            root_predictions = candidate
            break

    ext_summary = ", ".join(f"{count} {ext}" for ext, count in spec_exts.items())

    return {
        "found": True,
        "result": {
            "structure_type": "flat",
            "dates": [],
            "devices": [],
            "spectrogram_folder": spec_folder,
            "audio_folder": audio_folder,
            "predictions_file": predictions or root_predictions,
            "spectrogram_extensions": list(spec_exts.keys()),
            "spectrogram_count": len(spec_files),
            "audio_count": audio_count,
            "message": f"Found {ext_summary}" + (f", {audio_count} audio {'file' if audio_count == 1 else 'files'}" if audio_count else ""),
            # Include root-level file info for consistency
            "root_labels_file": root_labels,
            "root_predictions_file": root_predictions,
            "subfolder_labels_count": 0,
            "subfolder_predictions_count": 0,
            "subfolder_labels_locations": [],
            "subfolder_predictions_locations": [],
        }
    }


def discover_items_from_folder(
    spectrogram_folder: str,
    audio_folder: Optional[str] = None,
    predictions_file: Optional[str] = None
) -> List[Dict]:
    """
    Discover items from a spectrogram folder.
    
    Returns a list of items compatible with the verification app format.
    """
    items = []
    
    if not spectrogram_folder or not os.path.exists(spectrogram_folder):
        return items
    
    # Get all spectrogram files
    spec_files, _ = _find_spectrograms(spectrogram_folder, recursive=True)
    
    for spec_path in spec_files:
        filename = os.path.basename(spec_path)
        stem = os.path.splitext(filename)[0]
        
        # Try to find matching audio file
        audio_path = None
        if audio_folder:
            for ext in AUDIO_EXTENSIONS:
                candidate = os.path.join(audio_folder, stem + ext)
                if os.path.exists(candidate):
                    audio_path = candidate
                    break
        
        item = {
            "item_id": stem,
            "spectrogram_path": spec_path,
            "audio_path": audio_path,
            "predictions": {},
            "annotations": None,
        }
        items.append(item)
    
    return items
