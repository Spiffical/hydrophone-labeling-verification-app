"""Regression checks for small updates that preserve spectrogram data and UI state."""

from copy import deepcopy
from unittest.mock import Mock, patch
from types import SimpleNamespace

import numpy as np
import pytest
from dash import no_update

from app.main import create_app
from app.callbacks.modal.figure_helpers import apply_modal_boxes_to_figure, patch_modal_boxes
from app.services.grid_updates import grid_render_state, incremental_grid
from app.utils import image_processing as ip


def _apply_patch(value, delta):
    value = deepcopy(value)
    for operation in delta.to_plotly_json()["operations"]:
        location = operation["location"]
        target = value
        for key in location[:-1]:
            target = target[key]
        key = location[-1]
        kind = operation["operation"]
        if kind == "Assign":
            target[key] = operation["params"]["value"]
        elif kind == "Delete":
            del target[key]
        elif kind == "Append":
            target[key].append(operation["params"]["value"])
        else:
            raise AssertionError(kind)
    return value


def test_box_patch_preserves_heatmap_image_and_unrelated_traces():
    box = {"label": "Whale", "source": "manual", "annotation_extent": {
        "type": "time_freq_box",
        "time_start_sec": 1, "time_end_sec": 2, "freq_min_hz": 10, "freq_max_hz": 20,
    }}
    original = apply_modal_boxes_to_figure({
        "data": [{"type": "heatmap", "z": [[1, 2], [3, 4]]},
                 {"type": "scatter", "name": "other", "x": [1], "y": [2]}],
        "layout": {"meta": {"x_min": 0, "x_max": 3, "y_min": 5, "y_max": 30},
                   "images": [{"source": "data:image/png;base64,unchanged"}],
                   "uirevision": "preserve-zoom"},
    }, [box])
    context = {"layout": {k: deepcopy(v) for k, v in original["layout"].items() if k != "images"},
               "data": [{"type": t["type"], "name": t.get("name")} for t in original["data"]]}
    for boxes in ([], [dict(box, tag="Repeated")], [box, box]):
        result = _apply_patch(original, patch_modal_boxes(context, boxes))
        expected = apply_modal_boxes_to_figure(deepcopy(original), boxes)
        assert result == expected
        assert result["data"][:2] == original["data"][:2]
        assert result["layout"]["images"] == original["layout"]["images"]


def test_small_server_edits_never_receive_full_plotly_figure(mock_config):
    app = create_app(mock_config)
    for callback in app._callback_list:
        if callback.get("clientside_function"):
            continue
        assert not any(
            entry["id"] == "modal-image-graph" and entry["property"] == "figure"
            for entry in callback.get("inputs", []) + callback.get("state", [])
        ), callback["output"]


def test_grid_edits_only_replace_changed_card_and_rebuild_for_new_context():
    items = [{"item_id": "a", "labels": []}, {"item_id": "b", "labels": []}]
    before = grid_render_state(items, {"page": 0})
    build_full, build_card = Mock(return_value="full"), Mock(return_value="updated")
    update_card = Mock()
    assert incremental_grid(before, before, build_full, build_card, update_card) is no_update
    update_card.assert_not_called()
    items[1]["labels"] = ["Whale"]
    after = grid_render_state(items, {"page": 0})
    assert incremental_grid(before, after, build_full, build_card, update_card) is no_update
    build_card.assert_called_once_with(1)
    build_full.assert_not_called()
    update_card.assert_called_once_with("updated")
    assert incremental_grid(after, grid_render_state(items, {"page": 1}), build_full, build_card, update_card) == "full"


def test_cached_contrast_statistics_are_exact_and_reused(tmp_path):
    path = tmp_path / "test.mat"
    path.write_bytes(b"placeholder")
    psd = np.random.default_rng(42).normal(size=(32, 100)).astype(np.float32)
    psd[0, :3] = [np.nan, np.inf, -np.inf]
    spec = {"psd": psd, "freq": np.linspace(5, 100, 32), "time": np.arange(100)}
    valid = psd[np.isfinite(psd)]
    expected = np.percentile(valid, [2, 98])
    with patch.object(ip, "_load_mat", return_value=spec):
        cached = ip.load_spectrogram_cached(str(path))
    with patch.object(ip, "_compute_color_limit_summary", side_effect=AssertionError("recomputed")):
        fig = ip.create_spectrogram_figure(cached, "default")
        summary = ip.summarize_spectrogram_display_ranges(cached)
        assert fig.layout.meta["auto_color_min"] == expected[0]
        assert fig.layout.meta["auto_color_max"] == expected[1]
        assert summary["color_auto_min"] == expected[0]
        assert ip.generate_image_cached(str(path)).startswith("data:image/png;base64,")


