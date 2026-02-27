import os
import re
import time
import json
import logging
import hashlib
import colorsys
from copy import deepcopy
from datetime import datetime
from dash import Input, Output, State, callback, ctx, no_update, ALL, dcc
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html

from app.components.spectrogram_card import create_spectrogram_card
from app.components.hierarchical_selector import create_hierarchical_selector
from app.components.audio_player import (
    EQ_BAND_FREQUENCIES,
    EQ_LOW_FOCUS_MAX_HZ,
    create_audio_player,
    create_modal_audio_player,
)
from app.utils.data_loading import load_dataset
from app.utils.image_utils import get_item_image_src
from app.utils.image_processing import load_spectrogram_cached, create_spectrogram_figure, set_cache_sizes
from app.utils.persistence import save_label_mode, save_verify_predictions

logger = logging.getLogger(__name__)
_BBOX_DEBUG_ENABLED = os.getenv("O3_BBOX_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
_BBOX_DELETE_TRACE_NAME = "__bbox_delete_handle__"
_VERIFY_BADGE_DEBUG_ENABLED = os.getenv("O3_VERIFY_BADGE_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}
_TAB_ISO_DEBUG_ENABLED = os.getenv("O3_TAB_ISO_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
_RESET_PROFILE_ON_START = os.getenv("O3_RESET_PROFILE_ON_START", "0").strip().lower() in {"1", "true", "yes", "on"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROFILE_REQUIRED_MESSAGE = "Name and a valid email are required before labeling or verification."


def _bbox_debug(event, **payload):
    if not _BBOX_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[BBOX_DEBUG] %s | %s", event, serialized)


def _verify_badge_debug(event, **payload):
    if not _VERIFY_BADGE_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[VERIFY_BADGE_DEBUG] %s | %s", event, serialized)


def _tab_iso_debug(event, **payload):
    if not _TAB_ISO_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[TAB_ISO_DEBUG] %s | %s", event, serialized)


def _tab_data_snapshot(data):
    if not isinstance(data, dict):
        return {"loaded": False}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return {
        "loaded": True,
        "source_data_dir": data.get("source_data_dir"),
        "summary_data_root": summary.get("data_root"),
        "summary_active_date": summary.get("active_date"),
        "summary_active_hydrophone": summary.get("active_hydrophone"),
        "summary_predictions_file": summary.get("predictions_file"),
        "summary_labels_file": summary.get("labels_file"),
        "items_count": len(items),
    }


def _bbox_debug_box_summary(boxes):
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


def _modal_box_edit_revision(boxes, bump=None):
    normalized = []
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        normalized.append(
            {
                "label": (box.get("label") or "").strip(),
                "source": box.get("source"),
                "decision": box.get("decision"),
                "annotation_extent": _clean_annotation_extent(box.get("annotation_extent")) or {},
            }
        )
    payload = {"boxes": normalized, "bump": str(bump) if bump is not None else ""}
    token_src = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    token = hashlib.sha1(token_src.encode("utf-8")).hexdigest()[:16]
    return f"bbox-{token}"


def _parse_active_box_target(active_box_label):
    if isinstance(active_box_label, dict):
        label = (active_box_label.get("label") or "").strip()
        allow_existing = bool(active_box_label.get("allow_existing"))
        return label, allow_existing
    if isinstance(active_box_label, str):
        return active_box_label.strip(), False
    return "", False


def _item_action_key(item):
    if not isinstance(item, dict):
        return ""
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    parts = [
        item.get("item_id"),
        item.get("mat_path"),
        item.get("spectrogram_path"),
        item.get("audio_path"),
        metadata.get("predictions_path"),
        metadata.get("date"),
        metadata.get("hydrophone"),
        item.get("device_code"),
    ]
    raw = "|".join("" if value is None else str(value) for value in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _config_default_data_dir(cfg):
    if not isinstance(cfg, dict):
        return None
    data_cfg = cfg.get("data") if isinstance(cfg.get("data"), dict) else {}
    verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
    return data_cfg.get("data_dir") or verify_cfg.get("dashboard_root")


def _resolve_tab_data_dir(cfg, current_tab_data=None, trigger_cfg=None, trigger_source=None):
    current_source = None
    if isinstance(current_tab_data, dict):
        current_source = current_tab_data.get("source_data_dir")

    trigger_data_dir = _config_default_data_dir(trigger_cfg)
    configured_data_dir = _config_default_data_dir(cfg)

    # A data-config load is an explicit root switch for the active tab.
    if trigger_source == "data-config-load":
        return trigger_data_dir or current_source or configured_data_dir

    # Otherwise keep each tab pinned to its own previously loaded source.
    return current_source or trigger_data_dir or configured_data_dir


def _parse_verify_target(target):
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


def _profile_name_email(profile):
    if not isinstance(profile, dict):
        return "", ""
    name = str(profile.get("name") or "").strip()
    email = str(profile.get("email") or "").strip()
    return name, email


def _is_valid_email(email):
    return bool(email and _EMAIL_RE.match(email))


def _is_profile_complete(profile):
    name, email = _profile_name_email(profile)
    return bool(name) and _is_valid_email(email)


def _profile_actor(profile):
    name, email = _profile_name_email(profile)
    if not name or not email:
        return None
    return f"{name} <{email}>"


def _require_complete_profile(profile, action_name):
    if _is_profile_complete(profile):
        return
    logger.warning(
        "[PROFILE_REQUIRED] blocked_action=%s profile=%s",
        action_name,
        {"name": _profile_name_email(profile)[0], "email": _profile_name_email(profile)[1]},
    )
    raise PreventUpdate


def _update_item_labels(data, item_id, labels, mode, user_name=None, is_reverification=False, label_extents=None):
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
            annotations["labels"] = labels
            if isinstance(label_extents, dict):
                annotations["label_extents"] = label_extents
            annotations["annotated_at"] = datetime.now().isoformat()
            # Preserve explicit reviewer intent, including "no labels selected".
            annotations["has_manual_review"] = True
            
            if mode == "verify":
                if is_reverification:
                    # User clicked Re-verify - mark as verified and clear the flag
                    annotations["verified"] = True
                    annotations["verified_at"] = datetime.now().isoformat()
                    annotations["needs_reverify"] = False
                    annotations["pending_save"] = False
                else:
                    # User edited labels - if already verified, needs re-verification
                    if annotations.get("verified"):
                        annotations["needs_reverify"] = True
                    annotations["pending_save"] = True
            elif mode == "label":
                # Label mode now uses explicit Save action.
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


def _update_item_notes(data, item_id, notes, user_name=None):
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


def _filter_predictions(predictions, thresholds):
    if not predictions:
        return []
    
    thresholds = thresholds or {}
    global_threshold = float(thresholds.get("__global__", 0.5))
    filtered = []

    # Handle unified v2.x model_outputs
    model_outputs = predictions.get("model_outputs")
    if model_outputs and isinstance(model_outputs, list):
        for out in model_outputs:
            label = out.get("class_hierarchy")
            score = out.get("score", 0)
            if label:
                label_threshold = float(thresholds.get(label, global_threshold))
                if score >= label_threshold:
                    filtered.append(label)
        return filtered

    # Fallback to legacy confidence/labels
    probs = predictions.get("confidence") or {}
    labels = predictions.get("labels") or []
    if not probs:
        return labels

    for label, prob in probs.items():
        label_threshold = float(thresholds.get(label, global_threshold))
        if prob >= label_threshold:
            filtered.append(label)
    return filtered


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_annotation_extent(extent):
    if not isinstance(extent, dict):
        return None
    extent_type = extent.get("type")
    if extent_type not in {"clip", "time_range", "freq_range", "time_freq_box"}:
        return None

    out = {"type": extent_type}
    time_start = _safe_float(extent.get("time_start_sec"))
    time_end = _safe_float(extent.get("time_end_sec"))
    freq_min = _safe_float(extent.get("freq_min_hz"))
    freq_max = _safe_float(extent.get("freq_max_hz"))

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


def _axis_meta_from_figure(fig):
    layout = (fig or {}).get("layout", {}) if isinstance(fig, dict) else {}
    meta = layout.get("meta", {}) if isinstance(layout, dict) else {}
    xaxis = layout.get("xaxis", {}) if isinstance(layout, dict) else {}
    yaxis = layout.get("yaxis", {}) if isinstance(layout, dict) else {}

    x_range = xaxis.get("range") if isinstance(xaxis, dict) else None
    y_range = yaxis.get("range") if isinstance(yaxis, dict) else None

    x_min = _safe_float(meta.get("x_min"), None)
    x_max = _safe_float(meta.get("x_max"), None)
    y_min = _safe_float(meta.get("y_min"), None)
    y_max = _safe_float(meta.get("y_max"), None)

    # Fallback to visible axis ranges if metadata is missing.
    if x_min is None:
        x_min = _safe_float(x_range[0] if isinstance(x_range, (list, tuple)) and len(x_range) > 1 else None, 0.0)
    if x_max is None:
        x_max = _safe_float(x_range[1] if isinstance(x_range, (list, tuple)) and len(x_range) > 1 else None, 1.0)
    if y_min is None:
        y_min = _safe_float(y_range[0] if isinstance(y_range, (list, tuple)) and len(y_range) > 1 else None, 0.0)
    if y_max is None:
        y_max = _safe_float(y_range[1] if isinstance(y_range, (list, tuple)) and len(y_range) > 1 else None, 1.0)

    if x_max <= x_min:
        x_max = x_min + 1.0
    if y_max <= y_min:
        y_max = y_min + 1.0

    return {
        "x_to_seconds": _safe_float(meta.get("x_to_seconds"), 1.0) or 1.0,
        "y_to_hz": _safe_float(meta.get("y_to_hz"), 1.0) or 1.0,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
    }


def _extent_to_shape(extent, axis_meta):
    cleaned = _clean_annotation_extent(extent)
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

    # Normalize bounds for Plotly rectangle.
    if shape["x0"] > shape["x1"]:
        shape["x0"], shape["x1"] = shape["x1"], shape["x0"]
    if shape["y0"] > shape["y1"]:
        shape["y0"], shape["y1"] = shape["y1"], shape["y0"]

    # Clamp to spectrogram bounds so persisted extents cannot render outside axes.
    shape["x0"] = max(x_min, min(x_max, shape["x0"]))
    shape["x1"] = max(x_min, min(x_max, shape["x1"]))
    shape["y0"] = max(y_min, min(y_max, shape["y0"]))
    shape["y1"] = max(y_min, min(y_max, shape["y1"]))

    if shape["x0"] > shape["x1"]:
        shape["x0"], shape["x1"] = shape["x1"], shape["x0"]
    if shape["y0"] > shape["y1"]:
        shape["y0"], shape["y1"] = shape["y1"], shape["y0"]
    return shape


def _shape_to_extent(shape, axis_meta):
    if not isinstance(shape, dict):
        return None
    x0 = _safe_float(shape.get("x0"))
    x1 = _safe_float(shape.get("x1"))
    y0 = _safe_float(shape.get("y0"))
    y1 = _safe_float(shape.get("y1"))
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

    # Clamp incoming drawn/edited coordinates to spectrogram bounds.
    x0 = max(x_min, min(x_max, x0))
    x1 = max(x_min, min(x_max, x1))
    y0 = max(y_min, min(y_max, y0))
    y1 = max(y_min, min(y_max, y1))

    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0

    # Ignore degenerate shapes (e.g. dragged fully outside and collapsed by clamping).
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


def _label_color_rgb(label):
    normalized = (label or "").strip().lower() or "unlabeled"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    hue = (int(digest[:8], 16) % 360) / 360.0
    saturation = 0.64 + ((int(digest[8:10], 16) % 20) / 100.0)  # 0.64-0.83
    value = 0.70 + ((int(digest[10:12], 16) % 18) / 100.0)      # 0.70-0.87
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return int(red * 255), int(green * 255), int(blue * 255)


def _rgba(rgb, alpha):
    r_val, g_val, b_val = rgb
    return f"rgba({r_val}, {g_val}, {b_val}, {alpha})"


def _box_style(source, decision, label=None):
    base_rgb = _label_color_rgb(label)
    if decision == "rejected":
        return {
            "line_color": _rgba(base_rgb, 0.98),
            "line_dash": "dot",
            "fillcolor": _rgba(base_rgb, 0.20),
        }
    if source == "model":
        return {
            "line_color": _rgba(base_rgb, 0.95),
            "line_dash": "dash",
            "fillcolor": _rgba(base_rgb, 0.14),
        }
    return {
        "line_color": _rgba(base_rgb, 0.95),
        "line_dash": "solid",
        "fillcolor": _rgba(base_rgb, 0.18),
    }


def _build_modal_boxes_from_item(item):
    if not isinstance(item, dict):
        return []

    annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
    label_extents = annotations.get("label_extents") if isinstance(annotations, dict) else None
    annotation_boxes = []
    if isinstance(label_extents, dict):
        for label, extent in label_extents.items():
            cleaned = _clean_annotation_extent(extent)
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

    # While verify edits are unsaved, annotation extents are the source of truth.
    # This prevents stale boxes from the previous saved verification round.
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
            extent = _clean_annotation_extent(decision.get("annotation_extent"))
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
            extent = _clean_annotation_extent(output.get("annotation_extent"))
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

    # Fallback for label mode files saved from this app.
    if annotation_boxes:
        return annotation_boxes
    return []


def _apply_modal_boxes_to_figure(fig, boxes, revision_bump=None):
    if hasattr(fig, "to_dict"):
        fig = fig.to_dict()
    if not isinstance(fig, dict):
        return fig
    layout = fig.get("layout") or {}
    if not isinstance(layout, dict):
        return fig

    axis_meta = _axis_meta_from_figure(fig)
    x_span = max(1e-9, axis_meta.get("x_max", 1.0) - axis_meta.get("x_min", 0.0))
    y_span = max(1e-9, axis_meta.get("y_max", 1.0) - axis_meta.get("y_min", 0.0))

    existing_shapes = layout.get("shapes") or []
    marker_shape = None
    if isinstance(existing_shapes, list):
        for candidate in existing_shapes:
            if isinstance(candidate, dict) and candidate.get("name") == "playback-marker":
                marker_shape = candidate
                break
            if isinstance(candidate, dict) and candidate.get("type") == "line" and candidate.get("yref") == "paper":
                marker_shape = candidate
                break

    if marker_shape is None:
        marker_shape = {
            "type": "line",
            "x0": 0,
            "x1": 0,
            "y0": 0,
            "y1": 1,
            "yref": "paper",
            "editable": False,
            "name": "playback-marker",
            "line": {"color": "rgba(255, 0, 0, 0)", "width": 2, "dash": "solid"},
        }

    shape_list = [marker_shape]
    annotations = []
    delete_x = []
    delete_y = []
    delete_indices = []

    prepared_boxes = []
    for box_idx, box in enumerate(boxes or []):
        if not isinstance(box, dict):
            continue
        shape_base = _extent_to_shape(box.get("annotation_extent"), axis_meta)
        if not shape_base:
            continue
        style = _box_style(box.get("source"), box.get("decision"), box.get("label"))
        rect = {
            "x0": min(shape_base["x0"], shape_base["x1"]),
            "x1": max(shape_base["x0"], shape_base["x1"]),
            "y0": min(shape_base["y0"], shape_base["y1"]),
            "y1": max(shape_base["y0"], shape_base["y1"]),
        }
        prepared_boxes.append(
            {
                "box_idx": box_idx,
                "box": box,
                "style": style,
                "rect": rect,
            }
        )

    all_rects = [entry["rect"] for entry in prepared_boxes]
    placed_handles = []
    x_min = axis_meta.get("x_min", 0.0)
    x_max = axis_meta.get("x_max", 1.0)
    y_min = axis_meta.get("y_min", 0.0)
    y_max = axis_meta.get("y_max", 1.0)
    # Keep all overlay elements strictly inside the spectrogram axes.
    edge_pad_x = max(1e-6, 0.012 * x_span)
    edge_pad_y = max(1e-6, 0.014 * y_span)
    x_bound_min = x_min + edge_pad_x
    x_bound_max = x_max - edge_pad_x
    y_bound_min = y_min + edge_pad_y
    y_bound_max = y_max - edge_pad_y
    if x_bound_max <= x_bound_min:
        x_bound_min, x_bound_max = x_min, x_max
    if y_bound_max <= y_bound_min:
        y_bound_min, y_bound_max = y_min, y_max

    def _point_in_rect(x_val, y_val, rect, pad_x=0.0, pad_y=0.0):
        return (
            (rect["x0"] - pad_x) <= x_val <= (rect["x1"] + pad_x)
            and (rect["y0"] - pad_y) <= y_val <= (rect["y1"] + pad_y)
        )

    def _choose_delete_handle(rect, box_index):
        candidates = [
            (rect["x1"] + 0.012 * x_span, rect["y1"] + 0.012 * y_span),  # top-right outside
            (rect["x0"] - 0.012 * x_span, rect["y1"] + 0.012 * y_span),  # top-left outside
            (rect["x1"] + 0.012 * x_span, rect["y0"] - 0.012 * y_span),  # bottom-right outside
            (rect["x0"] - 0.012 * x_span, rect["y0"] - 0.012 * y_span),  # bottom-left outside
            (rect["x1"] - 0.008 * x_span, rect["y1"] + 0.010 * y_span),  # near top-right
            (rect["x0"] + 0.008 * x_span, rect["y1"] + 0.010 * y_span),  # near top-left
        ]
        pad_x = 0.002 * x_span
        pad_y = 0.002 * y_span
        min_dx = 0.020 * x_span
        min_dy = 0.030 * y_span

        for raw_x, raw_y in candidates:
            x_val = max(x_bound_min, min(x_bound_max, raw_x))
            y_val = max(y_bound_min, min(y_bound_max, raw_y))
            if any(_point_in_rect(x_val, y_val, r, pad_x=pad_x, pad_y=pad_y) for r in all_rects):
                continue
            if any(abs(x_val - hx) <= min_dx and abs(y_val - hy) <= min_dy for hx, hy in placed_handles):
                continue
            return x_val, y_val

        # Fallback search: sample a small deterministic grid inside plot bounds.
        x_candidates = [x_bound_max - i * 0.06 * x_span for i in range(0, 12)]
        y_candidates = [y_bound_max - j * 0.08 * y_span for j in range(0, 10)]
        row_offset = box_index % 3
        for y_val in y_candidates[row_offset:] + y_candidates[:row_offset]:
            y_val = max(y_bound_min, min(y_bound_max, y_val))
            for x_val in x_candidates:
                x_val = max(x_bound_min, min(x_bound_max, x_val))
                if any(_point_in_rect(x_val, y_val, r, pad_x=pad_x, pad_y=pad_y) for r in all_rects):
                    continue
                if any(abs(x_val - hx) <= min_dx and abs(y_val - hy) <= min_dy for hx, hy in placed_handles):
                    continue
                return x_val, y_val

        # Fallback: keep near top-right with deterministic vertical staggering.
        base_x = max(x_bound_min, min(x_bound_max, rect["x1"] - 0.006 * x_span))
        base_y = max(y_bound_min, min(y_bound_max, rect["y1"] - 0.006 * y_span))
        stagger = (box_index % 6) * 0.022 * y_span
        return base_x, max(y_bound_min, min(y_bound_max, base_y - stagger))

    for entry in prepared_boxes:
        box_idx = entry["box_idx"]
        box = entry["box"]
        style = entry["style"]
        rect = entry["rect"]

        shape_list.append(
            {
                "type": "rect",
                "x0": rect["x0"],
                "x1": rect["x1"],
                "y0": rect["y0"],
                "y1": rect["y1"],
                "line": {"color": style["line_color"], "width": 2, "dash": style["line_dash"]},
                "fillcolor": style["fillcolor"],
                "editable": True,
                "layer": "above",
            }
        )

        x_label = rect["x0"] + (0.004 * x_span)
        y_label = rect["y1"] - (0.004 * y_span)
        x_label = max(x_min, min(x_max, x_label))
        y_label = max(y_min, min(y_max, y_label))
        annotations.append(
            {
                "x": x_label,
                "y": y_label,
                "xref": "x",
                "yref": "y",
                "xanchor": "left",
                "yanchor": "top",
                "showarrow": False,
                "editable": False,
                "text": _leaf_label_text(box.get("label")),
                "font": {"size": 10, "color": style["line_color"]},
                "bgcolor": "rgba(255,255,255,0.55)",
                "borderpad": 2,
            }
        )

        x_handle, y_handle = _choose_delete_handle(rect, box_idx)
        placed_handles.append((x_handle, y_handle))
        delete_x.append(x_handle)
        delete_y.append(y_handle)
        delete_indices.append(box_idx)

    layout["shapes"] = shape_list
    layout["annotations"] = annotations
    layout["editrevision"] = _modal_box_edit_revision(boxes, bump=revision_bump)
    fig_data = fig.get("data") or []
    if not isinstance(fig_data, list):
        fig_data = []
    fig_data = [
        trace
        for trace in fig_data
        if not (isinstance(trace, dict) and trace.get("name") == _BBOX_DELETE_TRACE_NAME)
    ]
    if delete_indices:
        fig_data.append(
            {
                "type": "scatter",
                "mode": "markers+text",
                "name": _BBOX_DELETE_TRACE_NAME,
                "showlegend": False,
                "x": delete_x,
                "y": delete_y,
                "customdata": delete_indices,
                "text": ["×"] * len(delete_indices),
                "textposition": "middle center",
                "textfont": {"size": 12, "color": "#ffffff"},
                "marker": {
                    "size": 18,
                    "opacity": 1.0,
                    "color": "rgba(220, 53, 69, 0.98)",
                    "line": {"color": "#ffffff", "width": 1},
                    "symbol": "square",
                },
                "opacity": 1.0,
                "selectedpoints": [],
                "selected": {
                    "marker": {
                        "opacity": 1.0,
                        "color": "rgba(220, 53, 69, 0.98)",
                        "line": {"color": "#ffffff", "width": 1},
                    },
                    "textfont": {"color": "#ffffff"},
                },
                "unselected": {
                    "marker": {
                        "opacity": 1.0,
                        "color": "rgba(220, 53, 69, 0.98)",
                        "line": {"color": "#ffffff", "width": 1},
                    },
                    "textfont": {"color": "#ffffff"},
                },
                "hovertemplate": "Delete box<extra></extra>",
                "cliponaxis": True,
            }
        )
    fig["data"] = fig_data
    fig["layout"] = layout
    return fig


def _extract_label_extent_map_from_boxes(boxes):
    extent_map = {}
    for label, extents in _extract_label_extent_list_map_from_boxes(boxes).items():
        if extents:
            extent_map[label] = extents[0]
    return extent_map


def _extract_label_extent_list_map_from_boxes(boxes):
    extent_map = {}
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        label = box.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        cleaned_extent = _clean_annotation_extent(box.get("annotation_extent"))
        if not cleaned_extent:
            continue
        normalized = label.strip()
        extent_map.setdefault(normalized, []).append(cleaned_extent)
    return extent_map


def _ordered_unique_labels(labels):
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


def _split_hierarchy_label(label):
    if not isinstance(label, str):
        return []
    return [part.strip() for part in label.split(">") if part and part.strip()]


def _extract_verify_leaf_classes(items):
    classes = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        predictions = item.get("predictions") or {}

        model_outputs = predictions.get("model_outputs")
        if isinstance(model_outputs, list):
            for output in model_outputs:
                if not isinstance(output, dict):
                    continue
                label = output.get("class_hierarchy")
                if isinstance(label, str) and label.strip():
                    classes.add(label.strip())

        probs = predictions.get("confidence") or {}
        if isinstance(probs, dict):
            for label in probs.keys():
                if isinstance(label, str) and label.strip():
                    classes.add(label.strip())

        labels = predictions.get("labels") or []
        if isinstance(labels, list):
            for label in labels:
                if isinstance(label, str) and label.strip():
                    classes.add(label.strip())
    return sorted(classes, key=lambda text: text.lower())


def _build_verify_filter_paths(classes):
    tree = {}
    for label in classes or []:
        parts = _split_hierarchy_label(label)
        if not parts:
            continue
        cursor = tree
        for part in parts:
            cursor = cursor.setdefault(part, {})

    ordered_paths = []

    def _walk(node, prefix):
        for part in sorted(node.keys(), key=lambda text: text.lower()):
            path_parts = prefix + [part]
            ordered_paths.append(path_parts)
            _walk(node[part], path_parts)

    _walk(tree, [])

    paths = []
    for path_parts in ordered_paths:
        paths.append(" > ".join(path_parts))
    return paths


def _build_verify_filter_tree_rows(paths, selected_paths, expanded_paths):
    selected_set = set(_ordered_unique_labels(selected_paths or []))
    expanded_set = set(_ordered_unique_labels(expanded_paths or []))

    tree = {}
    for path in paths or []:
        parts = _split_hierarchy_label(path)
        if not parts:
            continue
        cursor = tree
        for part in parts:
            cursor = cursor.setdefault(part, {})

    def _walk(node, prefix, level):
        rows = []
        for name in sorted(node.keys(), key=lambda text: text.lower()):
            path_parts = prefix + [name]
            path = " > ".join(path_parts)
            children = node[name]
            has_children = bool(children)
            is_expanded = path in expanded_set
            is_selected = path in selected_set

            rows.append(
                html.Div(
                    [
                        html.Div(
                            [
                                (
                                    html.Button(
                                        "▾" if is_expanded else "▸",
                                        id={"type": "verify-filter-expand", "path": path},
                                        n_clicks=0,
                                        className="verify-filter-expand-btn",
                                        title=("Collapse" if is_expanded else "Expand"),
                                        type="button",
                                    )
                                    if has_children
                                    else html.Span("", className="verify-filter-expand-spacer")
                                ),
                                dbc.Checkbox(
                                    id={"type": "verify-filter-checkbox", "path": path},
                                    value=is_selected,
                                    className="verify-filter-node-check",
                                ),
                                html.Span(
                                    name,
                                    className="verify-filter-node-label",
                                    title=path,
                                ),
                            ],
                            className="verify-filter-node-row",
                            style={"paddingLeft": f"{level * 16}px"},
                        ),
                        html.Div(
                            _walk(children, path_parts, level + 1),
                            className="verify-filter-children",
                            style={"display": "block" if (has_children and is_expanded) else "none"},
                        ),
                    ],
                    className="verify-filter-node-group",
                )
            )
        return rows

    return _walk(tree, [], 0)


def _normalize_verify_class_filter(class_filter):
    if class_filter is None:
        return None
    if isinstance(class_filter, str):
        normalized = class_filter.strip()
        if not normalized or normalized.lower() == "all":
            return None
        return [normalized]
    if isinstance(class_filter, (list, tuple, set)):
        return _ordered_unique_labels(class_filter)
    return None


def _predicted_labels_match_filter(predicted_labels, selected_filter_paths):
    if selected_filter_paths is None:
        return True
    if not selected_filter_paths:
        return False
    selected = [path for path in selected_filter_paths if isinstance(path, str) and path.strip()]
    if not selected:
        return False
    for label in predicted_labels or []:
        if not isinstance(label, str):
            continue
        normalized_label = label.strip()
        if not normalized_label:
            continue
        for selected_path in selected:
            if normalized_label == selected_path or normalized_label.startswith(f"{selected_path} > "):
                return True
    return False


def _has_explicit_review(annotations):
    if not isinstance(annotations, dict):
        return False
    return bool(
        annotations.get("has_manual_review")
        or annotations.get("verified")
        or annotations.get("needs_reverify")
        or annotations.get("annotated_at")
        or annotations.get("annotated_by")
    )


def _has_pending_label_edits(annotations):
    if not isinstance(annotations, dict):
        return False
    return bool(annotations.get("pending_save") or annotations.get("needs_reverify"))


def _get_modal_label_sets(item, mode, thresholds):
    predictions = item.get("predictions") or {}
    annotations = item.get("annotations") or {}
    predicted_labels = _ordered_unique_labels(_filter_predictions(predictions, thresholds or {"__global__": 0.5}))
    verified_labels = _ordered_unique_labels(annotations.get("labels") or [])
    has_explicit_review = _has_explicit_review(annotations)

    if mode == "verify":
        # If a reviewer has interacted with this item, keep their chosen label-set
        # (including empty) instead of falling back to model predictions.
        active_labels = verified_labels if has_explicit_review else predicted_labels
    else:
        # Apply the same explicit-review behavior in label mode so deleting all
        # labels does not fall back to default/predicted labels.
        active_labels = (
            verified_labels
            if has_explicit_review
            else _ordered_unique_labels(predictions.get("labels") or [])
        )

    return predicted_labels, verified_labels, active_labels


def _get_item_rejected_labels(item):
    if not isinstance(item, dict):
        return []
    annotations = item.get("annotations") or {}
    annotation_rejected = _ordered_unique_labels(annotations.get("rejected_labels") or [])
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
        return _ordered_unique_labels(rejected)
    return []


def _label_has_box(label, boxes):
    target = (label or "").strip()
    if not target:
        return False
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        box_label = (box.get("label") or "").strip()
        if box_label == target:
            extent = _clean_annotation_extent(box.get("annotation_extent"))
            if extent and extent.get("type") != "clip":
                return True
    return False


def _leaf_label_text(label):
    if not isinstance(label, str):
        return "Unlabeled"
    parts = [part.strip() for part in label.split(">") if part.strip()]
    if parts:
        return parts[-1]
    cleaned = label.strip()
    return cleaned if cleaned else "Unlabeled"


def _build_grid(items, mode, colormap, y_axis_scale, items_per_page):
    if not items:
        return [html.Div("No items loaded.", className="text-muted text-center p-4")]

    grid = []
    limit = min(items_per_page, len(items))
    for item in items[:limit]:
        image_src = get_item_image_src(item, colormap=colormap, y_axis_scale=y_axis_scale)
        card = create_spectrogram_card(item, image_src=image_src, mode=mode)
        grid.append(dbc.Col(card, md=3, sm=6, xs=12, className="mb-3"))

    return dbc.Row(grid)


def _label_badges(labels, color="primary"):
    labels = labels or []
    if not labels:
        return html.Div("No labels", className="text-muted small")
    return html.Div(
        [dbc.Badge(label, color=color, className="me-1 mb-1", style={"font-size": "0.75em"}) for label in labels],
        style={"display": "flex", "flex-wrap": "wrap"},
    )


def _build_modal_item_actions(item, mode, thresholds, boxes=None, active_box_label=None):
    if not item:
        return html.Div("No item selected.", className="text-muted small")

    annotations = item.get("annotations") or {}
    predicted_labels, verified_labels, active_labels = _get_modal_label_sets(item, mode, thresholds)
    active_labels = _ordered_unique_labels(active_labels)
    rejected_labels = _get_item_rejected_labels(item) if mode == "verify" else []
    has_explicit_review = _has_explicit_review(annotations)
    accepted_set = set(active_labels)
    rejected_labels = [label for label in _ordered_unique_labels(rejected_labels) if label not in accepted_set]
    rejected_set = set(rejected_labels)
    is_verified = bool(annotations.get("verified"))
    has_pending_edits = _has_pending_label_edits(annotations)

    accepted_rows = []
    active_label, _ = _parse_active_box_target(active_box_label)
    for label in active_labels:
        add_btn_color = "primary" if active_label == label else "outline-primary"
        delete_action = None
        if mode != "explore":
            delete_button = dbc.Button(
                html.Span("×", className="modal-label-inline-delete-glyph"),
                id={"type": "modal-label-delete-btn", "label": label},
                color="link",
                size="sm",
                className="modal-label-inline-delete",
                title=f"Delete label: {label}",
                n_clicks=0,
            )
            delete_action = dcc.ConfirmDialogProvider(
                delete_button,
                id={"type": "modal-label-delete-confirm", "label": label},
                message=f"Delete label '{label}' and all its bounding boxes?",
            )
        accepted_rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(label, className="modal-label-text"),
                            delete_action if delete_action else None,
                        ],
                        className="modal-label-pill",
                    ),
                    html.Div(
                        [
                            dbc.Button(
                                html.I(className="fas fa-plus"),
                                id={"type": "modal-label-add-box", "label": label},
                                color=add_btn_color,
                                size="sm",
                                disabled=(mode == "explore"),
                                className="modal-label-icon-btn modal-label-add-box-btn",
                                title=f"Add bounding box for: {label}",
                                n_clicks=0,
                            ),
                        ],
                        className="modal-label-bbox-col",
                    ),
                ],
                className="modal-label-row",
            )
        )

    verify_rows = []
    if mode == "verify":
        predicted_set = set(predicted_labels)
        badge_models = []
        for label in predicted_labels:
            state = "model-unreviewed"
            if label in rejected_set:
                state = "model-rejected"
            elif label in accepted_set or (is_verified and not has_pending_edits and label not in rejected_set):
                state = "model-accepted"
            badge_models.append(
                {
                    "label": label,
                    "source": "model",
                    "state": state,
                    "actions": "accept_reject",
                }
            )
        for label in active_labels:
            if label in predicted_set:
                continue
            badge_models.append(
                {
                    "label": label,
                    "source": "human",
                    "state": "human-added",
                    "actions": "delete",
                }
            )

        for model in badge_models:
            label = model.get("label")
            if not isinstance(label, str):
                continue
            source = model.get("source")
            state = model.get("state") or "model-unreviewed"
            is_model = source == "model"
            state_text = {
                "model-unreviewed": "unverified",
                "model-accepted": "accepted",
                "model-rejected": "rejected",
                "human-added": "",
            }.get(state, "")
            icon = (
                html.I(className="bi bi-robot verify-label-source-icon", title="Model-derived label")
                if is_model
                else html.I(className="bi bi-person-fill verify-label-source-icon", title="Human-added label")
            )

            action_controls = None
            if model.get("actions") == "accept_reject":
                accept_disabled = state == "model-accepted"
                reject_disabled = state == "model-rejected"
                action_controls = html.Div(
                    [
                        html.Button(
                            "✓",
                            id={"type": "modal-verify-label-accept", "target": label},
                            className="verify-inline-action verify-inline-action--accept",
                            title=f"Accept: {label}",
                            n_clicks=0,
                            disabled=accept_disabled,
                        ),
                        html.Button(
                            "×",
                            id={"type": "modal-verify-label-reject", "target": label},
                            className="verify-inline-action verify-inline-action--reject",
                            title=f"Reject: {label}",
                            n_clicks=0,
                            disabled=reject_disabled,
                        ),
                    ],
                    className="verify-inline-actions",
                )
            elif model.get("actions") == "delete":
                action_controls = html.Div(
                    [
                        html.Button(
                            "×",
                            id={"type": "modal-verify-label-delete", "target": label},
                            className="verify-inline-action verify-inline-action--reject",
                            title=f"Delete: {label}",
                            n_clicks=0,
                        ),
                    ],
                    className="verify-inline-actions",
                )

            bbox_control = None
            if label in accepted_set:
                add_btn_color = "primary" if active_label == label else "outline-primary"
                bbox_control = html.Div(
                    [
                        dbc.Button(
                            html.I(className="fas fa-plus"),
                            id={"type": "modal-label-add-box", "label": label},
                            color=add_btn_color,
                            size="sm",
                            disabled=(mode == "explore"),
                            className="modal-label-icon-btn modal-label-add-box-btn",
                            title=f"Add bounding box for: {label}",
                            n_clicks=0,
                        ),
                    ],
                    className="modal-label-bbox-col",
                )
            else:
                bbox_control = html.Div([], className="modal-label-bbox-col")

            verify_rows.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                icon,
                                                html.Span(state_text, className="verify-label-state")
                                                if state_text
                                                else None,
                                            ],
                                            className="verify-label-row-meta",
                                        ),
                                        action_controls,
                                    ],
                                    className="verify-label-row-header",
                                ),
                                html.Span(label, className="verify-label-text verify-label-text--multiline"),
                            ],
                            className=f"verify-label-badge verify-label-badge--{state} verify-label-badge--row",
                        ),
                        bbox_control,
                    ],
                    className="modal-label-row modal-label-row--verify",
                )
            )

    action_buttons = []
    status_note = None

    if mode == "verify":
        if is_verified:
            status_note = "Verified" if not has_pending_edits else "Verified, unsaved label edits"
        else:
            status_note = "Unverified" if not has_pending_edits else "Unverified, unsaved label edits"
        action_buttons = [
            dbc.Button(
                "Save",
                id={"type": "modal-action-confirm", "scope": "modal"},
                color="success" if has_pending_edits else "secondary",
                size="sm",
                disabled=not has_pending_edits,
                outline=not has_pending_edits,
                className="me-2",
            ),
            dbc.Button(
                "Edit",
                id={"type": "modal-action-edit", "scope": "modal"},
                color="secondary",
                size="sm",
            ),
        ]
    elif mode == "label":
        status_note = "Unsaved label edits" if has_pending_edits else "All changes saved"
        action_buttons = [
            dbc.Button(
                "Save",
                id={"type": "modal-label-save", "scope": "modal"},
                color="success" if has_pending_edits else "secondary",
                disabled=not has_pending_edits,
                outline=not has_pending_edits,
                size="sm",
                className="me-2",
            ),
            dbc.Button(
                "Edit Labels",
                id={"type": "modal-action-edit", "scope": "modal"},
                color="secondary",
                size="sm",
            ),
        ]
    else:
        status_note = "Explore mode is read-only."

    if mode == "verify":
        verify_meta = f"Predicted: {len(predicted_labels)} | Current: {len(active_labels)}"
        status_note = f"{verify_meta} | {status_note}" if status_note else verify_meta

    if mode == "verify":
        return html.Div(
            [
                html.Div("Labels", className="small fw-semibold text-muted mb-2"),
                (
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Label", className="modal-label-col-title"),
                                    html.Span("BBox", className="modal-bbox-col-title"),
                                ],
                                className="modal-label-table-header",
                            ),
                            html.Div(verify_rows, className="modal-label-list"),
                        ],
                        className="modal-label-table mb-3",
                    )
                    if verify_rows
                    else html.Div("No labels", className="text-muted small mb-3")
                ),
                html.Div(status_note, className="modal-status-note") if status_note else None,
                html.Div(action_buttons, className="modal-action-buttons") if action_buttons else None,
            ],
            className="modal-item-actions-card",
        )

    return html.Div(
        [
            html.Div("Labels", className="small fw-semibold text-muted mb-2"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Label", className="modal-label-col-title"),
                            html.Span("BBox", className="modal-bbox-col-title"),
                        ],
                        className="modal-label-table-header",
                    ),
                    html.Div(accepted_rows, className="modal-label-list"),
                ],
                className="modal-label-table",
            )
            if accepted_rows
            else html.Div("No labels", className="text-muted small"),
            html.Div(status_note, className="modal-status-note") if status_note else None,
            html.Div(action_buttons, className="modal-action-buttons") if action_buttons else None,
        ],
        className="modal-item-actions-card",
    )


