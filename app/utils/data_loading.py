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


def load_label_mode(config: Dict) -> Dict:
    label_cfg = config.get("label", {})
    folder = label_cfg.get("folder")
    output_file = label_cfg.get("output_file")
    audio_folder = label_cfg.get("audio_folder")

    labels = read_json(output_file) if output_file else {}
    data = convert_legacy_labeling_to_unified(labels, folder or "")

    if folder and os.path.exists(folder):
        mat_files = sorted(glob.glob(os.path.join(folder, "*.mat")))
        items_by_id = {item["item_id"]: item for item in data["items"]}
        for mat_path in mat_files:
            filename = os.path.basename(mat_path)
            if filename not in items_by_id:
                items_by_id[filename] = {
                    "item_id": filename,
                    "spectrogram_path": None,
                    "mat_path": mat_path,
                    "audio_path": None,
                    "timestamps": {"start": None, "end": None},
                    "device_code": None,
                    "predictions": None,
                    "annotations": {
                        "labels": [],
                        "annotated_by": None,
                        "annotated_at": None,
                        "verified": False,
                        "notes": "",
                    },
                    "metadata": {},
                }

            if audio_folder:
                matches = find_matching_audio_files(filename, audio_folder)
                if matches:
                    items_by_id[filename]["audio_path"] = get_representative_audio_file(matches)

        data["items"] = list(items_by_id.values())
        data["summary"]["total_items"] = len(data["items"])
        data["summary"]["annotated"] = sum(1 for item in data["items"]
                                           if item.get("annotations", {}).get("labels"))
        data["summary"]["verified"] = sum(1 for item in data["items"]
                                          if item.get("annotations", {}).get("verified"))

    data["audio_roots"] = [audio_folder] if audio_folder else []
    return data


def load_verify_mode(config: Dict) -> Dict:
    verify_cfg = config.get("verify", {})
    dashboard_root = verify_cfg.get("dashboard_root")
    date_str = verify_cfg.get("date") or _find_latest_date(dashboard_root)
    hydrophone = verify_cfg.get("hydrophone") or _find_first_hydrophone(dashboard_root, date_str)

    labels_path = None
    image_dir = None
    labels_json = {}

    if dashboard_root and date_str and hydrophone:
        labels_path = os.path.join(dashboard_root, date_str, hydrophone, "labels.json")
        image_dir = os.path.join(dashboard_root, date_str, hydrophone, "images")
        labels_json = read_json(labels_path)

    data = convert_hydrophonedashboard_to_unified(labels_json, date_str, hydrophone, image_dir or "")
    data["audio_roots"] = []
    return data


def load_explore_mode(config: Dict) -> Dict:
    # For now, reuse label mode data for browsing.
    return load_label_mode(config)


def load_whale_mode(config: Dict) -> Dict:
    whale_cfg = config.get("whale", {})
    predictions_path = whale_cfg.get("predictions_json")
    predictions_json = read_json(predictions_path) if predictions_path else {}
    data = convert_whale_predictions_to_unified(predictions_json)

    audio_roots = []
    if predictions_json:
        audio_roots.append(os.path.dirname(predictions_path))
    data["audio_roots"] = audio_roots
    return data


def load_dataset(config: Dict, mode: str) -> Dict:
    if mode == "label":
        return load_label_mode(config)
    if mode == "verify":
        return load_verify_mode(config)
    if mode == "explore":
        return load_explore_mode(config)
    if mode == "whale":
        return load_whale_mode(config)
    return {"items": [], "summary": {"total_items": 0}}
