"""Bounding-box tag option loading and normalization."""

import os
from typing import Any, Dict, Iterable, List

import yaml


DEFAULT_BBOX_TAG_SET = "fin_whale"
DEFAULT_BBOX_TAG_OPTIONS_FILE = "config/bounding_box_tags.yaml"
DEFAULT_BBOX_TAG_OPTIONS = [
    {"label": "20 Hz", "value": "20Hz"},
    {"label": "30 Hz", "value": "30Hz"},
    {"label": "40 Hz", "value": "40Hz"},
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


def load_bbox_tag_options(repo_root: str, section: Any) -> Dict[str, Any]:
    """Load configured bbox tag options, falling back to the repo default file."""
    cfg = section if isinstance(section, dict) else {}
    active_set = str(cfg.get("active_set") or DEFAULT_BBOX_TAG_SET).strip() or DEFAULT_BBOX_TAG_SET

    inline_options = normalize_bbox_tag_options(cfg.get("options"))
    options_file = cfg.get("options_file") or DEFAULT_BBOX_TAG_OPTIONS_FILE
    if isinstance(options_file, str) and options_file and not os.path.isabs(options_file):
        options_file = os.path.join(repo_root, options_file)

    file_options = []
    file_data = _read_yaml(options_file) if isinstance(options_file, str) else {}
    tag_sets = file_data.get("tag_sets") if isinstance(file_data, dict) else None
    if isinstance(tag_sets, dict):
        file_options = normalize_bbox_tag_options(tag_sets.get(active_set))
    if not file_options:
        file_options = normalize_bbox_tag_options(file_data.get("options"))

    options = inline_options or file_options or list(DEFAULT_BBOX_TAG_OPTIONS)
    return {
        "active_set": active_set,
        "options_file": options_file,
        "options": options,
    }


def get_bbox_tag_options(config: Any) -> List[Dict[str, str]]:
    """Return dropdown options from loaded app config."""
    section = (config or {}).get("bounding_box_tags") if isinstance(config, dict) else None
    if not isinstance(section, dict):
        return list(DEFAULT_BBOX_TAG_OPTIONS)
    return normalize_bbox_tag_options(section.get("options")) or list(DEFAULT_BBOX_TAG_OPTIONS)


def option_values(options: Iterable[Dict[str, str]]) -> set:
    return {
        option.get("value")
        for option in options or []
        if isinstance(option, dict) and isinstance(option.get("value"), str)
    }
