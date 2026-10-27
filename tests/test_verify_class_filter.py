from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate

import app.callbacks.verify.class_filter_callbacks as class_filter_callbacks
from app.main import create_app

# Classes as the fin whale dashboard lists them once its review added vessel,
# humpback and instrumentation labels to fin whale.
OPTIONS = [
    "Anthropophony",
    "Anthropophony > Vessel",
    "Biophony",
    "Biophony > Marine mammal",
    "Biophony > Marine mammal > Cetacean",
    "Biophony > Marine mammal > Cetacean > Baleen whale",
    "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
    "Biophony > Marine mammal > Cetacean > Baleen whale > Humpback whale",
]
FIN = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
VESSEL = "Anthropophony > Vessel"
BOXES = [{"type": "verify-filter-checkbox", "path": path} for path in OPTIONS]


@pytest.fixture
def callbacks(mock_config):
    app = create_app(mock_config)
    return {
        entry["callback"].__wrapped__.__name__: entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if "callback" in entry
    }


def triggered(target, count=1):
    return patch.object(class_filter_callbacks, "ctx", SimpleNamespace(triggered_id=target, triggered=[{}] * count))


def test_a_data_refresh_with_the_same_classes_sends_no_filter_update(callbacks):
    # Each save refreshes the data store; an unchanged filter sent again set off the
    # grid's "Updating spectrograms" notice over the open clip.
    sync = callbacks["sync_verify_class_filter_state"]

    def apply(outputs, stores):  # as Dash does: no_update keeps the store's value
        return tuple(old if new is no_update else new for new, old in zip(outputs, stores))

    data = {"items": [{"predictions": {"model_outputs": [{"class_hierarchy": FIN, "score": 0.8}]}}]}
    stores = apply(sync(data, None, None, None), (None, None, None))
    assert FIN in stores[0] and stores[2]
    assert sync(data, *stores) == (no_update, no_update, no_update)
    # New classes still come through.
    more = {"items": data["items"] + [{"predictions": {"model_outputs": [{"class_hierarchy": VESSEL, "score": 0.6}]}}]}
    assert VESSEL in sync(more, *stores)[0]


def test_select_all_is_left_alone_while_classes_load(callbacks):
    # Unticking it here used to clear every class as the page opened.
    assert callbacks["render_verify_class_filter_tree"]([], None, [])[2] is no_update


def test_select_all_acts_only_when_it_disagrees_with_the_selection(callbacks):
    update = callbacks["update_verify_filter_selection"]
    with triggered("verify-class-filter-select-all"):
        with pytest.raises(PreventUpdate):
            update([], True, [], OPTIONS, None)  # shows "all", which it is
        with pytest.raises(PreventUpdate):
            update([], False, [], OPTIONS, [FIN])  # shows a partial selection
        assert update([], False, [], OPTIONS, None) == []  # reviewer cleared it
        assert update([], True, [], OPTIONS, [FIN]) is None  # reviewer selected all


def test_a_redrawn_tree_does_not_narrow_the_filter_to_its_first_class(callbacks):
    update = callbacks["update_verify_filter_selection"]
    ticked = [True] * len(BOXES)
    with triggered(BOXES[0], count=len(BOXES)):
        with pytest.raises(PreventUpdate):
            update(ticked, True, BOXES, OPTIONS, [])
    # A click on one class still toggles it.
    with triggered(BOXES[1]):
        assert update([box["path"] == VESSEL for box in BOXES], False, BOXES, OPTIONS, []) == [VESSEL]
