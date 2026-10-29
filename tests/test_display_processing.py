"""Frequency equalization and peak shrinking (config display.equalize_frequencies and display.shrink)."""

import numpy as np
import pytest

from app.callbacks.ui.display_range_callbacks import _auto_contrast_note
from app.config import _display_processing_config
from app.utils import image_processing
from app.utils.image_processing import (
    _SILENT_DB,
    EQUALIZE_PERCENTILE,
    _generate_image_from_spectrogram_data,
    _prepare_cached_spectrogram,
    equalize_frequency_rows,
    fit_modal_matrix_to_pixel_bounds,
    set_auto_contrast,
    set_display_processing,
)

EQUALIZED_PEAKS = {"equalize_frequencies": True, "shrink": "peak"}


@pytest.fixture(autouse=True)
def plain_afterwards():
    yield
    set_display_processing(None)
    set_auto_contrast(None)


def noise(row_levels_db, columns=8000, seed=0):
    """Noise in dB as a spectrogram shows it: exponential power around each row's level."""
    rng = np.random.default_rng(seed)
    power = rng.exponential(1.0, size=(len(row_levels_db), columns))
    return (10.0 * np.log10(power) + np.asarray(row_levels_db, dtype=float)[:, None]).astype(np.float32)


def test_config_turns_each_part_on():
    assert _display_processing_config({}) == {"equalize_frequencies": False, "shrink": "average"}
    assert _display_processing_config({"equalize_frequencies": True, "shrink": "Peak"}) == EQUALIZED_PEAKS
    assert _display_processing_config({"equalize_frequencies": "yes", "shrink": "max"}) == {
        "equalize_frequencies": True, "shrink": "average",
    }
    assert _display_processing_config({"equalize_frequencies": 1})["equalize_frequencies"] is False
    assert _display_processing_config(None) == {"equalize_frequencies": False, "shrink": "average"}


def test_equalizing_puts_every_rows_background_at_the_same_level():
    levels = [-20.0, -35.0, -50.0, -65.0]
    psd = noise(levels, columns=2000)
    psd[3, 1500:] = _SILENT_DB  # digital silence at the end of one row
    psd = np.vstack([psd, np.full((1, 2000), _SILENT_DB, dtype=np.float32)])  # an all-silent row
    equalized = equalize_frequency_rows(psd)
    heard = equalized[:4] > _SILENT_DB
    for row in range(4):
        assert np.percentile(equalized[row][heard[row]], EQUALIZE_PERCENTILE) == pytest.approx(0.0, abs=1e-4)
        assert np.median(equalized[row][heard[row]]) == pytest.approx(np.median(equalized[0]), abs=0.5)
    assert np.all(equalized[3, 1500:] == _SILENT_DB)
    assert np.all(equalized[4] == _SILENT_DB)
    # A call 15 dB over a quiet row's noise is 15 dB over zero, as one in a loud row is.
    psd = noise(levels, columns=2000)
    psd[0, 100] += 15.0
    psd[3, 100] += 15.0
    equalized = equalize_frequency_rows(psd)
    assert equalized[0, 100] - np.median(equalized[0]) == pytest.approx(psd[0, 100] - np.median(psd[0]), abs=1e-4)
    assert equalized[3, 100] - np.median(equalized[3]) == pytest.approx(psd[3, 100] - np.median(psd[3]), abs=1e-4)


def test_a_long_call_is_not_taken_for_background():
    # A tone 15 dB over the noise for 60% of the clip at its frequency: the row's
    # median is in the call, its quieter quarter is still the noise.
    psd = noise([-40.0, -40.0], columns=1000)
    psd[1, 200:800] = -40.0 + 15.0
    equalized = equalize_frequency_rows(psd)
    # The quieter quarter of that row is partly call, so the call stands about 11 dB over
    # the noise elsewhere (instead of 16.6); a median background would have hidden it.
    assert np.median(equalized[1, 200:800]) - np.median(equalized[0]) > 10.0


def test_cached_spectrograms_are_equalized_only_when_asked():
    set_auto_contrast({"mode": "background", "below_db": 3.0, "above_db": 12.0})
    plain = _prepare_cached_spectrogram({"psd": noise([-20.0, -60.0], columns=500)})
    assert "_frequencies_equalized" not in plain
    assert plain["_color_summary"]["auto_min"] == pytest.approx(np.median(plain["psd"]) - 3.0)

    set_display_processing(EQUALIZED_PEAKS)
    spec = _prepare_cached_spectrogram({"psd": noise([-20.0, -60.0], columns=500)})
    assert spec["_frequencies_equalized"] is True
    assert np.percentile(spec["psd"], EQUALIZE_PERCENTILE, axis=1) == pytest.approx([0.0, 0.0], abs=1e-4)
    # Auto contrast still runs from 3 dB under the (now flat) background to 12 dB over it.
    background = float(np.median(spec["psd"]))
    assert (spec["_color_summary"]["auto_min"], spec["_color_summary"]["auto_max"]) == pytest.approx(
        (background - 3.0, background + 12.0), abs=1e-4
    )


