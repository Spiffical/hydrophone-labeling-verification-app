"""Lightweight server-side cache for verify-mode item lookup/filtering and sync."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock

from app.services.annotations import ordered_unique_labels
from app.services.verification import get_item_rejected_labels, has_pending_label_edits

_MAX_VERIFY_CACHE_KEYS = 8
_VERIFY_MODAL_CACHE = OrderedDict()
_VERIFY_MODAL_CACHE_LOCK = Lock()


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _prediction_filter_entries(predictions):
    if not isinstance(predictions, dict):
        return [], []

    raw_labels = []
    entries = []
    model_outputs = predictions.get("model_outputs")
    if isinstance(model_outputs, list):
        for out in model_outputs:
            if not isinstance(out, dict):
                continue
            label = out.get("class_hierarchy")
            if not isinstance(label, str) or not label.strip():
                continue
            label_clean = label.strip()
            raw_labels.append(label_clean)
            entries.append((label_clean, _safe_float(out.get("score"), 0.0)))
        if entries:
            return ordered_unique_labels(raw_labels), entries

    confidence = predictions.get("confidence")
    if isinstance(confidence, dict):
        labels = ordered_unique_labels(predictions.get("labels") if isinstance(predictions.get("labels"), list) else [])
        matched_confidence_keys = set()
        for label_clean in labels:
            leaf_label = label_clean.split(">")[-1].strip()
            score = confidence.get(label_clean)
            confidence_key = label_clean
            if score is None and leaf_label:
                score = confidence.get(leaf_label)
                confidence_key = leaf_label
            if score is None:
                continue
            raw_labels.append(label_clean)
            entries.append((label_clean, _safe_float(score, 0.0)))
            matched_confidence_keys.add(confidence_key)

        for label, score in confidence.items():
            if not isinstance(label, str) or not label.strip():
                continue
            label_clean = label.strip()
            if label_clean in matched_confidence_keys:
                continue
            raw_labels.append(label_clean)
            entries.append((label_clean, _safe_float(score, 0.0)))
        if entries:
            return ordered_unique_labels(raw_labels), entries

    labels = predictions.get("labels")
    if isinstance(labels, list):
        for label in labels:
            if not isinstance(label, str) or not label.strip():
                continue
            label_clean = label.strip()
            raw_labels.append(label_clean)
            entries.append((label_clean, None))
    return ordered_unique_labels(raw_labels), entries


def _has_pending_verify_changes(item):
    annotations = item.get("annotations") if isinstance(item, dict) and isinstance(item.get("annotations"), dict) else {}
    if annotations.get("pending_save") or annotations.get("needs_reverify"):
        return True
    if annotations.get("verified"):
        return False
    return bool(annotations.get("has_manual_review")) and bool(
        annotations.get("labels")
        or annotations.get("rejected_labels")
        or annotations.get("notes")
        or annotations.get("annotated_at")
        or annotations.get("annotated_by")
    )


def _build_filter_record(item, index):
    if not isinstance(item, dict):
        return None
    item_id = item.get("item_id")
    if not item_id:
        return None
    predictions = item.get("predictions") if isinstance(item.get("predictions"), dict) else {}
    raw_labels, entries = _prediction_filter_entries(predictions)
    annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
    return {
        "item_id": item_id,
        "index": int(index),
        "raw_labels": raw_labels,
        "entries": entries,
        "is_verified": bool(annotations.get("verified")),
        "accepted_labels": ordered_unique_labels(annotations.get("labels") or []),
        "rejected_labels": ordered_unique_labels(get_item_rejected_labels(item)),
        "has_pending_label_edits": has_pending_label_edits(annotations),
        "has_pending_verify_changes": _has_pending_verify_changes(item),
    }


def _filter_record_labels(record, thresholds):
    if not isinstance(record, dict):
        return []
    thresholds = thresholds or {}
    global_threshold = _safe_float(thresholds.get("__global__"), 0.5)
    if global_threshold is None:
        global_threshold = 0.5

    filtered = []
    for label, score in record.get("entries") or []:
        if not isinstance(label, str) or not label.strip():
            continue
        label_clean = label.strip()
        if score is None:
            filtered.append(label_clean)
            continue
        label_threshold = _safe_float(thresholds.get(label_clean), global_threshold)
        if label_threshold is None:
            label_threshold = global_threshold
        if _safe_float(score, 0.0) >= label_threshold:
            filtered.append(label_clean)
    return ordered_unique_labels(filtered)


def _labels_match_filter(predicted_labels, selected_filter_paths):
    if selected_filter_paths is None:
        return True
    selected = [
        path.strip()
        for path in (selected_filter_paths or [])
        if isinstance(path, str) and path.strip()
    ]
    if not selected:
        return False
    for label in predicted_labels or []:
        if not isinstance(label, str) or not label.strip():
            continue
        label_clean = label.strip()
        for selected_path in selected:
            if label_clean == selected_path or label_clean.startswith(f"{selected_path} > "):
                return True
    return False


def _normalize_status_filter(status_filter):
    value = str(status_filter or "all").strip().lower()
    aliases = {
        "": "all",
        "any": "all",
        "accepted": "contains_accepted",
        "rejected": "contains_rejected",
        "reviewed": "verified",
    }
    return aliases.get(value, value)


def _verification_status_tokens(record, predicted_labels):
    if not isinstance(record, dict):
        return {"all"}
    accepted = set(ordered_unique_labels(record.get("accepted_labels") or []))
    rejected = set(ordered_unique_labels(record.get("rejected_labels") or []))
    if record.get("is_verified") and not record.get("has_pending_label_edits"):
        accepted.update(
            label
            for label in ordered_unique_labels(predicted_labels or [])
            if label not in rejected
        )

    has_accepted = bool(accepted)
    has_rejected = bool(rejected)
    tokens = {"all"}
    if record.get("is_verified"):
        tokens.add("verified")
    if has_accepted:
        tokens.add("contains_accepted")
    if has_rejected:
        tokens.add("contains_rejected")
    if has_accepted and not has_rejected:
        tokens.add("accepted_only")
    elif has_rejected and not has_accepted:
        tokens.add("rejected_only")
    elif has_accepted and has_rejected:
        tokens.add("mixed")
    elif not record.get("is_verified"):
        tokens.add("unverified")
    return tokens


def _status_matches_filter(record, predicted_labels, status_filter):
    normalized = _normalize_status_filter(status_filter)
    if normalized == "all":
        return True
    return normalized in _verification_status_tokens(record, predicted_labels)


def _build_verify_cache_key(data):
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    load_timestamp = data.get("load_timestamp")
    active_date = summary.get("active_date") or ""
    active_hydrophone = summary.get("active_hydrophone") or ""
    predictions_file = summary.get("predictions_file") or ""
    return f"{load_timestamp}|{active_date}|{active_hydrophone}|{predictions_file}|{len(items)}"


def build_verify_cache_key(data):
    """Return the deterministic cache key for a verify-mode dataset."""
    return _build_verify_cache_key(data)


def has_verify_modal_items(cache_key):
    """Return True when the verify modal cache already has this dataset."""
    if not cache_key:
        return False
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        return isinstance(cache_entry, dict)


def register_verify_modal_items(data):
    """Store the current verify items by ID and return a stable cache key."""
    cache_key = _build_verify_cache_key(data)
    if not cache_key:
        return None

    items = data.get("items") or []
    items_by_id = {}
    item_indices = {}
    filter_records = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        if not item_id:
            continue
        items_by_id[item_id] = deepcopy(item)
        item_indices[item_id] = idx
        record = _build_filter_record(item, idx)
        if record:
            filter_records[item_id] = record
    summary = deepcopy(data.get("summary")) if isinstance(data.get("summary"), dict) else {}

    with _VERIFY_MODAL_CACHE_LOCK:
        _VERIFY_MODAL_CACHE[cache_key] = {
            "load_timestamp": data.get("load_timestamp"),
            "items_by_id": items_by_id,
            "item_indices": item_indices,
            "filter_records": filter_records,
            "summary": summary,
        }
        _VERIFY_MODAL_CACHE.move_to_end(cache_key)
        while len(_VERIFY_MODAL_CACHE) > _MAX_VERIFY_CACHE_KEYS:
            _VERIFY_MODAL_CACHE.popitem(last=False)
    return cache_key


def get_verify_modal_data(cache_key):
    """Return a defensive dataset copy from the server-side verification cache."""
    if not cache_key:
        return None
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return None
        items_by_id = cache_entry.get("items_by_id")
        item_indices = cache_entry.get("item_indices")
        summary = cache_entry.get("summary")
        if not isinstance(items_by_id, dict) or not isinstance(item_indices, dict):
            return None
        ordered_ids = [
            item_id
            for item_id, _ in sorted(item_indices.items(), key=lambda entry: entry[1])
            if item_id in items_by_id
        ]
        data = {
            "load_timestamp": cache_entry.get("load_timestamp"),
            "items": [deepcopy(items_by_id[item_id]) for item_id in ordered_ids],
            "summary": deepcopy(summary) if isinstance(summary, dict) else {},
        }
    return data


def has_pending_verify_modal_changes(cache_key):
    """Return whether the cached dataset contains any unsaved verification edits."""
    if not cache_key:
        return False
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return False
        filter_records = cache_entry.get("filter_records")
        if not isinstance(filter_records, dict):
            return False
        return any(
            bool(record.get("has_pending_verify_changes"))
            for record in filter_records.values()
            if isinstance(record, dict)
        )


def ensure_verify_modal_items(data):
    """Register verify items only when this dataset is not already cached."""
    cache_key = _build_verify_cache_key(data)
    if not cache_key:
        return None
    if has_verify_modal_items(cache_key):
        return cache_key
    return register_verify_modal_items(data)


def get_verify_modal_items(cache_key):
    """Return cached verify items in original dataset order."""
    if not cache_key:
        return []
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return []
        items_by_id = cache_entry.get("items_by_id")
        item_indices = cache_entry.get("item_indices")
        if not isinstance(items_by_id, dict) or not isinstance(item_indices, dict):
            return []
        ordered = sorted(item_indices.items(), key=lambda entry: entry[1])
        items = [items_by_id.get(item_id) for item_id, _ in ordered]
    return [deepcopy(item) for item in items if isinstance(item, dict)]


def get_verify_filter_leaf_classes(cache_key):
    """Return all prediction classes from the cached verify dataset."""
    if not cache_key:
        return []
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return []
        filter_records = cache_entry.get("filter_records")
        if not isinstance(filter_records, dict):
            return []
        labels = []
        for record in filter_records.values():
            if not isinstance(record, dict):
                continue
            labels.extend(record.get("raw_labels") or [])
    return sorted(ordered_unique_labels(labels), key=lambda text: text.lower())


def get_filtered_verify_items_page(
    cache_key,
    thresholds,
    selected_filter_paths,
    current_page,
    items_per_page,
    status_filter="all",
):
    """Filter cached verify items and return one page plus lightweight summary data."""
    try:
        page_size = max(1, int(items_per_page or 25))
    except (TypeError, ValueError):
        page_size = 25
    try:
        requested_page = int(current_page or 0)
    except (TypeError, ValueError):
        requested_page = 0
    requested_page = max(0, requested_page)

    if not cache_key:
        return {
            "items": [],
            "visible_item_ids": [],
            "page_index": 0,
            "total_pages": 1,
            "total_items": 0,
        }

    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return {
                "items": [],
                "visible_item_ids": [],
                "page_index": 0,
                "total_pages": 1,
                "total_items": 0,
            }
        items_by_id = cache_entry.get("items_by_id")
        item_indices = cache_entry.get("item_indices")
        filter_records = cache_entry.get("filter_records")
        if not isinstance(items_by_id, dict) or not isinstance(item_indices, dict):
            return {
                "items": [],
                "visible_item_ids": [],
                "page_index": 0,
                "total_pages": 1,
                "total_items": 0,
            }
        if not isinstance(filter_records, dict):
            filter_records = {}

        ordered_ids = [
            item_id
            for item_id, _ in sorted(item_indices.items(), key=lambda entry: entry[1])
            if item_id in items_by_id
        ]
        visible_ids = []
        predicted_labels_by_id = {}
        for item_id in ordered_ids:
            record = filter_records.get(item_id)
            item = items_by_id.get(item_id)
            if not isinstance(record, dict):
                record = _build_filter_record(item, item_indices.get(item_id, 0))
            if not isinstance(record, dict):
                continue
            predicted_labels = _filter_record_labels(record, thresholds)
            if not record.get("is_verified") and not predicted_labels:
                continue
            if not _labels_match_filter(predicted_labels, selected_filter_paths):
                continue
            if not _status_matches_filter(record, predicted_labels, status_filter):
                continue
            visible_ids.append(item_id)
            predicted_labels_by_id[item_id] = predicted_labels

        total_items = len(visible_ids)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        page_index = max(0, min(requested_page, total_pages - 1))
        start_idx = page_index * page_size
        page_ids = visible_ids[start_idx : start_idx + page_size]
        page_items = []
        for item_id in page_ids:
            item = items_by_id.get(item_id)
            if not isinstance(item, dict):
                continue
            display_item = dict(item)
            display_predictions = dict(item.get("predictions") or {})
            display_predictions["labels"] = predicted_labels_by_id.get(item_id, [])
            display_item["predictions"] = display_predictions
            page_items.append(display_item)

    return {
        "items": page_items,
        "visible_item_ids": visible_ids,
        "page_index": page_index,
        "total_pages": total_pages,
        "total_items": total_items,
    }


def get_verify_modal_item(cache_key, item_id):
    """Return a defensive copy of a cached verify item, if present."""
    if not cache_key or not item_id:
        return None
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return None
        items_by_id = cache_entry.get("items_by_id")
        if not isinstance(items_by_id, dict):
            return None
        item = items_by_id.get(item_id)
    return deepcopy(item) if isinstance(item, dict) else None


def update_verify_modal_item(cache_key, item):
    """Update a cached verify item after a modal save and return its index."""
    if not cache_key or not isinstance(item, dict):
        return None
    item_id = item.get("item_id")
    if not item_id:
        return None
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return None
        items_by_id = cache_entry.get("items_by_id")
        item_indices = cache_entry.get("item_indices")
        if not isinstance(items_by_id, dict) or not isinstance(item_indices, dict):
            return None
        if item_id not in item_indices:
            return None
        items_by_id[item_id] = deepcopy(item)
        filter_records = cache_entry.get("filter_records")
        if isinstance(filter_records, dict):
            record = _build_filter_record(item, item_indices.get(item_id, 0))
            if record:
                filter_records[item_id] = record
        _VERIFY_MODAL_CACHE.move_to_end(cache_key)
        return item_indices.get(item_id)


def get_verify_modal_item_index(cache_key, item_id):
    if not cache_key or not item_id:
        return None
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return None
        item_indices = cache_entry.get("item_indices")
        if not isinstance(item_indices, dict):
            return None
        return item_indices.get(item_id)


def get_verify_modal_summary(cache_key):
    """Return cached summary with annotated/verified counts recomputed."""
    if not cache_key:
        return None
    with _VERIFY_MODAL_CACHE_LOCK:
        cache_entry = _VERIFY_MODAL_CACHE.get(cache_key)
        if not isinstance(cache_entry, dict):
            return None
        items_by_id = cache_entry.get("items_by_id")
        summary = cache_entry.get("summary")
        if not isinstance(items_by_id, dict):
            return None
        summary_copy = deepcopy(summary) if isinstance(summary, dict) else {}
        items = list(items_by_id.values())
    summary_copy["annotated"] = sum(
        1
        for item in items
        if isinstance(item, dict) and ((item.get("annotations") or {}).get("labels") or [])
    )
    summary_copy["verified"] = sum(
        1
        for item in items
        if isinstance(item, dict) and bool((item.get("annotations") or {}).get("verified"))
    )
    return summary_copy
