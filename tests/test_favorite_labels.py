"""Personal shortcuts must not alter annotations until explicitly picked/saved."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate

from app.components import hierarchical_selector as selector
from app.services.favorite_labels import favorite_labels, toggle_favorite

AMBIENT = "Other > Ambient sound"
UNKNOWN = "Other > Unknown sound of interest"
PROFILE = {"email": "reviewer@example.test"}


def context(path=UNKNOWN, value=1):
    return SimpleNamespace(triggered=[{"value": value}],
                           triggered_id={"filename": "clip", "path": path})


def walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from walk(child)
    elif hasattr(component, "to_plotly_json"):
        yield component
        yield from walk(getattr(component, "children", None))


def test_favorites_are_personal_immutable_and_toggleable():
    original = {"someone@example.test": [AMBIENT]}
    saved = deepcopy(original)
    store = toggle_favorite(original, PROFILE, UNKNOWN)
    assert original == saved
    assert favorite_labels(store, PROFILE) == [UNKNOWN]
    assert favorite_labels(store, {"email": " REVIEWER@EXAMPLE.TEST "}) == [UNKNOWN]
    assert favorite_labels(store, {"email": "someone@example.test"}) == [AMBIENT]
    assert favorite_labels(store, None) == []
    assert favorite_labels(toggle_favorite(store, PROFILE, UNKNOWN), PROFILE) == []


@pytest.mark.parametrize("store", [None, [], {PROFILE["email"]: "invalid"}])
def test_malformed_preferences_are_ignored(store):
    assert favorite_labels(store, PROFILE) == []


def test_obsolete_invalid_and_duplicate_labels_are_filtered():
    store = {PROFILE["email"]: [UNKNOWN, UNKNOWN, "obsolete", None, {}, "Other"]}
    assert favorite_labels(store, PROFILE) == [UNKNOWN, "Other"]
    assert toggle_favorite(store, PROFILE, "not a label") == store


def test_shortcut_preserves_other_labels_and_records_add_remove_actions():
    with patch.object(selector.dash, "callback_context", context()):
        selected, _, actions = selector.pick_starred_label([1], [AMBIENT], {},
                                                          {"__global__": .75}, "verify", False)
        assert set(selected) == {AMBIENT, UNKNOWN}
        assert actions["clip"][-1]["label"] == UNKNOWN
        assert actions["clip"][-1]["action"] == "add"
        assert actions["clip"][-1]["threshold_used"] == .75
        selected, _, actions = selector.pick_starred_label([1], selected, actions, {}, "verify", False)
        assert selected == [AMBIENT]
        assert actions["clip"][-1]["action"] == "remove"


def test_label_mode_shortcut_does_not_create_verification_actions():
    with patch.object(selector.dash, "callback_context", context()):
        selected, _, actions = selector.pick_starred_label([1], [], {}, {}, "label", False)
    assert selected == [UNKNOWN]
    assert actions is no_update


def test_mounting_controls_does_not_toggle_favorites_selection_or_expansion():
    with patch.object(selector.dash, "callback_context", context(value=0)):
        with pytest.raises(PreventUpdate):
            selector.toggle_starred_label([0], {}, PROFILE)
        with pytest.raises(PreventUpdate):
            selector.pick_starred_label([0], [], {}, {}, "verify", False)
        with pytest.raises(PreventUpdate):
            selector.toggle_tree_node([0], [], [])


def test_readonly_shortcuts_are_disabled_and_ignore_clicks():
    buttons = [c for c in walk(selector.create_favorite_labels_panel("clip", [UNKNOWN], [], True))
               if getattr(c, "id", None)]
    assert buttons and all(c.disabled for c in buttons)
    with patch.object(selector.dash, "callback_context", context()):
        with pytest.raises(PreventUpdate):
            selector.pick_starred_label([1], [], {}, {}, "verify", True)


def test_favorites_render_in_search_and_selected_state_is_independent():
    tree, _expanded = selector.filter_tree([], [AMBIENT], 1, {PROFILE["email"]: [UNKNOWN]}, PROFILE,
                                           "unknown sound of interest", [], {"filename": "clip"}, False)
    star = next(c for c in walk(tree) if getattr(c, "id", {}) == {
        "type": "favorite-label-toggle", "filename": "clip", "path": UNKNOWN})
    assert star.children == "★"
    panel = selector.render_starred_labels({PROFILE["email"]: [UNKNOWN]}, PROFILE,
                                           [AMBIENT], {"filename": "other-clip"}, False)
    pick = next(c for c in walk(panel) if getattr(c, "id", {}))
    assert pick.id["filename"] == "other-clip"
    assert getattr(pick, "aria-pressed") == "false"
