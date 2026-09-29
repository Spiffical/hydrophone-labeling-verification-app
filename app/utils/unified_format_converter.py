"""
Convert unified v2.x predictions format to internal app format.
"""
import json
from datetime import datetime, timezone
from typing import Dict, List

from app.services.annotations import clean_box_annotation
from app.services.label_attributes import normalize_label_attributes, prune_label_attributes
from taxonomy.hierarchical_labels import canonicalize_prediction_label


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_summary(items: List[dict]) -> dict:
    total = len(items)
    annotated = 0
    verified = 0
    for item in items:
        verifications = item.get("verifications") or []
        annotations = item.get("annotations") or {}
        if verifications:
            annotated += 1
            if verifications[-1].get("label_decisions"):
                verified += 1
        elif annotations.get("labels") or annotations.get("label_attributes"):
            annotated += 1
            if annotations.get("verified"):
                verified += 1
    return {"total_items": total, "annotated": annotated, "verified": verified}


def _build_data_source_index(predictions_json: dict) -> dict:
    """Build lookup from data_source_id to data source dict.

    Handles both new format (data_sources array) and old format (singular data_source object).
    """
    index = {}
    # New format: data_sources array
    for ds in predictions_json.get("data_sources", []):
        ds_id = ds.get("data_source_id")
        if ds_id:
            index[ds_id] = ds
    # Old format fallback: singular data_source object
    if not index:
        old_ds = predictions_json.get("data_source", {})
        if old_ds:
            index["_default"] = old_ds
    return index


