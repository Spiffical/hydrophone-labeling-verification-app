"""Modal bbox tag and editor callbacks."""

from copy import deepcopy
from datetime import datetime

from dash import ALL, ClientsideFunction, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.services.annotations import clean_box_tag


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
    if isinstance(value, list) and value:
        return _coerce_int(value[0])
    return None


def _safe_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_meta(box_index, box):
    source = box.get("source") or "manual"
    decision = box.get("decision") or "added"
    return f"Box {box_index + 1} | source: {source} | state: {decision}"


def _editor_values_for_box(box_index, box):
    extent = box.get("annotation_extent") if isinstance(box.get("annotation_extent"), dict) else {}
    return (
        True,
        box_index,
        box.get("label") or None,
        box.get("tag") or None,
        extent.get("time_start_sec"),
        extent.get("time_end_sec"),
        extent.get("freq_min_hz"),
        extent.get("freq_max_hz"),
        _format_meta(box_index, box),
        "",
    )


def _box_index_from_graph_click(click_data, figure, edit_trace_name):
    points = click_data.get("points") if isinstance(click_data, dict) else None
    point = points[0] if isinstance(points, list) and points and isinstance(points[0], dict) else None
    if not isinstance(point, dict):
        return None
    curve_number = _coerce_int(point.get("curveNumber"))
    if curve_number is None:
        return None
    fig_data = figure.get("data") if isinstance(figure, dict) else None
    if not isinstance(fig_data, list) or curve_number < 0 or curve_number >= len(fig_data):
        return None
    clicked_trace = fig_data[curve_number]
    if not isinstance(clicked_trace, dict) or clicked_trace.get("name") != edit_trace_name:
        return None
    return _coerce_int(point.get("customdata"))


def _normalize_extent(time_start, time_end, freq_min, freq_max):
    t0 = _safe_float(time_start)
    t1 = _safe_float(time_end)
    f0 = _safe_float(freq_min)
    f1 = _safe_float(freq_max)
    if None in (t0, t1, f0, f1):
        return None, "Enter all time and frequency limits."
    if t0 == t1:
        return None, "Start and end time must be different."
    if f0 == f1:
        return None, "Min and max frequency must be different."
    if t0 > t1:
        t0, t1 = t1, t0
    if f0 > f1:
        f0, f1 = f1, f0
    return (
        {
            "type": "time_freq_box",
            "time_start_sec": max(0.0, round(t0, 3)),
            "time_end_sec": max(0.0, round(t1, 3)),
            "freq_min_hz": max(0.0, round(f0, 3)),
            "freq_max_hz": max(0.0, round(f1, 3)),
        },
        "",
    )


def _has_box_for_label(boxes, label):
    target = (label or "").strip()
    if not target:
        return False
    return any(
        isinstance(box, dict) and (box.get("label") or "").strip() == target
        for box in boxes or []
    )


def update_modal_item_for_box_edit(
    modal_item,
    *,
    mode,
    thresholds,
    boxes,
    old_label,
    new_label,
    profile_name,
    get_modal_label_sets,
    get_item_rejected_labels,
    extract_label_extent_map_from_boxes,
    extract_box_annotations_from_boxes,
    ordered_unique_labels,
):
    """Apply bbox label edits to the modal item's label/rejection state."""
    if not isinstance(modal_item, dict) or mode == "explore":
        return None
    new_label = (new_label or "").strip()
    old_label = (old_label or "").strip()
    if not new_label:
        return None

    updated_item = deepcopy(modal_item)
    annotations = deepcopy(updated_item.get("annotations") or {})
    _, _, active_labels = get_modal_label_sets(
        updated_item,
        mode,
        thresholds or {"__global__": 0.5},
    )
    next_labels = ordered_unique_labels(active_labels)
    if new_label not in next_labels:
        next_labels.append(new_label)

    label_changed = bool(old_label and old_label != new_label)
    old_label_still_boxed = _has_box_for_label(boxes, old_label)
    if label_changed and not old_label_still_boxed:
        next_labels = [label for label in next_labels if label != old_label]

    label_extents = extract_label_extent_map_from_boxes(boxes)
    bbox_annotations = extract_box_annotations_from_boxes(boxes)
    annotations["labels"] = ordered_unique_labels(next_labels)
    annotations["label_extents"] = label_extents
    annotations["box_annotations"] = bbox_annotations
    annotations["annotated_at"] = datetime.now().isoformat()
    annotations["has_manual_review"] = True

    if mode == "verify":
        rejected = set(get_item_rejected_labels(updated_item))
        if label_changed and not old_label_still_boxed:
            rejected.add(old_label)
        rejected.discard(new_label)
        for label in annotations["labels"]:
            rejected.discard(label)
        annotations["rejected_labels"] = sorted(label for label in rejected if label)
        annotations["pending_save"] = True
        if annotations.get("verified"):
            annotations["needs_reverify"] = True
    elif mode == "label":
        annotations["pending_save"] = True

    if profile_name:
        annotations["annotated_by"] = profile_name

    updated_item["annotations"] = annotations
    return updated_item


