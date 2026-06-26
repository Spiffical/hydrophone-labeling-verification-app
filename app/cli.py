#!/usr/bin/env python3
"""CLI entry point for pip-installed verification app."""
import argparse
import os
from pathlib import Path

from app.config import get_config
from app.defaults import (
    DEFAULT_AUDIO_MP3_BITRATE,
    DEFAULT_AUDIO_TRANSPORT,
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_ITEMS_PER_PAGE,
)
from app.utils.audio_transport import normalize_audio_transport
from app.main import create_app


def _coerce_float(value, default, *, minimum=None, maximum=None):
    try:
        if value is None or value == "":
            number = float(default)
        else:
            number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if minimum is not None:
        number = max(float(minimum), number)
    if maximum is not None:
        number = min(float(maximum), number)
    return float(number)


def _apply_spectrogram_cli_args(config, args):
    spec_cfg = dict(config.get("spectrogram_render", {}) or {})
    if args.spectrogram_source:
        spec_cfg["source"] = args.spectrogram_source

    spec_cfg["win_dur_s"] = _coerce_float(
        args.spec_win_dur if args.spec_win_dur is not None else spec_cfg.get("win_dur_s", 1.0),
        1.0,
        minimum=0.05,
        maximum=30.0,
    )
    spec_cfg["overlap"] = _coerce_float(
        args.spec_overlap if args.spec_overlap is not None else spec_cfg.get("overlap", 0.9),
        0.9,
        minimum=0.0,
        maximum=0.99,
    )
    spec_cfg["freq_min_hz"] = _coerce_float(
        args.spec_freq_min if args.spec_freq_min is not None else spec_cfg.get("freq_min_hz", 5.0),
        5.0,
        minimum=0.0,
        maximum=200000.0,
    )
    spec_cfg["freq_max_hz"] = _coerce_float(
        args.spec_freq_max if args.spec_freq_max is not None else spec_cfg.get("freq_max_hz", 100.0),
        100.0,
        minimum=0.01,
        maximum=200000.0,
    )
    if spec_cfg["freq_max_hz"] <= spec_cfg["freq_min_hz"]:
        spec_cfg["freq_max_hz"] = max(spec_cfg["freq_min_hz"] + 1.0, 100.0)

    config["spectrogram_render"] = spec_cfg


