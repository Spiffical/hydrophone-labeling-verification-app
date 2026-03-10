"""Grouped callback-registration wiring for the app."""

from app.callbacks.data.config_callbacks import register_data_config_callbacks
from app.callbacks.data.discovery_callbacks import register_tab_state_callbacks
from app.callbacks.data.filter_state_callbacks import register_filter_state_callbacks
from app.callbacks.data.folder_browser_callbacks import register_folder_browser_callbacks
from app.callbacks.data.load_callbacks import (
    register_data_loading_callbacks,
    register_global_load_trigger_callback,
)
from app.callbacks.data.loading_overlay_callbacks import register_loading_overlay_callbacks
from app.callbacks.data.pagination_callbacks import register_pagination_callbacks
from app.callbacks.data.render_callbacks import register_render_callbacks
from app.callbacks.data.specgen_status_callbacks import register_specgen_status_callbacks
from app.callbacks.label.editor_callbacks import register_label_editor_callbacks
from app.callbacks.modal.audio_callbacks import register_modal_audio_callbacks
from app.callbacks.modal.bbox_callbacks import register_modal_bbox_callbacks
from app.callbacks.modal.label_callbacks import register_modal_label_callbacks
from app.callbacks.modal.lifecycle_callbacks import register_modal_lifecycle_callbacks
from app.callbacks.modal.view_callbacks import register_modal_view_callbacks
from app.callbacks.ui.app_config_callbacks import register_app_config_callbacks
from app.callbacks.ui.profile_callbacks import register_ui_callbacks
from app.callbacks.ui.tab_switch_callbacks import register_mode_tab_callbacks
from app.callbacks.ui.theme_callbacks import register_theme_callbacks
from app.callbacks.verify.class_filter_callbacks import register_verify_filter_callbacks
from app.callbacks.verify.decision_callbacks import register_verify_action_callbacks
from app.callbacks.verify.threshold_callbacks import register_verify_threshold_callbacks


