"""Reuse unchanged cards when annotations change on the current label page."""

import hashlib
import json

from dash import no_update


def _fingerprint(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def grid_render_state(items, render_context):
    return {
        "context": _fingerprint(render_context),
        "ids": [item.get("item_id") for item in items],
        "items": [_fingerprint(item) for item in items],
    }


def incremental_grid(previous, current, build_full, build_card, update_card):
    """Update changed columns; rebuild on navigation or display changes."""
    if (
        not isinstance(previous, dict)
        or not current["ids"]
        or not all(current["ids"])
        or len(set(current["ids"])) != len(current["ids"])
        or previous.get("context") != current["context"]
        or previous.get("ids") != current["ids"]
        or len(previous.get("items", [])) != len(current["items"])
    ):
        return build_full()
    changed = [
        index for index, fingerprint in enumerate(current["items"])
        if previous["items"][index] != fingerprint
    ]
    if not changed:
        return no_update
    # Target individual columns. Updating the parent's children (even with
    # Patch) remounts unchanged neighbours in Dash 4's renderer.
    for index in changed:
        update_card(build_card(index))
    return no_update
