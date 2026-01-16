from pathlib import Path

from app.utils.image_processing import load_spectrogram_cached, generate_image_cached
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

