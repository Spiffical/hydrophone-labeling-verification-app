"""Box checks and reviewer notes for a dashboard of boxes to correct (bbox_list.js)."""

import json

from app.components.modal import create_spectrogram_modal
from app.config import _box_checks_config
from app.main import create_app
from app.utils.data_loading import load_whale_mode

FIN = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
CHECKS = {
    "label": FIN,
    "max_box_seconds": 3.0,
    "detector_window_seconds": 9.6,
    "tag_bands_hz": {"20Hz": [0, 35], "40Hz": [35, 1000]},
}


def _find(node, target_id):
    if getattr(node, "id", None) == target_id:
        return node
    children = getattr(node, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children] if children is not None else []
    for child in children:
        found = _find(child, target_id)
        if found is not None:
            return found
    return None


def test_box_checks_are_off_unless_a_dashboard_turns_them_on():
    assert _box_checks_config(None) is None
    assert _box_checks_config({"enabled": False, "max_box_seconds": 3}) is None
    assert _box_checks_config(CHECKS) == CHECKS
    # Bad values are dropped rather than guessed.
    assert _box_checks_config({
        "label": "  ",
        "max_box_seconds": "x",
        "detector_window_seconds": -1,
        "tag_bands_hz": {"20Hz": [40, 35], "40Hz": ["a", 1], "30Hz": [20, 37], "x": 5},
    }) == {"label": None, "max_box_seconds": None, "detector_window_seconds": None, "tag_bands_hz": {"30Hz": [20.0, 37.0]}}


def test_the_box_list_gets_the_checks_and_the_open_item(mock_config):
    store = _find(create_spectrogram_modal({**mock_config, "box_checks": CHECKS}), "modal-bbox-list-config-store")
    assert store.data["box_checks"] == CHECKS
    assert _find(create_spectrogram_modal(mock_config), "modal-bbox-list-config-store").data["box_checks"] is None

    app = create_app(mock_config)
    render = next(
        entry for entry in app._callback_list
        if (entry.get("clientside_function") or {}).get("function_name") == "render"
        and (entry.get("clientside_function") or {}).get("namespace") == "bboxList"
    )
    # The list config first, then the item with its notes (render's last two arguments).
    assert [state["id"] for state in render["state"]] == ["modal-bbox-list-config-store", "modal-item-store"]


def test_reviewer_notes_on_an_item_survive_loading(tmp_path):
    hints = ["Box at 0.5–2.1 s may start earlier",
             {"text": "Accepted as fin whale with no boxes: draw a box on each call", "only_without_boxes": True}]
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps({"schema_version": "2.1", "items": [{
        "item_id": "fw-clip-1",
        "audio_start_time": "2025-04-01T04:36:40.300Z",
        "model_outputs": [{"class_hierarchy": FIN, "score": 0.97}],
        "review_hints": hints,
        "verifications": [],
    }]}))
    loaded = load_whale_mode({"whale": {"predictions_json": str(predictions)}})
    # Extra source fields are kept in metadata, where bbox_list.js reads them.
    assert loaded["items"][0]["metadata"]["review_hints"] == hints


def test_reference_boxes_are_drawn_dashed_after_the_boxes():
    from app.callbacks.modal.figure_helpers import apply_modal_boxes_to_figure
    from app.services.modal_boxes import reference_box_extents

    lynn = {"type": "time_freq_box", "time_start_sec": 72.252, "time_end_sec": 79.176,
            "freq_min_hz": 16.388, "freq_max_hz": 33.742}
    item = {"item_id": "clip-1", "metadata": {"reference_boxes": {
        "title": "Lynn's boxes", "boxes": [{"annotation_extent": lynn, "tag": "30Hz"}, {"type": "clip"}, "bad"]}}}
    assert reference_box_extents(item) == [lynn]
    assert reference_box_extents({"reference_boxes": [lynn]}) == [lynn]
    assert reference_box_extents({}) == []

    figure = {"data": [], "layout": {"meta": {"x_min": 0, "x_max": 300, "y_min": 5, "y_max": 100,
                                               "reference_boxes": reference_box_extents(item)}, "shapes": []}}
    box = {"label": FIN, "decision": "accepted", "annotation_extent": dict(lynn, time_start_sec=75.0, time_end_sec=76.8)}
    shapes = apply_modal_boxes_to_figure(figure, [box])["layout"]["shapes"]
    assert [shape.get("name") for shape in shapes] == ["playback-marker", "bbox-0", "ref-box-0"]
    reference = shapes[-1]
    assert reference["editable"] is False and reference["line"]["dash"] == "dash"
    assert (reference["x0"], reference["x1"]) == (72.252, 79.176)
