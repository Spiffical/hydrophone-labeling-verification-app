import os
from typing import Dict

import dash
import dash_bootstrap_components as dbc
from flask import abort, send_file

from app.layouts.main_layout import create_main_layout
from app.callbacks.main_callbacks import register_callbacks
from app.callbacks.pagination_callbacks import register_pagination_callbacks
from app.callbacks.folder_browser_callbacks import register_folder_browser_callbacks
from app.callbacks.data_config_callbacks import register_data_config_callbacks


# Global audio search roots (updated on data load)
_audio_search_roots = []


def set_audio_roots(roots):
    global _audio_search_roots
    _audio_search_roots = [r for r in roots if r]


def create_app(config: Dict) -> dash.Dash:
    # Get the absolute path to assets folder relative to package
    this_dir = os.path.dirname(os.path.abspath(__file__))
    assets_path = os.path.join(this_dir, 'assets')
    
    app = dash.Dash(
        __name__,
        assets_folder=assets_path,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
            "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css",
        ],
        suppress_callback_exceptions=True,
    )

    app.layout = create_main_layout(config)
    register_callbacks(app, config)
    register_pagination_callbacks(app)
    register_folder_browser_callbacks(app)
    register_data_config_callbacks(app)

    # Serve audio files by filename lookup in configured roots
    @app.server.route("/audio/<filename>")
    def serve_audio(filename):
        search_roots = list(_audio_search_roots)
        if not search_roots:
            # fallback to label audio folder if configured
            search_roots = [config.get("label", {}).get("audio_folder")]

        for root in [r for r in search_roots if r and os.path.exists(r)]:
            # Try direct path first
            candidate = os.path.join(root, filename)
            if os.path.exists(candidate):
                return send_file(candidate, as_attachment=False)

            # Walk subdirectories
            for dirpath, _, files in os.walk(root):
                if filename in files:
                    return send_file(os.path.join(dirpath, filename), as_attachment=False)

        abort(404)

    return app
