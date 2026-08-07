from unittest.mock import patch

import numpy as np

from app.main import create_app
from app.utils.image_processing import create_spectrogram_figure, summarize_spectrogram_display_ranges
from app.utils.image_utils import (
    build_item_image_request_src,
    build_modal_image_request_src,
    decode_item_image_request,
    get_item_image_src,
    use_full_resolution_modal_image,
)
from app.layouts.display_controls import create_display_range_bar
from app.callbacks.modal.display_helpers import build_modal_display_range_ui, resolve_mode_value
from app.callbacks.ui.display_range_callbacks import _frequency_slider_state


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
    assert fig.layout.xaxis.showgrid is False
    assert fig.layout.yaxis.showgrid is False


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


def test_modal_image_request_uses_separate_full_resolution_route():
    src = build_modal_image_request_src(
        {"mat_path": "/tmp/example.mat"},
        color_min=-72.0,
        color_max=-18.0,
    )

    assert src.startswith("/modal-image/")
    token = src.split("/modal-image/", 1)[1].split("?", 1)[0]
    payload = decode_item_image_request(token)
    assert payload["mat_path"] == "/tmp/example.mat"
    assert payload["color_min"] == -72.0
    assert payload["color_max"] == -18.0


def test_modal_data_route_returns_full_float_matrix(mock_config):
    source = build_modal_image_request_src({"mat_path": "/tmp/example.mat"})
    data_url = source.replace("/modal-image/", "/modal-data/", 1)
    expected = np.arange(35, dtype="<f4").reshape(5, 7)
    app = create_app(mock_config)

    with patch("app.main.resolve_item_modal_matrix", return_value=expected):
        response = app.server.test_client().get(data_url)

    assert response.status_code == 200
    assert response.headers["X-Spectrogram-Rows"] == "5"
    assert response.headers["X-Spectrogram-Columns"] == "7"
    assert response.headers["X-Spectrogram-Dtype"] == "float32-le"
    assert np.array_equal(np.frombuffer(response.data, dtype="<f4").reshape(5, 7), expected)


def test_full_resolution_modal_image_falls_back_for_log_axes():
    cfg = {"display": {"modal_render_mode": "full_resolution_image"}}

    assert use_full_resolution_modal_image(cfg, "linear") is True
    assert use_full_resolution_modal_image(cfg, "log") is False


def test_get_item_image_src_uses_dynamic_render_when_contrast_changes_even_if_image_src_exists():
    item = {
        "image_src": "data:image/png;base64,existing",
        "mat_path": "/tmp/example.mat",
        "spectrogram_path": "/tmp/example.png",
    }

    with patch("app.utils.image_utils.generate_item_image_cached", return_value="data:image/png;base64,dynamic"):
        result = get_item_image_src(
            item,
            color_min=-72.0,
            color_max=-18.0,
            cfg={},
        )

    assert result.startswith("/item-image/")
    token = result.split("/item-image/", 1)[1].split("?", 1)[0]
    payload = decode_item_image_request(token)
    assert payload["mat_path"] == "/tmp/example.mat"
    assert payload["color_min"] == -72.0
    assert payload["color_max"] == -18.0


def test_get_item_image_src_defers_existing_mat_rendering_to_image_route():
    item = {
        "item_id": "example",
        "mat_path": "/tmp/example.mat",
    }

    with patch("app.utils.image_utils.generate_item_image_cached") as generate:
        result = get_item_image_src(item, cfg={"spectrogram_render": {"source": "existing"}})

    assert result.startswith("/item-image/")
    generate.assert_not_called()


def test_get_item_image_src_uses_audio_generation_settings_in_request_url():
    item = {
        "image_src": "data:image/png;base64,existing",
        "audio_path": "/tmp/example.wav",
        "spectrogram_path": "/tmp/example.png",
    }

    result = get_item_image_src(
        item,
        cfg={
            "spectrogram_render": {
                "source": "audio_generated",
                "overlap": 0.5,
            }
        },
    )

    assert "src=audio_generated" in result
    assert "ov=0.5" in result
    token = result.split("/item-image/", 1)[1].split("?", 1)[0]
    payload = decode_item_image_request(token)
    assert payload["render_cfg"]["source"] == "audio_generated"
    assert payload["render_cfg"]["overlap"] == 0.5


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
    summary = controls.children[0]

    assert controls.id == "verify-display-settings-details"
    assert controls.open is False
    assert summary.id == "verify-display-settings-summary"
    assert summary.n_clicks == 0


def test_resolve_mode_value_selects_the_active_page_control():
    values = {"label": "label value", "verify": "verify value", "explore": "explore value"}

    assert resolve_mode_value("label", **values) == "label value"
    assert resolve_mode_value("verify", **values) == "verify value"
    assert resolve_mode_value("explore", **values) == "explore value"


