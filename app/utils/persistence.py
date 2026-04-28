from datetime import datetime, timezone
import os
from copy import deepcopy
from typing import Dict, List, Optional

from app.utils.file_io import read_json, write_json


def _sanitize_label_decisions(label_decisions: Optional[List[Dict]]) -> List[Dict]:
    cleaned: List[Dict] = []
    if not isinstance(label_decisions, list):
        return cleaned

    for entry in label_decisions:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        decision = entry.get("decision")
        if not isinstance(label, str) or not label.strip():
            continue
        if decision not in {"accepted", "rejected", "added"}:
            continue

        sanitized = {
            "label": label.strip(),
            "decision": decision,
            "threshold_used": entry.get("threshold_used"),
        }
        extent = entry.get("annotation_extent")
        if isinstance(extent, dict):
            sanitized["annotation_extent"] = extent
        cleaned.append(sanitized)
    return cleaned


def _sanitize_verification_payload(verification: Dict) -> Dict:
    if not isinstance(verification, dict):
        return {}

    out: Dict = {}
    for key in (
        "verified_at",
        "verified_by",
        "verification_status",
        "confidence",
        "notes",
        "label_source",
        "reviewer_affiliation",
        "taxonomy_version",
        "date",
        "hydrophone",
        "device",
        "device_code",
    ):
        if key in verification:
            out[key] = verification[key]

    out["label_decisions"] = _sanitize_label_decisions(verification.get("label_decisions"))
    return out


def _append_verification_to_item(item: Dict, verification: Dict) -> Dict:
    """Append a sanitized verification to one JSON item and return the stored record."""
    verifications = item.get("verifications")
    if not isinstance(verifications, list):
        verifications = []

    stored_verification = _sanitize_verification_payload(verification)
    stored_verification["verification_round"] = len(verifications) + 1
    verifications.append(stored_verification)
    item["verifications"] = verifications
    return stored_verification


def _strict_predictions_path_for(active_predictions_path: str) -> Optional[str]:
    """Return sibling strict O3 predictions.json for an app sidecar, if present."""
    if not active_predictions_path:
        return None
    normalized = os.path.abspath(active_predictions_path)
    if os.path.basename(normalized) == "predictions.json":
        return None
    candidate = os.path.join(os.path.dirname(normalized), "predictions.json")
    if os.path.exists(candidate):
        return candidate
    return None


def _strict_target_indexes(items: List[Dict], item_id: str, source_item: Optional[Dict]) -> List[int]:
    """Map one app review item to its strict O3 item(s).

    Non-split events usually share the same item_id. Cross-source merged events
    are split in strict O3 as "<app item_id>__source_*".
    """
    if not item_id:
        return []

    direct = [i for i, item in enumerate(items) if item.get("item_id") == item_id]
    if direct:
        return direct

    prefix = f"{item_id}__source_"
    prefixed = [i for i, item in enumerate(items) if str(item.get("item_id", "")).startswith(prefix)]
    if prefixed:
        return prefixed

    source_segments = []
    if isinstance(source_item, dict):
        source_segments = source_item.get("source_segments") or []
    source_audio_names = {
        segment.get("source_audio")
        for segment in source_segments
        if isinstance(segment, dict) and segment.get("source_audio")
    }
    if not source_audio_names:
        return []

    return [
        i
        for i, item in enumerate(items)
        if str(item.get("item_id", "")).startswith(item_id)
        and isinstance(item.get("source_audio"), dict)
        and item["source_audio"].get("file_name") in source_audio_names
    ]


def _mirror_verification_to_strict_predictions(
    active_predictions_path: str,
    item_id: str,
    verification: Dict,
    source_item: Optional[Dict],
) -> int:
    """Mirror an app-side verification into sibling strict O3 predictions.json.

    Returns the number of strict O3 items updated. Missing strict files or
    unmatched items are intentionally non-fatal so review saves still succeed.
    """
    strict_path = _strict_predictions_path_for(active_predictions_path)
    if not strict_path:
        return 0

    data = read_json(strict_path)
    items = data.get("items")
    if not isinstance(items, list):
        return 0

    target_indexes = _strict_target_indexes(items, item_id, source_item)
    if not target_indexes:
        return 0

    for index in target_indexes:
        _append_verification_to_item(items[index], deepcopy(verification))

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(strict_path, data)
    return len(target_indexes)


def save_label_mode(
    output_file: Optional[str],
    item_id: str,
    labels: List[str],
    annotated_by: Optional[str] = None,
    notes: Optional[str] = None,
    label_extents: Optional[Dict[str, dict]] = None,
) -> None:
    """Save labels for an item to a labels.json file."""
    if not output_file:
        return
    
    # Use label_operations for proper file locking
    from app.utils.label_operations import save_labels
    save_labels(
        output_file,
        item_id,
        labels,
        annotated_by=annotated_by,
        notes=notes,
        label_extents=label_extents,
    )


def save_verify_predictions(
    predictions_path: Optional[str],
    item_id: str,
    verification: Dict,
    source_item: Optional[Dict] = None,
) -> Optional[Dict]:
    """Append a verification record to predictions.json (unified v2+ items array).

    When the active review file is an app sidecar such as
    predictions_postprocessed.app.json, also mirror the verification into the
    sibling strict O3 predictions.json. A merged app event may map to multiple
    strict source-audio items.

    Returns the stored verification (with verification_round) on success, otherwise None.
    """
    if not predictions_path:
        return None

    data = read_json(predictions_path)
    items = data.get("items")
    if not isinstance(items, list):
        return None

    stored_verification = None
    for item in items:
        if item.get("item_id") != item_id:
            continue

        stored_verification = _append_verification_to_item(item, verification)
        break

    if stored_verification is None:
        return None

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(predictions_path, data)
    _mirror_verification_to_strict_predictions(
        predictions_path,
        item_id,
        verification,
        source_item,
    )
    return stored_verification
