"""Helper functions for modal bbox graph relayout processing."""

import re


def shape_signature(raw_shape, *, safe_float):
    if not isinstance(raw_shape, dict):
        return None
    x0 = safe_float(raw_shape.get("x0"), None)
    x1 = safe_float(raw_shape.get("x1"), None)
    y0 = safe_float(raw_shape.get("y0"), None)
    y1 = safe_float(raw_shape.get("y1"), None)
    if None in (x0, x1, y0, y1):
        return None
    return (
        round(min(x0, x1), 6),
        round(max(x0, x1), 6),
        round(min(y0, y1), 6),
        round(max(y0, y1), 6),
    )


def box_signature(box, *, axis_meta, extent_to_shape, safe_float):
    if not isinstance(box, dict):
        return None
    shape = extent_to_shape(box.get("annotation_extent"), axis_meta)
    return shape_signature(shape, safe_float=safe_float) if shape else None


def resolve_add_mode(*, boxes, chosen_label, allow_existing_label):
    existing_labels = [
        (box.get("label") or "").strip() for box in boxes if isinstance(box, dict)
    ]
    is_add_mode = bool(chosen_label) and (
        allow_existing_label or chosen_label not in existing_labels
    )
    return is_add_mode, existing_labels


def filter_payload_shapes(relayout_data):
    if not isinstance(relayout_data.get("shapes"), list):
        return None
    return [
        shape
        for shape in relayout_data.get("shapes", [])
        if isinstance(shape, dict) and shape.get("type") == "rect"
    ]


def process_payload_shapes(
    *,
    payload_shapes,
    boxes,
    is_add_mode,
    chosen_label,
    axis_meta,
    safe_float,
    shape_to_extent,
    extent_to_shape,
    bbox_debug,
):
    updated = False
    force_resync = False
    clear_active_label = False

    if payload_shapes is None:
        return boxes, updated, force_resync, clear_active_label

    bbox_debug(
        "payload_shapes_filtered",
        payload_count=len(payload_shapes),
        payload_signatures=[shape_signature(shape, safe_float=safe_float) for shape in payload_shapes],
    )

    if is_add_mode and chosen_label:
        existing_signatures = {
            box_signature(
                box,
                axis_meta=axis_meta,
                extent_to_shape=extent_to_shape,
                safe_float=safe_float,
            )
            for box in boxes
        }
        existing_signatures.discard(None)
        new_shape = None
        for shape in payload_shapes:
            sig = shape_signature(shape, safe_float=safe_float)
            if sig and sig not in existing_signatures:
                new_shape = shape
                bbox_debug("add_mode_new_shape_candidate", signature=sig, shape=shape)
                break
        if new_shape is not None:
            extent = shape_to_extent(new_shape, axis_meta)
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
                bbox_debug(
                    "add_mode_append_from_payload",
                    chosen_label=chosen_label,
                    extent=extent,
                )

    if not is_add_mode:
        payload_counts = {}
        for shape in payload_shapes:
            sig = shape_signature(shape, safe_float=safe_float)
            if not sig:
                continue
            payload_counts[sig] = payload_counts.get(sig, 0) + 1

        keep_counts = {}
        delete_indices = []
        for idx, box in enumerate(boxes):
            sig = box_signature(
                box,
                axis_meta=axis_meta,
                extent_to_shape=extent_to_shape,
                safe_float=safe_float,
            )
            if not sig:
                continue
            used = keep_counts.get(sig, 0)
            allowed = payload_counts.get(sig, 0)
            if used < allowed:
                keep_counts[sig] = used + 1
            else:
                delete_indices.append(idx)

        for idx in reversed(delete_indices):
            if 0 <= idx < len(boxes):
                bbox_debug("delete_index", index=idx, box=boxes[idx])
                boxes.pop(idx)
                updated = True

        if len(payload_shapes) > len(boxes):
            force_resync = True
            bbox_debug(
                "stale_payload_shape_count_mismatch",
                payload_count=len(payload_shapes),
                box_count=len(boxes),
            )

    return boxes, updated, force_resync, clear_active_label


def extract_coord_updates(*, relayout_data, safe_float):
    coord_updates = {}
    for key, value in relayout_data.items():
        match = re.match(r"shapes\[(\d+)\]\.(x0|x1|y0|y1)", str(key))
        if not match:
            continue
        raw_idx = int(match.group(1))
        coord = match.group(2)
        if raw_idx <= 0:
            continue
        idx = raw_idx - 1
        coord_updates.setdefault(idx, {})[coord] = safe_float(value, None)
    return coord_updates


def process_coord_updates(
    *,
    coord_updates,
    boxes,
    is_add_mode,
    chosen_label,
    axis_meta,
    extent_to_shape,
    shape_to_extent,
    bbox_debug,
):
    updated = False
    force_resync = False
    clear_active_label = False

    for box_idx, updates in coord_updates.items():
        if box_idx < 0:
            continue
        bbox_debug(
            "coord_update",
            box_idx=box_idx,
            updates=updates,
            is_add_mode=is_add_mode,
        )

        if is_add_mode:
            if box_idx < len(boxes):
                continue
            if not chosen_label:
                continue
            if all(updates.get(k) is not None for k in ("x0", "x1", "y0", "y1")):
                extent = shape_to_extent({"type": "rect", **updates}, axis_meta)
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
                    bbox_debug(
                        "add_mode_append_from_coords",
                        chosen_label=chosen_label,
                        extent=extent,
                    )
            continue

        if box_idx < len(boxes):
            shape = extent_to_shape(boxes[box_idx].get("annotation_extent"), axis_meta) or {
                "type": "rect"
            }
            for axis_key in ("x0", "x1", "y0", "y1"):
                if updates.get(axis_key) is not None:
                    shape[axis_key] = updates[axis_key]
            extent = shape_to_extent(shape, axis_meta)
            if (
                extent
                and extent.get("type") != "clip"
                and extent != boxes[box_idx].get("annotation_extent")
            ):
                bbox_debug(
                    "update_existing_box_extent",
                    box_idx=box_idx,
                    old_extent=boxes[box_idx].get("annotation_extent"),
                    new_extent=extent,
                )
                boxes[box_idx]["annotation_extent"] = extent
                updated = True
        else:
            force_resync = True
            bbox_debug(
                "stale_coord_without_box",
                box_idx=box_idx,
                total_boxes=len(boxes),
                updates=updates,
            )

    return boxes, updated, force_resync, clear_active_label
