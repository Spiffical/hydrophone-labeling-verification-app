import os
from typing import Dict
import base64

import dash
import dash_bootstrap_components as dbc
from flask import Response, abort, redirect, request, send_file, url_for

from app.layouts.main_layout import create_main_layout
from app.callbacks import register_callbacks
from app.defaults import (
    DEFAULT_AUDIO_CACHE_MAX_AGE,
    DEFAULT_AUDIO_LEGACY_FILENAME_ROUTE,
    DEFAULT_AUDIO_MP3_BITRATE,
    DEFAULT_AUDIO_STALE_IF_ERROR,
    DEFAULT_AUDIO_STALE_WHILE_REVALIDATE,
    DEFAULT_AUDIO_TRANSPORT,
)
from app.utils.audio_request import decode_audio_request, encode_audio_request
from app.utils.audio_transport import (
    DEFAULT_AUDIO_CACHE_DIR,
    build_audio_transport_query,
    normalize_audio_transport,
    resolve_audio_delivery_path,
)
from app.utils.image_processing import generate_item_image_cached
from app.utils.image_utils import decode_item_image_request


# Global audio search roots (updated on data load)
_audio_search_roots = []
_normalized_audio_search_roots = []


def set_audio_roots(roots):
    global _audio_search_roots, _normalized_audio_search_roots
    _audio_search_roots = [r for r in roots if r]
    _normalized_audio_search_roots = [
        os.path.abspath(r)
        for r in _audio_search_roots
        if r and os.path.exists(r)
    ]


def _is_audio_path_allowed(audio_path, fallback_root=None):
    if not audio_path:
        return False
    candidate = os.path.abspath(audio_path)
    allowed_roots = list(_normalized_audio_search_roots)
    if fallback_root and os.path.exists(fallback_root):
        allowed_roots.append(os.path.abspath(fallback_root))

    for root in allowed_roots:
        try:
            if os.path.commonpath([candidate, root]) == root:
                return True
        except ValueError:
            continue
    return False


def _coerce_non_negative_int(value, default):
    try:
        if value is None or value == "":
            return int(default)
        return max(0, int(value))
    except (TypeError, ValueError):
        return int(default)


def _coerce_bool(value, default):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    candidate = str(value).strip().lower()
    if candidate in {"1", "true", "yes", "on"}:
        return True
    if candidate in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _get_audio_config(config):
    audio_cfg = config.get("audio", {})
    return audio_cfg if isinstance(audio_cfg, dict) else {}


def _build_cache_control_header(max_age, stale_while_revalidate=None, stale_if_error=None):
    parts = [
        "private",
        "no-transform",
        f"max-age={max(0, int(max_age))}",
    ]
    if stale_while_revalidate is not None:
        parts.append(f"stale-while-revalidate={max(0, int(stale_while_revalidate))}")
    if stale_if_error is not None:
        parts.append(f"stale-if-error={max(0, int(stale_if_error))}")
    return ", ".join(parts)


def _build_audio_response(audio_path, *, cache_max_age, stale_while_revalidate, stale_if_error):
    response = send_file(
        audio_path,
        as_attachment=False,
        conditional=True,
        max_age=cache_max_age,
        etag=True,
    )
    response.headers["Cache-Control"] = _build_cache_control_header(
        cache_max_age,
        stale_while_revalidate=stale_while_revalidate,
        stale_if_error=stale_if_error,
    )
    response.headers["Accept-Ranges"] = "bytes"
    return response


def _find_audio_path_by_filename(filename, fallback_root=None):
    search_roots = list(_audio_search_roots)
    if not search_roots:
        search_roots = [fallback_root]

    for root in [r for r in search_roots if r and os.path.exists(r)]:
        candidate = os.path.join(root, filename)
        if os.path.exists(candidate):
            return candidate

        for dirpath, _, files in os.walk(root):
            if filename in files:
                return os.path.join(dirpath, filename)

    return None


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
    audio_cfg = _get_audio_config(config)
    audio_transport = normalize_audio_transport(
        audio_cfg.get("transport", DEFAULT_AUDIO_TRANSPORT)
    )
    audio_mp3_bitrate = str(audio_cfg.get("mp3_bitrate", DEFAULT_AUDIO_MP3_BITRATE))
    audio_cache_max_age = _coerce_non_negative_int(
        audio_cfg.get("cache_max_age", DEFAULT_AUDIO_CACHE_MAX_AGE),
        DEFAULT_AUDIO_CACHE_MAX_AGE,
    )
    audio_stale_while_revalidate = _coerce_non_negative_int(
        audio_cfg.get("stale_while_revalidate", DEFAULT_AUDIO_STALE_WHILE_REVALIDATE),
        DEFAULT_AUDIO_STALE_WHILE_REVALIDATE,
    )
    audio_stale_if_error = _coerce_non_negative_int(
        audio_cfg.get("stale_if_error", DEFAULT_AUDIO_STALE_IF_ERROR),
        DEFAULT_AUDIO_STALE_IF_ERROR,
    )
    audio_legacy_filename_route = _coerce_bool(
        audio_cfg.get("legacy_filename_route", DEFAULT_AUDIO_LEGACY_FILENAME_ROUTE),
        DEFAULT_AUDIO_LEGACY_FILENAME_ROUTE,
    )

    # Serve audio files by filename lookup in configured roots
    @app.server.route("/audio/<filename>")
    def serve_audio(filename):
        if not audio_legacy_filename_route:
            abort(404)

        fallback_root = config.get("label", {}).get("audio_folder")
        audio_path = _find_audio_path_by_filename(filename, fallback_root=fallback_root)
        if not audio_path:
            abort(404)

        token = encode_audio_request(audio_path)
        if not token:
            abort(404)

        query = build_audio_transport_query(
            transport=request.args.get("transport") or audio_transport,
            mp3_bitrate=request.args.get("mp3_bitrate") or audio_mp3_bitrate,
        )
        return redirect(url_for("serve_audio_file", token=token) + query, code=308)

    @app.server.route("/audio-file/<token>")
    def serve_audio_file(token):
        payload = decode_audio_request(token)
        if not payload:
            abort(404)

        audio_path = payload.get("audio_path")
        fallback_root = config.get("label", {}).get("audio_folder")
        if not audio_path or not os.path.exists(audio_path):
            abort(404)
        if not _is_audio_path_allowed(audio_path, fallback_root=fallback_root):
            abort(404)

        requested_transport = normalize_audio_transport(
            request.args.get("transport") or audio_cfg.get("transport", DEFAULT_AUDIO_TRANSPORT)
        )
        requested_bitrate = request.args.get("mp3_bitrate") or audio_cfg.get("mp3_bitrate", DEFAULT_AUDIO_MP3_BITRATE)
        cache_dir = audio_cfg.get("cache_dir", DEFAULT_AUDIO_CACHE_DIR)
        delivery_path = resolve_audio_delivery_path(
            audio_path,
            transport=requested_transport,
            mp3_bitrate=requested_bitrate,
            cache_dir=cache_dir,
        )
        if not delivery_path or not os.path.exists(delivery_path):
            abort(404)

        return _build_audio_response(
            delivery_path,
            cache_max_age=audio_cache_max_age,
            stale_while_revalidate=audio_stale_while_revalidate,
            stale_if_error=audio_stale_if_error,
        )

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
        y_axis_min_hz = payload.get("y_axis_min_hz")
        y_axis_max_hz = payload.get("y_axis_max_hz")
        color_min = payload.get("color_min")
        color_max = payload.get("color_max")

        image_src = generate_item_image_cached(
            item,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
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
