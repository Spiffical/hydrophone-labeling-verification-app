import os
import re
import time
import json
import logging
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


def _bbox_debug(event, **payload):
    if not _BBOX_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[BBOX_DEBUG] %s | %s", event, serialized)


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
            
            if mode == "verify":
                if is_reverification:
                    # User clicked Re-verify - mark as verified and clear the flag
                    annotations["verified"] = True
                    annotations["verified_at"] = datetime.now().isoformat()
                    annotations["needs_reverify"] = False
                else:
                    # User edited labels - if already verified, needs re-verification
                    if annotations.get("verified"):
                        annotations["needs_reverify"] = True
            
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


def _box_style(source, decision):
    if decision == "rejected":
        return {
            "line_color": "rgba(220, 53, 69, 0.95)",
            "line_dash": "dot",
            "fillcolor": "rgba(220, 53, 69, 0.18)",
        }
    if source == "model":
        return {
            "line_color": "rgba(13, 110, 253, 0.95)",
            "line_dash": "dash",
            "fillcolor": "rgba(13, 110, 253, 0.14)",
        }
    return {
        "line_color": "rgba(25, 135, 84, 0.95)",
        "line_dash": "solid",
        "fillcolor": "rgba(25, 135, 84, 0.18)",
    }


def _build_modal_boxes_from_item(item):
    if not isinstance(item, dict):
        return []

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
    annotations = item.get("annotations") or {}
    label_extents = annotations.get("label_extents") if isinstance(annotations, dict) else None
    if isinstance(label_extents, dict):
        fallback_boxes = []
        for label, extent in label_extents.items():
            cleaned = _clean_annotation_extent(extent)
            if not label or not cleaned or cleaned.get("type") == "clip":
                continue
            fallback_boxes.append(
                {
                    "label": label,
                    "annotation_extent": cleaned,
                    "source": "label",
                    "decision": "added",
                }
            )
        return fallback_boxes
    return []


def _apply_modal_boxes_to_figure(fig, boxes):
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
    for box_idx, box in enumerate(boxes or []):
        if not isinstance(box, dict):
            continue
        shape_base = _extent_to_shape(box.get("annotation_extent"), axis_meta)
        if not shape_base:
            continue
        style = _box_style(box.get("source"), box.get("decision"))
        shape_list.append(
            {
                "type": "rect",
                "x0": shape_base["x0"],
                "x1": shape_base["x1"],
                "y0": shape_base["y0"],
                "y1": shape_base["y1"],
                "line": {"color": style["line_color"], "width": 2, "dash": style["line_dash"]},
                "fillcolor": style["fillcolor"],
                "editable": True,
                "layer": "above",
            }
        )
        annotations.append(
            {
                "x": min(shape_base["x0"], shape_base["x1"]),
                "y": max(shape_base["y0"], shape_base["y1"]),
                "xref": "x",
                "yref": "y",
                "xanchor": "left",
                "yanchor": "bottom",
                "showarrow": False,
                "text": str(box.get("label") or "Unlabeled"),
                "font": {"size": 10, "color": style["line_color"]},
                "bgcolor": "rgba(255,255,255,0.55)",
                "borderpad": 2,
            }
        )

        # Inline delete handle in top-right corner of each box.
        x_corner = max(shape_base["x0"], shape_base["x1"])
        y_corner = max(shape_base["y0"], shape_base["y1"])
        x_handle = max(axis_meta.get("x_min", 0.0), min(axis_meta.get("x_max", 1.0), x_corner - 0.012 * x_span))
        y_handle = max(axis_meta.get("y_min", 0.0), min(axis_meta.get("y_max", 1.0), y_corner - 0.015 * y_span))
        delete_x.append(x_handle)
        delete_y.append(y_handle)
        delete_indices.append(box_idx)

    layout["shapes"] = shape_list
    layout["annotations"] = annotations
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
                "textfont": {"size": 11, "color": "#ffffff"},
                "marker": {
                    "size": 15,
                    "color": "rgba(220, 53, 69, 0.95)",
                    "line": {"color": "#ffffff", "width": 1},
                    "symbol": "square",
                },
                "hovertemplate": "Delete box<extra></extra>",
                "cliponaxis": False,
            }
        )
    fig["data"] = fig_data
    fig["layout"] = layout
    return fig