def register_all_callback_sections(app, *, config, deps):
    d = deps
    d["set_cache_sizes"]((config or {}).get("cache", {}).get("max_size", 400))
    register_mode_tab_callbacks(app)
    register_pagination_callbacks(app)
    register_folder_browser_callbacks(app)
    register_data_config_callbacks(app)
    register_ui_callbacks(
        app,
        reset_profile_on_start=d["reset_profile_on_start"],
        profile_required_message=d["profile_required_message"],
        profile_name_email=d["profile_name_email"],
        is_profile_complete=d["is_profile_complete"],
        is_valid_email=d["is_valid_email"],
    )
    register_app_config_callbacks(app, set_cache_sizes=d["set_cache_sizes"])
    register_theme_callbacks(app)

    register_global_load_trigger_callback(
        app,
        tab_iso_debug=d["tab_iso_debug"],
        config_default_data_dir=d["config_default_data_dir"],
    )

    register_data_loading_callbacks(
        app,
        load_dataset=d["load_dataset"],
        _resolve_tab_data_dir=d["resolve_tab_data_dir"],
        _config_default_data_dir=d["config_default_data_dir"],
        _tab_iso_debug=d["tab_iso_debug"],
        _tab_data_snapshot=d["tab_data_snapshot"],
    )

    register_specgen_status_callbacks(
        app,
        _estimate_page_audio_generation_work=d["estimate_page_audio_generation_work"],
        _filter_predictions=d["filter_predictions"],
        _predicted_labels_match_filter=d["predicted_labels_match_filter"],
        _extract_verify_leaf_classes=d["extract_verify_leaf_classes"],
        _build_verify_filter_paths=d["build_verify_filter_paths"],
        _normalize_verify_class_filter=d["normalize_verify_class_filter"],
    )
    register_render_callbacks(
        app,
        _build_grid=d["build_grid"],
        _create_folder_display=d["create_folder_display"],
        _filter_predictions=d["filter_predictions"],
        _predicted_labels_match_filter=d["predicted_labels_match_filter"],
        _extract_verify_leaf_classes=d["extract_verify_leaf_classes"],
        _build_verify_filter_paths=d["build_verify_filter_paths"],
        _normalize_verify_class_filter=d["normalize_verify_class_filter"],
        _schedule_specgen_prefetch_for_current_page_images=d["schedule_specgen_prefetch_for_current_page_images"],
        _schedule_specgen_prefetch_for_future_pages=d["schedule_specgen_prefetch_for_future_pages"],
    )

    register_verify_filter_callbacks(
        app,
        extract_verify_leaf_classes=d["extract_verify_leaf_classes"],
        build_verify_filter_paths=d["build_verify_filter_paths"],
        normalize_verify_class_filter=d["normalize_verify_class_filter"],
        ordered_unique_labels=d["ordered_unique_labels"],
        split_hierarchy_label=d["split_hierarchy_label"],
        build_verify_filter_tree_rows=d["build_verify_filter_tree_rows"],
    )
    register_verify_threshold_callbacks(app)

    register_label_editor_callbacks(
        app,
        _create_folder_display=d["create_folder_display"],
        _get_mode_data=d["get_mode_data"],
        _require_complete_profile=d["require_complete_profile"],
        _filter_predictions=d["filter_predictions"],
        create_hierarchical_selector=d["create_hierarchical_selector"],
        _extract_label_extent_map_from_boxes=d["extract_label_extent_map_from_boxes"],
        _profile_actor=d["profile_actor"],
        _update_item_labels=d["update_item_labels"],
        _update_item_notes=d["update_item_notes"],
        save_label_mode=d["save_label_mode"],
        _build_modal_boxes_from_item=d["build_modal_boxes_from_item"],
        _modal_snapshot_payload=d["modal_snapshot_payload"],
        _parse_verify_target=d["parse_verify_target"],
        _get_modal_label_sets=d["get_modal_label_sets"],
        _ordered_unique_labels=d["ordered_unique_labels"],
        _clean_annotation_extent=d["clean_annotation_extent"],
        _has_pending_label_edits=d["has_pending_label_edits"],
    )

    register_verify_action_callbacks(
        app,
        _require_complete_profile=d["require_complete_profile"],
        _filter_predictions=d["filter_predictions"],
        _clean_annotation_extent=d["clean_annotation_extent"],
        _extract_label_extent_list_map_from_boxes=d["extract_label_extent_list_map_from_boxes"],
        _extract_label_extent_map_from_boxes=d["extract_label_extent_map_from_boxes"],
        _get_modal_label_sets=d["get_modal_label_sets"],
        _parse_verify_target=d["parse_verify_target"],
        _profile_actor=d["profile_actor"],
        _update_item_labels=d["update_item_labels"],
        _build_modal_boxes_from_item=d["build_modal_boxes_from_item"],
        _modal_snapshot_payload=d["modal_snapshot_payload"],
        _get_item_rejected_labels=d["get_item_rejected_labels"],
        _item_action_key=d["item_action_key"],
        _ordered_unique_labels=d["ordered_unique_labels"],
        _verify_badge_debug=d["verify_badge_debug"],
    )

    register_modal_lifecycle_callbacks(
        app,
        _get_mode_data=d["get_mode_data"],
        _get_modal_navigation_items=d["get_modal_navigation_items"],
        _is_modal_dirty=d["is_modal_dirty"],
        _modal_snapshot_payload=d["modal_snapshot_payload"],
        _build_modal_boxes_from_item=d["build_modal_boxes_from_item"],
        _apply_modal_boxes_to_figure=d["apply_modal_boxes_to_figure"],
        _build_modal_item_actions=d["build_modal_item_actions"],
        _persist_modal_item_before_exit=d["persist_modal_item_before_exit"],
        _replace_item_in_data=d["replace_item_in_data"],
    )

    register_modal_view_callbacks(
        app,
        _get_mode_data=d["get_mode_data"],
        _build_modal_boxes_from_item=d["build_modal_boxes_from_item"],
        _apply_modal_boxes_to_figure=d["apply_modal_boxes_to_figure"],
        _build_modal_item_actions=d["build_modal_item_actions"],
    )

    register_modal_label_callbacks(
        app,
        _require_complete_profile=d["require_complete_profile"],
        _get_mode_data=d["get_mode_data"],
        _get_modal_label_sets=d["get_modal_label_sets"],
        _profile_actor=d["profile_actor"],
        _extract_label_extent_map_from_boxes=d["extract_label_extent_map_from_boxes"],
        _update_item_labels=d["update_item_labels"],
        _get_item_rejected_labels=d["get_item_rejected_labels"],
        _apply_modal_boxes_to_figure=d["apply_modal_boxes_to_figure"],
    )

    register_modal_bbox_callbacks(
        app,
        _apply_modal_boxes_to_figure=d["apply_modal_boxes_to_figure"],
        _require_complete_profile=d["require_complete_profile"],
        _parse_active_box_target=d["parse_active_box_target"],
        _bbox_debug=d["bbox_debug"],
        _bbox_debug_box_summary=d["bbox_debug_box_summary"],
        _axis_meta_from_figure=d["axis_meta_from_figure"],
        _safe_float=d["safe_float"],
        _shape_to_extent=d["shape_to_extent"],
        _extent_to_shape=d["extent_to_shape"],
        _clean_annotation_extent=d["clean_annotation_extent"],
        _ordered_unique_labels=d["ordered_unique_labels"],
        _has_pending_label_edits=d["has_pending_label_edits"],
        _extract_label_extent_map_from_boxes=d["extract_label_extent_map_from_boxes"],
        _get_modal_label_sets=d["get_modal_label_sets"],
        _profile_actor=d["profile_actor"],
        _update_item_labels=d["update_item_labels"],
        _is_modal_dirty=d["is_modal_dirty"],
        _BBOX_DELETE_TRACE_NAME=d["bbox_delete_trace_name"],
    )

    register_modal_audio_callbacks(app)
    register_loading_overlay_callbacks(app)

    register_filter_state_callbacks(
        app,
        tab_iso_debug=d["tab_iso_debug"],
    )

    register_tab_state_callbacks(
        app,
        tab_iso_debug=d["tab_iso_debug"],
        config_default_data_dir=d["config_default_data_dir"],
        tab_data_snapshot=d["tab_data_snapshot"],
    )
