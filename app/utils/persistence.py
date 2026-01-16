from datetime import datetime
import os
from typing import List, Optional

from app.utils.file_io import read_json, write_json


def save_label_mode(output_file: Optional[str], item_id: str, labels: List[str]) -> None:
    if not output_file:
        return
    data = read_json(output_file)
    data[item_id] = labels
    write_json(output_file, data)


def save_verify_mode(dashboard_root: Optional[str], date_str: Optional[str], hydrophone: Optional[str],
                     item_id: str, labels: List[str], username: Optional[str] = None,
                     role: Optional[str] = None) -> None:
    if not dashboard_root or not date_str or not hydrophone:
        return

    labels_path = os.path.join(dashboard_root, date_str, hydrophone, "labels.json")
    data = read_json(labels_path)

    entry = data.get(item_id)
    if isinstance(entry, list):
        entry = {
            "predicted_labels": entry,
            "probabilities": {},
            "verified_labels": None,
            "verified_by": None,
            "verified_at": None,
            "notes": "",
            "t0": "",
            "t1": "",
            "hydrophone": hydrophone,
        }
    elif entry is None:
        entry = {
            "predicted_labels": [],
            "probabilities": {},
            "verified_labels": None,
            "verified_by": None,
            "verified_at": None,
            "notes": "",
            "t0": "",
            "t1": "",
            "hydrophone": hydrophone,
        }

    entry["verified_labels"] = labels
    entry["verified_by"] = username or "anonymous"
    if role:
        entry["verified_role"] = role
    entry["verified_at"] = datetime.now().isoformat()

    data[item_id] = entry
    write_json(labels_path, data)
