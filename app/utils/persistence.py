from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.utils.file_io import read_json, write_json


def save_label_mode(
    output_file: Optional[str],
    item_id: str,
    labels: List[str],
    annotated_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Save labels for an item to a labels.json file."""
    if not output_file:
        return
    
    # Use label_operations for proper file locking
    from app.utils.label_operations import save_labels
    save_labels(output_file, item_id, labels, annotated_by=annotated_by, notes=notes)


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

        stored_verification = dict(verification)
        stored_verification["verification_round"] = len(verifications) + 1
        verifications.append(stored_verification)
        item["verifications"] = verifications
        break

    if stored_verification is None:
        return None

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(predictions_path, data)
    return stored_verification
