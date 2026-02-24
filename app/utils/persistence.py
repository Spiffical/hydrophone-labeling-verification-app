from datetime import datetime, timezone
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
    ):
        if key in verification:
            out[key] = verification[key]

    out["label_decisions"] = _sanitize_label_decisions(verification.get("label_decisions"))
    return out


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


def save_verify_predictions(predictions_path: Optional[str], item_id: str, verification: Dict) -> Optional[Dict]:
    """Append a verification record to predictions.json (unified v2+ items array).

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

        verifications = item.get("verifications")
        if not isinstance(verifications, list):
            verifications = []

        stored_verification = _sanitize_verification_payload(verification)
        stored_verification["verification_round"] = len(verifications) + 1
        verifications.append(stored_verification)
        item["verifications"] = verifications
        break

    if stored_verification is None:
        return None

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(predictions_path, data)
    return stored_verification
