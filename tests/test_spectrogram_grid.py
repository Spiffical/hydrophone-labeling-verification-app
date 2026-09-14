from app.layouts.display_controls import create_spectrogram_grid_controls
from app.services.spectrogram_grid import (
    config_with_spectrogram_grid,
    infer_spectrogram_grid,
    normalize_spectrogram_grid,
    spectrogram_grid_class,
)


def test_legacy_page_sizes_infer_balanced_grid_dimensions():
    assert infer_spectrogram_grid(16) == {"rows": 4, "columns": 4}
    assert infer_spectrogram_grid(20) == {"rows": 4, "columns": 5}
    assert infer_spectrogram_grid(25) == {"rows": 5, "columns": 5}


def test_explicit_grid_dimensions_define_exact_page_size_and_are_bounded():
    layout = normalize_spectrogram_grid({}, rows=20, columns=0)

    assert layout == {"rows": 8, "columns": 1, "items_per_page": 8}


def test_config_update_keeps_grid_and_page_size_in_sync():
    updated = config_with_spectrogram_grid(
        {"display": {"items_per_page": 25, "colormap": "viridis"}},
        rows=3,
        columns=6,
    )

    assert updated["display"] == {
        "items_per_page": 18,
        "colormap": "viridis",
        "grid_rows": 3,
        "grid_columns": 6,
    }


def test_grid_class_is_safe_for_css_column_variants():
    assert spectrogram_grid_class(4).endswith("spectrogram-card-grid--columns-4")
    assert spectrogram_grid_class(99).endswith("spectrogram-card-grid--columns-6")


def test_application_settings_grid_controls_expose_rows_columns_and_page_capacity():
    controls = create_spectrogram_grid_controls({"display": {"items_per_page": 16}})

    assert controls.children[0].children[1].id == "spectrogram-grid-rows"
    assert controls.children[0].children[1].value == 4
    assert controls.children[1].children[1].id == "spectrogram-grid-columns"
    assert controls.children[1].children[1].value == 4
    assert controls.children[2].children == "16 spectrograms per page"


def test_config_load_preserves_explicit_grid_and_cli_page_size_override(tmp_path, monkeypatch):
    import json
    import sys
    from app.config import get_config
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'display': {'items_per_page': 25, 'grid_rows': 2, 'grid_columns': 3}}))
    monkeypatch.setattr(sys, 'argv', ['app', '--config', str(path)])
    display = get_config()['display']
    assert (display['grid_rows'], display['grid_columns'], display['items_per_page']) == (2, 3, 6)
    monkeypatch.setattr(sys, 'argv', ['app', '--config', str(path), '--items-per-page', '4'])
    display = get_config()['display']
    assert (display['grid_rows'], display['grid_columns'], display['items_per_page']) == (2, 2, 4)
