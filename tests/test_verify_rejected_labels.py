import json

from app.callbacks.label.editor_modal_callbacks import (
    _resolve_grid_editor_item_id,
    _resolve_selected_labels,
)
from app.callbacks.verify.badge_helpers import (
    box_annotations_after_label_action,
    review_states_match,
)
from app.components.spectrogram_card import create_spectrogram_card
from app.callbacks.modal.actions_helpers import build_modal_item_actions
from app.services.modal_state import persist_modal_item_before_exit
from app.services.verification import get_item_rejected_labels, get_modal_label_sets
from app.services.verification import filter_predictions
from app.services.verify_pagination import _filter_predictions as filter_pagination_predictions
from app.services.verify_modal_cache import (
    _prediction_filter_entries,
    get_verify_modal_baseline_item,
    get_verify_modal_item,
    register_verify_modal_items,
    update_verify_modal_item,
)
from app.services.verify_pagination import _build_verification_payload
from app.utils.unified_format_converter import convert_unified_v2_to_internal


FIN_WHALE = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
BLUE_WHALE = "Biophony > Marine mammal > Cetacean > Baleen whale > Blue whale"
HUMAN_LABEL = "Biophony > Marine mammal > Cetacean > Baleen whale > Humpback whale"


def _extent(start=1.0, end=2.0, low=20.0, high=40.0):
    return {
        "type": "time_freq_box",
        "time_start_sec": start,
        "time_end_sec": end,
        "freq_min_hz": low,
        "freq_max_hz": high,
    }


def _component_tree_contains_class(component, class_name):
    if component is None:
        return False
    if isinstance(component, (list, tuple)):
        return any(_component_tree_contains_class(child, class_name) for child in component)

    component_class = getattr(component, "className", None)
    if isinstance(component_class, str) and class_name in component_class.split():
        return True

    children = getattr(component, "children", None)
    return _component_tree_contains_class(children, class_name)


def _component_tree_contains_text(component, expected):
    if component is None:
        return False
    if isinstance(component, str):
        return expected in component
    if isinstance(component, (list, tuple)):
        return any(_component_tree_contains_text(child, expected) for child in component)

    children = getattr(component, "children", None)
    return _component_tree_contains_text(children, expected)


def _decisions_include(decisions, expected):
    return any(all(decision.get(key) == value for key, value in expected.items()) for decision in decisions)


def test_label_delete_prunes_matching_box_annotations_without_modal_store():
    annotations = {
        "box_annotations": [
            {"label": BLUE_WHALE, "annotation_extent": _extent(3, 4, 35, 60)},
            {"label": HUMAN_LABEL, "annotation_extent": _extent(5, 6, 100, 180)},
        ]
    }

    boxes = box_annotations_after_label_action(
        action="delete",
        label=BLUE_WHALE,
        annotations_obj=annotations,
        next_bbox_store=None,
    )

    assert boxes == [{"label": HUMAN_LABEL, "annotation_extent": _extent(5, 6, 100, 180)}]


def test_label_delete_uses_filtered_modal_store_box_annotations():
    next_bbox_store = {
        "item_id": "clip-1",
        "boxes": [
            {"label": HUMAN_LABEL, "annotation_extent": _extent(5, 6, 100, 180)},
        ],
    }

    boxes = box_annotations_after_label_action(
        action="delete",
        label=BLUE_WHALE,
        annotations_obj={
            "box_annotations": [
                {"label": BLUE_WHALE, "annotation_extent": _extent(3, 4, 35, 60)},
            ]
        },
        next_bbox_store=next_bbox_store,
    )

    assert boxes == [{"label": HUMAN_LABEL, "annotation_extent": _extent(5, 6, 100, 180)}]


def test_filter_predictions_preserves_hierarchy_when_confidence_key_is_leaf():
    predictions = {
        "labels": [FIN_WHALE],
        "confidence": {"Fin whale": 0.93},
    }

    assert filter_predictions(predictions, {"__global__": 0.5}) == [FIN_WHALE]
    assert filter_pagination_predictions(predictions, {"__global__": 0.5}) == [FIN_WHALE]
    assert _prediction_filter_entries(predictions) == ([FIN_WHALE], [(FIN_WHALE, 0.93)])