def _get_modal_navigation_items(
    mode,
    label_data,
    verify_data,
    explore_data,
    thresholds,
    class_filter,
):
    mode = mode or "label"

    if mode == "verify":
        data = verify_data or {}
        items = data.get("items", [])
        thresholds = thresholds or {"__global__": 0.5}
        available_values = set(_build_verify_filter_paths(_extract_verify_leaf_classes(items)))
        selected_filters = _normalize_verify_class_filter(class_filter)
        if not available_values:
            selected_filters = None
        if selected_filters is not None:
            selected_filters = [value for value in selected_filters if value in available_values]
        filtered_items = []
        for item in items:
            if not item:
                continue
            annotations = (item.get("annotations") or {})
            is_verified = bool(annotations.get("verified"))
            predictions = item.get("predictions") or {}
            predicted_labels = _filter_predictions(predictions, thresholds)
            if not is_verified and not predicted_labels:
                continue
            if not _predicted_labels_match_filter(predicted_labels, selected_filters):
                continue
            display_item = dict(item)
            display_predictions = dict(predictions)
            display_predictions["labels"] = predicted_labels
            display_item["predictions"] = display_predictions
            display_item["ui_rejected_labels"] = _get_item_rejected_labels(item)
            filtered_items.append(display_item)
        return filtered_items

    if mode == "explore":
        data = explore_data or {}
        items = data.get("items", [])
        return items

    data = label_data or {}
    items = data.get("items", [])
    return items


def _get_mode_data(mode, label_data, verify_data, explore_data):
    return {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}


def _replace_item_in_data(data, item_id, replacement_item):
    if not isinstance(data, dict) or not item_id:
        return data
    updated = deepcopy(data)
    items = updated.get("items")
    if not isinstance(items, list):
        return updated
    replaced = False
    for idx, item in enumerate(items):
        if isinstance(item, dict) and item.get("item_id") == item_id:
            items[idx] = deepcopy(replacement_item) if isinstance(replacement_item, dict) else replacement_item
            replaced = True
            break
    if not replaced:
        return updated

    summary = updated.get("summary")
    if isinstance(summary, dict):
        summary["annotated"] = sum(
            1
            for item in items
            if isinstance(item, dict) and ((item.get("annotations") or {}).get("labels") or [])
        )
        summary["verified"] = sum(
            1
            for item in items
            if isinstance(item, dict) and bool((item.get("annotations") or {}).get("verified"))
        )
        updated["summary"] = summary
    return updated


def _modal_snapshot_payload(mode, item_id, item, boxes):
    if not item_id or not isinstance(item, dict):
        return None
    return {
        "mode": mode or "label",
        "item_id": item_id,
        "item": deepcopy(item),
        "boxes": deepcopy(boxes) if isinstance(boxes, list) else [],
    }


def _is_modal_dirty(unsaved_store, current_item_id=None):
    if not isinstance(unsaved_store, dict):
        return False
    if not bool(unsaved_store.get("dirty")):
        return False
    dirty_item = unsaved_store.get("item_id")
    if current_item_id and dirty_item and dirty_item != current_item_id:
        return False
    return True


