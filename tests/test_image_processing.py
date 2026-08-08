import base64
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import threading
import time
from unittest.mock import patch

from matplotlib.image import imread
import numpy as np

from app.utils import image_processing
from app.utils.image_processing import (
    create_image_file_figure,
    create_item_spectrogram_figure,
    generate_item_image_cached,
    load_audio_spectrogram_cached,
    load_spectrogram_cached,
    generate_image_cached,
)
from app.utils.image_utils import image_file_to_base64


def test_load_spectrogram_cached(mock_root):
    mat_dir = Path(mock_root) / "label" / "mat_files"
    mat_path = next(mat_dir.glob("*.mat"))
    spec = load_spectrogram_cached(str(mat_path))
    assert spec is not None
    assert "psd" in spec and "freq" in spec and "time" in spec


def test_generate_image_cached(mock_root):
    mat_dir = Path(mock_root) / "label" / "mat_files"
    mat_path = next(mat_dir.glob("*.mat"))
    image_src = generate_image_cached(str(mat_path), colormap="default", y_axis_scale="linear")
    assert image_src.startswith("data:image/png;base64,")


def test_page_generation_status_identifies_requested_colormap():
    status = image_processing.estimate_page_audio_generation_work(
        [],
        {"spectrogram_render": {"source": "existing"}},
        colormap="hydrophone",
    )

    assert status["params"]["colormap"] == "hydrophone"


def test_modal_image_preserves_every_source_cell():
    source = {
        "psd": np.arange(35, dtype=float).reshape(5, 7),
        "freq": np.linspace(0.0, 200.0, 5),
        "time": np.linspace(0.0, 300.0, 7),
    }

    image_src = image_processing._generate_modal_image_from_spectrogram_data(
        source,
        colormap="default",
        color_min=None,
        color_max=None,
    )
    image_bytes = base64.b64decode(image_src.split(",", 1)[1])
    rendered = imread(BytesIO(image_bytes), format="png")

    assert rendered.shape[:2] == source["psd"].shape


def test_modal_image_tile_preserves_requested_source_cells():
    source = {
        "psd": np.arange(35, dtype=float).reshape(5, 7),
        "freq": np.linspace(0.0, 200.0, 5),
        "time": np.linspace(0.0, 300.0, 7),
    }

    image_src = image_processing._generate_modal_image_from_spectrogram_data(
        source,
        colormap="default",
        color_min=None,
        color_max=None,
        tile_row_start=1,
        tile_row_end=4,
        tile_column_start=2,
        tile_column_end=6,
    )
    image_bytes = base64.b64decode(image_src.split(",", 1)[1])
    rendered = imread(BytesIO(image_bytes), format="png")

    assert rendered.shape[:2] == (3, 4)


def test_modal_image_figure_keeps_full_source_shape_in_plotly_metadata():
    source = {
        "psd": np.arange(35, dtype=float).reshape(5, 7),
        "freq": np.linspace(0.0, 200.0, 5),
        "time": np.linspace(0.0, 300.0, 7),
    }

    fig = image_processing.create_spectrogram_figure(
        source,
        "default",
        image_source="/modal-image/test-token",
    )

    assert fig.layout.images[0].source == "/modal-image/test-token"
    assert fig.layout.meta["transport_mode"] == "full_resolution_lossless_png"
    assert fig.layout.meta["source_matrix_shape"] == list(source["psd"].shape)
    assert fig.layout.meta["modal_data_url"] == "/modal-data/test-token"
    assert fig.layout.meta["modal_image_url"] == "/modal-image/test-token"
    assert len(fig.layout.meta["raster_tiles"]) == 1
    assert len(fig.layout.meta["raster_palette"]) == 256
    assert len(fig.data[0].z) == 1


def test_modal_image_figure_tiles_matrices_larger_than_browser_limits():
    source = {
        "psd": np.arange(63, dtype=float).reshape(9, 7),
        "freq": np.linspace(0.0, 800.0, 9),
        "time": np.linspace(0.0, 300.0, 7),
    }

    with patch.object(image_processing, "MODAL_RASTER_TILE_MAX_DIMENSION", 4):
        fig = image_processing.create_spectrogram_figure(
            source,
            "default",
            image_source="/modal-image/test-token?rv=1",
        )

    assert len(fig.layout.images) == 9
    assert len(fig.layout.meta["raster_tiles"]) == 9
    assert all("tile_r0=" in image.source for image in fig.layout.images)
    assert all("tile_c0=" in image.source for image in fig.layout.images)
    assert fig.layout.images[0].x == source["time"][0]
    assert fig.layout.images[-1].y == source["freq"][-1]
    assert fig.layout.meta["raster_tiles"][3]["row_start"] == 2
    assert fig.layout.meta["raster_tiles"][0]["row_end"] == 3
    assert all(
        tile["row_end"] - tile["row_start"] <= 4
        and tile["column_end"] - tile["column_start"] <= 4
        for tile in fig.layout.meta["raster_tiles"]
    )


def test_modal_image_figure_uses_one_viewport_sized_raster():
    source = {
        "psd": np.arange(63, dtype=float).reshape(9, 7),
        "freq": np.linspace(0.0, 800.0, 9),
        "time": np.linspace(0.0, 300.0, 7),
    }

    with patch.object(image_processing, "MODAL_RASTER_TILE_MAX_DIMENSION", 4):
        fig = image_processing.create_spectrogram_figure(
            source,
            "default",
            image_source="/modal-image/test-token?mw=4&mh=3",
            image_target_width=4,
            image_target_height=3,
        )

    assert len(fig.layout.images) == 1
    assert fig.layout.meta["source_matrix_shape"] == [9, 7]
    assert fig.layout.meta["rendered_image_shape"] == [3, 4]
    assert fig.layout.meta["raster_tiles"] == [
        {
            "row_start": 0,
            "row_end": 9,
            "column_start": 0,
            "column_end": 7,
        }
    ]


