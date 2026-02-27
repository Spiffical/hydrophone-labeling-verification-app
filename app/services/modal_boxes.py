"""Modal box conversion/style and per-item box extraction helpers."""

import colorsys
import hashlib
import json

from app.services.annotations import clean_annotation_extent, safe_float


def bbox_debug_box_summary(boxes):
    summary = []
    for idx, box in enumerate(boxes or []):
        if not isinstance(box, dict):
            summary.append({"idx": idx, "invalid": True})
            continue
        extent = box.get("annotation_extent") if isinstance(box.get("annotation_extent"), dict) else {}
        summary.append(
            {
                "idx": idx,
                "label": box.get("label"),
                "source": box.get("source"),
                "decision": box.get("decision"),
                "extent_type": extent.get("type"),
                "x": [extent.get("time_start_sec"), extent.get("time_end_sec")],
                "y": [extent.get("freq_min_hz"), extent.get("freq_max_hz")],
            }
        )
    return summary


def modal_box_edit_revision(boxes, bump=None):
    normalized = []
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        normalized.append(
            {
                "label": (box.get("label") or "").strip(),
                "source": box.get("source"),
                "decision": box.get("decision"),
                "annotation_extent": clean_annotation_extent(box.get("annotation_extent")) or {},
            }
        )
    payload = {"boxes": normalized, "bump": str(bump) if bump is not None else ""}
    token_src = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    token = hashlib.sha1(token_src.encode("utf-8")).hexdigest()[:16]
    return f"bbox-{token}"


def parse_active_box_target(active_box_label):
    if isinstance(active_box_label, dict):
        label = (active_box_label.get("label") or "").strip()
        allow_existing = bool(active_box_label.get("allow_existing"))
        return label, allow_existing
    if isinstance(active_box_label, str):
        return active_box_label.strip(), False
    return "", False


def axis_meta_from_figure(fig):
    layout = (fig or {}).get("layout", {}) if isinstance(fig, dict) else {}
    meta = layout.get("meta", {}) if isinstance(layout, dict) else {}
    xaxis = layout.get("xaxis", {}) if isinstance(layout, dict) else {}
    yaxis = layout.get("yaxis", {}) if isinstance(layout, dict) else {}

    x_range = xaxis.get("range") if isinstance(xaxis, dict) else None
    y_range = yaxis.get("range") if isinstance(yaxis, dict) else None

    x_min = safe_float(meta.get("x_min"), None)
    x_max = safe_float(meta.get("x_max"), None)
    y_min = safe_float(meta.get("y_min"), None)
    y_max = safe_float(meta.get("y_max"), None)

    if x_min is None:
        x_min = safe_float(x_range[0] if isinstance(x_range, (list, tuple)) and len(x_range) > 1 else None, 0.0)
    if x_max is None:
        x_max = safe_float(x_range[1] if isinstance(x_range, (list, tuple)) and len(x_range) > 1 else None, 1.0)
    if y_min is None:
        y_min = safe_float(y_range[0] if isinstance(y_range, (list, tuple)) and len(y_range) > 1 else None, 0.0)
    if y_max is None:
        y_max = safe_float(y_range[1] if isinstance(y_range, (list, tuple)) and len(y_range) > 1 else None, 1.0)

    if x_max <= x_min:
        x_max = x_min + 1.0
    if y_max <= y_min:
        y_max = y_min + 1.0

    return {
        "x_to_seconds": safe_float(meta.get("x_to_seconds"), 1.0) or 1.0,
        "y_to_hz": safe_float(meta.get("y_to_hz"), 1.0) or 1.0,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
    }