def test_modal_save_uses_staged_box_draft_not_stale_page_item(mock_config, tmp_path):
    from app.callbacks.label import editor_save_callbacks

    app = create_app(mock_config)
    callback = next(
        entry["callback"].__wrapped__ for entry in app.callback_map.values()
        if any("modal-label-save" in i["id"] for i in entry.get("inputs", []))
        and "callback" in entry
    )
    baseline = {"item_id": "clip", "annotations": {"labels": ["Whale"], "pending_save": False}}
    draft = deepcopy(baseline)
    draft["annotations"]["pending_save"] = True
    box = {"label": "Whale", "source": "manual", "annotation_extent": {
        "type": "time_freq_box",
        "time_start_sec": 1, "time_end_sec": 2, "freq_min_hz": 10, "freq_max_hz": 20,
    }}
    output = tmp_path / "labels.json"
    with patch.object(editor_save_callbacks, "ctx", SimpleNamespace(triggered_id={"type": "modal-label-save"})):
        updated, dirty, _, saved_item = callback(
            card_save_clicks=[], modal_save_clicks=[1], modal_item_id="clip",
            label_data={"items": [baseline]}, modal_bbox_store={"item_id": "clip", "boxes": [box]},
            profile={"name": "Test", "email": "test@example.test"}, cfg={},
            label_output_path=str(output), card_note_values=[], card_note_ids=[],
            modal_note_text="", modal_item=draft,
        )
    assert output.exists()
    assert dirty == {"dirty": False, "item_id": "clip"}
    assert saved_item["annotations"]["box_annotations"][0]["annotation_extent"] == box["annotation_extent"]
    assert updated["items"][0]["annotations"]["pending_save"] is False
    assert baseline["annotations"]["pending_save"] is False
    assert draft["annotations"]["pending_save"] is True


@pytest.mark.parametrize("action", ["unsaved-stay-btn", "unsaved-discard-btn"])
def test_unsaved_actions_without_verification_cards_return_valid_http_response(mock_config, action):
    app = create_app(mock_config)
    key, entry = next(
        (key, entry) for key, entry in app.callback_map.items()
        if any(i["id"] == "unsaved-stay-btn" for i in entry.get("inputs", []))
    )
    outputs = [
        [] if isinstance(output.component_id, dict)
        else {"id": output.component_id, "property": output.component_property}
        for output in entry["output"]
    ]
    states = [dict(state, value=[] if state["id"].startswith("{") else None) for state in entry["state"]]
    response = app.server.test_client().post("/_dash-update-component", json={
        "output": key, "outputs": outputs,
        "inputs": [dict(i, value=int(i["id"] == action)) for i in entry["inputs"]],
        "state": states, "changedPropIds": [f"{action}.n_clicks"],
    })
    assert response.status_code == 200
    assert response.json["response"]["unsaved-changes-modal"]["is_open"] is False


def test_verify_grid_keeps_cards_when_a_review_leaves_the_page_as_it_was(mock_config):
    # Discarding or saving a review re-sends the data, thresholds and class
    # filter. Dash 4 remounts every card of a grid sent again, so rebuilding it
    # reloaded every spectrogram on the page; only changed cards may be replaced.
    from app.callbacks.data import render_callbacks
    from app.services.verify_modal_cache import (
        get_verify_modal_item,
        register_verify_modal_items,
        update_verify_modal_item,
    )

    app = create_app(mock_config)
    render = next(
        entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if "callback" in entry and entry["callback"].__wrapped__.__name__ == "render_verify"
    )
    items = [
        {"item_id": f"clip-{n}", "predictions": {"labels": ["Whale"], "confidence": {"Whale": 0.9}}}
        for n in range(3)
    ]
    key = register_verify_modal_items({"items": items, "summary": {"total_items": 3}, "load_timestamp": 1})
    cfg = {"display": {"items_per_page": 25}}

    def run(revision, previous_ui_ready, page=0, status="all"):
        return render(
            key, revision, {"__global__": 0.5}, None, status, page,
            False, False, None, None, None, None, cfg, None, "verify", previous_ui_ready,
        )

    revision = {"verify-data-cache-revision-store.data": "verify-data-cache-revision-store"}
    with patch.object(render_callbacks, "ctx", SimpleNamespace(triggered_prop_ids=revision)), \
            patch.object(render_callbacks, "set_props") as set_props:
        first = run(1, None)
        assert first[1] is not no_update
        ready = first[8]

        # An edit discarded: same clips, same reviews, new revision.
        discarded = run(2, ready)
        assert discarded[1] is no_update
        set_props.assert_not_called()

        # A review saved: only that clip's card is replaced.
        saved_item = dict(get_verify_modal_item(key, "clip-1"), annotations={"labels": ["Whale"], "verified": True})
        update_verify_modal_item(key, saved_item)
        saved = run(3, discarded[8])
        assert saved[1] is no_update
        assert set_props.call_count == 1
        assert set_props.call_args[0][0]["item_id"] == "clip-1"

        # A filter that changes which clips are shown still rebuilds the grid.
        assert run(4, saved[8], status="unverified")[1] is not no_update
