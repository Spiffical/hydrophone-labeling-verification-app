"""Review queue regressions: compact datasets, save paths, and filtered counts."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dash import no_update

from app.main import create_app
from app.services.verify_modal_cache import (
    ensure_verify_modal_items, get_filtered_verify_items_page,
    get_verify_modal_item, get_verify_modal_summary, register_verify_modal_items,
    update_verify_modal_item, verify_item_store_patch,
)
from app.callbacks.verify import badge_callbacks, confirm_callbacks
from app.callbacks.modal import lifecycle_unsaved_callbacks

LABEL = "Other > Ambient sound"
PROFILE = {"name": "UI regression test", "email": "ui-test@example.test"}
THRESHOLDS = {"__global__": 0.5}


def apply_patch(data, delta):
    assert delta is not no_update, "Saving must notify the grid immediately"
    result = deepcopy(data)
    for op in delta.to_plotly_json()["operations"]:
        assert op["operation"] == "Assign"
        dest = result
        for key in op["location"][:-1]:
            dest = dest[key]
        dest[op["location"][-1]] = op["params"]["value"]
    return result


def callback(app, name):
    return next(c["callback"].__wrapped__ for c in app.callback_map.values()
                if "callback" in c and c["callback"].__wrapped__.__name__ == name)


@pytest.fixture
def review_app(mock_config):
    return create_app(mock_config)


def dataset(tmp_path, *, compact=False):
    data = {
        "load_timestamp": str(tmp_path),
        "summary": {"total_items": 5, "active_date": "All" if compact else "2026-09-02",
                    "all_dates_index_available": compact,
                    "predictions_file": str(tmp_path / "predictions.json")},
        "items": [{"item_id": f"clip-{i}", "predictions": {
            "model_outputs": [{"class_hierarchy": LABEL, "score": .9}]},
            "annotations": {}, "metadata": {"predictions_path": str(tmp_path / "predictions.json")}} for i in range(5)],
    }
    (tmp_path / "predictions.json").write_text(json.dumps({"schema_version": "2.1", "items": deepcopy(data["items"])}))
    key = register_verify_modal_items(data)
    browser = deepcopy(data)
    if compact:
        browser["items"] = browser["items"][:2]
        browser["summary"]["verify_modal_cache_key"] = key
        browser["load_timestamp"] = "browser-preview-time"
    return key, browser


def page(key, status="all", classes=None, threshold=.5, current=0):
    return get_filtered_verify_items_page(key, {"__global__": threshold}, classes, current, 2, status)


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("action", ["accept", "reject"])
def test_main_page_decision_preserves_full_queue_and_pending_item(review_app, tmp_path, compact, action):
    key, browser = dataset(tmp_path, compact=compact)
    target = {"type": f"verify-label-{action}", "item_id": "clip-4", "label": LABEL}
    context = SimpleNamespace(triggered_id=target, triggered=[], inputs_list=[[
        {"id": target, "value": 123, "property": "n_clicks_timestamp"}]],)
    with patch.object(badge_callbacks, "ctx", context):
        result = callback(review_app, "quick_update_verify_labels")(
            [], [], [], [123], [], [], THRESHOLDS, None, None, PROFILE, None, key, None, [], [])
    browser = apply_patch(browser, result[0])
    assert ensure_verify_modal_items(browser) == key
    assert len(browser["items"]) == (2 if compact else 5)
    assert page(key)["visible_item_ids"] == [f"clip-{i}" for i in range(5)]
    assert page(key, "unverified")["remaining_items"] == 5
    assert "clip-4" in page(key, "unverified")["visible_item_ids"]
    assert get_verify_modal_item(key, "clip-4")["annotations"]["pending_save"]


@pytest.mark.parametrize("save_path", ["card", "modal", "editor", "modal_editor", "save_on_close"])
@pytest.mark.parametrize("compact", [False, True])
def test_every_save_path_removes_only_saved_item_and_notifies_grid(review_app, tmp_path, save_path, compact):
    key, browser = dataset(tmp_path, compact=compact)
    draft = get_verify_modal_item(key, "clip-4")
    draft["annotations"] = {"labels": [LABEL], "pending_save": True, "has_manual_review": True}
    update_verify_modal_item(key, draft)
    if save_path == "card":
        with patch.object(confirm_callbacks, "ctx", SimpleNamespace(triggered_id={"item_id": "clip-4"})):
            result = callback(review_app, "confirm_verification")([1], THRESHOLDS, [], [], PROFILE, key, [], [])
        delta = result[0]
    elif save_path == "modal":
        result = callback(review_app, "confirm_modal_verification")(
            [1], draft, THRESHOLDS, [], [], None, PROFILE, key, [], None, [], [])
        delta = result[4]
    elif save_path == "save_on_close":
        with patch.object(lifecycle_unsaved_callbacks, "ctx", SimpleNamespace(triggered_id="unsaved-save-btn")):
            result = callback(review_app, "resolve_unsaved_modal_action")(
                0, 1, 0, {"kind": "close"}, None, "verify", None, None, "clip-4", draft,
                THRESHOLDS, None, None, PROFILE, None, {}, key, [], [])
        delta = result[6]
    else:
        result = callback(review_app, "save_label_editor")(
            1, "clip-4", [[LABEL]], [{"filename": "clip-4"}], [], [], None, None,
            PROFILE, "verify", THRESHOLDS, key, {}, None, None,
            "clip-4" if save_path == "modal_editor" else None, None, [], [])
        delta = result[1]
    browser = apply_patch(browser, delta)
    assert ensure_verify_modal_items(browser) == key
    assert page(key)["total_items"] == 5
    assert page(key)["remaining_items"] == 4
    remaining = page(key, "unverified", current=2)
    assert remaining["visible_item_ids"] == [f"clip-{i}" for i in range(4)]
    assert remaining["page_index"] == 1  # Last-page save clamps the page.
    assert page(key, "verified")["visible_item_ids"] == ["clip-4"]
    assert get_verify_modal_summary(key)["verified"] == 1
    # Exercise real persistence using disposable predictions, never expert data.
    saved = json.loads((tmp_path / "predictions.json").read_text())["items"]
    assert len(saved[4]["verifications"]) == 1
    assert all(not item.get("verifications") for item in saved[:4])


def test_remaining_count_obeys_class_threshold_status_and_empty_results(tmp_path):
    key, _ = dataset(tmp_path)
    item = get_verify_modal_item(key, "clip-0")
    item["annotations"] = {"labels": [LABEL], "verified": True}
    update_verify_modal_item(key, item)
    item = get_verify_modal_item(key, "clip-1")
    item["predictions"]["model_outputs"] = [{"class_hierarchy": "Other > Data gap", "score": .6}]
    update_verify_modal_item(key, item)
    assert page(key)["remaining_items"] == 4  # Across every page, not just two cards.
    assert page(key, classes=[LABEL])["remaining_items"] == 3
    assert page(key, threshold=.8)["remaining_items"] == 3
    assert page(key, "verified")["remaining_items"] == 0
    assert page(key, classes=[])["remaining_items"] == 0
    assert page(key, threshold=1)["remaining_items"] == 0
    assert page(None)["remaining_items"] == 0


@pytest.mark.parametrize('mode', ['verify', 'label'])
@pytest.mark.parametrize('visible_cards', [[], ['clip-0', 'clip-1'], ['clip-4']])
@pytest.mark.parametrize('modal_open', [False, True])
def test_add_label_http_save_handles_absent_and_unrelated_cards(
    review_app, tmp_path, mode, visible_cards, modal_open
):
    """Exercise Dash response validation as well as real disposable persistence."""
    key, browser = dataset(tmp_path, compact=True)
    new_label = 'Other > Data gap'
    labels_file = tmp_path / 'labels.json'
    callback_key, entry = next(
        (key, value) for key, value in review_app.callback_map.items()
        if value.get('callback') and value['callback'].__wrapped__.__name__ == 'save_label_editor'
    )
    block_ids = [{'type': 'verify-label-block', 'item_id': item} for item in visible_cards]
    button_ids = [{'type': 'confirm-btn', 'item_id': item} for item in visible_cards]
    label_data = {'items': [get_verify_modal_item(key, 'clip-4')]}
    values = {
        'active-item-store': 'clip-4', 'label-data-store': label_data,
        'user-profile-store': PROFILE, 'mode-tabs': mode,
        'verify-thresholds-store': THRESHOLDS, 'verify-data-cache-key-store': key,
        'config-store': {}, 'label-output-input': str(labels_file),
        'current-filename': 'clip-4' if modal_open else None,
    }
    pattern_values = {
        'selected-labels-store': [[LABEL, new_label]],
        'note-editor-text': ['Saved new label'],
        'verify-label-block': block_ids, 'confirm-btn': button_ids,
    }
    states = []
    for state in entry['state']:
        if state['id'].startswith('{'):
            pattern = json.loads(state['id'])
            if state['property'] == 'id' and 'filename' in pattern:
                value = [{'type': pattern['type'], 'filename': 'clip-4'}]
            else:
                value = pattern_values[pattern['type']]
        else:
            value = values.get(state['id'])
        states.append(dict(state, value=value))
    outputs = []
    for output in entry['output']:
        if isinstance(output.component_id, dict):
            ids = block_ids if output.component_id['type'] == 'verify-label-block' else button_ids
            outputs.append([{'id': id_, 'property': output.component_property} for id_ in ids])
        else:
            outputs.append({'id': output.component_id, 'property': output.component_property})
    response = review_app.server.test_client().post('/_dash-update-component', json={
        'output': callback_key, 'outputs': outputs,
        'inputs': [dict(entry['inputs'][0], value=1)], 'state': states,
        'changedPropIds': ['label-editor-save.n_clicks'],
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    updates = response.json['response']
    assert updates['label-editor-modal']['is_open'] is False
    if mode == 'verify':
        assert page(key, 'unverified')['remaining_items'] == 4
        assert len(page(key)['visible_item_ids']) == 5
        saved = json.loads((tmp_path / 'predictions.json').read_text())['items'][4]
        assert any(d['label'] == new_label and d['decision'] == 'added'
                   for d in saved['verifications'][-1]['label_decisions'])
        assert updates['verify-data-store']['data']['__dash_patch_update']
    else:
        assert labels_file.exists()
        assert new_label in labels_file.read_text()
        assert new_label in updates['label-data-store']['data']['items'][0]['annotations']['labels']
    if modal_open:
        assert new_label in updates['modal-item-store']['data']['annotations']['labels']
