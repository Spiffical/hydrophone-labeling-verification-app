import json
import shutil
from pathlib import Path

from app.utils.file_io import read_json
from app.utils.persistence import save_label_mode, save_verify_mode


def test_save_label_mode(tmp_path, mock_root):
    src = mock_root / "label" / "labels.json"
    dst = tmp_path / "labels.json"
    shutil.copy(src, dst)

    save_label_mode(str(dst), "new_file.mat", ["Other > Ambient sound"])
    data = read_json(str(dst))
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