def click_height(shrunk, row, column):
    """How far the pixel holding a click stands over its row's typical level."""
    return float(shrunk[row, column] - np.median(shrunk[row]))


def test_peak_shrinking_keeps_a_one_frame_click_that_averaging_loses():
    psd = noise([-40.0] * 8)
    psd[:, 4000] = -20.0  # a click one frame long, about 20 dB over the noise in every row
    assert click_height(psd, 3, 4000) > 18.0

    averaged = fit_modal_matrix_to_pixel_bounds(psd, max_width=800)
    set_display_processing({"shrink": "peak"})
    peaks = fit_modal_matrix_to_pixel_bounds(psd, max_width=800)
    assert averaged.shape == peaks.shape == (8, 800)
    # 10 frames per pixel: averaging leaves a few dB, the loudest frame keeps most of it.
    assert max(click_height(averaged, 3, c) for c in (399, 400, 401)) < 6.0
    assert click_height(peaks, 3, 400) > 12.0
    # The shrunk background is moved back to where it was, so the colour scale still fits.
    assert np.median(peaks) == pytest.approx(np.median(psd), abs=0.05)


def test_peak_shrinking_keeps_equalized_rows_level_and_silence_silent():
    set_display_processing(EQUALIZED_PEAKS)
    psd = equalize_frequency_rows(noise([-20.0, -50.0, -70.0], columns=4000))
    psd[1, 2000:] = _SILENT_DB
    shrunk = fit_modal_matrix_to_pixel_bounds(psd, max_width=400, max_height=3)
    assert shrunk.shape == (3, 400)
    for row in range(3):  # quiet noise can dip under the silence floor, which is left out
        heard_median = np.median(psd[row][psd[row] > _SILENT_DB])
        assert np.median(shrunk[row][shrunk[row] > _SILENT_DB]) == pytest.approx(heard_median, abs=1e-4)
    assert np.all(shrunk[1, 200:] == _SILENT_DB)
    # Rows are combined too when there are more than pixels; each keeps its loudest cell.
    tall = np.zeros((10, 4), dtype=np.float32)
    tall[7, 2] = 9.0
    squat = fit_modal_matrix_to_pixel_bounds(tall, max_height=5)
    assert squat.shape == (5, 4)
    assert squat[3, 2] == pytest.approx(9.0)


def test_small_rasters_are_never_enlarged():
    set_display_processing(EQUALIZED_PEAKS)
    psd = noise([-30.0, -40.0], columns=50)
    assert fit_modal_matrix_to_pixel_bounds(psd, max_width=800, max_height=600) is psd


def test_grid_cards_draw_with_peak_shrinking():
    set_display_processing(EQUALIZED_PEAKS)
    spec = _prepare_cached_spectrogram({
        "psd": noise([-30.0, -40.0, -50.0], columns=8000),
        "freq": np.array([1000.0, 2000.0, 3000.0]),
        "time": np.linspace(0.0025, 19.9975, 8000),
        "_time_reference": "audio_start",
    })
    image = _generate_image_from_spectrogram_data(spec)
    assert image.startswith("data:image/png;base64,")


def test_changing_the_setting_empties_the_caches():
    image_processing.image_cache["key"] = "an image drawn the old way"
    set_display_processing(EQUALIZED_PEAKS)
    assert "key" not in image_processing.image_cache
    image_processing.image_cache["key"] = "kept"
    set_display_processing(dict(EQUALIZED_PEAKS))  # the same setting again keeps the caches
    assert image_processing.image_cache.get("key") == "kept"
    image_processing.image_cache.clear()


def test_the_contrast_menu_says_what_the_range_is_against():
    background = {"auto_contrast": {"mode": "background", "below_db": 3.0, "above_db": 12.0}}
    assert _auto_contrast_note(background) == (
        "Auto: each spectrogram from 3 dB below its background level to 12 dB above it."
    )
    assert _auto_contrast_note(dict(background, equalize_frequencies=True)) == (
        "Auto: each frequency from 3 dB below its own background level to 12 dB above it."
    )
    at_background = {"auto_contrast": {"mode": "background", "below_db": 0.0, "above_db": 12.0}}
    assert _auto_contrast_note(dict(at_background, equalize_frequencies=True)) == (
        "Auto: each frequency from its own background level to 12 dB above it."
    )
    assert _auto_contrast_note({"auto_contrast": {"mode": "percentile"}}) is None
    assert _auto_contrast_note(None) is None
