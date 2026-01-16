import json

from app.utils.format_converters import (
    convert_hydrophonedashboard_to_unified,
    convert_legacy_labeling_to_unified,
    convert_whale_predictions_to_unified,
)


def test_convert_legacy_labeling_to_unified(mock_root):
    labels = {
        "file_a.mat": ["Anthropophony > Vessel"],
        "file_b.mat": ["Other > Ambient sound"],
    }
    data = convert_legacy_labeling_to_unified(labels, str(mock_root / "label" / "mat_files"))
    assert data["version"] == "2.0"
    assert len(data["items"]) == 2
    assert data["summary"]["annotated"] == 2


def test_convert_hydrophonedashboard_to_unified(mock_root):
    labels_path = mock_root / "verify" / "dashboard" / "2026-01-07" / "ICLISTENHF0001" / "labels.json"
    labels_json = json.loads(labels_path.read_text())
    data = convert_hydrophonedashboard_to_unified(labels_json, "2026-01-07", "ICLISTENHF0001",
                                                  str(labels_path.parent / "images"))
    assert data["items"], "Expected converted items"
    assert data["summary"]["total_items"] == len(data["items"])
    assert data["items"][0]["predictions"] is not None


def test_convert_whale_predictions_to_unified(mock_root):
    pred_path = mock_root / "whale" / "predictions.json"
    predictions_json = json.loads(pred_path.read_text())
    data = convert_whale_predictions_to_unified(predictions_json)
    assert len(data["items"]) == 2
    assert data["items"][0]["predictions"] is not None