def merge_duplicate_item_records(raw_items):
    """Collapse repeated item ids from merged inference passes into one record each.

    The last occurrence wins for model outputs and paths, since a later pass is
    appended after an earlier one. Verifications from every copy are kept in
    file order with exact repeats dropped, so no expert decision is lost.
    Records without an item id pass through untouched.
    """
    if not isinstance(raw_items, list):
        return []
    merged = []
    position = {}
    for record in raw_items:
        if not isinstance(record, dict):
            continue
        item_id = record.get("item_id")
        if not item_id or item_id not in position:
            if item_id:
                position[item_id] = len(merged)
            merged.append(record)
            continue
        index = position[item_id]
        previous = merged[index]
        combined = dict(record)
        verifications = []
        seen = set()
        for source in (previous.get("verifications"), record.get("verifications")):
            for verification in source if isinstance(source, list) else []:
                key = json.dumps(verification, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                verifications.append(verification)
        combined["verifications"] = verifications
        merged[index] = combined
    return merged


def convert_unified_v2_to_internal(predictions_json: dict, base_path: str = None, *, path_exists=None) -> dict:
    """Convert unified v2.x predictions format to internal app format.

    Handles both the new schema (schema_version, data_sources, paths object,
    label_decisions) and older format for backwards compatibility.

    Args:
        predictions_json: Unified v2.x format dict
        base_path: Optional base path to resolve relative paths

    Returns:
        Internal app format dict
    """
    import os

    def resolve_path(path):
        """Resolve relative path to absolute using base_path."""
        if not path or not base_path:
            return path
        if os.path.isabs(path):
            return path
        resolved = os.path.join(base_path, path)
        return resolved if (path_exists or os.path.exists)(resolved) else path

    items = []
    model = predictions_json.get("model", {})
    ds_index = _build_data_source_index(predictions_json)
    task_type = predictions_json.get("task_type", "unknown")

    global_review_filter_classes = predictions_json.get("review_filter_classes") or []
    for item_data in merge_duplicate_item_records(predictions_json.get("items", [])):
        # Look up data source for this item
        ds_id = item_data.get("data_source_id", "_default")
        data_source = ds_index.get(ds_id, ds_index.get("_default", {}))

        # Get latest verification (if any)
        verifications = item_data.get("verifications", [])
        latest_verification = verifications[-1] if verifications else None

        model_outputs = []
        for output in item_data.get("model_outputs", []):
            if not isinstance(output, dict):
                continue
            canonical_label = canonicalize_prediction_label(output.get("class_hierarchy"))
            if not canonical_label:
                continue
            normalized_output = dict(output)
            normalized_output["class_hierarchy"] = canonical_label
            model_outputs.append(normalized_output)

        predictions = {
            "model_id": model.get("model_id"),
            "model_outputs": model_outputs,
            "label_attributes": normalize_label_attributes(
                item_data.get("label_attributes"),
                default_source="model",
            ),
            "task_type": task_type,
        }

        # Resolve paths: new format nests under "paths", old format has flat fields
        paths_obj = item_data.get("paths", {})
        spect_png = (
            paths_obj.get("spectrogram_png_path")
            or item_data.get("spectrogram_png_path")
            or item_data.get("spectrogram_path")
        )
        mat = (
            paths_obj.get("spectrogram_mat_path")
            or item_data.get("spectrogram_mat_path")
            or item_data.get("mat_path")
        )
        audio = paths_obj.get("audio_path") or item_data.get("audio_path")

        # Timestamps: new format uses audio_start_time/audio_end_time
        start_time = item_data.get("audio_start_time") or item_data.get("audio_timestamp")
        end_time = item_data.get("audio_end_time")

        # Build annotations from latest verification
        annotations = None
        if latest_verification:
            # Extract accepted labels from label_decisions (new) or flat labels (old)
            label_decisions = latest_verification.get("label_decisions", [])
            if label_decisions:
                accepted = [ld["label"] for ld in label_decisions if ld.get("decision") == "accepted"]
                added = [ld["label"] for ld in label_decisions if ld.get("decision") == "added"]
                rejected = [ld["label"] for ld in label_decisions if ld.get("decision") == "rejected"]
                label_extents = {}
                box_annotations = []
                for ld in label_decisions:
                    if ld.get("decision") not in ("accepted", "added"):
                        continue
                    label = ld.get("label")
                    extent = ld.get("annotation_extent")
                    if isinstance(label, str) and isinstance(extent, dict):
                        label_extents[label] = extent
                        box = clean_box_annotation(
                            {
                                "label": label,
                                "annotation_extent": extent,
                                "tag": ld.get("tag"),
                                "tag_source": ld.get("tag_source"),
                                "tag_scope": ld.get("tag_scope"),
                            }
                        )
                        if box:
                            box_annotations.append(box)
            else:
                accepted = latest_verification.get("labels", [])
                added = latest_verification.get("added_labels", [])
                rejected = latest_verification.get("rejected_labels", [])
                label_extents = {}
                box_annotations = []

            annotations = {
                "labels": accepted + added,
                "rejected_labels": rejected,
                "label_attributes": prune_label_attributes(
                    latest_verification.get("label_attributes"),
                    accepted + added,
                    default_source="human",
                ),
                "annotated_by": latest_verification.get("verified_by"),
                "annotated_at": latest_verification.get("verified_at"),
                "verified": True,
                "notes": latest_verification.get("notes", ""),
                "confidence": latest_verification.get("confidence"),
                "label_extents": label_extents,
                "box_annotations": box_annotations,
            }

        items.append({
            "item_id": item_data.get("item_id"),
            "spectrogram_path": resolve_path(spect_png),
            "mat_path": resolve_path(mat),
            "audio_path": resolve_path(audio),
            "source_audio": item_data.get("source_audio"),
            "timestamps": {
                "start": start_time,
                "end": end_time,
            },
            "device_code": data_source.get("device_code"),
            "predictions": predictions,
            "annotations": annotations,
            "metadata": {
                **({"review_filter_classes": list(global_review_filter_classes)} if global_review_filter_classes else {}),
                **{k: v for k, v in item_data.items()
                if k not in ["item_id", "data_source_id", "spectrogram_path", "mat_path",
                            "spectrogram_png_path", "spectrogram_mat_path",
                            "audio_path", "source_audio", "paths",
                            "audio_start_time", "audio_end_time",
                            "audio_timestamp", "model_outputs", "label_attributes", "tag_outputs", "verifications"]}
            },
            "verifications": verifications,
        })

    version = predictions_json.get("schema_version") or predictions_json.get("version", "2.1")

    # Flatten data_sources for the source block (use first if multiple)
    first_ds = next(iter(ds_index.values()), {})

    return {
        "version": version,
        "created_at": predictions_json.get("created_at", _now_iso()),
        "source": {
            "type": "ml_prediction",
            "model": model,
            "data_source": first_ds,
            "task_type": task_type
        },
        "items": items,
        "summary": _build_summary(items),
    }


def is_unified_v2_format(predictions_json: dict) -> bool:
    """Check if the predictions JSON is in unified v2.x format.

    Accepts:
    - Explicit schema_version or version "2.0"/"2.1" with items array
    - Items array with model_outputs (even without version)

    Args:
        predictions_json: Predictions dict

    Returns:
        True if unified v2.x format
    """
    if not predictions_json:
        return False

    version = predictions_json.get("schema_version") or predictions_json.get("version")
    has_items = "items" in predictions_json and isinstance(predictions_json["items"], list)

    if version in {"2.0", "2.1"} and has_items:
        return True

    if has_items and predictions_json["items"]:
        first_item = predictions_json["items"][0]
        if "model_outputs" in first_item or "verifications" in first_item:
            return True

    return False
