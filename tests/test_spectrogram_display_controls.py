from unittest.mock import patch

import numpy as np

from app.utils.image_processing import (
    create_spectrogram_figure,
    get_item_spectrogram_render_settings,
    summarize_spectrogram_display_ranges,
)
from app.utils.image_utils import build_item_image_request_src, decode_item_image_request, get_item_image_src
from app.layouts.display_controls import create_display_range_bar


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


def test_item_image_request_uses_json_recommended_spectrogram():
    cfg = {
        "spectrogram_render": {
            "source": "audio_generated",
            "active_preset": "recommended",
            "win_dur_s": 1.0,
            "overlap": 0.9,
            "freq_min_hz": 5.0,
            "freq_max_hz": 125.0,
            "presets": [
                {
                    "id": "recommended",
                    "label": "Recommended",
                    "scope": "item",
                    "metadata_key": "recommended_spectrogram",
                    "win_dur_s": 1.0,
                    "overlap": 0.9,
                    "freq_min_hz": 5.0,
                    "freq_max_hz": 125.0,
                }
            ],
        }
    }
    item = {
        "audio_path": "/tmp/example.wav",
        "metadata": {
            "recommended_spectrogram": {
                "label": "Mid | 100-2,000 Hz",
                "win_dur_s": 0.25,
                "overlap": 0.9,
                "freq_min_hz": 100.0,
                "freq_max_hz": 2000.0,
            }
        },
    }

    settings = get_item_spectrogram_render_settings(item, cfg)
    src = build_item_image_request_src(item, cfg=cfg)
    token = src.split("/item-image/", 1)[1].split("?", 1)[0]
    payload = decode_item_image_request(token)

    assert settings["item_override_applied"] is True
    assert settings["win_dur_s"] == 0.25
    assert settings["freq_min_hz"] == 100.0
    assert settings["freq_max_hz"] == 2000.0
    assert payload["render_cfg"]["freq_min_hz"] == 100.0
    assert payload["render_cfg"]["freq_max_hz"] == 2000.0


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


def test_display_range_analysis_is_collapsed_by_default():
    controls = create_display_range_bar("verify")
    details = controls.children[0]
    content = details.children[1]
    colormap_row = content.children[1]
    selector = colormap_row.children[1]
    summary = details.children[0]

    assert controls.id == "verify-display-controls"
    assert details.id == "verify-display-settings-details"
    assert details.open is False
    assert selector.id == "verify-colormap-toggle"
    assert selector.value == "default"
    assert [option["value"] for option in selector.options] == ["default", "hydrophone"]
    assert summary.id == "verify-display-settings-summary"
    assert summary.n_clicks == 0


def test_display_settings_contains_presets_and_custom_frequency_controls():
    cfg = {
        "spectrogram_render": {
            "active_preset": "recommended",
            "win_dur_s": 1.0,
            "overlap": 0.9,
            "freq_min_hz": 5.0,
            "freq_max_hz": 125.0,
            "presets": [
                {
                    "id": "recommended",
                    "label": "Recommended",
                    "scope": "item",
                    "win_dur_s": 1.0,
                    "overlap": 0.9,
                    "freq_min_hz": 5.0,
                    "freq_max_hz": 125.0,
                },
                {
                    "id": "high",
                    "label": "High | 500-8,000 Hz",
                    "win_dur_s": 0.1,
                    "overlap": 0.9,
                    "freq_min_hz": 500.0,
                    "freq_max_hz": 8000.0,
                },
            ],
        }
    }

    controls = create_display_range_bar("verify", config=cfg)
    details = controls.children[0]
    content = details.children[1]
    preset_bar = content.children[0]
    frequency_group = content.children[3].children[0]

    assert preset_bar.id == "verify-spectrogram-preset-bar"
    assert preset_bar.children[1].id == "verify-spectrogram-preset"
    assert preset_bar.children[1].value == "recommended"
    assert [option["value"] for option in preset_bar.children[1].options] == [
        "recommended",
        "high",
    ]
    assert frequency_group.children[0].children[0].children == "Custom frequency window (Hz)"
