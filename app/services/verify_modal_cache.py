"""Lightweight server-side cache for verify-mode modal item lookup and sync."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock

_MAX_VERIFY_CACHE_KEYS = 8
_VERIFY_MODAL_CACHE = OrderedDict()
_VERIFY_MODAL_CACHE_LOCK = Lock()


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


def register_verify_modal_items(data):
    """Store the current verify items by ID and return a stable cache key."""
    cache_key = _build_verify_cache_key(data)
    if not cache_key:
        return None

    items = data.get("items") or []
    items_by_id = {}
    item_indices = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        if not item_id:
            continue
        items_by_id[item_id] = deepcopy(item)
        item_indices[item_id] = idx
    summary = deepcopy(data.get("summary")) if isinstance(data.get("summary"), dict) else {}

    with _VERIFY_MODAL_CACHE_LOCK:
        _VERIFY_MODAL_CACHE[cache_key] = {
            "items_by_id": items_by_id,
            "item_indices": item_indices,
            "summary": summary,
        }
        _VERIFY_MODAL_CACHE.move_to_end(cache_key)
        while len(_VERIFY_MODAL_CACHE) > _MAX_VERIFY_CACHE_KEYS:
            _VERIFY_MODAL_CACHE.popitem(last=False)
    return cache_key


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
