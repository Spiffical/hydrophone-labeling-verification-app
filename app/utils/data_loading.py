import glob
import os
from copy import deepcopy
from typing import Dict, Optional, Tuple

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


def _build_predictions_override_index(predictions_overrides: Optional[list]) -> Tuple[dict, dict, dict]:
    """Build indices for fast lookup of prediction overrides."""
    date_device = {}
    date_only = {}
    device_only = {}

    for entry in predictions_overrides or []:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not path:
            continue
        date = entry.get("date")
        device = entry.get("device")
        if date and device:
            date_device[(date, device)] = path
        elif date:
            date_only[date] = path
        elif device:
            device_only[device] = path

    return date_device, date_only, device_only


def _get_predictions_override_path(
    override_index: Tuple[dict, dict, dict],
    date: Optional[str],
    device: Optional[str],
) -> Optional[str]:
    """Resolve an override path for the given date/device."""
    date_device, date_only, device_only = override_index
    if date and device and (date, device) in date_device:
        return date_device[(date, device)]
    if date and date in date_only:
        return date_only[date]
    if device and device in device_only:
        return device_only[device]
    return None


def _has_spectrograms(folder: Optional[str]) -> bool:
    if not folder or not os.path.exists(folder):
        return False
    for pattern in ("*.mat", "*.npy", "*.png", "*.jpg", "*.jpeg"):
        if glob.glob(os.path.join(folder, pattern)):
            return True
    return False


def _find_first_hydrophone(dashboard_root: str, date_str: str) -> Optional[str]:
    if not dashboard_root or not date_str:
        return None
    date_dir = os.path.join(dashboard_root, date_str)
    if not os.path.exists(date_dir):
        return None
    hydrophones = [d for d in os.listdir(date_dir) if os.path.isdir(os.path.join(date_dir, d))]
    for device in sorted(hydrophones):
        base_path = os.path.join(date_dir, device)
        spec_folder = _get_spectrogram_folder(base_path)
        if _has_spectrograms(spec_folder):
            return device
    return sorted(hydrophones)[0] if hydrophones else None


def _find_first_device_with_data(root_path: str, devices: list, spec_folder_names: list) -> Optional[str]:
    for device in sorted(devices):
        base_path = os.path.join(root_path, device)
        spec_folder = _get_spectrogram_folder(base_path, spec_folder_names)
        if _has_spectrograms(spec_folder):
            return device
    return sorted(devices)[0] if devices else None


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


def _is_segment_item_id(item_id: Optional[str]) -> bool:
    if not isinstance(item_id, str) or "_seg" not in item_id:
        return False
    prefix, suffix = item_id.rsplit("_seg", 1)
    return bool(prefix) and suffix.isdigit()


def _item_matches_scope(item: dict, active_date: Optional[str], active_device: Optional[str]) -> bool:
    if not isinstance(item, dict):
        return False

    if active_device:
        device_code = item.get("device_code")
        if isinstance(device_code, str) and device_code and device_code != active_device:
            return False

    if active_date:
        item_date = item.get("date")
        if isinstance(item_date, str) and item_date and item_date != active_date:
            return False

    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if active_device:
        meta_device = metadata.get("hydrophone")
        if isinstance(meta_device, str) and meta_device and meta_device != active_device:
            return False
    if active_date:
        meta_date = metadata.get("date")
        if isinstance(meta_date, str) and meta_date and meta_date != active_date:
            return False

    path_values = []
    for key in ("mat_path", "spectrogram_path", "audio_path"):
        value = item.get(key)
        if isinstance(value, str) and value:
            path_values.append(value.replace("\\", "/"))

    if path_values:
        if active_date and not any(f"/{active_date}/" in p for p in path_values):
            return False
        if active_device and not any(f"/{active_device}/" in p for p in path_values):
            return False
        return True

    if active_date or active_device:
        has_scope_hint = any(
            bool(item.get(k))
            for k in ("date", "device_code")
        ) or any(bool(metadata.get(k)) for k in ("date", "hydrophone"))
        return has_scope_hint

    return True


def _item_dedupe_key(item: dict, index: int) -> str:
    if not isinstance(item, dict):
        return f"__index__{index}"

    item_id = item.get("item_id")
    if isinstance(item_id, str) and item_id.strip():
        return f"id::{item_id.strip()}"

    for path_key in ("spectrogram_path", "mat_path"):
        raw_path = item.get(path_key)
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        normalized = os.path.normcase(os.path.abspath(raw_path.strip()))
        return f"{path_key}::{normalized}"

    return f"__index__{index}"


