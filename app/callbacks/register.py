"""Top-level callback registration entrypoint."""

import logging
import os

from app.callbacks.common.debug import (
    bbox_debug as _bbox_debug,
    tab_iso_debug as _tab_iso_debug,
    verify_badge_debug as _verify_badge_debug,
)
from app.callbacks.common.profile_guard import (
    _PROFILE_REQUIRED_MESSAGE,
    is_profile_complete as _is_profile_complete,
    is_valid_email as _is_valid_email,
    profile_actor as _profile_actor,
    profile_name_email as _profile_name_email,
)
from app.callbacks.common.register_helpers import (
    build_grid as _build_grid_helper,
    build_persist_modal_item_before_exit as _build_persist_modal_item_before_exit,
    build_require_complete_profile as _build_require_complete_profile,
)
from app.callbacks.common.tab_context import (
    config_default_data_dir as _config_default_data_dir,
    resolve_tab_data_dir as _resolve_tab_data_dir,
    tab_data_snapshot as _tab_data_snapshot,
)
from app.callbacks.modal.helpers import (
    BBOX_DELETE_TRACE_NAME as _BBOX_DELETE_TRACE_NAME,
    apply_modal_boxes_to_figure as _apply_modal_boxes_to_figure,
    build_modal_item_actions as _build_modal_item_actions,
    create_folder_display as _create_folder_display,
)
from app.callbacks.common.register_sections import register_all_callback_sections
from app.components.hierarchical_selector import create_hierarchical_selector
from app.components.spectrogram_card import create_spectrogram_card
from app.services.annotations import (
    clean_annotation_extent as _clean_annotation_extent,
    extract_label_extent_list_map_from_boxes as _extract_label_extent_list_map_from_boxes,
    extract_label_extent_map_from_boxes as _extract_label_extent_map_from_boxes,
    ordered_unique_labels as _ordered_unique_labels,
    safe_float as _safe_float,
    split_hierarchy_label as _split_hierarchy_label,
)
from app.services.modal_boxes import (
    axis_meta_from_figure as _axis_meta_from_figure,
    bbox_debug_box_summary as _bbox_debug_box_summary,
    build_modal_boxes_from_item as _build_modal_boxes_from_item,
    extent_to_shape as _extent_to_shape,
    parse_active_box_target as _parse_active_box_target,
    shape_to_extent as _shape_to_extent,
)
from app.services.modal_state import (
    get_mode_data as _get_mode_data,
    get_modal_navigation_items as _get_modal_navigation_items,
    is_modal_dirty as _is_modal_dirty,
    item_action_key as _item_action_key,
    modal_snapshot_payload as _modal_snapshot_payload,
    persist_modal_item_before_exit as _persist_modal_item_before_exit_service,
    replace_item_in_data as _replace_item_in_data,
)
from app.services.verification import (
    filter_predictions as _filter_predictions,
    get_item_rejected_labels as _get_item_rejected_labels,
    get_modal_label_sets as _get_modal_label_sets,
    has_pending_label_edits as _has_pending_label_edits,
    parse_verify_target as _parse_verify_target,
    update_item_labels as _update_item_labels,
    update_item_notes as _update_item_notes,
)
from app.services.verify_filter_tree import (
    build_verify_leaf_paths as _build_verify_leaf_paths,
    build_verify_filter_paths as _build_verify_filter_paths,
    build_verify_filter_tree_rows as _build_verify_filter_tree_rows,
    expand_verify_filter_selection as _expand_verify_filter_selection,
    extract_verify_leaf_classes as _extract_verify_leaf_classes,
    normalize_verify_class_filter as _normalize_verify_class_filter,
    predicted_labels_match_filter as _predicted_labels_match_filter,
    toggle_verify_filter_selection as _toggle_verify_filter_selection,
)
from app.utils.data_loading import load_dataset
from app.utils.image_processing import (
    estimate_page_audio_generation_work,
    prefetch_page_modal_spectrograms_in_background,
    prefetch_page_images_in_background,
    schedule_modal_prefetch_for_future_pages,
    schedule_prefetch_for_future_pages,
    set_cache_sizes,
)
from app.utils.image_utils import get_item_image_src
from app.utils.persistence import save_label_mode

