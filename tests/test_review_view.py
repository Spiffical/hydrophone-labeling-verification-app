"""The review page: which clips are in view, their order, and the progress counts."""

import pytest

from app.callbacks.modal.actions_helpers import build_modal_item_actions
from app.callbacks.verify.review_view_callbacks import next_review_view
from app.components.review_progress import create_progress_chart, create_progress_total
from app.components.spectrogram_card import create_spectrogram_card
from app.services.review_view import (
    AMBIENT_LABEL,
    MIN_SUGGESTION_SCORE,
    REVIEW_CATEGORIES,
    active_class_filter,
    build_progress,
    confidence_range,
    normalize_review_view,
    order_review_ids,
    review_category,
    thresholds_for_range,
)
from app.services.verification import filter_predictions, get_modal_label_sets
from app.services.verify_modal_cache import (
    get_filtered_verify_items_page,
    get_verify_progress,
    register_verify_modal_items,
    update_verify_modal_item,
)
from taxonomy.hierarchical_labels import HIERARCHICAL_LABELS

VESSEL = "Anthropophony > Vessel"
DATA_GAP = "Instrumentation > Malfunction > Data gap"
UNKNOWN = "Other > Unknown sound of interest"
ADCP = "Instrumentation > Other ONC equipment > ADCP"
SNAPPING = "Biophony > Unknown biophony > Snapping"
FIN_WHALE = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"

EXCLUDE_AMBIENT = {"exclude_ambient": True}


def clip(item_id, scores, **annotations):
    return {
        "item_id": item_id,
        "predictions": {
            "model_outputs": [
                {"class_hierarchy": label, "score": score} for label, score in scores.items()
            ],
        },
        "annotations": annotations,
    }


def reviewed(item_id, scores, labels):
    return clip(item_id, scores, labels=labels, verified=True)


def register(*items):
    return register_verify_modal_items(
        {"items": list(items), "summary": {"total_items": len(items)}, "load_timestamp": items[0]["item_id"]}
    )


def visible(key, lower=0.0, upper=1.0, selected=None, status="all", view=None):
    page = get_filtered_verify_items_page(
        key, thresholds_for_range(None, lower, upper), selected, 0, 50, status, view
    )
    return page["visible_item_ids"]


def test_every_category_of_the_hierarchy_is_on_the_page():
    assert set(REVIEW_CATEGORIES) == set(HIERARCHICAL_LABELS)
    assert review_category(FIN_WHALE) == "Biophony"
    assert review_category(VESSEL) == "Anthropophony"
    assert review_category("Not a category > Thing") == "Other"


def test_confidence_range_falls_back_to_the_threshold_saved_before_ranges():
    assert confidence_range({"__global__": 0.8}) == (0.8, 1.0)
    assert confidence_range(None) == (0.5, 1.0)
    assert confidence_range({"__global__": 8}) == (0.5, 1.0)
    assert confidence_range(thresholds_for_range(None, 0.28, 0.6)) == (0.28, 0.6)


def test_a_range_from_zero_does_not_suggest_a_clips_near_zero_classes():
    # Saving accepts every suggestion left unrejected, so these would all be
    # recorded as the reviewer's labels.
    thresholds = thresholds_for_range(None, 0.0, 1.0)
    scores = {AMBIENT_LABEL: 0.93, VESSEL: 0.04, DATA_GAP: 0.02, UNKNOWN: 0.01}
    predictions = clip("clip", scores)["predictions"]

    assert thresholds["__global__"] == MIN_SUGGESTION_SCORE
    assert filter_predictions(predictions, thresholds) == [AMBIENT_LABEL]

    item = clip("clip", scores)
    assert get_modal_label_sets(item, "verify", thresholds)[2] == [AMBIENT_LABEL]


def test_a_range_above_the_floor_is_the_suggestion_threshold():
    assert thresholds_for_range(None, 0.28, 1.0)["__global__"] == 0.28


def test_range_tests_a_clips_top_score_not_each_of_its_classes():
    # Nearly every clip has some class under 10%; that must not put it in a low band.
    key = register(
        clip("confident", {VESSEL: 0.7, DATA_GAP: 0.02}),
        clip("unsure", {VESSEL: 0.3, DATA_GAP: 0.02}),
        clip("quiet", {VESSEL: 0.05, DATA_GAP: 0.02}),
    )

    assert visible(key, 0.5, 1.0) == ["confident"]
    assert visible(key, 0.2, 0.5) == ["unsure"]
    assert visible(key, 0.0, 0.1) == ["quiet"]


