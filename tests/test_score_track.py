"""The detector score strip under the main spectrogram (config score_track)."""

import json
import os

import pytest

from app.callbacks.modal.score_track_callbacks import register_modal_score_track_callbacks, score_track_view
from app.components.modal import create_spectrogram_modal
from app.config import _score_track_config
from app.services import score_tracks
from app.services.score_tracks import score_track_for_item


def _walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    if component is None or isinstance(component, (str, int, float)):
        return
    yield component
    yield from _walk(getattr(component, "children", None))


@pytest.fixture
def score_file(tmp_path):
    path = tmp_path / "scores.json"
    path.write_text(json.dumps({
        "label": "Fin whale detector score",
        "items": {
            "clip-a": {"start_s": 0.0, "step_s": 0.5, "scores": [0.1, None, 0.9, 1.2, -0.1]},
            "clip-b": {"times": [1.0, 2.0], "scores": [0.4, 0.6]},
            "clip-c": {"start_s": 0.0, "step_s": 0.5, "scores": [None, None]},
            "clip-d": {"times": [1.0], "scores": [0.4, 0.6]},
        },
    }))
    return str(path)


def test_a_score_track_needs_a_file():
    assert _score_track_config(None, "/app") is None
    assert _score_track_config({"label": "x"}, "/app") is None
    assert _score_track_config({"file": "s.json", "enabled": False}, "/app") is None
    assert _score_track_config({"file": "tracks/s.json", "threshold": 0.9}, "/app") == {
        "file": "/app/tracks/s.json", "label": None, "threshold": 0.9,
    }
    for bad in (0, 1, 2, "high"):
        assert _score_track_config({"file": "/s.json", "threshold": bad}, "/app")["threshold"] is None


def test_each_clip_gets_its_scores_in_clip_seconds(score_file):
    cfg = {"file": score_file, "label": None, "threshold": None}
    track = score_track_for_item(cfg, "clip-a")
    assert track["times"] == [0.0, 0.5, 1.0, 1.5, 2.0]
    # Gaps stay gaps; scores stay within 0..1.
    assert track["scores"] == [0.1, None, 0.9, 1.0, 0.0]
    assert track["label"] == "Fin whale detector score"
    assert score_track_for_item(cfg, "clip-b")["times"] == [1.0, 2.0]
    # Clips the file does not list, with no scores, or with mismatched times get none.
    for item_id in ("clip-z", "clip-c", "clip-d", None):
        assert score_track_for_item(cfg, item_id) is None
    assert score_track_for_item({**cfg, "label": "Detector"}, "clip-b")["label"] == "Detector"
    assert score_track_for_item({**cfg, "file": score_file + ".missing"}, "clip-a") is None


def test_the_file_is_read_again_when_it_changes(score_file):
    cfg = {"file": score_file, "label": None, "threshold": None}
    assert score_track_for_item(cfg, "clip-b")["scores"] == [0.4, 0.6]
    with open(score_file, "w", encoding="utf-8") as handle:
        json.dump({"items": {"clip-b": {"times": [1.0, 2.0, 3.0], "scores": [0.7, 0.8, 0.95]}}}, handle)
    stat = os.stat(score_file)
    os.utime(score_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert score_track_for_item(cfg, "clip-b")["scores"] == [0.7, 0.8, 0.95]
    assert score_tracks.load_score_tracks(score_file)["items"].keys() == {"clip-b"}


def test_the_strip_sits_on_the_main_plots_time_axis(score_file):
    track = score_track_for_item({"file": score_file, "label": None, "threshold": 0.5}, "clip-b")
    # A plot whose axis starts at its first frame, half a second into the clip.
    context = {"layout": {
        "meta": {"x_min": 0.0, "x_max": 3.0, "x_to_seconds": 1.0, "x_origin_seconds": 0.5},
        "xaxis": {"range": [0.5, 1.5]},
    }}
    figure = score_track_view(track, "clip-b", context).to_plotly_json()
    trace = figure["data"][0]
    assert list(trace["x"]) == [0.5, 1.5]
    assert list(trace["customdata"]) == [1.0, 2.0]
    layout = figure["layout"]
    assert list(layout["xaxis"]["range"]) == [0.5, 1.5]
    assert layout["xaxis"]["fixedrange"] and layout["yaxis"]["fixedrange"]
    assert layout["meta"] == {"kind": "score_track", "x_min": 0.0, "x_max": 3.0, "x_to_seconds": 1.0}
    assert layout["shapes"][0]["y0"] == 0.5
    assert layout["annotations"][0]["text"] == "Fin whale detector score"
    # Without the main plot's context: clip time, the whole track.
    bare = score_track_view(track, "clip-b", None).to_plotly_json()
    assert list(bare["data"][0]["x"]) == [1.0, 2.0]
    assert list(bare["layout"]["xaxis"]["range"]) == [1.0, 2.0]


class _App:
    def __init__(self):
        self.callbacks = []

    def callback(self, *args, **kwargs):
        def register(function):
            self.callbacks.append((args, function))
            return function
        return register


def test_only_dashboards_with_a_score_file_get_the_strip(score_file):
    app = _App()
    register_modal_score_track_callbacks(app, config={"score_track": None})
    assert app.callbacks == []

    register_modal_score_track_callbacks(app, config={"score_track": {"file": score_file, "label": None, "threshold": None}})
    (_outputs, render), = app.callbacks
    figure, hidden = render({"item_id": "clip-a"}, None)
    assert hidden is False and figure.to_plotly_json()["data"][0]["y"] is not None
    _figure, hidden = render({"item_id": "clip-z"}, None)
    assert hidden is True

    modal = create_spectrogram_modal(config={})
    strip = next(node for node in _walk(modal) if getattr(node, "id", None) == "modal-score-track")
    assert strip.hidden is True
    assert strip.children.id == "modal-score-track-graph"
