from copy import deepcopy

from app.callbacks.modal.bbox_graph_helpers import (
    extract_coord_updates,
    filter_payload_shapes,
    process_coord_updates,
    process_payload_shapes,
    resolve_add_mode,
)
from app.callbacks.modal.figure_helpers import BBOX_DELETE_TRACE_NAME, BBOX_EDIT_TRACE_NAME, apply_modal_boxes_to_figure
from app.callbacks.modal.bbox_editor_callbacks import update_modal_item_for_box_edit
from app.callbacks.modal.bbox_sync_callbacks import unverify_predictions_without_boxes
from app.components.modal import create_spectrogram_modal
from app.services.annotations import (
    extract_box_annotations_from_boxes,
    extract_label_extent_map_from_boxes,
    ordered_unique_labels,
    safe_float,
)
from app.services.modal_boxes import extent_to_shape, shape_to_extent
from app.services.verification import get_item_rejected_labels, get_modal_label_sets


AXIS_META = {
    "x_min": 0.0,
    "x_max": 10.0,
    "y_min": 0.0,
    "y_max": 100.0,
    "x_to_seconds": 1.0,
    "y_to_hz": 1.0,
}


def _debug(*_args, **_kwargs):
    return None


def _extent(x0=1.0, x1=3.0, y0=20.0, y1=40.0):
    return {
        "type": "time_freq_box",
        "time_start_sec": x0,
        "time_end_sec": x1,
        "freq_min_hz": y0,
        "freq_max_hz": y1,
    }


def _box(label="Bio > Whale", extent=None, source="manual", decision="added", tag=None):
    box = {
        "label": label,
        "annotation_extent": extent or _extent(),
        "source": source,
        "decision": decision,
    }
    if tag:
        box["tag"] = tag
    return box


