#!/usr/bin/env python3
"""CLI entry point for pip-installed verification app."""
import argparse
import os
from pathlib import Path

from app.config import get_config
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
    args = parser.parse_args()
    
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
            'data': {
                'mode': 'verify',  # Default to verify mode for browsing
                'data_dir': args.data_dir
            },
            'display': {
                'items_per_page': 25,
                'y_axis_scale': 'linear',
                'colormap': 'default'
            },
            'cache': {
                'max_size': 400
            }
        }
        startup_mode = "data_dir"
    else:
        # No arguments - start in browse mode
        config = {
            'data': {
                'mode': 'verify',
                'data_dir': None  # Will be set via folder browser
            },
            'display': {
                'items_per_page': 25,
                'y_axis_scale': 'linear',
                'colormap': 'default'
            },
            'cache': {
                'max_size': 400
            }
        }
        startup_mode = "browse"
    
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
