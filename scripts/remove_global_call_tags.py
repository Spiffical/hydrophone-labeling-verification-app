#!/usr/bin/env python3
"""Remove obsolete free-floating call tags without changing review records."""

import argparse
import json
from copy import deepcopy
from pathlib import Path


def remove_global_call_tags(data):
    updated = deepcopy(data)
    stats = {"items": 0, "model_tag_outputs_removed": 0, "manual_global_tags_found": 0}
    for item in updated.get("items") or []:
        if not isinstance(item, dict):
            continue
        stats["items"] += 1
        raw_tags = item.pop("tag_outputs", None)
        if isinstance(raw_tags, list):
            stats["model_tag_outputs_removed"] += len(raw_tags)
        predictions = item.get("predictions")
        if isinstance(predictions, dict):
            raw_tags = predictions.pop("tag_outputs", None)
            if isinstance(raw_tags, list):
                stats["model_tag_outputs_removed"] += len(raw_tags)
        annotations = item.get("annotations")
        if isinstance(annotations, dict) and annotations.get("spectrogram_tags"):
            stats["manual_global_tags_found"] += len(annotations["spectrogram_tags"])
        for verification in item.get("verifications") or []:
            if isinstance(verification, dict) and verification.get("spectrogram_tags"):
                stats["manual_global_tags_found"] += len(verification["spectrogram_tags"])

    if stats["manual_global_tags_found"]:
        raise ValueError(
            "Refusing to remove data: manual whole-spectrogram tags are present. "
            "Migrate them to label_attributes explicitly."
        )

    integration = updated.get("e170_integration")
    if isinstance(integration, dict):
        integration.pop("scoped_call_tags", None)
        integration["label_attribute_policy"] = {
            "global_call_tags_enabled": False,
            "species_specific_attributes": ["Killer whale", "Fin whale"],
            "machine_attributes_present": False,
        }
    return updated, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    original = json.loads(args.input_json.read_text())
    updated, stats = remove_global_call_tags(original)
    args.output_json.write_text(json.dumps(updated, indent=2) + "\n")
    print(json.dumps(stats, sort_keys=True))


if __name__ == "__main__":
    main()
