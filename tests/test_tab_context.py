from app.callbacks.common.tab_context import config_default_data_dir, resolve_tab_data_dir
from app.callbacks.data.discovery_callbacks import active_selection_label
from app.callbacks.ui.tab_switch_callbacks import _has_pending_label_changes


def test_config_default_data_dir_uses_active_mode_root(mock_config):
    assert config_default_data_dir(mock_config, "label") == mock_config["label"]["folder"]
    assert config_default_data_dir(mock_config, "verify") == mock_config["verify"]["dashboard_root"]


def test_resolve_tab_data_dir_does_not_cross_modes(mock_config):
    assert resolve_tab_data_dir(mock_config, mode="label") == mock_config["label"]["folder"]
    assert resolve_tab_data_dir(mock_config, mode="verify") == mock_config["verify"]["dashboard_root"]


def test_pending_label_changes_detected():
    clean = {"items": [{"annotations": {"pending_save": False}}]}
    dirty = {"items": [{"annotations": {"pending_save": True}}]}

    assert not _has_pending_label_changes(clean)
    assert _has_pending_label_changes(dirty)


def test_active_selection_label_for_direct_and_hierarchical_data(tmp_path):
    direct = {"source_data_dir": str(tmp_path), "summary": {}}
    hierarchical = {
        "source_data_dir": str(tmp_path),
        "summary": {"active_date": "2026-01-07", "active_hydrophone": "DEVICE01"},
    }

    assert active_selection_label(direct) == "Direct folder"
    assert active_selection_label(hierarchical) == "2026-01-07 / DEVICE01"
