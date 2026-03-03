"""App configuration callbacks."""

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate


def _coerce_positive_int(value, fallback):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _coerce_float(value, fallback, *, minimum=None, maximum=None):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = float(fallback)
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return float(value)


def register_app_config_callbacks(app, *, set_cache_sizes):
    """Register app config modal open/save/cancel callbacks."""

    @app.callback(
        Output("app-config-modal", "is_open"),
        Output("app-config-items-per-page", "value"),
        Output("app-config-cache-size", "value"),
        Output("app-config-spectrogram-source", "value"),
        Output("app-config-spec-win-dur", "value"),
        Output("app-config-spec-overlap", "value"),
        Output("app-config-spec-freq-min", "value"),
        Output("app-config-spec-freq-max", "value"),
        Output("config-store", "data", allow_duplicate=True),
        Input("app-config-btn", "n_clicks"),
        Input("app-config-cancel", "n_clicks"),
        Input("app-config-save", "n_clicks"),
        State("config-store", "data"),
        State("app-config-items-per-page", "value"),
        State("app-config-cache-size", "value"),
        State("app-config-spectrogram-source", "value"),
        State("app-config-spec-win-dur", "value"),
        State("app-config-spec-overlap", "value"),
        State("app-config-spec-freq-min", "value"),
        State("app-config-spec-freq-max", "value"),
        prevent_initial_call=True,
    )
    def handle_app_config(
        open_clicks,
        cancel_clicks,
        save_clicks,
        cfg,
        items_per_page,
        cache_size,
        spectrogram_source,
        spec_win_dur,
        spec_overlap,
        spec_freq_min,
        spec_freq_max,
    ):
        _ = open_clicks, cancel_clicks, save_clicks
        triggered = ctx.triggered_id
        cfg = cfg or {}
        display_cfg = cfg.get("display", {}) or {}
        cache_cfg = cfg.get("cache", {}) or {}
        spec_cfg = cfg.get("spectrogram_render", {}) or {}

        if triggered == "app-config-btn":
            return (
                True,
                display_cfg.get("items_per_page", 25),
                cache_cfg.get("max_size", 400),
                spec_cfg.get("source", "existing"),
                spec_cfg.get("win_dur_s", 1.0),
                spec_cfg.get("overlap", 0.9),
                spec_cfg.get("freq_min_hz", 5.0),
                spec_cfg.get("freq_max_hz", 100.0),
                no_update,
            )

        if triggered == "app-config-cancel":
            return False, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        if triggered != "app-config-save":
            raise PreventUpdate

        new_items_per_page = _coerce_positive_int(items_per_page, display_cfg.get("items_per_page", 25))
        new_cache_size = _coerce_positive_int(cache_size, cache_cfg.get("max_size", 400))
        new_source = str(spectrogram_source or spec_cfg.get("source", "existing")).strip().lower()
        if new_source not in {"existing", "audio_generated"}:
            new_source = "existing"
        new_win_dur = _coerce_float(spec_win_dur, spec_cfg.get("win_dur_s", 1.0), minimum=0.05, maximum=30.0)
        new_overlap = _coerce_float(spec_overlap, spec_cfg.get("overlap", 0.9), minimum=0.0, maximum=0.99)
        new_freq_min = _coerce_float(spec_freq_min, spec_cfg.get("freq_min_hz", 5.0), minimum=0.0, maximum=200000.0)
        new_freq_max = _coerce_float(spec_freq_max, spec_cfg.get("freq_max_hz", 100.0), minimum=0.01, maximum=200000.0)
        if new_freq_max <= new_freq_min:
            new_freq_max = max(new_freq_min + 1.0, float(spec_cfg.get("freq_max_hz", 100.0)))

        updated_cfg = dict(cfg)
        updated_cfg["display"] = dict(display_cfg)
        updated_cfg["display"]["items_per_page"] = new_items_per_page
        updated_cfg["cache"] = dict(cache_cfg)
        updated_cfg["cache"]["max_size"] = new_cache_size
        updated_cfg["spectrogram_render"] = {
            "source": new_source,
            "win_dur_s": float(new_win_dur),
            "overlap": float(new_overlap),
            "freq_min_hz": float(new_freq_min),
            "freq_max_hz": float(new_freq_max),
        }

        set_cache_sizes(new_cache_size)

        return (
            False,
            new_items_per_page,
            new_cache_size,
            new_source,
            float(new_win_dur),
            float(new_overlap),
            float(new_freq_min),
            float(new_freq_max),
            updated_cfg,
        )
