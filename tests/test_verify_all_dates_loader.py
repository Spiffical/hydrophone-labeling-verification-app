import threading
import time
from unittest.mock import Mock

from app.layouts.main_layout import create_main_layout
from app.callbacks.data.load_verify_callbacks import (
    _all_dates_preview,
    _finish_all_dates_data,
    _indexed_all_dates_view,
    _is_all_dates_filter_change,
    _is_all_dates_ready_signal,
    _is_all_dates_ui_ready,
)
from app.services.verify_all_dates_loader import (
    build_all_dates_cache_key,
    cache_all_dates_preview,
    clear_all_dates_loads,
    get_all_dates_preview,
    get_all_dates_load,
    load_persisted_all_dates,
    queue_all_dates_load,
    start_queued_all_dates_load,
    start_all_dates_load,
)
from app.services.verify_modal_cache import get_verify_modal_data


def test_all_dates_cache_key_is_stable_and_device_specific():
    config_a = {
        "verify": {"date": "2026-04-08", "dashboard_root": "/tmp/dashboard"},
        "data": {"data_dir": "/tmp/data", "spectrogram_folder_names": ["spectrograms"]},
        "display": {"items_per_page": 25},
        "profile": {"name": "Reviewer A"},
    }
    config_b = {
        "profile": {"name": "Reviewer B"},
        "display": {"items_per_page": 100},
        "data": {"spectrogram_folder_names": ["spectrograms"], "data_dir": "/tmp/data"},
        "verify": {"dashboard_root": "/tmp/dashboard", "date": "2026-04-17"},
    }

    assert build_all_dates_cache_key(config_a, "ICLISTENHF6020") == build_all_dates_cache_key(
        config_b,
        "ICLISTENHF6020",
    )
    assert build_all_dates_cache_key(config_a, "ICLISTENHF6020") != build_all_dates_cache_key(
        config_a,
        "ICLISTENHF6021",
    )
    config_b["data"]["predictions_file"] = "/tmp/other-predictions.json"
    assert build_all_dates_cache_key(config_a, "ICLISTENHF6020") != build_all_dates_cache_key(
        config_b,
        "ICLISTENHF6020",
    )


def test_all_dates_preview_cache_returns_a_copy():
    clear_all_dates_loads()
    preview = {"items": [{"item_id": "one"}], "summary": {"total_items": 1}}

    cache_all_dates_preview("preview-key", preview)
    cached = get_all_dates_preview("preview-key")
    cached["items"][0]["item_id"] = "changed"

    assert get_all_dates_preview("preview-key")["items"][0]["item_id"] == "one"
    clear_all_dates_loads()


def test_all_dates_queued_loader_waits_for_explicit_start():
    clear_all_dates_loads()
    started = threading.Event()

    def loader():
        started.set()
        return {"items": [], "summary": {"total_items": 0}}

    assert queue_all_dates_load("queued-key", loader)["status"] == "pending"
    assert started.wait(timeout=0.05) is False
    assert get_all_dates_load("queued-key", include_data=False)["status"] == "pending"
    assert start_queued_all_dates_load("queued-key")["status"] == "loading"
    assert started.wait(timeout=2)

    deadline = time.monotonic() + 2
    while get_all_dates_load("queued-key", include_data=False)["status"] == "loading":
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert get_all_dates_load("queued-key", include_data=False)["status"] == "ready"
    clear_all_dates_loads()


