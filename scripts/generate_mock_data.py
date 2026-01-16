import json
import os
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import matplotlib.pyplot as plt
import scipy.io as sio
import soundfile as sf


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_spectrogram_struct(psd, freq, time):
    spect_data = np.empty((1, 1), dtype=[("PSD", "O"), ("frequency", "O"), ("time", "O")])
    spect_data["PSD"][0, 0] = psd
    spect_data["frequency"][0, 0] = freq
    spect_data["time"][0, 0] = time
    return spect_data


def generate_label_data(root: Path):
    mat_dir = root / "label" / "mat_files"
    audio_dir = root / "label" / "audio"
    mat_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    base_ts = "20260107T120000.000Z"
    filenames = [
        f"ICLISTENHF0001_{base_ts}_20260107T120500.000Z-spect_plotRes.mat",
        "ICLISTENHF0001_20260107T120500.000Z_20260107T121000.000Z-spect_plotRes.mat",
        "ICLISTENHF0001_20260107T121000.000Z_20260107T121500.000Z-spect_plotRes.mat",
    ]

    rng = np.random.default_rng(42)
    freq = np.linspace(0, 1000, 64)
    time = np.linspace(0, 1, 128)

    for idx, name in enumerate(filenames):
        psd = rng.random((64, 128)) * 100 + 40
        spect_data = _make_spectrogram_struct(psd, freq, time)
        sio.savemat(mat_dir / name, {"SpectData": spect_data})

        audio_name = f"ICLISTENHF0001_20260107T12{idx}000.000Z.flac"
        sample_rate = 8000
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        tone = 0.1 * np.sin(2 * np.pi * (200 + 50 * idx) * t)
        sf.write(audio_dir / audio_name, tone, sample_rate)

    labels = {
        filenames[0]: ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"],
        filenames[1]: ["Anthropophony > Vessel"],
    }

    with open(root / "label" / "labels.json", "w") as f:
        json.dump(labels, f, indent=2, sort_keys=True)


def _save_image(path: Path, title: str):
    fig, ax = plt.subplots(figsize=(2.5, 1.6))
    ax.imshow(np.random.random((64, 128)), aspect="auto", cmap="viridis")
    ax.set_title(title, fontsize=8)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def generate_verify_data(root: Path):
    dash_root = root / "verify" / "dashboard" / "2026-01-07" / "ICLISTENHF0001"
    image_dir = dash_root / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    image_files = [
        "ICLISTENHF0001_20260107T120000.000Z_20260107T120500.000Z.png",
        "ICLISTENHF0001_20260107T120500.000Z_20260107T121000.000Z.png",
    ]

    for name in image_files:
        _save_image(image_dir / name, name)

    labels = {
        image_files[0]: {
            "hydrophone": "ICLISTENHF0001",
            "predicted_labels": ["Anthropophony > Vessel"],
            "probabilities": {"Anthropophony > Vessel": 0.82},
            "t0": "2026-01-07T12:00:00Z",
            "t1": "2026-01-07T12:05:00Z",
            "verified_labels": ["Anthropophony > Vessel"],
            "verified_by": "mock_user",
            "verified_at": _now_iso(),
            "notes": "",
        },
        image_files[1]: {
            "hydrophone": "ICLISTENHF0001",
            "predicted_labels": ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"],
            "probabilities": {"Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale": 0.91},
            "t0": "2026-01-07T12:05:00Z",
            "t1": "2026-01-07T12:10:00Z",
            "verified_labels": None,
            "verified_by": None,
            "verified_at": None,
            "notes": "",
        },
    }

    with open(dash_root / "labels.json", "w") as f:
        json.dump(labels, f, indent=2, sort_keys=True)


def generate_whale_data(root: Path):
    whale_root = root / "whale"
    spec_dir = whale_root / "spectrograms"
    audio_dir = whale_root / "audio"
    spec_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    spec_files = [spec_dir / "segment_001.png", spec_dir / "segment_002.png"]
    for spec in spec_files:
        _save_image(spec, spec.name)

    sample_rate = 8000
    duration = 1.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    whale_audio = 0.1 * np.sin(2 * np.pi * 120 * t)
    audio_path = audio_dir / "segment_001.wav"
    sf.write(audio_path, whale_audio, sample_rate)

    predictions = {
        "version": "1.0",
        "created_at": _now_iso(),
        "model": {
            "model_id": "sha256-mock",
            "architecture": "resnet18",
            "checkpoint_path": "/mock/checkpoint.pt",
        },
        "data_source": {
            "device_code": "ICLISTENHF0001",
            "date_from": "2026-01-07T12:00:00Z",
            "date_to": "2026-01-07T12:10:00Z",
        },
        "segments": [
            {
                "segment_id": "segment_001",
                "max_confidence": 0.93,
                "spectrogram_path": str(spec_files[0]),
                "audio_path": str(audio_path),
                "mat_path": None,
                "audio_timestamp": "2026-01-07T12:00:00Z",
                "windows": [
                    {"window_start": 0, "window_time_start": 0, "window_time_end": 5, "confidence": 0.93}
                ],
                "num_positive": {"0.5": 1},
            },
            {
                "segment_id": "segment_002",
                "max_confidence": 0.31,
                "spectrogram_path": str(spec_files[1]),
                "audio_path": None,
                "mat_path": None,
                "audio_timestamp": "2026-01-07T12:05:00Z",
                "windows": [],
                "num_positive": {"0.5": 0},
            },
        ],
    }

    with open(whale_root / "predictions.json", "w") as f:
        json.dump(predictions, f, indent=2, sort_keys=True)


def main():
    root = Path(__file__).resolve().parents[1] / "data" / "mock"
    root.mkdir(parents=True, exist_ok=True)

    generate_label_data(root)
    generate_verify_data(root)
    generate_whale_data(root)

    print(f"Mock data generated at {root}")


if __name__ == "__main__":
    main()

