from app.callbacks.modal.actions_helpers import build_modal_item_actions
from app.components.modal import create_spectrogram_modal
from app.config import get_repo_root
from app.main import create_app
from app.services.bbox_tags import load_bbox_tag_options


FIN_WHALE = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
TAGS = [{"label": "20 Hz", "value": "20Hz"}, {"label": "40 Hz", "value": "40Hz"}]


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children] if children is not None else []
    for child in children:
        yield from _walk(child)


def _components_by_id(root):
    return {
        str(getattr(node, "id")): node
        for node in _walk(root)
        if getattr(node, "id", None) is not None
    }


def test_modal_has_box_toolbar_panel_and_tag_stores():
    modal = create_spectrogram_modal({"bounding_box_tags": {"options": TAGS}})
    components = _components_by_id(modal)

    assert "modal-bbox-toolbar" in components
    assert "modal-bbox-panel" in components
    assert "modal-bbox-command-store" in components
    assert "modal-bbox-edit-request-store" in components
    # The tag for new boxes carries over between clips for the browser session.
    assert components["modal-bbox-active-tag-store"].storage_type == "session"
    assert components["modal-bbox-list-config-store"].data == {
        "tag_options": TAGS,
        # Inline options without a species apply to every box.
        "tag_sets": [{"label": None, "options": TAGS}],
        "bulk_tagging": True,
    }
    help_text = " ".join(node for node in _walk(modal) if isinstance(node, str))
    assert "1–2" in help_text
    assert "Tag new boxes · 0 no tag" in help_text


def test_default_tags_belong_to_fin_whale_boxes(mock_config):
    app_config = {**mock_config, "bounding_box_tags": load_bbox_tag_options(get_repo_root(), {})}
    modal = create_spectrogram_modal(app_config)
    data = _components_by_id(modal)["modal-bbox-list-config-store"].data

    assert data["tag_sets"] == [{
        "label": FIN_WHALE,
        "options": [
            {"label": "20 Hz", "value": "20Hz"},
            {"label": "30 Hz", "value": "30Hz"},
            {"label": "40 Hz", "value": "40Hz"},
        ],
    }]
    help_text = " ".join(node for node in _walk(modal) if isinstance(node, str))
    assert "Tag new fin whale boxes · 0 no tag" in help_text


def test_bulk_tagging_defaults_on_and_can_be_disabled():
    repo_root = get_repo_root()
    assert load_bbox_tag_options(repo_root, {})["bulk_tagging"] is True
    assert load_bbox_tag_options(repo_root, {"bulk_tagging": False})["bulk_tagging"] is False

    modal = create_spectrogram_modal({"bounding_box_tags": {"options": TAGS, "bulk_tagging": False}})
    assert _components_by_id(modal)["modal-bbox-list-config-store"].data["bulk_tagging"] is False


def test_item_actions_panel_keeps_label_controls_but_not_the_box_list():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE]},
        "annotations": {"labels": [FIN_WHALE], "verified": True},
    }

    actions = build_modal_item_actions(item, "verify", {"__global__": 0.5})
    ids = [getattr(node, "id", None) for node in _walk(actions)]
    classes = " ".join(str(getattr(node, "className", "") or "") for node in _walk(actions))

    assert {"type": "modal-label-add-box", "label": FIN_WHALE} in ids
    assert not any(isinstance(node_id, dict) and node_id.get("type") == "modal-bbox-tag-dropdown" for node_id in ids)
    assert "modal-bbox-panel" not in classes
    assert "modal-bbox-list" not in classes


def test_box_list_is_rendered_and_tagged_in_the_browser(mock_config):
    app = create_app(mock_config)
    list_callbacks = {
        entry["clientside_function"]["function_name"]: entry
        for entry in app._callback_list
        if (entry.get("clientside_function") or {}).get("namespace") == "bboxList"
    }

    assert set(list_callbacks) == {"render", "applyCommand", "editorTagOptions"}
    # The box editor lists the tags of the species chosen in it.
    assert list_callbacks["editorTagOptions"]["output"] == "bbox-editor-tag-dropdown.options"
    assert ("bbox-editor-label-dropdown", "value") in {
        (i["id"], i["property"]) for i in list_callbacks["editorTagOptions"]["inputs"]
    }
    render_inputs = {(i["id"], i["property"]) for i in list_callbacks["render"]["inputs"]}
    assert ("modal-bbox-store", "data") in render_inputs
    assert ("modal-bbox-active-tag-store", "data") in render_inputs
    assert "modal-bbox-store.data" in list_callbacks["applyCommand"]["output"]
    assert "modal-image-graph.figure" in list_callbacks["applyCommand"]["output"]

    # No server callback listens to per-row tag dropdowns any more.
    for entry in app._callback_list:
        for input_obj in entry.get("inputs", []):
            assert "modal-bbox-tag-dropdown" not in str(input_obj["id"])


