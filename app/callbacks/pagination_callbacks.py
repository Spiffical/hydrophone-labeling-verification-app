"""Pagination callbacks for label mode."""
from copy import deepcopy
from datetime import datetime

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.utils.persistence import save_verify_predictions


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
    if extent_type == "time_freq_box":
        t0 = _safe_float(extent.get("time_start_sec"), None)
        t1 = _safe_float(extent.get("time_end_sec"), None)
        f0 = _safe_float(extent.get("freq_min_hz"), None)
        f1 = _safe_float(extent.get("freq_max_hz"), None)
        if None in (t0, t1, f0, f1):
            return None
        if t0 > t1:
            t0, t1 = t1, t0
        if f0 > f1:
            f0, f1 = f1, f0
        return {
            "type": "time_freq_box",
            "time_start_sec": round(t0, 3),
            "time_end_sec": round(t1, 3),
            "freq_min_hz": round(f0, 3),
            "freq_max_hz": round(f1, 3),
        }
    if extent_type == "time_range":
        t0 = _safe_float(extent.get("time_start_sec"), None)
        t1 = _safe_float(extent.get("time_end_sec"), None)
        if None in (t0, t1):
            return None
        if t0 > t1:
            t0, t1 = t1, t0
        return {
            "type": "time_range",
            "time_start_sec": round(t0, 3),
            "time_end_sec": round(t1, 3),
        }
    if extent_type == "freq_range":
        f0 = _safe_float(extent.get("freq_min_hz"), None)
        f1 = _safe_float(extent.get("freq_max_hz"), None)
        if None in (f0, f1):
            return None
        if f0 > f1:
            f0, f1 = f1, f0
        return {
            "type": "freq_range",
            "freq_min_hz": round(f0, 3),
            "freq_max_hz": round(f1, 3),
        }
    if extent_type == "clip":
        return {"type": "clip"}
    return None


def _filter_predictions(predictions, thresholds):
    if not isinstance(predictions, dict):
        return []
    thresholds = thresholds or {}
    global_threshold = float(thresholds.get("__global__", 0.5))
    filtered = []

    model_outputs = predictions.get("model_outputs")
    if isinstance(model_outputs, list):
        for out in model_outputs:
            if not isinstance(out, dict):
                continue
            label = out.get("class_hierarchy")
            score = _safe_float(out.get("score"), 0.0)
            if not isinstance(label, str) or not label.strip():
                continue
            label_threshold = float(thresholds.get(label, global_threshold))
            if score >= label_threshold:
                filtered.append(label.strip())
        return _ordered_unique_labels(filtered)

    confidence = predictions.get("confidence")
    if isinstance(confidence, dict):
        for label, score in confidence.items():
            if not isinstance(label, str):
                continue
            label_clean = label.strip()
            if not label_clean:
                continue
            label_threshold = float(thresholds.get(label_clean, global_threshold))
            if _safe_float(score, 0.0) >= label_threshold:
                filtered.append(label_clean)
        return _ordered_unique_labels(filtered)

    labels = predictions.get("labels")
    return _ordered_unique_labels(labels if isinstance(labels, list) else [])


def _has_pending_verify_changes(item):
    if not isinstance(item, dict):
        return False
    annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
    if annotations.get("pending_save"):
        return True
    if annotations.get("needs_reverify"):
        return True
    if annotations.get("verified"):
        return False
    # Backward-compatible fallback for edits made before pending_save existed.
    return bool(annotations.get("has_manual_review")) and bool(
        annotations.get("labels")
        or annotations.get("rejected_labels")
        or annotations.get("notes")
        or annotations.get("annotated_at")
        or annotations.get("annotated_by")
    )


def _any_pending_verify_changes(verify_data):
    items = (verify_data or {}).get("items")
    if not isinstance(items, list):
        return False
    return any(_has_pending_verify_changes(item) for item in items if isinstance(item, dict))


