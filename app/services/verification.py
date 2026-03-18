"""Verification and annotation-state helpers."""

import json
from datetime import datetime

from app.services.annotations import (
    clean_annotation_extent,
    ordered_unique_labels,
)


def parse_verify_target(target):
    item_key = ""
    item_id = ""
    label = ""
    if not isinstance(target, str):
        return item_key, item_id, label
    text = target.strip()
    if not text:
        return item_key, item_id, label
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            item_key = (payload.get("item_key") or "").strip()
            item_id = (payload.get("item_id") or "").strip()
            label = (payload.get("label") or "").strip()
            if item_key or item_id or label:
                return item_key, item_id, label
    if "||" in text:
        item_id, _, label = text.partition("||")
        return "", (item_id or "").strip(), (label or "").strip()
    return "", "", text


def filter_predictions(predictions, thresholds):
    if not predictions:
        return []

    thresholds = thresholds or {}
    global_threshold = float(thresholds.get("__global__", 0.5))
    filtered = []

    model_outputs = predictions.get("model_outputs")
    if model_outputs and isinstance(model_outputs, list):
        for output in model_outputs:
            label = output.get("class_hierarchy")
            score = output.get("score", 0)
            if label:
                label_threshold = float(thresholds.get(label, global_threshold))
                if score >= label_threshold:
                    filtered.append(label)
        return filtered

    probs = predictions.get("confidence") or {}
    labels = predictions.get("labels") or []
    if not probs:
        return labels

    for label, prob in probs.items():
        label_threshold = float(thresholds.get(label, global_threshold))
        if prob >= label_threshold:
            filtered.append(label)
    return filtered


def update_item_labels(data, item_id, labels, mode, user_name=None, is_reverification=False, label_extents=None):
    if not data or not item_id:
        return data
    normalized_labels = ordered_unique_labels(labels or [])
    items = data.get("items", [])
    for item in items:
        if not item:
            continue
        if item.get("item_id") == item_id:
            annotations = item.get("annotations") or {
                "labels": [],
                "annotated_by": None,
                "annotated_at": None,
                "verified": False,
                "notes": "",
            }
            annotations["labels"] = normalized_labels
            if isinstance(label_extents, dict):
                annotations["label_extents"] = label_extents
            annotations["annotated_at"] = datetime.now().isoformat()
            annotations["has_manual_review"] = True

            if mode == "verify":
                if is_reverification:
                    annotations["verified"] = True
                    annotations["verified_at"] = datetime.now().isoformat()
                    annotations["needs_reverify"] = False
                    annotations["pending_save"] = False
                else:
                    if annotations.get("verified"):
                        annotations["needs_reverify"] = True
                    annotations["pending_save"] = True
            elif mode == "label":
                annotations["pending_save"] = not bool(is_reverification)

            if user_name:
                annotations["annotated_by"] = user_name
                if mode == "verify" and is_reverification:
                    annotations["verified_by"] = user_name
            item["annotations"] = annotations
            break

    summary = data.get("summary", {})
    summary["annotated"] = sum(1 for item in items if item and (item.get("annotations") or {}).get("labels"))
    summary["verified"] = sum(1 for item in items if item and (item.get("annotations") or {}).get("verified"))
    data["summary"] = summary
    return data


def update_item_notes(data, item_id, notes, user_name=None):
    if not data or not item_id:
        return data
    items = data.get("items", [])
    for item in items:
        if not item:
            continue
        if item.get("item_id") == item_id:
            annotations = item.get("annotations") or {
                "labels": [],
                "annotated_by": None,
                "annotated_at": None,
                "verified": False,
                "notes": "",
            }
            annotations["notes"] = notes or ""
            annotations["annotated_at"] = datetime.now().isoformat()
            if user_name:
                annotations["annotated_by"] = user_name
            item["annotations"] = annotations
            break
    return data


def has_explicit_review(annotations):
    if not isinstance(annotations, dict):
        return False
    return bool(
        annotations.get("has_manual_review")
        or annotations.get("verified")
        or annotations.get("needs_reverify")
        or annotations.get("annotated_at")
        or annotations.get("annotated_by")
    )


def has_pending_label_edits(annotations):
    if not isinstance(annotations, dict):
        return False
    return bool(annotations.get("pending_save") or annotations.get("needs_reverify"))


def get_modal_label_sets(item, mode, thresholds):
    predictions = item.get("predictions") or {}
    annotations = item.get("annotations") or {}
    predicted_labels = ordered_unique_labels(filter_predictions(predictions, thresholds or {"__global__": 0.5}))
    verified_labels = ordered_unique_labels(annotations.get("labels") or [])
    explicit_review = has_explicit_review(annotations)

    if mode == "verify":
        active_labels = verified_labels if explicit_review else predicted_labels
    else:
        active_labels = (
            verified_labels
            if explicit_review
            else ordered_unique_labels(predictions.get("labels") or [])
        )

    return predicted_labels, verified_labels, active_labels


def get_item_rejected_labels(item):
    if not isinstance(item, dict):
        return []
    annotations = item.get("annotations") or {}
    annotation_rejected = ordered_unique_labels(annotations.get("rejected_labels") or [])
    if annotation_rejected:
        return annotation_rejected

    verifications = item.get("verifications")
    if isinstance(verifications, list) and verifications:
        latest = verifications[-1] if isinstance(verifications[-1], dict) else {}
        rejected = []
        for decision in latest.get("label_decisions", []) or []:
            if not isinstance(decision, dict):
                continue
            if decision.get("decision") != "rejected":
                continue
            label = decision.get("label")
            if isinstance(label, str):
                rejected.append(label)
        return ordered_unique_labels(rejected)
    return []


def merge_clean_label_extents(extents_map):
    cleaned = {}
    if not isinstance(extents_map, dict):
        return cleaned
    for label, extent in extents_map.items():
        if not isinstance(label, str):
            continue
        normalized = label.strip()
        if not normalized:
            continue
        cleaned_extent = clean_annotation_extent(extent)
        if cleaned_extent:
            cleaned[normalized] = cleaned_extent
    return cleaned