def _merge_duplicate_items(primary: dict, incoming: dict) -> dict:
    if not isinstance(primary, dict):
        return deepcopy(incoming) if isinstance(incoming, dict) else primary
    if not isinstance(incoming, dict):
        return primary

    merged = primary

    # Fill in missing top-level fields while preserving the first-loaded item.
    for field in (
        "spectrogram_path",
        "mat_path",
        "audio_path",
        "device_code",
        "date",
        "predictions",
        "model_outputs",
        "verifications",
    ):
        existing_value = merged.get(field)
        incoming_value = incoming.get(field)
        if existing_value in (None, "", [], {}) and incoming_value not in (None, "", [], {}):
            merged[field] = incoming_value

    primary_ts = merged.get("timestamps")
    incoming_ts = incoming.get("timestamps")
    if not isinstance(primary_ts, dict):
        primary_ts = {}
    if isinstance(incoming_ts, dict):
        for key in ("start", "end"):
            if primary_ts.get(key) in (None, "") and incoming_ts.get(key) not in (None, ""):
                primary_ts[key] = incoming_ts.get(key)
    if primary_ts:
        merged["timestamps"] = primary_ts

    primary_annotations = merged.get("annotations")
    incoming_annotations = incoming.get("annotations")
    if not isinstance(primary_annotations, dict) and isinstance(incoming_annotations, dict):
        merged["annotations"] = deepcopy(incoming_annotations)
    elif isinstance(primary_annotations, dict) and isinstance(incoming_annotations, dict):
        for field in ("annotated_by", "annotated_at", "notes"):
            if not primary_annotations.get(field) and incoming_annotations.get(field):
                primary_annotations[field] = incoming_annotations.get(field)
        primary_annotations["verified"] = bool(primary_annotations.get("verified")) or bool(
            incoming_annotations.get("verified")
        )

        for field in ("labels", "rejected_labels"):
            base = primary_annotations.get(field)
            extra = incoming_annotations.get(field)
            if not isinstance(base, list):
                base = []
            if isinstance(extra, list):
                seen = set(base)
                for value in extra:
                    if value not in seen:
                        base.append(value)
                        seen.add(value)
            primary_annotations[field] = base

        base_extents = primary_annotations.get("label_extents")
        extra_extents = incoming_annotations.get("label_extents")
        if not isinstance(base_extents, dict):
            base_extents = {}
        if isinstance(extra_extents, dict):
            for label, extent in extra_extents.items():
                if label not in base_extents and isinstance(extent, dict):
                    base_extents[label] = extent
        if base_extents:
            primary_annotations["label_extents"] = base_extents

        merged["annotations"] = primary_annotations

    primary_metadata = merged.get("metadata")
    incoming_metadata = incoming.get("metadata")
    if not isinstance(primary_metadata, dict) and isinstance(incoming_metadata, dict):
        merged["metadata"] = deepcopy(incoming_metadata)
    elif isinstance(primary_metadata, dict) and isinstance(incoming_metadata, dict):
        for key, value in incoming_metadata.items():
            if key not in primary_metadata or primary_metadata.get(key) in (None, "", [], {}):
                primary_metadata[key] = value
        merged["metadata"] = primary_metadata

    return merged


def _dedupe_items(items: list) -> Tuple[list, int]:
    if not isinstance(items, list) or not items:
        return items or [], 0

    deduped = {}
    order = []
    removed = 0

    for idx, item in enumerate(items):
        key = _item_dedupe_key(item, idx)
        if key in deduped:
            deduped[key] = _merge_duplicate_items(deduped[key], item)
            removed += 1
        else:
            deduped[key] = deepcopy(item) if isinstance(item, dict) else item
            order.append(key)

    return [deduped[key] for key in order], removed


