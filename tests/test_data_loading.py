from pathlib import Path

from app.utils.data_loading import load_label_mode, load_verify_mode, load_whale_mode


def test_load_label_mode(mock_config):
    data = load_label_mode(mock_config)
    assert data["items"], "Expected label items"
    assert data["summary"]["total_items"] >= len(data["items"])
    assert data["summary"]["annotated"] >= 1
    assert any(item.get("audio_path") for item in data["items"])
    assert all(Path(item["mat_path"]).exists() for item in data["items"] if item.get("mat_path"))


def test_load_verify_mode(mock_config):
    data = load_verify_mode(mock_config)
    assert data["items"], "Expected verify items"
    assert data["summary"]["total_items"] == len(data["items"])
    first = data["items"][0]
    assert first.get("predictions") is not None
    assert first.get("spectrogram_path")


def test_load_whale_mode(mock_config):
    data = load_whale_mode(mock_config)
    assert data["items"], "Expected whale items"
    assert data["summary"]["total_items"] == len(data["items"])
    assert any(item.get("predictions") for item in data["items"])

