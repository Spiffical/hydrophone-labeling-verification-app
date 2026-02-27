"""Orchestration entrypoint for data configuration callbacks."""

from app.callbacks.data.config_helpers import (
    build_predictions_entries,
    create_info_badge,
    create_predictions_info,
    tab_iso_debug,
)
from app.callbacks.data.config_load_callbacks import register_data_config_load_callbacks
from app.callbacks.data.config_modal_callbacks import register_data_config_modal_callbacks
from app.callbacks.data.config_path_callbacks import register_data_config_path_callbacks


def register_data_config_callbacks(app):
    """Register all data-configuration callback groups."""
    register_data_config_modal_callbacks(
        app,
        tab_iso_debug=tab_iso_debug,
        build_predictions_entries=build_predictions_entries,
        create_info_badge=create_info_badge,
        create_predictions_info=create_predictions_info,
    )
    register_data_config_load_callbacks(
        app,
        tab_iso_debug=tab_iso_debug,
    )
    register_data_config_path_callbacks(
        app,
        create_info_badge=create_info_badge,
        create_predictions_info=create_predictions_info,
    )

