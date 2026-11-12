"""The evidence figure for a clip's labels (config evidence_figures), and the
similar clips it can open beside the review window."""

import json

import pytest

from app.callbacks.modal.evidence_figure_callbacks import (
    evidence_figure_view,
    evidence_related_buttons,
    register_modal_evidence_figure_callbacks,
    related_clip_view,
)
from app.components.modal import create_spectrogram_modal
from app.config import _evidence_figures_config
from app.main import create_app
from app.services.evidence_figures import evidence_caption, evidence_figure_path, evidence_figure_src, evidence_related
from app.services.verify_modal_cache import register_verify_modal_items


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
def folder(tmp_path):
    (tmp_path / "clip-a.png").write_bytes(b"\x89PNG\r\n\x1a\nfigure")
    (tmp_path / "secret.png").write_bytes(b"\x89PNG\r\n\x1a\nnot for clips")
    return str(tmp_path)


def test_evidence_figures_need_a_folder():
    assert _evidence_figures_config(None, "/app") is None
    assert _evidence_figures_config({}, "/app") is None
    assert _evidence_figures_config({"folder": "  "}, "/app") is None
    assert _evidence_figures_config({"folder": "figs", "enabled": False}, "/app") is None
    assert _evidence_figures_config({"folder": "figs"}, "/app") == {"folder": "/app/figs"}
    assert _evidence_figures_config({"folder": "/data/figs"}, "/app") == {"folder": "/data/figs"}


def test_each_clip_gets_its_own_file_and_nothing_else(folder):
    cfg = {"folder": folder}
    assert evidence_figure_path(cfg, "clip-a").endswith("clip-a.png")
    src = evidence_figure_src(cfg, "clip-a")
    assert src.startswith("/evidence-figure/clip-a?v=")
    # No figure, no config, or an id that is not a plain file name: nothing.
    for item_id in ("clip-b", None, 7, "", "../clip-a", "a/clip-a", ".hidden", "clip-a/.."):
        assert evidence_figure_path(cfg, item_id) is None
    assert evidence_figure_path(None, "clip-a") is None
    assert evidence_figure_src({"folder": ""}, "clip-a") is None


def test_the_button_shows_only_for_clips_with_a_figure(folder):
    cfg = {"folder": folder}
    src, href, caption, hidden = evidence_figure_view(cfg, {"item_id": "clip-a"})
    assert src == href and src.startswith("/evidence-figure/clip-a") and hidden is False
    assert caption == []
    assert evidence_figure_view(cfg, {"item_id": "clip-b"}) == ("", "", [], True)
    assert evidence_figure_view(cfg, None) == ("", "", [], True)


def test_a_caption_file_gives_a_few_short_lines(folder, tmp_path):
    cfg = {"folder": folder}
    (tmp_path / "clip-a.txt").write_text("Annotated: killer whale clicks\n\n  Suggested: sperm whale clicks  \n", encoding="utf-8")
    assert evidence_caption(cfg, "clip-a") == ["Annotated: killer whale clicks", "Suggested: sperm whale clicks"]
    _, _, caption, _ = evidence_figure_view(cfg, {"item_id": "clip-a"})
    assert [line.children for line in caption] == ["Annotated: killer whale clicks", "Suggested: sperm whale clicks"]
    (tmp_path / "clip-a.txt").write_text("\n".join(["x" * 400] * 9), encoding="utf-8")
    assert [len(line) for line in evidence_caption(cfg, "clip-a")] == [300] * 4
    # No caption without a file, and none for an id that cannot name one.
    assert evidence_caption(cfg, "secret") == [] and evidence_caption(cfg, "../clip-a") == []


class _App:
    def __init__(self):
        self.callbacks = []

    def callback(self, *args, **kwargs):
        def register(function):
            self.callbacks.append((args, function))
            return function
        return register


def test_the_callbacks_are_registered_only_when_configured(folder):
    app = _App()
    register_modal_evidence_figure_callbacks(app, config={"evidence_figures": None})
    assert app.callbacks == []
    register_modal_evidence_figure_callbacks(app, config={"evidence_figures": {"folder": folder}})
    assert len(app.callbacks) == 4
    (_, show), (open_args, open_viewer), (related_args, related), (open_related_args, _) = app.callbacks
    assert show({"item_id": "clip-a"})[3] is False
    assert open_args[0].component_id == "modal-evidence-viewer" and open_viewer(1) is True
    assert related_args[0].component_id == "modal-evidence-related" and related({"item_id": "clip-a"}) == []
    assert open_related_args[0].component_id == "modal-related-viewer"


def test_the_modal_has_a_hidden_button_and_a_closed_viewer():
    ids = {getattr(c, "id", None): c for c in _walk(create_spectrogram_modal())}
    assert ids["modal-evidence"].hidden is True
    assert "modal-evidence-open" in ids and "modal-evidence-caption" in ids
    assert ids["modal-evidence-viewer"].is_open is False
    assert "modal-evidence-image" in ids and "modal-evidence-link" in ids
    # Similar clips: buttons in the evidence section, and a closed window that
    # neither dims nor blocks the review window.
    assert "modal-evidence-related" in ids
    viewer = ids["modal-related-viewer"]
    assert viewer.is_open is False and viewer.backdrop is False and viewer.enforceFocus is False
    assert {"modal-related-title", "modal-related-plot", "modal-related-audio", "modal-related-caption"} <= set(ids)
    # The figure is in its own dialog, not in the sidebar beside the box list.
    side = next(c for c in _walk(create_spectrogram_modal()) if "modal-workbench-side" in (getattr(c, "className", "") or ""))
    assert "modal-evidence-image" not in {getattr(c, "id", None) for c in _walk(side)}


