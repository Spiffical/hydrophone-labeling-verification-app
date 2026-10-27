"""A figure per clip with the evidence for a suggested label: for example the
clicks' rhythm and spectrum against reference recordings, next to what the clip
was annotated as. The sidebar's Evidence button opens it.

The dashboard config names a folder (``evidence_figures.folder``, app/config.py).
A clip's figure is ``<folder>/<item_id>.png``; clips without one show no button.
An optional ``<folder>/<item_id>.txt`` holds a few short lines shown above the
button (say, who gave which label). The app only reads the folder.
"""

import os
import re
from typing import Any, Dict, List, Optional

# Item ids that can name a file in the folder (no separators, no "..").
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# The caption stays a few lines beside the labels.
_CAPTION_LINES = 4
_CAPTION_CHARS = 300


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
