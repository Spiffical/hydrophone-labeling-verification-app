"""Modal bbox callbacks to sync modal edits back to label/verify item stores."""

from copy import deepcopy

from dash import Input, Output, State
from dash.exceptions import PreventUpdate


def register_modal_bbox_sync_callbacks(
    app,
    *,
    _require_complete_profile,
    _clean_annotation_extent,
    _ordered_unique_labels,
    _has_pending_label_edits,
    _extract_label_extent_map_from_boxes,
    _get_modal_label_sets,
    _profile_actor,
    _update_item_labels,
    _is_modal_dirty,
):
    @app.callback(
        Output("modal-item-store", "data", allow_duplicate=True),
        Input("modal-bbox-store", "data"),
        Input("modal-unsaved-store", "data"),
        State("mode-tabs", "data"),
        State("current-filename", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("verify-thresholds-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def sync_bbox_edits_to_modal_item(
        bbox_store,
        unsaved_store,
        mode,
        current_item_id,
        label_data,
        verify_data,
        thresholds,
        profile,
    ):
        """Mirror modal bbox edits into the active mode store so Save becomes available."""
        if mode not in {"label", "verify"}:
            raise PreventUpdate
        if not current_item_id:
            raise PreventUpdate
        if not isinstance(bbox_store, dict) or bbox_store.get("item_id") != current_item_id:
            raise PreventUpdate
        if not _is_modal_dirty(unsaved_store, current_item_id=current_item_id):
            raise PreventUpdate
        _require_complete_profile(profile, "sync_label_bbox_edits_to_item")

        data = deepcopy((label_data if mode == "label" else verify_data) or {})
        items = data.get("items") or []
        active_item = next(
            (
                item
                for item in items
                if isinstance(item, dict) and item.get("item_id") == current_item_id
            ),
            None,
        )
        if not isinstance(active_item, dict):
            raise PreventUpdate

        boxes = bbox_store.get("boxes")
        boxes = boxes if isinstance(boxes, list) else []
        next_label_extents = _extract_label_extent_map_from_boxes(boxes)
        existing_annotations = (
            active_item.get("annotations")
            if isinstance(active_item.get("annotations"), dict)
            else {}
        )
        existing_raw_extents = (
            existing_annotations.get("label_extents")
            if isinstance(existing_annotations, dict)
            else None
        )
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

        thresholds = thresholds or {"__global__": 0.5}
        _, _, active_labels = _get_modal_label_sets(active_item, mode, thresholds)
        active_labels = _ordered_unique_labels(active_labels)

        if mode == "label":
            if next_label_extents:
                merged_labels = list(active_labels)
                seen_labels = set(merged_labels)
                for extent_label in next_label_extents.keys():
                    if extent_label not in seen_labels:
                        merged_labels.append(extent_label)
                        seen_labels.add(extent_label)
                active_labels = merged_labels

            existing_labels = _ordered_unique_labels(existing_annotations.get("labels") or [])
            if (
                existing_labels == active_labels
                and existing_label_extents == next_label_extents
                and _has_pending_label_edits(existing_annotations)
            ):
                raise PreventUpdate
        else:
            # Ignore no-op updates so opening the modal does not trigger a fake dirty state.
            if existing_label_extents == next_label_extents:
                raise PreventUpdate

        profile_name = _profile_actor(profile)
        updated_data = _update_item_labels(
            data,
            current_item_id,
            active_labels,
            mode=mode,
            user_name=profile_name,
            label_extents=next_label_extents,
        )
        updated_modal_item = next(
            (
                item
                for item in (updated_data.get("items") or [])
                if isinstance(item, dict) and item.get("item_id") == current_item_id
            ),
            None,
        )
        return updated_modal_item