def test_item_figures_use_recording_specific_ui_revisions():
    source = {
        "psd": np.arange(35, dtype=float).reshape(5, 7),
        "freq": np.linspace(0.0, 200.0, 5),
        "time": np.linspace(0.0, 300.0, 7),
    }

    with patch.object(image_processing, "resolve_item_spectrogram", return_value=source):
        first, _ = create_item_spectrogram_figure(
            {"item_id": "recording-a"},
            {},
            "default",
            image_source="/modal-image/a",
            image_target_width=4,
            image_target_height=3,
        )
        second, _ = create_item_spectrogram_figure(
            {"item_id": "recording-b"},
            {},
            "default",
            image_source="/modal-image/b",
            image_target_width=4,
            image_target_height=3,
        )

    assert first.layout.uirevision != second.layout.uirevision
    assert "recording-a" in first.layout.uirevision
    assert "recording-b" in second.layout.uirevision


def test_modal_image_render_is_downsampled_without_upscaling():
    source = {
        "psd": np.arange(63, dtype=np.float32).reshape(9, 7),
        "freq": np.linspace(0.0, 800.0, 9),
        "time": np.linspace(0.0, 300.0, 7),
    }

    encoded = image_processing._generate_modal_image_from_spectrogram_data(
        source,
        colormap="default",
        color_min=None,
        color_max=None,
        max_width=4,
        max_height=3,
    )
    rendered = imread(BytesIO(base64.b64decode(encoded.split(",", 1)[1])))

    assert rendered.shape[:2] == (3, 4)


def test_image_file_to_base64(mock_root):
    image_dir = Path(mock_root) / "verify" / "dashboard" / "2026-01-07" / "ICLISTENHF0001" / "images"
    image_path = next(image_dir.glob("*.png"))
    src = image_file_to_base64(str(image_path))
    assert src.startswith("data:image/png;base64,")


def test_create_image_file_figure_embeds_existing_spectrogram_image(mock_root):
    image_dir = Path(mock_root) / "verify" / "dashboard" / "2026-01-07" / "ICLISTENHF0001" / "images"
    image_path = next(image_dir.glob("*.png"))

    fig = create_image_file_figure(str(image_path), x_max_seconds=300.0)

    assert fig is not None
    assert fig.layout.images
    assert fig.layout.images[0].source.startswith("data:image/png;base64,")
    assert list(fig.layout.xaxis.range) == [0.0, 300.0]
    assert fig.layout.meta["render_source"] == "image_file"
    assert fig.layout.meta["x_to_seconds"] == 1.0
    assert fig.layout.meta["y_to_hz"] == 1.0


def test_create_item_spectrogram_figure_falls_back_to_image_file_duration(mock_root):
    image_dir = Path(mock_root) / "verify" / "dashboard" / "2026-01-07" / "ICLISTENHF0001" / "images"
    image_path = next(image_dir.glob("*.png"))

    fig, spectrogram = create_item_spectrogram_figure(
        {"spectrogram_path": str(image_path)},
        {},
        "default",
    )

    assert spectrogram is None
    assert fig.layout.meta["render_source"] == "image_file"
    assert list(fig.layout.xaxis.range) == [0.0, 300.0]
    assert fig.layout.xaxis.title.text == "Time (seconds)"


def test_concurrent_audio_spectrogram_requests_share_one_computation(tmp_path):
    audio_path = tmp_path / "shared.wav"
    audio_path.write_bytes(b"audio-placeholder")
    expected = {"psd": object(), "freq": object(), "time": object()}
    calls = 0
    calls_lock = threading.Lock()

    def fake_load(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return expected

    def load_once(_):
        return load_audio_spectrogram_cached(
            str(audio_path),
            win_dur_s=1.0,
            overlap=0.9,
            freq_min_hz=5.0,
            freq_max_hz=100.0,
        )

    with patch.object(image_processing, "_load_audio_spectrogram_torch", side_effect=fake_load):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(load_once, range(8)))

    assert calls == 1
    assert all(result is expected for result in results)


def test_cached_item_image_does_not_rebuild_evicted_spectrogram(tmp_path):
    audio_path = tmp_path / "cached.wav"
    audio_path.write_bytes(b"audio-placeholder")
    item = {"audio_path": str(audio_path)}
    cfg = {
        "spectrogram_render": {
            "source": "audio_generated",
            "win_dur_s": 1.0,
            "overlap": 0.9,
            "freq_min_hz": 5.0,
            "freq_max_hz": 100.0,
        }
    }
    cache_key = image_processing._item_image_generation_key(item, cfg)
    assert cache_key is not None

    with image_processing._IMAGE_CACHE_LOCK:
        image_processing.image_cache[cache_key] = "data:image/png;base64,cached"

    with patch.object(
        image_processing,
        "resolve_item_spectrogram_with_key",
        side_effect=AssertionError("cached image should bypass spectrogram resolution"),
    ):
        result = generate_item_image_cached(item, cfg)

    assert result == "data:image/png;base64,cached"
