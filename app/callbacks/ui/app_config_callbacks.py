"""App configuration callbacks."""

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.defaults import DEFAULT_CACHE_MAX_SIZE
from app.services.spectrogram_grid import (
    config_with_spectrogram_grid,
    normalize_spectrogram_grid,
)


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
        Output("spectrogram-grid-rows", "value"),
        Output("spectrogram-grid-columns", "value"),
        Output("spectrogram-grid-layout-summary", "children", allow_duplicate=True),
        Output("app-config-cache-size", "value"),
        Output("config-store", "data", allow_duplicate=True),
        Input("app-config-btn", "n_clicks"),
        Input("app-config-cancel", "n_clicks"),
        Input("app-config-save", "n_clicks"),
        State("config-store", "data"),
        State("spectrogram-grid-rows", "value"),
        State("spectrogram-grid-columns", "value"),
        State("app-config-cache-size", "value"),
        prevent_initial_call=True,
    )
    def handle_app_config(
        open_clicks,
        cancel_clicks,
        save_clicks,
        cfg,
        grid_rows,
        grid_columns,
        cache_size,
    ):
        _ = open_clicks, cancel_clicks, save_clicks
        triggered = ctx.triggered_id
        cfg = cfg or {}
        display_cfg = cfg.get("display", {}) or {}
        cache_cfg = cfg.get("cache", {}) or {}

        if triggered == "app-config-btn":
            layout = normalize_spectrogram_grid(cfg)
            return (
                True,
                layout["rows"],
                layout["columns"],
                f"{layout['items_per_page']} spectrograms per page",
                cache_cfg.get("max_size", DEFAULT_CACHE_MAX_SIZE),
                no_update,
            )

        if triggered == "app-config-cancel":
            return False, no_update, no_update, no_update, no_update, no_update

        if triggered != "app-config-save":
            raise PreventUpdate

        new_cache_size = _coerce_positive_int(cache_size, cache_cfg.get("max_size", DEFAULT_CACHE_MAX_SIZE))

        updated_cfg = config_with_spectrogram_grid(
            cfg,
            rows=grid_rows,
            columns=grid_columns,
        )
        layout = normalize_spectrogram_grid(updated_cfg)
        updated_cfg["cache"] = dict(cache_cfg)
        updated_cfg["cache"]["max_size"] = new_cache_size

        previous_cache_size = _coerce_positive_int(
            cache_cfg.get("max_size", DEFAULT_CACHE_MAX_SIZE),
            DEFAULT_CACHE_MAX_SIZE,
        )
        if new_cache_size != previous_cache_size:
            set_cache_sizes(new_cache_size)

        return (
            False,
            layout["rows"],
            layout["columns"],
            f"{layout['items_per_page']} spectrograms per page",
            new_cache_size,
            updated_cfg,
        )

    app.clientside_callback(
        """
        function(rows, columns) {
            var parsedRows = Math.max(1, Math.min(8, Number(rows) || 1));
            var parsedColumns = Math.max(1, Math.min(6, Number(columns) || 1));
            return String(parsedRows * parsedColumns) + " spectrograms per page";
        }
        """,
        Output("spectrogram-grid-layout-summary", "children", allow_duplicate=True),
        Input("spectrogram-grid-rows", "value"),
        Input("spectrogram-grid-columns", "value"),
        prevent_initial_call=True,
    )
