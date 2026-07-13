from pathlib import Path

from app.utils.image_processing import (
    create_image_file_figure,
    create_item_spectrogram_figure,
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
