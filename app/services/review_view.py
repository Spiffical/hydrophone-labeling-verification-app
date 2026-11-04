"""Which clips the review page shows, in what order, and how far review has got.

A clip's confidence is the model's highest score among the classes in view. The
progress chart bins clips by it and the confidence range selects by it, so the
range picks out bars of the chart. Scores below the top one say little: nearly
every clip has some class under 10%.
"""

import hashlib

from app.services.annotations import split_hierarchy_label
from app.services.verify_filter_tree import (
    normalize_verify_class_filter,
    predicted_labels_match_filter,
)

AMBIENT_LABEL = "Other > Ambient sound"

# Top of the label hierarchy, bottom of the stack upward. Biophony and
# Anthropophony stay apart: their colours merge under red-green colour blindness.
REVIEW_CATEGORIES = ("Biophony", "Geophony", "Anthropophony", "Instrumentation", "Other")

PROGRESS_BIN_COUNT = 10

DEFAULT_CONFIDENCE_THRESHOLD = 0.5
RANGE_MIN_KEY = "__range_min__"
RANGE_MAX_KEY = "__range_max__"

# Saving accepts every suggested label the reviewer did not reject, so a range
# starting at 0% must not turn all of a clip's near-zero classes into suggestions.
MIN_SUGGESTION_SCORE = 0.05

ORDER_DATASET = "dataset"
ORDER_PRECISION = "precision"
ORDER_SHUFFLE = "shuffle"
REVIEW_ORDERS = (ORDER_DATASET, ORDER_PRECISION, ORDER_SHUFFLE)


