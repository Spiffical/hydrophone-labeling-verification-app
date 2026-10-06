"""A dashboard's own default contrast (config display colorbar_min/max)."""

from app.callbacks.ui.display_range_callbacks import _color_slider_state
from app.config import _default_contrast
from app.layouts.display_controls import create_display_range_bar

FIN = {"colorbar_min": -33.9, "colorbar_max": -21.9}
# A page of spectrograms whose data run -60 to -5 dB/Hz, automatic -45 to -15.
SUMMARY = {"color_data_min": -60.0, "color_data_max": -5.0, "color_auto_min": -45.0, "color_auto_max": -15.0}


def _walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    if component is None or isinstance(component, (str, int, float)):
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _by_id(component, wanted):
    return next(node for node in _walk(component) if getattr(node, "id", None) == wanted)


def test_a_default_contrast_needs_both_ends_in_order():
    assert _default_contrast({"display_unrelated": 1}) == {"colorbar_min": None, "colorbar_max": None}
    assert _default_contrast(FIN) == {"colorbar_min": -33.9, "colorbar_max": -21.9}
    assert _default_contrast({"colorbar_min": "-33.9", "colorbar_max": "-21.9"}) == FIN
    for broken in ({"colorbar_min": -33.9}, {"colorbar_min": -21.9, "colorbar_max": -33.9},
                   {"colorbar_min": "loud", "colorbar_max": -21.9}, {"colorbar_min": float("nan"), "colorbar_max": 0}):
        assert _default_contrast(broken) == {"colorbar_min": None, "colorbar_max": None}


def test_spectrograms_open_with_the_dashboard_contrast_and_reset_returns_to_it():
    bar = create_display_range_bar("verify", display_cfg=FIN, compact=True)
    assert (_by_id(bar, "verify-colorbar-min-input").value, _by_id(bar, "verify-colorbar-max-input").value) == (-33.9, -21.9)
    assert _by_id(bar, "verify-colorbar-reset-btn").children == "Default"

    reset = _color_slider_state("verify", SUMMARY, -40.0, -30.0, "verify-colorbar-reset-btn", default_range=(-33.9, -21.9))
    assert (reset[6], reset[7]) == (-33.9, -21.9)
    assert reset[4] == "-33.9 dB/Hz to -21.9 dB/Hz"
    assert reset[5].startswith("Default: -33.9 dB/Hz to -21.9 dB/Hz.")


def test_without_one_contrast_stays_automatic():
    bar = create_display_range_bar("verify", display_cfg={}, compact=True)
    assert _by_id(bar, "verify-colorbar-min-input").value is None
    assert _by_id(bar, "verify-colorbar-reset-btn").children == "Auto"
    reset = _color_slider_state("verify", SUMMARY, -40.0, -30.0, "verify-colorbar-reset-btn")
    assert (reset[4], reset[6], reset[7]) == ("Auto contrast", None, None)


def test_a_dashboard_config_keeps_its_contrast(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "data:\n  mode: verify\n  data_dir: {}\n"
        "display:\n  y_axis_scale: linear\n  colorbar_min: -33.9\n  colorbar_max: -21.9\n".format(tmp_path)
    )
    monkeypatch.setattr("sys.argv", ["run.py", "--config", str(config_file)])
    from app.config import get_config

    display = get_config()["display"]
    assert (display["colorbar_min"], display["colorbar_max"]) == (-33.9, -21.9)