def test_range_applies_to_reviewed_clips_too():
    # Precision within a band has to count the clips already reviewed in it.
    key = register(reviewed("low", {VESSEL: 0.2}, [VESSEL]), reviewed("high", {VESSEL: 0.8}, [VESSEL]))

    assert visible(key, 0.5, 1.0) == ["high"]


def test_excluding_ambient_ranges_over_the_other_classes():
    key = register(
        clip("ambient", {AMBIENT_LABEL: 0.95, VESSEL: 0.03}),
        clip("both", {AMBIENT_LABEL: 0.6, VESSEL: 0.35}),
    )

    assert visible(key, 0.3, 1.0) == ["ambient", "both"]
    assert visible(key, 0.3, 1.0, view=EXCLUDE_AMBIENT) == ["both"]
    assert visible(key, 0.0, 0.1, view=EXCLUDE_AMBIENT) == ["ambient"]


def test_excluding_ambient_keeps_it_among_a_shown_clips_suggestions():
    # Hidden from the card it would still be accepted or rejected on save.
    key = register(clip("both", {AMBIENT_LABEL: 0.6, VESSEL: 0.35}))
    page = get_filtered_verify_items_page(
        key, thresholds_for_range(None, 0.3, 1.0), None, 0, 50, "all", EXCLUDE_AMBIENT
    )

    assert page["items"][0]["predictions"]["labels"] == [AMBIENT_LABEL, VESSEL]


def test_selection_ranges_over_the_selected_classes_only():
    key = register(
        clip("vessel", {VESSEL: 0.3, DATA_GAP: 0.6}),
        clip("gap", {VESSEL: 0.02, DATA_GAP: 0.9}),
    )

    assert visible(key, 0.28, 1.0, ["Anthropophony"]) == ["vessel"]
    assert visible(key, 0.28, 1.0, ["Instrumentation"]) == ["vessel", "gap"]


def test_a_reviewers_label_the_model_cannot_output_is_found_at_any_range():
    key = register(
        reviewed("snapping", {AMBIENT_LABEL: 0.97, VESSEL: 0.01}, [AMBIENT_LABEL, SNAPPING]),
        clip("vessel", {VESSEL: 0.8}),
    )

    assert visible(key, 0.5, 1.0, ["Biophony"]) == ["snapping"]
    assert visible(key, 0.9, 1.0, ["Biophony > Unknown biophony"]) == ["snapping"]
    assert visible(key, 0.5, 1.0, view=EXCLUDE_AMBIENT) == ["snapping", "vessel"]


def test_a_reviewers_ambient_label_does_not_bring_a_clip_past_the_exclusion():
    key = register(reviewed("ambient", {VESSEL: 0.01}, [AMBIENT_LABEL]))

    assert visible(key, 0.5, 1.0, view=EXCLUDE_AMBIENT) == []


def test_a_class_the_model_scores_stays_under_the_range_once_reviewed():
    key = register(reviewed("vessel", {VESSEL: 0.1}, [VESSEL]))

    assert visible(key, 0.5, 1.0, ["Anthropophony"]) == []
    assert visible(key, 0.0, 1.0, ["Anthropophony"]) == ["vessel"]


def test_status_counts_cover_the_clips_in_view_before_the_status_filter():
    key = register(
        clip("one", {VESSEL: 0.8}),
        clip("two", {VESSEL: 0.9}),
        reviewed("three", {VESSEL: 0.7}, [VESSEL]),
        clip("out-of-range", {VESSEL: 0.1}),
    )
    page = get_filtered_verify_items_page(
        key, thresholds_for_range(None, 0.5, 1.0), None, 0, 50, "unverified"
    )

    assert page["visible_item_ids"] == ["one", "two"]
    assert page["status_counts"]["all"] == 3
    assert page["status_counts"]["unverified"] == 2
    assert page["status_counts"]["verified"] == 1


