"""Orchestrator for modal lifecycle callbacks."""

from app.callbacks.modal.lifecycle_navigation_callbacks import (
    register_modal_lifecycle_navigation_callbacks,
)
from app.callbacks.modal.lifecycle_unsaved_callbacks import (
    register_modal_lifecycle_unsaved_callbacks,
)


def register_modal_lifecycle_callbacks(
    app,
    *,
    _get_mode_data,
    _get_modal_navigation_items,
    _is_modal_dirty,
    _modal_snapshot_payload,
    _build_modal_boxes_from_item,
    _apply_modal_boxes_to_figure,
    _build_modal_item_actions,
    _persist_modal_item_before_exit,
    _replace_item_in_data,
):
    register_modal_lifecycle_navigation_callbacks(
        app,
        _get_mode_data=_get_mode_data,
        _get_modal_navigation_items=_get_modal_navigation_items,
        _is_modal_dirty=_is_modal_dirty,
        _modal_snapshot_payload=_modal_snapshot_payload,
        _build_modal_boxes_from_item=_build_modal_boxes_from_item,
        _apply_modal_boxes_to_figure=_apply_modal_boxes_to_figure,
        _build_modal_item_actions=_build_modal_item_actions,
    )

    register_modal_lifecycle_unsaved_callbacks(
        app,
        _persist_modal_item_before_exit=_persist_modal_item_before_exit,
        _replace_item_in_data=_replace_item_in_data,
    )