def test_all_dates_background_loader_runs_once_and_returns_a_copy():
    clear_all_dates_loads()
    started = threading.Event()
    release = threading.Event()
    calls = []

    def loader():
        calls.append(True)
        started.set()
        assert release.wait(timeout=2)
        return {"items": [{"item_id": "one"}], "summary": {"total_items": 1}}

    assert start_all_dates_load("test-key", loader)["status"] == "loading"
    assert started.wait(timeout=2)
    assert start_all_dates_load("test-key", loader, force=True)["status"] == "loading"
    assert len(calls) == 1

    release.set()
    deadline = time.monotonic() + 2
    result = get_all_dates_load("test-key")
    while result["status"] == "loading" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = get_all_dates_load("test-key")

    assert result["status"] == "ready"
    assert result["data"]["items"] == [{"item_id": "one"}]
    assert get_all_dates_load("test-key", include_data=False) == {
        "status": "ready",
        "data": None,
        "error": None,
    }
    result["data"]["items"][0]["item_id"] = "changed"
    assert get_all_dates_load("test-key")["data"]["items"][0]["item_id"] == "one"
    clear_all_dates_loads()


def test_all_dates_background_loader_persists_completed_index(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.verify_all_dates_loader._PERSISTED_CACHE_DIR",
        tmp_path,
    )
    clear_all_dates_loads()
    data = {"items": [{"item_id": "one"}], "summary": {"total_items": 1}}

    assert start_all_dates_load("persisted-key", lambda: data, persist=True)["status"] == "loading"
    deadline = time.monotonic() + 2
    while get_all_dates_load("persisted-key", include_data=False)["status"] == "loading":
        assert time.monotonic() < deadline
        time.sleep(0.01)

    persisted = load_persisted_all_dates("persisted-key")
    assert persisted == data
    persisted["items"][0]["item_id"] = "changed"
    assert load_persisted_all_dates("persisted-key")["items"][0]["item_id"] == "one"
    clear_all_dates_loads()


def test_all_dates_preview_reuses_current_date_without_loading():
    current = {
        "items": [{"item_id": "one"}],
        "summary": {
            "total_items": 1,
            "active_date": "2026-04-08",
            "active_hydrophone": "ICLISTENHF6020",
        },
        "source_data_dir": "/tmp/data",
    }
    load_dataset = Mock()

    preview = _all_dates_preview(
        current,
        active_data_dir="/tmp/data",
        effective_cfg={},
        requested_device="ICLISTENHF6020",
        load_dataset=load_dataset,
    )

    load_dataset.assert_not_called()
    assert preview["items"] == [{"item_id": "one"}]
    assert preview["summary"]["active_date"] == "All"
    assert preview["summary"]["all_dates_loading"] is True
    assert preview["summary"]["all_dates_preview"] is True
    assert preview["summary"]["all_dates_preview_items"] == 1
    assert current["summary"]["active_date"] == "2026-04-08"


def test_all_dates_preview_caps_items_before_rendering():
    current = {
        "items": [{"item_id": str(index)} for index in range(100)],
        "summary": {
            "total_items": 100,
            "active_date": "2026-04-08",
            "active_hydrophone": "ICLISTENHF6020",
        },
        "source_data_dir": "/tmp/data",
    }

    preview = _all_dates_preview(
        current,
        active_data_dir="/tmp/data",
        effective_cfg={},
        requested_device="ICLISTENHF6020",
        load_dataset=Mock(),
    )

    assert len(preview["items"]) == 50
    assert preview["summary"]["total_items"] == 50
    assert preview["summary"]["all_dates_preview_items"] == 50
    assert preview["summary"]["all_dates_preview_source_items"] == 100


def test_initial_empty_ready_store_is_not_treated_as_completion_signal():
    triggered = {"verify-all-dates-ready-store", "global-date-selector"}

    assert _is_all_dates_ready_signal(triggered, None) is False
    assert _is_all_dates_ready_signal(triggered, {}) is False
    assert _is_all_dates_ready_signal(
        triggered,
        {
            "cache_key": "cache-key",
            "request_id": "request-id",
            "status": "ready",
        },
    ) is True


def test_all_dates_poll_restarts_for_date_or_device_changes():
    assert _is_all_dates_filter_change({"global-date-selector"}) is True
    assert _is_all_dates_filter_change({"global-device-selector"}) is True
    assert _is_all_dates_filter_change({"verify-all-dates-poll"}) is False