def test_the_route_serves_a_clips_figure_and_nothing_else(folder):
    app = create_app({"evidence_figures": {"folder": folder}})
    client = app.server.test_client()
    response = client.get("/evidence-figure/clip-a")
    assert response.status_code == 200 and response.mimetype == "image/png"
    assert response.data.endswith(b"figure")
    for path in ("/evidence-figure/clip-b", "/evidence-figure/.secret"):
        assert client.get(path).status_code == 404
    # A path that climbs out of the folder never reaches the route (Dash's page answers it): no image, no file.
    escaped = client.get("/evidence-figure/..%2Fsecret")
    assert escaped.mimetype != "image/png" and b"not for clips" not in escaped.data
    bare = create_app({}).server.test_client()
    assert bare.get("/evidence-figure/clip-a").status_code == 404



def _write_related(tmp_path, entries, item_id="clip-a"):
    (tmp_path / f"{item_id}.json").write_text(json.dumps({"related": entries}), encoding="utf-8")


def test_similar_clips_come_from_the_clips_own_file(folder, tmp_path):
    cfg = {"folder": folder}
    assert evidence_related(cfg, "clip-a") == []
    _write_related(tmp_path, [
        {"item_id": "clip-b", "label": "Clip 157 \u00b7 2022-07-11", "detail": "r 0.77"},
        {"item_id": "../secret", "label": "cannot name a clip"},
        {"item_id": "clip-a", "label": "the clip itself"},
        {"item_id": "clip-b", "label": "again"},
        "not an entry",
        {"item_id": "clip-c"},
    ] + [{"item_id": f"clip-{n}", "label": "y" * 200} for n in range(10)])
    related = evidence_related(cfg, "clip-a")
    assert [entry["item_id"] for entry in related] == ["clip-b", "clip-c", "clip-0", "clip-1", "clip-2", "clip-3"]
    assert related[0] == {"item_id": "clip-b", "label": "Clip 157 \u00b7 2022-07-11", "detail": "r 0.77"}
    assert related[1]["label"] == "clip-c" and len(related[2]["label"]) == 60
    (tmp_path / "clip-a.json").write_text("{not json", encoding="utf-8")
    assert evidence_related(cfg, "clip-a") == []
    assert evidence_related(cfg, "../clip-a") == [] and evidence_related(None, "clip-a") == []


def test_each_similar_clip_is_a_button_that_names_it(folder, tmp_path):
    cfg = {"folder": folder}
    assert evidence_related_buttons(cfg, {"item_id": "clip-a"}) == []
    _write_related(tmp_path, [{"item_id": "clip-b", "label": "Clip 157", "detail": "r 0.77"}])
    title, row = evidence_related_buttons(cfg, {"item_id": "clip-a"})
    (button,) = row.children
    assert button.id == {"type": "evidence-related-open", "item_id": "clip-b"}
    assert button.children == "Clip 157" and button.title == "r 0.77" and button.n_clicks == 0
    assert evidence_related_buttons(cfg, None) == []


def test_a_similar_clip_opens_view_only_from_the_loaded_queue(folder, tmp_path):
    cfg = {"folder": folder}
    audio = tmp_path / "clip-b.flac"
    audio.write_bytes(b"fLaC")
    (tmp_path / "clip-b.png").write_bytes(b"\x89PNG\r\n\x1a\nb")
    (tmp_path / "clip-b.txt").write_text("Main sound: dolphin-type clicks\n", encoding="utf-8")
    key = register_verify_modal_items({"items": [{"item_id": "clip-b", "audio_path": str(audio),
                                                   "audio_start_time": "2022-07-11T02:35:00+00:00",
                                                   "audio_end_time": "2022-07-11T02:35:45+00:00"}],
                                        "load_timestamp": "t1", "summary": {}})
    config = {"evidence_figures": cfg, "audio": {"transport": "direct"},
              "spectrogram_render": {"freq_min_hz": 2000.0, "freq_max_hz": 64000.0}}
    title, plot, sound, caption, link = related_clip_view(cfg, config, key, "clip-b", "Clip 157")
    assert title == "Clip 157" and sound.startswith("/audio-file/")
    image, yaxis, xaxis = plot.children
    assert image.src.startswith("/modal-image/")
    assert [tick.children for tick in xaxis.children] == ["0 s", "10 s", "20 s", "30 s", "40 s"]
    assert [tick.children for tick in yaxis.children] == ["10", "20", "30", "40", "50", "60", "kHz"]
    # A low range such as the fin whale's 5-100 Hz is labelled in Hz.
    low_axis = related_clip_view(cfg, {"evidence_figures": cfg}, key, "clip-b", "Clip 157")[1].children[1]
    assert low_axis.children[-1].children == "Hz" and [t.children for t in low_axis.children[:-1]] == ["20", "40", "60", "80", "100"]
    assert [line.children for line in caption] == ["Main sound: dolphin-type clicks"]
    assert link.startswith("/evidence-figure/clip-b")
    # A clip outside the loaded queue shows a note and loads nothing.
    title, plot, sound, caption, link = related_clip_view(cfg, config, key, "clip-z", "Clip 9")
    assert (title, plot, sound, link) == ("Clip 9", [], "", "")
    assert "not in the loaded queue" in caption[0].children
