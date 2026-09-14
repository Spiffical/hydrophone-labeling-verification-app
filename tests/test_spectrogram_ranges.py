from app.services.spectrogram_ranges import (
    add_custom_spectrogram_range,
    config_for_spectrogram_range,
    infer_custom_fft_settings,
    normalize_spectrogram_range_state,
    remove_custom_spectrogram_range,
    resolve_companion_spectrogram_ranges,
    resolve_visible_spectrogram_ranges,
    sort_spectrogram_ranges_for_display,
    update_spectrogram_range_visibility,
)


def _config():
    return {
        "spectrogram_render": {
            "source": "audio_generated",
            "active_preset": "recommended",
            "win_dur_s": 0.25,
            "overlap": 0.9,
            "freq_min_hz": 5.0,
            "freq_max_hz": 30000.0,
            "presets": [
                {
                    "id": "recommended",
                    "label": "Recommended",
                    "scope": "item",
                    "metadata_key": "recommended_spectrogram",
                    "win_dur_s": 0.25,
                    "overlap": 0.9,
                    "freq_min_hz": 5.0,
                    "freq_max_hz": 30000.0,
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
                    "label": "High | 2-32 kHz",
                    "win_dur_s": 0.02,
                    "overlap": 0.9,
                    "freq_min_hz": 2000.0,
                    "freq_max_hz": 32000.0,
                },
            ],
        }
    }


def test_custom_range_lifecycle_and_visibility():
    cfg = _config()
    state, error = add_custom_spectrogram_range(
        None,
        cfg,
        label="Orca social",
        freq_min_hz=500,
        freq_max_hz=16000,
    )
    assert error is None
    custom_id = state["custom_ranges"][0]["id"]
    assert state["custom_ranges"][0]["visible"] is True

    hidden = update_spectrogram_range_visibility(
        state,
        cfg,
        preset_ids=["low", "missing"],
        visible_custom_ids=[],
    )
    assert hidden["preset_ids"] == ["low"]
    assert hidden["custom_ranges"][0]["visible"] is False
    assert remove_custom_spectrogram_range(hidden, cfg, custom_id)["custom_ranges"] == []


def test_custom_range_validation_is_fail_closed():
    state, error = add_custom_spectrogram_range(
        None,
        _config(),
        label="Invalid",
        freq_min_hz=2000,
        freq_max_hz=100,
    )
    assert state == normalize_spectrogram_range_state(None, _config())
    assert "maximum" in error.lower()


def test_resolved_ranges_are_ordered_and_primary_duplicates_are_removed():
    cfg = _config()
    item = {
        "metadata": {
            "recommended_spectrogram": {
                "win_dur_s": 1.0,
                "overlap": 0.9,
                "freq_min_hz": 5.0,
                "freq_max_hz": 125.0,
            }
        }
    }
    state = {
        "preset_ids": ["recommended", "low", "high"],
        "custom_ranges": [],
    }
    primary = (5.0, 125.0, 1.0, 0.9)
    resolved = resolve_companion_spectrogram_ranges(
        item,
        cfg,
        state,
        primary_signature=primary,
    )
    assert [entry["preset_id"] for entry in resolved] == ["high"]


def test_visible_ranges_are_one_frequency_ordered_collection():
    cfg = _config()
    state = {
        "schema_version": "spectrogram-visible-ranges-v2",
        "preset_ids": ["low", "high"],
        "custom_ranges": [
            {
                "id": "custom-mid",
                "label": "Mid",
                "freq_min_hz": 100.0,
                "freq_max_hz": 2000.0,
                "visible": True,
            }
        ],
        "active_range_id": "low",
    }

    resolved = resolve_visible_spectrogram_ranges({}, cfg, state)

    assert [entry["selection_id"] for entry in resolved] == [
        "high",
        "custom-mid",
        "low",
    ]