def test_all_dates_full_scan_waits_for_matching_render():
    summary = {"all_dates_request_id": "current-request"}

    assert _is_all_dates_ui_ready(summary, None) is False
    assert _is_all_dates_ui_ready(
        summary,
        {"all_dates_request_id": "stale-request", "active_date": "All"},
    ) is False
    assert _is_all_dates_ui_ready(
        summary,
        {"all_dates_request_id": "current-request", "active_date": "2026-04-08"},
    ) is False
    assert _is_all_dates_ui_ready(
        summary,
        {"all_dates_request_id": "current-request", "active_date": "All"},
    ) is True


def test_all_dates_preview_skips_known_empty_date(tmp_path):
    for date_value in ["2026-04-17", "2026-04-16", "2026-04-15"]:
        (tmp_path / date_value).mkdir()

    current = {
        "items": [],
        "summary": {
            "total_items": 0,
            "active_date": "2026-04-17",
            "active_hydrophone": "ICLISTENHF6324",
        },
        "source_data_dir": str(tmp_path),
    }

    def load_dataset(_config, _mode, *, date_str, hydrophone):
        assert hydrophone == "ICLISTENHF6324"
        items = [{"item_id": "preview"}] if date_str == "2026-04-15" else []
        return {
            "items": items,
            "summary": {
                "total_items": len(items),
                "active_date": date_str,
                "active_hydrophone": hydrophone,
            },
        }

    preview = _all_dates_preview(
        current,
        active_data_dir=str(tmp_path),
        effective_cfg={},
        requested_device="ICLISTENHF6324",
        load_dataset=load_dataset,
    )

    assert preview["items"] == [{"item_id": "preview"}]
    assert preview["summary"]["all_dates_preview_date"] == "2026-04-15"
    assert preview["summary"]["active_date"] == "All"


def test_completed_all_dates_data_has_final_state():
    completed = _finish_all_dates_data(
        {"items": [{"item_id": "one"}], "summary": {"total_items": 1}},
        cache_key="cache-key",
        active_data_dir="/tmp/data",
        request_id="request-id",
    )

    assert completed["summary"]["all_dates_loading"] is False
    assert completed["summary"]["all_dates_preview"] is False
    assert completed["summary"]["all_dates_cache_key"] == "cache-key"
    assert completed["summary"]["all_dates_request_id"] == "request-id"
    assert completed["source_data_dir"] == "/tmp/data"
    assert isinstance(completed["load_timestamp"], float)


def test_indexed_all_dates_view_keeps_full_server_index_and_compact_client_data():
    indexed = {
        "items": [{"item_id": str(index)} for index in range(100)],
        "summary": {
            "total_items": 100,
            "verified": 7,
            "active_hydrophone": "ICLISTENHF6020",
        },
    }

    compact = _indexed_all_dates_view(
        indexed,
        cache_key="index-key",
        active_data_dir="/tmp/data",
        request_id="request-id",
        updating=True,
    )

    assert len(compact["items"]) == 50
    assert compact["summary"]["total_items"] == 100
    assert compact["summary"]["verified"] == 7
    assert compact["summary"]["all_dates_index_available"] is True
    assert compact["summary"]["all_dates_loading"] is True
    modal_data = get_verify_modal_data(compact["summary"]["verify_modal_cache_key"])
    assert len(modal_data["items"]) == 100


def test_all_dates_poll_is_disabled_until_a_background_load_starts():
    layout = create_main_layout({})
    poll = next(
        component
        for component in layout.children
        if getattr(component, "id", None) == "verify-all-dates-poll"
    )

    assert poll.disabled is True
    assert poll.interval == 1500
    assert any(
        getattr(component, "id", None) == "verify-all-dates-ready-store"
        for component in layout.children
    )
    assert any(
        getattr(component, "id", None) == "verify-all-dates-request-store"
        for component in layout.children
    )
