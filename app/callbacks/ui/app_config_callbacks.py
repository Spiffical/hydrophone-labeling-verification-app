"""App configuration callbacks."""

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate


def _coerce_positive_int(value, fallback):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def register_app_config_callbacks(app, *, set_cache_sizes):
    """Register app config modal open/save/cancel callbacks."""

    @app.callback(
        Output("app-config-modal", "is_open"),
        Output("app-config-items-per-page", "value"),
        Output("app-config-cache-size", "value"),
        Output("config-store", "data", allow_duplicate=True),
        Input("app-config-btn", "n_clicks"),
        Input("app-config-cancel", "n_clicks"),
        Input("app-config-save", "n_clicks"),
        State("config-store", "data"),
        State("app-config-items-per-page", "value"),
        State("app-config-cache-size", "value"),
        prevent_initial_call=True,
    )
    def handle_app_config(open_clicks, cancel_clicks, save_clicks, cfg, items_per_page, cache_size):
        _ = open_clicks, cancel_clicks, save_clicks
        triggered = ctx.triggered_id
        cfg = cfg or {}
        display_cfg = cfg.get("display", {}) or {}
        cache_cfg = cfg.get("cache", {}) or {}

        if triggered == "app-config-btn":
            return (
                True,
                display_cfg.get("items_per_page", 25),
                cache_cfg.get("max_size", 400),
                no_update,
            )

        if triggered == "app-config-cancel":
            return False, no_update, no_update, no_update

        if triggered != "app-config-save":
            raise PreventUpdate

        new_items_per_page = _coerce_positive_int(items_per_page, display_cfg.get("items_per_page", 25))
        new_cache_size = _coerce_positive_int(cache_size, cache_cfg.get("max_size", 400))

        updated_cfg = dict(cfg)
        updated_cfg["display"] = dict(display_cfg)
        updated_cfg["display"]["items_per_page"] = new_items_per_page
        updated_cfg["cache"] = dict(cache_cfg)
        updated_cfg["cache"]["max_size"] = new_cache_size

        set_cache_sizes(new_cache_size)

        return False, new_items_per_page, new_cache_size, updated_cfg
