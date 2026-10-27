"""The cached MP3 playback transport on hosts without ffmpeg (oncvm): libsndfile
encodes the MP3 instead (app/utils/audio_transport.py)."""

import numpy as np
import pytest
import soundfile as sf

from app.main import create_app, set_audio_roots
from app.utils import audio_transport
from app.utils.audio_request import encode_audio_request
from app.utils.audio_transport import resolve_audio_delivery_path

pytestmark = pytest.mark.skipif("MP3" not in sf.available_formats(), reason="libsndfile without MP3")


def _write_flac(path, seconds=1.0, rate=256000):
    t = np.arange(int(seconds * rate)) / rate
    audio = 0.3 * np.sin(2 * np.pi * 20.0 * t) + 0.01 * np.random.default_rng(0).standard_normal(t.size)
    sf.write(str(path), audio.astype("float32"), rate, subtype="PCM_24", format="FLAC")


@pytest.fixture
def no_ffmpeg(monkeypatch):
    monkeypatch.setattr(audio_transport.shutil, "which", lambda name: None)


def test_mp3_transport_encodes_with_libsndfile_without_ffmpeg(tmp_path, no_ffmpeg):
    source = tmp_path / "clip.flac"
    _write_flac(source)
    delivered = resolve_audio_delivery_path(str(source), transport="mp3_cached", mp3_bitrate="128k",
                                            cache_dir=str(tmp_path / "cache"))
    assert delivered.endswith(".mp3") and str(tmp_path / "cache") in delivered
    info = sf.info(delivered)
    # 256 kHz is above what MP3 allows: resampled to 48 kHz, the length kept.
    assert info.samplerate == 48000 and abs(info.duration - 1.0) < 0.1
    assert source.stat().st_size > 4 * (tmp_path / "cache" / delivered.split("/")[-1]).stat().st_size
    # A second request is served from the cache.
    assert resolve_audio_delivery_path(str(source), transport="mp3_cached", mp3_bitrate="128k",
                                       cache_dir=str(tmp_path / "cache")) == delivered


def test_long_files_are_served_as_they_are_without_ffmpeg(tmp_path, no_ffmpeg, monkeypatch):
    monkeypatch.setattr(audio_transport, "_SOUNDFILE_MAX_SECONDS", 0.5)
    source = tmp_path / "clip.flac"
    _write_flac(source)
    delivered = resolve_audio_delivery_path(str(source), transport="mp3_cached", mp3_bitrate="128k",
                                            cache_dir=str(tmp_path / "cache"))
    assert delivered == str(source)


def test_audio_route_serves_mp3_without_ffmpeg(tmp_path, no_ffmpeg):
    source = tmp_path / "clip.flac"
    _write_flac(source)
    config = {
        "mode": "label",
        "label": {"folder": str(tmp_path), "audio_folder": str(tmp_path), "output_file": str(tmp_path / "labels.json")},
        "display": {"items_per_page": 25, "colormap": "default", "y_axis_scale": "linear"},
        "cache": {"max_size": 25},
        "audio": {"transport": "mp3_cached", "mp3_bitrate": "128k", "cache_dir": str(tmp_path / "cache")},
    }
    app = create_app(config)
    set_audio_roots([str(tmp_path)])
    token = encode_audio_request(str(source))
    response = app.server.test_client().get(f"/audio-file/{token}?transport=mp3_cached&mp3_bitrate=128k")
    assert response.status_code == 200
    assert response.mimetype == "audio/mpeg"
    assert len(response.data) < source.stat().st_size / 4