def test_box_edits_do_not_rebuild_the_actions_panel_directly(mock_config):
    # Rebuilding modal-item-actions on every box change reset the box list's scroll.
    app = create_app(mock_config)
    refresh = [
        entry
        for entry in app._callback_list
        if not entry.get("clientside_function")
        and "modal-item-actions.children" in entry.get("output", "")
        and any(i["id"] == "modal-item-store" for i in entry.get("inputs", []))
    ]

    assert len(refresh) == 1
    assert not any(i["id"] == "modal-bbox-store" for i in refresh[0]["inputs"])


def test_box_editor_opens_from_list_requests(mock_config):
    app = create_app(mock_config)
    open_editor = next(
        entry
        for entry in app._callback_list
        if (entry.get("clientside_function") or {}).get("function_name") == "openEditor"
    )
    inputs = {(i["id"], i["property"]) for i in open_editor["inputs"]}

    assert ("modal-bbox-edit-request-store", "data") in inputs
    assert ("modal-image-graph", "clickData") in inputs


def test_new_boxes_read_the_tag_for_new_boxes(mock_config):
    app = create_app(mock_config)
    draw = next(
        entry
        for entry in app._callback_list
        if (entry.get("clientside_function") or {}).get("function_name") == "updateBoxesFromGraph"
    )
    states = [(s["id"], s["property"]) for s in draw["state"]]

    # bbox_clientside.js reads these as its last two arguments.
    assert states[-2:] == [
        ("modal-bbox-active-tag-store", "data"),
        ("modal-bbox-list-config-store", "data"),
    ]


def _find_by_class(root, class_name):
    return next(
        node for node in _walk(root)
        if class_name in str(getattr(node, "className", "") or "").split()
    )


def test_modal_puts_plot_and_sidebar_on_one_screen():
    modal = create_spectrogram_modal({"bounding_box_tags": {"options": TAGS}})

    def ids_in(node):
        return {str(getattr(child, "id", None)) for child in _walk(node)}

    plot_column = _find_by_class(modal, "modal-workbench-plot")
    sidebar = _find_by_class(modal, "modal-workbench-side")
    toolbar = _find_by_class(modal, "modal-workbench-toolbar")
    assert {"modal-image-graph", "modal-audio-player"} <= ids_in(plot_column)
    assert {"modal-item-actions", "modal-bbox-panel"} <= ids_in(sidebar)
    assert {"modal-bbox-toolbar", "modal-colormap-toggle"} <= ids_in(toolbar)
    assert "modal-save-next" in _components_by_id(modal)


def test_modal_audio_player_can_fold_away_its_controls(mock_root):
    from app.components.audio_player import create_modal_audio_player

    audio_path = next((mock_root / "label" / "audio").glob("*.wav"))
    player = create_modal_audio_player(str(audio_path), "clip-1")
    toggles = [
        node for node in _walk(player)
        if "modal-audio-tools-toggle" in str(getattr(node, "className", "") or "")
    ]

    assert len(toggles) == 1


def test_box_editor_drops_a_call_type_when_the_box_changes_species(mock_config):
    humpback = "Biophony > Marine mammal > Cetacean > Baleen whale > Humpback whale"
    app = create_app(mock_config)
    apply = next(
        entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if "callback" in entry and entry["callback"].__wrapped__.__name__ == "apply_modal_box_editor"
    )
    extent = {"type": "time_freq_box", "time_start_sec": 1.0, "time_end_sec": 2.0, "freq_min_hz": 15.0, "freq_max_hz": 30.0}
    store = {"item_id": "clip-1", "boxes": [{
        "label": FIN_WHALE, "annotation_extent": extent, "tag": "20Hz",
        "tag_source": "human", "tag_scope": "time_freq_box", "source": "manual", "decision": "added",
    }]}
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE, humpback]},
        "annotations": {"labels": [FIN_WHALE, humpback], "boxes": store["boxes"]},
    }
    figure = {"data": [], "layout": {"meta": {"x_min": 0, "x_max": 10, "y_min": 5, "y_max": 100, "x_to_seconds": 1, "y_to_hz": 1}}}
    list_config = {"tag_sets": [{"label": FIN_WHALE, "options": TAGS}]}
    profile = {"name": "Tester", "email": "tester@example.com"}

    def tag_after_edit(label):
        result = apply(1, 0, label, "20Hz", 1.0, 2.0, 15.0, 30.0, store, figure, item, {}, None,
                       "clip-1", "verify", profile, list_config)
        return result[0]["boxes"][0].get("tag")

    assert tag_after_edit(FIN_WHALE) == "20Hz"
    assert tag_after_edit(humpback) is None
