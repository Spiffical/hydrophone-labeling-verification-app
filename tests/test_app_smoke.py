from app.main import create_app
from app.layouts.main_layout import create_main_layout


def _find_component(node, target_id):
    if getattr(node, "id", None) == target_id:
        return node
    children = getattr(node, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children] if children is not None else []
    for child in children:
        found = _find_component(child, target_id)
        if found is not None:
            return found
    return None


def test_create_app(mock_config):
    app = create_app(mock_config)
    assert app.layout is not None


def test_latency_sensitive_bbox_actions_are_clientside(mock_config):
    app = create_app(mock_config)
    bbox_callbacks = {
        entry["clientside_function"]["function_name"]: entry
        for entry in app._callback_list
        if (entry.get("clientside_function") or {}).get("namespace") == "bboxInteractions"
    }

    assert set(bbox_callbacks) == {"activateDraw", "deleteBox", "openEditor"}
    assert "modal-image-graph.figure" not in bbox_callbacks["activateDraw"]["output"]


def test_label_startup_uses_label_folder_for_data_root(mock_config):
    layout = create_main_layout(mock_config)

    data_root = _find_component(layout, "data-root-path-store")
    load_trigger = _find_component(layout, "data-load-trigger-store")

    assert data_root.data == mock_config["label"]["folder"]
    assert load_trigger.data["mode"] == "label"
    assert load_trigger.data["config"] == mock_config
