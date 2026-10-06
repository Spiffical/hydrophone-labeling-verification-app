"""Automatic contrast tied to each spectrogram's background (config display.auto_contrast)."""

import numpy as np
import pytest

from app.callbacks.ui.display_range_callbacks import _color_slider_state
from app.config import _auto_contrast_config
from app.utils import image_processing
from app.utils.image_processing import _compute_color_limit_summary, set_auto_contrast

BACKGROUND = {"mode": "background", "below_db": 3.0, "above_db": 12.0}


@pytest.fixture(autouse=True)
def percentile_afterwards():
    yield
    set_auto_contrast(None)


def spectrogram(background_db, calls_db=None, silent_columns=0, shape=(96, 400), seed=0):
    """Background noise around ``background_db`` with a few loud pulses and some digital silence."""
    rng = np.random.default_rng(seed)
    psd = rng.normal(background_db, 2.0, size=shape).astype(np.float32)
    if calls_db is not None:
        psd[20:30, 100:110] = calls_db
        psd[60:70, 300:310] = calls_db
    if silent_columns:
        psd[:, -silent_columns:] = -100.0
    return psd


def test_config_chooses_the_mode():
    assert _auto_contrast_config({}) == {"mode": "percentile", "below_db": 3.0, "above_db": 12.0}
    assert _auto_contrast_config({"auto_contrast": "background"}) == BACKGROUND
    assert _auto_contrast_config({"auto_contrast": {"mode": "Background", "below_db": 2, "above_db": 15}}) == {
        "mode": "background", "below_db": 2.0, "above_db": 15.0,
    }
    assert _auto_contrast_config({"auto_contrast": {"mode": "background", "below_db": "loud", "above_db": -4}}) == BACKGROUND
    assert _auto_contrast_config({"auto_contrast": {"mode": "fancy"}})["mode"] == "percentile"


def test_background_mode_follows_each_clips_background():
    set_auto_contrast(BACKGROUND)
    for level in (-42.0, -27.0, -16.0):
        summary = _compute_color_limit_summary(spectrogram(level, calls_db=level + 20))
        assert summary["auto_min"] == pytest.approx(level - 3.0, abs=0.2)
        assert summary["auto_max"] == pytest.approx(level + 12.0, abs=0.2)
        # Calls 20 dB over the background are at the top of the scale.
        assert level + 20 > summary["auto_max"]


def test_digital_silence_does_not_drag_the_background_down():
    set_auto_contrast(BACKGROUND)
    summary = _compute_color_limit_summary(spectrogram(-30.0, silent_columns=250))
    assert summary["auto_min"] == pytest.approx(-33.0, abs=0.3)
    assert summary["data_min"] == -100.0
    silent = _compute_color_limit_summary(np.full((10, 10), -100.0, dtype=np.float32))
    assert (silent["auto_min"], silent["auto_max"]) == (-103.0, -88.0)


def test_percentile_mode_is_unchanged_and_switching_empties_the_caches():
    psd = spectrogram(-30.0, calls_db=-5.0)
    expected = tuple(float(v) for v in np.percentile(psd, [2, 98]))
    summary = _compute_color_limit_summary(psd)
    assert (summary["auto_min"], summary["auto_max"]) == pytest.approx(expected)

    image_processing.image_cache["key"] = "an image with the old contrast"
    set_auto_contrast(BACKGROUND)
    assert "key" not in image_processing.image_cache
    image_processing.image_cache["key"] = "kept"
    set_auto_contrast(dict(BACKGROUND))  # the same setting again keeps the caches
    assert image_processing.image_cache.get("key") == "kept"
    image_processing.image_cache.clear()


def test_the_contrast_menu_says_how_auto_is_set():
    summary = {"color_data_min": -100.0, "color_data_max": 0.0, "color_auto_min": -45.0, "color_auto_max": -15.0}
    note = "Auto: each spectrogram from 3 dB below its background level to 12 dB above it."
    state = _color_slider_state("verify", summary, None, None, None, auto_note=note)
    assert (state[4], state[5], state[6], state[7]) == ("Auto contrast", note, None, None)
    plain = _color_slider_state("verify", summary, None, None, None)
    assert plain[5].startswith("Automatic range for this page")
