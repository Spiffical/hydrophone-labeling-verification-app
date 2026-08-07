from app.services.verify_filter_tree import (
    build_verify_filter_paths,
    build_verify_leaf_paths,
    extract_verify_leaf_classes,
    expand_verify_filter_selection,
    predicted_labels_match_filter,
    toggle_verify_filter_selection,
)
from app.services.verify_modal_cache import (
    get_filtered_verify_items_page,
    get_verify_modal_data,
    get_verify_filter_leaf_classes,
    has_pending_verify_modal_changes,
    register_verify_modal_items,
    update_verify_modal_item,
)
from app.callbacks.data.render_callbacks import (
    _collect_verify_future_page_items,
    _compute_prefetch_pages_ahead,
    _modal_prefetch_enabled,
    _prefetch_enabled,
    _verify_page_info,
)
from app.callbacks.verify.class_filter_callbacks import preserve_dynamic_all_selection
from app.utils.unified_format_converter import convert_unified_v2_to_internal


def test_verify_page_info_distinguishes_page_range_from_filter_matches():
    assert _verify_page_info(0, 25, 5737) == (
        "Showing 1-25 of 5,737 matches | Page 1 of 230"
    )
    assert _verify_page_info(1, 25, 5737) == (
        "Showing 26-50 of 5,737 matches | Page 2 of 230"
    )
    assert _verify_page_info(0, 25, 49, index_available=False) == (
        "Showing available recordings while the index is built"
    )


def test_modal_prefetch_defaults_on_for_existing_mat_spectrograms():
    cfg = {"spectrogram_render": {"source": "existing"}}

    assert _prefetch_enabled(cfg) is False
    assert _modal_prefetch_enabled(cfg) is True
    assert _modal_prefetch_enabled({"cache": {"modal_prefetch_enabled": False}}) is False


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


def test_dynamic_all_selection_includes_classes_discovered_after_preview():
    preview_paths = build_verify_filter_paths(
        [
            "Anthrophony > Vessel > Cargo",
            "Biophony > Whale",
        ]
    )
    complete_paths = build_verify_filter_paths(
        [
            "Anthrophony > Vessel > Cargo",
            "Biophony > Whale",
            "Geophony > Earthquake",
        ]
    )

    assert preserve_dynamic_all_selection(
        complete_paths,
        build_verify_leaf_paths(preview_paths),
        preview_paths,
        build_verify_leaf_paths=build_verify_leaf_paths,
        expand_verify_filter_selection=expand_verify_filter_selection,
    ) is None


def test_dynamic_class_subset_remains_explicit_after_dataset_change():
    preview_paths = build_verify_filter_paths(
        [
            "Anthrophony > Vessel > Cargo",
            "Biophony > Whale",
        ]
    )
    complete_paths = build_verify_filter_paths(
        [
            "Anthrophony > Vessel > Cargo",
            "Biophony > Whale",
            "Geophony > Earthquake",
        ]
    )

    assert preserve_dynamic_all_selection(
        complete_paths,
        ["Biophony > Whale"],
        preview_paths,
        build_verify_leaf_paths=build_verify_leaf_paths,
        expand_verify_filter_selection=expand_verify_filter_selection,
    ) == ["Biophony > Whale"]


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


def test_extract_verify_leaf_classes_uses_only_canonical_model_outputs():
    items = [
        {
            "predictions": {
                "model_outputs": [
                    {"class_hierarchy": "Other > fin_whale", "score": 0.8},
                    {
                        "class_hierarchy": "Geophony > Weather > Precipitation > Rain",
                        "score": 0.4,
                    },
                    {"class_hierarchy": "Not a taxonomy class", "score": 0.2},
                ],
                "confidence": {"Other > bogus_confidence_class": 0.99},
                "labels": ["Other > bogus_display_label"],
            }
        }
    ]

    assert extract_verify_leaf_classes(items) == [
        "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
        "Geophony > Weather > Precipitation > Rain",
    ]


def test_unified_converter_canonicalizes_model_outputs_without_mutating_source():
    predictions_json = {
        "schema_version": "2.1",
        "model": {"model_id": "test-model"},
        "items": [
            {
                "item_id": "clip-1",
                "model_outputs": [
                    {"class_hierarchy": "Other > fin_whale", "score": 0.8},
                    {"class_hierarchy": "Other > ship", "score": 0.7},
                    {"class_hierarchy": "Other > sonar", "score": 0.6},
                    {"class_hierarchy": "Other > unknown_biological", "score": 0.5},
                    {"class_hierarchy": "Other > other_anthropogenic", "score": 0.4},
                    {"class_hierarchy": "Other > invalid_class", "score": 0.3},
                ],
            }
        ],
    }

    converted = convert_unified_v2_to_internal(predictions_json)

    assert [
        output["class_hierarchy"]
        for output in converted["items"][0]["predictions"]["model_outputs"]
    ] == [
        "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
        "Anthropophony > Vessel",
        "Anthropophony > Sonar",
        "Biophony > Unknown biophony",
        "Anthropophony > Unknown anthropophony",
    ]
    assert (
        predictions_json["items"][0]["model_outputs"][0]["class_hierarchy"]
        == "Other > fin_whale"
    )


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


def test_audio_generated_pages_prefetch_filtered_future_items():
    label = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
    data = {
        "load_timestamp": "prefetch-filter-test",
        "summary": {"total_items": 5},
        "items": [
            {
                "item_id": f"clip-{index}",
                "audio_path": f"/tmp/clip-{index}.wav",
                "predictions": {"model_outputs": [{"class_hierarchy": label, "score": 0.8}]},
                "annotations": {},
            }
            for index in range(5)
        ],
    }
    cache_key = register_verify_modal_items(data)

    future_items = _collect_verify_future_page_items(
        cache_key,
        {"__global__": 0.5},
        None,
        "all",
        current_page=0,
        total_pages=5,
        items_per_page=1,
        pages_ahead=2,
    )

    assert [item["item_id"] for item in future_items] == ["clip-1", "clip-2"]
    assert _prefetch_enabled({"spectrogram_render": {"source": "audio_generated"}}) is True
    assert _prefetch_enabled({"spectrogram_render": {"source": "existing"}}) is False
    assert _prefetch_enabled(
        {
            "cache": {"prefetch_enabled": True},
            "spectrogram_render": {"source": "existing"},
        }
    ) is True
    assert _prefetch_enabled({"cache": {"prefetch_enabled": False}}) is False
    assert _compute_prefetch_pages_ahead({"cache": {"max_size": 75}}, 25) == 2
    assert _compute_prefetch_pages_ahead(
        {
            "cache": {"max_size": 75},
            "spectrogram_render": {"source": "audio_generated"},
        },
        25,
    ) == 1
    assert has_pending_verify_modal_changes(cache_key) is False

    cached_data = get_verify_modal_data(cache_key)
    assert cached_data["load_timestamp"] == "prefetch-filter-test"
    assert [item["item_id"] for item in cached_data["items"]] == [
        "clip-0",
        "clip-1",
        "clip-2",
        "clip-3",
        "clip-4",
    ]

    updated_item = cached_data["items"][0]
    updated_item["annotations"] = {"pending_save": True}
    update_verify_modal_item(cache_key, updated_item)
    assert has_pending_verify_modal_changes(cache_key) is True


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
