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


def extract_label_extent_list_map_from_boxes(boxes):
    extent_map = {}
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        label = box.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        cleaned_extent = clean_annotation_extent(box.get("annotation_extent"))
        if not cleaned_extent:
            continue
        normalized = label.strip()
        extent_map.setdefault(normalized, []).append(cleaned_extent)
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
