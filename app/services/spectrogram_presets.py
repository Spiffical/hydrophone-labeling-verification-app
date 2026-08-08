"""Configurable spectrogram rendering presets for review workflows."""

from copy import deepcopy
from typing import Any, Dict, List, Optional


_RENDER_KEYS = ("win_dur_s", "overlap", "freq_min_hz", "freq_max_hz")
_RENDER_LIMITS = {
    "win_dur_s": (0.05, 30.0),
    "overlap": (0.0, 0.99),
    "freq_min_hz": (0.0, 200000.0),
    "freq_max_hz": (0.01, 200000.0),
}


def _coerce_float(value: Any, *, minimum: float, maximum: float) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < minimum or parsed > maximum:
        return None
    return parsed


def _format_frequency(value: float) -> str:
    if value >= 1000.0 and value % 1000.0 == 0:
        return f"{int(value / 1000.0)} kHz"
    if value >= 1000.0:
        return f"{value / 1000.0:g} kHz"
    return f"{value:g} Hz"


def get_spectrogram_presets(cfg: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return valid presets in configured display order."""
    render_cfg = (cfg or {}).get("spectrogram_render", {})
    if not isinstance(render_cfg, dict):
        return []

    raw_presets = render_cfg.get("presets")
    if isinstance(raw_presets, dict):
        candidates = [
            dict(value, id=key)
            for key, value in raw_presets.items()
            if isinstance(value, dict)
        ]
    elif isinstance(raw_presets, list):
        candidates = [value for value in raw_presets if isinstance(value, dict)]
    else:
        return []

    presets: List[Dict[str, Any]] = []
    seen = set()
    for raw in candidates:
        preset_id = str(raw.get("id") or raw.get("name") or "").strip()
        if not preset_id or preset_id in seen:
            continue

        resolved = {}
        for key, (minimum, maximum) in _RENDER_LIMITS.items():
            default = 0.9 if key == "overlap" else None
            value = _coerce_float(
                raw.get(key, default),
                minimum=minimum,
                maximum=maximum,
            )
            if value is None:
                resolved = {}
                break
            resolved[key] = value
        if not resolved or resolved["freq_max_hz"] <= resolved["freq_min_hz"]:
            continue

        label = str(raw.get("label") or "").strip()
        if not label:
            label = (
                f"{preset_id.replace('_', ' ').title()} "
                f"({_format_frequency(resolved['freq_min_hz'])}-"
                f"{_format_frequency(resolved['freq_max_hz'])})"
            )
        presets.append(
            {
                "id": preset_id,
                "label": label,
                "scope": "item" if str(raw.get("scope") or "").strip().lower() == "item" else "global",
                "metadata_key": str(raw.get("metadata_key") or "recommended_spectrogram").strip(),
                **resolved,
            }
        )
        seen.add(preset_id)
    return presets


def get_item_spectrogram_recommendation(
    item: Optional[Dict[str, Any]],
    preset: Optional[Dict[str, Any]],
) -> Optional[Dict[str, float]]:
    """Return validated item metadata for an item-scoped preset."""
    if not isinstance(item, dict) or not isinstance(preset, dict):
        return None
    if preset.get("scope") != "item":
        return None

    metadata_key = str(preset.get("metadata_key") or "recommended_spectrogram")
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    recommendation = metadata.get(metadata_key)
    if not isinstance(recommendation, dict):
        recommendation = item.get(metadata_key)
    if not isinstance(recommendation, dict):
        return None

    resolved = {}
    for key, (minimum, maximum) in _RENDER_LIMITS.items():
        value = _coerce_float(
            recommendation.get(key),
            minimum=minimum,
            maximum=maximum,
        )
        if value is None:
            return None
        resolved[key] = value
    if resolved["freq_max_hz"] <= resolved["freq_min_hz"]:
        return None
    return resolved


def find_matching_spectrogram_preset(
    cfg: Optional[Dict[str, Any]],
    *,
    tolerance: float = 1e-9,
) -> Optional[str]:
    """Return the preset whose render parameters match the active config."""
    render_cfg = (cfg or {}).get("spectrogram_render", {})
    if not isinstance(render_cfg, dict):
        return None

    presets = get_spectrogram_presets(cfg)
    active_preset = str(render_cfg.get("active_preset") or "").strip()
    if active_preset == "custom":
        return "custom"
    if active_preset:
        active = next((preset for preset in presets if preset["id"] == active_preset), None)
        if active and active.get("scope") == "item":
            return active_preset

    for preset in presets:
        if preset.get("scope") == "item":
            continue
        if all(
            _coerce_float(
                render_cfg.get(key),
                minimum=_RENDER_LIMITS[key][0],
                maximum=_RENDER_LIMITS[key][1],
            )
            is not None
            and abs(float(render_cfg[key]) - float(preset[key])) <= tolerance
            for key in _RENDER_KEYS
        ):
            return str(preset["id"])
    return None


def apply_spectrogram_preset(
    cfg: Optional[Dict[str, Any]],
    preset_id: str,
) -> Optional[Dict[str, Any]]:
    """Return a copied config with one validated preset applied."""
    requested = str(preset_id or "").strip()
    preset = next(
        (candidate for candidate in get_spectrogram_presets(cfg) if candidate["id"] == requested),
        None,
    )
    if preset is None:
        return None

    updated_cfg = deepcopy(cfg or {})
    render_cfg = updated_cfg.get("spectrogram_render")
    render_cfg = dict(render_cfg) if isinstance(render_cfg, dict) else {}
    for key in _RENDER_KEYS:
        render_cfg[key] = float(preset[key])
    render_cfg["active_preset"] = requested
    updated_cfg["spectrogram_render"] = render_cfg
    return updated_cfg