def main():
    """Main entry point for the verification app CLI."""
    parser = argparse.ArgumentParser(
        description='Hydrophone Verification App - Interactive acoustic analysis and labeling'
    )
    parser.add_argument(
        '--data-dir',
        type=str,
        help='Root data directory (e.g., /data/onc). Will auto-discover dates and devices.',
        default=os.environ.get('DATA_DIR')
    )
    parser.add_argument(
        '--audio-folder',
        type=str,
        help='Folder containing audio files when it differs from the data directory',
        default=None
    )
    parser.add_argument(
        '--spectrogram-folder',
        type=str,
        help='Folder containing existing MAT/NPY/PNG spectrogram files',
        default=None
    )
    parser.add_argument(
        '--predictions-json',
        type=str,
        help='Predictions JSON or labels JSON file to load at startup',
        default=None
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to config YAML file (optional - overrides data-dir)',
        default=None
    )
    parser.add_argument(
        '--mode',
        choices=['label', 'verify', 'explore'],
        default=None,
        help='Initial workspace mode'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8051,
        help='Port to run on (default: 8051)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Run in debug mode'
    )
    parser.add_argument(
        '--spectrogram-source',
        choices=['existing', 'audio_generated'],
        default=None,
        help='Default spectrogram source mode at startup'
    )
    parser.add_argument(
        '--spec-window-duration',
        '--spec-win-dur',
        '--fft-window-sec',
        dest='spec_win_dur',
        type=float,
        default=None,
        help='FFT window duration in seconds for generated spectrograms'
    )
    parser.add_argument(
        '--spec-overlap',
        '--fft-overlap',
        dest='spec_overlap',
        type=float,
        default=None,
        help='FFT window overlap ratio for generated spectrograms, from 0 to 0.99'
    )
    parser.add_argument(
        '--spec-freq-min',
        '--freq-min-hz',
        dest='spec_freq_min',
        type=float,
        default=None,
        help='Minimum frequency in Hz for generated spectrograms'
    )
    parser.add_argument(
        '--spec-freq-max',
        '--freq-max-hz',
        dest='spec_freq_max',
        type=float,
        default=None,
        help='Maximum frequency in Hz for generated spectrograms'
    )
    parser.add_argument(
        '--audio-transport',
        choices=['direct', 'mp3_cached'],
        default=None,
        help='Playback transport for audio players'
    )
    parser.add_argument(
        '--audio-mp3-bitrate',
        type=str,
        default=None,
        help='Bitrate for cached MP3 playback transport'
    )
    args = parser.parse_args()

    for path_arg in ("data_dir", "audio_folder", "spectrogram_folder", "predictions_json"):
        raw_path = getattr(args, path_arg, None)
        if raw_path:
            expanded = os.path.expanduser(os.path.expandvars(raw_path))
            setattr(args, path_arg, expanded if os.path.isabs(expanded) else os.path.abspath(expanded))
    
    # Priority: config file > data_dir argument > DATA_DIR env var > browse mode
    if args.config:
        os.environ['HYDROPHONE_VERIFY_CONFIG'] = args.config
        try:
            config = get_config()
        except Exception as e:
            print(f"Error loading configuration: {e}")
            print("\nPlease ensure you have a valid config file.")
            return 1
        if args.mode:
            config["mode"] = args.mode
            config.setdefault("data", {})["mode"] = args.mode
        data_cfg = config.setdefault("data", {})
        if args.data_dir:
            data_cfg["data_dir"] = args.data_dir
        if args.audio_folder:
            data_cfg["audio_folder"] = args.audio_folder
            config.setdefault("label", {})["audio_folder"] = args.audio_folder
        if args.spectrogram_folder:
            data_cfg["spectrogram_folder"] = args.spectrogram_folder
            config.setdefault("label", {})["folder"] = args.spectrogram_folder
        if args.predictions_json:
            data_cfg["predictions_file"] = args.predictions_json
            config.setdefault("verify", {})["predictions_json"] = args.predictions_json
        startup_mode = "config"
    elif args.data_dir or args.audio_folder or args.spectrogram_folder:
        # Create dynamic config from data directory
        active_mode = args.mode or "label"
        data_root = args.data_dir or args.spectrogram_folder or args.audio_folder
        config = {
            'mode': active_mode,
            'data': {
                'mode': active_mode,
                'data_dir': data_root,
                'audio_folder': args.audio_folder,
                'spectrogram_folder': args.spectrogram_folder,
                'predictions_file': args.predictions_json,
            },
            'label': {
                'folder': args.spectrogram_folder,
                'audio_folder': args.audio_folder,
                'output_file': None,
            },
            'verify': {
                'dashboard_root': data_root,
                'predictions_json': args.predictions_json,
            },
            'display': {
                'items_per_page': DEFAULT_ITEMS_PER_PAGE,
                'y_axis_scale': 'linear',
                'colormap': 'default'
            },
            'cache': {
                'max_size': DEFAULT_CACHE_MAX_SIZE
            }
        }
        startup_mode = "data_dir"
    else:
        # No arguments - start in browse mode
        active_mode = args.mode or "label"
        config = {
            'mode': active_mode,
            'data': {
                'mode': active_mode,
                'data_dir': None  # Will be set via folder browser
            },
            'display': {
                'items_per_page': DEFAULT_ITEMS_PER_PAGE,
                'y_axis_scale': 'linear',
                'colormap': 'default'
            },
            'cache': {
                'max_size': DEFAULT_CACHE_MAX_SIZE
            }
        }
        startup_mode = "browse"
    
    _apply_spectrogram_cli_args(config, args)

    audio_cfg = dict(config.get("audio", {}) or {})
    audio_cfg["transport"] = normalize_audio_transport(
        args.audio_transport or audio_cfg.get("transport", DEFAULT_AUDIO_TRANSPORT)
    )
    audio_cfg["mp3_bitrate"] = str(
        args.audio_mp3_bitrate or audio_cfg.get("mp3_bitrate", DEFAULT_AUDIO_MP3_BITRATE)
    )
    config["audio"] = audio_cfg

    app = create_app(config)
    
    print("=" * 60)
    print("🎧 Hydrophone Verification App")
    print("=" * 60)
    print(f"Starting server on http://{args.host}:{args.port}")
    print(f"Debug mode: {'ON' if args.debug else 'OFF'}")
    if startup_mode == "config":
        print(f"Config: {args.config}")
    elif startup_mode == "data_dir":
        print(f"Data directory: {args.data_dir or args.spectrogram_folder or args.audio_folder}")
        if args.audio_folder:
            print(f"Audio folder: {args.audio_folder}")
        if args.spectrogram_folder:
            print(f"Spectrogram folder: {args.spectrogram_folder}")
        if args.predictions_json:
            print(f"Predictions JSON: {args.predictions_json}")
        print("Mode: Auto-discover dates and devices")
    else:
        print("Mode: Browse - Use the folder browser to select a data directory")
    spec_cfg = config.get("spectrogram_render", {}) or {}
    print(
        "Spectrograms: "
        f"{spec_cfg.get('source', 'existing')} "
        f"(window={spec_cfg.get('win_dur_s')}s, "
        f"overlap={spec_cfg.get('overlap')}, "
        f"freq={spec_cfg.get('freq_min_hz')}-{spec_cfg.get('freq_max_hz')} Hz)"
    )
    print("=" * 60)
    print("\nPress Ctrl+C to stop the server")
    print()
    
    app.run(debug=args.debug, host=args.host, port=args.port)
    
    return 0


if __name__ == '__main__':
    exit(main())
