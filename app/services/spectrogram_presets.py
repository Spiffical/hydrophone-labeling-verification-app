"""Configurable spectrogram rendering presets for review workflows."""

from copy import deepcopy
from typing import Any, Dict, List, Optional


_RENDER_KEYS = ("win_dur_s", "overlap", "freq_min_hz", "freq_max_hz")


def _coerce_float(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> Optional[float]:
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
    """Return validated presets in their configured display order."""
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

        win_dur_s = _coerce_float(raw.get("win_dur_s"), minimum=0.05, maximum=30.0)
        overlap = _coerce_float(raw.get("overlap", 0.9), minimum=0.0, maximum=0.99)
        freq_min_hz = _coerce_float(raw.get("freq_min_hz"), minimum=0.0, maximum=200000.0)
        freq_max_hz = _coerce_float(raw.get("freq_max_hz"), minimum=0.01, maximum=200000.0)
        if (
            win_dur_s is None
            or overlap is None
            or freq_min_hz is None
            or freq_max_hz is None
            or freq_max_hz <= freq_min_hz
        ):
            continue

        label = str(raw.get("label") or "").strip()
        if not label:
            label = (
                f"{preset_id.replace('_', ' ').title()} "
                f"({_format_frequency(freq_min_hz)}-{_format_frequency(freq_max_hz)})"
            )

        presets.append(
            {
                "id": preset_id,
                "label": label,
                "win_dur_s": win_dur_s,
                "overlap": overlap,
                "freq_min_hz": freq_min_hz,
                "freq_max_hz": freq_max_hz,
            }
        )
        seen.add(preset_id)
    return presets


def find_matching_spectrogram_preset(
    cfg: Optional[Dict[str, Any]],
    *,
    tolerance: float = 1e-9,
) -> Optional[str]:
    """Return the preset whose render parameters match the active config."""
    render_cfg = (cfg or {}).get("spectrogram_render", {})
    if not isinstance(render_cfg, dict):
        return None

    for preset in get_spectrogram_presets(cfg):
        matches = True
        for key in _RENDER_KEYS:
            try:
                active_value = float(render_cfg.get(key))
            except (TypeError, ValueError):
                matches = False
                break
            if abs(active_value - float(preset[key])) > tolerance:
                matches = False
                break
        if matches:
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
    if not isinstance(render_cfg, dict):
        render_cfg = {}
    render_cfg = dict(render_cfg)
    for key in _RENDER_KEYS:
        render_cfg[key] = float(preset[key])
    render_cfg["active_preset"] = requested
    updated_cfg["spectrogram_render"] = render_cfg
    return updated_cfg
