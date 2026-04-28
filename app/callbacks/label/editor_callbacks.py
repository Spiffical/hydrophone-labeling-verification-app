"""Orchestrator for label editor callbacks."""

from app.callbacks.label.editor_modal_callbacks import (
    register_label_editor_modal_callbacks,
)
from app.callbacks.label.editor_save_callbacks import register_label_save_callbacks
from app.callbacks.label.note_callbacks import register_label_note_callbacks
from app.callbacks.label.editor_shell_callbacks import register_label_editor_shell_callbacks


def register_label_editor_callbacks(
    app,
    *,
    _create_folder_display,
    _get_mode_data,
    _require_complete_profile,
    _filter_predictions,
    create_hierarchical_selector,
    _extract_label_extent_map_from_boxes,
    _profile_actor,
    _update_item_labels,
    _update_item_notes,
    save_label_mode,
    _build_modal_boxes_from_item,
    _modal_snapshot_payload,
    _parse_verify_target,
    _get_modal_label_sets,
    _ordered_unique_labels,
    _clean_annotation_extent,
    _has_pending_label_edits,
    _stage_label_note_edit,
):
    register_label_editor_shell_callbacks(
        app,
        _create_folder_display=_create_folder_display,
    )

    register_label_editor_modal_callbacks(
        app,
        _get_mode_data=_get_mode_data,
        _require_complete_profile=_require_complete_profile,
        _filter_predictions=_filter_predictions,
        create_hierarchical_selector=create_hierarchical_selector,
        _extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
        _profile_actor=_profile_actor,
        _update_item_labels=_update_item_labels,
        _update_item_notes=_update_item_notes,
        save_label_mode=save_label_mode,
        _build_modal_boxes_from_item=_build_modal_boxes_from_item,
        _modal_snapshot_payload=_modal_snapshot_payload,
    )

    register_label_note_callbacks(
        app,
        _require_complete_profile=_require_complete_profile,
        _profile_actor=_profile_actor,
        _stage_label_note_edit=_stage_label_note_edit,
    )

    register_label_save_callbacks(
        app,
        _require_complete_profile=_require_complete_profile,
        _extract_label_extent_map_from_boxes=_extract_label_extent_map_from_boxes,
        _profile_actor=_profile_actor,
        _update_item_labels=_update_item_labels,
        _update_item_notes=_update_item_notes,
        save_label_mode=save_label_mode,
        _build_modal_boxes_from_item=_build_modal_boxes_from_item,
        _modal_snapshot_payload=_modal_snapshot_payload,
        _parse_verify_target=_parse_verify_target,
        _get_modal_label_sets=_get_modal_label_sets,
        _ordered_unique_labels=_ordered_unique_labels,
        _clean_annotation_extent=_clean_annotation_extent,
        _has_pending_label_edits=_has_pending_label_edits,
        _stage_label_note_edit=_stage_label_note_edit,
    )