logger = logging.getLogger(__name__)
_RESET_PROFILE_ON_START = os.getenv("O3_RESET_PROFILE_ON_START", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

_require_complete_profile = _build_require_complete_profile(
    is_profile_complete=_is_profile_complete,
    profile_name_email=_profile_name_email,
    logger=logger,
)
_persist_modal_item_before_exit = _build_persist_modal_item_before_exit(
    persist_modal_item_before_exit_service=_persist_modal_item_before_exit_service,
    require_complete_profile=_require_complete_profile,
    profile_actor=_profile_actor,
)


def register_callbacks(app, config):
    def _build_grid(items, mode, colormap, y_axis_scale, items_per_page, cfg):
        return _build_grid_helper(
            items,
            mode,
            colormap,
            y_axis_scale,
            items_per_page,
            cfg,
            get_item_image_src=get_item_image_src,
            create_spectrogram_card=create_spectrogram_card,
        )

    deps = {
        "set_cache_sizes": set_cache_sizes,
        "estimate_page_audio_generation_work": estimate_page_audio_generation_work,
        "schedule_specgen_prefetch_for_current_page_images": prefetch_page_images_in_background,
        "schedule_specgen_prefetch_for_future_pages": schedule_prefetch_for_future_pages,
        "schedule_modal_prefetch_for_current_page_spectrograms": prefetch_page_modal_spectrograms_in_background,
        "schedule_modal_prefetch_for_future_pages": schedule_modal_prefetch_for_future_pages,
        "reset_profile_on_start": _RESET_PROFILE_ON_START,
        "profile_required_message": _PROFILE_REQUIRED_MESSAGE,
        "profile_name_email": _profile_name_email,
        "is_profile_complete": _is_profile_complete,
        "is_valid_email": _is_valid_email,
        "tab_iso_debug": _tab_iso_debug,
        "config_default_data_dir": _config_default_data_dir,
        "load_dataset": load_dataset,
        "resolve_tab_data_dir": _resolve_tab_data_dir,
        "tab_data_snapshot": _tab_data_snapshot,
        "build_grid": _build_grid,
        "create_folder_display": _create_folder_display,
        "filter_predictions": _filter_predictions,
        "predicted_labels_match_filter": _predicted_labels_match_filter,
        "extract_verify_leaf_classes": _extract_verify_leaf_classes,
        "build_verify_filter_paths": _build_verify_filter_paths,
        "build_verify_leaf_paths": _build_verify_leaf_paths,
        "expand_verify_filter_selection": _expand_verify_filter_selection,
        "normalize_verify_class_filter": _normalize_verify_class_filter,
        "ordered_unique_labels": _ordered_unique_labels,
        "split_hierarchy_label": _split_hierarchy_label,
        "build_verify_filter_tree_rows": _build_verify_filter_tree_rows,
        "toggle_verify_filter_selection": _toggle_verify_filter_selection,
        "get_mode_data": _get_mode_data,
        "require_complete_profile": _require_complete_profile,
        "create_hierarchical_selector": create_hierarchical_selector,
        "extract_label_extent_map_from_boxes": _extract_label_extent_map_from_boxes,
        "profile_actor": _profile_actor,
        "update_item_labels": _update_item_labels,
        "update_item_notes": _update_item_notes,
        "save_label_mode": save_label_mode,
        "build_modal_boxes_from_item": _build_modal_boxes_from_item,
        "modal_snapshot_payload": _modal_snapshot_payload,
        "parse_verify_target": _parse_verify_target,
        "get_modal_label_sets": _get_modal_label_sets,
        "clean_annotation_extent": _clean_annotation_extent,
        "has_pending_label_edits": _has_pending_label_edits,
        "extract_label_extent_list_map_from_boxes": _extract_label_extent_list_map_from_boxes,
        "get_item_rejected_labels": _get_item_rejected_labels,
        "item_action_key": _item_action_key,
        "verify_badge_debug": _verify_badge_debug,
        "get_modal_navigation_items": _get_modal_navigation_items,
        "is_modal_dirty": _is_modal_dirty,
        "apply_modal_boxes_to_figure": _apply_modal_boxes_to_figure,
        "build_modal_item_actions": _build_modal_item_actions,
        "persist_modal_item_before_exit": _persist_modal_item_before_exit,
        "replace_item_in_data": _replace_item_in_data,
        "parse_active_box_target": _parse_active_box_target,
        "bbox_debug": _bbox_debug,
        "bbox_debug_box_summary": _bbox_debug_box_summary,
        "axis_meta_from_figure": _axis_meta_from_figure,
        "safe_float": _safe_float,
        "shape_to_extent": _shape_to_extent,
        "extent_to_shape": _extent_to_shape,
        "bbox_delete_trace_name": _BBOX_DELETE_TRACE_NAME,
    }
    register_all_callback_sections(app, config=config, deps=deps)