def _persist_modal_item_before_exit(
    mode,
    item_id,
    label_data,
    verify_data,
    explore_data,
    thresholds,
    profile,
    bbox_store,
    label_output_path,
    cfg,
):
    """Persist modal edits for the active item, then allow pending modal action."""
    mode = (mode or "label").strip()
    if not item_id:
        return no_update, no_update, no_update
    _require_complete_profile(profile, "persist_modal_item_before_exit")

    profile_name = _profile_actor(profile)

    if mode == "label":
        data = deepcopy(label_data or {})
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return no_update, no_update, no_update
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            return no_update, no_update, no_update

        _, _, active_labels = _get_modal_label_sets(active_item, "label", thresholds or {"__global__": 0.5})
        labels_to_save = _ordered_unique_labels(active_labels)
        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        note_text = annotations_obj.get("notes", "") if isinstance(annotations_obj.get("notes"), str) else ""

        label_extents = {}
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            label_extents = _extract_label_extent_map_from_boxes(bbox_store.get("boxes") or [])
        else:
            existing_extents = annotations_obj.get("label_extents")
            if isinstance(existing_extents, dict):
                for label, extent in existing_extents.items():
                    if not isinstance(label, str):
                        continue
                    normalized_label = label.strip()
                    if not normalized_label:
                        continue
                    cleaned_extent = _clean_annotation_extent(extent)
                    if cleaned_extent:
                        label_extents[normalized_label] = cleaned_extent

        updated = _update_item_labels(
            data,
            item_id,
            labels_to_save,
            mode="label",
            user_name=profile_name,
            label_extents=label_extents or None,
        )
        updated = _update_item_notes(updated or {}, item_id, note_text, user_name=profile_name)

        labels_file = (
            label_output_path
            or (updated or {}).get("summary", {}).get("labels_file")
            or ((cfg or {}).get("label", {}).get("output_file"))
        )
        save_label_mode(
            labels_file,
            item_id,
            labels_to_save,
            annotated_by=profile_name,
            notes=note_text,
            label_extents=label_extents or None,
        )
        updated = _update_item_labels(
            updated or {},
            item_id,
            labels_to_save,
            mode="label",
            user_name=profile_name,
            is_reverification=True,
            label_extents=label_extents or None,
        )
        return updated, no_update, no_update

    if mode == "verify":
        thresholds = thresholds or {"__global__": 0.5}
        data = deepcopy(verify_data or {})
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return no_update, no_update, no_update
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            return no_update, no_update, no_update

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        predictions = active_item.get("predictions") if isinstance(active_item.get("predictions"), dict) else {}

        _, _, active_labels = _get_modal_label_sets(active_item, "verify", thresholds)
        labels_to_confirm = _ordered_unique_labels(active_labels)
        labels_set = set(labels_to_confirm)
        predicted_labels = _ordered_unique_labels(_filter_predictions(predictions, thresholds))
        predicted_set = set(predicted_labels)

        model_extent_map = {}
        model_scores = {}
        model_outputs = predictions.get("model_outputs")
        if isinstance(model_outputs, list):
            for output in model_outputs:
                if not isinstance(output, dict):
                    continue
                label = output.get("class_hierarchy")
                if not isinstance(label, str) or not label.strip():
                    continue
                label = label.strip()
                score = output.get("score")
                if isinstance(score, (int, float)):
                    model_scores[label] = float(score)
                cleaned_extent = _clean_annotation_extent(output.get("annotation_extent"))
                if cleaned_extent:
                    model_extent_map[label] = cleaned_extent
        else:
            confidence = predictions.get("confidence") if isinstance(predictions.get("confidence"), dict) else {}
            for label, score in confidence.items():
                if isinstance(label, str) and isinstance(score, (int, float)):
                    model_scores[label.strip()] = float(score)

        box_extent_map = {}
        box_extent_lists = {}
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            modal_boxes = bbox_store.get("boxes") or []
            box_extent_map = _extract_label_extent_map_from_boxes(modal_boxes)
            box_extent_lists = _extract_label_extent_list_map_from_boxes(modal_boxes)
        else:
            existing_extents = annotations_obj.get("label_extents")
            if isinstance(existing_extents, dict):
                for label, extent in existing_extents.items():
                    if not isinstance(label, str) or not label.strip():
                        continue
                    cleaned_extent = _clean_annotation_extent(extent)
                    if not cleaned_extent:
                        continue
                    label = label.strip()
                    box_extent_map[label] = cleaned_extent
                    box_extent_lists[label] = [cleaned_extent]

        threshold_used = float(thresholds.get("__global__", 0.5))
        rejected_labels = set(_ordered_unique_labels(annotations_obj.get("rejected_labels") or []))
        for label in predicted_labels:
            if label not in labels_set:
                rejected_labels.add(label)
        for label in labels_to_confirm:
            rejected_labels.discard(label)

        label_decisions = []
        for label in labels_to_confirm:
            decision = "accepted" if label in predicted_set else "added"
            entry = {
                "label": label,
                "decision": decision,
                "threshold_used": threshold_used,
            }
            label_extents = box_extent_lists.get(label) or []
            extent = (label_extents[0] if label_extents else None) or model_extent_map.get(label)
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)
            for extra_extent in label_extents[1:]:
                if not isinstance(extra_extent, dict):
                    continue
                label_decisions.append(
                    {
                        "label": label,
                        "decision": decision,
                        "threshold_used": threshold_used,
                        "annotation_extent": extra_extent,
                    }
                )

        for label in sorted(rejected_labels - labels_set):
            entry = {
                "label": label,
                "decision": "rejected",
                "threshold_used": threshold_used,
            }
            label_extents = box_extent_lists.get(label) or []
            extent = model_extent_map.get(label) or (label_extents[0] if label_extents else box_extent_map.get(label))
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)

        note_text = annotations_obj.get("notes", "") if isinstance(annotations_obj.get("notes"), str) else ""
        verification = {
            "verified_at": datetime.now().isoformat(),
            "verified_by": profile_name or "anonymous",
            "label_decisions": label_decisions,
            "verification_status": "verified",
            "notes": note_text,
        }

        predictions_path = (active_item.get("metadata") or {}).get("predictions_path")
        if not predictions_path:
            summary_pred = (data or {}).get("summary", {}).get("predictions_file")
            if isinstance(summary_pred, str) and summary_pred.endswith(".json"):
                predictions_path = summary_pred

        updated = _update_item_labels(
            data,
            item_id,
            labels_to_confirm,
            mode="verify",
            user_name=profile_name,
            is_reverification=True,
            label_extents=box_extent_map or None,
        )
        for item in (updated or {}).get("items", []):
            if not isinstance(item, dict) or item.get("item_id") != item_id:
                continue
            item_annotations = item.get("annotations") or {}
            item_annotations["rejected_labels"] = sorted(rejected_labels)
            item["annotations"] = item_annotations
            break

        stored_verification = save_verify_predictions(predictions_path, item_id, verification)
        if stored_verification:
            for item in (updated or {}).get("items", []):
                if item.get("item_id") != item_id:
                    continue
                verifications = item.get("verifications")
                if not isinstance(verifications, list):
                    verifications = []
                verifications.append(stored_verification)
                item["verifications"] = verifications
                break

        return no_update, updated, no_update

    # Explore mode is read-only.
    return no_update, no_update, no_update


def _create_folder_display(display_text, folders_list, data_root, popover_id):
    """Create a folder display — hoverable popover if multiple folders, plain text if single."""
    if folders_list and len(folders_list) > 1:
        relative_paths = []
        for f in folders_list:
            if data_root and f.startswith(data_root):
                relative_paths.append(f[len(data_root):].lstrip("/"))
            else:
                relative_paths.append(f)
        folder_items = [html.Div(p, className="mono-muted small") for p in relative_paths]
        return html.Div([
            html.Span(
                display_text,
                id=popover_id,
                style={"cursor": "pointer", "textDecoration": "underline", "color": "var(--link)"}
            ),
            dbc.Popover(
                dbc.PopoverBody(
                    html.Div(folder_items, style={"maxHeight": "200px", "overflowY": "auto"})
                ),
                target=popover_id,
                trigger="hover",
                placement="bottom",
            ),
        ])
    return display_text


