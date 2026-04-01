from unittest.mock import patch

import numpy as np

from app.utils.image_processing import create_spectrogram_figure, summarize_spectrogram_display_ranges
from app.utils.image_utils import build_item_image_request_src, decode_item_image_request, get_item_image_src


def test_create_spectrogram_figure_applies_linear_y_limits_and_colorbar_limits():
    spectrogram = {
        "psd": np.array(
            [
                [-90.0, -70.0, -50.0],
                [-80.0, -60.0, -40.0],
                [-70.0, -50.0, -30.0],
                [-60.0, -40.0, -20.0],
                [-50.0, -30.0, -10.0],
            ],
            dtype=float,
        ),
        "freq": np.array([0.0, 50.0, 100.0, 150.0, 200.0], dtype=float),
        "time": np.array([0.0, 1.0, 2.0], dtype=float),
    }

    fig = create_spectrogram_figure(
        spectrogram,
        "default",
        "linear",
        y_axis_min_hz=50.0,
        y_axis_max_hz=150.0,
        color_min=-75.0,
        color_max=-15.0,
    )

    assert list(fig.layout.yaxis.range) == [50.0, 150.0]
    assert fig.data[0].zmin == -75.0
    assert fig.data[0].zmax == -15.0
    assert fig.layout.meta["display_y_min_hz"] == 50.0
    assert fig.layout.meta["display_y_max_hz"] == 150.0
    assert fig.layout.meta["display_color_min"] == -75.0
    assert fig.layout.meta["display_color_max"] == -15.0


def test_create_spectrogram_figure_applies_log_y_limits_in_plotly_log_space():
    spectrogram = {
        "psd": np.array(
            [
                [-90.0, -85.0],
                [-80.0, -75.0],
                [-70.0, -65.0],
                [-60.0, -55.0],
            ],
            dtype=float,
        ),
        "freq": np.array([1.0, 10.0, 100.0, 1000.0], dtype=float),
        "time": np.array([0.0, 1.0], dtype=float),
    }

    fig = create_spectrogram_figure(
        spectrogram,
        "default",
        "log",
        y_axis_min_hz=10.0,
        y_axis_max_hz=1000.0,
    )

    assert fig.layout.yaxis.type == "log"
    assert np.allclose(list(fig.layout.yaxis.range), [1.0, 3.0])
    assert fig.layout.meta["display_y_min_hz"] == 10.0
    assert fig.layout.meta["display_y_max_hz"] == 1000.0


def test_item_image_request_payload_includes_custom_y_axis_limits():
    src = build_item_image_request_src(
        {
            "audio_path": "/tmp/example.wav",
            "mat_path": "/tmp/example.mat",
            "spectrogram_path": "/tmp/example.png",
        },
        colormap="hydrophone",
        y_axis_scale="log",
        y_axis_min_hz=12.5,
        y_axis_max_hz=240.0,
        color_min=-72.0,
        color_max=-18.0,
    )

    token = src.split("/item-image/", 1)[1].split("?", 1)[0]
    payload = decode_item_image_request(token)

    assert payload["colormap"] == "hydrophone"
    assert payload["y_axis_scale"] == "log"
    assert payload["y_axis_min_hz"] == 12.5
    assert payload["y_axis_max_hz"] == 240.0
    assert payload["color_min"] == -72.0
    assert payload["color_max"] == -18.0


def test_get_item_image_src_uses_dynamic_render_when_contrast_changes_even_if_image_src_exists():
    item = {
        "image_src": "data:image/png;base64,existing",
        "spectrogram_path": "/tmp/example.png",
    }

    with patch("app.utils.image_utils.generate_item_image_cached", return_value="data:image/png;base64,dynamic"):
        result = get_item_image_src(
            item,
            color_min=-72.0,
            color_max=-18.0,
            cfg={},
        )

    assert result == "data:image/png;base64,dynamic"


def test_summarize_spectrogram_display_ranges_reports_frequency_and_color_bounds():
    summary = summarize_spectrogram_display_ranges(
        {
            "psd": np.array(
                [
                    [-100.0, -80.0, -60.0],
                    [-90.0, -70.0, -50.0],
                    [-80.0, -60.0, -40.0],
                ],
                dtype=float,
            ),
            "freq": np.array([0.0, 25.0, 125.0], dtype=float),
            "time": np.array([0.0, 1.0, 2.0], dtype=float),
        }
    )

    assert summary["freq_data_min_hz"] == 0.0
    assert summary["freq_data_max_hz"] == 125.0
    assert summary["freq_positive_min_hz"] == 25.0
    assert summary["color_data_min"] == -100.0
    assert summary["color_data_max"] == -40.0
    assert -100.0 <= summary["color_auto_min"] <= -80.0
    assert -60.0 <= summary["color_auto_max"] <= -40.0