def _apply_item_deduplication(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return data

    items = data.get("items", [])
    deduped_items, removed = _dedupe_items(items)
    data["items"] = deduped_items

    summary = data.get("summary")
    if not isinstance(summary, dict):
        summary = {}

    summary["total_items"] = len(deduped_items)
    summary["annotated"] = sum(
        1
        for item in deduped_items
        if isinstance(item, dict) and (item.get("annotations") or {}).get("labels")
    )
    summary["verified"] = sum(
        1
        for item in deduped_items
        if isinstance(item, dict) and (item.get("annotations") or {}).get("verified")
    )
    if removed > 0:
        summary["duplicates_removed"] = removed
    else:
        summary.pop("duplicates_removed", None)

    data["summary"] = summary
    return data


def _build_audio_index(audio_dir: Optional[str]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    if not audio_dir or not os.path.exists(audio_dir):
        return index
    for entry in os.listdir(audio_dir):
        full_path = os.path.join(audio_dir, entry)
        if not os.path.isfile(full_path):
            continue
        ext = os.path.splitext(entry)[1].lower()
        if ext not in {".flac", ".wav", ".mp3", ".ogg"}:
            continue
        base_name = os.path.splitext(entry)[0]
        if base_name and base_name not in index:
            index[base_name] = full_path
    return index


def _resolve_audio_path_for_item(
    raw_path: Optional[str],
    *,
    base_path: Optional[str],
    audio_dir: Optional[str],
    predictions_path: Optional[str],
) -> Optional[str]:
    if not raw_path:
        return None
    if os.path.exists(raw_path):
        return raw_path

    candidates = []
    if not os.path.isabs(raw_path):
        if base_path:
            candidates.append(os.path.join(base_path, raw_path))
        if predictions_path:
            candidates.append(os.path.join(os.path.dirname(predictions_path), raw_path))
        if audio_dir:
            candidates.append(os.path.join(audio_dir, raw_path))
            candidates.append(os.path.join(audio_dir, os.path.basename(raw_path)))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _enrich_items_with_audio_paths(items: list, audio_dir: Optional[str], base_path: Optional[str] = None) -> None:
    if not items or not audio_dir or not os.path.exists(audio_dir):
        return

    audio_index = _build_audio_index(audio_dir)

    for item in items:
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata") or {}
        predictions_path = metadata.get("predictions_path") if isinstance(metadata, dict) else None
        current_audio = item.get("audio_path")
        resolved = _resolve_audio_path_for_item(
            current_audio,
            base_path=base_path,
            audio_dir=audio_dir,
            predictions_path=predictions_path,
        )
        if resolved:
            item["audio_path"] = resolved
            continue

        item_id = item.get("item_id")
        candidate_keys = [item_id, _normalize_item_key(item_id)]
        matched = None
        for key in candidate_keys:
            if key and key in audio_index:
                matched = audio_index[key]
                break

        # Segment-indexed items should only bind to exact filename matches.
        # Do not fallback to broad timestamp matching, which can assign the wrong segment.
        if not matched and _is_segment_item_id(item_id):
            continue

        if not matched:
            probe_name = None
            mat_path = item.get("mat_path")
            spec_path = item.get("spectrogram_path")
            if isinstance(mat_path, str) and mat_path:
                probe_name = os.path.basename(mat_path)
            elif isinstance(spec_path, str) and spec_path:
                probe_name = os.path.basename(spec_path)
            elif isinstance(item_id, str) and item_id:
                probe_name = item_id

            if probe_name:
                matches = find_matching_audio_files(probe_name, audio_dir)
                matched = get_representative_audio_file(matches)

        if matched:
            item["audio_path"] = matched


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
                rejected_labels = [
                    ld["label"] for ld in label_decisions
                    if ld.get("decision") == "rejected"
                ]
                label_extents = {}
                for ld in label_decisions:
                    if ld.get("decision") not in ("accepted", "added"):
                        continue
                    label = ld.get("label")
                    extent = ld.get("annotation_extent")
                    if isinstance(label, str) and isinstance(extent, dict):
                        label_extents[label] = extent
                entry = {
                    "labels": labels,
                    "notes": latest.get("notes", "") or "",
                    "annotated_by": latest.get("verified_by"),
                    "annotated_at": latest.get("verified_at"),
                    "verified": True,
                    "rejected_labels": rejected_labels,
                    "label_extents": label_extents,
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
                    "rejected_labels": annotations.get("rejected_labels", []) or [],
                    "label_extents": annotations.get("label_extents", {}) or {},
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
            "rejected_labels": entry.get("rejected_labels", []) if isinstance(entry, dict) else [],
            "label_extents": entry.get("label_extents", {}) if isinstance(entry, dict) else {},
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
    from app.utils.data_discovery import detect_data_structure
    
    label_cfg = config.get("label", {})
    data_cfg = config.get("data", {})
    structure_type = data_cfg.get("structure_type", "unknown")
    
    # Get configurable folder names
    spec_folder_names = data_cfg.get("spectrogram_folder_names", ["spectrograms", "onc_spectrograms", "mat_files"])
    audio_folder_names = data_cfg.get("audio_folder_names", ["audio"])
    
    data_dir = data_cfg.get("data_dir") or label_cfg.get("folder")
    folder = data_cfg.get("spectrogram_folder")
    labels_file = data_cfg.get("labels_file") or label_cfg.get("output_file")
    audio_folder = data_cfg.get("audio_folder") or label_cfg.get("audio_folder")

    # Auto-detect structure when config is missing/stale so top-level Load works
    # without requiring a manual "Reload data" or repeated folder browsing.
    if data_dir and structure_type in {"unknown", "flat", None, ""}:
        try:
            detected = detect_data_structure(data_dir).get("structure_type")
        except Exception:
            detected = None
        if detected in {"hierarchical", "device_only", "flat"}:
            if structure_type in {"unknown", None, ""} or (structure_type == "flat" and detected != "flat"):
                structure_type = detected
    
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
                annotations["rejected_labels"] = match.get("rejected_labels", []) or []
                annotations["label_extents"] = match.get("label_extents", {}) or {}
                item["annotations"] = annotations

    elif structure_type == "device_only" and data_dir:
        # Device-only structure (DATE folder selected as root)
        devices = []
        try:
            for item in os.listdir(data_dir):
                item_path = os.path.join(data_dir, item)
                if os.path.isdir(item_path) and not item.startswith("."):
                    devices.append(item)
        except Exception:
            devices = []

        devices = sorted(devices)
        if hydrophone == "__all__":
            devices_to_load = devices
        elif hydrophone:
            devices_to_load = [hydrophone]
        else:
            preferred_device = _find_first_device_with_data(data_dir, devices, spec_folder_names)
            devices_to_load = [preferred_device] if preferred_device else devices[:1]

        # Use date from selector when available, otherwise infer from root folder name.
        active_date_label = None
        if date_str and date_str not in ("__all__", "__flat__", "__device_only__"):
            active_date_label = date_str
        else:
            folder_name = os.path.basename(data_dir.rstrip(os.sep))
            if len(folder_name) == 10 and folder_name[4] == "-" and folder_name[7] == "-":
                active_date_label = folder_name

        all_items = []
        folders_loaded = []

        for dev in devices_to_load:
            if not dev:
                continue

            base_device_path = os.path.join(data_dir, dev)
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
            selected_labels_file = labels_file
            if os.path.exists(device_labels_file):
                selected_labels_file = device_labels_file

            if device_audio_folder and os.path.exists(device_audio_folder):
                audio_roots.append(device_audio_folder)

            items = _load_items_from_folder(
                spec_folder,
                device_audio_folder if device_audio_folder and os.path.exists(device_audio_folder) else None,
                selected_labels_file if selected_labels_file and os.path.exists(selected_labels_file) else None,
                dev,
                active_date_label,
            )
            all_items.extend(items)
            if spec_folder:
                folders_loaded.append(spec_folder)

        data["items"] = all_items
        data["_spec_folders_loaded"] = folders_loaded
        data["_audio_folders_loaded"] = [r for r in audio_roots]
        folder = ", ".join(folders_loaded[:3]) + ("..." if len(folders_loaded) > 3 else "") if folders_loaded else None

        # Overlay root-level labels.json when present (useful for shared labels at date root).
        root_labels = os.path.join(data_dir, "labels.json")
        root_labels_map = _extract_labels_map(read_json(root_labels) or {}) if os.path.exists(root_labels) else {}
        if root_labels_map and data["items"]:
            for item in data["items"]:
                item_id = item.get("item_id")
                match = root_labels_map.get(item_id) or root_labels_map.get(_normalize_item_key(item_id))
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
                annotations["rejected_labels"] = match.get("rejected_labels", []) or []
                annotations["label_extents"] = match.get("label_extents", {}) or {}
                item["annotations"] = annotations

        if not labels_file:
            labels_file = root_labels if os.path.exists(root_labels) else os.path.join(data_dir, "labels.json")

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
    predictions_overrides = data_cfg.get("predictions_overrides")
    override_index = _build_predictions_override_index(predictions_overrides)
    override_cache = {}

    def load_predictions_cached(predictions_path: str) -> Dict:
        if predictions_path in override_cache:
            return override_cache[predictions_path]
        whale_config = {"whale": {"predictions_json": predictions_path}}
        loaded = load_whale_mode(whale_config)
        _attach_predictions_path(loaded.get("items", []), predictions_path)
        override_cache[predictions_path] = loaded
        return loaded
    
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
                            "rejected_labels": [],
                            "notes": "",
                        },
                        "metadata": {},
                    })
            
            data["summary"]["total_items"] = len(data["items"])

        _enrich_items_with_audio_paths(data.get("items", []), audio_dir, base_path=mat_dir)
    
    elif dashboard_root and structure_type == "device_only":
        # Device-only structure (DATE folder selected as root)
        devices = []
        try:
            for item in os.listdir(dashboard_root):
                item_path = os.path.join(dashboard_root, item)
                if os.path.isdir(item_path) and not item.startswith("."):
                    devices.append(item)
        except Exception:
            devices = []

        devices = sorted(devices)
        if hydrophone == "__all__":
            devices_to_load = devices
        elif hydrophone:
            devices_to_load = [hydrophone]
        else:
            preferred_device = _find_first_device_with_data(dashboard_root, devices, spec_folder_names)
            devices_to_load = [preferred_device] if preferred_device else devices[:1]

        # Use date label from folder name if it looks like YYYY-MM-DD
        folder_name = os.path.basename(dashboard_root)
        active_date_label = folder_name if len(folder_name) == 10 and folder_name[4] == '-' and folder_name[7] == '-' else None

        all_items = []
        audio_roots = []

        # Cascading predictions: override > root-level > device-level
        root_predictions_path = None
        root_data = None

        if predictions_file_override and os.path.exists(predictions_file_override):
            whale_config = {"whale": {"predictions_json": predictions_file_override}}
            root_data = load_whale_mode(whale_config)
            predictions_path = predictions_file_override
            predictions_paths_loaded.append(predictions_file_override)
            _attach_predictions_path(root_data.get("items", []), predictions_path)
        else:
            root_pred_candidate = os.path.join(dashboard_root, "predictions.json")
            if os.path.exists(root_pred_candidate):
                root_predictions_path = root_pred_candidate
                whale_config = {"whale": {"predictions_json": root_pred_candidate}}
                root_data = load_whale_mode(whale_config)
                predictions_path = root_pred_candidate
                predictions_paths_loaded.append(root_pred_candidate)
                _attach_predictions_path(root_data.get("items", []), predictions_path)

        root_items = root_data.get("items", []) if root_data else []
        root_has_device = any(item.get("device_code") for item in root_items)

        for active_device in devices_to_load:
            if not active_device:
                continue

            base_path = os.path.join(dashboard_root, active_device)
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

            folder_data = {"items": [], "summary": {}}

            override_path = None
            if not predictions_file_override:
                override_path = _get_predictions_override_path(override_index, active_date_label, active_device)

            if override_path and os.path.exists(override_path):
                override_data = load_predictions_cached(override_path)
                filtered_override_items = [
                    deepcopy(i)
                    for i in override_data.get("items", [])
                    if _item_matches_scope(i, active_date_label, active_device)
                ]
                folder_data = {"items": filtered_override_items, "summary": {}}
                predictions_paths_loaded.append(override_path)
            elif root_data:
                filtered = [
                    deepcopy(i)
                    for i in root_items
                    if _item_matches_scope(i, active_date_label, active_device)
                ]
                if not filtered and not root_has_device:
                    # Legacy fallback: if root predictions have no scope info at all, only show once.
                    filtered = [deepcopy(i) for i in root_items] if active_device == devices_to_load[0] else []
                folder_data = {"items": filtered, "summary": {}}
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
                    folder_data = convert_hydrophonedashboard_to_unified(labels_json, active_date_label, active_device, image_dir)

            # Enrich items with spectrogram/mat file paths
            spec_files = []
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

            if local_audio_dir and os.path.exists(local_audio_dir):
                _enrich_items_with_audio_paths(folder_data.get("items", []), local_audio_dir, base_path=base_path)
                audio_roots.append(local_audio_dir)
                audio_folders_loaded.append(local_audio_dir)

            all_items.extend(folder_data.get("items", []))

        data["items"] = all_items
        data["summary"]["total_items"] = len(all_items)
        data["summary"]["active_date"] = active_date_label
        data["summary"]["active_hydrophone"] = "All" if hydrophone == "__all__" else (devices_to_load[0] if devices_to_load else None)
        data["audio_roots"] = list(set(audio_roots))

        # When showing summary, use the actual folders based on selection
        if len(devices_to_load) == 1:
            single_base = os.path.join(dashboard_root, devices_to_load[0])
            mat_dir = _get_spectrogram_folder(single_base, spec_folder_names) if os.path.exists(single_base) else None
            audio_dir = None
            for audio_name in audio_folder_names:
                candidate = os.path.join(single_base, audio_name)
                if os.path.exists(candidate):
                    audio_dir = candidate
                    break
            if predictions_file_override:
                predictions_path = predictions_file_override
            elif root_predictions_path:
                predictions_path = root_predictions_path
            else:
                predictions_path = predictions_paths_loaded[0] if predictions_paths_loaded else None
        else:
            mat_dir = mat_dirs_loaded[0] if mat_dirs_loaded else None
            audio_dir = audio_roots[0] if audio_roots else None
            predictions_path = predictions_paths_loaded[0] if predictions_paths_loaded else None

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

        date_device_overrides, date_overrides, _device_overrides = override_index
        
        for active_date in dates_to_load:
            if not active_date:
                continue
            
            date_override_path = None
            date_override_data = None
            if not predictions_file_override:
                date_override_path = date_overrides.get(active_date)
                if date_override_path and os.path.exists(date_override_path):
                    date_override_data = load_predictions_cached(date_override_path)
                    predictions_paths_loaded.append(date_override_path)

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

                device_override_path = None
                if not predictions_file_override:
                    device_override_path = date_device_overrides.get((active_date, active_device))

                if device_override_path and os.path.exists(device_override_path):
                    override_data = load_predictions_cached(device_override_path)
                    filtered_override_items = [
                        deepcopy(i)
                        for i in override_data.get("items", [])
                        if _item_matches_scope(i, active_date, active_device)
                    ]
                    folder_data = {"items": filtered_override_items, "summary": {}}
                    predictions_paths_loaded.append(device_override_path)
                elif date_override_data:
                    filtered_date_override_items = [
                        deepcopy(i)
                        for i in date_override_data.get("items", [])
                        if _item_matches_scope(i, active_date, active_device)
                    ]
                    if not filtered_date_override_items and active_device == devices_to_load[0]:
                        filtered_date_override_items = [deepcopy(i) for i in date_override_data.get("items", [])]
                    folder_data = {"items": filtered_date_override_items, "summary": {}}
                elif root_data:
                    filtered_root_items = [
                        deepcopy(i)
                        for i in root_data.get("items", [])
                        if _item_matches_scope(i, active_date, active_device)
                    ]
                    if (
                        not filtered_root_items
                        and active_date == dates_to_load[0]
                        and active_device == devices_to_load[0]
                    ):
                        filtered_root_items = [deepcopy(i) for i in root_data.get("items", [])]
                    folder_data = {"items": filtered_root_items, "summary": {}}
                elif date_data:
                    filtered_date_items = [
                        deepcopy(i)
                        for i in date_data.get("items", [])
                        if _item_matches_scope(i, active_date, active_device)
                    ]
                    if not filtered_date_items and active_device == devices_to_load[0]:
                        filtered_date_items = [deepcopy(i) for i in date_data.get("items", [])]
                    folder_data = {"items": filtered_date_items, "summary": {}}
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
                                "rejected_labels": [],
                                "notes": "",
                            },
                            "metadata": {"date": active_date, "hydrophone": active_device},
                        })
                        existing_ids.add(item_id)
                        existing_ids.add(filename)

                _enrich_items_with_audio_paths(folder_data.get("items", []), local_audio_dir, base_path=base_path)
                
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
                annotations["rejected_labels"] = match.get("rejected_labels", []) or []
                annotations["label_extents"] = match.get("label_extents", {}) or {}
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
    data: Dict
    if mode == "label":
        data = load_label_mode(config, date_str, hydrophone)
    elif mode == "verify":
        data = load_verify_mode(config, date_str, hydrophone)
    elif mode == "explore":
        data = load_explore_mode(config, date_str, hydrophone)
    elif mode == "whale":
        data = load_whale_mode(config)
    else:
        data = {"items": [], "summary": {"total_items": 0}}
    return _apply_item_deduplication(data)