def _extract_label_extent_map_from_boxes(boxes):
    extent_map = {}
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        label = box.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        cleaned_extent = _clean_annotation_extent(box.get("annotation_extent"))
        if cleaned_extent:
            extent_map[label.strip()] = cleaned_extent
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


def _get_modal_label_sets(item, mode, thresholds):
    predictions = item.get("predictions") or {}
    annotations = item.get("annotations") or {}
    predicted_labels = _ordered_unique_labels(_filter_predictions(predictions, thresholds or {"__global__": 0.5}))
    verified_labels = _ordered_unique_labels(annotations.get("labels") or [])

    if mode == "verify":
        active_labels = verified_labels or predicted_labels
    else:
        active_labels = _ordered_unique_labels(verified_labels or predictions.get("labels") or [])

    return predicted_labels, verified_labels, active_labels


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
    is_verified = bool(annotations.get("verified"))
    needs_reverify = bool(annotations.get("needs_reverify"))

    rows = []
    for label in active_labels:
        has_box = _label_has_box(label, boxes)
        add_btn_color = "primary" if (active_box_label or "").strip() == label and not has_box else "outline-primary"
        add_icon_class = "fas fa-check" if has_box else "fas fa-vector-square"
        delete_button = dbc.Button(
            html.I(className="fas fa-trash"),
            id={"type": "modal-label-delete-btn", "label": label},
            color="outline-danger",
            size="sm",
            disabled=mode == "explore",
            className="modal-label-icon-btn modal-label-delete-btn",
            title=f"Delete label: {label}",
            n_clicks=0,
        )
        delete_action = (
            dcc.ConfirmDialogProvider(
                delete_button,
                id={"type": "modal-label-delete-confirm", "label": label},
                message=f"Delete label '{label}'?",
            )
            if mode != "explore"
            else delete_button
        )
        rows.append(
            html.Div(
                [
                    html.Span(label, className="modal-label-name"),
                    html.Div(
                        [
                            dbc.Button(
                                html.I(className=add_icon_class),
                                id={"type": "modal-label-add-box", "label": label},
                                color=add_btn_color,
                                size="sm",
                                disabled=(mode == "explore" or has_box),
                                className="modal-label-icon-btn modal-label-add-box-btn",
                                title=f"Add box for: {label}",
                                n_clicks=0,
                            ),
                            delete_action,
                        ],
                        className="modal-label-row-actions",
                    ),
                ],
                className="modal-label-row",
            )
        )

    action_buttons = []
    status_note = None

    if mode == "verify":
        if is_verified:
            status_note = "Verified" if not needs_reverify else "Verified, label edits require re-verification"
            action_buttons = [
                dbc.Button(
                    "Re-verify",
                    id={"type": "modal-action-confirm", "scope": "modal"},
                    color="success" if needs_reverify else "secondary",
                    size="sm",
                    disabled=not needs_reverify,
                    outline=not needs_reverify,
                    className="me-2",
                ),
                dbc.Button(
                    "Revise",
                    id={"type": "modal-action-edit", "scope": "modal"},
                    color="primary",
                    size="sm",
                ),
            ]
        else:
            status_note = "Unverified"
            action_buttons = [
                dbc.Button(
                    "Confirm",
                    id={"type": "modal-action-confirm", "scope": "modal"},
                    color="success",
                    size="sm",
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
        status_note = None
        action_buttons = [
            dbc.Button(
                "Add Label(s)",
                id={"type": "modal-action-edit", "scope": "modal"},
                color="primary",
                size="sm",
            ),
        ]
    else:
        status_note = "Explore mode is read-only."

    if mode == "verify":
        verify_meta = f"Predicted: {len(predicted_labels)} | Current: {len(active_labels)}"
        status_note = f"{verify_meta} | {status_note}" if status_note else verify_meta

    return html.Div(
        [
            html.Div("Labels", className="small fw-semibold text-muted mb-2"),
            html.Div(rows, className="modal-label-list") if rows else html.Div("No labels", className="text-muted small"),
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
        class_filter = class_filter or "all"
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
            if class_filter != "all" and class_filter not in predicted_labels:
                continue
            display_item = dict(item)
            display_predictions = dict(predictions)
            display_predictions["labels"] = predicted_labels
            display_item["predictions"] = display_predictions
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
        return {
            "timestamp": time.time(),
            "mode": active_mode,
            "source": "global-load",
            "config": cfg or {},
            "date_value": date_value,
            "device_value": device_value,
        }

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
        has_source = current_label_data and current_label_data.get("source_data_dir")

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

        if should_load:
            try:
                trigger_cfg = None
                requested_date = date_val
                requested_device = device_val
                if isinstance(config_load_trigger, dict) and "data-load-trigger-store" in triggered_props:
                    trigger_cfg = config_load_trigger.get("config")
                    requested_date = config_load_trigger.get("date_value", requested_date)
                    requested_device = config_load_trigger.get("device_value", requested_device)

                # The configured data root is authoritative across tabs.
                effective_cfg = trigger_cfg.copy() if trigger_cfg else (cfg.copy() if cfg else {})
                data_cfg = dict(effective_cfg.get("data", {}))
                current_source_data_dir = current_label_data.get("source_data_dir") if current_label_data else None
                active_data_dir = data_cfg.get("data_dir") or current_source_data_dir
                if active_data_dir:
                    data_cfg["data_dir"] = active_data_dir
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
                return data
            except Exception as e:
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

        # Only process if in verify mode
        if mode != "verify":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Verify data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in verify mode (already checked above)
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = current_verify_data and current_verify_data.get("source_data_dir")

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
                current_source_data_dir = current_verify_data.get("source_data_dir") if current_verify_data else None
                active_data_dir = data_cfg.get("data_dir") or current_source_data_dir
                if active_data_dir:
                    data_cfg["data_dir"] = active_data_dir
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
                return data
            except Exception as e:
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

        # Only process if in explore mode
        if mode != "explore":
            raise PreventUpdate

        # For date/device filter changes, only reload if:
        # 1. Explore data was ALREADY loaded (has source_data_dir), AND
        # 2. We're in explore mode (already checked above)
        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = current_explore_data and current_explore_data.get("source_data_dir")

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
                current_source_data_dir = current_explore_data.get("source_data_dir") if current_explore_data else None
                active_data_dir = data_cfg.get("data_dir") or current_source_data_dir
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
                return data
            except Exception as e:
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
        Input("verify-class-filter", "value"),
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
        class_filter = class_filter or "all"
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

            # Apply class filter - skip if a specific class is selected and item doesn't have it
            if class_filter != "all":
                if class_filter not in predicted_labels:
                    continue

            display_item = dict(item)
            display_predictions = dict(predictions)
            display_predictions["labels"] = predicted_labels
            display_item["predictions"] = display_predictions
            filtered_items.append(display_item)

        colormap = "hydrophone" if use_hydrophone_colormap else cfg.get("display", {}).get("colormap", "default")
        y_axis_scale = "log" if use_log_y_axis else cfg.get("display", {}).get("y_axis_scale", "linear")
        items_per_page = cfg.get("display", {}).get("items_per_page", 25)
        summary_block = html.Div([
            html.Span(f"Visible: {len(filtered_items)}", className="fw-semibold"),
            html.Span(f"Total: {summary.get('total_items', len(items))}", className="ms-3 text-muted"),
            html.Span(f"Verified: {summary.get('verified', 0)}", className="ms-3 text-muted"),
            html.Span(f"Threshold: {current_threshold*100:.0f}%", className="ms-3 text-muted"),
            html.Span(f"Filter: {class_filter}", className="ms-3 text-muted"),
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
        Output("verify-class-filter", "options"),
        Output("verify-class-filter", "value"),
        Input("verify-data-store", "data"),
        State("verify-class-filter", "value"),
        prevent_initial_call=False,
    )
    def update_verify_class_filter(data, current_value):
        items = (data or {}).get("items", [])
        classes = set()
        for item in items:
            predictions = item.get("predictions") or {}
            
            # Unified v2.x
            model_outputs = predictions.get("model_outputs")
            if model_outputs and isinstance(model_outputs, list):
                for out in model_outputs:
                    if out.get("class_hierarchy"):
                        classes.add(out.get("class_hierarchy"))
            
            # Legacy
            probs = predictions.get("confidence") or {}
            labels = predictions.get("labels") or []
            classes.update(list(probs.keys()) + list(labels))

        options = [{"label": "All classes", "value": "all"}] + [
            {"label": label, "value": label} for label in sorted(classes)
        ]
        if current_value and any(opt["value"] == current_value for opt in options):
            return options, current_value
        return options, "all"

    @app.callback(
        Output("verify-thresholds-store", "data"),
        Input("verify-threshold-slider", "value"),
        State("verify-class-filter", "value"),
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
        Input("verify-class-filter", "value"),
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
        prevent_initial_call=True,
    )
    def open_label_editor(n_clicks_list, modal_edit_clicks_list, cancel_clicks, click_store, edit_ids, modal_item_id, label_data, verify_data,
                          explore_data, active_item_id, thresholds, mode):
        # Select the appropriate data store based on mode
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        triggered = ctx.triggered_id
        if triggered == "label-editor-cancel":
            return False, no_update, None, click_store or {}
        if mode == "explore":
            return False, no_update, None, click_store or {}

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
        prevent_initial_call=True,
    )
    def save_label_editor(save_clicks, active_item_id, labels_list, labels_ids,
                          note_values, note_ids, label_data, verify_data, explore_data,
                          profile, mode, cfg, label_output_path, modal_bbox_store):
        if not save_clicks or not active_item_id:
            raise PreventUpdate
        if mode == "explore":
            return no_update, no_update, no_update, False, []

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

        profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
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

        if mode == "label":
            # Priority: user input > data summary > config
            labels_file = label_output_path or (data or {}).get("summary", {}).get("labels_file") or cfg.get("label", {}).get("output_file")
            save_label_mode(
                labels_file,
                active_item_id,
                selected_labels,
                annotated_by=profile_name,
                notes=note_text,
                label_extents=label_extents or None,
            )
        elif mode == "verify":
            # Verify mode persists only on Confirm/Re-verify.
            pass

        # Return updated data to the appropriate store, no_update for others
        if mode == "label":
            return updated, no_update, no_update, False, []
        elif mode == "verify":
            return no_update, updated, no_update, False, []
        else:
            return no_update, no_update, updated, False, []

    @app.callback(
        Output("verify-data-store", "data", allow_duplicate=True),
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
                labels_to_confirm = annotations.get("labels") or []
                if not labels_to_confirm:
                    labels_to_confirm = _filter_predictions(predictions, {"__global__": threshold_used})
                break

        box_extent_map = {}
        if isinstance(modal_bbox_store, dict) and modal_bbox_store.get("item_id") == item_id:
            box_extent_map = _extract_label_extent_map_from_boxes(modal_bbox_store.get("boxes") or [])

        if box_extent_map:
            ordered = list(labels_to_confirm or [])
            seen = set(ordered)
            for label in box_extent_map.keys():
                if label not in seen:
                    ordered.append(label)
                    seen.add(label)
            labels_to_confirm = ordered

        if not predictions_path:
            summary_pred = (data or {}).get("summary", {}).get("predictions_file")
            if isinstance(summary_pred, str) and summary_pred.endswith(".json"):
                predictions_path = summary_pred

        predicted_labels = _filter_predictions(predictions, {"__global__": threshold_used})
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

        added_labels = {label for label in labels_set if label not in predicted_set}

        label_decisions = []
        for label in labels_to_confirm:
            if label in predicted_set:
                decision = "accepted"
            else:
                decision = "added"
            entry = {
                "label": label,
                "decision": decision,
                "threshold_used": float(last_add_threshold.get(label, threshold_used)),
            }
            extent = box_extent_map.get(label) or model_extent_map.get(label)
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)
        for label in sorted(rejected_labels - labels_set):
            entry = {
                "label": label,
                "decision": "rejected",
                "threshold_used": float(last_remove_threshold.get(label, threshold_used)),
            }
            extent = model_extent_map.get(label) or box_extent_map.get(label)
            if extent:
                entry["annotation_extent"] = extent
            label_decisions.append(entry)

        profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
        note_text = annotations.get("notes", "") if isinstance(annotations, dict) else ""
        verification = {
            "verified_at": datetime.now().isoformat(),
            "verified_by": profile_name or "anonymous",
            "labels": labels_to_confirm,
            "threshold_used": threshold_used,
            "rejected_labels": sorted(rejected_labels),
            "added_labels": sorted(added_labels),
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
        return updated

    @app.callback(
        Output("profile-modal", "is_open"),
        Output("profile-name", "value"),
        Output("profile-email", "value"),
        Input("profile-btn", "n_clicks"),
        Input("profile-cancel", "n_clicks"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_profile_modal(open_clicks, cancel_clicks, profile):
        triggered = ctx.triggered_id
        if triggered == "profile-btn":
            profile = profile or {}
            return True, profile.get("name", ""), profile.get("email", "")
        if triggered == "profile-cancel":
            return False, no_update, no_update
        raise PreventUpdate

    @app.callback(
        Output("user-profile-store", "data"),
        Output("profile-modal", "is_open", allow_duplicate=True),
        Input("profile-save", "n_clicks"),
        State("profile-name", "value"),
        State("profile-email", "value"),
        prevent_initial_call=True,
    )
    def save_profile(n_clicks, name, email):
        if not n_clicks:
            raise PreventUpdate
        return {"name": name or "", "email": email or ""}, False

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
        Input({"type": "spectrogram-image", "item_id": ALL}, "n_clicks"),
        Input("modal-nav-prev", "n_clicks"),
        Input("modal-nav-next", "n_clicks"),
        Input("close-modal", "n_clicks"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("mode-tabs", "data"),
        State("verify-thresholds-store", "data"),
        State("verify-class-filter", "value"),
        State("modal-audio-settings-store", "data"),
        State("current-filename", "data"),
        State("modal-colormap-toggle", "value"),
        State("modal-y-axis-toggle", "value"),
        prevent_initial_call=True,
    )
    def handle_modal_trigger(
        image_clicks_list,
        prev_clicks,
        next_clicks,
        close_clicks,
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
    ):
        mode = mode or "label"
        data = _get_mode_data(mode, label_data, verify_data, explore_data)
        triggered = ctx.triggered_id
        if triggered == "close-modal":
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
            )

        page_items = _get_modal_navigation_items(
            mode,
            label_data,
            verify_data,
            explore_data,
            thresholds,
            class_filter,
        )
        page_item_ids = [item.get("item_id") for item in page_items if item and item.get("item_id")]

        item_id = None
        if isinstance(triggered, dict) and triggered.get("type") == "spectrogram-image":
            if not any(image_clicks_list):
                raise PreventUpdate
            item_id = triggered.get("item_id")
        elif triggered in {"modal-nav-prev", "modal-nav-next"}:
            if not current_item_id or not page_item_ids:
                raise PreventUpdate
            if current_item_id not in page_item_ids:
                item_id = page_item_ids[0]
            else:
                current_index = page_item_ids.index(current_item_id)
                if triggered == "modal-nav-prev":
                    item_id = page_item_ids[max(0, current_index - 1)]
                else:
                    item_id = page_item_ids[min(len(page_item_ids) - 1, current_index + 1)]
        else:
            raise PreventUpdate

        if not item_id:
            raise PreventUpdate

        active_item = next((i for i in page_items if i.get("item_id") == item_id), None)
        if not active_item:
            items = (data or {}).get("items", [])
            active_item = next((i for i in items if i.get("item_id") == item_id), None)
        if not active_item:
            raise PreventUpdate

        mat_path = active_item.get("mat_path")
        spectrogram = load_spectrogram_cached(mat_path)
        fig = create_spectrogram_figure(spectrogram, colormap, y_axis_scale)
        modal_boxes = _build_modal_boxes_from_item(active_item)
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

        audio_path = active_item.get("audio_path")
        modal_audio = create_modal_audio_player(
            audio_path,
            item_id,
            player_id="modal-player",
            pitch_value=pitch_value,
            eq_values=eq_values,
            gain_value=gain_value,
        ) if audio_path else html.P("No audio available for this segment.", className="text-muted italic")

        modal_actions = _build_modal_item_actions(
            active_item,
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
        prevent_initial_call=True,
    )
    def set_modal_active_box_label(add_box_clicks, figure):
        if not add_box_clicks or all((clicks or 0) <= 0 for clicks in add_box_clicks):
            raise PreventUpdate
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        label = (triggered.get("label") or "").strip()
        if not label:
            raise PreventUpdate

        if not isinstance(figure, dict):
            return label, no_update

        updated_figure = deepcopy(figure)
        layout = updated_figure.get("layout")
        if not isinstance(layout, dict):
            layout = {}
        layout["dragmode"] = "drawrect"
        updated_figure["layout"] = layout
        return label, updated_figure

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Output("verify-data-store", "data", allow_duplicate=True),
        Output("explore-data-store", "data", allow_duplicate=True),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
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
        State("config-store", "data"),
        State("label-output-input", "value"),
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
        cfg,
        label_output_path,
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

        data = deepcopy(_get_mode_data(mode, label_data, verify_data, explore_data))
        if not data:
            raise PreventUpdate

        items = data.get("items", [])
        active_item = next((item for item in items if item and item.get("item_id") == current_item_id), None)
        if not active_item:
            raise PreventUpdate

        _, _, active_labels = _get_modal_label_sets(active_item, mode, thresholds or {"__global__": 0.5})
        if label_to_delete not in active_labels:
            raise PreventUpdate
        updated_labels = [label for label in active_labels if label != label_to_delete]

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {"item_id": current_item_id, "boxes": []}
        existing_boxes = store.get("boxes") if isinstance(store.get("boxes"), list) else []
        filtered_boxes = [
            box for box in existing_boxes
            if (box.get("label") if isinstance(box, dict) else None) != label_to_delete
        ]
        store["item_id"] = current_item_id
        store["boxes"] = filtered_boxes

        profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
        label_extents = _extract_label_extent_map_from_boxes(filtered_boxes)
        updated_data = _update_item_labels(
            data,
            current_item_id,
            updated_labels,
            mode,
            user_name=profile_name,
            label_extents=label_extents or None,
        )

        if mode == "label":
            updated_item = next(
                (item for item in (updated_data or {}).get("items", []) if item and item.get("item_id") == current_item_id),
                None,
            )
            note_text = ((updated_item or {}).get("annotations") or {}).get("notes", "")
            labels_file = (
                label_output_path
                or (updated_data or {}).get("summary", {}).get("labels_file")
                or (cfg or {}).get("label", {}).get("output_file")
            )
            save_label_mode(
                labels_file,
                current_item_id,
                updated_labels,
                annotated_by=profile_name,
                notes=note_text,
                label_extents=label_extents or None,
            )

        updated_fig = _apply_modal_boxes_to_figure(deepcopy(figure) if isinstance(figure, dict) else {}, filtered_boxes)
        next_active_label = None

        if mode == "label":
            return updated_data, no_update, no_update, store, updated_fig, next_active_label
        if mode == "verify":
            return no_update, updated_data, no_update, store, updated_fig, next_active_label
        return no_update, no_update, updated_data, store, updated_fig, next_active_label

    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Input("modal-image-graph", "relayoutData"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("modal-active-box-label", "data"),
        State("current-filename", "data"),
        prevent_initial_call=True,
    )
    def update_modal_boxes_from_graph(relayout_data, bbox_store, figure, active_box_label, current_item_id):
        if not current_item_id or not relayout_data:
            raise PreventUpdate

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {}
        if store.get("item_id") != current_item_id:
            store = {"item_id": current_item_id, "boxes": []}
        boxes = deepcopy(store.get("boxes") or [])
        axis_meta = _axis_meta_from_figure(figure if isinstance(figure, dict) else {})

        chosen_label = (active_box_label or "").strip()
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
        _bbox_debug(
            "mode_decision",
            is_add_mode=is_add_mode,
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
                    and not any((existing.get("label") or "").strip() == chosen_label for existing in boxes)
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
                        and not any((existing.get("label") or "").strip() == chosen_label for existing in boxes)
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
        updated_fig = _apply_modal_boxes_to_figure(deepcopy(figure) if isinstance(figure, dict) else {}, boxes)
        if force_resync and not updated:
            _bbox_debug("return_resync_only", boxes_after=_bbox_debug_box_summary(boxes))
        _bbox_debug(
            "return_update",
            clear_active_label=clear_active_label,
            boxes_after=_bbox_debug_box_summary(boxes),
        )
        return store, updated_fig, (None if clear_active_label else no_update)

    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Input("modal-image-graph", "clickData"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("current-filename", "data"),
        prevent_initial_call=True,
    )
    def delete_modal_box_from_graph_click(click_data, bbox_store, figure, current_item_id):
        if not current_item_id:
            raise PreventUpdate

        points = click_data.get("points") if isinstance(click_data, dict) else None
        point = points[0] if isinstance(points, list) and points and isinstance(points[0], dict) else None
        curve_number = point.get("curveNumber") if isinstance(point, dict) else None
        custom_data = point.get("customdata") if isinstance(point, dict) else None
        _bbox_debug(
            "inline_delete_start",
            triggered=ctx.triggered_id,
            current_item_id=current_item_id,
            click_data=click_data,
            curve_number=curve_number,
            custom_data=custom_data,
        )
        if not isinstance(curve_number, int):
            raise PreventUpdate

        fig_data = figure.get("data") if isinstance(figure, dict) else None
        if not isinstance(fig_data, list) or curve_number < 0 or curve_number >= len(fig_data):
            raise PreventUpdate
        clicked_trace = fig_data[curve_number]
        if not isinstance(clicked_trace, dict) or clicked_trace.get("name") != _BBOX_DELETE_TRACE_NAME:
            raise PreventUpdate

        box_index = None
        if isinstance(custom_data, (int, float)):
            box_index = int(custom_data)
        elif isinstance(custom_data, list) and custom_data:
            first_val = custom_data[0]
            if isinstance(first_val, (int, float)):
                box_index = int(first_val)
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
            updated_fig = _apply_modal_boxes_to_figure(deepcopy(figure) if isinstance(figure, dict) else {}, boxes)
            return store, updated_fig, no_update

        _bbox_debug("inline_delete_remove_index", box_index=box_index, box=boxes[box_index])
        boxes.pop(box_index)

        store["item_id"] = current_item_id
        store["boxes"] = boxes
        updated_fig = _apply_modal_boxes_to_figure(deepcopy(figure) if isinstance(figure, dict) else {}, boxes)
        _bbox_debug("inline_delete_return", boxes_after=_bbox_debug_box_summary(boxes))
        return store, updated_fig, no_update

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
        Output("global-date-selector", "options", allow_duplicate=True),
        Output("global-date-selector", "value", allow_duplicate=True),
        Input("mode-tabs", "data"),
        State("config-store", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def discover_dates(mode, cfg, label_data, verify_data, explore_data):
        # Prefer the configured data root so root changes persist across tab switches.
        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        configured_data_dir = cfg.get("data", {}).get("data_dir") or cfg.get("verify", {}).get("dashboard_root")
        tab_data_dir = tab_data.get("source_data_dir") if tab_data else None
        data_dir = configured_data_dir or tab_data_dir
        if not data_dir or not os.path.exists(data_dir):
            return [], None

        # Dates are folders like YYYY-MM-DD
        try:
            base_name = os.path.basename(data_dir.rstrip(os.sep))
            if len(base_name) == 10 and base_name[4] == '-' and base_name[7] == '-':
                return [{"label": base_name, "value": base_name}], base_name

            dates = [d for d in os.listdir(data_dir) if len(d) == 10 and os.path.isdir(os.path.join(data_dir, d))]
            dates.sort(reverse=True)

            options = [{"label": "All Dates", "value": "__all__"}] + [
                {"label": d, "value": d} for d in dates
            ]
            default_val = dates[0] if dates else None

            # Override with config if present
            config_date = cfg.get("verify", {}).get("date")
            if config_date in dates:
                default_val = config_date

            if dates:
                return options, default_val

            # Device-only root (no date folders) - keep date selector meaningful
            devices = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
            if devices:
                return [{"label": "Device folders", "value": "__device_only__"}], "__device_only__"

            return [], None
        except Exception:
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
    )
    def discover_devices(selected_date, cfg, mode, label_data, verify_data, explore_data):
        if not selected_date:
            return [], None

        # Skip discovery for flat structures
        if selected_date == "__flat__":
            return [], None

        # Prefer the configured data root so root changes persist across tab switches.
        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        configured_data_dir = cfg.get("data", {}).get("data_dir") or cfg.get("verify", {}).get("dashboard_root")
        tab_data_dir = tab_data.get("source_data_dir") if tab_data else None
        data_dir = configured_data_dir or tab_data_dir
        if not data_dir:
            return [], None
        
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
            default_val = devices[0] if devices else None
            
            # Override with config if present
            config_dev = cfg.get("verify", {}).get("hydrophone")
            if config_dev in devices:
                default_val = config_dev
                
            return options, default_val
        except Exception:
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
        configured_data_dir = cfg.get("data", {}).get("data_dir") if isinstance(cfg, dict) else None
        data_dir = configured_data_dir or (data.get("source_data_dir") if data else None)
        data_dir_display = data_dir or "Not selected"

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