def test_precision_order_puts_the_highest_confidence_first_and_keeps_ties_in_order():
    key = register(
        clip("low", {VESSEL: 0.6}),
        clip("tie-a", {VESSEL: 0.8}),
        clip("high", {VESSEL: 0.9}),
        clip("tie-b", {VESSEL: 0.8}),
    )

    assert visible(key, view={"order": "precision"}) == ["high", "tie-a", "tie-b", "low"]


def test_precision_order_follows_the_classes_in_view():
    key = register(
        clip("a", {VESSEL: 0.3, DATA_GAP: 0.6}),
        clip("b", {VESSEL: 0.4, DATA_GAP: 0.2}),
    )

    assert visible(key, view={"order": "precision"}) == ["a", "b"]
    assert visible(key, selected=["Anthropophony"], view={"order": "precision"}) == ["b", "a"]


def test_unscored_clips_sort_after_scored_ones():
    view = normalize_review_view({"order": "precision"})

    assert order_review_ids(["unscored", "zero"], {"zero": 0.0}, view) == ["zero", "unscored"]


def test_shuffle_is_repeatable_and_a_new_seed_deals_a_new_order():
    ids = [f"clip-{index}" for index in range(30)]
    first = order_review_ids(ids, {}, normalize_review_view({"order": "shuffle", "seed": 1}))
    again = order_review_ids(ids, {}, normalize_review_view({"order": "shuffle", "seed": 1}))
    second = order_review_ids(ids, {}, normalize_review_view({"order": "shuffle", "seed": 2}))

    assert first == again
    assert first != ids
    assert first != second
    assert sorted(first) == sorted(ids)


def test_shuffle_keeps_the_remaining_clips_in_place_as_one_leaves():
    ids = [f"clip-{index}" for index in range(30)]
    view = normalize_review_view({"order": "shuffle", "seed": 3})
    first = order_review_ids(ids, {}, view)
    saved = first[4]
    remaining = order_review_ids([item_id for item_id in ids if item_id != saved], {}, view)

    assert remaining == [item_id for item_id in first if item_id != saved]


def test_view_defaults_filter_nothing():
    assert normalize_review_view(None) == {"exclude_ambient": False, "order": "dataset", "seed": 0}
    assert normalize_review_view({"order": "nonsense", "seed": "x"})["order"] == "dataset"


def test_shuffling_again_deals_a_new_order_and_precision_keeps_the_seed():
    view = {"exclude_ambient": True, "order": "precision", "seed": 4}
    shuffled = next_review_view(view, triggered="verify-order-shuffle", exclude_ambient=True)

    assert shuffled == {"exclude_ambient": True, "order": "shuffle", "seed": 5}
    assert next_review_view(shuffled, triggered="verify-order-shuffle", exclude_ambient=True)["seed"] == 6
    assert next_review_view(shuffled, triggered="verify-order-precision", exclude_ambient=True) == {
        "exclude_ambient": True,
        "order": "precision",
        "seed": 5,
    }
    assert next_review_view(shuffled, triggered="verify-exclude-ambient", exclude_ambient=False)["exclude_ambient"] is False


def test_an_empty_selection_means_every_class():
    assert active_class_filter(None) is None
    assert active_class_filter([]) is None
    assert active_class_filter(["Biophony"]) == ["Biophony"]


def progress_of(*items, **kwargs):
    return get_verify_progress(register(*items), **kwargs)


def bin_at(progress, start):
    return next(entry for entry in progress["bins"] if entry["start"] == start)


def category_counts(progress_bin, category):
    return next(entry for entry in progress_bin["categories"] if entry["category"] == category)


def test_each_clip_counts_once_so_the_bars_add_up_to_the_total():
    progress = progress_of(
        clip("a", {AMBIENT_LABEL: 0.5, VESSEL: 0.3, DATA_GAP: 0.2}),
        clip("b", {AMBIENT_LABEL: 0.9, VESSEL: 0.1}),
        reviewed("c", {DATA_GAP: 1.0}, [DATA_GAP]),
        exclude_ambient=True,
    )

    assert sum(entry["total"] for entry in progress["bins"]) == progress["total"] == 3
    assert progress["verified"] == 1


def test_a_perfect_score_lands_in_the_top_bin():
    progress = progress_of(clip("a", {DATA_GAP: 1.0}))

    assert bin_at(progress, 90)["total"] == 1