def test_unified_conversion_preserves_rejected_label_decisions():
    data = convert_unified_v2_to_internal(
        {
            "schema_version": "2.1",
            "model": {"model_id": "test-model"},
            "items": [
                {
                    "item_id": "clip-1",
                    "model_outputs": [{"class_hierarchy": FIN_WHALE, "score": 0.95}],
                    "verifications": [
                        {
                            "verified_at": "2026-05-12T00:00:00Z",
                            "verified_by": "tester",
                            "verification_status": "verified",
                            "label_decisions": [
                                {"label": FIN_WHALE, "decision": "rejected"},
                            ],
                        }
                    ],
                }
            ],
        }
    )

    annotations = data["items"][0]["annotations"]
    assert annotations["verified"] is True
    assert annotations["labels"] == []
    assert annotations["rejected_labels"] == [FIN_WHALE]


def test_verify_card_reads_rejected_labels_from_verifications_when_annotations_are_sparse():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE]},
        "annotations": {"labels": [], "verified": True},
        "verifications": [
            {
                "label_decisions": [
                    {"label": FIN_WHALE, "decision": "rejected"},
                ],
            }
        ],
    }

    card = create_spectrogram_card(item, image_src="/assets/example.png", mode="verify")

    assert _component_tree_contains_class(card, "verify-label-badge--model-rejected")
    assert not _component_tree_contains_class(card, "verify-label-badge--model-accepted")


def test_modal_label_sets_exclude_rejected_labels_from_latest_verification():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE, BLUE_WHALE]},
        "annotations": {},
        "verifications": [
            {
                "label_decisions": [
                    {"label": FIN_WHALE, "decision": "rejected"},
                    {"label": BLUE_WHALE, "decision": "accepted"},
                ],
            }
        ],
    }

    predicted, verified, active = get_modal_label_sets(item, "verify", {"__global__": 0.5})

    assert predicted == [FIN_WHALE, BLUE_WHALE]
    assert verified == [BLUE_WHALE]
    assert active == [BLUE_WHALE]


def test_label_editor_does_not_reselect_rejected_prediction():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE]},
        "annotations": {"labels": [], "verified": True},
        "verifications": [
            {
                "label_decisions": [
                    {"label": FIN_WHALE, "decision": "rejected"},
                ],
            }
        ],
    }

    selected, _ = _resolve_selected_labels(
        item,
        "verify",
        {"__global__": 0.5},
        lambda predictions, _thresholds: predictions.get("labels", []),
    )

    assert selected == []


def test_grid_editor_uses_triggered_edit_button_despite_stale_modal_click_store():
    chosen, updated_store = _resolve_grid_editor_item_id(
        [1],
        {"clip-1": 1},
        [{"type": "edit-btn", "item_id": "clip-1"}],
        {"type": "edit-btn", "item_id": "clip-1"},
    )

    assert chosen == "clip-1"
    assert updated_store == {"clip-1": 1}


def test_modal_label_sets_respect_explicit_empty_labels_after_delete():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE]},
        "annotations": {
            "labels": [],
            "rejected_labels": [FIN_WHALE],
            "has_manual_review": True,
            "pending_save": True,
        },
        "verifications": [
            {
                "label_decisions": [
                    {"label": HUMAN_LABEL, "decision": "added"},
                    {"label": FIN_WHALE, "decision": "rejected"},
                ],
            }
        ],
    }

    predicted, verified, active = get_modal_label_sets(item, "verify", {"__global__": 0.5})

    assert predicted == [FIN_WHALE]
    assert verified == []
    assert active == []