def extent_to_shape(extent, axis_meta):
    cleaned = clean_annotation_extent(extent)
    if not cleaned or cleaned.get("type") == "clip":
        return None

    x_to_seconds = axis_meta.get("x_to_seconds", 1.0) or 1.0
    y_to_hz = axis_meta.get("y_to_hz", 1.0) or 1.0
    x_min = axis_meta.get("x_min", 0.0)
    x_max = axis_meta.get("x_max", 1.0)
    y_min = axis_meta.get("y_min", 0.0)
    y_max = axis_meta.get("y_max", 1.0)

    shape = {"type": "rect"}
    if cleaned["type"] in {"time_range", "time_freq_box"}:
        shape["x0"] = cleaned["time_start_sec"] / x_to_seconds
        shape["x1"] = cleaned["time_end_sec"] / x_to_seconds
    else:
        shape["x0"] = x_min
        shape["x1"] = x_max

    if cleaned["type"] in {"freq_range", "time_freq_box"}:
        shape["y0"] = cleaned["freq_min_hz"] / y_to_hz
        shape["y1"] = cleaned["freq_max_hz"] / y_to_hz
    else:
        shape["y0"] = y_min
        shape["y1"] = y_max

    if shape["x0"] > shape["x1"]:
        shape["x0"], shape["x1"] = shape["x1"], shape["x0"]
    if shape["y0"] > shape["y1"]:
        shape["y0"], shape["y1"] = shape["y1"], shape["y0"]

    shape["x0"] = max(x_min, min(x_max, shape["x0"]))
    shape["x1"] = max(x_min, min(x_max, shape["x1"]))
    shape["y0"] = max(y_min, min(y_max, shape["y0"]))
    shape["y1"] = max(y_min, min(y_max, shape["y1"]))

    if shape["x0"] > shape["x1"]:
        shape["x0"], shape["x1"] = shape["x1"], shape["x0"]
    if shape["y0"] > shape["y1"]:
        shape["y0"], shape["y1"] = shape["y1"], shape["y0"]
    return shape


def shape_to_extent(shape, axis_meta):
    if not isinstance(shape, dict):
        return None
    x0 = safe_float(shape.get("x0"))
    x1 = safe_float(shape.get("x1"))
    y0 = safe_float(shape.get("y0"))
    y1 = safe_float(shape.get("y1"))
    if None in (x0, x1, y0, y1):
        return None

    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0

    x_to_seconds = axis_meta.get("x_to_seconds", 1.0) or 1.0
    y_to_hz = axis_meta.get("y_to_hz", 1.0) or 1.0
    x_min = axis_meta.get("x_min", 0.0)
    x_max = axis_meta.get("x_max", 1.0)
    y_min = axis_meta.get("y_min", 0.0)
    y_max = axis_meta.get("y_max", 1.0)
    x_span = max(1e-9, x_max - x_min)
    y_span = max(1e-9, y_max - y_min)

    x0 = max(x_min, min(x_max, x0))
    x1 = max(x_min, min(x_max, x1))
    y0 = max(y_min, min(y_max, y0))
    y1 = max(y_min, min(y_max, y1))

    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0

    min_x_span = max(1e-9, x_span * 1e-4)
    min_y_span = max(1e-9, y_span * 1e-4)
    if (x1 - x0) < min_x_span or (y1 - y0) < min_y_span:
        return None

    full_axis_tolerance = 0.005
    full_x = abs((x1 - x0) - x_span) <= full_axis_tolerance * x_span
    full_y = abs((y1 - y0) - y_span) <= full_axis_tolerance * y_span

    if full_x and full_y:
        return {"type": "clip"}

    if full_y:
        return {
            "type": "time_range",
            "time_start_sec": max(0.0, round(x0 * x_to_seconds, 3)),
            "time_end_sec": max(0.0, round(x1 * x_to_seconds, 3)),
        }

    if full_x:
        return {
            "type": "freq_range",
            "freq_min_hz": max(0.0, round(y0 * y_to_hz, 3)),
            "freq_max_hz": max(0.0, round(y1 * y_to_hz, 3)),
        }

    return {
        "type": "time_freq_box",
        "time_start_sec": max(0.0, round(x0 * x_to_seconds, 3)),
        "time_end_sec": max(0.0, round(x1 * x_to_seconds, 3)),
        "freq_min_hz": max(0.0, round(y0 * y_to_hz, 3)),
        "freq_max_hz": max(0.0, round(y1 * y_to_hz, 3)),
    }


