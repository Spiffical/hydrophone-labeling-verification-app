"""The page's frequency window shows only where it changes what is drawn, and
the modal has none: its spectrograms take their band from the visible ranges."""

import pytest
from dash.exceptions import PreventUpdate

from app.callbacks.data.render_callbacks import _page_frequency_window
from app.components.modal import create_spectrogram_modal
from app.layouts.display_controls import create_display_range_bar
from app.main import create_app
from app.services.spectrogram_ranges import resolve_visible_spectrogram_ranges, uses_visible_ranges

# Spectrograms drawn from audio (every review dashboard), and spectrogram
# files made beforehand.
FROM_AUDIO = {"spectrogram_render": {"source": "audio_generated", "win_dur_s": 1.0, "overlap": 0.9,
                                     "freq_min_hz": 5.0, "freq_max_hz": 100.0}}
FROM_FILES = {"spectrogram_render": {"source": "existing"}}

REMOVED_MODAL_IDS = {
    "modal-yaxis-slider",
    "modal-yaxis-readout",
    "modal-yaxis-hint",
    "modal-yaxis-reset-btn",
    "modal-yaxis-manual-min-input",
    "modal-yaxis-manual-max-input",
    "modal-yaxis-min-input",
    "modal-yaxis-max-input",
}


def _find(node, target_id):
    if getattr(node, "id", None) == target_id:
        return node
    children = getattr(node, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children] if children is not None else []
    for child in children:
        found = _find(child, target_id)
        if found is not None:
            return found
    return None


def _ids(node):
    found = set()
    node_id = getattr(node, "id", None)
    if isinstance(node_id, str):
        found.add(node_id)
    children = getattr(node, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children] if children is not None else []
    for child in children:
        found |= _ids(child)
    return found


def test_ranges_are_in_use_only_for_spectrograms_drawn_from_audio():
    assert uses_visible_ranges(FROM_AUDIO) is True
    assert uses_visible_ranges(FROM_FILES) is False
    assert uses_visible_ranges({}) is False
    assert uses_visible_ranges(None) is False
    assert uses_visible_ranges({"spectrogram_render": None}) is False
    # The same check decides whether any ranges are drawn.
    assert resolve_visible_spectrogram_ranges({}, FROM_FILES, None) == []
    assert resolve_visible_spectrogram_ranges({}, FROM_AUDIO, None)


@pytest.mark.parametrize("prefix", ["label", "verify", "explore"])
@pytest.mark.parametrize("compact", [False, True])
def test_the_page_window_is_hidden_when_visible_ranges_set_the_bands(prefix, compact):
    with_ranges = create_display_range_bar(prefix, compact=compact, config=FROM_AUDIO)
    group = _find(with_ranges, f"{prefix}-frequency-window-group")
    assert group is not None and group.hidden is True
    # Its controls stay in the page for the callbacks that read them.
    assert _find(with_ranges, f"{prefix}-yaxis-slider") is not None
    assert _find(with_ranges, f"{prefix}-spectrogram-extra-presets") is not None

    with_files = create_display_range_bar(prefix, compact=compact, config=FROM_FILES)
    assert _find(with_files, f"{prefix}-frequency-window-group").hidden is False


def test_the_page_window_follows_the_spectrogram_source(mock_config):
    app = create_app(mock_config)
    for prefix in ("label", "verify", "explore"):
        entries = [
            entry for entry in app._callback_list
            if entry.get("output") == f"{prefix}-frequency-window-group.hidden"
        ]
        assert len(entries) == 1, prefix
        assert [(i["id"], i["property"]) for i in entries[0]["inputs"]] == [("config-store", "data")]


def test_the_grid_ignores_the_page_window_when_visible_ranges_set_the_bands():
    window = {"verify-yaxis-min-input.value": "verify-yaxis-min-input"}
    both = {**window, "verify-yaxis-max-input.value": "verify-yaxis-max-input"}
    page = {"verify-current-page.data": "verify-current-page"}

    # Spectrogram files made beforehand: the window picks the band.
    assert _page_frequency_window("verify", FROM_FILES, 300.0, 800.0, window) == (300.0, 800.0)

    # With visible ranges, a change to nothing but the window redraws nothing...
    with pytest.raises(PreventUpdate):
        _page_frequency_window("verify", FROM_AUDIO, 300.0, 800.0, window)
    with pytest.raises(PreventUpdate):
        _page_frequency_window("verify", FROM_AUDIO, None, None, both)
    # ...and other redraws leave it out.
    assert _page_frequency_window("verify", FROM_AUDIO, 300.0, 800.0, page) == (None, None)
    assert _page_frequency_window("verify", FROM_AUDIO, 300.0, 800.0, {**window, **page}) == (None, None)
    assert _page_frequency_window("verify", FROM_AUDIO, 300.0, 800.0, {}) == (None, None)
    # Another page's window is not this page's.
    assert _page_frequency_window(
        "label", FROM_AUDIO, 300.0, 800.0, window,
    ) == (None, None)


def test_the_modal_has_no_frequency_window(mock_config):
    modal_ids = _ids(create_spectrogram_modal(mock_config))
    assert not modal_ids & REMOVED_MODAL_IDS
    # Contrast stays.
    assert {
        "modal-colorbar-slider",
        "modal-colorbar-readout",
        "modal-colorbar-reset-btn",
        "modal-colorbar-manual-min-input",
        "modal-colorbar-manual-max-input",
        "modal-colorbar-min-input",
        "modal-colorbar-max-input",
    } <= modal_ids

    app = create_app(mock_config)
    for entry in app._callback_list:
        referenced = [entry.get("output", "")] + [
            str(item.get("id")) for item in entry.get("inputs", []) + entry.get("state", [])
        ]
        assert not any("modal-yaxis-" in ref for ref in referenced), entry.get("output")
