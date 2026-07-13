from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from unittest.mock import patch

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
