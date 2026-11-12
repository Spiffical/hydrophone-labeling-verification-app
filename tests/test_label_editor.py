"""Edit labels dialog: Save stays put, the tree only opens on a search, names tick boxes."""
from types import SimpleNamespace
from unittest.mock import patch

from dash import no_update

from app.callbacks.label.editor_modal_callbacks import _build_editor_body
from app.components import hierarchical_selector as selector
from app.layouts.main_layout import create_main_layout

FIN = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"


def walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from walk(child)
    elif hasattr(component, "to_plotly_json"):
        yield component
        yield from walk(getattr(component, "children", None))


def _trigger(kind):
    return SimpleNamespace(triggered=[{"value": 1}], triggered_id={"type": kind, "filename": "clip"})


def _filter(expanded, trigger_kind, search="whale", selected=()):
    with patch.object(selector.dash, "callback_context", _trigger(trigger_kind)):
        return selector.filter_tree(list(expanded), list(selected), 1, {}, {}, search, [], {"filename": "clip"}, False)


def _open_paths(tree):
    return {
        node.id["path"]
        for node in walk(tree)
        if isinstance(getattr(node, "id", None), dict)
        and node.id.get("type") == "children-container"
        and (getattr(node, "style", None) or {}).get("display") == "block"
    }


def test_a_search_opens_its_matches_once_and_remembers_them():
    tree, expanded = _filter([], "search-debounce-timer")
    assert "Biophony > Marine mammal" in expanded
    assert "Biophony > Marine mammal" in _open_paths(tree)


def test_ticking_or_collapsing_during_a_search_does_not_reopen_branches():
    _tree, expanded = _filter([], "search-debounce-timer")
    collapsed = [path for path in expanded if path != "Biophony > Marine mammal"]
    for kind in ("tree-expanded-store", "selected-labels-store"):
        tree, update = _filter(collapsed, kind, selected=[FIN])
        assert update is no_update
        assert "Biophony > Marine mammal" not in _open_paths(tree)


def test_label_names_are_checkbox_labels():
    tree = selector.build_tree_children("clip", [], expanded_paths=[])
    checks = [node for node in walk(tree) if getattr(node, "id", {}).get("type") == "hierarchical-checkbox"]
    assert checks and all(check.label for check in checks)


def test_editor_body_scrolls_at_a_fixed_height_and_the_note_is_themed(mock_config):
    layout = create_main_layout(mock_config)
    editor = next(node for node in walk(layout) if getattr(node, "id", None) == "label-editor-modal")
    assert editor.scrollable is True
    assert "label-editor-modal" in editor.className

    _item_id, body = _build_editor_body(
        {"item_id": "clip", "annotations": {"labels": [FIN], "notes": "hi"}},
        "label", {}, None, selector.create_hierarchical_selector,
    )
    note = next(node for node in walk(body) if getattr(node, "id", {}).get("type") == "note-editor-text")
    assert "note-editor-textarea" in note.className


class _Registry:
    """Collects callbacks the way a Dash app would register them."""

    def __init__(self):
        self.functions = {}

    def callback(self, *args, **kwargs):
        def register(function):
            self.functions[function.__name__] = function
            return function
        return register

    def clientside_callback(self, *args, **kwargs):
        return None


def _open_editor_from_review_window():
    import logging

    from app.callbacks.common.profile_guard import is_profile_complete, profile_name_email
    from app.callbacks.common.register_helpers import build_require_complete_profile
    from app.callbacks.label.editor_modal_callbacks import register_label_editor_modal_callbacks

    registry = _Registry()
    unused = lambda *args, **kwargs: None  # noqa: E731
    register_label_editor_modal_callbacks(
        registry,
        _get_mode_data=unused,
        _require_complete_profile=build_require_complete_profile(
            is_profile_complete=is_profile_complete, profile_name_email=profile_name_email, logger=logging.getLogger("test")
        ),
        _filter_predictions=unused,
        create_hierarchical_selector=unused,
        _extract_label_extent_map_from_boxes=unused,
        _profile_actor=unused,
        _update_item_labels=unused,
        _update_item_notes=unused,
        save_label_mode=unused,
        _build_modal_boxes_from_item=unused,
        _build_modal_item_actions=unused,
        _modal_snapshot_payload=unused,
    )
    return registry.functions["open_label_editor_from_modal"]


def test_edit_labels_that_cannot_open_takes_the_updating_overlay_away():
    # The click puts "Updating spectrogram" over the clip; when the editor does not
    # open (no reviewer name and email yet, or explore mode), the overlay must go
    # again, or the spectrogram stays covered.
    import pytest
    from dash.exceptions import PreventUpdate

    open_editor = _open_editor_from_review_window()
    no_profile = open_editor([1], {"item_id": "clip-a"}, {}, {}, "verify", {})
    assert no_profile == (no_update, no_update, no_update, no_update, False)
    explore = open_editor([1], {"item_id": "clip-a"}, {}, {}, "explore", {"name": "A", "email": "a@example.org"})
    assert explore[-1] is False and explore[0] is no_update
    # No click at all: nothing put the overlay up, nothing to change.
    with pytest.raises(PreventUpdate):
        open_editor([0], {"item_id": "clip-a"}, {}, {}, "verify", {})
