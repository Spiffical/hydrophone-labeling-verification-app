from app.layouts.display_controls import create_spectrogram_preset_bar
from app.services.spectrogram_presets import (
    apply_spectrogram_preset,
    find_matching_spectrogram_preset,
    get_spectrogram_presets,
)


def _preset_config():
    return {
        "mode": "verify",
        "spectrogram_render": {
            "source": "audio_generated",
            "win_dur_s": 1.0,
            "overlap": 0.9,
            "freq_min_hz": 5.0,
            "freq_max_hz": 125.0,
            "active_preset": "low",
            "presets": [
                {
                    "id": "low",
                    "label": "Low | 5-125 Hz",
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
        },
    }


def test_spectrogram_presets_are_validated_and_preserve_order():
    presets = get_spectrogram_presets(_preset_config())

    assert [preset["id"] for preset in presets] == ["low", "high"]
    assert presets[0]["freq_max_hz"] == 125.0
    assert presets[1]["win_dur_s"] == 0.1


def test_apply_spectrogram_preset_preserves_unrelated_config():
    cfg = _preset_config()
    cfg["spectrogram_render"]["custom_key"] = "preserved"

    updated = apply_spectrogram_preset(cfg, "high")

    assert updated is not cfg
    assert updated["spectrogram_render"]["active_preset"] == "high"
    assert updated["spectrogram_render"]["win_dur_s"] == 0.1
    assert updated["spectrogram_render"]["freq_min_hz"] == 500.0
    assert updated["spectrogram_render"]["freq_max_hz"] == 8000.0
    assert updated["spectrogram_render"]["source"] == "audio_generated"
    assert updated["spectrogram_render"]["custom_key"] == "preserved"
    assert cfg["spectrogram_render"]["active_preset"] == "low"


def test_item_scoped_recommended_preset_remains_selected():
    cfg = _preset_config()
    cfg["spectrogram_render"]["presets"].append(
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
    )

    updated = apply_spectrogram_preset(cfg, "recommended")

    assert updated["spectrogram_render"]["active_preset"] == "recommended"
    assert find_matching_spectrogram_preset(updated) == "recommended"
    assert get_spectrogram_presets(updated)[-1]["scope"] == "item"
    assert get_spectrogram_presets(updated)[-1]["metadata_key"] == "recommended_spectrogram"


def test_matching_preset_tracks_manual_render_settings():
    cfg = _preset_config()
    assert find_matching_spectrogram_preset(cfg) == "low"

    cfg["spectrogram_render"]["win_dur_s"] = 0.4
    assert find_matching_spectrogram_preset(cfg) is None


def test_invalid_preset_is_ignored():
    cfg = _preset_config()
    cfg["spectrogram_render"]["presets"].append(
        {
            "id": "invalid",
            "win_dur_s": 0.01,
            "overlap": 0.9,
            "freq_min_hz": 100.0,
            "freq_max_hz": 50.0,
        }
    )

    assert [preset["id"] for preset in get_spectrogram_presets(cfg)] == ["low", "high"]
    assert apply_spectrogram_preset(cfg, "invalid") is None


def test_preset_bar_is_hidden_without_configured_presets():
    bar = create_spectrogram_preset_bar("verify", config={})

    assert bar.id == "verify-spectrogram-preset-bar"
    assert bar.style == {"display": "none"}
    assert bar.children[1].options == []


def test_preset_bar_uses_matching_active_preset():
    bar = create_spectrogram_preset_bar("verify", config=_preset_config())
    selector = bar.children[1]

    assert bar.style == {}
    assert selector.id == "verify-spectrogram-preset"
    assert selector.value == "low"
    assert [option["value"] for option in selector.options] == ["low", "high"]
