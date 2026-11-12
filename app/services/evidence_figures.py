"""A figure per clip with the evidence for a suggested label: for example the
clicks' rhythm and spectrum against reference recordings, next to what the clip
was annotated as. The sidebar's Evidence button opens it.

The dashboard config names a folder (``evidence_figures.folder``, app/config.py).
A clip's figure is ``<folder>/<item_id>.png``; clips without one show no button.
An optional ``<folder>/<item_id>.txt`` holds a few short lines shown above the
button (say, who gave which label). An optional ``<folder>/<item_id>.json``
names clips worth comparing with this one, ``{"related": [{"item_id": ...,
"label": ..., "detail": ...}]}``: each becomes a button under the Evidence
button that opens that clip in a view-only window beside the review window
(evidence_figure_callbacks.py). The app only reads the folder.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

# Item ids that can name a file in the folder (no separators, no "..").
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# The caption stays a few lines beside the labels.
_CAPTION_LINES = 4
_CAPTION_CHARS = 300
# A few related clips, each a short button.
_RELATED_MAX = 6
_RELATED_LABEL_CHARS = 60
_RELATED_DETAIL_CHARS = 160


def _clip_file(cfg: Optional[Dict[str, Any]], item_id: Any, extension: str) -> Optional[str]:
    if not isinstance(cfg, dict) or not isinstance(item_id, str):
        return None
    if not _SAFE_ID.match(item_id) or ".." in item_id:
        return None
    folder = cfg.get("folder")
    if not isinstance(folder, str) or not folder:
        return None
    path = os.path.join(folder, f"{item_id}{extension}")
    return path if os.path.isfile(path) else None


def evidence_figure_path(cfg: Optional[Dict[str, Any]], item_id: Any) -> Optional[str]:
    """The figure file for one clip, or None (no config, an id that cannot be a
    file name, or no figure for it)."""
    return _clip_file(cfg, item_id, ".png")


def evidence_figure_src(cfg: Optional[Dict[str, Any]], item_id: Any) -> Optional[str]:
    """The URL the dialog loads the figure from (with its file time, so a new
    figure is not served from the browser cache), or None."""
    path = evidence_figure_path(cfg, item_id)
    if path is None:
        return None
    return f"/evidence-figure/{item_id}?v={os.stat(path).st_mtime_ns}"


def evidence_caption(cfg: Optional[Dict[str, Any]], item_id: Any) -> List[str]:
    """The clip's caption lines (blank lines dropped, at most a few short ones),
    or [] without a caption file."""
    path = _clip_file(cfg, item_id, ".txt")
    if path is None:
        return []
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read(_CAPTION_LINES * (_CAPTION_CHARS + 2) * 4)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [line[:_CAPTION_CHARS] for line in lines[:_CAPTION_LINES]]


def evidence_related(cfg: Optional[Dict[str, Any]], item_id: Any) -> List[Dict[str, str]]:
    """The clips to compare with this one, from ``<folder>/<item_id>.json``, as
    [{"item_id", "label", "detail"}] (label: the button text; detail: its
    tooltip). Entries whose id cannot name a clip, or that repeat the clip itself
    or an earlier entry, are dropped; at most a few are kept. [] without a file
    or when it cannot be read."""
    path = _clip_file(cfg, item_id, ".json")
    if path is None:
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    entries = data.get("related") if isinstance(data, dict) else None
    related: List[Dict[str, str]] = []
    seen = {item_id}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        other = entry.get("item_id")
        if not isinstance(other, str) or not _SAFE_ID.match(other) or ".." in other or other in seen:
            continue
        seen.add(other)
        label = str(entry.get("label") or other).strip()[:_RELATED_LABEL_CHARS]
        detail = str(entry.get("detail") or "").strip()[:_RELATED_DETAIL_CHARS]
        related.append({"item_id": other, "label": label, "detail": detail})
        if len(related) >= _RELATED_MAX:
            break
    return related
