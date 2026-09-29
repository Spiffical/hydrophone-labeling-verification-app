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
