"""Annotation and extent utility helpers."""


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_annotation_extent(extent):
    if not isinstance(extent, dict):
        return None
    extent_type = extent.get("type")
    if extent_type not in {"clip", "time_range", "freq_range", "time_freq_box"}:
        return None

    out = {"type": extent_type}
    time_start = safe_float(extent.get("time_start_sec"))
    time_end = safe_float(extent.get("time_end_sec"))
    freq_min = safe_float(extent.get("freq_min_hz"))
    freq_max = safe_float(extent.get("freq_max_hz"))

    if time_start is not None:
        out["time_start_sec"] = max(0.0, time_start)
    if time_end is not None:
        out["time_end_sec"] = max(0.0, time_end)
    if freq_min is not None:
        out["freq_min_hz"] = max(0.0, freq_min)
    if freq_max is not None:
        out["freq_max_hz"] = max(0.0, freq_max)

    if extent_type == "time_range":
        if "time_start_sec" not in out or "time_end_sec" not in out:
            return None
    elif extent_type == "freq_range":
        if "freq_min_hz" not in out or "freq_max_hz" not in out:
            return None
    elif extent_type == "time_freq_box":
        required = {"time_start_sec", "time_end_sec", "freq_min_hz", "freq_max_hz"}
        if not required.issubset(out):
            return None
    return out


def clean_box_tag(tag):
    if tag is None:
        return None
    normalized = str(tag).strip()
    return normalized or None


def clean_box_annotation(entry):
    if not isinstance(entry, dict):
        return None
    label = entry.get("label")
    if not isinstance(label, str) or not label.strip():
        return None
    cleaned_extent = clean_annotation_extent(entry.get("annotation_extent"))
    if not cleaned_extent:
        return None
    cleaned = {
        "label": label.strip(),
        "annotation_extent": cleaned_extent,
    }
    tag = clean_box_tag(entry.get("tag"))
    if tag:
        cleaned["tag"] = tag
    return cleaned


def extract_box_annotations_from_boxes(boxes):
    annotations = []
    for box in boxes or []:
        cleaned = clean_box_annotation(box)
        if cleaned:
            annotations.append(cleaned)
    return annotations


def extract_box_annotation_list_map_from_boxes(boxes):
    annotation_map = {}
    for annotation in extract_box_annotations_from_boxes(boxes):
        annotation_map.setdefault(annotation["label"], []).append(annotation)
    return annotation_map


def extract_label_extent_list_map_from_boxes(boxes):
    extent_map = {}
    for label, annotations in extract_box_annotation_list_map_from_boxes(boxes).items():
        for annotation in annotations:
            extent_map.setdefault(label, []).append(annotation["annotation_extent"])
    return extent_map


def extract_label_extent_map_from_boxes(boxes):
    extent_map = {}
    for label, extents in extract_label_extent_list_map_from_boxes(boxes).items():
        if extents:
            extent_map[label] = extents[0]
    return extent_map


def ordered_unique_labels(labels):
    ordered = []
    seen = set()
    for label in labels or []:
        if not isinstance(label, str):
            continue
        normalized = label.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def split_hierarchy_label(label):
    if not isinstance(label, str):
        return []
    return [part.strip() for part in label.split(">") if part and part.strip()]