def label_color_rgb(label):
    normalized = (label or "").strip().lower() or "unlabeled"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    hue = (int(digest[:8], 16) % 360) / 360.0
    saturation = 0.64 + ((int(digest[8:10], 16) % 20) / 100.0)
    value = 0.70 + ((int(digest[10:12], 16) % 18) / 100.0)
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return int(red * 255), int(green * 255), int(blue * 255)


def rgba(rgb, alpha):
    r_val, g_val, b_val = rgb
    return f"rgba({r_val}, {g_val}, {b_val}, {alpha})"


def box_style(source, decision, label=None):
    base_rgb = label_color_rgb(label)
    if decision == "rejected":
        return {
            "line_color": rgba(base_rgb, 0.98),
            "line_dash": "dot",
            "fillcolor": rgba(base_rgb, 0.20),
        }
    if source == "model":
        return {
            "line_color": rgba(base_rgb, 0.95),
            "line_dash": "dash",
            "fillcolor": rgba(base_rgb, 0.14),
        }
    return {
        "line_color": rgba(base_rgb, 0.95),
        "line_dash": "solid",
        "fillcolor": rgba(base_rgb, 0.18),
    }


def build_modal_boxes_from_item(item):
    if not isinstance(item, dict):
        return []

    annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
    label_extents = annotations.get("label_extents") if isinstance(annotations, dict) else None
    annotation_boxes = []
    if isinstance(label_extents, dict):
        for label, extent in label_extents.items():
            cleaned = clean_annotation_extent(extent)
            if not label or not cleaned or cleaned.get("type") == "clip":
                continue
            annotation_boxes.append(
                {
                    "label": label,
                    "annotation_extent": cleaned,
                    "source": "label",
                    "decision": "added",
                }
            )

    if annotations.get("pending_save") or annotations.get("needs_reverify"):
        return annotation_boxes

    verification_boxes = []
    verifications = item.get("verifications")
    if isinstance(verifications, list) and verifications:
        latest = verifications[-1] if isinstance(verifications[-1], dict) else {}
        for decision in latest.get("label_decisions", []) or []:
            if not isinstance(decision, dict):
                continue
            label = decision.get("label")
            extent = clean_annotation_extent(decision.get("annotation_extent"))
            if not label or not extent or extent.get("type") == "clip":
                continue
            verification_boxes.append(
                {
                    "label": label,
                    "annotation_extent": extent,
                    "source": "verification",
                    "decision": decision.get("decision", "accepted"),
                }
            )

    if verification_boxes:
        return verification_boxes

    model_boxes = []
    predictions = item.get("predictions") or {}
    model_outputs = predictions.get("model_outputs") if isinstance(predictions, dict) else None
    if isinstance(model_outputs, list):
        for output in model_outputs:
            if not isinstance(output, dict):
                continue
            label = output.get("class_hierarchy")
            extent = clean_annotation_extent(output.get("annotation_extent"))
            if not label or not extent or extent.get("type") == "clip":
                continue
            model_boxes.append(
                {
                    "label": label,
                    "annotation_extent": extent,
                    "source": "model",
                    "decision": "accepted",
                }
            )

    if model_boxes:
        return model_boxes

    if annotation_boxes:
        return annotation_boxes
    return []


def label_has_box(label, boxes):
    target = (label or "").strip()
    if not target:
        return False
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        box_label = (box.get("label") or "").strip()
        if box_label == target:
            extent = clean_annotation_extent(box.get("annotation_extent"))
            if extent and extent.get("type") != "clip":
                return True
    return False


def leaf_label_text(label):
    if not isinstance(label, str):
        return "Unlabeled"
    parts = [part.strip() for part in label.split(">") if part.strip()]
    if parts:
        return parts[-1]
    cleaned = label.strip()
    return cleaned if cleaned else "Unlabeled"
