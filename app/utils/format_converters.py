from datetime import datetime, timezone
import os
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_summary(items: List[dict]) -> dict:
    total = len(items)
    annotated = 0
    verified = 0
    for item in items:
        annotations = item.get("annotations") or {}
        if annotations.get("labels"):
            annotated += 1
        if annotations.get("verified"):
            verified += 1
    return {"total_items": total, "annotated": annotated, "verified": verified}


def convert_legacy_labeling_to_unified(labels_json: dict, mat_folder: str) -> dict:
    items = []
    
    # Check if this is already in unified format (has 'items' array)
    if "items" in labels_json and isinstance(labels_json["items"], list):
        # New unified format - parse the items from the array
        for item in labels_json["items"]:
            item_id = item.get("item_id", "")
            mat_path = item.get("spectrogram_path") or os.path.join(mat_folder, f"{item_id}.mat")
            audio_path = item.get("audio_file") or item.get("audio_path")
            annotations = item.get("annotations", {}) or {}
            metadata = item.get("metadata", {}) or {}
            
            items.append({
                "item_id": item_id,
                "spectrogram_path": None,
                "mat_path": mat_path,
                "audio_path": audio_path,
                "timestamps": {"start": metadata.get("timestamp"), "end": None},
                "device_code": labels_json.get("data_source", {}).get("device_code"),
                "predictions": None,
                "annotations": {
                    "labels": annotations.get("labels", []),
                    "annotated_by": annotations.get("annotated_by"),
                    "annotated_at": annotations.get("annotated_at"),
                    "verified": False,
                    "notes": annotations.get("notes", ""),
                },
                "metadata": metadata,
            })
    else:
        # Legacy format - keys are filenames, values are label arrays
        for filename, labels in labels_json.items():
            mat_path = os.path.join(mat_folder, filename)
            items.append({
                "item_id": filename,
                "spectrogram_path": None,
                "mat_path": mat_path,
                "audio_path": None,
                "timestamps": {"start": None, "end": None},
                "device_code": None,
                "predictions": None,
                "annotations": {
                    "labels": labels if isinstance(labels, list) else [],
                    "annotated_by": None,
                    "annotated_at": None,
                    "verified": False,
                    "notes": "",
                },
                "metadata": {},
            })

    return {
        "version": "2.0",
        "created_at": _now_iso(),
        "source": {"type": "manual", "model": None, "data_source": labels_json.get("data_source", {})},
        "items": items,
        "summary": _build_summary(items),
    }


def convert_hydrophonedashboard_to_unified(labels_json: dict, date: str, hydrophone: str, image_dir: str) -> dict:
    items = []
    for filename, entry in labels_json.items():
        if isinstance(entry, list):
            predicted = entry
            probabilities = {}
            verified = None
            notes = ""
            t0 = ""
            t1 = ""
        else:
            predicted = entry.get("predicted_labels", [])
            probabilities = entry.get("probabilities", {})
            verified = entry.get("verified_labels")
            notes = entry.get("notes", "")
            t0 = entry.get("t0")
            t1 = entry.get("t1")

        items.append({
            "item_id": filename,
            "spectrogram_path": os.path.join(image_dir, filename),
            "mat_path": None,
            "audio_path": None,
            "timestamps": {"start": t0, "end": t1},
            "device_code": hydrophone,
            "predictions": {
                "labels": predicted,
                "confidence": probabilities,
                "model_id": None,
            },
            "annotations": {
                "labels": verified or [],
                "annotated_by": entry.get("verified_by") if isinstance(entry, dict) else None,
                "annotated_at": entry.get("verified_at") if isinstance(entry, dict) else None,
                "verified": verified is not None,
                "notes": notes,
            },
            "metadata": {},
        })

    return {
        "version": "2.0",
        "created_at": _now_iso(),
        "source": {
            "type": "ml_prediction",
            "model": None,
            "data_source": {"date": date, "hydrophone": hydrophone},
        },
        "items": items,
        "summary": _build_summary(items),
    }


def convert_whale_predictions_to_unified(predictions_json: dict) -> dict:
    items = []
    model = predictions_json.get("model", {})
    data_source = predictions_json.get("data_source", {})

    segments = predictions_json.get("segments")
    if segments:
        for seg in segments:
            items.append({
                "item_id": seg.get("segment_id"),
                "spectrogram_path": seg.get("spectrogram_path"),
                "mat_path": seg.get("mat_path"),
                "audio_path": seg.get("audio_path"),
                "timestamps": {"start": seg.get("audio_timestamp"), "end": None},
                "device_code": data_source.get("device_code"),
                "predictions": {
                    "labels": ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"]
                    if seg.get("max_confidence", 0) > 0.5 else [],
                    "confidence": {"Fin whale": seg.get("max_confidence", 0)},
                    "model_id": model.get("model_id"),
                },
                "annotations": None,
                "metadata": {
                    "windows": seg.get("windows", []),
                    "num_positive": seg.get("num_positive", {}),
                },
            })
    else:
        for pred in predictions_json.get("predictions", []):
            items.append({
                "item_id": pred.get("file_id"),
                "spectrogram_path": pred.get("spectrogram_path"),
                "mat_path": pred.get("mat_path"),
                "audio_path": pred.get("audio_path"),
                "timestamps": {"start": pred.get("audio_timestamp"), "end": None},
                "device_code": data_source.get("device_code"),
                "predictions": {
                    "labels": [],
                    "confidence": {"confidence": pred.get("confidence", 0)},
                    "model_id": model.get("model_id"),
                },
                "annotations": None,
                "metadata": {},
            })

    return {
        "version": "2.0",
        "created_at": _now_iso(),
        "source": {"type": "ml_prediction", "model": model, "data_source": data_source},
        "items": items,
        "summary": _build_summary(items),
    }