def register_callbacks(app, config):
    set_cache_sizes((config or {}).get("cache", {}).get("max_size", 400))

    # ── Tab switching: buttons → store ─────────────────────────
    app.clientside_callback(
        """
        function(labelClicks, verifyClicks, exploreClicks) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (ctx && ctx.triggered && ctx.triggered.length > 0) {
                var id = ctx.triggered[0].prop_id.split('.')[0];
                if (id === 'tab-btn-label') return 'label';
                if (id === 'tab-btn-verify') return 'verify';
                if (id === 'tab-btn-explore') return 'explore';
                return dc.no_update;
            }
            var lc = labelClicks || 0;
            var vc = verifyClicks || 0;
            var ec = exploreClicks || 0;
            var max = Math.max(lc, vc, ec);
            if (max === 0) return dc.no_update;
            if (max === lc) return 'label';
            if (max === vc) return 'verify';
            return 'explore';
        }
        """,
        Output("mode-tabs", "data"),
        [Input("tab-btn-label", "n_clicks"),
         Input("tab-btn-verify", "n_clicks"),
         Input("tab-btn-explore", "n_clicks")],
        prevent_initial_call=True,
    )

    # ── Tab switching: store → update UI ────────────────────────
    app.clientside_callback(
        """
        function(mode) {
            var labelStyle = {display: mode === 'label' ? 'block' : 'none'};
            var verifyStyle = {display: mode === 'verify' ? 'block' : 'none'};
            var exploreStyle = {display: mode === 'explore' ? 'block' : 'none'};
            var labelClass = 'mode-tab' + (mode === 'label' ? ' mode-tab--active' : '');
            var verifyClass = 'mode-tab' + (mode === 'verify' ? ' mode-tab--active' : '');
            var exploreClass = 'mode-tab' + (mode === 'explore' ? ' mode-tab--active' : '');
            return [labelStyle, verifyStyle, exploreStyle, labelClass, verifyClass, exploreClass];
        }
        """,
        [Output("label-tab-content", "style"),
         Output("verify-tab-content", "style"),
         Output("explore-tab-content", "style"),
         Output("tab-btn-label", "className"),
         Output("tab-btn-verify", "className"),
         Output("tab-btn-explore", "className")],
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("data-load-trigger-store", "data", allow_duplicate=True),
        Input("global-load-btn", "n_clicks"),
        State("mode-tabs", "data"),
        State("config-store", "data"),
        State("global-date-selector", "value"),
        State("global-device-selector", "value"),
        prevent_initial_call=True,
    )
    def trigger_global_load(n_clicks, mode, cfg, date_value, device_value):
        """Trigger data loading for the active tab from the top-level Load button."""
        if not n_clicks:
            raise PreventUpdate
        active_mode = mode or "label"
        payload = {
            "timestamp": time.time(),
            "mode": active_mode,
            "source": "global-load",
            "config": cfg or {},
            "date_value": date_value,
            "device_value": device_value,
        }
        _tab_iso_debug(
            "global_load_trigger",
            n_clicks=n_clicks,
            active_mode=active_mode,
            date_value=date_value,
            device_value=device_value,
            cfg_data_dir=_config_default_data_dir(cfg or {}),
        )
        return payload

    @app.callback(
        Output("label-data-store", "data"),
        Input("label-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
    )
    def load_label_data(reload_clicks, config_load_trigger, date_val, device_val, cfg, mode, current_label_data):
        """Load data specifically for Label mode."""
        # Check all triggered inputs (not just triggered_id) since multiple may change at once
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        # Get the mode that triggered the data load (if any)
        trigger_mode = None
        trigger_source = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")
            trigger_source = config_load_trigger.get("source")

        trigger_cfg_snapshot = (
            config_load_trigger.get("config")
            if isinstance(config_load_trigger, dict) and isinstance(config_load_trigger.get("config"), dict)
            else None
        )
        _tab_iso_debug(
            "load_label_start",
            mode=mode,
            trigger_mode=trigger_mode,
            trigger_source=trigger_source,
            triggered_props=sorted(triggered_props),
            date_val=date_val,
            device_val=device_val,
            cfg_data_dir=_config_default_data_dir(cfg or {}),
            trigger_cfg_data_dir=_config_default_data_dir(trigger_cfg_snapshot),
            current_label_snapshot=_tab_data_snapshot(current_label_data),
        )

        # Only process if in label mode
        if mode != "label":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Label data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in label mode (already checked above)
        # Note: We check for source_data_dir rather than config matching because config-store
        # gets overwritten when loading data in other tabs (e.g., verify), so it won't match
        # the label data's source after switching tabs.
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = bool(current_label_data and current_label_data.get("source_data_dir"))

        # Load on: reload button, config load (for label mode only), or filter change (only if label data exists)
        # Note: trigger_mode == "label" means data-load-trigger-store was set for label mode,
        # even if ctx.triggered_id reports a different input (due to simultaneous updates)
        config_panel_trigger = (
            "data-load-trigger-store" in triggered_props and trigger_source == "data-config-load"
        )
        should_load = (
            "label-reload" in triggered_props or
            trigger_mode == "label" or
            config_panel_trigger or
            (filter_triggered and has_source)
        )
        _tab_iso_debug(
            "load_label_decision",
            filter_triggered=bool(filter_triggered),
            has_source=bool(has_source),
            config_panel_trigger=config_panel_trigger,
            should_load=should_load,
        )

        if should_load:
            try:
                trigger_cfg = None
                requested_date = date_val
                requested_device = device_val
                if isinstance(config_load_trigger, dict) and "data-load-trigger-store" in triggered_props:
                    trigger_cfg = config_load_trigger.get("config")
                    requested_date = config_load_trigger.get("date_value", requested_date)
                    requested_device = config_load_trigger.get("device_value", requested_device)

                effective_cfg = trigger_cfg.copy() if trigger_cfg else (cfg.copy() if cfg else {})
                data_cfg = dict(effective_cfg.get("data", {}))
                active_data_dir = _resolve_tab_data_dir(
                    cfg,
                    current_tab_data=current_label_data,
                    trigger_cfg=trigger_cfg,
                    trigger_source=trigger_source,
                )
                _tab_iso_debug(
                    "load_label_resolved_root",
                    active_data_dir=active_data_dir,
                    cfg_data_dir=_config_default_data_dir(cfg or {}),
                    trigger_cfg_data_dir=_config_default_data_dir(trigger_cfg or {}),
                    current_source_data_dir=(current_label_data or {}).get("source_data_dir") if isinstance(current_label_data, dict) else None,
                )
                if active_data_dir:
                    data_cfg["data_dir"] = active_data_dir

                # Keep Label mode labels source isolated from Verify/Explore config updates.
                explicit_label_config_load = (
                    "data-load-trigger-store" in triggered_props
                    and trigger_source == "data-config-load"
                    and trigger_mode == "label"
                )
                if not explicit_label_config_load and isinstance(current_label_data, dict):
                    current_label_file = (
                        (current_label_data.get("summary") or {}).get("labels_file")
                        if isinstance(current_label_data.get("summary"), dict)
                        else None
                    )
                    if current_label_file:
                        data_cfg["predictions_file"] = current_label_file
                effective_cfg["data"] = data_cfg

                data = load_dataset(effective_cfg, "label", date_str=requested_date, hydrophone=requested_device)

                # Preserve manual labels path if it exists in current data
                # This prevents filter changes or tab switches from resetting a manually entered path
                if current_label_data and isinstance(current_label_data, dict):
                    old_summary = current_label_data.get("summary", {})
                    if old_summary.get("labels_file"):
                        data["summary"]["labels_file"] = old_summary["labels_file"]

                if "data-load-trigger-store" in triggered_props and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                elif filter_triggered:
                    data["load_timestamp"] = time.time()
                else:
                    data["load_timestamp"] = time.time()

                # Keep source root aligned with the loaded configuration.
                data["source_data_dir"] = active_data_dir
                from app.main import set_audio_roots
                set_audio_roots(data.get("audio_roots", []))
                _tab_iso_debug(
                    "load_label_success",
                    requested_date=requested_date,
                    requested_device=requested_device,
                    effective_predictions_file=(effective_cfg.get("data") or {}).get("predictions_file"),
                    loaded_label_snapshot=_tab_data_snapshot(data),
                )
                return data
            except Exception as e:
                _tab_iso_debug("load_label_error", error=str(e))
                print(f"Error loading label dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate

    @app.callback(
        Output("verify-data-store", "data"),
        Input("verify-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("verify-data-store", "data"),
    )
    def load_verify_data(reload_clicks, config_load_trigger, date_val, device_val, cfg, mode, current_verify_data):
        """Load data specifically for Verify mode."""
        # Check all triggered inputs (not just triggered_id) since multiple may change at once
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        # Get the mode that triggered the data load (if any)
        trigger_mode = None
        trigger_source = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")
            trigger_source = config_load_trigger.get("source")

        trigger_cfg_snapshot = (
            config_load_trigger.get("config")
            if isinstance(config_load_trigger, dict) and isinstance(config_load_trigger.get("config"), dict)
            else None
        )
        _tab_iso_debug(
            "load_verify_start",
            mode=mode,
            trigger_mode=trigger_mode,
            trigger_source=trigger_source,
            triggered_props=sorted(triggered_props),
            date_val=date_val,
            device_val=device_val,
            cfg_data_dir=_config_default_data_dir(cfg or {}),
            trigger_cfg_data_dir=_config_default_data_dir(trigger_cfg_snapshot),
            current_verify_snapshot=_tab_data_snapshot(current_verify_data),
        )

        # Only process if in verify mode
        if mode != "verify":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Verify data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in verify mode (already checked above)
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = bool(current_verify_data and current_verify_data.get("source_data_dir"))

        # Load on: reload button, config load (for verify mode only), or filter change (only if verify data exists)
        config_panel_trigger = (
            "data-load-trigger-store" in triggered_props and trigger_source == "data-config-load"
        )
        should_load = (
            "verify-reload" in triggered_props or
            trigger_mode == "verify" or
            config_panel_trigger or
            (filter_triggered and has_source)
        )
        _tab_iso_debug(
            "load_verify_decision",
            filter_triggered=bool(filter_triggered),
            has_source=bool(has_source),
            config_panel_trigger=config_panel_trigger,
            should_load=should_load,
        )

        if should_load:
            try:
                trigger_cfg = None
                requested_date = date_val
                requested_device = device_val
                if isinstance(config_load_trigger, dict) and "data-load-trigger-store" in triggered_props:
                    trigger_cfg = config_load_trigger.get("config")
                    requested_date = config_load_trigger.get("date_value", requested_date)
                    requested_device = config_load_trigger.get("device_value", requested_device)

                effective_cfg = trigger_cfg.copy() if trigger_cfg else (cfg.copy() if cfg else {})
                data_cfg = dict(effective_cfg.get("data", {}))
                active_data_dir = _resolve_tab_data_dir(
                    cfg,
                    current_tab_data=current_verify_data,
                    trigger_cfg=trigger_cfg,
                    trigger_source=trigger_source,
                )
                _tab_iso_debug(
                    "load_verify_resolved_root",
                    active_data_dir=active_data_dir,
                    cfg_data_dir=_config_default_data_dir(cfg or {}),
                    trigger_cfg_data_dir=_config_default_data_dir(trigger_cfg or {}),
                    current_source_data_dir=(current_verify_data or {}).get("source_data_dir") if isinstance(current_verify_data, dict) else None,
                )
                if active_data_dir:
                    data_cfg["data_dir"] = active_data_dir

                # Keep Verify mode predictions source isolated from Label/Explore config updates.
                explicit_verify_config_load = (
                    "data-load-trigger-store" in triggered_props
                    and trigger_source == "data-config-load"
                    and trigger_mode == "verify"
                )
                if not explicit_verify_config_load and isinstance(current_verify_data, dict):
                    current_pred_file = (
                        (current_verify_data.get("summary") or {}).get("predictions_file")
                        if isinstance(current_verify_data.get("summary"), dict)
                        else None
                    )
                    if current_pred_file and isinstance(current_pred_file, str):
                        data_cfg["predictions_file"] = current_pred_file
                effective_cfg["data"] = data_cfg

                data = load_dataset(effective_cfg, "verify", date_str=requested_date, hydrophone=requested_device)

                # Preserve manual predictions path if it exists in current data
                if current_verify_data and isinstance(current_verify_data, dict):
                    old_summary = current_verify_data.get("summary", {})
                    if old_summary.get("predictions_file"):
                        data["summary"]["predictions_file"] = old_summary["predictions_file"]

                if "data-load-trigger-store" in triggered_props and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                elif filter_triggered:
                    data["load_timestamp"] = time.time()
                else:
                    data["load_timestamp"] = time.time()

                data["source_data_dir"] = active_data_dir
                from app.main import set_audio_roots
                set_audio_roots(data.get("audio_roots", []))
                _tab_iso_debug(
                    "load_verify_success",
                    requested_date=requested_date,
                    requested_device=requested_device,
                    effective_predictions_file=(effective_cfg.get("data") or {}).get("predictions_file"),
                    loaded_verify_snapshot=_tab_data_snapshot(data),
                )
                return data
            except Exception as e:
                _tab_iso_debug("load_verify_error", error=str(e))
                print(f"Error loading verify dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate

    @app.callback(
        Output("explore-data-store", "data"),
        Input("explore-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("explore-data-store", "data"),
    )
    def load_explore_data(reload_clicks, config_load_trigger, date_val, device_val, cfg, mode, current_explore_data):
        """Load data specifically for Explore mode."""
        # Check all triggered inputs (not just triggered_id) since multiple may change at once
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        # Get the mode that triggered the data load (if any)
        trigger_mode = None
        trigger_source = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")
            trigger_source = config_load_trigger.get("source")

        trigger_cfg_snapshot = (
            config_load_trigger.get("config")
            if isinstance(config_load_trigger, dict) and isinstance(config_load_trigger.get("config"), dict)
            else None
        )
        _tab_iso_debug(
            "load_explore_start",
            mode=mode,
            trigger_mode=trigger_mode,
            trigger_source=trigger_source,
            triggered_props=sorted(triggered_props),
            date_val=date_val,
            device_val=device_val,
            cfg_data_dir=_config_default_data_dir(cfg or {}),
            trigger_cfg_data_dir=_config_default_data_dir(trigger_cfg_snapshot),
            current_explore_snapshot=_tab_data_snapshot(current_explore_data),
        )

        # Only process if in explore mode
        if mode != "explore":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Explore data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in explore mode (already checked above)
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = bool(current_explore_data and current_explore_data.get("source_data_dir"))

        # Load on: reload button, config load (for explore mode only), or filter change (only if explore data exists)
        config_panel_trigger = (
            "data-load-trigger-store" in triggered_props and trigger_source == "data-config-load"
        )
        should_load = (
            "explore-reload" in triggered_props or
            trigger_mode == "explore" or
            config_panel_trigger or
            (filter_triggered and has_source)
        )
        _tab_iso_debug(
            "load_explore_decision",
            filter_triggered=bool(filter_triggered),
            has_source=bool(has_source),
            config_panel_trigger=config_panel_trigger,
            should_load=should_load,
        )

        if should_load:
            try:
                trigger_cfg = None
                requested_date = date_val
                requested_device = device_val
                if isinstance(config_load_trigger, dict) and "data-load-trigger-store" in triggered_props:
                    trigger_cfg = config_load_trigger.get("config")
                    requested_date = config_load_trigger.get("date_value", requested_date)
                    requested_device = config_load_trigger.get("device_value", requested_device)

                effective_cfg = trigger_cfg.copy() if trigger_cfg else (cfg.copy() if cfg else {})
                data_cfg = dict(effective_cfg.get("data", {}))
                active_data_dir = _resolve_tab_data_dir(
                    cfg,
                    current_tab_data=current_explore_data,
                    trigger_cfg=trigger_cfg,
                    trigger_source=trigger_source,
                )
                _tab_iso_debug(
                    "load_explore_resolved_root",
                    active_data_dir=active_data_dir,
                    cfg_data_dir=_config_default_data_dir(cfg or {}),
                    trigger_cfg_data_dir=_config_default_data_dir(trigger_cfg or {}),
                    current_source_data_dir=(current_explore_data or {}).get("source_data_dir") if isinstance(current_explore_data, dict) else None,
                )
                if active_data_dir:
                    data_cfg["data_dir"] = active_data_dir
                effective_cfg["data"] = data_cfg

                data = load_dataset(effective_cfg, "explore", date_str=requested_date, hydrophone=requested_device)
                if "data-load-trigger-store" in triggered_props and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                elif filter_triggered:
                    data["load_timestamp"] = time.time()
                else:
                    data["load_timestamp"] = time.time()
                data["source_data_dir"] = active_data_dir
                from app.main import set_audio_roots
                set_audio_roots(data.get("audio_roots", []))
                _tab_iso_debug(
                    "load_explore_success",
                    requested_date=requested_date,
                    requested_device=requested_device,
                    loaded_explore_snapshot=_tab_data_snapshot(data),
                )
                return data
            except Exception as e:
                _tab_iso_debug("load_explore_error", error=str(e))
                print(f"Error loading explore dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate

    @app.callback(
        Output("label-summary", "children"),
        Output("label-grid", "children"),
        Output("label-page-info", "children"),
        Output("label-page-input", "max"),
        Output("label-spec-folder-display", "children", allow_duplicate=True),
        Output("label-audio-folder-display", "children", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Output("label-ui-ready-store", "data"),
        Input("label-data-store", "data"),
        Input("label-colormap-toggle", "value"),
        Input("label-yaxis-toggle", "value"),
        Input("label-current-page", "data"),
        Input("config-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def render_label(data, use_hydrophone_colormap, use_log_y_axis, current_page, cfg, mode):
        # Render even if not in label mode (to maintain state when switching back)
        pass

        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        
        # Calculate pagination
        total_items = len(items)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))
        
        # Slice items for current page
        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = items[start_idx:end_idx]

        summary_block = html.Div([
            html.Span(f"Items: {summary.get('total_items', len(items))}", className="fw-semibold"),
            html.Span(f"Annotated: {summary.get('annotated', 0)}", className="ms-3 text-muted"),
        ])
        
        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "label", colormap, y_axis_scale, items_per_page)
        
        # Update folder displays with popover support for multiple folders
        data_root = summary.get("data_root", "")
        folder_display = _create_folder_display(
            summary.get("spectrogram_folder") or "Not set",
            summary.get("spectrogram_folders_list", []),
            data_root, "label-spec-popover"
        )
        audio_folder_display = _create_folder_display(
            summary.get("audio_folder") or "Not set",
            summary.get("audio_folders_list", []),
            data_root, "label-audio-popover"
        )
        labels_file_display = summary.get("labels_file") or no_update

        ui_ready = no_update
        if (data or {}).get("load_timestamp"):
            ui_ready = {"timestamp": data.get("load_timestamp")}

        return (
            summary_block,
            grid,
            page_info,
            total_pages,
            folder_display,
            audio_folder_display,
            labels_file_display,
            ui_ready,
        )

    @app.callback(
        Output("verify-summary", "children"),
        Output("verify-grid", "children"),
        Output("verify-page-info", "children"),
        Output("verify-page-input", "max"),
        Output("verify-spec-folder-display", "children"),
        Output("verify-audio-folder-display", "children"),
        Output("verify-predictions-display", "children"),
        Output("verify-data-root-display", "children"),
        Output("verify-ui-ready-store", "data"),
        Input("verify-data-store", "data"),
        Input("verify-thresholds-store", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-current-page", "data"),
        Input("verify-colormap-toggle", "value"),
        Input("verify-yaxis-toggle", "value"),
        Input("config-store", "data"),
        State("mode-tabs", "data"),
    )
    def render_verify(data, thresholds, class_filter, current_page, use_hydrophone_colormap, use_log_y_axis, cfg, mode):
        # Render even if not in verify mode (to maintain state when switching back)
        pass

        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])
        thresholds = thresholds or {"__global__": 0.5}
        available_values = _build_verify_filter_paths(_extract_verify_leaf_classes(items))
        available_value_set = set(available_values)
        selected_filters = _normalize_verify_class_filter(class_filter)
        if not available_values:
            selected_filters = None
        if selected_filters is not None:
            selected_filters = [value for value in selected_filters if value in available_value_set]
        current_threshold = float(thresholds.get("__global__", 0.5))

        # Get folder display info from summary
        spec_folder = summary.get("spectrogram_folder") or "Not set"
        audio_folder = summary.get("audio_folder") or "Not set"
        predictions_file = summary.get("predictions_file") or "Not set"

        filtered_items = []
        for item in items:
            if not item:
                continue
            annotations = (item.get("annotations") or {})
            is_verified = bool(annotations.get("verified"))
            predictions = item.get("predictions") or {}
            predicted_labels = _filter_predictions(predictions, thresholds)

            if not is_verified and not predicted_labels:
                continue

            if not _predicted_labels_match_filter(predicted_labels, selected_filters):
                continue

            display_item = dict(item)
            display_predictions = dict(predictions)
            display_predictions["labels"] = predicted_labels
            display_item["predictions"] = display_predictions
            filtered_items.append(display_item)

        if selected_filters is None:
            filter_text = "All selected"
        elif not selected_filters:
            filter_text = "None selected"
        elif available_values and len(selected_filters) == len(available_values):
            filter_text = "All selected"
        else:
            filter_text = f"{len(selected_filters)} selected"

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Visible: {len(filtered_items)}", className="fw-semibold"),
            html.Span(f"Total: {summary.get('total_items', len(items))}", className="ms-3 text-muted"),
            html.Span(f"Verified: {summary.get('verified', 0)}", className="ms-3 text-muted"),
            html.Span(f"Threshold: {current_threshold*100:.0f}%", className="ms-3 text-muted"),
            html.Span(f"Filter: {filter_text}", className="ms-3 text-muted"),
        ], className="summary-info")

        total_items = len(filtered_items)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))

        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = filtered_items[start_idx:end_idx]

        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "verify", colormap, y_axis_scale, items_per_page)
        
        data_root = summary.get("data_root") or "Not set"

        spec_folder_display = _create_folder_display(
            summary.get("spectrogram_folder") or "Not set",
            summary.get("spectrogram_folders_list", []),
            summary.get("data_root", ""), "spec-folder-popover-trigger"
        )
        audio_folder_display = _create_folder_display(
            summary.get("audio_folder") or "Not set",
            summary.get("audio_folders_list", []),
            summary.get("data_root", ""), "audio-folder-popover-trigger"
        )
        pred_file_display = _create_folder_display(
            summary.get("predictions_file") or "Not set",
            summary.get("predictions_files_list", []),
            summary.get("data_root", ""), "pred-file-popover-trigger"
        )

        ui_ready = no_update
        if (data or {}).get("load_timestamp"):
            ui_ready = {"timestamp": data.get("load_timestamp")}

        return (
            summary_block,
            grid,
            page_info,
            total_pages,
            spec_folder_display,
            audio_folder_display,
            pred_file_display,
            data_root,
            ui_ready,
        )

    @app.callback(
        Output("verify-class-filter-options", "data"),
        Output("verify-class-filter", "data"),
        Output("verify-class-filter-expanded", "data"),
        Input("verify-data-store", "data"),
        State("verify-class-filter", "data"),
        State("verify-class-filter-expanded", "data"),
        prevent_initial_call=False,
    )
    def sync_verify_class_filter_state(data, current_value, expanded_value):
        items = (data or {}).get("items", [])
        classes = _extract_verify_leaf_classes(items)
        option_values = _build_verify_filter_paths(classes)
        option_value_set = set(option_values)

        normalized_current = _normalize_verify_class_filter(current_value)
        # Default behavior should be all selected when no prior selection exists.
        if normalized_current is None or not normalized_current:
            selected_values = list(option_values)
        else:
            selected_values = [value for value in normalized_current if value in option_value_set]

        normalized_expanded = _ordered_unique_labels(expanded_value or [])
        if not option_values:
            return [], selected_values, []

        valid_paths = set()
        for path in option_values:
            parts = _split_hierarchy_label(path)
            for depth in range(1, len(parts) + 1):
                valid_paths.add(" > ".join(parts[:depth]))
        expanded_paths = [path for path in normalized_expanded if path in valid_paths]

        if not expanded_paths:
            roots = []
            seen = set()
            for path in option_values:
                parts = _split_hierarchy_label(path)
                if not parts:
                    continue
                root = parts[0]
                if root in seen:
                    continue
                roots.append(root)
                seen.add(root)
            expanded_paths = roots

        return option_values, selected_values, expanded_paths

    @app.callback(
        Output("verify-class-filter-tree", "children"),
        Output("verify-class-filter-toggle", "children"),
        Output("verify-class-filter-select-all", "value"),
        Input("verify-class-filter-options", "data"),
        Input("verify-class-filter", "data"),
        Input("verify-class-filter-expanded", "data"),
        prevent_initial_call=False,
    )
    def render_verify_class_filter_tree(option_values, selected_values, expanded_values):
        option_values = _ordered_unique_labels(option_values or [])
        if not option_values:
            return (
                html.Div("No classes available", className="text-muted small"),
                [
                    html.Span("No classes available", className="verify-class-filter-toggle-label"),
                    html.Span("▾", className="verify-class-filter-toggle-caret"),
                ],
                False,
            )

        normalized_selected = _normalize_verify_class_filter(selected_values)
        if normalized_selected is None:
            normalized_selected = list(option_values)
        else:
            normalized_selected = [value for value in normalized_selected if value in set(option_values)]

        tree_rows = _build_verify_filter_tree_rows(option_values, normalized_selected, expanded_values or [])
        if len(normalized_selected) == len(option_values):
            toggle_label = "All classes selected"
            select_all_value = True
        elif not normalized_selected:
            toggle_label = "No classes selected"
            select_all_value = False
        elif len(normalized_selected) == 1:
            toggle_label = normalized_selected[0]
            select_all_value = False
        else:
            toggle_label = f"{len(normalized_selected)} classes selected"
            select_all_value = False

        return (
            html.Div(tree_rows),
            [
                html.Span(toggle_label, className="verify-class-filter-toggle-label"),
                html.Span("▾", className="verify-class-filter-toggle-caret"),
            ],
            select_all_value,
        )

    @app.callback(
        Output("verify-class-filter-collapse", "is_open"),
        Output("verify-class-filter-toggle", "className"),
        Output("verify-class-filter-dismiss-overlay", "style"),
        Input("verify-class-filter-toggle", "n_clicks"),
        Input("verify-class-filter-dismiss-overlay", "n_clicks"),
        State("verify-class-filter-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_verify_class_filter_dropdown(toggle_clicks, dismiss_clicks, is_open):
        triggered = ctx.triggered_id
        if triggered not in {"verify-class-filter-toggle", "verify-class-filter-dismiss-overlay"}:
            raise PreventUpdate

        is_currently_open = bool(is_open)
        if triggered == "verify-class-filter-toggle":
            if not toggle_clicks:
                raise PreventUpdate
            next_open = not is_currently_open
        else:
            if not dismiss_clicks or not is_currently_open:
                raise PreventUpdate
            next_open = False

        base_class = "w-100 text-start verify-class-filter-toggle"
        overlay_style = {"display": "block"} if next_open else {"display": "none"}
        return (
            next_open,
            (f"{base_class} verify-class-filter-toggle--open" if next_open else base_class),
            overlay_style,
        )

    @app.callback(
        Output("verify-class-filter-expanded", "data", allow_duplicate=True),
        Input({"type": "verify-filter-expand", "path": ALL}, "n_clicks"),
        State("verify-class-filter-expanded", "data"),
        prevent_initial_call=True,
    )
    def toggle_verify_filter_expand(expand_clicks, expanded_paths):
        if not ctx.triggered:
            raise PreventUpdate
        if (ctx.triggered[0].get("value") or 0) <= 0:
            raise PreventUpdate

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        path = (triggered.get("path") or "").strip()
        if not path:
            raise PreventUpdate

        next_paths = set(_ordered_unique_labels(expanded_paths or []))
        if path in next_paths:
            next_paths.remove(path)
        else:
            next_paths.add(path)
        return sorted(next_paths, key=lambda text: text.lower())

    @app.callback(
        Output("verify-class-filter", "data", allow_duplicate=True),
        Input({"type": "verify-filter-checkbox", "path": ALL}, "value"),
        Input("verify-class-filter-select-all", "value"),
        State({"type": "verify-filter-checkbox", "path": ALL}, "id"),
        State("verify-class-filter-options", "data"),
        State("verify-class-filter", "data"),
        prevent_initial_call=True,
    )
    def update_verify_filter_selection(
        checkbox_values,
        select_all_checked,
        checkbox_ids,
        option_values,
        current_values,
    ):
        option_values = _ordered_unique_labels(option_values or [])
        if not option_values:
            raise PreventUpdate

        option_set = set(option_values)
        normalized_current = _normalize_verify_class_filter(current_values)
        if normalized_current is None:
            selected_values = list(option_values)
        else:
            selected_values = [value for value in normalized_current if value in option_set]

        triggered = ctx.triggered_id

        if triggered == "verify-class-filter-select-all":
            is_all_selected = len(selected_values) == len(option_values)
            if bool(select_all_checked):
                if is_all_selected:
                    raise PreventUpdate
                return option_values
            if is_all_selected:
                return []
            raise PreventUpdate

        if not (isinstance(triggered, dict) and triggered.get("type") == "verify-filter-checkbox"):
            raise PreventUpdate

        selected_from_checks = []
        for checkbox_value, checkbox_id in zip(checkbox_values or [], checkbox_ids or []):
            if not isinstance(checkbox_id, dict):
                continue
            path = (checkbox_id.get("path") or "").strip()
            if not path or path not in option_set:
                continue
            if bool(checkbox_value):
                selected_from_checks.append(path)
        selected_from_checks = _ordered_unique_labels(selected_from_checks)
        if selected_from_checks == selected_values:
            raise PreventUpdate
        return selected_from_checks

    @app.callback(
        Output("verify-thresholds-store", "data"),
        Input("verify-threshold-slider", "value"),
        State("verify-class-filter", "data"),
        State("verify-thresholds-store", "data"),
        prevent_initial_call=True,
    )
    def update_thresholds_store(slider_value, class_filter, thresholds):
        thresholds = thresholds or {"__global__": 0.5}
        class_filter = class_filter or "all"
        if slider_value is None:
            return thresholds

        value = float(slider_value)
        thresholds["__global__"] = value
        return thresholds

    @app.callback(
        Output("verify-threshold-slider", "value"),
        Input("verify-class-filter", "data"),
        State("verify-thresholds-store", "data"),
        prevent_initial_call=True,
    )
    def sync_threshold_slider(class_filter, thresholds):
        thresholds = thresholds or {"__global__": 0.5}
        class_filter = class_filter or "all"
        return float(thresholds.get("__global__", 0.5))

    @app.callback(
        Output("explore-summary", "children"),
        Output("explore-grid", "children"),
        Output("explore-page-info", "children"),
        Output("explore-page-input", "max"),
        Output("explore-ui-ready-store", "data"),
        Input("explore-data-store", "data"),
        Input("explore-current-page", "data"),
        Input("explore-colormap-toggle", "value"),
        Input("explore-yaxis-toggle", "value"),
        Input("config-store", "data"),
    )
    def render_explore(data, current_page, use_hydrophone_colormap, use_log_y_axis, cfg):
        data = data or {"items": [], "summary": {"total_items": 0}}
        summary = data.get("summary", {})
        items = data.get("items", [])

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Items: {summary.get('total_items', len(items))}", className="fw-semibold"),
        ])

        total_items = len(items)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = current_page or 0
        current_page = max(0, min(current_page, total_pages - 1))
        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = items[start_idx:end_idx]
        page_info = f"Page {current_page + 1} of {total_pages}"

        grid = _build_grid(page_items, "explore", colormap, y_axis_scale, items_per_page)
        ui_ready = no_update
        if (data or {}).get("load_timestamp"):
            ui_ready = {"timestamp": data.get("load_timestamp")}
        return summary_block, grid, page_info, total_pages, ui_ready

    @app.callback(
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def close_editor_on_tab_switch(_mode):
        return False, [], None

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Input("label-output-input", "value"),
        State("label-data-store", "data"),
        prevent_initial_call=True
    )
    def sync_label_output_path_to_store(path_value, label_data):
        """Sync manual edits to the labels output path back to the data store."""
        if not label_data or path_value is None:
            raise PreventUpdate
        
        # Avoid unnecessary updates if the value matches
        summary = label_data.get("summary", {})
        if summary.get("labels_file") == path_value:
            raise PreventUpdate
            
        # Update the store with the new path
        new_data = dict(label_data)
        new_data["summary"] = dict(summary)
        new_data["summary"]["labels_file"] = path_value
        return new_data

    @app.callback(
        Output("label-spec-folder-display", "children", allow_duplicate=True),
        Output("label-audio-folder-display", "children", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Input("mode-tabs", "data"),
        State("label-data-store", "data"),
        prevent_initial_call=True,
    )
    def reset_label_displays_on_tab_switch(mode, label_data):
        """Restore Label tab folder displays when switching to Label tab.

        When switching tabs, date/device selectors get cleared which can trigger
        update_dynamic_path_displays and reset folder paths. This callback
        restores correct values from the label data store.
        """
        if mode != "label":
            raise PreventUpdate

        if not label_data or not label_data.get("items"):
            # No label data loaded - show clean slate
            return "Not set", "Not set", ""

        # Restore folder displays from label data summary
        summary = label_data.get("summary", {})
        data_root = summary.get("data_root", "")
        spec_display = _create_folder_display(
            summary.get("spectrogram_folder") or "Not set",
            summary.get("spectrogram_folders_list", []),
            data_root, "label-spec-popover-tab"
        )
        audio_display = _create_folder_display(
            summary.get("audio_folder") or "Not set",
            summary.get("audio_folders_list", []),
            data_root, "label-audio-popover-tab"
        )
        labels_file = summary.get("labels_file") or ""
        return spec_display, audio_display, labels_file

    @app.callback(
        Output("label-editor-modal", "is_open"),
        Output("label-editor-body", "children"),
        Output("active-item-store", "data"),
        Output("label-editor-clicks", "data"),
        Input({"type": "edit-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-action-edit", "scope": ALL}, "n_clicks"),
        Input("label-editor-cancel", "n_clicks"),
        State("label-editor-clicks", "data"),
        State({"type": "edit-btn", "item_id": ALL}, "id"),
        State("current-filename", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("active-item-store", "data"),
        State("verify-thresholds-store", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def open_label_editor(n_clicks_list, modal_edit_clicks_list, cancel_clicks, click_store, edit_ids, modal_item_id, label_data, verify_data,
                          explore_data, active_item_id, thresholds, mode, profile):
        # Select the appropriate data store based on mode
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        triggered = ctx.triggered_id
        if triggered == "label-editor-cancel":
            return False, no_update, None, click_store or {}
        if mode == "explore":
            return False, no_update, None, click_store or {}
        _require_complete_profile(profile, "open_label_editor")

        click_store = click_store or {}
        updated_store = dict(click_store)
        chosen_item_id = None

        if isinstance(triggered, dict) and triggered.get("type") == "modal-action-edit":
            if not modal_edit_clicks_list or not any(modal_edit_clicks_list) or not modal_item_id:
                return no_update, no_update, no_update, click_store
            chosen_item_id = modal_item_id
            updated_store[chosen_item_id] = (updated_store.get(chosen_item_id, 0) or 0) + 1
        else:
            if not n_clicks_list or not edit_ids:
                return no_update, no_update, no_update, click_store

            for i, id_dict in enumerate(edit_ids):
                item_id = id_dict.get("item_id")
                if not item_id:
                    continue
                current_clicks = n_clicks_list[i] or 0
                previous_clicks = click_store.get(item_id, 0)
                updated_store[item_id] = current_clicks
                if current_clicks > previous_clicks:
                    chosen_item_id = item_id

        if not chosen_item_id:
            return no_update, no_update, no_update, updated_store

        items = (data or {}).get("items", [])
        selected_labels = []
        existing_note = ""
        for item in items:
            if item.get("item_id") == chosen_item_id:
                annotations = item.get("annotations") or {}
                predicted = item.get("predictions", {}) if isinstance(item.get("predictions"), dict) else {}
                selected_labels = annotations.get("labels") or predicted.get("labels") or []
                existing_note = annotations.get("notes", "") if isinstance(annotations, dict) else ""
                if not selected_labels and mode == "verify":
                    selected_labels = _filter_predictions(predicted, thresholds or {"__global__": 0.5})
                break

        selector = create_hierarchical_selector(chosen_item_id, selected_labels)
        note_section = html.Details(
            [
                html.Summary("Note", style={"cursor": "pointer", "fontWeight": "600"}),
                dcc.Textarea(
                    id={"type": "note-editor-text", "filename": chosen_item_id},
                    value=existing_note,
                    placeholder="Add a note for this spectrogram...",
                    style={"width": "100%", "minHeight": "140px", "marginTop": "8px"},
                ),
            ],
            open=bool(existing_note),
            style={"marginTop": "12px"},
        )
        return True, html.Div([selector, note_section]), chosen_item_id, updated_store

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Input("label-editor-save", "n_clicks"),
        State("active-item-store", "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "data"),
        State({"type": "selected-labels-store", "filename": ALL}, "id"),
        State({"type": "note-editor-text", "filename": ALL}, "value"),
        State({"type": "note-editor-text", "filename": ALL}, "id"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        State("config-store", "data"),
        State("label-output-input", "value"),
        State("modal-bbox-store", "data"),
        State("current-filename", "data"),
        prevent_initial_call=True,
    )
    def save_label_editor(save_clicks, active_item_id, labels_list, labels_ids,
                          note_values, note_ids, label_data, verify_data, explore_data,
                          profile, mode, cfg, label_output_path, modal_bbox_store, current_modal_item_id):
        if not save_clicks or not active_item_id:
            raise PreventUpdate
        if mode == "explore":
            return no_update, no_update, no_update, False, [], no_update, no_update
        _require_complete_profile(profile, "save_label_editor")

        # Select the appropriate data store based on mode
        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}

        selected_labels = []
        for i, label_id in enumerate(labels_ids or []):
            if label_id.get("filename") == active_item_id:
                selected_labels = labels_list[i] or []
                break

        note_text = None
        for i, note_id in enumerate(note_ids or []):
            if note_id.get("filename") == active_item_id:
                note_text = note_values[i] if note_values else None
                break

        label_extents = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == active_item_id:
            label_extents = _extract_label_extent_map_from_boxes(modal_bbox_store.get("boxes") or [])

        if label_extents:
            merged = list(selected_labels or [])
            existing = set(merged)
            for label in label_extents.keys():
                if label not in existing:
                    merged.append(label)
                    existing.add(label)
            selected_labels = merged

        profile_name = _profile_actor(profile)
        updated = _update_item_labels(
            data or {},
            active_item_id,
            selected_labels,
            mode,
            user_name=profile_name,
            label_extents=label_extents or None,
        )
        if note_text is not None:
            updated = _update_item_notes(updated or {}, active_item_id, note_text, user_name=profile_name)

        if mode == "verify":
            # Verify mode persists only on Confirm/Re-verify.
            pass
        elif mode == "label":
            cfg = cfg or {}
            labels_file = (
                label_output_path
                or (updated.get("summary", {}) if isinstance(updated.get("summary"), dict) else {}).get("labels_file")
                or (cfg.get("label", {}) if isinstance(cfg.get("label"), dict) else {}).get("output_file")
            )
            save_label_mode(
                labels_file,
                active_item_id,
                selected_labels,
                annotated_by=profile_name,
                notes=(note_text or ""),
                label_extents=label_extents or None,
            )
            # "Save Labels" in label mode is a full save, so clear pending-save state.
            updated = _update_item_labels(
                updated or {},
                active_item_id,
                selected_labels,
                mode="label",
                user_name=profile_name,
                is_reverification=True,
                label_extents=label_extents or None,
            )

        dirty_update = no_update
        snapshot_update = no_update
        if active_item_id and active_item_id == current_modal_item_id:
            updated_item = next(
                (item for item in (updated or {}).get("items", []) if isinstance(item, dict) and item.get("item_id") == active_item_id),
                None,
            )
            if isinstance(updated_item, dict):
                if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == active_item_id:
                    snapshot_boxes = modal_bbox_store.get("boxes") or []
                else:
                    snapshot_boxes = _build_modal_boxes_from_item(updated_item)
                if mode == "verify":
                    dirty_update = {"dirty": True, "item_id": active_item_id}
                else:
                    dirty_update = {"dirty": False, "item_id": active_item_id}
                    snapshot_update = _modal_snapshot_payload("label", active_item_id, updated_item, snapshot_boxes)

        # Return updated data to the appropriate store, no_update for others
        if mode == "label":
            return updated, no_update, no_update, False, [], dirty_update, snapshot_update
        elif mode == "verify":
            return no_update, updated, no_update, False, [], dirty_update, snapshot_update
        else:
            return no_update, no_update, updated, False, [], dirty_update, snapshot_update

    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Input({"type": "confirm-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-action-confirm", "scope": ALL}, "n_clicks"),
        State("current-filename", "data"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "data"),
        State({"type": "verify-actions-store", "filename": ALL}, "id"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_verification(
        n_clicks_list,
        modal_confirm_clicks_list,
        modal_item_id,
        data,
        thresholds,
        actions_list,
        actions_ids,
        modal_bbox_store,
        profile,
    ):
        _require_complete_profile(profile, "confirm_verification")

        triggered = ctx.triggered_id
        if isinstance(triggered, dict) and triggered.get("type") == "modal-action-confirm":
            if not modal_confirm_clicks_list or not any(modal_confirm_clicks_list) or not modal_item_id:
                raise PreventUpdate
            item_id = modal_item_id
        else:
            if not n_clicks_list or not any(n_clicks_list):
                raise PreventUpdate
            if not isinstance(triggered, dict) or "item_id" not in triggered:
                raise PreventUpdate
            item_id = triggered["item_id"]

        items = (data or {}).get("items", [])
        labels_to_confirm = []
        predictions = {}
        predictions_path = None
        annotations = {}
        thresholds = thresholds or {"__global__": 0.5}
        threshold_used = float(thresholds.get("__global__", 0.5))
        for item in items:
            if item.get("item_id") == item_id:
                annotations = item.get("annotations") or {}
                predictions = item.get("predictions") or {}
                predictions_path = (item.get("metadata") or {}).get("predictions_path")
                _, _, active_labels = _get_modal_label_sets(item, "verify", thresholds)
                labels_to_confirm = list(active_labels or [])
                break

        box_extent_map = {}
        box_extent_lists = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
            modal_boxes = modal_bbox_store.get("boxes") or []
            box_extent_map = _extract_label_extent_map_from_boxes(modal_boxes)
            box_extent_lists = _extract_label_extent_list_map_from_boxes(modal_boxes)

        if box_extent_lists:
            ordered = list(labels_to_confirm or [])
            seen = set(ordered)
            for label in box_extent_lists.keys():
                if label not in seen:
                    ordered.append(label)
                    seen.add(label)
            labels_to_confirm = ordered

        if not predictions_path:
            summary_pred = (data or {}).get("summary", {}).get("predictions_file")
            if isinstance(summary_pred, str) and summary_pred.endswith(".json"):
                predictions_path = summary_pred

        predicted_labels = _filter_predictions(predictions, thresholds)
        predicted_set = set(predicted_labels)
        labels_set = set(labels_to_confirm)

        model_scores = {}
        model_extent_map = {}
        model_outputs = predictions.get("model_outputs")
        if model_outputs and isinstance(model_outputs, list):
            for out in model_outputs:
                label = out.get("class_hierarchy")
                score = out.get("score")
                if label and isinstance(score, (int, float)):
                    model_scores[label] = score
                if label:
                    cleaned_extent = _clean_annotation_extent(out.get("annotation_extent"))
                    if cleaned_extent:
                        model_extent_map[label] = cleaned_extent
        else:
            probs = predictions.get("confidence") or {}
            for label, score in probs.items():
                if isinstance(score, (int, float)):
                    model_scores[label] = score

        item_actions = []
        for i, action_id in enumerate(actions_ids or []):
            if action_id.get("filename") == item_id:
                item_actions = (actions_list or [])[i] or []
                break
        last_add_threshold = {}
        last_remove_threshold = {}
        for action in item_actions:
            label = action.get("label")
            threshold_value = action.get("threshold_used")
            if not label or threshold_value is None:
                continue
            if action.get("action") == "add":
                last_add_threshold[label] = threshold_value
            elif action.get("action") == "remove":
                last_remove_threshold[label] = threshold_value

        rejected_labels = set()
        for label in predicted_labels:
            if label not in labels_set:
                rejected_labels.add(label)
        for label, removed_threshold in last_remove_threshold.items():
            score = model_scores.get(label)
            if score is not None and score >= float(removed_threshold):
                rejected_labels.add(label)

        label_decisions = []
        for label in labels_to_confirm:
            if label in predicted_set:
                decision = "accepted"
            else:
                decision = "added"
            threshold_for_label = float(last_add_threshold.get(label, threshold_used))
            entry = {
                "label": label,
                "decision": decision,
                "threshold_used": threshold_for_label,
            }
            label_extents = box_extent_lists.get(label) or []
            extent = (label_extents[0] if label_extents else None) or model_extent_map.get(label)
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)
            for extra_extent in label_extents[1:]:
                if not isinstance(extra_extent, dict):
                    continue
                label_decisions.append(
                    {
                        "label": label,
                        "decision": decision,
                        "threshold_used": threshold_for_label,
                        "annotation_extent": extra_extent,
                    }
                )
        for label in sorted(rejected_labels - labels_set):
            entry = {
                "label": label,
                "decision": "rejected",
                "threshold_used": float(last_remove_threshold.get(label, threshold_used)),
            }
            label_extents = box_extent_lists.get(label) or []
            extent = model_extent_map.get(label) or (label_extents[0] if label_extents else box_extent_map.get(label))
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)

        profile_name = _profile_actor(profile)
        note_text = annotations.get("notes", "") if isinstance(annotations, dict) else ""
        verification = {
            "verified_at": datetime.now().isoformat(),
            "verified_by": profile_name or "anonymous",
            "label_decisions": label_decisions,
            "verification_status": "verified",
            "notes": note_text,
        }

        updated = _update_item_labels(
            data or {},
            item_id,
            labels_to_confirm,
            mode="verify",
            user_name=profile_name,
            is_reverification=True,
            label_extents=box_extent_map or None,
        )
        for item in (updated or {}).get("items", []):
            if not isinstance(item, dict) or item.get("item_id") != item_id:
                continue
            annotations_obj = item.get("annotations") or {}
            annotations_obj["rejected_labels"] = sorted(rejected_labels)
            item["annotations"] = annotations_obj
            break

        stored_verification = save_verify_predictions(predictions_path, item_id, verification)
        if stored_verification:
            for item in (updated or {}).get("items", []):
                if item.get("item_id") == item_id:
                    verifications = item.get("verifications")
                    if not isinstance(verifications, list):
                        verifications = []
                    verifications.append(stored_verification)
                    item["verifications"] = verifications
                    break
        dirty_update = no_update
        snapshot_update = no_update
        if modal_item_id and modal_item_id == item_id:
            dirty_update = {"dirty": False, "item_id": item_id}
            updated_item = next(
                (item for item in (updated or {}).get("items", []) if isinstance(item, dict) and item.get("item_id") == item_id),
                None,
            )
            if isinstance(updated_item, dict):
                if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
                    snapshot_boxes = modal_bbox_store.get("boxes") or []
                else:
                    snapshot_boxes = _build_modal_boxes_from_item(updated_item)
                snapshot_update = _modal_snapshot_payload("verify", item_id, updated_item, snapshot_boxes)

        return updated, dirty_update, snapshot_update

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input({"type": "label-label-delete", "target": ALL}, "n_clicks_timestamp"),
        State("label-data-store", "data"),
        State("current-filename", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def quick_delete_label_mode(delete_timestamps, label_data, modal_item_id, modal_bbox_store, profile):
        if not ctx.triggered:
            raise PreventUpdate
        if (ctx.triggered[0].get("value") or 0) <= 0:
            raise PreventUpdate
        _require_complete_profile(profile, "quick_delete_label_mode")

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate

        item_key, item_id, label = _parse_verify_target((triggered.get("target") or "").strip())
        _ = item_key  # label-mode delete currently resolves by item_id.
        if not item_id:
            item_id = (triggered.get("item_id") or "").strip()
        if not label:
            label = (triggered.get("label") or "").strip()
        if not item_id or not label:
            raise PreventUpdate

        data = deepcopy(label_data or {})
        items = data.get("items") or []
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            raise PreventUpdate

        _, _, active_labels = _get_modal_label_sets(active_item, "label", {"__global__": 0.5})
        updated_labels = [
            existing
            for existing in _ordered_unique_labels(active_labels)
            if existing != label
        ]
        if len(updated_labels) == len(_ordered_unique_labels(active_labels)):
            raise PreventUpdate

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        label_extents = {}
        raw_label_extents = annotations_obj.get("label_extents") if isinstance(annotations_obj, dict) else None
        if isinstance(raw_label_extents, dict):
            for extent_label, extent in raw_label_extents.items():
                if not isinstance(extent_label, str):
                    continue
                normalized = extent_label.strip()
                if not normalized or normalized == label:
                    continue
                cleaned_extent = _clean_annotation_extent(extent)
                if cleaned_extent:
                    label_extents[normalized] = cleaned_extent

        next_bbox_store = no_update
        unsaved_update = no_update
        if item_id == (modal_item_id or ""):
            unsaved_update = {"dirty": True, "item_id": item_id}
            if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
                filtered_boxes = [
                    box
                    for box in (modal_bbox_store.get("boxes") or [])
                    if isinstance(box, dict) and (box.get("label") or "").strip() != label
                ]
                next_bbox_store = {"item_id": item_id, "boxes": filtered_boxes}
                label_extents = _extract_label_extent_map_from_boxes(filtered_boxes)

        profile_name = _profile_actor(profile)
        updated_data = _update_item_labels(
            data,
            item_id,
            updated_labels,
            mode="label",
            user_name=profile_name,
            label_extents=label_extents or None,
        )
        return updated_data, next_bbox_store, unsaved_update

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-snapshot-store", "data", allow_duplicate=True),
        Input({"type": "label-save-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-label-save", "scope": ALL}, "n_clicks"),
        State("current-filename", "data"),
        State("label-data-store", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("config-store", "data"),
        State("label-output-input", "value"),
        prevent_initial_call=True,
    )
    def save_label_changes(
        card_save_clicks,
        modal_save_clicks,
        modal_item_id,
        label_data,
        modal_bbox_store,
        profile,
        cfg,
        label_output_path,
    ):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate

        if triggered.get("type") == "modal-label-save":
            if not modal_save_clicks or not any(modal_save_clicks) or not modal_item_id:
                raise PreventUpdate
            item_id = modal_item_id
        elif triggered.get("type") == "label-save-btn":
            if not card_save_clicks or not any(card_save_clicks):
                raise PreventUpdate
            item_id = (triggered.get("item_id") or "").strip()
        else:
            raise PreventUpdate

        if not item_id:
            raise PreventUpdate
        _require_complete_profile(profile, "save_label_changes")

        data = deepcopy(label_data or {})
        items = data.get("items") or []
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == item_id),
            None,
        )
        if not isinstance(active_item, dict):
            raise PreventUpdate

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        if not _has_pending_label_edits(annotations_obj):
            raise PreventUpdate

        labels_to_save = _ordered_unique_labels(annotations_obj.get("labels") or [])
        note_text = annotations_obj.get("notes", "") if isinstance(annotations_obj.get("notes"), str) else ""

        label_extents = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
            label_extents = _extract_label_extent_map_from_boxes(modal_bbox_store.get("boxes") or [])
        else:
            raw_label_extents = annotations_obj.get("label_extents")
            if isinstance(raw_label_extents, dict):
                for extent_label, extent in raw_label_extents.items():
                    if not isinstance(extent_label, str):
                        continue
                    normalized = extent_label.strip()
                    if not normalized:
                        continue
                    cleaned_extent = _clean_annotation_extent(extent)
                    if cleaned_extent:
                        label_extents[normalized] = cleaned_extent

        if label_extents:
            merged = list(labels_to_save)
            seen = set(merged)
            for label in label_extents.keys():
                if label not in seen:
                    merged.append(label)
                    seen.add(label)
            labels_to_save = merged

        cfg = cfg or {}
        labels_file = (
            label_output_path
            or (data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}).get("labels_file")
            or (cfg.get("label", {}) if isinstance(cfg.get("label"), dict) else {}).get("output_file")
        )
        profile_name = _profile_actor(profile)

        save_label_mode(
            labels_file,
            item_id,
            labels_to_save,
            annotated_by=profile_name,
            notes=note_text,
            label_extents=label_extents or None,
        )

        updated = _update_item_labels(
            data,
            item_id,
            labels_to_save,
            mode="label",
            user_name=profile_name,
            is_reverification=True,
            label_extents=label_extents or None,
        )

        dirty_update = no_update
        snapshot_update = no_update
        if item_id == (modal_item_id or ""):
            dirty_update = {"dirty": False, "item_id": item_id}
            updated_item = next(
                (
                    item
                    for item in (updated or {}).get("items", [])
                    if isinstance(item, dict) and item.get("item_id") == item_id
                ),
                None,
            )
            if isinstance(updated_item, dict):
                if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
                    snapshot_boxes = modal_bbox_store.get("boxes") or []
                else:
                    snapshot_boxes = _build_modal_boxes_from_item(updated_item)
                snapshot_update = _modal_snapshot_payload("label", item_id, updated_item, snapshot_boxes)

        return updated, dirty_update, snapshot_update

    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("verify-badge-event-store", "data", allow_duplicate=True),
        Input({"type": "verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-accept", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "label": ALL}, "n_clicks_timestamp"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("current-filename", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("verify-badge-event-store", "data"),
        prevent_initial_call=True,
    )
    def quick_update_verify_labels(
        card_accept_ts,
        card_reject_ts,
        card_delete_ts,
        card_accept_ts_legacy,
        card_reject_ts_legacy,
        card_delete_ts_legacy,
        modal_accept_ts,
        modal_reject_ts,
        modal_delete_ts,
        modal_accept_ts_legacy,
        modal_reject_ts_legacy,
        modal_delete_ts_legacy,
        verify_data,
        thresholds,
        modal_item_id,
        modal_bbox_store,
        profile,
        badge_event_store,
    ):
        _require_complete_profile(profile, "quick_update_verify_labels")
        _verify_badge_debug(
            "start",
            triggered_id=ctx.triggered_id,
            triggered=ctx.triggered,
            modal_item_id=modal_item_id,
            verify_items=len((verify_data or {}).get("items") or []),
            modal_bbox_item_id=(modal_bbox_store or {}).get("item_id") if isinstance(modal_bbox_store, dict) else None,
            timestamp_summary={
                "card_accept_target": max((v or -1) for v in (card_accept_ts or [None])) if card_accept_ts else -1,
                "card_reject_target": max((v or -1) for v in (card_reject_ts or [None])) if card_reject_ts else -1,
                "card_delete_target": max((v or -1) for v in (card_delete_ts or [None])) if card_delete_ts else -1,
                "card_accept_legacy": max((v or -1) for v in (card_accept_ts_legacy or [None])) if card_accept_ts_legacy else -1,
                "card_reject_legacy": max((v or -1) for v in (card_reject_ts_legacy or [None])) if card_reject_ts_legacy else -1,
                "card_delete_legacy": max((v or -1) for v in (card_delete_ts_legacy or [None])) if card_delete_ts_legacy else -1,
                "modal_accept_target": max((v or -1) for v in (modal_accept_ts or [None])) if modal_accept_ts else -1,
                "modal_reject_target": max((v or -1) for v in (modal_reject_ts or [None])) if modal_reject_ts else -1,
                "modal_delete_target": max((v or -1) for v in (modal_delete_ts or [None])) if modal_delete_ts else -1,
                "modal_accept_legacy": max((v or -1) for v in (modal_accept_ts_legacy or [None])) if modal_accept_ts_legacy else -1,
                "modal_reject_legacy": max((v or -1) for v in (modal_reject_ts_legacy or [None])) if modal_reject_ts_legacy else -1,
                "modal_delete_legacy": max((v or -1) for v in (modal_delete_ts_legacy or [None])) if modal_delete_ts_legacy else -1,
            },
            last_event_store=badge_event_store,
        )
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            _verify_badge_debug("prevent_missing_triggered_id", triggered_id=triggered)
            raise PreventUpdate

        action_type = (triggered.get("type") or "").strip()
        if action_type not in {
            "verify-label-accept",
            "verify-label-reject",
            "verify-label-delete",
            "modal-verify-label-accept",
            "modal-verify-label-reject",
            "modal-verify-label-delete",
        }:
            _verify_badge_debug("prevent_unknown_action_type", action_type=action_type, triggered=triggered)
            raise PreventUpdate

        input_entries = []
        for group in (ctx.inputs_list or []):
            if isinstance(group, list):
                input_entries.extend(group)
            elif isinstance(group, dict):
                input_entries.append(group)

        triggered_key_json = json.dumps(triggered, sort_keys=True, ensure_ascii=True)
        matching_timestamps = []
        for entry in input_entries:
            if not isinstance(entry, dict):
                continue
            event_id = entry.get("id")
            if not isinstance(event_id, dict):
                continue
            if json.dumps(event_id, sort_keys=True, ensure_ascii=True) != triggered_key_json:
                continue
            ts_val = entry.get("value")
            if isinstance(ts_val, (int, float)) and ts_val > 0:
                matching_timestamps.append(int(ts_val))

        if not matching_timestamps:
            _verify_badge_debug(
                "prevent_no_timestamp_for_trigger",
                triggered=triggered,
                inputs_count=len(input_entries),
            )
            raise PreventUpdate

        triggered_value = max(matching_timestamps)
        selected_key = f"{triggered_value}|{triggered_key_json}"
        last_key = (badge_event_store or {}).get("last_key") if isinstance(badge_event_store, dict) else ""
        if selected_key == last_key:
            _verify_badge_debug("prevent_duplicate_event", selected_key=selected_key)
            raise PreventUpdate

        label = ""
        item_id = ""
        item_key = ""
        target = (triggered.get("target") or "").strip()
        _verify_badge_debug(
            "resolved_trigger_payload",
            action_type=action_type,
            target=target,
            triggered=triggered,
            triggered_value=triggered_value,
        )
        if action_type in {"verify-label-accept", "verify-label-reject", "verify-label-delete"}:
            parsed_key, parsed_item_id, parsed_label = _parse_verify_target(target)
            item_key = parsed_key
            item_id = parsed_item_id or (triggered.get("item_id") or "").strip()
            label = parsed_label or (triggered.get("label") or target).strip()
        elif action_type in {"modal-verify-label-accept", "modal-verify-label-reject", "modal-verify-label-delete"}:
            item_id = (modal_item_id or "").strip()
            label = (triggered.get("label") or target).strip()
        else:
            _verify_badge_debug("prevent_unknown_action_type", action_type=action_type)
            raise PreventUpdate

        if not item_id:
            _verify_badge_debug("prevent_missing_item_id", action_type=action_type, target=target, triggered=triggered)
            raise PreventUpdate
        if not label:
            _verify_badge_debug("prevent_missing_label", action_type=action_type, target=target, triggered=triggered)
            raise PreventUpdate

        if action_type.endswith("accept"):
            action = "accept"
        elif action_type.endswith("reject"):
            action = "reject"
        else:
            action = "delete"
        _verify_badge_debug("resolved_action", action=action, item_id=item_id, label=label, modal_item_id=modal_item_id)
        thresholds = thresholds or {"__global__": 0.5}
        data = deepcopy(verify_data or {})
        items = data.get("items") or []
        active_item = None
        active_item_index = -1
        if item_key:
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                if _item_action_key(item) == item_key:
                    active_item = item
                    active_item_index = idx
                    break
        if active_item is None:
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                if item.get("item_id") == item_id:
                    active_item = item
                    active_item_index = idx
                    break
        if not isinstance(active_item, dict):
            _verify_badge_debug(
                "prevent_item_not_found",
                item_id=item_id,
                item_key=item_key,
                available_ids=[i.get("item_id") for i in items if isinstance(i, dict)][:40],
            )
            raise PreventUpdate
        item_id = (active_item.get("item_id") or item_id).strip()
        if not item_id:
            _verify_badge_debug("prevent_active_item_missing_id", item_key=item_key)
            raise PreventUpdate

        predicted_set = set(_filter_predictions(active_item.get("predictions") or {}, thresholds))
        _, _, active_labels = _get_modal_label_sets(active_item, "verify", thresholds)
        updated_labels = _ordered_unique_labels(active_labels)
        rejected_set = set(_get_item_rejected_labels(active_item))
        _verify_badge_debug(
            "before_update",
            item_id=item_id,
            label=label,
            action=action,
            predicted_labels=sorted(predicted_set),
            active_labels=updated_labels,
            rejected_labels=sorted(rejected_set),
        )
        if action == "accept":
            if label not in updated_labels:
                updated_labels.append(label)
            rejected_set.discard(label)
        elif action == "reject":
            updated_labels = [existing for existing in updated_labels if existing != label]
            if label in predicted_set:
                rejected_set.add(label)
            else:
                rejected_set.discard(label)
        else:
            updated_labels = [existing for existing in updated_labels if existing != label]
            rejected_set.discard(label)

        annotations_obj = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        label_extents = {}
        raw_label_extents = annotations_obj.get("label_extents") if isinstance(annotations_obj, dict) else None
        if isinstance(raw_label_extents, dict):
            for extent_label, extent in raw_label_extents.items():
                if not isinstance(extent_label, str):
                    continue
                normalized_label = extent_label.strip()
                if not normalized_label:
                    continue
                cleaned_extent = _clean_annotation_extent(extent)
                if cleaned_extent:
                    label_extents[normalized_label] = cleaned_extent

        next_bbox_store = no_update
        is_modal_target = item_id == (modal_item_id or "")
        if is_modal_target:
            if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
                boxes = deepcopy(modal_bbox_store.get("boxes") or [])
            else:
                boxes = _build_modal_boxes_from_item(active_item)
            if action in {"reject", "delete"}:
                boxes = [
                    box
                    for box in boxes
                    if not (isinstance(box, dict) and (box.get("label") or "").strip() == label)
                ]
            next_bbox_store = {"item_id": item_id, "boxes": boxes}
            label_extents = _extract_label_extent_map_from_boxes(boxes)
        elif action in {"reject", "delete"}:
            label_extents.pop(label, None)

        profile_name = _profile_actor(profile)
        annotations_update = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {
            "labels": [],
            "annotated_by": None,
            "annotated_at": None,
            "verified": False,
            "notes": "",
        }
        annotations_update["labels"] = updated_labels
        annotations_update["label_extents"] = label_extents
        annotations_update["rejected_labels"] = sorted(rejected_set)
        annotations_update["annotated_at"] = datetime.now().isoformat()
        annotations_update["has_manual_review"] = True
        if annotations_update.get("verified"):
            annotations_update["needs_reverify"] = True
        annotations_update["pending_save"] = True
        if profile_name:
            annotations_update["annotated_by"] = profile_name
        active_item["annotations"] = annotations_update
        if 0 <= active_item_index < len(items):
            items[active_item_index] = active_item

        summary_obj = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        summary_obj["annotated"] = sum(
            1
            for entry in items
            if isinstance(entry, dict) and ((entry.get("annotations") or {}).get("labels") or [])
        )
        summary_obj["verified"] = sum(
            1
            for entry in items
            if isinstance(entry, dict) and bool((entry.get("annotations") or {}).get("verified"))
        )
        data["summary"] = summary_obj
        updated_data = data

        unsaved_update = {"dirty": True, "item_id": item_id} if item_id == (modal_item_id or "") else no_update
        _verify_badge_debug(
            "return_update",
            item_id=item_id,
            item_key=item_key,
            label=label,
            action=action,
            labels_after=updated_labels,
            rejected_after=sorted(rejected_set),
            next_bbox_store_item=(next_bbox_store or {}).get("item_id") if isinstance(next_bbox_store, dict) else None,
            unsaved_update=unsaved_update,
            event_key=selected_key,
        )
        return updated_data, next_bbox_store, unsaved_update, {"last_key": selected_key}

    @app.callback(
        Output("user-profile-store", "data", allow_duplicate=True),
        Output("profile-reset-applied-store", "data"),
        Input("mode-tabs", "data"),
        State("profile-reset-applied-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def maybe_reset_profile_on_start(mode, reset_applied, current_profile):
        _ = mode
        if not _RESET_PROFILE_ON_START:
            raise PreventUpdate
        if reset_applied:
            raise PreventUpdate
        profile = current_profile if isinstance(current_profile, dict) else {}
        if not profile.get("name") and not profile.get("email"):
            return no_update, True
        logger.warning("[PROFILE_RESET] reset_profile_on_start_applied=true")
        return {"name": "", "email": ""}, True

    @app.callback(
        Output("profile-modal", "is_open", allow_duplicate=True),
        Output("profile-name", "value", allow_duplicate=True),
        Output("profile-email", "value", allow_duplicate=True),
        Output("profile-name", "invalid", allow_duplicate=True),
        Output("profile-email", "invalid", allow_duplicate=True),
        Output("profile-required-message", "children", allow_duplicate=True),
        Input({"type": "edit-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-action-edit", "scope": ALL}, "n_clicks"),
        Input("label-editor-save", "n_clicks"),
        Input({"type": "confirm-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-action-confirm", "scope": ALL}, "n_clicks"),
        Input({"type": "label-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "label-save-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-accept", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-label-add-box", "label": ALL}, "n_clicks"),
        Input({"type": "modal-label-delete-confirm", "label": ALL}, "submit_n_clicks"),
        Input("unsaved-save-btn", "n_clicks"),
        Input("modal-image-graph", "relayoutData"),
        Input("modal-image-graph", "clickData"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def prompt_profile_for_blocked_actions(
        edit_clicks,
        modal_edit_clicks,
        label_editor_save_clicks,
        confirm_clicks,
        modal_confirm_clicks,
        label_delete_clicks,
        label_save_clicks,
        verify_accept_clicks,
        verify_reject_clicks,
        verify_delete_clicks,
        verify_accept_clicks_legacy,
        verify_reject_clicks_legacy,
        verify_delete_clicks_legacy,
        modal_verify_accept_clicks,
        modal_verify_reject_clicks,
        modal_verify_delete_clicks,
        modal_verify_accept_clicks_legacy,
        modal_verify_reject_clicks_legacy,
        modal_verify_delete_clicks_legacy,
        modal_add_box_clicks,
        modal_delete_label_clicks,
        unsaved_save_clicks,
        modal_graph_relayout,
        modal_graph_click,
        profile,
        mode,
    ):
        _ = (
            edit_clicks,
            modal_edit_clicks,
            label_editor_save_clicks,
            confirm_clicks,
            modal_confirm_clicks,
            label_delete_clicks,
            label_save_clicks,
            verify_accept_clicks,
            verify_reject_clicks,
            verify_delete_clicks,
            verify_accept_clicks_legacy,
            verify_reject_clicks_legacy,
            verify_delete_clicks_legacy,
            modal_verify_accept_clicks,
            modal_verify_reject_clicks,
            modal_verify_delete_clicks,
            modal_verify_accept_clicks_legacy,
            modal_verify_reject_clicks_legacy,
            modal_verify_delete_clicks_legacy,
            modal_add_box_clicks,
            modal_delete_label_clicks,
            unsaved_save_clicks,
            modal_graph_relayout,
            modal_graph_click,
        )
        if not ctx.triggered:
            raise PreventUpdate
        if _is_profile_complete(profile):
            raise PreventUpdate
        if (mode or "label") == "explore":
            raise PreventUpdate

        prop_id = (ctx.triggered[0] or {}).get("prop_id", "")
        if prop_id.endswith(".relayoutData"):
            relayout = modal_graph_relayout if isinstance(modal_graph_relayout, dict) else {}
            keys = set(relayout.keys())
            has_shape_edit = bool(
                "shapes" in relayout
                or any(str(key).startswith("shapes[") for key in keys)
            )
            if not has_shape_edit:
                raise PreventUpdate
        elif prop_id.endswith(".clickData"):
            click_data = modal_graph_click if isinstance(modal_graph_click, dict) else {}
            points = click_data.get("points")
            if not (isinstance(points, list) and points):
                raise PreventUpdate

        name, email = _profile_name_email(profile)
        return (
            True,
            name,
            email,
            not bool(name),
            not _is_valid_email(email),
            _PROFILE_REQUIRED_MESSAGE,
        )

    @app.callback(
        Output("profile-modal", "is_open"),
        Output("profile-name", "value"),
        Output("profile-email", "value"),
        Output("profile-name", "invalid"),
        Output("profile-email", "invalid"),
        Output("profile-required-message", "children"),
        Input("profile-btn", "n_clicks"),
        Input("profile-cancel", "n_clicks"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_profile_modal(open_clicks, cancel_clicks, profile):
        triggered = ctx.triggered_id
        if triggered == "profile-btn":
            profile = profile or {}
            name, email = _profile_name_email(profile)
            return True, name, email, False, False, _PROFILE_REQUIRED_MESSAGE
        if triggered == "profile-cancel":
            return False, no_update, no_update, False, False, _PROFILE_REQUIRED_MESSAGE
        raise PreventUpdate

    @app.callback(
        Output("user-profile-store", "data"),
        Output("profile-modal", "is_open", allow_duplicate=True),
        Output("profile-name", "invalid", allow_duplicate=True),
        Output("profile-email", "invalid", allow_duplicate=True),
        Output("profile-required-message", "children", allow_duplicate=True),
        Input("profile-save", "n_clicks"),
        State("profile-name", "value"),
        State("profile-email", "value"),
        prevent_initial_call=True,
    )
    def save_profile(n_clicks, name, email):
        if not n_clicks:
            raise PreventUpdate
        normalized_name = str(name or "").strip()
        normalized_email = str(email or "").strip()
        name_invalid = not bool(normalized_name)
        email_invalid = not _is_valid_email(normalized_email)
        if name_invalid or email_invalid:
            return (
                no_update,
                True,
                name_invalid,
                email_invalid,
                _PROFILE_REQUIRED_MESSAGE,
            )
        return (
            {"name": normalized_name, "email": normalized_email},
            False,
            False,
            False,
            _PROFILE_REQUIRED_MESSAGE,
        )

    @app.callback(
        Output("profile-name-display", "children"),
        Output("profile-email-display", "children"),
        Input("user-profile-store", "data"),
        prevent_initial_call=False,
    )
    def update_profile_display(profile):
        profile = profile or {}
        name = profile.get("name") or "Anonymous"
        email = profile.get("email") or "email not set"
        return name, email

    @app.callback(
        Output("profile-required-banner", "children"),
        Output("profile-required-banner", "style"),
        Output("profile-btn", "className"),
        Input("user-profile-store", "data"),
        Input("mode-tabs", "data"),
        prevent_initial_call=False,
    )
    def render_profile_requirement_banner(profile, mode):
        base_profile_class = "profile-summary"
        mode = (mode or "label").strip()
        profile_complete = _is_profile_complete(profile)

        if mode == "explore" or profile_complete:
            return (
                no_update,
                {"display": "none"},
                base_profile_class,
            )

        banner = html.Div(
            [
                html.I(className="bi bi-exclamation-triangle-fill"),
                html.Span("Set your profile (name and email) using the top-right profile button before labeling or verifying."),
            ],
            className="profile-required-banner-inner",
        )
        return (
            banner,
            {"display": "block"},
            f"{base_profile_class} profile-summary--required",
        )

    def _coerce_positive_int(value, fallback):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    @app.callback(
        Output("app-config-modal", "is_open"),
        Output("app-config-items-per-page", "value"),
        Output("app-config-cache-size", "value"),
        Output("config-store", "data", allow_duplicate=True),
        Input("app-config-btn", "n_clicks"),
        Input("app-config-cancel", "n_clicks"),
        Input("app-config-save", "n_clicks"),
        State("config-store", "data"),
        State("app-config-items-per-page", "value"),
        State("app-config-cache-size", "value"),
        prevent_initial_call=True,
    )
    def handle_app_config(open_clicks, cancel_clicks, save_clicks, cfg, items_per_page, cache_size):
        triggered = ctx.triggered_id
        cfg = cfg or {}
        display_cfg = cfg.get("display", {}) or {}
        cache_cfg = cfg.get("cache", {}) or {}

        if triggered == "app-config-btn":
            return (
                True,
                display_cfg.get("items_per_page", 25),
                cache_cfg.get("max_size", 400),
                no_update,
            )

        if triggered == "app-config-cancel":
            return False, no_update, no_update, no_update

        if triggered != "app-config-save":
            raise PreventUpdate

        new_items_per_page = _coerce_positive_int(items_per_page, display_cfg.get("items_per_page", 25))
        new_cache_size = _coerce_positive_int(cache_size, cache_cfg.get("max_size", 400))

        updated_cfg = dict(cfg)
        updated_cfg["display"] = dict(display_cfg)
        updated_cfg["display"]["items_per_page"] = new_items_per_page
        updated_cfg["cache"] = dict(cache_cfg)
        updated_cfg["cache"]["max_size"] = new_cache_size

        set_cache_sizes(new_cache_size)

        return False, new_items_per_page, new_cache_size, updated_cfg

    @app.callback(
        Output("theme-store", "data"),
        Input("theme-toggle", "n_clicks"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_theme_store(n_clicks, theme):
        if not n_clicks:
            raise PreventUpdate
        theme = theme or "light"
        return "dark" if theme == "light" else "light"

    @app.callback(
        Output("theme-toggle", "children"),
        Output("theme-toggle", "className"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def sync_theme_toggle(theme):
        theme = theme or "light"
        is_dark = theme == "dark"
        icon_class = "bi bi-sun" if is_dark else "bi bi-moon-stars"
        btn_class = "icon-btn theme-btn"
        if is_dark:
            btn_class += " icon-btn--active"
        return html.I(className=icon_class), btn_class

    @app.callback(
        Output("app-shell", "className"),
        Output("app-shell", "style"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def apply_theme(theme):
        theme = theme or "light"
        # Return className and empty style (CSS handles theming via classes now)
        return f"app-shell theme-{theme}", {}

    # Clientside callback to apply theme to body element (for modals)
    app.clientside_callback(
        """
        function(theme) {
            theme = theme || 'light';
            document.body.classList.remove('theme-light', 'theme-dark');
            document.body.classList.add('theme-' + theme);
            return '';
        }
        """,
        Output("dummy-output", "data"),
        Input("theme-store", "data"),
        prevent_initial_call=False
    )

    @app.callback(
        Output("image-modal", "is_open"),
        Output("current-filename", "data"),
        Output("modal-image-graph", "figure"),
        Output("modal-bbox-store", "data"),
        Output("modal-active-box-label", "data"),
        Output("modal-header", "children"),
        Output("modal-audio-player", "children"),
        Output("modal-item-actions", "children"),
        Output("modal-nav-prev", "disabled"),
        Output("modal-nav-next", "disabled"),
        Output("modal-nav-position", "children"),
        Output("modal-snapshot-store", "data"),
        Output("modal-unsaved-store", "data"),
        Output("unsaved-changes-modal", "is_open"),
        Output("modal-pending-action-store", "data"),
        Input({"type": "spectrogram-image", "item_id": ALL}, "n_clicks"),
        Input("modal-nav-prev", "n_clicks"),
        Input("modal-nav-next", "n_clicks"),
        Input("close-modal", "n_clicks"),
        Input("modal-force-action-store", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("mode-tabs", "data"),
        State("verify-thresholds-store", "data"),
        State("verify-class-filter", "data"),
        State("modal-audio-settings-store", "data"),
        State("current-filename", "data"),
        State("modal-colormap-toggle", "value"),
        State("modal-y-axis-toggle", "value"),
        State("modal-unsaved-store", "data"),
        prevent_initial_call=True,
    )
    def handle_modal_trigger(
        image_clicks_list,
        prev_clicks,
        next_clicks,
        close_clicks,
        force_action,
        label_data,
        verify_data,
        explore_data,
        mode,
        thresholds,
        class_filter,
        audio_settings,
        current_item_id,
        colormap,
        y_axis_scale,
        unsaved_store,
    ):
        mode = mode or "label"
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        triggered = ctx.triggered_id

        page_items = _get_modal_navigation_items(
            mode,
            label_data,
            verify_data,
            explore_data,
            thresholds,
            class_filter,
        )
        page_item_ids = [item.get("item_id") for item in page_items if item and item.get("item_id")]

        is_forced = triggered == "modal-force-action-store"
        action = None
        if is_forced:
            if not isinstance(force_action, dict):
                raise PreventUpdate
            candidate = force_action.get("action")
            if isinstance(candidate, dict) and candidate.get("kind") in {"close", "open"}:
                action = candidate
        elif triggered == "close-modal":
            action = {"kind": "close"}
        elif isinstance(triggered, dict) and triggered.get("type") == "spectrogram-image":
            if not any(image_clicks_list):
                raise PreventUpdate
            clicked_item_id = (triggered.get("item_id") or "").strip()
            if clicked_item_id:
                action = {"kind": "open", "item_id": clicked_item_id}
        elif triggered in {"modal-nav-prev", "modal-nav-next"}:
            if not current_item_id or not page_item_ids:
                raise PreventUpdate
            if current_item_id not in page_item_ids:
                action = {"kind": "open", "item_id": page_item_ids[0]}
            else:
                current_index = page_item_ids.index(current_item_id)
                if triggered == "modal-nav-prev":
                    target_item_id = page_item_ids[max(0, current_index - 1)]
                else:
                    target_item_id = page_item_ids[min(len(page_item_ids) - 1, current_index + 1)]
                action = {"kind": "open", "item_id": target_item_id}
        if not isinstance(action, dict):
            raise PreventUpdate

        is_dirty = _is_modal_dirty(unsaved_store, current_item_id=current_item_id)
        if not is_forced and is_dirty:
            if action.get("kind") == "close":
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    action,
                )
            pending_item_id = (action.get("item_id") or "").strip() if action.get("kind") == "open" else ""
            if pending_item_id and pending_item_id != current_item_id:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    action,
                )

        if action.get("kind") == "close":
            return (
                False,
                None,
                no_update,
                {"item_id": None, "boxes": []},
                None,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                None,
                {"dirty": False, "item_id": None},
                False,
                None,
            )

        item_id = (action.get("item_id") or "").strip()

        if not item_id:
            raise PreventUpdate
        if item_id == current_item_id and not is_forced:
            raise PreventUpdate

        active_item = next((i for i in page_items if i.get("item_id") == item_id), None)
        if not active_item:
            items = (data or {}).get("items", [])
            active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate
        source_items = (data or {}).get("items", [])
        source_item = next(
            (item for item in source_items if isinstance(item, dict) and item.get("item_id") == item_id),
            active_item,
        )

        mat_path = active_item.get("mat_path")
        spectrogram = load_spectrogram_cached(mat_path)
        fig = create_spectrogram_figure(spectrogram, colormap, y_axis_scale)
        modal_boxes = _build_modal_boxes_from_item(source_item)
        fig = _apply_modal_boxes_to_figure(fig, modal_boxes)
        default_box_label = None

        settings = audio_settings or {}
        pitch_value = settings.get("pitch", 1.0)
        legacy_bass = settings.get("bass", 0.0)
        eq_values = {}
        for frequency in EQ_BAND_FREQUENCIES:
            eq_key = f"eq_{frequency}"
            if eq_key in settings:
                raw_eq_value = settings.get(eq_key)
            elif frequency <= EQ_LOW_FOCUS_MAX_HZ:
                raw_eq_value = legacy_bass
            else:
                raw_eq_value = 0.0
            try:
                eq_values[eq_key] = max(-24.0, min(24.0, float(raw_eq_value)))
            except (TypeError, ValueError):
                eq_values[eq_key] = 0.0
        gain_value = settings.get("gain", 1.0)

        audio_path = source_item.get("audio_path")
        modal_audio = create_modal_audio_player(
            audio_path,
            item_id,
            player_id="modal-player",
            pitch_value=pitch_value,
            eq_values=eq_values,
            gain_value=gain_value,
        ) if audio_path else html.P("No audio available for this item.", className="text-muted italic")

        modal_actions = _build_modal_item_actions(
            source_item,
            mode,
            thresholds or {"__global__": 0.5},
            boxes=modal_boxes,
            active_box_label=default_box_label,
        )

        if not page_item_ids:
            prev_disabled = True
            next_disabled = True
            position = "1 / 1"
        else:
            current_index = page_item_ids.index(item_id) if item_id in page_item_ids else 0
            prev_disabled = current_index <= 0
            next_disabled = current_index >= len(page_item_ids) - 1
            position = f"{current_index + 1} / {len(page_item_ids)}"

        snapshot_payload = _modal_snapshot_payload(mode, item_id, source_item, modal_boxes)

        return (
            True,
            item_id,
            fig,
            {"item_id": item_id, "boxes": modal_boxes},
            default_box_label,
            f"Spectrogram: {item_id}",
            modal_audio,
            modal_actions,
            prev_disabled,
            next_disabled,
            position,
            snapshot_payload,
            {"dirty": False, "item_id": item_id},
            False,
            None,
        )

    @app.callback(
        Output("unsaved-changes-modal", "is_open", allow_duplicate=True),
        Output("modal-pending-action-store", "data", allow_duplicate=True),
        Output("modal-force-action-store", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Input("unsaved-stay-btn", "n_clicks"),
        Input("unsaved-save-btn", "n_clicks"),
        Input("unsaved-discard-btn", "n_clicks"),
        State("modal-pending-action-store", "data"),
        State("modal-snapshot-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("current-filename", "data"),
        State("verify-thresholds-store", "data"),
        State("modal-bbox-store", "data"),
        State("user-profile-store", "data"),
        State("label-output-input", "value"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def resolve_unsaved_modal_action(
        stay_clicks,
        save_clicks,
        discard_clicks,
        pending_action,
        snapshot_store,
        mode,
        label_data,
        verify_data,
        explore_data,
        current_item_id,
        thresholds,
        bbox_store,
        profile,
        label_output_path,
        cfg,
    ):
        triggered = ctx.triggered_id
        if triggered == "unsaved-stay-btn":
            if not stay_clicks:
                raise PreventUpdate
            return False, None, no_update, no_update, no_update, no_update, no_update, no_update

        force_payload = no_update
        if isinstance(pending_action, dict) and pending_action.get("kind") in {"close", "open"}:
            force_payload = {
                "action": pending_action,
                "ts": time.time_ns(),
            }

        if triggered == "unsaved-save-btn":
            if not save_clicks:
                raise PreventUpdate
            next_label_data, next_verify_data, next_explore_data = _persist_modal_item_before_exit(
                mode=mode,
                item_id=current_item_id,
                label_data=label_data,
                verify_data=verify_data,
                explore_data=explore_data,
                thresholds=thresholds,
                profile=profile,
                bbox_store=bbox_store,
                label_output_path=label_output_path,
                cfg=cfg,
            )
            dirty_update = {"dirty": False, "item_id": current_item_id}
            return (
                False,
                None,
                force_payload,
                dirty_update,
                next_label_data,
                next_verify_data,
                next_explore_data,
                no_update,
            )

        if triggered != "unsaved-discard-btn" or not discard_clicks:
            raise PreventUpdate

        restored_label_data = no_update
        restored_verify_data = no_update
        restored_explore_data = no_update
        restored_bbox_store = no_update
        dirty_update = {"dirty": False, "item_id": current_item_id}

        snap = snapshot_store if isinstance(snapshot_store, dict) else {}
        snap_item_id = (snap.get("item_id") or "").strip()
        snap_item = snap.get("item")
        snap_boxes = snap.get("boxes")
        snap_mode = (snap.get("mode") or mode or "label").strip()

        if snap_item_id and isinstance(snap_item, dict):
            if snap_mode == "label":
                restored_label_data = _replace_item_in_data(label_data, snap_item_id, snap_item)
            elif snap_mode == "verify":
                restored_verify_data = _replace_item_in_data(verify_data, snap_item_id, snap_item)
            elif snap_mode == "explore":
                restored_explore_data = _replace_item_in_data(explore_data, snap_item_id, snap_item)
            restored_bbox_store = {
                "item_id": snap_item_id,
                "boxes": deepcopy(snap_boxes) if isinstance(snap_boxes, list) else [],
            }
            dirty_update = {"dirty": False, "item_id": snap_item_id}

        return (
            False,
            None,
            force_payload,
            dirty_update,
            restored_label_data,
            restored_verify_data,
            restored_explore_data,
            restored_bbox_store,
        )

    @app.callback(
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input("modal-colormap-toggle", "value"),
        Input("modal-y-axis-toggle", "value"),
        State("current-filename", "data"),
        State("modal-bbox-store", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def update_modal_view(colormap, y_axis_scale, item_id, bbox_store, label_data, verify_data, explore_data, mode):
        # Select the appropriate data store based on mode
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        if not item_id or not data:
            raise PreventUpdate

        items = data.get("items", [])
        active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate

        mat_path = active_item.get("mat_path")
        spectrogram = load_spectrogram_cached(mat_path)
        fig = create_spectrogram_figure(spectrogram, colormap, y_axis_scale)
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        else:
            boxes = _build_modal_boxes_from_item(active_item)
        return _apply_modal_boxes_to_figure(fig, boxes)

    @app.callback(
        Output("modal-item-actions", "children", allow_duplicate=True),
        Input("current-filename", "data"),
        Input("label-data-store", "data"),
        Input("verify-data-store", "data"),
        Input("explore-data-store", "data"),
        Input("mode-tabs", "data"),
        Input("verify-thresholds-store", "data"),
        Input("modal-bbox-store", "data"),
        Input("modal-active-box-label", "data"),
        prevent_initial_call=True,
    )
    def refresh_modal_item_actions(
        item_id,
        label_data,
        verify_data,
        explore_data,
        mode,
        thresholds,
        bbox_store,
        active_box_label,
    ):
        if not item_id:
            raise PreventUpdate
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        items = (data or {}).get("items", [])
        active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate
        boxes = []
        if isinstance(bbox_store, dict) and bbox_store.get("item_id") == item_id:
            boxes = bbox_store.get("boxes") or []
        return _build_modal_item_actions(
            active_item,
            mode,
            thresholds or {"__global__": 0.5},
            boxes=boxes,
            active_box_label=active_box_label,
        )

    @app.callback(
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input({"type": "modal-label-add-box", "label": ALL}, "n_clicks"),
        State("modal-image-graph", "figure"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def set_modal_active_box_label(add_box_clicks, figure, profile):
        if not ctx.triggered or (ctx.triggered[0].get("value") or 0) <= 0:
            raise PreventUpdate
        _require_complete_profile(profile, "set_modal_active_box_label")
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        if triggered.get("type") != "modal-label-add-box":
            raise PreventUpdate
        label = (triggered.get("label") or "").strip()
        if not label:
            raise PreventUpdate
        # BBox '+' always allows drawing another box for the same label.
        target = {"label": label, "allow_existing": True}

        if not isinstance(figure, dict):
            return target, no_update

        updated_figure = deepcopy(figure)
        layout = updated_figure.get("layout")
        if not isinstance(layout, dict):
            layout = {}
        layout["dragmode"] = "drawrect"
        updated_figure["layout"] = layout
        return target, updated_figure

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input({"type": "modal-label-delete-confirm", "label": ALL}, "submit_n_clicks"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("verify-thresholds-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def delete_modal_label(
        submit_clicks,
        current_item_id,
        mode,
        label_data,
        verify_data,
        explore_data,
        bbox_store,
        figure,
        thresholds,
        profile,
    ):
        if not submit_clicks or all((clicks or 0) <= 0 for clicks in submit_clicks):
            raise PreventUpdate
        if not ctx.triggered or (ctx.triggered[0].get("value") or 0) <= 0:
            raise PreventUpdate

        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        if not current_item_id:
            raise PreventUpdate

        label_to_delete = (triggered.get("label") or "").strip()
        if not label_to_delete:
            raise PreventUpdate

        mode = mode or "label"
        if mode == "explore":
            raise PreventUpdate
        _require_complete_profile(profile, "delete_modal_label")

        data = deepcopy(_get_mode_data(mode, label_data, verify_data, explore_data))
        if not data:
            raise PreventUpdate

        items = data.get("items", [])
        active_item = next((item for item in items if item and item.get("item_id") == current_item_id), None)
        if not active_item:
            raise PreventUpdate

        _, _, active_labels = _get_modal_label_sets(active_item, mode, thresholds or {"__global__": 0.5})
        active_label_set = {(label or "").strip() for label in active_labels if isinstance(label, str)}
        if label_to_delete not in active_label_set:
            raise PreventUpdate
        updated_labels = [
            label for label in active_labels
            if isinstance(label, str) and (label or "").strip() != label_to_delete
        ]

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {"item_id": current_item_id, "boxes": []}
        existing_boxes = store.get("boxes") if isinstance(store.get("boxes"), list) else []
        filtered_boxes = [
            box for box in existing_boxes
            if isinstance(box, dict) and (box.get("label") or "").strip() != label_to_delete
        ]
        store["item_id"] = current_item_id
        store["boxes"] = filtered_boxes

        profile_name = _profile_actor(profile)
        label_extents = _extract_label_extent_map_from_boxes(filtered_boxes)
        updated_data = _update_item_labels(
            data,
            current_item_id,
            updated_labels,
            mode,
            user_name=profile_name,
            label_extents=label_extents or None,
        )
        if mode == "verify":
            current_rejected = set(_get_item_rejected_labels(active_item))
            current_rejected.add(label_to_delete)
            for entry in (updated_data or {}).get("items", []):
                if not isinstance(entry, dict) or entry.get("item_id") != current_item_id:
                    continue
                annotations_obj = entry.get("annotations") or {}
                annotations_obj["rejected_labels"] = sorted(current_rejected)
                entry["annotations"] = annotations_obj
                break

        updated_fig = _apply_modal_boxes_to_figure(deepcopy(figure) if isinstance(figure, dict) else {}, filtered_boxes)
        next_active_label = None
        unsaved_update = {"dirty": True, "item_id": current_item_id}

        if mode == "label":
            return updated_data, no_update, no_update, store, updated_fig, next_active_label, unsaved_update
        if mode == "verify":
            return no_update, updated_data, no_update, store, updated_fig, next_active_label, unsaved_update
        return no_update, no_update, updated_data, store, updated_fig, next_active_label, unsaved_update

    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input("modal-image-graph", "relayoutData"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("modal-active-box-label", "data"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def update_modal_boxes_from_graph(relayout_data, bbox_store, figure, active_box_label, current_item_id, mode, profile):
        if not current_item_id or not relayout_data:
            raise PreventUpdate
        if mode == "explore":
            raise PreventUpdate
        _require_complete_profile(profile, "update_modal_boxes_from_graph")

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {}
        if store.get("item_id") != current_item_id:
            store = {"item_id": current_item_id, "boxes": []}
        boxes = deepcopy(store.get("boxes") or [])
        axis_meta = _axis_meta_from_figure(figure if isinstance(figure, dict) else {})

        chosen_label, allow_existing_label = _parse_active_box_target(active_box_label)
        _bbox_debug(
            "start",
            item_id=current_item_id,
            triggered=ctx.triggered_id,
            chosen_label=chosen_label,
            relayout_keys=sorted(relayout_data.keys()),
            relayout_data=relayout_data,
            boxes_before=_bbox_debug_box_summary(boxes),
        )

        keys = set(relayout_data.keys())
        if keys and keys.issubset({"shapes[0].x0", "shapes[0].x1"}):
            # Ignore playback marker updates coming from audio timeline sync.
            _bbox_debug("ignore_playback_marker_update", keys=sorted(keys))
            raise PreventUpdate

        updated = False
        force_resync = False
        clear_active_label = False
        is_add_mode = bool(chosen_label) and not any(
            (existing.get("label") or "").strip() == chosen_label
            for existing in boxes
            if isinstance(existing, dict)
        )
        if allow_existing_label and chosen_label:
            is_add_mode = True
        _bbox_debug(
            "mode_decision",
            is_add_mode=is_add_mode,
            allow_existing_label=allow_existing_label,
            chosen_label=chosen_label,
            existing_labels=[(b.get("label") if isinstance(b, dict) else None) for b in boxes],
        )

        def _shape_signature(raw_shape):
            if not isinstance(raw_shape, dict):
                return None
            x0 = _safe_float(raw_shape.get("x0"), None)
            x1 = _safe_float(raw_shape.get("x1"), None)
            y0 = _safe_float(raw_shape.get("y0"), None)
            y1 = _safe_float(raw_shape.get("y1"), None)
            if None in (x0, x1, y0, y1):
                return None
            if x0 > x1:
                x0, x1 = x1, x0
            if y0 > y1:
                y0, y1 = y1, y0
            x_min = axis_meta.get("x_min", 0.0)
            x_max = axis_meta.get("x_max", 1.0)
            y_min = axis_meta.get("y_min", 0.0)
            y_max = axis_meta.get("y_max", 1.0)
            x0 = max(x_min, min(x_max, x0))
            x1 = max(x_min, min(x_max, x1))
            y0 = max(y_min, min(y_max, y0))
            y1 = max(y_min, min(y_max, y1))
            if x0 > x1:
                x0, x1 = x1, x0
            if y0 > y1:
                y0, y1 = y1, y0
            return (round(x0, 6), round(x1, 6), round(y0, 6), round(y1, 6))

        # Incremental edits and delete events.
        delete_indices = []
        coord_updates = {}
        for key, value in relayout_data.items():
            delete_match = re.match(r"^shapes\[(\d+)\]$", str(key))
            if delete_match and value is None:
                delete_idx = int(delete_match.group(1)) - 1
                if delete_idx >= 0:
                    delete_indices.append(delete_idx)
                continue

            coord_match = re.match(r"^shapes\[(\d+)\]\.(x0|x1|y0|y1)$", str(key))
            if coord_match:
                shape_idx = int(coord_match.group(1))
                if shape_idx == 0:
                    continue
                box_idx = shape_idx - 1
                coord_updates.setdefault(box_idx, {})
                coord_updates[box_idx][coord_match.group(2)] = _safe_float(value)

        payload_shapes = None
        if isinstance(relayout_data.get("shapes"), list):
            filtered_shapes = []
            for shape in relayout_data.get("shapes", []):
                if not isinstance(shape, dict):
                    continue
                if shape.get("name") == "playback-marker":
                    continue
                if shape.get("type") == "line" and shape.get("yref") == "paper":
                    continue
                if shape.get("type") != "rect":
                    continue
                if _shape_signature(shape) is None:
                    continue
                filtered_shapes.append(shape)
            payload_shapes = filtered_shapes
            _bbox_debug(
                "payload_shapes_filtered",
                payload_count=len(filtered_shapes),
                payload_signatures=[_shape_signature(shape) for shape in filtered_shapes],
            )

        # Full shapes payload handling.
        if isinstance(payload_shapes, list):
            if is_add_mode and chosen_label:
                existing_signatures = set()
                for existing in boxes:
                    if not isinstance(existing, dict):
                        continue
                    existing_shape = _extent_to_shape(existing.get("annotation_extent"), axis_meta)
                    signature = _shape_signature(existing_shape)
                    if signature is not None:
                        existing_signatures.add(signature)
                _bbox_debug(
                    "add_mode_existing_signatures",
                    signatures=sorted(existing_signatures),
                )

                new_shape = None
                for shape in payload_shapes:
                    signature = _shape_signature(shape)
                    if signature is None or signature in existing_signatures:
                        continue
                    new_shape = shape
                    _bbox_debug("add_mode_new_shape_candidate", signature=signature, shape=shape)

                if (
                    new_shape is not None
                    and (
                        allow_existing_label
                        or not any((existing.get("label") or "").strip() == chosen_label for existing in boxes)
                    )
                ):
                    extent = _shape_to_extent(new_shape, axis_meta)
                    if extent and extent.get("type") != "clip":
                        boxes.append(
                            {
                                "label": chosen_label,
                                "annotation_extent": extent,
                                "source": "manual",
                                "decision": "added",
                            }
                        )
                        updated = True
                        clear_active_label = True
                        _bbox_debug("add_mode_append_from_payload", chosen_label=chosen_label, extent=extent)
            elif not coord_updates and not delete_indices:
                rebuilt = []
                for idx, shape in enumerate(payload_shapes):
                    extent = _shape_to_extent(shape, axis_meta)
                    if not extent or extent.get("type") == "clip":
                        continue

                    if idx < len(boxes):
                        box = deepcopy(boxes[idx])
                    else:
                        if not chosen_label:
                            continue
                        if any((existing.get("label") or "").strip() == chosen_label for existing in rebuilt):
                            continue
                        box = {"label": chosen_label, "source": "manual", "decision": "added"}
                    box["annotation_extent"] = extent
                    if not (box.get("label") or "").strip():
                        box["label"] = chosen_label or "Unlabeled"
                    if idx >= len(boxes):
                        box["source"] = "manual"
                        box["decision"] = "added"
                    rebuilt.append(box)

                if rebuilt != boxes:
                    boxes = rebuilt
                    updated = True
                    _bbox_debug("rebuild_from_payload", boxes_after=_bbox_debug_box_summary(boxes))
                elif len(payload_shapes) != len(boxes):
                    # Graph still has stale/ghost rectangles not represented in store.
                    force_resync = True
                    _bbox_debug(
                        "stale_payload_shape_count_mismatch",
                        payload_count=len(payload_shapes),
                        box_count=len(boxes),
                    )

        for idx in sorted(set(delete_indices), reverse=True):
            if 0 <= idx < len(boxes):
                _bbox_debug("delete_index", index=idx, box=boxes[idx] if idx < len(boxes) else None)
                boxes.pop(idx)
                updated = True

        for box_idx, updates in coord_updates.items():
            if box_idx < 0:
                continue
            _bbox_debug("coord_update", box_idx=box_idx, updates=updates, is_add_mode=is_add_mode)
            if is_add_mode:
                # In add mode, only accept updates that target a new shape index.
                if box_idx < len(boxes):
                    _bbox_debug("coord_ignored_existing_in_add_mode", box_idx=box_idx, total_boxes=len(boxes))
                    continue
                if not chosen_label:
                    _bbox_debug("coord_ignored_no_label_in_add_mode", box_idx=box_idx)
                    continue
                if all(updates.get(k) is not None for k in ("x0", "x1", "y0", "y1")):
                    extent = _shape_to_extent({"type": "rect", **updates}, axis_meta)
                    if (
                        extent
                        and extent.get("type") != "clip"
                        and (
                            allow_existing_label
                            or not any((existing.get("label") or "").strip() == chosen_label for existing in boxes)
                        )
                    ):
                        boxes.append(
                            {
                                "label": chosen_label,
                                "annotation_extent": extent,
                                "source": "manual",
                                "decision": "added",
                            }
                        )
                        updated = True
                        clear_active_label = True
                        _bbox_debug("add_mode_append_from_coords", chosen_label=chosen_label, extent=extent)
                continue

            if box_idx < len(boxes):
                shape = _extent_to_shape(boxes[box_idx].get("annotation_extent"), axis_meta) or {"type": "rect"}
                for axis_key in ("x0", "x1", "y0", "y1"):
                    if updates.get(axis_key) is not None:
                        shape[axis_key] = updates[axis_key]
                extent = _shape_to_extent(shape, axis_meta)
                if extent and extent.get("type") != "clip":
                    if extent != boxes[box_idx].get("annotation_extent"):
                        _bbox_debug(
                            "update_existing_box_extent",
                            box_idx=box_idx,
                            old_extent=boxes[box_idx].get("annotation_extent"),
                            new_extent=extent,
                        )
                        boxes[box_idx]["annotation_extent"] = extent
                        updated = True
            else:
                # Plotly can emit stale shape index updates immediately after delete.
                force_resync = True
                _bbox_debug(
                    "stale_coord_without_box",
                    box_idx=box_idx,
                    total_boxes=len(boxes),
                    updates=updates,
                )

        if not updated and not force_resync:
            _bbox_debug("no_update", boxes_after=_bbox_debug_box_summary(boxes))
            raise PreventUpdate
        store["item_id"] = current_item_id
        store["boxes"] = boxes
        updated_fig = _apply_modal_boxes_to_figure(
            deepcopy(figure) if isinstance(figure, dict) else {},
            boxes,
            revision_bump=(time.time_ns() if force_resync else None),
        )
        if clear_active_label and isinstance(updated_fig, dict):
            layout = updated_fig.get("layout")
            if not isinstance(layout, dict):
                layout = {}
            layout["dragmode"] = "pan"
            updated_fig["layout"] = layout
        if force_resync and not updated:
            _bbox_debug("return_resync_only", boxes_after=_bbox_debug_box_summary(boxes))
        _bbox_debug(
            "return_update",
            clear_active_label=clear_active_label,
            boxes_after=_bbox_debug_box_summary(boxes),
        )
        dirty_update = {"dirty": True, "item_id": current_item_id} if updated else no_update
        return store, updated_fig, (None if clear_active_label else no_update), dirty_update

    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input("modal-image-graph", "clickData"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def delete_modal_box_from_graph_click(click_data, bbox_store, figure, current_item_id, mode, profile):
        if not current_item_id:
            raise PreventUpdate
        if mode == "explore":
            raise PreventUpdate
        _require_complete_profile(profile, "delete_modal_box_from_graph_click")

        def _coerce_int(value):
            if isinstance(value, bool) or value is None:
                return None
            if isinstance(value, (int, float)):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return None
                try:
                    return int(float(text))
                except (TypeError, ValueError):
                    return None
            return None

        points = click_data.get("points") if isinstance(click_data, dict) else None
        point = points[0] if isinstance(points, list) and points and isinstance(points[0], dict) else None
        curve_number = _coerce_int(point.get("curveNumber")) if isinstance(point, dict) else None
        custom_data = point.get("customdata") if isinstance(point, dict) else None
        _bbox_debug(
            "inline_delete_start",
            triggered=ctx.triggered_id,
            current_item_id=current_item_id,
            click_data=click_data,
            curve_number=curve_number,
            custom_data=custom_data,
        )
        if curve_number is None:
            raise PreventUpdate

        fig_data = figure.get("data") if isinstance(figure, dict) else None
        if not isinstance(fig_data, list) or curve_number < 0 or curve_number >= len(fig_data):
            raise PreventUpdate
        clicked_trace = fig_data[curve_number]
        if not isinstance(clicked_trace, dict) or clicked_trace.get("name") != _BBOX_DELETE_TRACE_NAME:
            raise PreventUpdate

        box_index = None
        if isinstance(custom_data, (int, float, str)):
            box_index = _coerce_int(custom_data)
        elif isinstance(custom_data, list) and custom_data:
            first_val = custom_data[0]
            box_index = _coerce_int(first_val)
        if box_index is None:
            _bbox_debug("inline_delete_missing_index", custom_data=custom_data)
            raise PreventUpdate

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {}
        if store.get("item_id") != current_item_id:
            raise PreventUpdate
        boxes = deepcopy(store.get("boxes") or [])
        if not boxes:
            raise PreventUpdate

        if not isinstance(box_index, int) or box_index < 0 or box_index >= len(boxes):
            # Stale click on a handle from an older figure state: re-sync display.
            _bbox_debug(
                "inline_delete_stale_index_resync",
                box_index=box_index,
                total_boxes=len(boxes),
            )
            updated_fig = _apply_modal_boxes_to_figure(
                deepcopy(figure) if isinstance(figure, dict) else {},
                boxes,
                revision_bump=time.time_ns(),
            )
            return store, updated_fig, no_update, no_update

        _bbox_debug("inline_delete_remove_index", box_index=box_index, box=boxes[box_index])
        boxes.pop(box_index)

        store["item_id"] = current_item_id
        store["boxes"] = boxes
        updated_fig = _apply_modal_boxes_to_figure(deepcopy(figure) if isinstance(figure, dict) else {}, boxes)
        if isinstance(updated_fig, dict):
            layout = updated_fig.get("layout")
            if not isinstance(layout, dict):
                layout = {}
            layout["dragmode"] = "pan"
            updated_fig["layout"] = layout
        _bbox_debug("inline_delete_return", boxes_after=_bbox_debug_box_summary(boxes))
        return store, updated_fig, no_update, {"dirty": True, "item_id": current_item_id}

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Input("modal-bbox-store", "data"),
        Input("modal-unsaved-store", "data"),
        State("mode-tabs", "data"),
        State("current-filename", "data"),
        State("label-data-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def sync_label_bbox_edits_to_item(
        bbox_store,
        unsaved_store,
        mode,
        current_item_id,
        label_data,
        profile,
    ):
        """Mirror modal bbox edits into label item annotations so Save becomes available."""
        if mode != "label":
            raise PreventUpdate
        if not current_item_id:
            raise PreventUpdate
        if not isinstance(bbox_store, dict) or bbox_store.get("item_id") != current_item_id:
            raise PreventUpdate
        if not _is_modal_dirty(unsaved_store, current_item_id=current_item_id):
            raise PreventUpdate
        _require_complete_profile(profile, "sync_label_bbox_edits_to_item")

        data = deepcopy(label_data or {})
        items = data.get("items") or []
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == current_item_id),
            None,
        )
        if not isinstance(active_item, dict):
            raise PreventUpdate

        _, _, active_labels = _get_modal_label_sets(active_item, "label", {"__global__": 0.5})
        active_labels = _ordered_unique_labels(active_labels)

        boxes = bbox_store.get("boxes")
        boxes = boxes if isinstance(boxes, list) else []
        next_label_extents = _extract_label_extent_map_from_boxes(boxes)
        if next_label_extents:
            merged_labels = list(active_labels)
            seen_labels = set(merged_labels)
            for extent_label in next_label_extents.keys():
                if extent_label not in seen_labels:
                    merged_labels.append(extent_label)
                    seen_labels.add(extent_label)
            active_labels = merged_labels

        existing_annotations = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        existing_labels = _ordered_unique_labels(existing_annotations.get("labels") or [])
        existing_raw_extents = existing_annotations.get("label_extents") if isinstance(existing_annotations, dict) else None
        existing_label_extents = {}
        if isinstance(existing_raw_extents, dict):
            for label, extent in existing_raw_extents.items():
                if not isinstance(label, str):
                    continue
                normalized_label = label.strip()
                if not normalized_label:
                    continue
                cleaned = _clean_annotation_extent(extent)
                if cleaned:
                    existing_label_extents[normalized_label] = cleaned

        if (
            existing_labels == active_labels
            and existing_label_extents == next_label_extents
            and _has_pending_label_edits(existing_annotations)
        ):
            raise PreventUpdate

        profile_name = _profile_actor(profile)
        updated_data = _update_item_labels(
            data,
            current_item_id,
            active_labels,
            mode="label",
            user_name=profile_name,
            label_extents=next_label_extents,
        )
        return updated_data

    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
        Input("modal-bbox-store", "data"),
        Input("modal-unsaved-store", "data"),
        State("mode-tabs", "data"),
        State("current-filename", "data"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def sync_verify_bbox_edits_to_item(
        bbox_store,
        unsaved_store,
        mode,
        current_item_id,
        verify_data,
        thresholds,
        profile,
    ):
        """Mirror modal bbox edits into verify item annotations so Save becomes available."""
        if mode != "verify":
            raise PreventUpdate
        if not current_item_id:
            raise PreventUpdate
        if not isinstance(bbox_store, dict) or bbox_store.get("item_id") != current_item_id:
            raise PreventUpdate
        if not _is_modal_dirty(unsaved_store, current_item_id=current_item_id):
            raise PreventUpdate
        _require_complete_profile(profile, "sync_verify_bbox_edits_to_item")

        data = deepcopy(verify_data or {})
        items = data.get("items") or []
        active_item = next(
            (item for item in items if isinstance(item, dict) and item.get("item_id") == current_item_id),
            None,
        )
        if not isinstance(active_item, dict):
            raise PreventUpdate

        thresholds = thresholds or {"__global__": 0.5}
        _, _, active_labels = _get_modal_label_sets(active_item, "verify", thresholds)
        active_labels = _ordered_unique_labels(active_labels)

        boxes = bbox_store.get("boxes")
        boxes = boxes if isinstance(boxes, list) else []
        next_label_extents = _extract_label_extent_map_from_boxes(boxes)

        existing_annotations = active_item.get("annotations") if isinstance(active_item.get("annotations"), dict) else {}
        existing_raw_extents = existing_annotations.get("label_extents") if isinstance(existing_annotations, dict) else None
        existing_label_extents = {}
        if isinstance(existing_raw_extents, dict):
            for label, extent in existing_raw_extents.items():
                if not isinstance(label, str):
                    continue
                normalized_label = label.strip()
                if not normalized_label:
                    continue
                cleaned = _clean_annotation_extent(extent)
                if cleaned:
                    existing_label_extents[normalized_label] = cleaned

        # Ignore no-op updates so opening the modal does not trigger a fake dirty state.
        if existing_label_extents == next_label_extents:
            raise PreventUpdate

        profile_name = _profile_actor(profile)
        updated_data = _update_item_labels(
            data,
            current_item_id,
            active_labels,
            mode="verify",
            user_name=profile_name,
            label_extents=next_label_extents,
        )
        return updated_data

    # Initialize audio players when page content or modal changes
    app.clientside_callback(
        """
        function(trigger) {
            if (window.dash_clientside && window.dash_clientside.namespace) {
                setTimeout(function() {
                    window.dash_clientside.namespace.initializeAudioPlayers();
                }, 150);
            }
            return '';
        }
        """,
        Output("dummy-output-audio", "children"),
        [Input("label-grid", "children"), 
         Input("verify-grid", "children"), 
         Input("modal-audio-player", "children")],
        prevent_initial_call=True
    )

    @app.callback(
        Output("modal-player-pitch-display", "children"),
        Input("modal-player-pitch-slider", "value"),
        prevent_initial_call=True,
    )
    def update_modal_pitch_display(value):
        if value is None:
            raise PreventUpdate
        try:
            return f"{float(value):.2f}x"
        except (TypeError, ValueError):
            return "1.00x"

    @app.callback(
        Output("modal-player-eq-display", "children"),
        Input("modal-player-eq-20-slider", "value"),
        Input("modal-player-eq-40-slider", "value"),
        Input("modal-player-eq-80-slider", "value"),
        Input("modal-player-eq-160-slider", "value"),
        Input("modal-player-eq-315-slider", "value"),
        Input("modal-player-eq-630-slider", "value"),
        Input("modal-player-eq-1250-slider", "value"),
        Input("modal-player-eq-2500-slider", "value"),
        Input("modal-player-eq-5000-slider", "value"),
        Input("modal-player-eq-10000-slider", "value"),
        Input("modal-player-eq-16000-slider", "value"),
        prevent_initial_call=True,
    )
    def update_modal_eq_display(
        eq_20,
        eq_40,
        eq_80,
        eq_160,
        eq_315,
        eq_630,
        eq_1250,
        eq_2500,
        eq_5000,
        eq_10000,
        eq_16000,
    ):
        return "Full-range EQ: 20 Hz to 16 kHz"

    @app.callback(
        Output("modal-player-gain-display", "children"),
        Input("modal-player-gain-slider", "value"),
        prevent_initial_call=True,
    )
    def update_modal_gain_display(value):
        if value is None:
            raise PreventUpdate
        try:
            return f"{float(value):.1f}x"
        except (TypeError, ValueError):
            return "1.0x"

    @app.callback(
        Output("modal-audio-settings-store", "data"),
        Input("modal-player-pitch-slider", "value"),
        Input("modal-player-eq-20-slider", "value"),
        Input("modal-player-eq-40-slider", "value"),
        Input("modal-player-eq-80-slider", "value"),
        Input("modal-player-eq-160-slider", "value"),
        Input("modal-player-eq-315-slider", "value"),
        Input("modal-player-eq-630-slider", "value"),
        Input("modal-player-eq-1250-slider", "value"),
        Input("modal-player-eq-2500-slider", "value"),
        Input("modal-player-eq-5000-slider", "value"),
        Input("modal-player-eq-10000-slider", "value"),
        Input("modal-player-eq-16000-slider", "value"),
        Input("modal-player-gain-slider", "value"),
        State("modal-audio-settings-store", "data"),
        prevent_initial_call=True,
    )
    def persist_modal_audio_settings(
        pitch,
        eq_20,
        eq_40,
        eq_80,
        eq_160,
        eq_315,
        eq_630,
        eq_1250,
        eq_2500,
        eq_5000,
        eq_10000,
        eq_16000,
        gain,
        current_settings,
    ):
        current_settings = current_settings or {
            "pitch": 1.0,
            "eq_20": 0.0,
            "eq_40": 0.0,
            "eq_80": 0.0,
            "eq_160": 0.0,
            "eq_315": 0.0,
            "eq_630": 0.0,
            "eq_1250": 0.0,
            "eq_2500": 0.0,
            "eq_5000": 0.0,
            "eq_10000": 0.0,
            "eq_16000": 0.0,
            "gain": 1.0,
        }
        updated = dict(current_settings)
        changed = False

        if pitch is not None:
            try:
                pitch_value = float(pitch)
                if updated.get("pitch") != pitch_value:
                    updated["pitch"] = pitch_value
                    changed = True
            except (TypeError, ValueError):
                pass

        eq_inputs = {
            "eq_20": eq_20,
            "eq_40": eq_40,
            "eq_80": eq_80,
            "eq_160": eq_160,
            "eq_315": eq_315,
            "eq_630": eq_630,
            "eq_1250": eq_1250,
            "eq_2500": eq_2500,
            "eq_5000": eq_5000,
            "eq_10000": eq_10000,
            "eq_16000": eq_16000,
        }
        for eq_key, eq_input in eq_inputs.items():
            if eq_input is None:
                continue
            try:
                eq_value = max(-24.0, min(24.0, float(eq_input)))
                if updated.get(eq_key) != eq_value:
                    updated[eq_key] = eq_value
                    changed = True
            except (TypeError, ValueError):
                continue

        if gain is not None:
            try:
                gain_value = float(gain)
                if updated.get("gain") != gain_value:
                    updated["gain"] = gain_value
                    changed = True
            except (TypeError, ValueError):
                pass

        if not changed:
            raise PreventUpdate
        return updated



    # Data Discovery Callbacks
    app.clientside_callback(
        """
        function(loadTrigger, labelReload, verifyReload, exploreReload, dateVal, deviceVal, mode, labelData, verifyData, exploreData) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (!ctx || !ctx.triggered || ctx.triggered.length === 0) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }

            var triggered = ctx.triggered[0];
            var triggerId = triggered.prop_id.split('.')[0];
            var triggerVal = triggered.value;

            function show(title, subtitle) {
                return [{display: "flex"}, title, subtitle];
            }

            if (triggerId === "data-load-trigger-store" && loadTrigger && loadTrigger.mode) {
                var title = "Loading dataset...";
                var subtitle = "Applying configuration and preparing your workspace.";
                if (loadTrigger.mode === "verify") {
                    subtitle = "Applying configuration and loading predictions.";
                } else if (loadTrigger.mode === "label") {
                    subtitle = "Applying configuration and loading items.";
                } else if (loadTrigger.mode === "explore") {
                    subtitle = "Applying configuration and loading items for exploration.";
                }
                return show(title, subtitle);
            }

            if (!triggerVal) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }

            if (triggerId === "label-reload" && mode === "label") {
                return show("Loading dataset...", "Reloading items.");
            }
            if (triggerId === "verify-reload" && mode === "verify") {
                return show("Loading dataset...", "Reloading predictions.");
            }
            if (triggerId === "explore-reload" && mode === "explore") {
                return show("Loading dataset...", "Reloading items for exploration.");
            }

            if (triggerId === "global-date-selector" || triggerId === "global-device-selector") {
                var tabData = mode === "label" ? labelData : (mode === "verify" ? verifyData : exploreData);
                var hasSource = tabData && tabData.source_data_dir;
                if (!hasSource) {
                    return [dc.no_update, dc.no_update, dc.no_update];
                }
                var title2 = "Updating filters...";
                var subtitle2 = "Loading data for the selected date/device.";
                if (mode === "verify") {
                    subtitle2 = "Loading predictions for the selected date/device.";
                } else if (mode === "explore") {
                    subtitle2 = "Loading items for exploration.";
                }
                return show(title2, subtitle2);
            }

            return [dc.no_update, dc.no_update, dc.no_update];
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Output("data-load-title", "children", allow_duplicate=True),
        Output("data-load-subtitle", "children", allow_duplicate=True),
        Input("data-load-trigger-store", "data"),
        Input("label-reload", "n_clicks"),
        Input("verify-reload", "n_clicks"),
        Input("explore-reload", "n_clicks"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("tab-filter-state-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("mode-tabs", "data"),
        State("tab-filter-state-store", "data"),
        prevent_initial_call=True,
    )
    def persist_active_tab_filters(selected_date, selected_device, mode, tab_filter_state):
        mode = (mode or "").strip()
        if mode not in {"label", "verify", "explore"}:
            _tab_iso_debug(
                "persist_filters_skip_invalid_mode",
                mode=mode,
                selected_date=selected_date,
                selected_device=selected_device,
            )
            raise PreventUpdate

        state = deepcopy(tab_filter_state or {})
        for tab in ("label", "verify", "explore"):
            if not isinstance(state.get(tab), dict):
                state[tab] = {"date": None, "device": None}

        current = state.get(mode, {})
        next_entry = dict(current)
        triggered = ctx.triggered_id
        if triggered == "global-date-selector":
            next_entry["date"] = selected_date
        elif triggered == "global-device-selector":
            next_entry["device"] = selected_device
        else:
            next_entry["date"] = selected_date
            next_entry["device"] = selected_device

        if current == next_entry:
            _tab_iso_debug(
                "persist_filters_nochange",
                mode=mode,
                triggered=str(triggered),
                selected_date=selected_date,
                selected_device=selected_device,
            )
            raise PreventUpdate

        state[mode] = next_entry
        _tab_iso_debug(
            "persist_filters_update",
            mode=mode,
            triggered=str(triggered),
            selected_date=selected_date,
            selected_device=selected_device,
            next_entry=next_entry,
        )
        return state

    @app.callback(
        Output("global-date-selector", "options", allow_duplicate=True),
        Output("global-date-selector", "value", allow_duplicate=True),
        Input("mode-tabs", "data"),
        State("config-store", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("tab-filter-state-store", "data"),
        State("global-date-selector", "value"),
        prevent_initial_call="initial_duplicate",
    )
    def discover_dates(mode, cfg, label_data, verify_data, explore_data, tab_filter_state, global_date_value):
        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        configured_data_dir = _config_default_data_dir(cfg or {})
        tab_data_dir = tab_data.get("source_data_dir") if tab_data else None
        # Keep tab roots isolated: use this tab's loaded source first.
        data_dir = tab_data_dir or configured_data_dir
        _tab_iso_debug(
            "discover_dates_start",
            mode=mode,
            tab_data_dir=tab_data_dir,
            configured_data_dir=configured_data_dir,
            resolved_data_dir=data_dir,
            global_date_value=global_date_value,
        )
        if not data_dir or not os.path.exists(data_dir):
            _tab_iso_debug("discover_dates_no_dir", mode=mode, resolved_data_dir=data_dir)
            return [], None

        tab_state = (tab_filter_state or {}).get(mode, {}) if isinstance(tab_filter_state, dict) else {}
        saved_date = tab_state.get("date") if isinstance(tab_state, dict) else None
        current_date = global_date_value

        # Dates are folders like YYYY-MM-DD
        try:
            base_name = os.path.basename(data_dir.rstrip(os.sep))
            if len(base_name) == 10 and base_name[4] == '-' and base_name[7] == '-':
                _tab_iso_debug("discover_dates_return_base_date", mode=mode, base_name=base_name)
                return [{"label": base_name, "value": base_name}], base_name

            dates = [d for d in os.listdir(data_dir) if len(d) == 10 and os.path.isdir(os.path.join(data_dir, d))]
            dates.sort(reverse=True)

            options = [{"label": "All Dates", "value": "__all__"}] + [
                {"label": d, "value": d} for d in dates
            ]
            option_values = {"__all__", *dates}
            default_val = dates[0] if dates else None

            # Apply config defaults only for Verify mode.
            config_date = None
            if mode == "verify" and isinstance(cfg, dict):
                verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
                config_date = verify_cfg.get("date")
            if saved_date in option_values:
                default_val = saved_date
            elif current_date in option_values:
                default_val = current_date
            elif config_date in dates:
                default_val = config_date

            if dates:
                _tab_iso_debug(
                    "discover_dates_return_dates",
                    mode=mode,
                    options_count=len(options),
                    default_val=default_val,
                    saved_date=saved_date,
                    current_date=current_date,
                    config_date=config_date,
                )
                return options, default_val

            # Device-only root (no date folders) - keep date selector meaningful
            devices = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
            if devices:
                device_only_val = "__device_only__"
                if saved_date == device_only_val:
                    _tab_iso_debug("discover_dates_return_device_only_saved", mode=mode, default_val=saved_date)
                    return [{"label": "Device folders", "value": device_only_val}], saved_date
                if current_date == device_only_val:
                    _tab_iso_debug("discover_dates_return_device_only_current", mode=mode, default_val=current_date)
                    return [{"label": "Device folders", "value": device_only_val}], current_date
                _tab_iso_debug("discover_dates_return_device_only_default", mode=mode, default_val=device_only_val)
                return [{"label": "Device folders", "value": device_only_val}], device_only_val

            _tab_iso_debug("discover_dates_return_empty", mode=mode)
            return [], None
        except Exception as e:
            _tab_iso_debug("discover_dates_error", mode=mode, error=str(e))
            return [], None

    @app.callback(
        Output("global-device-selector", "options"),
        Output("global-device-selector", "value"),
        Input("global-date-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("tab-filter-state-store", "data"),
        State("global-device-selector", "value"),
    )
    def discover_devices(selected_date, cfg, mode, label_data, verify_data, explore_data, tab_filter_state, global_device_value):
        if not selected_date:
            _tab_iso_debug("discover_devices_no_selected_date", mode=mode)
            return [], None

        # Skip discovery for flat structures
        if selected_date == "__flat__":
            _tab_iso_debug("discover_devices_skip_flat", mode=mode)
            return [], None

        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        configured_data_dir = _config_default_data_dir(cfg or {})
        tab_data_dir = tab_data.get("source_data_dir") if tab_data else None
        # Keep tab roots isolated: use this tab's loaded source first.
        data_dir = tab_data_dir or configured_data_dir
        _tab_iso_debug(
            "discover_devices_start",
            mode=mode,
            selected_date=selected_date,
            tab_data_dir=tab_data_dir,
            configured_data_dir=configured_data_dir,
            resolved_data_dir=data_dir,
            global_device_value=global_device_value,
        )
        if not data_dir:
            _tab_iso_debug("discover_devices_no_dir", mode=mode)
            return [], None

        tab_state = (tab_filter_state or {}).get(mode, {}) if isinstance(tab_filter_state, dict) else {}
        saved_device = tab_state.get("device") if isinstance(tab_state, dict) else None
        current_device = global_device_value
        
        try:
            devices = set()
            base_name = os.path.basename(data_dir.rstrip(os.sep))
            is_base_date = len(base_name) == 10 and base_name[4] == '-' and base_name[7] == '-'

            if selected_date == "__device_only__" or (is_base_date and selected_date in {base_name, "__all__"}):
                devices = {d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))}
            # If "All Dates" is selected, find all devices across all dates
            elif selected_date == "__all__":
                for date_folder in os.listdir(data_dir):
                    date_path = os.path.join(data_dir, date_folder)
                    # Check for date-like folder (YYYY-MM-DD format)
                    if os.path.isdir(date_path) and len(date_folder) == 10 and date_folder[4] == '-':
                        for d in os.listdir(date_path):
                            if os.path.isdir(os.path.join(date_path, d)):
                                devices.add(d)
            else:
                # Single date selected
                date_path = os.path.join(data_dir, selected_date)
                if os.path.exists(date_path):
                    devices = {d for d in os.listdir(date_path) if os.path.isdir(os.path.join(date_path, d))}

            devices = sorted(devices)
            
            # Add "All Devices" option at the beginning
            options = [{"label": "All Devices", "value": "__all__"}] + [
                {"label": d, "value": d} for d in devices
            ]
            option_values = {"__all__", *devices}
            default_val = devices[0] if devices else None
            
            # Apply config defaults only for Verify mode.
            config_dev = None
            if mode == "verify" and isinstance(cfg, dict):
                verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
                config_dev = verify_cfg.get("hydrophone")
            if saved_device in option_values:
                default_val = saved_device
            elif current_device in option_values:
                default_val = current_device
            elif config_dev in devices:
                default_val = config_dev

            _tab_iso_debug(
                "discover_devices_return",
                mode=mode,
                selected_date=selected_date,
                devices_count=len(devices),
                default_val=default_val,
                saved_device=saved_device,
                current_device=current_device,
                config_dev=config_dev,
            )
            return options, default_val
        except Exception as e:
            _tab_iso_debug("discover_devices_error", mode=mode, selected_date=selected_date, error=str(e))
            return [], None

    @app.callback(
        Output("global-active-selection", "children"),
        Output("global-data-dir-display", "children", allow_duplicate=True),
        Input("label-data-store", "data"),
        Input("verify-data-store", "data"),
        Input("explore-data-store", "data"),
        Input("mode-tabs", "data"),
        Input("config-store", "data"),
        prevent_initial_call=True,
    )
    def update_active_selection_display(label_data, verify_data, explore_data, mode, cfg):
        # Select the appropriate data store based on mode
        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}

        # Show the current tab's data directory
        configured_data_dir = _config_default_data_dir(cfg or {})
        data_dir = (data.get("source_data_dir") if data else None) or configured_data_dir
        data_dir_display = data_dir or "Not selected"
        _tab_iso_debug(
            "active_selection_display",
            mode=mode,
            data_dir_display=data_dir_display,
            selected_snapshot=_tab_data_snapshot(data),
        )

        if not data:
            return "No data loaded", data_dir_display

        summary = data.get("summary", {})
        date_str = summary.get("active_date")
        device = summary.get("active_hydrophone")

        if date_str and device:
            return f"{date_str} / {device}", data_dir_display
        return "Not selected", data_dir_display

    app.clientside_callback(
        """
        function(is_open) {
            if (is_open === false || is_open === null) {
                document.querySelectorAll('audio[id$="-audio"]').forEach(function(audio) {
                    audio.pause();
                });
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("dummy-output", "data", allow_duplicate=True),
        Input("image-modal", "is_open"),
        prevent_initial_call=True
    )