def test_frequency_sort_places_low_ranges_below_mid_ranges():
    ordered = sort_spectrogram_ranges_for_display(
        [
            {"label": "Low", "freq_min_hz": 5, "freq_max_hz": 125},
            {"label": "Mid", "freq_min_hz": 100, "freq_max_hz": 2000},
        ]
    )

    assert [entry["label"] for entry in ordered] == ["Mid", "Low"]


def test_visible_range_selection_caps_presets_and_custom_ranges_together():
    cfg = _config()
    custom_ranges = [
        {
            "id": f"custom-{index}",
            "label": f"Custom {index}",
            "freq_min_hz": 100.0 * index,
            "freq_max_hz": 100.0 * index + 50.0,
            "visible": False,
        }
        for index in range(1, 5)
    ]
    updated = update_spectrogram_range_visibility(
        {
            "schema_version": "spectrogram-visible-ranges-v2",
            "preset_ids": ["recommended"],
            "custom_ranges": custom_ranges,
            "active_range_id": "recommended",
        },
        cfg,
        preset_ids=["recommended", "low", "high"],
        visible_custom_ids=[candidate["id"] for candidate in custom_ranges],
    )

    assert updated["preset_ids"] == ["recommended", "low", "high"]
    assert [
        candidate["id"]
        for candidate in updated["custom_ranges"]
        if candidate["visible"]
    ] == ["custom-1", "custom-2"]


def test_custom_fft_settings_and_render_config():
    assert infer_custom_fft_settings(125) == (1.0, 0.9)
    assert infer_custom_fft_settings(16000) == (0.05, 0.9)
    assert infer_custom_fft_settings(96000) == (0.002, 0.75)
    cfg = config_for_spectrogram_range(
        _config(),
        {"freq_min_hz": 8000.0, "freq_max_hz": 96000.0},
    )
    render = cfg["spectrogram_render"]
    assert render["source"] == "audio_generated"
    assert render["win_dur_s"] == 0.002
    assert render["overlap"] == 0.75
    assert render["freq_min_hz"] == 8000.0
    assert render["freq_max_hz"] == 96000.0


def test_existing_files_ignore_saved_ranges_and_restore_them_for_audio():
    from copy import deepcopy
    from app.layouts.display_controls import create_spectrogram_range_controls

    cfg = _config()
    state = update_spectrogram_range_visibility(None, cfg, preset_ids=['low', 'high'], visible_custom_ids=[])
    saved = deepcopy(state)
    expected = resolve_visible_spectrogram_ranges({}, cfg, state)
    assert len(expected) == 2
    cfg['spectrogram_render']['source'] = 'existing'
    assert resolve_visible_spectrogram_ranges({}, cfg, state) == []
    assert create_spectrogram_range_controls('verify', cfg).style['display'] == 'none'
    cfg['spectrogram_render']['source'] = 'audio_generated'
    assert create_spectrogram_range_controls('verify', cfg).style['display'] == 'block'
    assert resolve_visible_spectrogram_ranges({}, cfg, state) == expected
    assert state == saved


def test_default_templates_are_available_without_dashboard_specific_config():
    from app.services.spectrogram_presets import get_spectrogram_presets
    presets = get_spectrogram_presets({'spectrogram_render': {'presets': []}})
    assert [p['id'] for p in presets] == ['low', 'mid', 'social', 'high', 'ultrasonic']
    assert presets[-1]['win_dur_s'] == 0.002


def test_active_modal_range_uses_selected_band_instead_of_page_full_range():
    from app.services.spectrogram_ranges import resolve_active_spectrogram_range

    cfg = {"spectrogram_render": {"source": "audio_generated", "freq_min_hz": 0, "freq_max_hz": 24000}}
    state = {"preset_ids": ["low", "mid"], "active_range_id": "low"}
    active = resolve_active_spectrogram_range({}, cfg, state)
    assert (active["freq_min_hz"], active["freq_max_hz"]) == (5, 125)
    assert config_for_spectrogram_range(cfg, active)["spectrogram_render"]["freq_max_hz"] == 125
    cfg["spectrogram_render"]["source"] = "existing"
    assert resolve_active_spectrogram_range({}, cfg, state) is None
