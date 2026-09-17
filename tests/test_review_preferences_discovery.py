from app.callbacks.data.discovery_callbacks import register_tab_state_callbacks


class CallbackApp:
    def __init__(self):
        self.functions = {}

    def callback(self, *args, **kwargs):
        def register(fn):
            self.functions[fn.__name__] = fn
            return fn
        return register


def callbacks(tmp_path):
    for date in ("2026-09-03", "2026-09-04"):
        for device in ("Hydrophone-A", "Hydrophone-B"):
            (tmp_path / date / device).mkdir(parents=True)
    app = CallbackApp()
    register_tab_state_callbacks(app, tab_iso_debug=lambda *a, **k: None,
                                 config_default_data_dir=lambda *a: str(tmp_path),
                                 tab_data_snapshot=lambda *a: {})
    return app.functions


def test_profile_restore_uses_dataset_dates_not_current_loaded_subset(tmp_path):
    f = callbacks(tmp_path)
    loaded = {"source_data_dir": str(tmp_path), "available_dates": ["2026-09-04"]}
    saved = {"verify": {"date": "2026-09-03", "device": "Hydrophone-B"}}
    options, value = f["discover_dates"]("verify", "alice@example.test", {}, None, loaded, None, saved, "2026-09-04")
    assert value == "2026-09-03"
    assert {o["value"] for o in options} == {"__all__", "2026-09-03", "2026-09-04"}


def test_profile_restore_uses_available_devices_not_current_loaded_subset(tmp_path):
    f = callbacks(tmp_path)
    loaded = {"source_data_dir": str(tmp_path), "available_devices": ["Hydrophone-A"]}
    options, value = f["discover_devices"]("2026-09-03", {}, "verify", None, loaded, None,
                                           {"verify": {"device": "Hydrophone-B"}}, "Hydrophone-A")
    assert value == "Hydrophone-B"
    assert {o["value"] for o in options} == {"__all__", "Hydrophone-A", "Hydrophone-B"}


def test_new_profile_and_removed_saved_date_use_defaults_not_previous_profile(tmp_path):
    f = callbacks(tmp_path)
    for saved in ({}, {"verify": {"date": "2020-01-01", "device": "missing"}}):
        _, value = f["discover_dates"]("verify", "bob@example.test", {}, None, None, None, saved, "2026-09-03")
        assert value == "2026-09-04"
        _, device = f["discover_devices"]("2026-09-04", {}, "verify", None, None, None, saved, "Hydrophone-B")
        assert device == "Hydrophone-A"


def test_discovery_waits_for_profile_restoration(tmp_path):
    import pytest
    from dash.exceptions import PreventUpdate
    f = callbacks(tmp_path)
    with pytest.raises(PreventUpdate):
        f["discover_dates"]("verify", None, {}, None, None, None, {}, None)
