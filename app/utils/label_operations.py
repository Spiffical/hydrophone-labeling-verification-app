"""
Label file operations for the labeling verification app.
Handles reading and writing labels.json files with proper locking.

Output uses the unified O3 schema: items[].verifications[].label_decisions[]
so both label and verify modes produce the same structure.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Optional
from filelock import FileLock

# Create a FileLock instance at module level
_lock_file = os.path.join(tempfile.gettempdir(), 'hydrophone_labels_lock.lock')
_file_lock = FileLock(_lock_file)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_item_key(key: Optional[str]) -> Optional[str]:
    if not key:
        return key
    lower_key = key.lower()
    for ext in (".mat", ".npy", ".png", ".jpg", ".jpeg", ".wav", ".flac", ".mp3"):
        if lower_key.endswith(ext):
            return key[: -len(ext)]
    return key


def _labels_from_verifications(verifications: list) -> List[str]:
    """Extract current labels from the latest verification round."""
    if not verifications:
        return []
    latest = verifications[-1]
    label_decisions = latest.get("label_decisions", [])
    return [
        ld["label"] for ld in label_decisions
        if ld.get("decision") in ("accepted", "added")
    ]


def _labels_from_annotations(annotations: dict) -> List[str]:
    """Extract labels from legacy annotations object."""
    if not annotations:
        return []
    return annotations.get("labels") or []


def load_labels(filepath: str) -> Dict[str, List[str]]:
    """
    Load labels from a JSON file.

    Supports unified verifications format, legacy annotations format,
    and legacy flat mapping format.
    """
    if not filepath or not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, "r") as f:
            data = json.load(f)

        if isinstance(data, dict) and isinstance(data.get("items"), list):
            normalized: Dict[str, List[str]] = {}
            for item in data.get("items", []):
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id")
                if not item_id:
                    continue

                # Prefer verifications (unified format)
                verifications = item.get("verifications")
                if verifications and isinstance(verifications, list):
                    labels = _labels_from_verifications(verifications)
                else:
                    # Fallback to legacy annotations
                    annotations = item.get("annotations") or {}
                    labels = _labels_from_annotations(annotations)

                normalized[item_id] = labels if isinstance(labels, list) else []
            return normalized

        # Legacy mapping format
        normalized = {}
        if isinstance(data, dict):
            for filename, labels in data.items():
                if isinstance(labels, list):
                    normalized[filename] = labels
                else:
                    normalized[filename] = [str(labels)]
        return normalized
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading labels from {filepath}: {e}")
        return {}


def save_labels(
    filepath: str,
    filename: str,
    labels: List[str],
    annotated_by: Optional[str] = None,
    annotated_at: Optional[str] = None,
    notes: Optional[str] = None,
    verified: Optional[bool] = None,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Save or update labels for a specific file using unified verifications format.

    Labels are stored as verifications[].label_decisions[] with decision="added"
    and threshold_used=null (no model). Legacy files are upgraded on write.
    """
    with _file_lock:
        # Load existing data
        current_data: dict = {}
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            try:
                with open(filepath, "r") as f:
                    current_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                current_data = {}

        # Initialize unified structure
        if isinstance(current_data, dict) and isinstance(current_data.get("items"), list):
            data = current_data
        else:
            data = {
                "schema_version": "2.0",
                "created_at": _now_iso(),
                "task_type": "classification",
                "items": [],
            }

            # Upgrade legacy mapping entries into items
            if isinstance(current_data, dict):
                items = []
                for key, entry in current_data.items():
                    if not key or not isinstance(entry, (list, str)):
                        continue
                    label_list = entry if isinstance(entry, list) else [str(entry)]
                    item_id = _normalize_item_key(key) or key
                    # Convert legacy labels to verifications format
                    verification = {
                        "verified_at": _now_iso(),
                        "verified_by": "migrated",
                        "verification_round": 1,
                        "verification_status": "verified",
                        "label_decisions": [
                            {"label": lbl, "decision": "added", "threshold_used": None}
                            for lbl in label_list
                        ],
                        "label_source": "expert",
                        "notes": "",
                    }
                    items.append({
                        "item_id": item_id,
                        "verifications": [verification] if label_list else [],
                    })
                data["items"] = items

        data.setdefault("schema_version", "2.0")
        data.setdefault("created_at", _now_iso())
        data.setdefault("task_type", "classification")
        data["updated_at"] = _now_iso()

        items = data.get("items") or []
        normalized_filename = _normalize_item_key(filename) or filename

        existing_item = None
        for item in items:
            item_id = item.get("item_id")
            if item_id == filename or item_id == normalized_filename:
                existing_item = item
                break
            if _normalize_item_key(item_id) == normalized_filename:
                existing_item = item
                break

        if existing_item is None:
            existing_item = {"item_id": filename}
            items.append(existing_item)
        else:
            existing_item["item_id"] = filename

        # Migrate legacy annotations to verifications if present
        if "annotations" in existing_item and "verifications" not in existing_item:
            old_ann = existing_item.pop("annotations", {})
            old_labels = old_ann.get("labels") or []
            if old_labels:
                existing_item["verifications"] = [{
                    "verified_at": old_ann.get("annotated_at") or _now_iso(),
                    "verified_by": old_ann.get("annotated_by") or "migrated",
                    "verification_round": 1,
                    "verification_status": "verified",
                    "label_decisions": [
                        {"label": lbl, "decision": "added", "threshold_used": None}
                        for lbl in old_labels
                    ],
                    "label_source": "expert",
                    "notes": old_ann.get("notes", ""),
                }]
            else:
                existing_item["verifications"] = []

        # Build the new verification entry
        verifications = existing_item.get("verifications") or []
        now = annotated_at or _now_iso()
        by = annotated_by or "anonymous"

        # Determine note text: use provided notes, or preserve from latest verification
        if notes is not None:
            note_text = notes or ""
        elif verifications:
            note_text = verifications[-1].get("notes", "")
        else:
            note_text = ""

        label_list = labels if isinstance(labels, list) else []

        if label_list or note_text:
            new_verification = {
                "verified_at": now,
                "verified_by": by,
                "verification_round": len(verifications) + 1,
                "verification_status": "verified",
                "label_decisions": [
                    {"label": lbl, "decision": "added", "threshold_used": None}
                    for lbl in label_list
                ],
                "label_source": "expert",
                "notes": note_text,
            }
            verifications.append(new_verification)
            existing_item["verifications"] = verifications
        else:
            # No labels and no notes — remove item
            data["items"] = [item for item in items if item is not existing_item]

        if metadata:
            existing_item["metadata"] = metadata

        data["items"] = data.get("items") or items

        # Build summary
        summary = data.get("summary", {})
        summary["total_items"] = len(data["items"])
        summary["annotated"] = sum(
            1 for item in data["items"]
            if _labels_from_verifications(item.get("verifications") or [])
        )
        summary["verified"] = summary["annotated"]  # all manual labels are "verified"
        data["summary"] = summary

        try:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, sort_keys=False)
            return True
        except IOError as e:
            print(f"Error saving labels to {filepath}: {e}")
            return False


