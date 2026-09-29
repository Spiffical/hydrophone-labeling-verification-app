"""Bounding-box tag option loading and normalization.

Tags are call types, so each tag set belongs to a species: a box is tagged
from the set whose species label is the box's label or one of its ancestors.
Boxes of other species have no tags to choose from. A set without a species
label applies to every box (inline ``options`` in older configs).
"""

import os
from typing import Any, Dict, Iterable, List, Optional

import yaml

from app.services.label_attributes import FIN_WHALE_LABEL
from taxonomy.hierarchical_labels import canonicalize_prediction_label


DEFAULT_BBOX_TAG_SET = "fin_whale"
DEFAULT_BBOX_TAG_OPTIONS_FILE = "config/bounding_box_tags.yaml"
DEFAULT_BBOX_TAG_OPTIONS = [
    {"label": "20 Hz", "value": "20Hz"},
    {"label": "30 Hz", "value": "30Hz"},
    {"label": "40 Hz", "value": "40Hz"},
]
DEFAULT_BBOX_TAG_SETS = [
    {"name": DEFAULT_BBOX_TAG_SET, "label": FIN_WHALE_LABEL, "options": DEFAULT_BBOX_TAG_OPTIONS},
]


def normalize_bbox_tag_options(raw_options: Any) -> List[Dict[str, str]]:
    """Normalize YAML/user config into Dash dropdown options."""
    if not isinstance(raw_options, list):
        return []

    normalized: List[Dict[str, str]] = []
    seen = set()
    for entry in raw_options:
        label = None
        value = None
        if isinstance(entry, str):
            value = entry.strip()
            label = value
        elif isinstance(entry, dict):
            raw_value = entry.get("value") or entry.get("id") or entry.get("name") or entry.get("label")
            raw_label = entry.get("label") or raw_value
            value = str(raw_value).strip() if raw_value is not None else ""
            label = str(raw_label).strip() if raw_label is not None else value

        if not value or value in seen:
            continue
        normalized.append({"label": label or value, "value": value})
        seen.add(value)
    return normalized


def _read_yaml(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r") as file:
        loaded = yaml.safe_load(file) or {}
    return loaded if isinstance(loaded, dict) else {}


def _species_label(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return canonicalize_prediction_label(value.strip()) or value.strip()


def _tag_set(name: str, raw: Any) -> Optional[Dict[str, Any]]:
    """One tag set: ``{label, options}`` or, in older files, a bare option list."""
    if isinstance(raw, dict):
        label, options = _species_label(raw.get("label")), normalize_bbox_tag_options(raw.get("options"))
    else:
        label, options = None, normalize_bbox_tag_options(raw)
    return {"name": name, "label": label, "options": options} if options else None


def _active_set_names(cfg: Dict[str, Any]) -> List[str]:
    raw = cfg.get("active_sets", cfg.get("active_set"))
    names = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    names = [str(name).strip() for name in names if str(name or "").strip()]
    return names or [DEFAULT_BBOX_TAG_SET]


def _all_options(tag_sets: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    seen = set()
    for tag_set in tag_sets:
        for option in tag_set["options"]:
            if option["value"] not in seen:
                merged.append(dict(option))
                seen.add(option["value"])
    return merged


def load_bbox_tag_options(repo_root: str, section: Any) -> Dict[str, Any]:
    """Load configured bbox tag sets, falling back to the repo default file."""
    cfg = section if isinstance(section, dict) else {}
    active_sets = _active_set_names(cfg)

    options_file = cfg.get("options_file") or DEFAULT_BBOX_TAG_OPTIONS_FILE
    if isinstance(options_file, str) and options_file and not os.path.isabs(options_file):
        options_file = os.path.join(repo_root, options_file)
    file_data = _read_yaml(options_file) if isinstance(options_file, str) else {}

    inline = _tag_set("inline", {"label": cfg.get("label"), "options": cfg.get("options")})
    if inline:
        tag_sets = [inline]
    else:
        file_sets = file_data.get("tag_sets") if isinstance(file_data.get("tag_sets"), dict) else {}
        tag_sets = [
            tag_set
            for tag_set in (_tag_set(name, file_sets.get(name)) for name in active_sets)
            if tag_set
        ]
        if not tag_sets:
            legacy = _tag_set(active_sets[0], file_data.get("options"))
            tag_sets = [legacy] if legacy else []
    if not tag_sets:
        tag_sets = [dict(tag_set, options=list(tag_set["options"])) for tag_set in DEFAULT_BBOX_TAG_SETS]

    return {
        "active_set": active_sets[0],
        "active_sets": active_sets,
        "options_file": options_file,
        "tag_sets": tag_sets,
        # Every option in any set, for callers that only need the vocabulary.
        "options": _all_options(tag_sets),
        # Bulk tagging suits expert reviewers; volunteer deployments can switch it off.
        "bulk_tagging": cfg.get("bulk_tagging", True) is not False,
    }


def get_bbox_tag_sets(config: Any) -> List[Dict[str, Any]]:
    """Return ``[{name, label, options}]`` from loaded app config."""
    section = (config or {}).get("bounding_box_tags") if isinstance(config, dict) else None
    if not isinstance(section, dict):
        return [dict(tag_set, options=list(tag_set["options"])) for tag_set in DEFAULT_BBOX_TAG_SETS]
    loaded = section.get("tag_sets")
    if isinstance(loaded, list):
        tag_sets = [
            _tag_set(str(entry.get("name") or "set"), entry)
            for entry in loaded
            if isinstance(entry, dict)
        ]
        tag_sets = [tag_set for tag_set in tag_sets if tag_set]
        if tag_sets:
            return tag_sets
    inline = _tag_set("inline", {"label": section.get("label"), "options": section.get("options")})
    if inline:
        return [inline]
    return [dict(tag_set, options=list(tag_set["options"])) for tag_set in DEFAULT_BBOX_TAG_SETS]


def get_bbox_tag_options(config: Any) -> List[Dict[str, str]]:
    """Return every tag option (all species) from loaded app config."""
    return _all_options(get_bbox_tag_sets(config))


def _label_parts(label: Any) -> List[str]:
    return [part.strip().casefold() for part in str(label or "").split(">") if part.strip()]


def tag_set_applies(tag_set: Dict[str, Any], label: Any) -> bool:
    """Mirrors labelMatches in bbox_list.js."""
    root = _label_parts(tag_set.get("label"))
    if not root:
        return True
    parts = _label_parts(label)
    return parts[: len(root)] == root or root[-1] in parts


def tag_options_for_label(tag_sets: Any, label: Any) -> List[Dict[str, str]]:
    """Tag options for a box with ``label``: the first set whose species it belongs to."""
    for tag_set in tag_sets if isinstance(tag_sets, list) else []:
        if isinstance(tag_set, dict) and tag_set_applies(tag_set, label):
            return normalize_bbox_tag_options(tag_set.get("options"))
    return []


def get_bbox_bulk_tagging(config: Any) -> bool:
    """Return whether the box list offers multi-select tagging."""
    section = (config or {}).get("bounding_box_tags") if isinstance(config, dict) else None
    if not isinstance(section, dict):
        return True
    return section.get("bulk_tagging", True) is not False


def option_values(options: Iterable[Dict[str, str]]) -> set:
    return {
        option.get("value")
        for option in options or []
        if isinstance(option, dict) and isinstance(option.get("value"), str)
    }
