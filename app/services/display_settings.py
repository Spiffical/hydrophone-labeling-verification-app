"""Normalization helpers for interactive display settings."""

from typing import Any, Dict, Optional


VALID_COLORMAPS = {"default", "hydrophone"}


def resolve_colormap_choice(
    selected: Any,
    display_cfg: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolve current and legacy colormap-control values."""
    fallback = str((display_cfg or {}).get("colormap") or "default").strip().lower()
    if fallback not in VALID_COLORMAPS:
        fallback = "default"
    if isinstance(selected, bool):
        return "hydrophone" if selected else fallback
    normalized = str(selected or "").strip().lower()
    return normalized if normalized in VALID_COLORMAPS else fallback
