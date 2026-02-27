"""Orchestrator for modal bounding-box callbacks."""

from app.callbacks.modal.bbox_graph_callbacks import (
    register_modal_bbox_graph_callbacks,
)
from app.callbacks.modal.bbox_inline_delete_callbacks import (
    register_modal_bbox_inline_delete_callbacks,
)
from app.callbacks.modal.bbox_sync_callbacks import register_modal_bbox_sync_callbacks


def register_modal_bbox_callbacks(
    app,
    *,
    _apply_modal_boxes_to_figure,
    _require_complete_profile,
    _parse_active_box_target,
    _bbox_debug,
    _bbox_debug_box_summary,
    _axis_meta_from_figure,
    _safe_float,
    _shape_to_extent,
    _extent_to_shape,
    _clean_annotation_extent,
    _ordered_unique_labels,
    _has_pending_label_edits,
    _extract_label_extent_map_from_boxes,
    _get_modal_label_sets,
    _profile_actor,
    _update_item_labels,
    _is_modal_dirty,
    _BBOX_DELETE_TRACE_NAME,
):
    register_modal_bbox_graph_callbacks(
        app,
        _apply_modal_boxes_to_figure=_apply_modal_boxes_to_figure,
        _require_complete_profile=_require_complete_profile,
        _parse_active_box_target=_parse_active_box_target,
        _bbox_debug=_bbox_debug,
        _bbox_debug_box_summary=_bbox_debug_box_summary,
        _axis_meta_from_figure=_axis_meta_from_figure,
        _safe_float=_safe_float,
        _shape_to_extent=_shape_to_extent,
        _extent_to_shape=_extent_to_shape,
    )

    register_modal_bbox_inline_delete_callbacks(
        app,
        _apply_modal_boxes_to_figure=_apply_modal_boxes_to_figure,
        _require_complete_profile=_require_complete_profile,
        _bbox_debug=_bbox_debug,
        _bbox_debug_box_summary=_bbox_debug_box_summary,
        _BBOX_DELETE_TRACE_NAME=_BBOX_DELETE_TRACE_NAME,
    )

    register_modal_bbox_sync_callbacks(
        app,
        _require_complete_profile=_require_complete_profile,
        _clean_annotation_extent=_clean_annotation_extent,
        _ordered_unique_labels=_ordered_unique_labels,
        _has_pending_label_edits=_has_pending_label_edits,
        _extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
        _get_modal_label_sets=_get_modal_label_sets,
        _profile_actor=_profile_actor,
        _update_item_labels=_update_item_labels,
        _is_modal_dirty=_is_modal_dirty,
    )
