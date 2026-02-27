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
            (
                item
                for item in items
                if isinstance(item, dict) and item.get("item_id") == current_item_id
            ),
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

        existing_annotations = (
            active_item.get("annotations")
            if isinstance(active_item.get("annotations"), dict)
            else {}
        )
        existing_labels = _ordered_unique_labels(existing_annotations.get("labels") or [])
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
            (
                item
                for item in items
                if isinstance(item, dict) and item.get("item_id") == current_item_id
            ),
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
