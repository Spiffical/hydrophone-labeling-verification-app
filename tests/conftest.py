from pathlib import Path
import sys
import pytest


@pytest.fixture(scope="session")
def mock_root():
    return Path(__file__).resolve().parents[1] / "data" / "mock"


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def mock_config(mock_root):
    return {
        "mode": "label",
        "label": {
            "folder": str(mock_root / "label" / "mat_files"),
            "audio_folder": str(mock_root / "label" / "audio"),
            "output_file": str(mock_root / "label" / "labels.json"),
        },
        "verify": {
            "dashboard_root": str(mock_root / "verify" / "dashboard"),
            "date": "2026-01-07",
            "hydrophone": "ICLISTENHF0001",
        },
        "whale": {
            "predictions_json": str(mock_root / "whale" / "predictions.json"),
        },
        "display": {
            "items_per_page": 25,
            "colormap": "default",
            "y_axis_scale": "linear",
        },
        "cache": {
            "max_size": 64,
        },
    }