def _build_verification_payload(item, thresholds, profile_name):
    annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
    predictions = item.get("predictions") if isinstance(item.get("predictions"), dict) else {}
    threshold_used = float((thresholds or {}).get("__global__", 0.5))

    current_labels = _ordered_unique_labels(annotations.get("labels") or [])
    predicted_labels = _ordered_unique_labels(_filter_predictions(predictions, thresholds))
    predicted_set = set(predicted_labels)
    current_set = set(current_labels)

    model_extent_map = {}
    for model_out in predictions.get("model_outputs") or []:
        if not isinstance(model_out, dict):
            continue
        label = model_out.get("class_hierarchy")
        if not isinstance(label, str) or not label.strip():
            continue
        cleaned_extent = _clean_annotation_extent(model_out.get("annotation_extent"))
        if cleaned_extent:
            model_extent_map[label.strip()] = cleaned_extent

    annotation_extent_map = {}
    raw_extents = annotations.get("label_extents")
    if isinstance(raw_extents, dict):
        for label, extent in raw_extents.items():
            if not isinstance(label, str) or not label.strip():
                continue
            cleaned_extent = _clean_annotation_extent(extent)
            if cleaned_extent:
                annotation_extent_map[label.strip()] = cleaned_extent

    explicit_rejected = set(_ordered_unique_labels(annotations.get("rejected_labels") or []))
    rejected_labels = sorted((predicted_set - current_set) | explicit_rejected)

    label_decisions = []
    for label in current_labels:
        decision = "accepted" if label in predicted_set else "added"
        entry = {
            "label": label,
            "decision": decision,
            "threshold_used": threshold_used,
        }
        extent = annotation_extent_map.get(label) or model_extent_map.get(label)
        if extent:
            entry["annotation_extent"] = extent
        label_decisions.append(entry)

    for label in rejected_labels:
        if label in current_set:
            continue
        entry = {
            "label": label,
            "decision": "rejected",
            "threshold_used": threshold_used,
        }
        extent = model_extent_map.get(label) or annotation_extent_map.get(label)
        if extent:
            entry["annotation_extent"] = extent
        label_decisions.append(entry)

    verified_at = datetime.now().isoformat()
    verification = {
        "verified_at": verified_at,
        "verified_by": profile_name or "anonymous",
        "label_decisions": label_decisions,
        "verification_status": "verified",
        "notes": annotations.get("notes", "") if isinstance(annotations.get("notes"), str) else "",
    }
    return verification, current_labels, rejected_labels, verified_at


def _resolve_predictions_path(item, summary_predictions_file):
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        item_level = metadata.get("predictions_path")
        if isinstance(item_level, str) and item_level.strip():
            return item_level.strip()
    if isinstance(summary_predictions_file, str) and summary_predictions_file.strip().endswith(".json"):
        return summary_predictions_file.strip()
    return None


def _save_all_pending_verify_changes(verify_data, thresholds, profile):
    if not isinstance(verify_data, dict):
        return verify_data, 0
    updated_data = deepcopy(verify_data)
    items = updated_data.get("items")
    if not isinstance(items, list):
        return updated_data, 0

    summary = updated_data.get("summary") if isinstance(updated_data.get("summary"), dict) else {}
    summary_predictions_file = summary.get("predictions_file")
    profile_name = (profile or {}).get("name") if isinstance(profile, dict) else None
    saved_count = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        if not _has_pending_verify_changes(item):
            continue

        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            continue

        verification, labels, rejected_labels, verified_at = _build_verification_payload(
            item,
            thresholds,
            profile_name,
        )
        predictions_path = _resolve_predictions_path(item, summary_predictions_file)
        stored_verification = save_verify_predictions(predictions_path, item_id, verification)

        verifications = item.get("verifications")
        if not isinstance(verifications, list):
            verifications = []
        if isinstance(stored_verification, dict):
            verifications.append(stored_verification)
        item["verifications"] = verifications

        annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
        annotations["labels"] = labels
        annotations["rejected_labels"] = rejected_labels
        annotations["verified"] = True
        annotations["verified_at"] = verified_at
        annotations["verified_by"] = profile_name or "anonymous"
        annotations["needs_reverify"] = False
        annotations["pending_save"] = False
        annotations["has_manual_review"] = True
        annotations["annotated_at"] = verified_at
        if profile_name:
            annotations["annotated_by"] = profile_name
        item["annotations"] = annotations
        saved_count += 1

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
    updated_data["summary"] = summary
    return updated_data, saved_count


def _compute_target_page(triggered_id, current_page, goto_page, max_pages):
    current_page = current_page or 0
    max_pages = max_pages or 1
    if triggered_id == "verify-prev-page":
        return max(0, current_page - 1)
    if triggered_id == "verify-next-page":
        return min(max_pages - 1, current_page + 1)
    if triggered_id == "verify-goto-page" and goto_page:
        return max(0, min(int(goto_page) - 1, max_pages - 1))
    return current_page


