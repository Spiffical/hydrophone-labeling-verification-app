from app.layouts.display_controls import create_spectrogram_preset_bar
from app.callbacks.ui.spectrogram_preset_callbacks import _selected_preset_value
from app.services.spectrogram_presets import (
    apply_spectrogram_preset,
    find_matching_spectrogram_preset,
    get_item_spectrogram_recommendation,
    get_spectrogram_presets,
)
from app.services.verify_modal_cache import (
    has_verify_spectrogram_recommendations,
    register_verify_modal_items,
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
                    "id": "recommended",
                    "label": "Recommended",
                    "scope": "item",
                    "metadata_key": "recommended_spectrogram",
                    "win_dur_s": 1.0,
                    "overlap": 0.9,
                    "freq_min_hz": 5.0,
                    "freq_max_hz": 125.0,
                },
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

    assert [preset["id"] for preset in presets] == ["recommended", "low", "high"]
    assert presets[0]["scope"] == "item"
    assert presets[2]["win_dur_s"] == 0.1


def test_apply_spectrogram_preset_preserves_unrelated_config():
    cfg = _preset_config()
    cfg["spectrogram_render"]["custom_key"] = "preserved"

    updated = apply_spectrogram_preset(cfg, "high")

    assert updated["spectrogram_render"]["active_preset"] == "high"
    assert updated["spectrogram_render"]["freq_min_hz"] == 500.0
    assert updated["spectrogram_render"]["freq_max_hz"] == 8000.0
    assert updated["spectrogram_render"]["custom_key"] == "preserved"
    assert cfg["spectrogram_render"]["active_preset"] == "low"


def test_recommended_metadata_is_validated():
    preset = get_spectrogram_presets(_preset_config())[0]
    item = {
        "metadata": {
            "recommended_spectrogram": {
                "win_dur_s": 0.25,
                "overlap": 0.9,
                "freq_min_hz": 100.0,
                "freq_max_hz": 2000.0,
            }
        }
    }

    recommendation = get_item_spectrogram_recommendation(item, preset)

    assert recommendation["win_dur_s"] == 0.25
    assert recommendation["freq_max_hz"] == 2000.0


def test_recommended_availability_reflects_cached_predictions_metadata():
    cache_key = register_verify_modal_items(
        {
            "load_timestamp": "preset-availability",
            "items": [
                {
                    "item_id": "with-recommendation",
                    "metadata": {
                        "recommended_spectrogram": {
                            "win_dur_s": 1.0,
                            "overlap": 0.9,
                            "freq_min_hz": 5.0,
                            "freq_max_hz": 125.0,
                        }
                    },
                }
            ],
            "summary": {},
        }
    )

    assert has_verify_spectrogram_recommendations(cache_key) is True
    assert has_verify_spectrogram_recommendations("missing-cache") is False


def test_recommended_option_starts_disabled_until_dataset_is_loaded():
    cfg = _preset_config()
    cfg["spectrogram_render"]["active_preset"] = "recommended"

    bar = create_spectrogram_preset_bar("verify", config=cfg)
    selector = bar.children[1]

    assert selector.value == "custom"
    assert selector.options[0]["value"] == "recommended"
    assert selector.options[0]["disabled"] is True
    assert selector.options[-1] == {"label": "Custom", "value": "custom"}
    assert find_matching_spectrogram_preset(cfg) == "recommended"


def test_explicit_custom_selection_overrides_numeric_preset_matching():
    cfg = _preset_config()
    cfg["spectrogram_render"]["active_preset"] = "custom"

    assert find_matching_spectrogram_preset(cfg) == "custom"

    bar = create_spectrogram_preset_bar("verify", config=cfg)
    assert bar.children[1].value == "custom"


def test_custom_frequency_limits_take_visual_priority_over_a_named_preset():
    availability = {"low": True, "custom": True}

    assert _selected_preset_value(_preset_config(), availability, None, None) == "low"
    assert _selected_preset_value(_preset_config(), availability, 30.0, 8000.0) == "custom"