def _walk_components(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk_components(child)
        return
    if component is None:
        return
    yield component
    children = getattr(component, "children", None)
    yield from _walk_components(children)


def _modal_graph():
    modal = create_spectrogram_modal()
    for component in _walk_components(modal):
        if getattr(component, "id", None) == "modal-image-graph":
            return component
    raise AssertionError("modal-image-graph not found")


def test_modal_graph_hides_plotly_shape_modebar_buttons():
    config = _modal_graph().config

    assert config["modeBarButtonsToAdd"] == ["drawrect"]
    removed = set(config.get("modeBarButtonsToRemove") or [])
    assert {
        "drawline",
        "drawopenpath",
        "drawclosedpath",
        "drawcircle",
        "eraseshape",
        "lasso2d",
        "select2d",
    }.issubset(removed)
    assert config["edits"]["shapePosition"] is True


def test_spectrogram_modal_includes_bbox_editor_and_configured_tags():
    modal = create_spectrogram_modal(
        {"bounding_box_tags": {"options": [{"label": "20 Hz", "value": "20Hz"}]}}
    )
    editor = None
    tag_dropdown = None
    for component in _walk_components(modal):
        if getattr(component, "id", None) == "bbox-editor-modal":
            editor = component
        if getattr(component, "id", None) == "bbox-editor-tag-dropdown":
            tag_dropdown = component

    assert editor is not None
    assert tag_dropdown is not None
    assert tag_dropdown.options == [{"label": "20 Hz", "value": "20Hz"}]


def test_filter_payload_shapes_keeps_only_rectangles():
    payload_shapes = filter_payload_shapes(
        {
            "shapes": [
                {"type": "line", "name": "playback-marker"},
                {"type": "rect", "x0": 1, "x1": 2, "y0": 10, "y1": 20},
                {"type": "circle", "x0": 3, "x1": 4, "y0": 30, "y1": 40},
                "not-a-shape",
            ]
        }
    )

    assert payload_shapes == [{"type": "rect", "x0": 1, "x1": 2, "y0": 10, "y1": 20}]


def test_extract_coord_updates_ignores_playback_marker_and_offsets_box_index():
    updates = extract_coord_updates(
        relayout_data={
            "shapes[0].x0": 4,
            "shapes[0].x1": 4,
            "shapes[1].x0": 1.25,
            "shapes[1].y1": 42,
            "xaxis.range[0]": 0,
        },
        safe_float=safe_float,
    )

    assert updates == {0: {"x0": 1.25, "y1": 42.0}}


def test_resolve_add_mode_allows_multiple_boxes_for_same_label_when_requested():
    boxes = [_box(label="Bio > Fin whale")]

    add_mode, existing_labels = resolve_add_mode(
        boxes=boxes,
        chosen_label="Bio > Fin whale",
        allow_existing_label=False,
    )
    assert add_mode is False
    assert existing_labels == ["Bio > Fin whale"]

    add_mode, _ = resolve_add_mode(
        boxes=boxes,
        chosen_label="Bio > Fin whale",
        allow_existing_label=True,
    )
    assert add_mode is True


def test_payload_shapes_adds_new_box_and_clears_active_label():
    existing_box = _box(label="Bio > Blue whale", extent=_extent(1, 2, 10, 20))
    payload_shapes = [
        extent_to_shape(existing_box["annotation_extent"], AXIS_META),
        {"type": "rect", "x0": 4, "x1": 6, "y0": 30, "y1": 55},
    ]

    boxes, updated, force_resync, clear_active_label = process_payload_shapes(
        payload_shapes=payload_shapes,
        boxes=[deepcopy(existing_box)],
        is_add_mode=True,
        chosen_label="Bio > Fin whale",
        axis_meta=AXIS_META,
        safe_float=safe_float,
        shape_to_extent=shape_to_extent,
        extent_to_shape=extent_to_shape,
        bbox_debug=_debug,
    )

    assert updated is True
    assert force_resync is False
    assert clear_active_label is True
    assert boxes[-1] == {
        "label": "Bio > Fin whale",
        "annotation_extent": _extent(4, 6, 30, 55),
        "source": "manual",
        "decision": "added",
    }


def test_coord_updates_can_add_new_box_after_bbox_button_enables_drawing():
    coord_updates = extract_coord_updates(
        relayout_data={
            "shapes[1].x0": 2,
            "shapes[1].x1": 5,
            "shapes[1].y0": 25,
            "shapes[1].y1": 65,
        },
        safe_float=safe_float,
    )

    boxes, updated, force_resync, clear_active_label = process_coord_updates(
        coord_updates=coord_updates,
        boxes=[],
        is_add_mode=True,
        chosen_label="Bio > Fin whale",
        axis_meta=AXIS_META,
        extent_to_shape=extent_to_shape,
        shape_to_extent=shape_to_extent,
        bbox_debug=_debug,
    )

    assert updated is True
    assert force_resync is False
    assert clear_active_label is True
    assert boxes == [
        {
            "label": "Bio > Fin whale",
            "annotation_extent": _extent(2, 5, 25, 65),
            "source": "manual",
            "decision": "added",
        }
    ]


def test_coord_updates_edit_existing_box_extent():
    boxes = [_box(extent=_extent(1, 3, 20, 40))]

    boxes, updated, force_resync, clear_active_label = process_coord_updates(
        coord_updates={0: {"x1": 4.5, "y0": 22.5}},
        boxes=boxes,
        is_add_mode=False,
        chosen_label="",
        axis_meta=AXIS_META,
        extent_to_shape=extent_to_shape,
        shape_to_extent=shape_to_extent,
        bbox_debug=_debug,
    )

    assert updated is True
    assert force_resync is False
    assert clear_active_label is False
    assert boxes[0]["annotation_extent"] == _extent(1, 4.5, 22.5, 40)


def test_payload_shapes_delete_missing_box_when_not_adding():
    first = _box(label="Bio > Fin whale", extent=_extent(1, 2, 10, 20))
    second = _box(label="Bio > Blue whale", extent=_extent(3, 5, 30, 60))

    boxes, updated, force_resync, clear_active_label = process_payload_shapes(
        payload_shapes=[extent_to_shape(second["annotation_extent"], AXIS_META)],
        boxes=[deepcopy(first), deepcopy(second)],
        is_add_mode=False,
        chosen_label="",
        axis_meta=AXIS_META,
        safe_float=safe_float,
        shape_to_extent=shape_to_extent,
        extent_to_shape=extent_to_shape,
        bbox_debug=_debug,
    )

    assert updated is True
    assert force_resync is False
    assert clear_active_label is False
    assert boxes == [second]


def test_payload_shapes_extra_shape_without_active_label_requests_resync():
    boxes = [_box(label="Bio > Fin whale", extent=_extent(1, 2, 10, 20))]
    extra_shape = {"type": "rect", "x0": 3, "x1": 5, "y0": 30, "y1": 60}

    boxes, updated, force_resync, clear_active_label = process_payload_shapes(
        payload_shapes=[
            extent_to_shape(boxes[0]["annotation_extent"], AXIS_META),
            extra_shape,
        ],
        boxes=boxes,
        is_add_mode=False,
        chosen_label="",
        axis_meta=AXIS_META,
        safe_float=safe_float,
        shape_to_extent=shape_to_extent,
        extent_to_shape=extent_to_shape,
        bbox_debug=_debug,
    )

    assert updated is False
    assert force_resync is True
    assert clear_active_label is False
    assert boxes == [_box(label="Bio > Fin whale", extent=_extent(1, 2, 10, 20))]


def test_apply_modal_boxes_to_figure_preserves_marker_and_adds_delete_handle():
    fig = {
        "data": [
            {"type": "heatmap", "z": [[1, 2], [3, 4]]},
            {"type": "scatter", "name": BBOX_DELETE_TRACE_NAME, "customdata": [99]},
        ],
        "layout": {
            "xaxis": {"range": [0, 10]},
            "yaxis": {"range": [0, 100]},
            "shapes": [
                {
                    "type": "line",
                    "name": "playback-marker",
                    "x0": 7,
                    "x1": 7,
                    "y0": 0,
                    "y1": 1,
                    "yref": "paper",
                }
            ],
        },
    }

    updated = apply_modal_boxes_to_figure(
        deepcopy(fig),
        [_box(label="Bio > Marine mammal > Fin whale", extent=_extent(1, 3, 20, 45))],
    )

    shapes = updated["layout"]["shapes"]
    assert shapes[0]["name"] == "playback-marker"
    assert shapes[0]["x0"] == 7
    assert shapes[1]["type"] == "rect"
    assert shapes[1]["editable"] is True
    assert shapes[1]["x0"] == 1
    assert shapes[1]["x1"] == 3
    assert shapes[1]["y0"] == 20
    assert shapes[1]["y1"] == 45

    delete_traces = [
        trace for trace in updated["data"] if trace.get("name") == BBOX_DELETE_TRACE_NAME
    ]
    assert len(delete_traces) == 1
    assert delete_traces[0]["customdata"] == [0]
    assert delete_traces[0]["text"] == ["\u00d7"]
    assert delete_traces[0]["hovertemplate"] == "Delete box<extra></extra>"
    assert updated["layout"]["annotations"][0]["text"] == "Box 1: Fin whale"

    edit_traces = [
        trace for trace in updated["data"] if trace.get("name") == BBOX_EDIT_TRACE_NAME
    ]
    assert len(edit_traces) == 1
    assert edit_traces[0]["customdata"] == [0]
    assert edit_traces[0]["text"] == ["\u270e"]
    assert "Edit box" in edit_traces[0]["hovertemplate"][0]
    assert edit_traces[0]["x"][0] > updated["layout"]["annotations"][0]["x"]
    assert edit_traces[0]["marker"]["size"] == 22


def test_apply_modal_boxes_to_figure_clears_stale_bbox_overlays():
    with_box = apply_modal_boxes_to_figure(
        {
            "data": [{"type": "heatmap", "z": [[1, 2], [3, 4]]}],
            "layout": {
                "xaxis": {"range": [0, 10]},
                "yaxis": {"range": [0, 100]},
                "shapes": [
                    {
                        "type": "line",
                        "name": "playback-marker",
                        "x0": 7,
                        "x1": 7,
                        "y0": 0,
                        "y1": 1,
                        "yref": "paper",
                    }
                ],
            },
        },
        [_box(label="Bio > Marine mammal > Fin whale", extent=_extent(1, 3, 20, 45))],
    )

    cleared = apply_modal_boxes_to_figure(deepcopy(with_box), [], revision_bump=123)

    assert [shape.get("name") for shape in cleared["layout"]["shapes"]] == ["playback-marker"]
    assert cleared["layout"]["annotations"] == []
    trace_names = [trace.get("name") for trace in cleared["data"]]
    assert BBOX_DELETE_TRACE_NAME not in trace_names
    assert BBOX_EDIT_TRACE_NAME not in trace_names
    assert cleared["layout"]["editrevision"].startswith("bbox-")
    assert cleared["layout"]["editrevision"] != with_box["layout"]["editrevision"]


def test_apply_modal_boxes_to_figure_displays_bbox_tag():
    updated = apply_modal_boxes_to_figure(
        {
            "data": [{"type": "heatmap", "z": [[1]]}],
            "layout": {"xaxis": {"range": [0, 10]}, "yaxis": {"range": [0, 100]}},
        },
        [_box(label="Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale", tag="20Hz")],
    )

    assert updated["layout"]["annotations"][0]["text"] == "Box 1: Fin whale \u00b7 20Hz"
    edit_trace = next(trace for trace in updated["data"] if trace.get("name") == BBOX_EDIT_TRACE_NAME)
    assert "Tag: 20Hz" in edit_trace["hovertemplate"][0]


def test_extract_box_annotations_from_boxes_preserves_tag():
    assert extract_box_annotations_from_boxes([_box(label="Bio > Fin whale", tag="30Hz")]) == [
        {
            "label": "Bio > Fin whale",
            "annotation_extent": _extent(),
            "tag": "30Hz",
        }
    ]


def test_removing_final_bbox_returns_prediction_to_unverified():
    predicted = "Bio > Fin whale"
    other = "Bio > Blue whale"

    labels = unverify_predictions_without_boxes(
        active_labels=[predicted, other],
        predicted_labels=[predicted, other],
        existing_box_annotations=[
            {"label": predicted, "annotation_extent": _extent()},
            {"label": other, "annotation_extent": _extent(4, 6, 30, 50)},
        ],
        next_box_annotations=[
            {"label": other, "annotation_extent": _extent(4, 6, 30, 50)},
        ],
    )

    assert labels == [other]


def test_removing_one_of_multiple_bboxes_keeps_prediction_verified():
    predicted = "Bio > Fin whale"

    labels = unverify_predictions_without_boxes(
        active_labels=[predicted],
        predicted_labels=[predicted],
        existing_box_annotations=[
            {"label": predicted, "annotation_extent": _extent()},
            {"label": predicted, "annotation_extent": _extent(4, 6, 30, 50)},
        ],
        next_box_annotations=[
            {"label": predicted, "annotation_extent": _extent(4, 6, 30, 50)},
        ],
    )

    assert labels == [predicted]


def test_bbox_species_edit_rejects_original_label_in_verify_mode():
    old_label = "Bio > Fin whale"
    new_label = "Bio > Blue whale"
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [old_label]},
        "annotations": {
            "labels": [old_label],
            "verified": True,
            "has_manual_review": True,
        },
    }
    boxes = [_box(label=new_label, tag="20Hz")]

    updated = update_modal_item_for_box_edit(
        item,
        mode="verify",
        thresholds={"__global__": 0.5},
        boxes=boxes,
        old_label=old_label,
        new_label=new_label,
        profile_name="QA Tester",
        get_modal_label_sets=get_modal_label_sets,
        get_item_rejected_labels=get_item_rejected_labels,
        extract_label_extent_map_from_boxes=extract_label_extent_map_from_boxes,
        extract_box_annotations_from_boxes=extract_box_annotations_from_boxes,
        ordered_unique_labels=ordered_unique_labels,
    )

    annotations = updated["annotations"]
    assert annotations["labels"] == [new_label]
    assert annotations["rejected_labels"] == [old_label]
    assert annotations["pending_save"] is True
    assert annotations["needs_reverify"] is True
    assert annotations["box_annotations"] == [
        {
            "label": new_label,
            "annotation_extent": _extent(),
            "tag": "20Hz",
        }
    ]
