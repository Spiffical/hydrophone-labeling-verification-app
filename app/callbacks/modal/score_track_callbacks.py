"""The detector score strip under the main spectrogram (config ``score_track``,
app/services/score_tracks.py). Dashboards without one keep it hidden."""

from dash import Input, Output, no_update

from app.services.score_tracks import build_score_track_figure, score_track_for_item


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _range(value):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lower, upper = _number(value[0]), _number(value[1])
        if lower is not None and upper is not None and upper > lower:
            return [lower, upper]
    return None


def score_track_view(track, item_id, active_figure):
    """The strip's figure for one clip, on the axis of the main plot
    (``modal-figure-context-store``): its clip extent, the window it shows,
    and how its x maps to seconds."""
    layout = active_figure.get("layout") if isinstance(active_figure, dict) else None
    layout = layout if isinstance(layout, dict) else {}
    meta = layout.get("meta") if isinstance(layout.get("meta"), dict) else {}
    xaxis = layout.get("xaxis") if isinstance(layout.get("xaxis"), dict) else {}
    x_to_seconds = _number(meta.get("x_to_seconds"))
    x_to_seconds = x_to_seconds if x_to_seconds and x_to_seconds > 0 else 1.0
    origin = _number(meta.get("x_origin_seconds"))
    times = track["times"]
    clip = _range([meta.get("x_min"), meta.get("x_max")]) or [
        (min(times) - (origin or 0.0)) / x_to_seconds,
        (max(times) - (origin or 0.0)) / x_to_seconds,
    ]
    if clip[1] <= clip[0]:
        clip = [clip[0], clip[0] + 1.0]
    return build_score_track_figure(
        track,
        item_id=item_id,
        x_min=clip[0],
        x_max=clip[1],
        view_range=_range(xaxis.get("range")) or clip,
        x_to_seconds=x_to_seconds,
        x_origin_seconds=origin,
    )


def register_modal_score_track_callbacks(app, *, config):
    score_cfg = config.get("score_track") if isinstance(config, dict) else None
    if not score_cfg:
        return

    @app.callback(
        Output("modal-score-track-graph", "figure"),
        Output("modal-score-track", "hidden"),
        Input("modal-item-store", "data"),
        Input("modal-figure-context-store", "data"),
    )
    def render_modal_score_track(modal_item, active_figure):
        item_id = modal_item.get("item_id") if isinstance(modal_item, dict) else None
        track = score_track_for_item(score_cfg, item_id)
        if track is None:
            return no_update, True
        return score_track_view(track, item_id, active_figure), False
