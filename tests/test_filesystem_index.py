import os
from collections import Counter
from unittest.mock import patch

from app.utils.filesystem_index import DirectoryIndex
from app.utils.data_loading import _enrich_items_with_audio_paths
from app.utils.audio_matching import find_matching_audio_files
from app.utils.unified_format_converter import convert_unified_v2_to_internal


def test_thousands_of_path_checks_list_each_directory_once(tmp_path):
    for i in range(100):
        (tmp_path / f'clip-{i}.wav').touch()
    counts = Counter()
    original = os.scandir

    def counted(path):
        counts[str(path)] += 1
        return original(path)

    with patch('app.utils.filesystem_index.os.scandir', side_effect=counted):
        index = DirectoryIndex()
        for _ in range(10):
            for i in range(100):
                assert index.exists(tmp_path / f'clip-{i}.wav')
            assert not index.exists(tmp_path / 'missing.wav')
        assert len(index.files(str(tmp_path), {'.wav'})) == 100
    assert counts[str(tmp_path)] == 1


def test_new_index_sees_added_and_removed_files(tmp_path):
    old = tmp_path / 'old.wav'
    old.touch()
    first = DirectoryIndex()
    assert first.exists(old)
    old.unlink()
    new = tmp_path / 'new.wav'
    new.touch()
    fresh = DirectoryIndex()
    assert not fresh.exists(old)
    assert fresh.exists(new)


def test_broken_symlinks_and_file_parents_do_not_exist(tmp_path):
    valid = tmp_path / 'audio.wav'
    valid.touch()
    (tmp_path / 'valid-link').symlink_to(valid)
    (tmp_path / 'broken-link').symlink_to(tmp_path / 'missing')
    index = DirectoryIndex()
    assert index.exists(tmp_path / 'valid-link')
    assert not index.exists(tmp_path / 'broken-link')
    assert not index.exists(valid / 'child')
    assert not index.exists(tmp_path / 'absent' / 'child')


def test_unlistable_parent_falls_back_to_stat(tmp_path):
    audio = tmp_path / 'audio.wav'
    audio.touch()
    with patch('app.utils.filesystem_index.os.scandir', side_effect=PermissionError):
        assert DirectoryIndex().exists(audio)
        assert not DirectoryIndex().exists(tmp_path / 'missing.wav')


def test_audio_enrichment_preserves_matching_and_segment_isolation(tmp_path):
    audio_dir = tmp_path / 'audio'
    audio_dir.mkdir()
    for name in ('H_20260901T000000.000Z.flac', 'H_20260901T000500.000Z.wav', 'exact.ogg'):
        (audio_dir / name).touch()
    spec = 'H_20260901T000500.000Z_20260901T001000.000Z-spect_plotRes.mat'
    expected = find_matching_audio_files(spec, str(audio_dir))[0]
    items = [
        {'item_id': 'exact'},
        {'item_id': 'timestamp', 'mat_path': spec},
        {'item_id': 'H_20260901T000500.000Z_seg004'},
        {'item_id': 'relative', 'audio_path': 'audio/exact.ogg'},
    ]
    # Once directory listings are supplied, the matcher must not scan via glob.
    with patch('app.utils.audio_matching.glob.glob', side_effect=AssertionError('Repeated directory scan')):
        _enrich_items_with_audio_paths(items, str(audio_dir), str(tmp_path))
    assert items[0]['audio_path'] == str(audio_dir / 'exact.ogg')
    assert items[1]['audio_path'] == expected
    assert not items[2].get('audio_path')
    assert items[3]['audio_path'] == str(audio_dir / 'exact.ogg')


def test_converter_keeps_original_missing_paths_with_index(tmp_path):
    (tmp_path / 'existing.wav').touch()
    source = {'schema_version': '2.1', 'items': [
        {'item_id': 'clip', 'paths': {'audio_path': 'existing.wav', 'spectrogram_mat_path': 'missing.mat'}}
    ]}
    # Compare complete conversion to retain path resolution and annotation semantics.
    expected = convert_unified_v2_to_internal(source, str(tmp_path))
    actual = convert_unified_v2_to_internal(source, str(tmp_path), path_exists=DirectoryIndex().exists)
    actual.pop("created_at")
    expected.pop("created_at")
    assert actual == expected
    assert actual["items"][0]["audio_path"] == str(tmp_path / "existing.wav")
    assert actual["items"][0]["mat_path"] == "missing.mat"