def test_verify_payload_accepts_previously_rejected_prediction_when_rechecked():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE]},
        "annotations": {
            "labels": [FIN_WHALE],
            "rejected_labels": [FIN_WHALE],
            "has_manual_review": True,
        },
    }

    verification, labels, rejected, _ = _build_verification_payload(
        item,
        {"__global__": 0.5},
        "tester",
    )

    assert labels == [FIN_WHALE]
    assert rejected == []
    assert _decisions_include(
        verification["label_decisions"],
        {"label": FIN_WHALE, "decision": "accepted"},
    )
    assert not _decisions_include(
        verification["label_decisions"],
        {"label": FIN_WHALE, "decision": "rejected"},
    )


def test_verify_payload_rejects_accepted_prediction_when_unchecked():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE]},
        "annotations": {
            "labels": [],
            "rejected_labels": [],
            "has_manual_review": True,
        },
    }

    verification, labels, rejected, _ = _build_verification_payload(
        item,
        {"__global__": 0.5},
        "tester",
    )

    assert labels == []
    assert rejected == [FIN_WHALE]
    assert _decisions_include(
        verification["label_decisions"],
        {"label": FIN_WHALE, "decision": "rejected"},
    )


def test_verify_card_does_not_restore_deleted_human_label_from_latest_verification():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE]},
        "annotations": {
            "labels": [],
            "rejected_labels": [FIN_WHALE],
            "has_manual_review": True,
            "pending_save": True,
        },
        "verifications": [
            {
                "label_decisions": [
                    {"label": HUMAN_LABEL, "decision": "added"},
                    {"label": FIN_WHALE, "decision": "rejected"},
                ],
            }
        ],
    }

    card = create_spectrogram_card(item, image_src="/assets/example.png", mode="verify")

    assert _component_tree_contains_class(card, "verify-label-badge--model-rejected")
    assert not _component_tree_contains_text(card, HUMAN_LABEL)


def test_rejected_labels_respect_explicit_empty_review_state():
    item = {
        "item_id": "clip-1",
        "annotations": {
            "labels": [FIN_WHALE],
            "rejected_labels": [],
            "has_manual_review": True,
            "pending_save": True,
        },
        "verifications": [
            {
                "label_decisions": [
                    {"label": FIN_WHALE, "decision": "rejected"},
                ],
            }
        ],
    }

    assert get_item_rejected_labels(item) == []


def test_modal_actions_render_sparse_verification_rejection_as_rejected():
    item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE, BLUE_WHALE]},
        "annotations": {},
        "verifications": [
            {
                "label_decisions": [
                    {"label": FIN_WHALE, "decision": "rejected"},
                    {"label": BLUE_WHALE, "decision": "accepted"},
                ],
            }
        ],
    }

    actions = build_modal_item_actions(item, "verify", {"__global__": 0.5})

    assert _component_tree_contains_class(actions, "verify-label-badge--model-rejected")
    assert _component_tree_contains_class(actions, "verify-label-badge--model-accepted")


def test_verify_modal_cache_can_be_updated_after_card_reject():
    initial_item = {
        "item_id": "clip-1",
        "predictions": {"labels": [FIN_WHALE, BLUE_WHALE]},
        "annotations": {},
    }
    cache_key = register_verify_modal_items(
        {
            "load_timestamp": "2026-05-12T00:00:00Z",
            "summary": {"predictions_file": "/tmp/predictions.json"},
            "items": [initial_item],
        }
    )
    updated_item = {
        **initial_item,
        "annotations": {
            "labels": [BLUE_WHALE],
            "rejected_labels": [FIN_WHALE],
            "pending_save": True,
            "has_manual_review": True,
        },
    }

    assert update_verify_modal_item(cache_key, updated_item) == 0

    cached = get_verify_modal_item(cache_key, "clip-1")
    assert cached["annotations"]["labels"] == [BLUE_WHALE]
    assert cached["annotations"]["rejected_labels"] == [FIN_WHALE]

    baseline = get_verify_modal_baseline_item(cache_key, "clip-1")
    assert baseline == initial_item


