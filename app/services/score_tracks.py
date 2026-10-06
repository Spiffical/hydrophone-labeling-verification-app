"""A detector's score along each clip, drawn as a strip under the main
spectrogram so a reviewer can see where the model hears calls.

The dashboard config names a score file (``score_track.file``, app/config.py):

    {
      "label": "Fin whale detector score",
      "items": {
        "<item_id>": {"start_s": 0.0, "step_s": 0.1, "scores": [0.02, 0.03, ...]}
      }
    }

Times are clip time: seconds from the start of the clip's audio, as boxes are
(annotation_times.py). ``scores`` run 0 to 1, one every ``step_s`` seconds from
``start_s``; ``null`` leaves a gap. An item may give ``times`` instead of
``start_s`` and ``step_s``. Items the file does not list get no strip.

The file is read once and again only when it changes on disk; it is never
written by the app.
"""

import json
import math
import os
import threading
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go

DEFAULT_LABEL = "Detector score"
LINE_COLOR = "#0f766e"
FILL_COLOR = "rgba(15, 118, 110, 0.28)"

_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def load_score_tracks(path: Optional[str]) -> Optional[Dict[str, Any]]:
    """The score file at ``path``, or None if it is missing or not one."""
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    stamp = (stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _cache.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = None
    if not (isinstance(data, dict) and isinstance(data.get("items"), dict)):
        data = None
    with _cache_lock:
        _cache[path] = (stamp, data)
    return data


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def score_track_for_item(score_cfg: Optional[Dict[str, Any]], item_id: Any) -> Optional[Dict[str, Any]]:
    """``{"times", "scores", "label", "threshold"}`` for one clip (times in
    clip seconds, scores clamped to 0..1, None for gaps), or None."""
    if not isinstance(score_cfg, dict) or not item_id:
        return None
    data = load_score_tracks(score_cfg.get("file"))
    entry = (data or {}).get("items", {}).get(str(item_id))
    if not isinstance(entry, dict) or not isinstance(entry.get("scores"), list):
        return None
    raw_scores = entry["scores"]
    if isinstance(entry.get("times"), list):
        times = [_finite(value) for value in entry["times"]]
        if len(times) != len(raw_scores) or any(value is None for value in times):
            return None
    else:
        start = _finite(entry.get("start_s"))
        step = _finite(entry.get("step_s"))
        if start is None or step is None or step <= 0:
            return None
        times = [round(start + index * step, 6) for index in range(len(raw_scores))]
    scores: List[Optional[float]] = []
    for value in raw_scores:
        value = _finite(value)
        scores.append(None if value is None else min(1.0, max(0.0, value)))
    if not any(value is not None for value in scores):
        return None
    label = score_cfg.get("label") or (data.get("label") if isinstance(data.get("label"), str) else None)
    return {
        "times": times,
        "scores": scores,
        "label": label or DEFAULT_LABEL,
        "threshold": score_cfg.get("threshold"),
    }


def build_score_track_figure(
    track: Dict[str, Any],
    *,
    item_id: Any,
    x_min: float,
    x_max: float,
    view_range: List[float],
    x_to_seconds: float = 1.0,
    x_origin_seconds: Optional[float] = None,
) -> go.Figure:
    """The strip for one clip, on the main plot's time axis: x is
    ``(clip seconds - x_origin_seconds) / x_to_seconds``, as the playback line
    (audio_controls.js). Margins and time window follow the main plot
    (modal_range_panels.js), and scrolling over the strip zooms time there
    (modal_scroll_zoom.js), so Plotly zooms neither axis itself."""
    origin = x_origin_seconds if isinstance(x_origin_seconds, (int, float)) else 0.0
    scale = x_to_seconds if isinstance(x_to_seconds, (int, float)) and x_to_seconds > 0 else 1.0
    times = track["times"]
    figure = go.Figure(
        go.Scatter(
            x=[(time - origin) / scale for time in times],
            y=track["scores"],
            customdata=times,
            mode="lines",
            line={"color": LINE_COLOR, "width": 1.5},
            fill="tozeroy",
            fillcolor=FILL_COLOR,
            connectgaps=False,
            hovertemplate="%{y:.2f} at %{customdata:.1f} s<extra></extra>",
            showlegend=False,
        )
    )
    shapes = []
    threshold = track.get("threshold")
    if isinstance(threshold, (int, float)) and 0 < threshold < 1:
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": threshold,
                "y1": threshold,
                "line": {"color": "rgba(71, 85, 105, 0.7)", "width": 1, "dash": "dash"},
                "layer": "below",
            }
        )
    figure.update_layout(
        autosize=True,
        # Room above and below for the 0 and 1 tick labels.
        margin={"l": 70, "r": 36, "t": 8, "b": 8},
        template="plotly_white",
        dragmode=False,
        hovermode="x",
        showlegend=False,
        uirevision=f"{item_id}|score-track",
        meta={"kind": "score_track", "x_min": x_min, "x_max": x_max, "x_to_seconds": scale},
        shapes=shapes,
        annotations=[
            {
                "text": track["label"],
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": 1,
                "xanchor": "left",
                "yanchor": "top",
                "showarrow": False,
                "font": {"size": 11, "color": "#334155"},
                "bgcolor": "rgba(255, 255, 255, 0.75)",
                "borderpad": 2,
            }
        ],
        xaxis={
            "range": list(view_range),
            "fixedrange": True,
            "showticklabels": False,
            "showgrid": False,
            "zeroline": False,
            "ticks": "",
            "automargin": False,
        },
        yaxis={
            "range": [0, 1.04],
            "fixedrange": True,
            "tickvals": [0, 0.5, 1],
            "ticktext": ["0", "0.5", "1"],
            "tickfont": {"size": 10},
            "showgrid": True,
            "gridcolor": "rgba(148, 163, 184, 0.35)",
            "zeroline": False,
            "automargin": False,
        },
    )
    return figure
