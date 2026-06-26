from pathlib import Path

from app.config import get_config
from app.utils.data_discovery import detect_data_structure
from app.utils.data_loading import load_label_mode, load_verify_mode, load_whale_mode


def test_load_label_mode(mock_config):
    data = load_label_mode(mock_config)
    assert data["items"], "Expected label items"
    assert data["summary"]["total_items"] >= len(data["items"])
    assert data["summary"]["annotated"] >= 1
    assert any(item.get("audio_path") for item in data["items"])
    assert all(Path(item["mat_path"]).exists() for item in data["items"] if item.get("mat_path"))


def test_load_label_mode_audio_only_flat_folder(tmp_path):
    audio_path = tmp_path / "clip_001.wav"
    audio_path.write_bytes(b"placeholder")

    discovery = detect_data_structure(str(tmp_path))
    assert discovery["structure_type"] == "flat"
    assert discovery["audio_folder"] == str(tmp_path)
    assert discovery["audio_count"] == 1

    data = load_label_mode(
        {
            "data": {
                "data_dir": str(tmp_path),
                "structure_type": "flat",
                "audio_folder": str(tmp_path),
            },
            "label": {"folder": None, "audio_folder": str(tmp_path), "output_file": None},
        }
    )

    assert len(data["items"]) == 1
    assert data["items"][0]["item_id"] == "clip_001"
    assert data["items"][0]["audio_path"] == str(audio_path)
    assert data["items"][0]["mat_path"] is None


def test_get_config_accepts_startup_data_and_fft_params(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "run.py",
            "--mode",
            "label",
            "--data-dir",
            str(tmp_path),
            "--spectrogram-source",
            "audio_generated",
            "--fft-window-sec",
            "2.5",
            "--fft-overlap",
            "0.75",
            "--freq-min-hz",
            "10",
            "--freq-max-hz",
            "250",
        ],
    )

    config = get_config()

    assert config["mode"] == "label"
    assert config["data"]["data_dir"] == str(tmp_path)
    assert config["spectrogram_render"] == {
        "source": "audio_generated",
        "win_dur_s": 2.5,
        "overlap": 0.75,
        "freq_min_hz": 10.0,
        "freq_max_hz": 250.0,
    }


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