def test_verify_modal_cache_advances_baseline_after_save():
    initial_item = {
        "item_id": "clip-saved",
        "annotations": {"labels": [FIN_WHALE], "verified": True},
    }
    cache_key = register_verify_modal_items(
        {
            "load_timestamp": "2026-05-12T00:00:01Z",
            "summary": {"predictions_file": "/tmp/predictions.json"},
            "items": [initial_item],
        }
    )
    saved_item = {
        **initial_item,
        "annotations": {
            "labels": [BLUE_WHALE],
            "verified": True,
            "pending_save": False,
        },
    }

    update_verify_modal_item(cache_key, saved_item)

    assert get_verify_modal_baseline_item(cache_key, "clip-saved") == saved_item


def test_review_state_round_trip_ignores_transient_audit_fields():
    baseline = {
        "annotations": {
            "labels": [FIN_WHALE, BLUE_WHALE],
            "verified": True,
            "annotated_at": "2026-05-12T00:00:00Z",
            "annotated_by": "first reviewer",
        }
    }
    reverted = {
        "annotations": {
            "labels": [BLUE_WHALE, FIN_WHALE],
            "verified": True,
            "has_manual_review": True,
            "pending_save": True,
            "needs_reverify": True,
            "annotated_at": "2026-05-12T00:01:00Z",
            "annotated_by": "second reviewer",
        }
    }

    assert review_states_match(reverted, baseline)


def test_review_state_distinguishes_first_review_from_unverified_prediction():
    baseline = {
        "annotations": {
            "labels": [FIN_WHALE],
            "verified": False,
        }
    }
    reviewed = {
        "annotations": {
            "labels": [FIN_WHALE],
            "verified": False,
            "has_manual_review": True,
            "pending_save": True,
        }
    }

    assert not review_states_match(reviewed, baseline)


def test_persist_modal_item_before_exit_does_not_reaccept_sparse_rejection(tmp_path):
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(json.dumps({"items": [{"item_id": "clip-1"}]}))
    item = {
        "item_id": "clip-1",
        "predictions": {
            "model_outputs": [
                {"class_hierarchy": FIN_WHALE, "score": 0.95, "annotation_extent": _extent()},
                {"class_hierarchy": BLUE_WHALE, "score": 0.9, "annotation_extent": _extent(3, 4, 35, 60)},
            ]
        },
        "annotations": {},
        "verifications": [
            {
                "label_decisions": [
                    {"label": FIN_WHALE, "decision": "rejected"},
                    {"label": BLUE_WHALE, "decision": "accepted"},
                ],
            }
        ],
        "metadata": {"predictions_path": str(predictions_path)},
    }
    bbox_store = {
        "item_id": "clip-1",
        "boxes": [
            {"label": BLUE_WHALE, "annotation_extent": _extent(3, 4, 35, 60)},
            {"label": HUMAN_LABEL, "annotation_extent": _extent(5, 6, 100, 180)},
        ],
    }

    _, updated, _ = persist_modal_item_before_exit(
        mode="verify",
        item_id="clip-1",
        label_data=None,
        verify_data={"items": [item], "summary": {"predictions_file": str(predictions_path)}},
        explore_data=None,
        thresholds={"__global__": 0.5},
        profile={"name": "Tester", "email": "tester@example.com"},
        bbox_store=bbox_store,
        label_output_path=None,
        cfg={},
        require_complete_profile=lambda profile, callback_name: None,
        profile_actor=lambda profile: profile["name"],
    )

    annotations = updated["items"][0]["annotations"]
    assert annotations["labels"] == [BLUE_WHALE, HUMAN_LABEL]
    assert annotations["rejected_labels"] == [FIN_WHALE]

    saved = json.loads(predictions_path.read_text())
    decisions = saved["items"][0]["verifications"][0]["label_decisions"]
    assert _decisions_include(decisions, {"label": FIN_WHALE, "decision": "rejected", "threshold_used": 0.5})
    assert _decisions_include(
        decisions,
        {
            "label": BLUE_WHALE,
            "decision": "accepted",
            "threshold_used": 0.5,
            "annotation_extent": _extent(3, 4, 35, 60),
        },
    )
    assert _decisions_include(
        decisions,
        {
            "label": HUMAN_LABEL,
            "decision": "added",
            "threshold_used": 0.5,
            "annotation_extent": _extent(5, 6, 100, 180),
        },
    )