def add_label(filepath: str, filename: str, label: str) -> bool:
    """Add a single label to a file's labels."""
    current_data = load_labels(filepath)
    labels = current_data.get(filename, [])

    if label not in labels:
        labels.append(label)

    return save_labels(filepath, filename, labels)


def remove_label(filepath: str, filename: str, label: str) -> bool:
    """Remove a single label from a file's labels."""
    current_data = load_labels(filepath)
    labels = current_data.get(filename, [])

    if label in labels:
        labels.remove(label)

    return save_labels(filepath, filename, labels)


def save_labels_unlocked(filepath: str, current_data: Dict, filename: str, labels: List[str]) -> bool:
    """Internal function to save labels without acquiring lock (caller must hold lock)."""
    return save_labels(filepath, filename, labels)


def get_labels_for_file(filepath: str, filename: str) -> List[str]:
    """Get labels for a specific file."""
    data = load_labels(filepath)
    return data.get(filename, [])


def get_default_labels_path(spectrogram_folder: str) -> str:
    """
    Get the default labels.json path for a spectrogram folder.

    For hierarchical structures: DATE/DEVICE/labels.json
    For flat structures: FOLDER/labels.json
    """
    if not spectrogram_folder:
        return ""

    # If spectrogram_folder ends with "onc_spectrograms", put labels.json at the device level
    if spectrogram_folder.endswith("onc_spectrograms"):
        parent = os.path.dirname(spectrogram_folder)
        return os.path.join(parent, "labels.json")

    # Otherwise put it in the same folder
    return os.path.join(spectrogram_folder, "labels.json")


def get_smart_labels_path(
    data_root: str,
    structure_type: str,
    existing_root_labels: Optional[str] = None,
    subfolder_labels_count: int = 0,
    date_filter: Optional[str] = None,
    device_filter: Optional[str] = None,
) -> tuple:
    """
    Determine the best labels.json path based on context.

    Priority order:
    1. Existing root-level labels.json
    2. For hierarchical structures: root-level by default
    3. For flat structures: data_root/labels.json
    """
    if not data_root:
        return "", "No data directory set"

    # If root-level labels.json exists, use it
    if existing_root_labels and os.path.isfile(existing_root_labels):
        return existing_root_labels, "Using existing root-level labels.json"

    # Check for root-level file
    root_labels_path = os.path.join(data_root, "labels.json")
    if os.path.isfile(root_labels_path):
        return root_labels_path, "Using existing root-level labels.json"

    # For hierarchical or device_only structures
    if structure_type in ("hierarchical", "device_only"):
        if subfolder_labels_count > 0:
            return (
                root_labels_path,
                f"Found {subfolder_labels_count} labels.json in subfolders. "
                "Consider consolidating to root-level for consistency."
            )
        else:
            return root_labels_path, "New labels will be saved to root-level labels.json"

    # For flat structures - just use the data root
    return root_labels_path, "Labels will be saved to labels.json"


def get_path_for_filter(
    data_root: str,
    structure_type: str,
    date_filter: Optional[str],
    device_filter: Optional[str],
    path_type: str = "spectrogram"
) -> tuple:
    """
    Get the appropriate path display based on current filter selection.
    """
    if not data_root:
        return "Not set", ""

    # Flat structure - just return the root
    if structure_type == "flat" or date_filter == "__flat__":
        return data_root, ""

    # Hierarchical structure
    if structure_type == "hierarchical":
        if date_filter == "__all__" and device_filter == "__all__":
            return f"{data_root}/*/*/", "All dates and devices"
        elif date_filter == "__all__":
            return f"{data_root}/*/{device_filter}/", f"All dates, device: {device_filter}"
        elif device_filter == "__all__":
            return f"{data_root}/{date_filter}/*/", f"Date: {date_filter}, all devices"
        else:
            return os.path.join(data_root, date_filter, device_filter), ""

    # Device-only structure
    if structure_type == "device_only":
        if device_filter == "__all__":
            return f"{data_root}/*/", "All devices"
        else:
            return os.path.join(data_root, device_filter), ""

    return data_root, ""
