from types import SimpleNamespace
from unittest.mock import patch

from dash import no_update

import app.callbacks.ui.display_range_callbacks as display_range_callbacks

CFG = {"spectrogram_render": {"source": "audio_generated", "freq_min_hz": 5.0, "freq_max_hz": 100.0}}
VALUE_OUTPUTS = {3: "y slider", 6: "y min", 7: "y max", 13: "colour slider", 16: "colour min", 17: "colour max"}


def build(*current):
    with patch.object(display_range_callbacks, "ctx", SimpleNamespace(triggered_id="verify-display-settings-summary")):
        return display_range_callbacks._build_display_range_outputs("verify", [], CFG, *current)


def test_opening_the_spectrogram_menu_resends_only_changed_values():
    # The grid is rendered from these values; re-sending one unchanged
    # re-rendered every card and reloaded its image.
    # First open: the sliders get their values; the full range needs no limits.
    first = build(None, None, None, None)
    assert first[3] is not no_update and first[13] is not no_update
    assert all(first[index] is no_update for index in (6, 7, 16, 17))
    # Opening it again changes nothing, so nothing downstream runs.
    again = build(None, None, None, None, first[3], first[13])
    assert {VALUE_OUTPUTS[index] for index in VALUE_OUTPUTS if again[index] is no_update} == set(VALUE_OUTPUTS.values())
    # Everything else (ranges, marks, readouts) is still refreshed.
    assert again[0] == first[0] and again[2] == first[2] and again[4] == first[4]
    # A limit outside this page's range is still clamped and sent.
    stale = build(None, None, -200.0, None, first[3], first[13])
    assert stale[16] == -120.0 and stale[13] is not no_update


def test_same_value_compares_numbers_and_ranges_loosely():
    same = display_range_callbacks._same_value
    assert same([5, 100], [5.0, 100.0]) and same(None, None) and same("12.5", 12.5)
    assert not same([5, 100], [5, 90]) and not same(None, 0) and not same(5, None)
