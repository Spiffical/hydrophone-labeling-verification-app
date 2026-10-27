"""The flac_resampled playback transport (app/utils/audio_transport.py): a lossless
FLAC at a lower rate for high-rate hydrophone files on slow links."""

import time

import numpy as np
import soundfile as sf

from app.components.audio_player import create_modal_audio_player
from app.main import create_app, set_audio_roots
from app.utils.audio_request import encode_audio_request
from app.utils.audio_transport import (
    build_audio_transport_query,
    prewarm_audio_delivery_path,
    resolve_audio_delivery_path,
)

RATE = 256000
# Kept: a fin whale band tone, a knock band tone and one near the top of what is kept (7 kHz).
KEPT = ((20.0, 0.2), (1000.0, 0.1), (6500.0, 0.05))
# Removed: above the new Nyquist frequency (8 kHz). Without filtering, 9 kHz would
# fold onto 7 kHz and 100.02 kHz onto 4.02 kHz.
REMOVED = ((9000.0, 0.1), (100020.0, 0.1))


def _tones(tones, t):
    return sum(amplitude * np.sin(2 * np.pi * frequency * t + 0.3) for frequency, amplitude in tones)


def _write_flac(path, seconds=1.0, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    sf.write(str(path), _tones(KEPT + REMOVED, t), rate, subtype="PCM_24", format="FLAC")


def _flac(path, tmp_path, **kwargs):
    return resolve_audio_delivery_path(str(path), transport="flac_resampled", cache_dir=str(tmp_path / "cache"), **kwargs)


def test_flac_transport_keeps_the_low_band_exactly_and_removes_the_rest(tmp_path):
    source = tmp_path / "clip.flac"
    _write_flac(source)
    delivered = _flac(source, tmp_path, flac_sample_rate=16000)
    assert delivered.endswith(".flac") and str(tmp_path / "cache") in delivered
    info = sf.info(delivered)
    assert (info.samplerate, info.subtype, info.frames) == (16000, "PCM_24", 16000)
    assert source.stat().st_size > 8 * (tmp_path / "cache" / delivered.split("/")[-1]).stat().st_size

    played, _rate = sf.read(delivered)
    middle = slice(800, -800)  # the filter's start and end transients (50 ms)
    expected = _tones(KEPT, np.arange(16000) / 16000)
    # The kept tones come through in level and in time (no shift), and the removed ones
    # do not fold back: what is left is over 90 dB below the tones.
    assert np.max(np.abs(played[middle] - expected[middle])) < 0.1 * 10 ** (-90 / 20)
    # A second request is served from the cache.
    assert _flac(source, tmp_path, flac_sample_rate=16000) == delivered


def test_files_at_or_below_the_rate_are_served_as_they_are(tmp_path):
    source = tmp_path / "clip.flac"
    _write_flac(source, rate=16000)
    assert _flac(source, tmp_path, flac_sample_rate=16000) == str(source)


def test_flac_transport_query_takes_only_known_rates():
    assert build_audio_transport_query(transport="flac_resampled", flac_sample_rate=8000) == (
        "?transport=flac_resampled&sample_rate=8000"
    )
    for rate in (None, "12345", "abc"):
        assert build_audio_transport_query(transport="flac_resampled", flac_sample_rate=rate).endswith(
            "sample_rate=16000"
        )


def test_prewarm_makes_the_flac_in_the_background(tmp_path):
    source = tmp_path / "clip.flac"
    _write_flac(source)
    assert prewarm_audio_delivery_path(str(source), transport="flac_resampled", cache_dir=str(tmp_path / "cache"))
    deadline = time.time() + 20
    while not list((tmp_path / "cache").glob("*[0-9a-f].flac")) and time.time() < deadline:
        time.sleep(0.05)
    made = list((tmp_path / "cache").glob("*[0-9a-f].flac"))
    assert len(made) == 1 and _flac(source, tmp_path) == str(made[0])
    assert not prewarm_audio_delivery_path(str(source), transport="flac_resampled", cache_dir=str(tmp_path / "cache"))


def test_modal_player_and_audio_route_serve_the_flac(tmp_path):
    source = tmp_path / "clip.flac"
    _write_flac(source)
    player = create_modal_audio_player(
        str(source), "clip", player_id="modal-player", transport="flac_resampled", flac_sample_rate=16000
    ).to_plotly_json()
    assert "?transport=flac_resampled&sample_rate=16000" in str(player)

    config = {
        "mode": "label",
        "label": {"folder": str(tmp_path), "audio_folder": str(tmp_path), "output_file": str(tmp_path / "labels.json")},
        "display": {"items_per_page": 25, "colormap": "default", "y_axis_scale": "linear"},
        "cache": {"max_size": 25},
        "audio": {"transport": "flac_resampled", "flac_sample_rate": 16000, "cache_dir": str(tmp_path / "cache")},
    }
    app = create_app(config)
    set_audio_roots([str(tmp_path)])
    token = encode_audio_request(str(source))
    response = app.server.test_client().get(f"/audio-file/{token}?transport=flac_resampled&sample_rate=16000")
    assert response.status_code == 200
    assert response.mimetype in ("audio/flac", "audio/x-flac")
    assert len(response.data) < source.stat().st_size / 8
