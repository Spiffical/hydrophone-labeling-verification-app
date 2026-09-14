"""Helpers for audio controls shared across modal navigation."""

DEFAULT_AMPLIFICATION = 1.0
MAX_AMPLIFICATION = 50.0


def _clamp_amplification(value):
    try:
        return max(DEFAULT_AMPLIFICATION, min(MAX_AMPLIFICATION, float(value)))
    except (TypeError, ValueError):
        return DEFAULT_AMPLIFICATION


def get_modal_amplification(settings):
    if not isinstance(settings, dict):
        return DEFAULT_AMPLIFICATION
    return _clamp_amplification(settings.get("gain", DEFAULT_AMPLIFICATION))


def set_modal_amplification(settings, value):
    updated = dict(settings or {})
    updated["gain"] = _clamp_amplification(value)
    updated.pop("gain_by_item", None)
    return updated
