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


def test_modal_range_panels_take_their_height_from_the_layout(mock_config):
    # Other visible ranges share the modal's plot column with the main plot
    # (zz_workbench.css). A fixed figure height pushed the second range and the
    # audio player below the dialog on laptop screens.
    from app.main import create_app

    cfg = {**mock_config, **_config()}
    app = create_app(cfg)
    render = next(
        entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if "callback" in entry and entry["callback"].__wrapped__.__name__ == "render_modal_visible_ranges"
    )
    state = {
        "schema_version": "spectrogram-visible-ranges-v2",
        "preset_ids": ["low", "high"],
        "custom_ranges": [],
        "active_range_id": "low",
    }
    active_figure = {"layout": {"meta": {"x_min": 0.0, "x_max": 10.0}, "xaxis": {"range": [0, 10]}}}
    _title, _readout, above, below, _section = render(
        {"item_id": "clip-1", "audio_path": "clip-1.wav"},
        state, cfg, "default", "linear", {}, active_figure, None, None, None,
    )
    panels = above + below
    assert len(panels) == 1
    graph = panels[0].children[1]
    assert "height" not in (getattr(graph, "style", None) or {})
    assert graph.figure.layout.height is None
    assert graph.figure.layout.autosize is True
    assert list(graph.figure.layout.xaxis.range) == [0.0, 10.0]


def test_modal_range_panels_line_up_with_the_main_plot_in_clip_time(mock_config, monkeypatch):
    # The main plot's 0.25 s window puts x = 0 at 0.125 s into the clip; a
    # 1 s window's frames start 0.5 s in, so its image starts at x = 0.375.
    import app.callbacks.modal.view_callbacks as view_callbacks
    from app.main import create_app

    monkeypatch.setattr(view_callbacks, "spectrogram_time_span", lambda *args, **kwargs: (0.5, 9.5))
    cfg = {**mock_config, **_config()}
    app = create_app(cfg)
    render = next(
        entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if "callback" in entry and entry["callback"].__wrapped__.__name__ == "render_modal_visible_ranges"
    )
    state = {
        "schema_version": "spectrogram-visible-ranges-v2",
        "preset_ids": ["low", "high"],
        "custom_ranges": [],
        "active_range_id": "low",
    }
    active_figure = {"layout": {
        "meta": {"x_min": 0.0, "x_max": 9.75, "x_to_seconds": 1.0, "x_origin_seconds": 0.125},
        "xaxis": {"range": [2.0, 4.0], "tickformat": ".2f", "title": {"text": "Time (seconds)"}},
    }}
    _title, _readout, above, below, _section = render(
        {"item_id": "clip-1", "audio_path": "clip-1.wav"},
        state, cfg, "default", "linear", {}, active_figure, None, None, None,
    )
    figure = (above + below)[0].children[1].figure
    image = figure.layout.images[0]
    assert (image.xref, image.yref, image.x, image.sizex) == ("x", "paper", 0.375, 9.0)
    # The panel starts on the main plot's window and never zooms on its own
    # (modal_range_panels.js keeps it on the main plot's window and margins).
    assert list(figure.layout.xaxis.range) == [2.0, 4.0]
    assert figure.layout.xaxis.tickformat == ".2f"
    assert figure.layout.xaxis.fixedrange and figure.layout.yaxis.fixedrange
    assert figure.layout.xaxis.automargin is False and figure.layout.yaxis.automargin is False
