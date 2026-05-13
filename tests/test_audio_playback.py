from pathlib import Path
import wave

from app.components.audio_player import create_modal_audio_player
from app.defaults import DEFAULT_AUDIO_TRANSPORT
from app.main import create_app, set_audio_roots
from app.utils.audio_request import encode_audio_request
from app.utils.audio_transport import build_audio_transport_query


def _write_tiny_wav(path):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 16)


def _find_component_by_id(node, target_id):
    if hasattr(node, "to_plotly_json"):
        node = node.to_plotly_json()
    if isinstance(node, dict):
        props = node.get("props") or {}
        if props.get("id") == target_id:
            return node
        for value in props.values():
            found = _find_component_by_id(value, target_id)
            if found is not None:
                return found
        for value in node.values():
            found = _find_component_by_id(value, target_id)
            if found is not None:
                return found
    elif isinstance(node, (list, tuple)):
        for item in node:
            found = _find_component_by_id(item, target_id)
            if found is not None:
                return found
    return None


def test_default_audio_transport_is_direct():
    assert DEFAULT_AUDIO_TRANSPORT == "direct"
    assert build_audio_transport_query(transport=DEFAULT_AUDIO_TRANSPORT) == ""


def test_audio_controls_disable_browser_pitch_preservation():
    script_path = Path(__file__).resolve().parents[1] / "app" / "assets" / "audio_controls.js"
    script = script_path.read_text()

    assert "audio.preservesPitch = false" in script
    assert "audio.webkitPreservesPitch = false" in script
    assert "audio.mozPreservesPitch = false" in script
    assert script.index("disablePitchPreservation(audio);") < script.index("audio.playbackRate = rate;")


def test_audio_controls_include_visible_spectrogram_filter_mode():
    script_path = Path(__file__).resolve().parents[1] / "app" / "assets" / "audio_controls.js"
    script = script_path.read_text()

    assert "visibleHighpassFilter" in script
    assert "visibleLowpassFilter" in script
    assert "getSpectrogramVisibleFrequencyWindowHz" in script
    assert "updateVisibleFrequencyFilters(audio, isVisibleFrequencyFilterEnabled())" in script
    assert "audio.playbackRate = rate;\n                    refreshVisibleFrequencyFilter();" in script


def test_modal_audio_player_uses_source_url_without_mp3_transport_query(tmp_path):
    audio_path = tmp_path / "clip.wav"
    _write_tiny_wav(audio_path)

    player = create_modal_audio_player(
        str(audio_path),
        "clip",
        player_id="modal-player",
        transport="direct",
    )

    audio = _find_component_by_id(player, "modal-player-audio")
    assert audio is not None
    props = audio["props"]
    assert props["src"].startswith("/audio-file/")
    assert props["data-audio-src"] == props["src"]
    assert "transport=mp3_cached" not in props["src"]
    assert "mp3_bitrate" not in props["src"]


def test_modal_audio_player_has_visible_frequency_filter_toggle(tmp_path):
    audio_path = tmp_path / "clip.wav"
    _write_tiny_wav(audio_path)

    player = create_modal_audio_player(
        str(audio_path),
        "clip",
        player_id="modal-player",
        visible_filter_enabled=True,
    )

    toggle = _find_component_by_id(player, "modal-player-visible-filter-toggle")
    assert toggle is not None
    props = toggle["props"]
    assert props["value"] is True
    assert props["label"] == "Only play visible frequencies"

    root_props = player.to_plotly_json()["props"]
    assert root_props["data-visible-filter-default"] == "true"


def test_direct_audio_route_returns_original_source_bytes(tmp_path):
    audio_path = tmp_path / "clip.wav"
    _write_tiny_wav(audio_path)
    original_bytes = audio_path.read_bytes()

    config = {
        "mode": "label",
        "label": {
            "folder": str(tmp_path),
            "audio_folder": str(tmp_path),
            "output_file": str(tmp_path / "labels.json"),
        },
        "display": {
            "items_per_page": 25,
            "colormap": "default",
            "y_axis_scale": "linear",
        },
        "cache": {
            "max_size": 25,
        },
        "audio": {
            "transport": "direct",
        },
    }

    app = create_app(config)
    set_audio_roots([str(tmp_path)])

    token = encode_audio_request(str(audio_path))
    response = app.server.test_client().get(f"/audio-file/{token}")

    assert response.status_code == 200
    assert response.data == original_bytes
    assert response.headers.get("Accept-Ranges") == "bytes"
