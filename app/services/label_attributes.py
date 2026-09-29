"""Controlled, species-specific attributes attached to taxonomy labels."""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from taxonomy.hierarchical_labels import canonicalize_prediction_label, is_valid_path


KILLER_WHALE_LABEL = (
    "Biophony > Marine mammal > Cetacean > Toothed whale > Killer whale"
)
FIN_WHALE_LABEL = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"

CALL_TYPE_DEFINITIONS = {
    KILLER_WHALE_LABEL: [
        {"value": "echolocation_click", "display": "Echolocation clicks"},
        {"value": "whistle", "display": "Whistles"},
        {"value": "pulsed_call", "display": "Pulsed calls"},
    ],
    FIN_WHALE_LABEL: [
        {"value": "20Hz", "display": "20 Hz"},
        {"value": "30Hz", "display": "30 Hz"},
        {"value": "40Hz", "display": "40 Hz"},
    ],
}


def _canonical_label(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    label = canonicalize_prediction_label(value.strip())
    if not label or not is_valid_path(label.split(" > ")):
        return None
    return label


def attribute_owner_label(label: Any) -> Optional[str]:
    """Return the species root whose call-type vocabulary applies to ``label``."""
    canonical = _canonical_label(label)
    if not canonical:
        return None
    for owner in CALL_TYPE_DEFINITIONS:
        if canonical == owner or canonical.startswith(f"{owner} > "):
            return owner
    return None


def label_attribute_options(label: Any) -> List[Dict[str, str]]:
    owner = attribute_owner_label(label)
    return [dict(entry, label=entry["display"]) for entry in CALL_TYPE_DEFINITIONS.get(owner, [])]


def supports_call_type_attributes(label: Any) -> bool:
    return bool(attribute_owner_label(label))


def _definition_for(label: str, value: Any) -> Optional[Dict[str, str]]:
    text = str(value or "").strip()
    if not text:
        return None
    for definition in label_attribute_options(label):
        if text == definition["value"] or text.casefold() == definition["display"].casefold():
            return definition
    return None


def normalize_label_attribute_record(
    entry: Any,
    *,
    default_source: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    taxonomy_label = _canonical_label(entry.get("taxonomy_label") or entry.get("label"))
    if not taxonomy_label or not supports_call_type_attributes(taxonomy_label):
        return None
    attribute_type = str(entry.get("attribute_type") or "call_type").strip().lower()
    if attribute_type != "call_type":
        return None
    definition = _definition_for(
        taxonomy_label,
        entry.get("value") or entry.get("attribute_value") or entry.get("tag_id"),
    )
    if not definition:
        return None
    source = str(entry.get("source") or default_source).strip().lower()
    scope = str(entry.get("scope") or "clip").strip().lower()
    if source not in {"human", "model"} or scope != "clip":
        return None

    normalized: Dict[str, Any] = {
        "taxonomy_label": taxonomy_label,
        "attribute_type": "call_type",
        "value": definition["value"],
        "display": definition["display"],
        "source": source,
        "scope": "clip",
    }
    score = entry.get("score")
    if isinstance(score, (int, float)):
        normalized["score"] = float(score)
    for key in ("model_id", "annotated_by", "annotated_at"):
        field = entry.get(key)
        if isinstance(field, str) and field.strip():
            normalized[key] = field.strip()
    return normalized


def normalize_label_attributes(entries: Any, *, default_source: str) -> List[Dict[str, Any]]:
    normalized = []
    seen = set()
    for entry in entries if isinstance(entries, list) else []:
        record = normalize_label_attribute_record(entry, default_source=default_source)
        if not record:
            continue
        key = (
            record["taxonomy_label"],
            record["attribute_type"],
            record["value"],
            record["source"],
        )
        if key in seen:
            continue
        normalized.append(record)
        seen.add(key)
    return normalized


def prune_label_attributes(
    entries: Any,
    active_labels: Iterable[Any],
    *,
    default_source: str,
) -> List[Dict[str, Any]]:
    active = {_canonical_label(label) for label in active_labels or []}
    active.discard(None)
    return [
        record
        for record in normalize_label_attributes(entries, default_source=default_source)
        if record["taxonomy_label"] in active
    ]


def model_label_attributes(item: Any, label: Optional[str] = None) -> List[Dict[str, Any]]:
    predictions = item.get("predictions") if isinstance(item, dict) else {}
    predictions = predictions if isinstance(predictions, dict) else {}
    records = normalize_label_attributes(predictions.get("label_attributes"), default_source="model")
    return [record for record in records if not label or record["taxonomy_label"] == label]


def human_label_attributes(item: Any, label: Optional[str] = None) -> List[Dict[str, Any]]:
    annotations = item.get("annotations") if isinstance(item, dict) else {}
    annotations = annotations if isinstance(annotations, dict) else {}
    if "label_attributes" in annotations:
        raw = annotations.get("label_attributes")
    else:
        raw = None
        for verification in reversed(item.get("verifications") or [] if isinstance(item, dict) else []):
            if isinstance(verification, dict) and "label_attributes" in verification:
                raw = verification.get("label_attributes")
                break
    records = normalize_label_attributes(raw, default_source="human")
    return [record for record in records if not label or record["taxonomy_label"] == label]


def selected_human_attribute_values(item: Any, label: str) -> List[str]:
    return [record["value"] for record in human_label_attributes(item, label)]


def replace_human_call_type_attributes(
    entries: Any,
    taxonomy_label: str,
    values: Iterable[Any],
    *,
    active_labels: Iterable[Any],
    annotated_by: Optional[str] = None,
    annotated_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    canonical = _canonical_label(taxonomy_label)
    active = {_canonical_label(label) for label in active_labels or []}
    active.discard(None)
    if not canonical or canonical not in active or not supports_call_type_attributes(canonical):
        return prune_label_attributes(entries, active, default_source="human")

    retained = [
        record
        for record in prune_label_attributes(entries, active, default_source="human")
        if record["taxonomy_label"] != canonical or record["attribute_type"] != "call_type"
    ]
    now = annotated_at or datetime.now(timezone.utc).isoformat()
    seen = set()
    for value in values or []:
        definition = _definition_for(canonical, value)
        if not definition or definition["value"] in seen:
            continue
        record: Dict[str, Any] = {
            "taxonomy_label": canonical,
            "attribute_type": "call_type",
            "value": definition["value"],
            "display": definition["display"],
            "source": "human",
            "scope": "clip",
            "annotated_at": now,
        }
        if annotated_by:
            record["annotated_by"] = annotated_by
        retained.append(record)
        seen.add(definition["value"])
    return retained
