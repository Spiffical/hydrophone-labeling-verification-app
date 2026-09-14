"""State and render helpers for the unified visible spectrogram ranges."""

from copy import deepcopy
from math import isfinite
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from app.services.spectrogram_presets import (
    apply_spectrogram_preset,
    find_matching_spectrogram_preset,
    get_item_spectrogram_recommendation,
    get_spectrogram_presets,
)


MAX_CUSTOM_RANGES = 8
MAX_VISIBLE_COMPANION_RANGES = 5


def format_frequency(value: Any) -> str:
    parsed = float(value)
    if parsed >= 1000.0:
        scaled = parsed / 1000.0
        return f"{scaled:g} kHz"
    return f"{parsed:g} Hz"


def format_frequency_range(freq_min_hz: Any, freq_max_hz: Any) -> str:
    return f"{format_frequency(freq_min_hz)} - {format_frequency(freq_max_hz)}"


def _configured_preset_id(cfg: Optional[Dict[str, Any]]) -> Optional[str]:
    preset_id = find_matching_spectrogram_preset(cfg)
    valid_ids = {preset["id"] for preset in get_spectrogram_presets(cfg)}
    return preset_id if preset_id in valid_ids else None


def initial_spectrogram_range_state(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    active_preset_id = _configured_preset_id(cfg)
    return {
        "schema_version": "spectrogram-visible-ranges-v2",
        "preset_ids": [active_preset_id] if active_preset_id else [],
        "custom_ranges": [],
        "active_range_id": active_preset_id or "configured-range",
    }


def _finite_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _ordered_unique(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            out.append(normalized)
            seen.add(normalized)
    return out


def normalize_spectrogram_range_state(
    value: Any,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    valid_preset_ids = {preset["id"] for preset in get_spectrogram_presets(cfg)}
    preset_ids = [
        preset_id
        for preset_id in _ordered_unique(raw.get("preset_ids") or [])
        if preset_id in valid_preset_ids
    ][:MAX_VISIBLE_COMPANION_RANGES]

    configured_preset_id = _configured_preset_id(cfg)
    if (
        raw.get("schema_version") != "spectrogram-visible-ranges-v2"
        and configured_preset_id
        and configured_preset_id not in preset_ids
    ):
        preset_ids.insert(0, configured_preset_id)
        preset_ids = preset_ids[:MAX_VISIBLE_COMPANION_RANGES]

    custom_ranges = []
    seen_ids = set()
    for candidate in raw.get("custom_ranges") or []:
        if not isinstance(candidate, dict):
            continue
        range_id = str(candidate.get("id") or "").strip()
        label = str(candidate.get("label") or "").strip()
        freq_min_hz = _finite_float(candidate.get("freq_min_hz"))
        freq_max_hz = _finite_float(candidate.get("freq_max_hz"))
        if (
            not range_id
            or range_id in seen_ids
            or not label
            or freq_min_hz is None
            or freq_max_hz is None
            or freq_min_hz < 0.0
            or freq_max_hz <= freq_min_hz
            or freq_max_hz > 200000.0
        ):
            continue
        custom_ranges.append(
            {
                "id": range_id,
                "label": label[:40],
                "freq_min_hz": round(freq_min_hz, 6),
                "freq_max_hz": round(freq_max_hz, 6),
                "visible": bool(candidate.get("visible", True)),
            }
        )
        seen_ids.add(range_id)
        if len(custom_ranges) >= MAX_CUSTOM_RANGES:
            break

    visible_custom_ids = [
        candidate["id"] for candidate in custom_ranges if candidate.get("visible")
    ]
    if not preset_ids and not visible_custom_ids and configured_preset_id:
        preset_ids = [configured_preset_id]

    selected_ids = preset_ids + visible_custom_ids
    active_range_id = str(raw.get("active_range_id") or "").strip()
    if active_range_id not in selected_ids:
        active_range_id = selected_ids[0] if selected_ids else "configured-range"

    return {
        "schema_version": "spectrogram-visible-ranges-v2",
        "preset_ids": preset_ids,
        "custom_ranges": custom_ranges,
        "active_range_id": active_range_id,
    }


def add_custom_spectrogram_range(
    state: Any,
    cfg: Optional[Dict[str, Any]],
    *,
    label: Any,
    freq_min_hz: Any,
    freq_max_hz: Any,
) -> Tuple[Dict[str, Any], Optional[str]]:
    normalized = normalize_spectrogram_range_state(state, cfg)
    clean_label = str(label or "").strip()
    lower = _finite_float(freq_min_hz)
    upper = _finite_float(freq_max_hz)
    if not clean_label:
        return normalized, "Enter a range name."
    if lower is None or upper is None:
        return normalized, "Enter valid minimum and maximum frequencies."
    if lower < 0.0 or upper <= lower or upper > 200000.0:
        return normalized, "Use 0-200,000 Hz, with maximum greater than minimum."
    if len(normalized["custom_ranges"]) >= MAX_CUSTOM_RANGES:
        return normalized, f"A maximum of {MAX_CUSTOM_RANGES} custom ranges is supported."

    normalized["custom_ranges"].append(
        {
            "id": f"custom-{uuid4().hex[:10]}",
            "label": clean_label[:40],
            "freq_min_hz": round(lower, 6),
            "freq_max_hz": round(upper, 6),
            "visible": True,
        }
    )
    return normalized, None


def update_spectrogram_range_visibility(
    state: Any,
    cfg: Optional[Dict[str, Any]],
    *,
    preset_ids: Iterable[Any],
    visible_custom_ids: Iterable[Any],
) -> Dict[str, Any]:
    normalized = normalize_spectrogram_range_state(state, cfg)
    valid_preset_ids = {preset["id"] for preset in get_spectrogram_presets(cfg)}
    normalized["preset_ids"] = [
        preset_id
        for preset_id in _ordered_unique(preset_ids)
        if preset_id in valid_preset_ids
    ][:MAX_VISIBLE_COMPANION_RANGES]
    remaining = max(0, MAX_VISIBLE_COMPANION_RANGES - len(normalized["preset_ids"]))
    visible = set(_ordered_unique(visible_custom_ids)[:remaining])
    for custom_range in normalized["custom_ranges"]:
        custom_range["visible"] = custom_range["id"] in visible
    selected_ids = normalized["preset_ids"] + [
        candidate["id"]
        for candidate in normalized["custom_ranges"]
        if candidate.get("visible")
    ]
    if normalized.get("active_range_id") not in selected_ids:
        normalized["active_range_id"] = (
            selected_ids[0] if selected_ids else normalized.get("active_range_id")
        )
    return normalized


def remove_custom_spectrogram_range(
    state: Any,
    cfg: Optional[Dict[str, Any]],
    range_id: Any,
) -> Dict[str, Any]:
    normalized = normalize_spectrogram_range_state(state, cfg)
    target = str(range_id or "").strip()
    normalized["custom_ranges"] = [
        candidate for candidate in normalized["custom_ranges"] if candidate["id"] != target
    ]
    selected_ids = normalized["preset_ids"] + [
        candidate["id"]
        for candidate in normalized["custom_ranges"]
        if candidate.get("visible")
    ]
    if normalized.get("active_range_id") not in selected_ids:
        normalized["active_range_id"] = selected_ids[0] if selected_ids else "configured-range"
    return normalized


def sort_spectrogram_ranges_for_display(ranges: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Place higher-frequency ranges above lower-frequency ranges on screen."""
    return sorted(
        [dict(candidate) for candidate in ranges or [] if isinstance(candidate, dict)],
        key=lambda candidate: (
            -float(candidate.get("freq_max_hz", 0.0)),
            -float(candidate.get("freq_min_hz", 0.0)),
            str(candidate.get("label") or "").lower(),
        ),
    )


def infer_custom_fft_settings(freq_max_hz: Any) -> Tuple[float, float]:
    upper = float(freq_max_hz)
    if upper <= 250.0:
        return 1.0, 0.9
    if upper <= 2500.0:
        return 0.25, 0.9
    if upper <= 16000.0:
        return 0.05, 0.9
    if upper <= 40000.0:
        return 0.02, 0.9
    return 0.002, 0.75


def config_for_spectrogram_range(
    cfg: Optional[Dict[str, Any]],
    range_spec: Dict[str, Any],
) -> Dict[str, Any]:
    preset_id = str(range_spec.get("preset_id") or "").strip()
    if preset_id:
        preset_cfg = apply_spectrogram_preset(cfg, preset_id)
        if preset_cfg is not None:
            return preset_cfg

    updated = deepcopy(cfg or {})
    render_cfg = updated.get("spectrogram_render")
    render_cfg = dict(render_cfg) if isinstance(render_cfg, dict) else {}
    win_dur_s, overlap = infer_custom_fft_settings(range_spec["freq_max_hz"])
    render_cfg.update(
        {
            "active_preset": "custom",
            "win_dur_s": win_dur_s,
            "overlap": overlap,
            "freq_min_hz": float(range_spec["freq_min_hz"]),
            "freq_max_hz": float(range_spec["freq_max_hz"]),
        }
    )
    updated["spectrogram_render"] = render_cfg
    return updated


def resolve_visible_spectrogram_ranges(
    item: Optional[Dict[str, Any]],
    cfg: Optional[Dict[str, Any]],
    state: Any,
) -> List[Dict[str, Any]]:
    if (cfg or {}).get("spectrogram_render", {}).get("source", "existing") != "audio_generated":
        return []
    normalized = normalize_spectrogram_range_state(state, cfg)
    presets = {preset["id"]: preset for preset in get_spectrogram_presets(cfg)}
    resolved: List[Dict[str, Any]] = []
    signatures = set()

    for preset_id in normalized["preset_ids"]:
        preset = presets.get(preset_id)
        if not preset:
            continue
        settings = dict(preset)
        if preset.get("scope") == "item":
            recommendation = get_item_spectrogram_recommendation(item, preset)
            if recommendation is None:
                continue
            settings.update(recommendation)
        signature = (
            round(float(settings["freq_min_hz"]), 6),
            round(float(settings["freq_max_hz"]), 6),
            round(float(settings["win_dur_s"]), 6),
            round(float(settings["overlap"]), 6),
        )
        if signature in signatures:
            continue
        signatures.add(signature)
        resolved.append(
            {
                "id": f"preset-{preset_id}",
                "selection_id": preset_id,
                "preset_id": preset_id,
                "label": preset["label"],
                "freq_min_hz": float(settings["freq_min_hz"]),
                "freq_max_hz": float(settings["freq_max_hz"]),
                "win_dur_s": float(settings["win_dur_s"]),
                "overlap": float(settings["overlap"]),
            }
        )

    visible_custom = [
        candidate for candidate in normalized["custom_ranges"] if candidate.get("visible")
    ]
    remaining = max(0, MAX_VISIBLE_COMPANION_RANGES - len(resolved))
    for candidate in visible_custom[:remaining]:
        win_dur_s, overlap = infer_custom_fft_settings(candidate["freq_max_hz"])
        signature = (
            round(float(candidate["freq_min_hz"]), 6),
            round(float(candidate["freq_max_hz"]), 6),
            round(float(win_dur_s), 6),
            round(float(overlap), 6),
        )
        if signature in signatures:
            continue
        signatures.add(signature)
        resolved.append(
            {
                **candidate,
                "selection_id": candidate["id"],
                "win_dur_s": win_dur_s,
                "overlap": overlap,
            }
        )

    if not resolved:
        render_cfg = (cfg or {}).get("spectrogram_render", {})
        if isinstance(render_cfg, dict):
            freq_min_hz = _finite_float(render_cfg.get("freq_min_hz"))
            freq_max_hz = _finite_float(render_cfg.get("freq_max_hz"))
            win_dur_s = _finite_float(render_cfg.get("win_dur_s"))
            overlap = _finite_float(render_cfg.get("overlap"))
            if (
                freq_min_hz is not None
                and freq_max_hz is not None
                and freq_max_hz > freq_min_hz
                and win_dur_s is not None
                and overlap is not None
            ):
                resolved.append(
                    {
                        "id": "configured-range",
                        "selection_id": "configured-range",
                        "label": "Custom range",
                        "freq_min_hz": freq_min_hz,
                        "freq_max_hz": freq_max_hz,
                        "win_dur_s": win_dur_s,
                        "overlap": overlap,
                    }
                )

    return sort_spectrogram_ranges_for_display(resolved[:MAX_VISIBLE_COMPANION_RANGES])


def resolve_companion_spectrogram_ranges(
    item: Optional[Dict[str, Any]],
    cfg: Optional[Dict[str, Any]],
    state: Any,
    *,
    primary_signature: Optional[Tuple[float, float, float, float]] = None,
) -> List[Dict[str, Any]]:
    """Backward-compatible filtered view of the unified visible ranges."""
    resolved = resolve_visible_spectrogram_ranges(item, cfg, state)
    if primary_signature is None:
        return resolved
    return [
        candidate
        for candidate in resolved
        if (
            round(float(candidate["freq_min_hz"]), 6),
            round(float(candidate["freq_max_hz"]), 6),
            round(float(candidate["win_dur_s"]), 6),
            round(float(candidate["overlap"]), 6),
        )
        != primary_signature
    ]


def resolve_active_spectrogram_range(item, cfg, state):
    """Use the same selected range for the editable plot and its heading."""
    visible = resolve_visible_spectrogram_ranges(item, cfg, state)
    active_id = normalize_spectrogram_range_state(state, cfg).get("active_range_id")
    return next(
        (candidate for candidate in visible if candidate.get("selection_id") == active_id),
        visible[0] if visible else None,
    )
