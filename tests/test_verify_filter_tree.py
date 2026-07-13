from app.services.verify_filter_tree import (
    build_verify_filter_paths,
    build_verify_leaf_paths,
    expand_verify_filter_selection,
    predicted_labels_match_filter,
    toggle_verify_filter_selection,
)
from app.services.verify_modal_cache import (
    get_filtered_verify_items_page,
    get_verify_filter_leaf_classes,
    register_verify_modal_items,
)


def test_build_verify_leaf_paths_returns_only_leaf_nodes():
    paths = build_verify_filter_paths(
        [
            "Anthrophony > Vessel > Cargo",
            "Anthrophony > Vessel > Tug",
            "Biophony > Whale",
        ]
    )

    assert build_verify_leaf_paths(paths) == [
        "Anthrophony > Vessel > Cargo",
        "Anthrophony > Vessel > Tug",
        "Biophony > Whale",
    ]


def test_expand_verify_filter_selection_expands_parent_to_descendant_leaves():
    paths = build_verify_filter_paths(
        [
            "Anthrophony > Vessel > Cargo",
            "Anthrophony > Vessel > Tug",
            "Biophony > Whale",
        ]
    )

    assert expand_verify_filter_selection(paths, ["Anthrophony > Vessel"]) == [
        "Anthrophony > Vessel > Cargo",
        "Anthrophony > Vessel > Tug",
    ]


def test_toggle_verify_filter_selection_cascades_to_descendants():
    paths = build_verify_filter_paths(
        [
            "Anthrophony > Vessel > Cargo",
            "Anthrophony > Vessel > Tug",
            "Biophony > Whale",
        ]
    )

    selected = toggle_verify_filter_selection(paths, [], "Anthrophony", True)
    assert selected == [
        "Anthrophony > Vessel > Cargo",
        "Anthrophony > Vessel > Tug",
    ]

    selected = toggle_verify_filter_selection(paths, selected, "Anthrophony > Vessel > Cargo", False)
    assert selected == ["Anthrophony > Vessel > Tug"]

    selected = toggle_verify_filter_selection(paths, selected, "Anthrophony > Vessel", True)
    assert selected == [
        "Anthrophony > Vessel > Cargo",
        "Anthrophony > Vessel > Tug",
    ]

    selected = toggle_verify_filter_selection(paths, selected, "Anthrophony", False)
    assert selected == []


def test_predicted_labels_match_filter_works_with_leaf_only_selection():
    selected = ["Anthrophony > Vessel > Tug"]

    assert predicted_labels_match_filter(["Anthrophony > Vessel > Tug"], selected) is True
    assert predicted_labels_match_filter(["Anthrophony > Vessel > Cargo"], selected) is False


def test_verify_modal_cache_filters_thresholds_classes_and_pages():
    fin = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
    blue = "Biophony > Marine mammal > Cetacean > Baleen whale > Blue whale"
    data = {
        "load_timestamp": "cache-filter-test",
        "summary": {"active_date": "2026-05-15", "active_hydrophone": "HF1", "total_items": 3},
        "items": [
            {
                "item_id": "clip-fin",
                "audio_path": "/tmp/fin.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": fin, "score": 0.8}]},
                "annotations": {},
            },
            {
                "item_id": "clip-blue",
                "audio_path": "/tmp/blue.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": blue, "score": 0.4}]},
                "annotations": {},
            },
            {
                "item_id": "clip-reviewed",
                "audio_path": "/tmp/reviewed.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": blue, "score": 0.2}]},
                "annotations": {"verified": True},
            },
        ],
    }

    cache_key = register_verify_modal_items(data)

    assert get_verify_filter_leaf_classes(cache_key) == [blue, fin]

    page = get_filtered_verify_items_page(cache_key, {"__global__": 0.5}, None, 0, 10)
    assert page["visible_item_ids"] == ["clip-fin", "clip-reviewed"]
    assert [item["predictions"]["labels"] for item in page["items"]] == [[fin], []]

    fin_page = get_filtered_verify_items_page(cache_key, {"__global__": 0.5}, [fin], 0, 10)
    assert fin_page["visible_item_ids"] == ["clip-fin"]

    low_threshold_page_two = get_filtered_verify_items_page(cache_key, {"__global__": 0.3}, None, 1, 1)
    assert low_threshold_page_two["total_items"] == 3
    assert low_threshold_page_two["page_index"] == 1
    assert [item["item_id"] for item in low_threshold_page_two["items"]] == ["clip-blue"]


def test_verify_modal_cache_filters_by_verification_status():
    fin = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
    blue = "Biophony > Marine mammal > Cetacean > Baleen whale > Blue whale"
    data = {
        "load_timestamp": "cache-status-filter-test",
        "summary": {"active_date": "2026-05-15", "active_hydrophone": "HF1", "total_items": 5},
        "items": [
            {
                "item_id": "clip-unverified",
                "audio_path": "/tmp/unverified.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": fin, "score": 0.8}]},
                "annotations": {},
            },
            {
                "item_id": "clip-accepted",
                "audio_path": "/tmp/accepted.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": fin, "score": 0.8}]},
                "annotations": {"labels": [fin], "has_manual_review": True},
            },
            {
                "item_id": "clip-rejected",
                "audio_path": "/tmp/rejected.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": fin, "score": 0.8}]},
                "annotations": {"rejected_labels": [fin], "has_manual_review": True},
            },
            {
                "item_id": "clip-mixed",
                "audio_path": "/tmp/mixed.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": fin, "score": 0.8}]},
                "annotations": {"labels": [blue], "rejected_labels": [fin], "has_manual_review": True},
            },
            {
                "item_id": "clip-verified-sparse",
                "audio_path": "/tmp/verified.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": fin, "score": 0.8}]},
                "annotations": {"verified": True},
            },
        ],
    }

    cache_key = register_verify_modal_items(data)

    def item_ids(status_filter):
        page = get_filtered_verify_items_page(
            cache_key,
            {"__global__": 0.5},
            None,
            0,
            25,
            status_filter,
        )
        return page["visible_item_ids"]

    assert item_ids("all") == [
        "clip-unverified",
        "clip-accepted",
        "clip-rejected",
        "clip-mixed",
        "clip-verified-sparse",
    ]
    assert item_ids("unverified") == ["clip-unverified"]
    assert item_ids("accepted_only") == ["clip-accepted", "clip-verified-sparse"]
    assert item_ids("rejected_only") == ["clip-rejected"]
    assert item_ids("mixed") == ["clip-mixed"]
    assert item_ids("contains_accepted") == ["clip-accepted", "clip-mixed", "clip-verified-sparse"]
    assert item_ids("contains_rejected") == ["clip-rejected", "clip-mixed"]
    assert item_ids("verified") == ["clip-verified-sparse"]
