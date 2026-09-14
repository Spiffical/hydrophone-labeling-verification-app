"""Shared helper builders used by top-level callback registration."""

from dash import html
from dash.exceptions import PreventUpdate

from app.services.spectrogram_grid import (
    normalize_spectrogram_grid,
    spectrogram_grid_class,
)
from app.services.spectrogram_ranges import (
    config_for_spectrogram_range,
    format_frequency_range,
    resolve_visible_spectrogram_ranges,
)


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
    y_axis_min_hz,
    y_axis_max_hz,
    color_min,
    color_max,
    items_per_page,
    cfg=None,
    spectrogram_ranges=None,
    *,
    empty_message="No items loaded.",
    get_item_image_src,
    create_spectrogram_card,
):
    if not items:
        return [html.Div(empty_message, className="text-muted text-center p-4")]

    grid = []
    grid_layout = normalize_spectrogram_grid(cfg)
    limit = min(items_per_page, len(items))
    for item in items[:limit]:
        image_views = []
        for range_spec in resolve_visible_spectrogram_ranges(
            item,
            cfg,
            spectrogram_ranges,
        ):
            range_cfg = (
                cfg
                if range_spec["id"] == "configured-range"
                else config_for_spectrogram_range(cfg, range_spec)
            )
            range_src = get_item_image_src(
                item,
                colormap=colormap,
                y_axis_scale=y_axis_scale,
                y_axis_min_hz=range_spec["freq_min_hz"],
                y_axis_max_hz=range_spec["freq_max_hz"],
                color_min=color_min,
                color_max=color_max,
                cfg=range_cfg,
            )
            image_views.append(
                {
                    "id": range_spec["id"],
                    "label": range_spec["label"],
                    "frequency_label": format_frequency_range(
                        range_spec["freq_min_hz"],
                        range_spec["freq_max_hz"],
                    ),
                    "image_src": range_src,
                }
            )
        image_src = image_views[0]["image_src"] if image_views else get_item_image_src(
            item, colormap=colormap, y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz, y_axis_max_hz=y_axis_max_hz,
            color_min=color_min, color_max=color_max, cfg=cfg,
        )
        card = create_spectrogram_card(
            item,
            image_src=image_src,
            image_views=image_views,
            mode=mode,
        )
        column = html.Div(card, className="spectrogram-card-grid-cell")
        if item.get("item_id"):
            column.id = {"type": "spectrogram-card-column", "mode": mode, "item_id": item["item_id"]}
        grid.append(column)

    return html.Div(
        grid,
        className=spectrogram_grid_class(grid_layout["columns"]),
        style={"--spectrogram-grid-columns": str(grid_layout["columns"])},
    )


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