def _fraction(value, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if 0.0 <= number <= 1.0 else default


def confidence_range(thresholds):
    """Return the (lower, upper) confidence a clip must fall within."""
    thresholds = thresholds or {}
    global_threshold = _fraction(thresholds.get("__global__"), DEFAULT_CONFIDENCE_THRESHOLD)
    return (
        _fraction(thresholds.get(RANGE_MIN_KEY), global_threshold),
        _fraction(thresholds.get(RANGE_MAX_KEY), 1.0),
    )


def thresholds_for_range(thresholds, lower, upper):
    """Apply a confidence range, keeping the suggestion threshold saves rely on."""
    updated = dict(thresholds or {})
    updated["__global__"] = max(float(lower), MIN_SUGGESTION_SCORE)
    updated[RANGE_MIN_KEY] = float(lower)
    updated[RANGE_MAX_KEY] = float(upper)
    return updated


def normalize_review_view(view):
    """Return the page's ambient and ordering settings; no view filters nothing."""
    view = view if isinstance(view, dict) else {}
    order = view.get("order")
    try:
        seed = int(view.get("seed") or 0)
    except (TypeError, ValueError):
        seed = 0
    return {
        "exclude_ambient": bool(view.get("exclude_ambient")),
        "order": order if order in REVIEW_ORDERS else ORDER_DATASET,
        "seed": seed,
    }


def active_class_filter(class_filter):
    """Return the selected class paths, or None when every class is in view."""
    return normalize_verify_class_filter(class_filter) or None


def review_category(label):
    """Return the top-level category a label belongs to."""
    parts = split_hierarchy_label(label)
    return parts[0] if parts and parts[0] in REVIEW_CATEGORIES else "Other"


def selection_matcher(selected_paths):
    """Return a label test for this selection, remembering each label's answer."""
    if selected_paths is None:
        return lambda label: True
    answers = {}

    def matches(label):
        if label not in answers:
            answers[label] = predicted_labels_match_filter([label], selected_paths)
        return answers[label]

    return matches


def clip_confidence(record, in_selection, exclude_ambient):
    """Return a clip's confidence and whether a class in view has no score at all.

    A class has no score when it is a provisional label, or a reviewer's label the
    model cannot output. The confidence range has nothing to test on those, so they
    bring their clip into view whatever the range; otherwise labels from the wider
    hierarchy could never be found again.
    """
    confidence = None
    scored_labels = set()
    has_unscored_label = False
    for label, score in record.get("entries") or []:
        if score is not None:
            scored_labels.add(label)
        if (exclude_ambient and label == AMBIENT_LABEL) or not in_selection(label):
            continue
        if score is None:
            has_unscored_label = True
        elif confidence is None or score > confidence:
            confidence = score
    for label in record.get("accepted_labels") or []:
        if label in scored_labels or (exclude_ambient and label == AMBIENT_LABEL):
            continue
        if in_selection(label):
            has_unscored_label = True
            break
    return confidence, has_unscored_label


def shuffle_rank(seed, item_id):
    """Rank a clip for a shuffle.

    Hashing each clip rather than shuffling the list keeps the remaining clips in
    place as saved ones leave the page.
    """
    digest = hashlib.blake2b(f"{seed}|{item_id}".encode("utf-8"), digest_size=8)
    return digest.digest()


def order_review_ids(item_ids, confidences, view):
    """Sort clips for display; equal clips keep their dataset order."""
    order = view["order"]
    if order == ORDER_PRECISION:
        def highest_confidence_first(item_id):
            confidence = confidences.get(item_id)
            return 1.0 if confidence is None else -confidence

        return sorted(item_ids, key=highest_confidence_first)
    if order == ORDER_SHUFFLE:
        return sorted(item_ids, key=lambda item_id: shuffle_rank(view["seed"], item_id))
    return list(item_ids)


def _top_model_class(record, exclude_ambient):
    best_label = None
    best_score = None
    for label, score in record.get("entries") or []:
        if score is None or (exclude_ambient and label == AMBIENT_LABEL):
            continue
        if best_score is None or score > best_score:
            best_label, best_score = label, score
    return best_label, best_score


def _clip_progress_class(record, model_class, is_verified, in_selection, exclude_ambient):
    """Return the class a clip counts under: a reviewer's word over the model's.

    A clip with several labels counts under one the selection asked for. Ambient
    comes last when excluded, but stays the answer for a clip reviewed as ambient:
    the model's next guess is exactly what that reviewer turned down.
    """
    labels = record.get("accepted_labels") if is_verified else None
    if not labels:
        return model_class or AMBIENT_LABEL
    if exclude_ambient:
        labels = sorted(labels, key=lambda label: label == AMBIENT_LABEL)
    return next((label for label in labels if in_selection(label)), labels[0])


def build_progress(records, *, selected_paths=None, exclude_ambient=False):
    """Count clips by confidence bin, category and whether they are verified.

    Each clip counts once, so the bars add up to the total beside them. It sits at
    the model's confidence even once reviewed, so verifying a clip brightens its
    bar without moving it, and under the class a reviewer gave it, which is how
    classes the model cannot output reach the chart.

    Selected paths limit the count to clips of those classes.
    """
    in_selection = selection_matcher(selected_paths)
    bins = [
        {category: {"verified": 0, "unverified": 0} for category in REVIEW_CATEGORIES}
        for _ in range(PROGRESS_BIN_COUNT)
    ]
    total = 0
    verified_total = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        is_verified = bool(record.get("is_verified")) and not record.get("has_pending_verify_changes")
        model_class, score = _top_model_class(record, exclude_ambient)
        progress_class = _clip_progress_class(
            record, model_class, is_verified, in_selection, exclude_ambient
        )
        if not in_selection(progress_class):
            continue
        bin_index = min(PROGRESS_BIN_COUNT - 1, int((score or 0.0) * PROGRESS_BIN_COUNT))
        state = "verified" if is_verified else "unverified"
        bins[bin_index][review_category(progress_class)][state] += 1
        total += 1
        verified_total += int(is_verified)

    width = 100 // PROGRESS_BIN_COUNT
    return {
        "bins": [
            {
                "start": index * width,
                "end": (index + 1) * width,
                "total": sum(sum(counts.values()) for counts in categories.values()),
                "verified": sum(counts["verified"] for counts in categories.values()),
                "categories": [
                    {"category": category, **categories[category]}
                    for category in REVIEW_CATEGORIES
                    if sum(categories[category].values())
                ],
            }
            for index, categories in enumerate(bins)
        ],
        "total": total,
        "verified": verified_total,
    }
