from app.services.verify_filter_tree import (
    build_verify_filter_paths,
    build_verify_leaf_paths,
    expand_verify_filter_selection,
    predicted_labels_match_filter,
    toggle_verify_filter_selection,
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
