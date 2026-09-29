from app.services.label_attributes import (
    FIN_WHALE_LABEL,
    KILLER_WHALE_LABEL,
    human_label_attributes,
    label_attribute_options,
    model_label_attributes,
    normalize_label_attributes,
    prune_label_attributes,
    replace_human_call_type_attributes,
    supports_call_type_attributes,
)
from app.services.bbox_tags import get_bbox_tag_options
from app.utils.unified_format_converter import convert_unified_v2_to_internal


BIGGS = f"{KILLER_WHALE_LABEL} > Bigg's killer whale"
UNKNOWN_CLICK = "Biophony > Unknown biophony > Click train"


def test_species_specific_call_type_options_do_not_apply_to_unknown_click_labels():
    assert {entry["value"] for entry in label_attribute_options(KILLER_WHALE_LABEL)} == {
        "echolocation_click",
        "whistle",
        "pulsed_call",
    }
    assert supports_call_type_attributes(BIGGS)
    assert label_attribute_options(UNKNOWN_CLICK) == []


def test_fin_bbox_vocabulary_remains_only_frequency_tags():
    assert get_bbox_tag_options({}) == [
        {"label": "20 Hz", "value": "20Hz"},
        {"label": "30 Hz", "value": "30Hz"},
        {"label": "40 Hz", "value": "40Hz"},
    ]


def test_unknown_or_unassociated_attributes_are_rejected():
    assert normalize_label_attributes(
        [{"taxonomy_label": UNKNOWN_CLICK, "value": "echolocation_click"}],
        default_source="model",
    ) == []
    assert normalize_label_attributes(
        [{"taxonomy_label": KILLER_WHALE_LABEL, "value": "20Hz"}],
        default_source="model",
    ) == []


def test_human_and_model_attributes_remain_label_linked_and_independent():
    human = replace_human_call_type_attributes(
        [],
        KILLER_WHALE_LABEL,
        ["whistle"],
        active_labels=[KILLER_WHALE_LABEL],
        annotated_by="Reviewer",
        annotated_at="2026-08-11T12:00:00Z",
    )
    item = {
        "predictions": {
            "label_attributes": [
                {
                    "taxonomy_label": KILLER_WHALE_LABEL,
                    "value": "pulsed_call",
                    "source": "model",
                    "score": 0.82,
                }
            ]
        },
        "annotations": {"label_attributes": human},
    }
    assert model_label_attributes(item, KILLER_WHALE_LABEL)[0]["value"] == "pulsed_call"
    assert human_label_attributes(item, KILLER_WHALE_LABEL)[0]["value"] == "whistle"


def test_attributes_are_pruned_when_their_species_label_is_removed():
    attributes = replace_human_call_type_attributes(
        [],
        FIN_WHALE_LABEL,
        ["20Hz", "40Hz"],
        active_labels=[FIN_WHALE_LABEL],
    )
    assert len(attributes) == 2
    assert prune_label_attributes(attributes, [], default_source="human") == []


def test_converter_keeps_model_and_human_label_attributes_separate():
    converted = convert_unified_v2_to_internal(
        {
            "schema_version": "2.1",
            "model": {"model_id": "orca-audit"},
            "items": [
                {
                    "item_id": "clip-1",
                    "model_outputs": [
                        {"class_hierarchy": KILLER_WHALE_LABEL, "score": 0.7}
                    ],
                    "label_attributes": [
                        {
                            "taxonomy_label": KILLER_WHALE_LABEL,
                            "value": "echolocation_click",
                            "source": "model",
                        }
                    ],
                    "verifications": [
                        {
                            "verified_by": "Reviewer",
                            "verified_at": "2026-08-11T12:00:00Z",
                            "label_decisions": [
                                {"label": KILLER_WHALE_LABEL, "decision": "accepted"}
                            ],
                            "label_attributes": [
                                {
                                    "taxonomy_label": KILLER_WHALE_LABEL,
                                    "value": "whistle",
                                    "source": "human",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    item = converted["items"][0]
    assert item["predictions"]["label_attributes"][0]["value"] == "echolocation_click"
    assert item["annotations"]["label_attributes"][0]["value"] == "whistle"