def register_modal_bbox_editor_callbacks(
    app,
    *,
    _apply_modal_boxes_to_figure,
    _require_complete_profile,
    _BBOX_EDIT_TRACE_NAME,
    _build_modal_item_actions,
    _extract_label_extent_map_from_boxes,
    _extract_box_annotations_from_boxes,
    _get_modal_label_sets,
    _get_item_rejected_labels,
    _ordered_unique_labels,
    _profile_actor,
):
    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input({"type": "modal-bbox-tag-dropdown", "index": ALL}, "value"),
        State({"type": "modal-bbox-tag-dropdown", "index": ALL}, "id"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def update_modal_box_tag_from_list(
        tag_values,
        tag_ids,
        bbox_store,
        figure,
        current_item_id,
        mode,
        profile,
    ):
        if mode == "explore" or not current_item_id:
            raise PreventUpdate
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or triggered.get("type") != "modal-bbox-tag-dropdown":
            raise PreventUpdate
        _require_complete_profile(profile, "update_modal_box_tag_from_list")
        box_index = _coerce_int(triggered.get("index"))
        if box_index is None:
            raise PreventUpdate

        selected_value = None
        for idx, tag_id in enumerate(tag_ids or []):
            if isinstance(tag_id, dict) and _coerce_int(tag_id.get("index")) == box_index:
                selected_value = (tag_values or [None])[idx]
                break

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {}
        if store.get("item_id") != current_item_id:
            raise PreventUpdate
        boxes = deepcopy(store.get("boxes") or [])
        if box_index < 0 or box_index >= len(boxes) or not isinstance(boxes[box_index], dict):
            raise PreventUpdate

        next_tag = clean_box_tag(selected_value)
        current_tag = clean_box_tag(boxes[box_index].get("tag"))
        if next_tag == current_tag:
            raise PreventUpdate
        if next_tag:
            boxes[box_index]["tag"] = next_tag
        else:
            boxes[box_index].pop("tag", None)

        store["boxes"] = boxes
        updated_fig = _apply_modal_boxes_to_figure(
            deepcopy(figure) if isinstance(figure, dict) else {},
            boxes,
        )
        return store, updated_fig, {"dirty": True, "item_id": current_item_id}

    app.clientside_callback(
        ClientsideFunction(namespace="bboxInteractions", function_name="openEditor"),
        Output("bbox-editor-modal", "is_open", allow_duplicate=True),
        Output("bbox-editor-index-store", "data", allow_duplicate=True),
        Output("bbox-editor-label-dropdown", "value", allow_duplicate=True),
        Output("bbox-editor-tag-dropdown", "value", allow_duplicate=True),
        Output("bbox-editor-time-start-input", "value", allow_duplicate=True),
        Output("bbox-editor-time-end-input", "value", allow_duplicate=True),
        Output("bbox-editor-freq-min-input", "value", allow_duplicate=True),
        Output("bbox-editor-freq-max-input", "value", allow_duplicate=True),
        Output("bbox-editor-meta", "children", allow_duplicate=True),
        Output("bbox-editor-validation", "children", allow_duplicate=True),
        Input("modal-image-graph", "clickData"),
        Input({"type": "modal-bbox-edit-btn", "index": ALL}, "n_clicks"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("bbox-editor-modal", "is_open", allow_duplicate=True),
        Output("bbox-editor-validation", "children", allow_duplicate=True),
        Input("bbox-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_modal_box_editor(cancel_clicks):
        if not cancel_clicks:
            raise PreventUpdate
        return False, ""

    @app.callback(
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("bbox-editor-modal", "is_open", allow_duplicate=True),
        Output("bbox-editor-validation", "children", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-item-store", "data", allow_duplicate=True),
        Output("modal-item-actions", "children", allow_duplicate=True),
        Input("bbox-editor-apply", "n_clicks"),
        State("bbox-editor-index-store", "data"),
        State("bbox-editor-label-dropdown", "value"),
        State("bbox-editor-tag-dropdown", "value"),
        State("bbox-editor-time-start-input", "value"),
        State("bbox-editor-time-end-input", "value"),
        State("bbox-editor-freq-min-input", "value"),
        State("bbox-editor-freq-max-input", "value"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("modal-item-store", "data"),
        State("verify-thresholds-store", "data"),
        State("modal-active-box-label", "data"),
        State("config-store", "data"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def apply_modal_box_editor(
        apply_clicks,
        box_index,
        label,
        tag,
        time_start,
        time_end,
        freq_min,
        freq_max,
        bbox_store,
        figure,
        modal_item,
        thresholds,
        active_box_label,
        config,
        current_item_id,
        mode,
        profile,
    ):
        if not apply_clicks or mode == "explore" or not current_item_id:
            raise PreventUpdate
        _require_complete_profile(profile, "apply_modal_box_editor")
        box_index = _coerce_int(box_index)
        if box_index is None:
            raise PreventUpdate
        label = (label or "").strip()
        if not label:
            return no_update, no_update, True, "Choose a classification.", no_update, no_update, no_update
        extent, error = _normalize_extent(time_start, time_end, freq_min, freq_max)
        if error:
            return no_update, no_update, True, error, no_update, no_update, no_update

        store = deepcopy(bbox_store) if isinstance(bbox_store, dict) else {}
        if store.get("item_id") != current_item_id:
            raise PreventUpdate
        boxes = deepcopy(store.get("boxes") or [])
        if box_index < 0 or box_index >= len(boxes) or not isinstance(boxes[box_index], dict):
            raise PreventUpdate

        previous = boxes[box_index]
        old_label = (previous.get("label") or "").strip()
        label_changed = old_label != label
        extent_changed = previous.get("annotation_extent") != extent
        previous["label"] = label
        previous["annotation_extent"] = extent
        next_tag = clean_box_tag(tag)
        if next_tag:
            previous["tag"] = next_tag
        else:
            previous.pop("tag", None)
        if label_changed or extent_changed:
            previous["source"] = "manual"
            previous["decision"] = "added"
        boxes[box_index] = previous

        store["boxes"] = boxes
        updated_fig = _apply_modal_boxes_to_figure(
            deepcopy(figure) if isinstance(figure, dict) else {},
            boxes,
        )
        updated_item = update_modal_item_for_box_edit(
            modal_item,
            mode=mode,
            thresholds=thresholds,
            boxes=boxes,
            old_label=old_label,
            new_label=label,
            profile_name=_profile_actor(profile),
            get_modal_label_sets=_get_modal_label_sets,
            get_item_rejected_labels=_get_item_rejected_labels,
            extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
            extract_box_annotations_from_boxes=_extract_box_annotations_from_boxes,
            ordered_unique_labels=_ordered_unique_labels,
        )
        modal_actions = no_update
        if isinstance(updated_item, dict):
            modal_actions = _build_modal_item_actions(
                updated_item,
                mode,
                thresholds or {"__global__": 0.5},
                boxes=boxes,
                active_box_label=active_box_label,
                config=config,
            )
        else:
            updated_item = no_update
        return (
            store,
            updated_fig,
            False,
            "",
            {"dirty": True, "item_id": current_item_id},
            updated_item,
            modal_actions,
        )
