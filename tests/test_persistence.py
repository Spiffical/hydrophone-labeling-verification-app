import json
import shutil
from pathlib import Path

from app.utils.file_io import read_json
from app.utils.label_operations import load_labels
from app.utils.persistence import save_label_mode, save_verify_mode, save_verify_predictions
from app.utils.unified_format_converter import convert_unified_v2_to_internal


FIN_WHALE = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"


def _fin_whale_box(tag="20Hz"):
    return {
        "label": FIN_WHALE,
        "annotation_extent": {
            "type": "time_freq_box",
            "time_start_sec": 1.5,
            "time_end_sec": 3.0,
            "freq_min_hz": 18.0,
            "freq_max_hz": 26.0,
        },
        "tag": tag,
    }


def test_save_label_mode(tmp_path, mock_root):
    src = mock_root / "label" / "labels.json"
    dst = tmp_path / "labels.json"
    shutil.copy(src, dst)

    save_label_mode(str(dst), "new_file.mat", ["Other > Ambient sound"])
    data = load_labels(str(dst))
    assert data["new_file.mat"] == ["Other > Ambient sound"]


def test_save_verify_mode(tmp_path, mock_root):
    src_root = mock_root / "verify" / "dashboard"
    dst_root = tmp_path / "dashboard"
    shutil.copytree(src_root, dst_root)

    save_verify_mode(
        str(dst_root),
        "2026-01-07",
        "ICLISTENHF0001",
        "ICLISTENHF0001_20260107T120500.000Z_20260107T121000.000Z.png",
        ["Anthropophony > Vessel"],
        username="tester",
    )

    labels_path = dst_root / "2026-01-07" / "ICLISTENHF0001" / "labels.json"
    data = json.loads(labels_path.read_text())
    entry = data["ICLISTENHF0001_20260107T120500.000Z_20260107T121000.000Z.png"]
    assert entry["verified_labels"] == ["Anthropophony > Vessel"]
    assert entry["verified_by"] == "tester"
    assert entry["verified_at"]


def test_save_label_mode_persists_bbox_tag(tmp_path):
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps({"schema_version": "2.1", "items": []}))

    save_label_mode(
        str(labels_path),
        "clip-1",
        [FIN_WHALE],
        annotated_by="Reviewer <reviewer@example.com>",
        bbox_annotations=[_fin_whale_box("30Hz")],
    )

    saved = json.loads(labels_path.read_text())
    decision = saved["items"][0]["verifications"][0]["label_decisions"][0]
    assert decision == {
        "label": FIN_WHALE,
        "decision": "added",
        "threshold_used": None,
        "annotation_extent": _fin_whale_box()["annotation_extent"],
        "tag": "30Hz",
    }


def test_save_verify_predictions_persists_and_reloads_bbox_tag(tmp_path):
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(
        json.dumps(
            {
                "schema_version": "2.1",
                "items": [{"item_id": "clip-1", "model_outputs": [], "verifications": []}],
            }
        )
    )
    box = _fin_whale_box()

    save_verify_predictions(
        str(predictions_path),
        "clip-1",
        {
            "verified_at": "2026-07-13T12:00:00Z",
            "verified_by": "Reviewer <reviewer@example.com>",
            "verification_status": "verified",
            "label_decisions": [
                {
                    "label": FIN_WHALE,
                    "decision": "accepted",
                    "threshold_used": 0.5,
                    "annotation_extent": box["annotation_extent"],
                    "tag": box["tag"],
                }
            ],
        },
    )

    saved = json.loads(predictions_path.read_text())
    decision = saved["items"][0]["verifications"][0]["label_decisions"][0]
    assert decision["tag"] == "20Hz"

    reloaded = convert_unified_v2_to_internal(saved)
    assert reloaded["items"][0]["annotations"]["box_annotations"] == [box]
