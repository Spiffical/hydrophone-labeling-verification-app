"""Orchestration entrypoint for verify decision callbacks."""

from app.callbacks.verify.badge_callbacks import register_verify_badge_callbacks
from app.callbacks.verify.confirm_callbacks import register_verify_confirm_callbacks


def register_verify_action_callbacks(
    app,
    *,
    _require_complete_profile,
    _filter_predictions,
    _clean_annotation_extent,
    _extract_label_extent_list_map_from_boxes,
    _extract_label_extent_map_from_boxes,
    _get_modal_label_sets,
    _parse_verify_target,
    _profile_actor,
    _update_item_labels,
    _build_modal_boxes_from_item,
    _modal_snapshot_payload,
    _get_item_rejected_labels,
    _item_action_key,
    _ordered_unique_labels,
    _verify_badge_debug,
):
    """Register verify confirm/save and quick badge action callbacks."""
    register_verify_confirm_callbacks(
        app,
        _require_complete_profile=_require_complete_profile,
        _filter_predictions=_filter_predictions,
        _clean_annotation_extent=_clean_annotation_extent,
        _extract_label_extent_list_map_from_boxes=_extract_label_extent_list_map_from_boxes,
        _extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
        _get_modal_label_sets=_get_modal_label_sets,
        _profile_actor=_profile_actor,
        _update_item_labels=_update_item_labels,
        _build_modal_boxes_from_item=_build_modal_boxes_from_item,
        _modal_snapshot_payload=_modal_snapshot_payload,
    )
    register_verify_badge_callbacks(
        app,
        _require_complete_profile=_require_complete_profile,
        _filter_predictions=_filter_predictions,
        _clean_annotation_extent=_clean_annotation_extent,
        _extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
        _get_modal_label_sets=_get_modal_label_sets,
        _parse_verify_target=_parse_verify_target,
        _profile_actor=_profile_actor,
        _build_modal_boxes_from_item=_build_modal_boxes_from_item,
        _get_item_rejected_labels=_get_item_rejected_labels,
        _item_action_key=_item_action_key,
        _ordered_unique_labels=_ordered_unique_labels,
        _verify_badge_debug=_verify_badge_debug,
    )

