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
        '--config',
        type=str,
        help='Path to config YAML file (optional - overrides data-dir)',
        default=None
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

    if args.data_dir:
        expanded = os.path.expanduser(os.path.expandvars(args.data_dir))
        args.data_dir = expanded if os.path.isabs(expanded) else os.path.abspath(expanded)
    
    # Priority: config file > data_dir argument > DATA_DIR env var > browse mode
    if args.config:
        os.environ['HYDROPHONE_VERIFY_CONFIG'] = args.config
        try:
            config = get_config()
        except Exception as e:
            print(f"Error loading configuration: {e}")
            print("\nPlease ensure you have a valid config file.")
            return 1
        startup_mode = "config"
    elif args.data_dir:
        # Create dynamic config from data directory
        config = {
            'mode': 'verify',
            'data': {
                'mode': 'verify',  # Default to verify mode for browsing
                'data_dir': args.data_dir
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
        config = {
            'mode': 'verify',
            'data': {
                'mode': 'verify',
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
    
    if args.spectrogram_source:
        spec_cfg = dict(config.get("spectrogram_render", {}) or {})
        spec_cfg["source"] = args.spectrogram_source
        config["spectrogram_render"] = spec_cfg

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
        print(f"Data directory: {args.data_dir}")
        print("Mode: Auto-discover dates and devices")
    else:
        print("Mode: Browse - Use the folder browser to select a data directory")
    print("=" * 60)
    print("\nPress Ctrl+C to stop the server")
    print()
    
    app.run(debug=args.debug, host=args.host, port=args.port)
    
    return 0


if __name__ == '__main__':
    exit(main())