def test_modal_display_ranges_describe_inherited_page_settings():
    figure = {
        "layout": {
            "meta": {
                "positive_y_min_hz": 1.0,
                "data_y_max_hz": 1000.0,
                "display_y_min_hz": 10.0,
                "display_y_max_hz": 500.0,
                "data_color_min": -120.0,
                "data_color_max": 0.0,
                "auto_color_min": -90.0,
                "auto_color_max": -10.0,
                "display_color_min": -75.0,
                "display_color_max": -20.0,
            }
        }
    }

    ui = build_modal_display_range_ui(
        figure,
        modal_y_min=None,
        modal_y_max=None,
        inherited_y_min=10.0,
        inherited_y_max=500.0,
        modal_color_min=None,
        modal_color_max=None,
        inherited_color_min=-75.0,
        inherited_color_max=-20.0,
    )

    assert ui["y_readout"] == "Using page range: 10.0 Hz to 500 Hz"
    assert ui["color_slider_value"] == [-75.0, -20.0]
    assert ui["color_readout"] == "Using page contrast: -75.0 dB/Hz to -20.0 dB/Hz"

    partial_ui = build_modal_display_range_ui(
        figure,
        modal_y_min=None,
        modal_y_max=None,
        inherited_y_min=None,
        inherited_y_max=None,
        modal_color_min=None,
        modal_color_max=None,
        inherited_color_min=-75.0,
        inherited_color_max=None,
    )
    assert partial_ui["color_slider_value"] == [-75.0, -20.0]


def test_modal_display_controls_use_the_page_ranges_stored_on_the_figure():
    figure = {
        "layout": {
            "meta": {
                "positive_y_min_hz": 1.0,
                "data_y_max_hz": 25590.0,
                "display_y_min_hz": 30.338912,
                "display_y_max_hz": 25589.983155,
                "data_color_min": -90.0,
                "data_color_max": -5.0,
                "auto_color_min": -80.0,
                "auto_color_max": -10.0,
                "display_color_min": 39.6,
                "display_color_max": 76.36,
                "uses_page_y_range": True,
                "uses_page_color_range": True,
                "page_display_y_min_hz": 30.338912,
                "page_display_y_max_hz": 25589.983155,
                "page_display_color_min": 39.6,
                "page_display_color_max": 76.36,
            }
        }
    }

    ui = build_modal_display_range_ui(
        figure,
        modal_y_min=None,
        modal_y_max=None,
        inherited_y_min=None,
        inherited_y_max=None,
        modal_color_min=None,
        modal_color_max=None,
        inherited_color_min=None,
        inherited_color_max=None,
    )

    assert ui["y_readout"].startswith("Using page range:")
    assert ui["color_readout"] == "Using page contrast: 39.6 dB/Hz to 76.4 dB/Hz"
    assert ui["color_slider_value"] == [39.6, 76.36]
    assert ui["color_slider_max"] == 76.36
    assert ui["y_manual_max"] == 25590.0


def test_modal_display_controls_preserve_automatic_item_contrast():
    figure = {
        "layout": {
            "meta": {
                "positive_y_min_hz": 1.0,
                "data_y_max_hz": 25590.0,
                "display_y_min_hz": 1.0,
                "display_y_max_hz": 25590.0,
                "data_color_min": 5.0,
                "data_color_max": 90.0,
                "auto_color_min": 39.6,
                "auto_color_max": 76.36,
                "display_color_min": 39.6,
                "display_color_max": 76.36,
                "uses_page_y_range": True,
                "uses_page_color_range": True,
                "page_display_y_min_hz": None,
                "page_display_y_max_hz": None,
                "page_display_color_min": None,
                "page_display_color_max": None,
            }
        }
    }

    ui = build_modal_display_range_ui(
        figure,
        modal_y_min=None,
        modal_y_max=None,
        inherited_y_min=None,
        inherited_y_max=None,
        modal_color_min=None,
        modal_color_max=None,
        inherited_color_min=None,
        inherited_color_max=None,
    )

    assert ui["color_readout"] == "Auto contrast"
    assert ui["color_slider_value"] == [39.6, 76.36]
    assert ui["color_manual_min"] == 39.6
    assert ui["color_manual_max"] == 76.4


def test_page_frequency_manual_value_is_derived_from_the_slider_position():
    state = _frequency_slider_state(
        "verify",
        {
            "freq_positive_min_hz": 30.338912,
            "freq_data_max_hz": 25589.95,
        },
        None,
        None,
        None,
    )

    assert state[10] == 25590.0
