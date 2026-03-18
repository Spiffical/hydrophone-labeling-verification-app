import os
from typing import Dict
import base64

import dash
import dash_bootstrap_components as dbc
from flask import Response, abort, send_file

from app.layouts.main_layout import create_main_layout
from app.callbacks import register_callbacks
from app.utils.image_processing import generate_item_image_cached
from app.utils.image_utils import decode_item_image_request


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

    @app.server.route("/item-image/<token>")
    def serve_item_image(token):
        payload = decode_item_image_request(token)
        if not payload:
            abort(400)

        item = {
            "audio_path": payload.get("audio_path"),
            "mat_path": payload.get("mat_path"),
            "spectrogram_path": payload.get("spectrogram_path"),
        }
        cfg = {"spectrogram_render": payload.get("render_cfg") or {}}
        colormap = str(payload.get("colormap") or "default")
        y_axis_scale = str(payload.get("y_axis_scale") or "linear")

        image_src = generate_item_image_cached(
            item,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        if not image_src or not image_src.startswith("data:") or ";base64," not in image_src:
            abort(404)

        header, encoded = image_src.split(",", 1)
        mime_type = header[5:].split(";", 1)[0] or "image/png"
        try:
            image_bytes = base64.b64decode(encoded)
        except Exception:
            abort(500)

        return Response(
            image_bytes,
            mimetype=mime_type,
            headers={
                "Cache-Control": "private, max-age=300, stale-while-revalidate=60",
            },
        )

    return app
