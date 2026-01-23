"""
Convert unified v2.0 predictions format to internal app format.
"""
from datetime import datetime, timezone
from typing import Dict, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_summary(items: List[dict]) -> dict:
    total = len(items)
    annotated = 0
    verified = 0
    for item in items:
        annotations = item.get("annotations") or {}
        verifications = item.get("verifications") or []
        if annotations.get("labels") or verifications:
            annotated += 1
        if annotations.get("verified") or (verifications and verifications[-1].get("labels")):
            verified += 1
    return {"total_items": total, "annotated": annotated, "verified": verified}


def convert_unified_v2_to_internal(predictions_json: dict) -> dict:
    """Convert unified v2.0 predictions format to internal app format.
    
    Handles the new format with:
    - items (not predictions/segments)
    - model_outputs with class_hierarchy and score
    - verifications array
    
    Args:
        predictions_json: Unified v2.0 format dict
        
    Returns:
        Internal app format dict
    """
    items = []
    model = predictions_json.get("model", {})
    data_source = predictions_json.get("data_source", {})
    task_type = predictions_json.get("task_type", "unknown")
    
    # Process each item
    for item_data in predictions_json.get("items", []):
        # Get latest verification (if any)
        verifications = item_data.get("verifications", [])
        latest_verification = verifications[-1] if verifications else None
        
        # Extract model outputs
        model_outputs = item_data.get("model_outputs", [])
        
        # Build predictions structure for compatibility
        # For now, we'll store the raw model_outputs
        predictions = {
            "model_id": model.get("model_id"),
            "model_outputs": model_outputs,  # Store raw outputs
            "task_type": task_type,
        }
        
        # Build annotations from latest verification
        annotations = None
        if latest_verification:
            annotations = {
                "labels": latest_verification.get("labels", []),
                "annotated_by": latest_verification.get("verified_by"),
                "annotated_at": latest_verification.get("verified_at"),
                "verified": True,
                "notes": latest_verification.get("notes", ""),
                "confidence": latest_verification.get("confidence"),
                "threshold_used": latest_verification.get("threshold_used"),
            }
        
        items.append({
            "item_id": item_data.get("item_id"),
            "spectrogram_path": item_data.get("spectrogram_path"),
            "mat_path": item_data.get("mat_path"),
            "audio_path": item_data.get("audio_path"),
            "timestamps": {
                "start": item_data.get("audio_timestamp"),
                "end": None
            },
            "device_code": data_source.get("device_code"),
            "predictions": predictions,
            "annotations": annotations,
            "metadata": {
                k: v for k, v in item_data.items()
                if k not in ["item_id", "spectrogram_path", "mat_path", "audio_path",
                            "audio_timestamp", "model_outputs", "verifications"]
            },
            "verifications": verifications,  # Preserve all verifications
        })
    
    return {
        "version": predictions_json.get("version", "2.0"),
        "created_at": predictions_json.get("created_at", _now_iso()),
        "source": {
            "type": "ml_prediction",
            "model": model,
            "data_source": data_source,
            "task_type": task_type
        },
        "items": items,
        "summary": _build_summary(items),
    }


def is_unified_v2_format(predictions_json: dict) -> bool:
    """Check if the predictions JSON is in unified v2.0 format.
    
    More lenient detection - accepts:
    - Explicit version "2.0" with items array
    - Items array with model_outputs (even without version)
    
    Args:
        predictions_json: Predictions dict
        
    Returns:
        True if unified v2.0 format
    """
    if not predictions_json:
        return False
    
    # Check for v2.0 markers
    version = predictions_json.get("version")
    has_items = "items" in predictions_json and isinstance(predictions_json["items"], list)
    
    # If explicit v2.0 version with items, accept it
    if version == "2.0" and has_items:
        return True
    
    # Check if items have model_outputs (v2.0 structure)
    if has_items and predictions_json["items"]:
        first_item = predictions_json["items"][0]
        if "model_outputs" in first_item:
            return True
    
    return False
