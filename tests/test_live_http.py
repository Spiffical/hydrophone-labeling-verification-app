import os
import time

import pytest
import requests

pytestmark = pytest.mark.live


def _find_component_by_id(node, target_id):
    if isinstance(node, dict):
        if node.get("props", {}).get("id") == target_id:
            return node
        for key, value in node.items():
            found = _find_component_by_id(value, target_id)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_component_by_id(item, target_id)
            if found is not None:
                return found
    return None


@pytest.fixture(scope="session")
def base_url():
    url = os.environ.get("DASH_TEST_URL")
    if not url:
        pytest.skip("DASH_TEST_URL not set; live tests skipped")
    return url.rstrip("/")


def test_dash_layout_available(base_url):
    resp = requests.get(f"{base_url}/_dash-layout", timeout=5)
    assert resp.status_code == 200
    layout = resp.json()
    assert _find_component_by_id(layout, "mode-tabs") is not None
    assert _find_component_by_id(layout, "config-store") is not None
    assert _find_component_by_id(layout, "profile-btn") is not None
    assert _find_component_by_id(layout, "theme-toggle") is not None


def test_dash_dependencies_available(base_url):
    resp = requests.get(f"{base_url}/_dash-dependencies", timeout=5)
    assert resp.status_code == 200
    deps = resp.json()
    assert isinstance(deps, list)
    assert deps, "Expected at least one dependency"


def test_load_data_callback(base_url):
    layout_resp = requests.get(f"{base_url}/_dash-layout", timeout=5)
    layout = layout_resp.json()
    config_store = _find_component_by_id(layout, "config-store")
    assert config_store is not None
    config_data = config_store.get("props", {}).get("data")

    payload = {
        "output": "data-store.data",
        "outputs": {"id": "data-store", "property": "data"},
        "inputs": [
            {"id": "mode-tabs", "property": "value", "value": "label"},
            {"id": "label-reload", "property": "n_clicks", "value": None},
            {"id": "verify-reload", "property": "n_clicks", "value": None},
            {"id": "explore-reload", "property": "n_clicks", "value": None},
        ],
        "state": [
            {"id": "config-store", "property": "data", "value": config_data},
        ],
        "changedPropIds": ["mode-tabs.value"],
    }

    resp = requests.post(f"{base_url}/_dash-update-component", json=payload, timeout=10)
    assert resp.status_code == 200
    body = resp.json()
    response = body.get("response", {})
    assert "data-store" in response
    data = response["data-store"]["data"]
    assert data["items"], "Expected items from load_data"
    assert "summary" in data


def test_theme_toggle_updates_store(base_url):
    payload = {
        "output": "theme-store.data",
        "outputs": {"id": "theme-store", "property": "data"},
        "inputs": [
            {"id": "theme-toggle", "property": "value", "value": True},
        ],
        "state": [],
        "changedPropIds": ["theme-toggle.value"],
    }

    resp = requests.post(f"{base_url}/_dash-update-component", json=payload, timeout=10)
    assert resp.status_code == 200
    body = resp.json()
    response = body.get("response", {})
    assert response.get("theme-store", {}).get("data") == "dark"
