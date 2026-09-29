"""Box times in clip time: seconds from the start of the clip's audio.

That is what the O3 schema means by ``annotation_extent.time_start_sec`` and
``time_end_sec``, and every verification round the app writes says so with
``annotation_time_reference: "audio_start"``.

Rounds written before that field existed (review builds up to 2026-09-29)
measured box times on the spectrogram's plot axis, which for spectrograms
generated from audio started at the first frame's centre: half an FFT window
into the clip (0.5 s on the 1 s fin whale window). When a review file is read,
those rounds are moved to clip time by half the dashboard's window, so the
boxes stay on the calls they were drawn on. Files on disk are never rewritten:
saves append new rounds, which carry the field.

The offset is half the window each clip's spectrogram was drawn with: the
window pinned in the dashboard config (``annotation_times.legacy_window_s``),
or else the clip's current window. Pin it before changing a dashboard's window
so its older boxes stay where they were drawn. Boxes saved from now on are in
clip time on every plot, whatever its window.
"""

from typing import Any, Dict, Optional

TIME_REFERENCE_KEY = "annotation_time_reference"
AUDIO_START = "audio_start"
_TIME_KEYS = ("time_start_sec", "time_end_sec")


def legacy_box_time_offset(item: Optional[Dict[str, Any]], config: Optional[Dict[str, Any]]) -> float:
    """Seconds from the clip start to where old rounds' plot axis started."""
    if not isinstance(config, dict):
        return 0.0
    pinned = (config.get("annotation_times") or {}).get("legacy_window_s")
    if isinstance(pinned, (int, float)) and not isinstance(pinned, bool) and pinned > 0:
        return round(float(pinned) / 2.0, 6)
    # Imported here: image_processing is heavy and imports app services.
    from app.utils.image_processing import (
        SPECTROGRAM_SOURCE_AUDIO_GENERATED,
        get_item_spectrogram_render_settings,
    )

    settings = get_item_spectrogram_render_settings(item if isinstance(item, dict) else None, config)
    if settings.get("source") != SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        # Existing spectrogram files: their axis is unchanged, so are the boxes.
        return 0.0
    try:
        window = float(settings.get("win_dur_s") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return round(window / 2.0, 6) if window > 0 else 0.0


def shift_extent(extent: Any, offset: float) -> Any:
    """``extent`` with its times moved by ``offset`` seconds (never below 0)."""
    if not offset or not isinstance(extent, dict):
        return extent
    shifted = dict(extent)
    for key in _TIME_KEYS:
        value = extent.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            shifted[key] = round(max(0.0, float(value) + offset), 3)
    return shifted


def _shift_decisions(decisions: Any, offset: float) -> Any:
    if not isinstance(decisions, list):
        return decisions
    return [
        dict(decision, annotation_extent=shift_extent(decision["annotation_extent"], offset))
        if isinstance(decision, dict) and isinstance(decision.get("annotation_extent"), dict)
        else decision
        for decision in decisions
    ]


def _shift_annotation_fields(container: Dict[str, Any], offset: float) -> Dict[str, Any]:
    """Saved label extents and box lists, as older label files kept them."""
    out = dict(container)
    extents = container.get("label_extents")
    if isinstance(extents, dict):
        out["label_extents"] = {label: shift_extent(extent, offset) for label, extent in extents.items()}
    boxes = container.get("box_annotations")
    if isinstance(boxes, list):
        out["box_annotations"] = [
            dict(box, annotation_extent=shift_extent(box["annotation_extent"], offset))
            if isinstance(box, dict) and isinstance(box.get("annotation_extent"), dict)
            else box
            for box in boxes
        ]
    nested = container.get("annotations")
    if isinstance(nested, dict):
        out["annotations"] = _shift_annotation_fields(nested, offset)
    return out


def _has_saved_boxes(container: Dict[str, Any]) -> bool:
    nested = container.get("annotations")
    return bool(
        container.get("label_extents")
        or container.get("box_annotations")
        or (isinstance(nested, dict) and _has_saved_boxes(nested))
    )


def normalize_item(item: Any, config: Optional[Dict[str, Any]]) -> Any:
    """A copy of ``item`` whose rounds and saved annotations use clip time."""
    if not isinstance(item, dict):
        return item
    out = item
    offset = None

    def item_offset() -> float:
        nonlocal offset
        if offset is None:
            offset = legacy_box_time_offset(item, config)
        return offset

    rounds = item.get("verifications")
    if isinstance(rounds, list) and any(
        isinstance(record, dict) and record.get(TIME_REFERENCE_KEY) != AUDIO_START for record in rounds
    ):
        normalized = []
        for record in rounds:
            if isinstance(record, dict) and record.get(TIME_REFERENCE_KEY) != AUDIO_START:
                record = dict(record)
                if "label_decisions" in record:
                    record["label_decisions"] = _shift_decisions(record["label_decisions"], item_offset())
                record[TIME_REFERENCE_KEY] = AUDIO_START
            normalized.append(record)
        out = dict(out, verifications=normalized)

    annotations = item.get("annotations")
    if (
        isinstance(annotations, dict)
        and annotations.get(TIME_REFERENCE_KEY) != AUDIO_START
        and _has_saved_boxes(annotations)
    ):
        shifted = _shift_annotation_fields(annotations, item_offset())
        shifted[TIME_REFERENCE_KEY] = AUDIO_START
        out = dict(out, annotations=shifted)
    return out


def normalize_review_json(data: Any, config: Optional[Dict[str, Any]]) -> Any:
    """A review file (predictions or labels) with every box in clip time.

    Handles the unified format (``items`` with ``verifications``) and older
    label files keyed by file name.
    """
    if not isinstance(data, dict) or not isinstance(config, dict):
        return data
    items = data.get("items")
    if isinstance(items, list):
        return dict(data, items=[normalize_item(item, config) for item in items])

    out = {}
    for key, entry in data.items():
        if (
            isinstance(entry, dict)
            and entry.get(TIME_REFERENCE_KEY) != AUDIO_START
            and _has_saved_boxes(entry)
        ):
            entry = _shift_annotation_fields(entry, legacy_box_time_offset(None, config))
            entry[TIME_REFERENCE_KEY] = AUDIO_START
        out[key] = entry
    return out