def register_pagination_callbacks(app):
    """Register callbacks for pagination controls."""
    
    @app.callback(
        Output("label-current-page", "data"),
        Input("label-prev-page", "n_clicks"),
        Input("label-next-page", "n_clicks"),
        Input("label-goto-page", "n_clicks"),
        State("label-current-page", "data"),
        State("label-page-input", "value"),
        State("label-page-input", "max"),
        prevent_initial_call=True
    )
    def handle_pagination(prev_clicks, next_clicks, goto_clicks, current_page, goto_page, max_pages):
        """Handle pagination button clicks."""
        from dash import callback_context
        
        if not callback_context.triggered:
            raise PreventUpdate
        
        button_id = callback_context.triggered[0]["prop_id"].split(".")[0]
        current_page = current_page or 0
        max_pages = max_pages or 1
        
        if button_id == "label-prev-page":
            return max(0, current_page - 1)
        elif button_id == "label-next-page":
            return min(max_pages - 1, current_page + 1)
        elif button_id == "label-goto-page" and goto_page:
            # goto_page is 1-indexed, current_page is 0-indexed
            return max(0, min(int(goto_page) - 1, max_pages - 1))
        
        return current_page
    
    @app.callback(
        Output("label-page-input", "value"),
        Input("label-current-page", "data"),
    )
    def sync_page_input(current_page):
        """Sync page input with current page."""
        return (current_page or 0) + 1  # Convert 0-indexed to 1-indexed

    @app.callback(
        Output("verify-current-page", "data"),
        Output("verify-unsaved-page-modal", "is_open"),
        Output("verify-pending-page-store", "data"),
        Output("verify-data-store", "data", allow_duplicate=True),
        Input("verify-prev-page", "n_clicks"),
        Input("verify-next-page", "n_clicks"),
        Input("verify-goto-page", "n_clicks"),
        Input("verify-unsaved-page-stay", "n_clicks"),
        Input("verify-unsaved-page-save", "n_clicks"),
        State("verify-current-page", "data"),
        State("verify-page-input", "value"),
        State("verify-page-input", "max"),
        State("verify-pending-page-store", "data"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True
    )
    def handle_verify_pagination(
        prev_clicks,
        next_clicks,
        goto_clicks,
        stay_clicks,
        save_all_clicks,
        current_page,
        goto_page,
        max_pages,
        pending_page,
        verify_data,
        thresholds,
        profile,
    ):
        """Handle verify pagination, including unsaved-change guard + save-all."""
        triggered_id = ctx.triggered_id
        current_page = current_page or 0
        max_pages = max_pages or 1

        if triggered_id in {"verify-prev-page", "verify-next-page", "verify-goto-page"}:
            target_page = _compute_target_page(triggered_id, current_page, goto_page, max_pages)
            if target_page == current_page:
                raise PreventUpdate

            if _any_pending_verify_changes(verify_data):
                return no_update, True, target_page, no_update

            return target_page, False, None, no_update

        if triggered_id == "verify-unsaved-page-stay":
            if not stay_clicks:
                raise PreventUpdate
            return no_update, False, None, no_update

        if triggered_id == "verify-unsaved-page-save":
            if not save_all_clicks:
                raise PreventUpdate
            target_page = pending_page if isinstance(pending_page, int) else current_page
            target_page = max(0, min(max_pages - 1, target_page))
            updated_data, saved_count = _save_all_pending_verify_changes(verify_data, thresholds, profile)
            verify_data_update = updated_data if saved_count > 0 else no_update
            return target_page, False, None, verify_data_update

        raise PreventUpdate

    @app.callback(
        Output("verify-page-input", "value"),
        Input("verify-current-page", "data"),
    )
    def sync_verify_page_input(current_page):
        """Sync verify page input with current page."""
        return (current_page or 0) + 1

    @app.callback(
        Output("explore-current-page", "data"),
        Input("explore-prev-page", "n_clicks"),
        Input("explore-next-page", "n_clicks"),
        Input("explore-goto-page", "n_clicks"),
        State("explore-current-page", "data"),
        State("explore-page-input", "value"),
        State("explore-page-input", "max"),
        prevent_initial_call=True
    )
    def handle_explore_pagination(prev_clicks, next_clicks, goto_clicks, current_page, goto_page, max_pages):
        """Handle pagination button clicks in explore mode."""
        from dash import callback_context

        if not callback_context.triggered:
            raise PreventUpdate

        button_id = callback_context.triggered[0]["prop_id"].split(".")[0]
        current_page = current_page or 0
        max_pages = max_pages or 1

        if button_id == "explore-prev-page":
            return max(0, current_page - 1)
        elif button_id == "explore-next-page":
            return min(max_pages - 1, current_page + 1)
        elif button_id == "explore-goto-page" and goto_page:
            return max(0, min(int(goto_page) - 1, max_pages - 1))

        return current_page

    @app.callback(
        Output("explore-page-input", "value"),
        Input("explore-current-page", "data"),
    )
    def sync_explore_page_input(current_page):
        """Sync explore page input with current page."""
        return (current_page or 0) + 1
