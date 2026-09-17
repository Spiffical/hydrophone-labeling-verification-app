"""Duplicate item ids: merged inference passes and overlapping daily batches."""

from app.utils.unified_format_converter import (
    convert_unified_v2_to_internal,
    merge_duplicate_item_records,
)


def _record(item_id, score, verifications=None):
    return {
        "item_id": item_id,
        "data_source_id": "ICLISTENHF6324",
        "audio_start_time": "2026-02-02T18:10:00.000Z",
        "audio_end_time": "2026-02-02T18:15:00.000Z",
        "model_outputs": [{"class_hierarchy": "Other > Ambient sound", "score": score}],
        "verifications": verifications or [],
        "paths": {
            "spectrogram_mat_path": f"ICLISTENHF6324/onc_spectrograms/{item_id}.mat",
            "audio_path": f"ICLISTENHF6324/audio/{item_id}.flac",
        },
    }


def _verification(reviewer, decision="accepted"):
    return {
        "verified_by": reviewer,
        "verified_at": "2026-02-03T20:00:00Z",
        "label_decisions": [{"label": "Other > Ambient sound", "decision": decision}],
    }


def test_merge_keeps_one_record_per_id_with_last_pass_outputs_and_all_verifications():
    first = _record("clip-a", 0.90, [_verification("alice")])
    second = _record("clip-a", 0.93)
    other = _record("clip-b", 0.10)

    merged = merge_duplicate_item_records([first, other, second])

    assert [record["item_id"] for record in merged] == ["clip-a", "clip-b"]
    assert merged[0]["model_outputs"][0]["score"] == 0.93
    assert merged[0]["verifications"] == [_verification("alice")]


def test_merge_unions_verifications_and_drops_exact_repeats():
    shared = _verification("alice")
    first = _record("clip-a", 0.90, [shared])
    second = _record("clip-a", 0.91, [shared, _verification("bob", "rejected")])

    merged = merge_duplicate_item_records([first, second])

    assert len(merged) == 1
    assert merged[0]["verifications"] == [shared, _verification("bob", "rejected")]


def test_merge_passes_through_records_without_ids():
    anonymous = {"model_outputs": []}
    merged = merge_duplicate_item_records([anonymous, _record("clip-a", 0.5), anonymous])
    assert len(merged) == 3


def test_converter_shows_a_twice_listed_clip_once_and_keeps_its_review():
    payload = {
        "schema_version": "2.1",
        "model": {"model_id": "sha256-test"},
        "items": [
            _record("clip-a", 0.90, [_verification("alice")]),
            _record("clip-b", 0.20),
            _record("clip-a", 0.93),
        ],
    }

    data = convert_unified_v2_to_internal(payload)

    assert [item["item_id"] for item in data["items"]] == ["clip-a", "clip-b"]
    clip_a = data["items"][0]
    assert clip_a["predictions"]["model_outputs"][0]["score"] == 0.93
    assert clip_a["annotations"]["verified"] is True
    assert clip_a["annotations"]["annotated_by"] == "alice"
    assert data["summary"]["total_items"] == 2


def _write_day(root, date, records):
    import json

    day = root / date
    (day / "ICLISTENHF6324" / "onc_spectrograms").mkdir(parents=True)
    (day / "ICLISTENHF6324" / "audio").mkdir(parents=True)
    for record in records:
        (day / record["paths"]["spectrogram_mat_path"]).write_bytes(b"")
    (day / "predictions.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1",
                "model": {"model_id": "sha256-test"},
                "data_sources": [{"id": "ICLISTENHF6324", "device_code": "ICLISTENHF6324"}],
                "items": records,
            }
        )
    )


def test_loader_collapses_repeated_ids_within_a_day_and_across_overlapping_days(tmp_path):
    from app.utils.data_loading import load_dataset

    root = tmp_path / "daily-data-pipeline"
    shared = _record("clip-shared", 0.40)
    _write_day(root, "2026-02-02", [_record("clip-early", 0.10), shared])
    _write_day(
        root,
        "2026-02-03",
        [
            _record("clip-dup", 0.90, [_verification("alice")]),
            shared,
            _record("clip-dup", 0.93),
        ],
    )
    config = {
        "data": {
            "data_dir": str(root),
            "structure_type": "hierarchical",
            "spectrogram_folder_names": ["onc_spectrograms"],
            "audio_folder_names": ["audio"],
        },
        "verify": {"dashboard_root": str(root), "hydrophone": "ICLISTENHF6324"},
    }

    single = load_dataset(config, "verify", date_str="2026-02-03", hydrophone="ICLISTENHF6324")
    single_ids = [item["item_id"] for item in single["items"]]
    assert sorted(single_ids) == ["clip-dup", "clip-shared"]
    clip_dup = next(item for item in single["items"] if item["item_id"] == "clip-dup")
    assert clip_dup["predictions"]["model_outputs"][0]["score"] == 0.93
    assert clip_dup["annotations"]["verified"] is True

    all_dates = load_dataset(config, "verify", date_str="__all__", hydrophone="ICLISTENHF6324")
    all_ids = [item["item_id"] for item in all_dates["items"]]
    assert sorted(all_ids) == ["clip-dup", "clip-early", "clip-shared"]
    assert all_dates["summary"]["total_items"] == 3
    assert all_dates["summary"]["duplicates_removed"] == 1
