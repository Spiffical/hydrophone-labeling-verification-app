"""Shared helper builders used by top-level callback registration."""

import dash_bootstrap_components as dbc
from dash import html
from dash.exceptions import PreventUpdate


def build_require_complete_profile(*, is_profile_complete, profile_name_email, logger):
    def _require_complete_profile(profile, action_name):
        if is_profile_complete(profile):
            return
        logger.warning(
            "[PROFILE_REQUIRED] blocked_action=%s profile=%s",
            action_name,
            {"name": profile_name_email(profile)[0], "email": profile_name_email(profile)[1]},
        )
        raise PreventUpdate

    return _require_complete_profile


def build_grid(
    items,
    mode,
    colormap,
    y_axis_scale,
    items_per_page,
    *,
    get_item_image_src,
    create_spectrogram_card,
):
    if not items:
        return [html.Div("No items loaded.", className="text-muted text-center p-4")]

    grid = []
    limit = min(items_per_page, len(items))
    for item in items[:limit]:
        image_src = get_item_image_src(item, colormap=colormap, y_axis_scale=y_axis_scale)
        card = create_spectrogram_card(item, image_src=image_src, mode=mode)
        grid.append(dbc.Col(card, md=3, sm=6, xs=12, className="mb-3"))

    return dbc.Row(grid)


def build_persist_modal_item_before_exit(
    *,
    persist_modal_item_before_exit_service,
    require_complete_profile,
    profile_actor,
):
    def _persist_modal_item_before_exit(
        mode,
        item_id,
        label_data,
        verify_data,
        explore_data,
        thresholds,
        profile,
        bbox_store,
        label_output_path,
        cfg,
    ):
        return persist_modal_item_before_exit_service(
            mode,
            item_id,
            label_data,
            verify_data,
            explore_data,
            thresholds,
            profile,
            bbox_store,
            label_output_path,
            cfg,
            require_complete_profile=require_complete_profile,
            profile_actor=profile_actor,
        )

    return _persist_modal_item_before_exit
