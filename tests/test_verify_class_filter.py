from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dash.exceptions import PreventUpdate

import app.callbacks.verify.class_filter_callbacks as class_filter_callbacks
from app.callbacks.verify.class_filter_callbacks import selection_summary
from app.layouts.main_layout import create_main_layout
from app.main import create_app
from taxonomy.hierarchical_labels import get_all_paths, path_to_string

FIN = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
VESSEL = "Anthropophony > Vessel"


@pytest.fixture
def callbacks(mock_config):
    app = create_app(mock_config)
    return {
        entry["callback"].__wrapped__.__name__: entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if "callback" in entry
    }


def clicked(target, value=1):
    return patch.object(
        class_filter_callbacks,
        "ctx",
        SimpleNamespace(triggered_id=target, triggered=[{"value": value}]),
    )


def components_with_id_type(component, id_type):
    found = []
    if isinstance(component, (list, tuple)):
        for child in component:
            found.extend(components_with_id_type(child, id_type))
    elif component is not None and not isinstance(component, str):
        component_id = getattr(component, "id", None)
        if isinstance(component_id, dict) and component_id.get("type") == id_type:
            found.append(component_id)
        found.extend(components_with_id_type(getattr(component, "children", None), id_type))
    return found


def test_the_selection_offers_the_whole_hierarchy_whatever_the_model_outputs(mock_config):
    # Reviewers label from the full list, so it must not shrink to the model's classes.
    layout = create_main_layout(mock_config)

    categories = {entry["category"] for entry in components_with_id_type(layout, "verify-category-toggle")}
    nodes = {entry["path"] for entry in components_with_id_type(layout, "verify-filter-node")}
    every_path = {path_to_string(path) for path in get_all_paths()}

    assert categories == {path for path in every_path if " > " not in path}
    assert nodes == {path for path in every_path if " > " in path}
    assert FIN in nodes


def test_a_category_pill_turns_its_category_on_and_off(callbacks):
    update = callbacks["update_class_selection"]
    pill = {"type": "verify-category-toggle", "category": "Biophony"}

    with clicked(pill):
        assert update([1], [], 0, None) == (["Biophony"], 0)
        assert update([2], [], 0, ["Biophony"]) == (None, 0)
        assert update([1], [], 0, [VESSEL]) == ([VESSEL, "Biophony"], 0)


def test_a_class_in_a_menu_narrows_its_selected_category(callbacks):
    update = callbacks["update_class_selection"]
    node = {"type": "verify-filter-node", "path": VESSEL}

    with clicked(node):
        assert update([], [1], 0, ["Anthropophony"]) == ([VESSEL], 0)


def test_clear_shows_every_class_again(callbacks):
    with clicked("verify-selection-clear"):
        assert callbacks["update_class_selection"]([], [], 1, [VESSEL, FIN]) == (None, 0)


def test_a_redrawn_control_is_not_a_click(callbacks):
    with clicked({"type": "verify-filter-node", "path": VESSEL}, value=0):
        with pytest.raises(PreventUpdate):
            callbacks["update_class_selection"]([], [0], 0, None)


def test_the_selection_shows_on_the_pills_and_in_the_menus(callbacks):
    pills = [{"category": "Anthropophony"}, {"category": "Biophony"}, {"category": "Geophony"}]
    nodes = [{"path": VESSEL}, {"path": f"{VESSEL} > Tug"}, {"path": "Anthropophony > Sonar"}]

    pill_classes, node_classes, summary, clear_style = callbacks["render_class_selection"](
        [VESSEL, "Biophony"], pills, nodes
    )

    assert [value.split("--")[-1] for value in pill_classes] == ["partial", "on", "off"]
    assert [value.split("--")[-1] for value in node_classes] == ["on", "implied", "off"]
    assert summary == "2 selected"
    assert clear_style == {}


def test_with_nothing_selected_clear_is_hidden(callbacks):
    pill_classes, _, summary, clear_style = callbacks["render_class_selection"](
        None, [{"category": "Biophony"}], []
    )

    assert pill_classes == ["review-category-toggle review-category-toggle--off"]
    assert summary == "All classes"
    assert clear_style == {"display": "none"}


def test_selection_summary_names_a_single_class():
    assert selection_summary(None) == "All classes"
    assert selection_summary([FIN]) == "Fin whale"
    assert selection_summary([FIN, VESSEL]) == "2 selected"