def test_excluding_ambient_bins_clips_by_their_next_class():
    scores = {AMBIENT_LABEL: 0.95, VESSEL: 0.03}

    assert bin_at(progress_of(clip("a", scores)), 90)["total"] == 1
    assert bin_at(progress_of(clip("a", scores), exclude_ambient=True), 0)["total"] == 1


def test_verifying_a_clip_brightens_its_bar_without_moving_it():
    key = register(clip("a", {VESSEL: 0.45, AMBIENT_LABEL: 0.5}))
    before = get_verify_progress(key, exclude_ambient=True)
    assert category_counts(bin_at(before, 40), "Anthropophony")["unverified"] == 1

    update_verify_modal_item(key, reviewed("a", {VESSEL: 0.45, AMBIENT_LABEL: 0.5}, [VESSEL]))
    after = get_verify_progress(key, exclude_ambient=True)

    assert category_counts(bin_at(after, 40), "Anthropophony") == {
        "category": "Anthropophony",
        "verified": 1,
        "unverified": 0,
    }


def test_a_reviewers_class_puts_labels_the_model_cannot_output_on_the_chart():
    progress = progress_of(reviewed("a", {VESSEL: 0.3}, [FIN_WHALE]))

    assert category_counts(bin_at(progress, 30), "Biophony")["verified"] == 1


def test_a_clip_reviewed_as_ambient_is_not_counted_as_the_models_next_guess():
    progress = progress_of(
        reviewed("a", {AMBIENT_LABEL: 0.9, VESSEL: 0.1}, [AMBIENT_LABEL]),
        exclude_ambient=True,
    )

    assert category_counts(bin_at(progress, 10), "Other")["verified"] == 1


def test_selecting_classes_counts_a_clip_under_its_label_there():
    labelled = reviewed("a", {VESSEL: 0.1}, [AMBIENT_LABEL, ADCP, SNAPPING])

    biophony = progress_of(labelled, selected_filter_paths=["Biophony"], exclude_ambient=True)
    assert biophony["total"] == 1
    assert category_counts(bin_at(biophony, 10), "Biophony")["verified"] == 1

    instrumentation = progress_of(labelled, selected_filter_paths=["Instrumentation"], exclude_ambient=True)
    assert category_counts(bin_at(instrumentation, 10), "Instrumentation")["verified"] == 1

    assert progress_of(labelled, selected_filter_paths=["Geophony"], exclude_ambient=True)["total"] == 0


def test_a_saved_edit_in_progress_is_not_counted_as_verified():
    pending = clip("a", {VESSEL: 0.8}, labels=[VESSEL], verified=True, needs_reverify=True)

    assert progress_of(pending)["verified"] == 0


def test_empty_data_has_empty_bars():
    progress = build_progress([])

    assert progress["total"] == 0
    assert len(progress["bins"]) == 10
    assert all(entry["total"] == 0 for entry in progress["bins"])
    assert create_progress_chart(progress)
    assert create_progress_total(progress, scoped=False)


def find_class(component, class_name):
    found = []
    if isinstance(component, (list, tuple)):
        for child in component:
            found.extend(find_class(child, class_name))
    elif component is not None and not isinstance(component, str):
        if class_name in str(getattr(component, "className", "") or "").split():
            found.append(component)
        found.extend(find_class(getattr(component, "children", None), class_name))
    return found


@pytest.mark.parametrize(
    ("verified", "total", "shown"),
    [(0, 288, "0%"), (1, 288, "1%"), (183, 284, "64%"), (287, 288, "99%"), (288, 288, "100%")],
)
def test_total_never_rounds_a_review_away_or_finishes_it_early(verified, total, shown):
    children = create_progress_total({"verified": verified, "total": total}, scoped=False)

    assert find_class(children, "review-total-percent")[0].children == shown


def test_total_names_what_it_counts():
    assert find_class(create_progress_total({}, scoped=True), "review-total-title")[0].children == "Selected"
    assert find_class(create_progress_total({}, scoped=False), "review-total-title")[0].children == "Total"


def review_card(item):
    return create_spectrogram_card(item, image_src="/image.png", mode="verify")


def test_the_whole_review_card_opens_its_clip():
    card = review_card({"item_id": "clip", "predictions": {"labels": [VESSEL]}, "annotations": {}})

    assert card.id == {"type": "spectrogram-image", "item_id": "clip", "range_id": "card"}
    # A second id on the image would count every click twice.
    assert not any(getattr(image, "id", None) for image in find_class(card, "spectrogram-image"))


def test_review_card_shows_the_clip_time_with_its_date():
    item = {
        "item_id": "clip",
        "timestamps": {"start": "2026-09-17T21:10:00.000Z"},
        "predictions": {"labels": []},
        "annotations": {},
    }

    assert find_class(review_card(item), "review-card-time")[0].children == "2026-09-17 · 21:10 UTC"


def test_review_card_without_a_start_time_shows_no_time():
    item = {"item_id": "clip", "predictions": {"labels": []}, "annotations": {}}

    assert find_class(review_card(item), "review-card-time")[0].children == ""


def test_review_card_splits_suggestions_from_the_reviewers_own_labels():
    item = {
        "item_id": "clip",
        "predictions": {
            "labels": [VESSEL],
            "model_outputs": [{"class_hierarchy": VESSEL, "score": 0.58}],
        },
        "annotations": {"labels": [VESSEL, FIN_WHALE], "verified": True},
    }
    suggested, yours = find_class(review_card(item), "review-card-label-column")

    vessel = find_class(suggested, "review-label")
    assert [label.children for label in vessel] == ["Vessel"]
    assert vessel[0].title == f"{VESSEL} · 58% confidence"
    assert "review-label--model-accepted" in vessel[0].className
    assert "review-label--anthropophony" in vessel[0].className

    fin_whale = find_class(yours, "review-label")
    assert [label.children for label in fin_whale] == ["Fin whale"]
    assert "review-label--biophony" in fin_whale[0].className


def test_review_card_lists_suggestions_strongest_first():
    item = {
        "item_id": "clip",
        "predictions": {
            "labels": [AMBIENT_LABEL, VESSEL],
            "model_outputs": [
                {"class_hierarchy": AMBIENT_LABEL, "score": 0.3},
                {"class_hierarchy": VESSEL, "score": 0.6},
            ],
        },
        "annotations": {},
    }
    suggested, _ = find_class(review_card(item), "review-card-label-column")

    assert [label.children for label in find_class(suggested, "review-label")] == ["Vessel", "Ambient sound"]


def test_a_label_below_the_threshold_of_the_day_was_never_decided():
    # Lowering the range brings up classes the reviewer was never shown; the card
    # and modal must not say they were accepted.
    item = {
        "item_id": "clip",
        "predictions": {"labels": [AMBIENT_LABEL, VESSEL]},
        "annotations": {"labels": [AMBIENT_LABEL], "verified": True, "annotated_at": "2026-03-16"},
    }
    suggested, _ = find_class(review_card(item), "review-card-label-column")
    ambient, vessel = find_class(suggested, "review-label")

    assert "review-label--model-accepted" in ambient.className
    assert "review-label--model-unreviewed" in vessel.className

    rows = find_class(build_modal_item_actions(item, "verify", {"__global__": 0.0}), "modal-label-row--model-unreviewed")
    assert len(rows) == 1


def test_a_review_with_no_decisions_on_record_still_counts_its_suggestions_as_accepted():
    item = {"item_id": "clip", "predictions": {"labels": [VESSEL]}, "annotations": {"verified": True}}
    suggested, _ = find_class(review_card(item), "review-card-label-column")

    assert "review-label--model-accepted" in find_class(suggested, "review-label")[0].className


def test_undecided_labels_do_not_change_what_a_clip_counts_as():
    key = register(
        clip(
            "rejected",
            {VESSEL: 0.6, DATA_GAP: 0.1},
            rejected_labels=[VESSEL],
            verified=True,
        )
    )
    page = get_filtered_verify_items_page(key, thresholds_for_range(None, 0.0, 1.0), None, 0, 50, "rejected_only")

    assert page["visible_item_ids"] == ["rejected"]


def test_review_card_with_nothing_of_the_reviewers_says_so():
    item = {"item_id": "clip", "predictions": {"labels": [VESSEL]}, "annotations": {}}
    _, yours = find_class(review_card(item), "review-card-label-column")

    assert find_class(yours, "review-label-none")[0].children == "None"
