import base64
import json
import os
import time
from typing import Optional
from urllib.parse import urlencode

from cachetools import LRUCache

from app.utils.image_processing import (
    SPECTROGRAM_SOURCE_AUDIO_GENERATED,
    SPECTROGRAM_SOURCE_EXISTING,
    generate_image_cached,
    generate_item_image_cached,
    get_spectrogram_render_settings,
)

_file_image_cache = LRUCache(maxsize=256)
_ITEM_IMAGE_URL_VERSION = str(int(time.time() * 1000))


def _urlsafe_b64encode_json(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_item_image_request(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        padded = token + ("=" * ((4 - (len(token) % 4)) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def build_item_image_request_src(
    item: dict,
    *,
    cfg: Optional[dict] = None,
    colormap: str = "default",
    y_axis_scale: str = "linear",
    y_axis_min_hz: Optional[float] = None,
    y_axis_max_hz: Optional[float] = None,
    color_min: Optional[float] = None,
    color_max: Optional[float] = None,
) -> str:
    render_cfg = get_spectrogram_render_settings(cfg)
    payload = {
        "audio_path": item.get("audio_path"),
        "mat_path": item.get("mat_path"),
        "spectrogram_path": item.get("spectrogram_path"),
        "colormap": str(colormap or "default"),
        "y_axis_scale": str(y_axis_scale or "linear"),
        "y_axis_min_hz": y_axis_min_hz,
        "y_axis_max_hz": y_axis_max_hz,
        "color_min": color_min,
        "color_max": color_max,
        "render_cfg": render_cfg,
    }
    token = _urlsafe_b64encode_json(payload)
    # Include a compact query string so browser caches separate render settings independently.
    cache_key = urlencode(
        {
            "src": render_cfg.get("source"),
            "ov": render_cfg.get("overlap"),
            "wd": render_cfg.get("win_dur_s"),
            "fmin": render_cfg.get("freq_min_hz"),
            "fmax": render_cfg.get("freq_max_hz"),
            "cm": colormap,
            "ys": y_axis_scale,
            "ymin": y_axis_min_hz,
            "ymax": y_axis_max_hz,
            "cmin": color_min,
            "cmax": color_max,
            "rv": _ITEM_IMAGE_URL_VERSION,
        }
    )
    return f"/item-image/{token}?{cache_key}"


def image_file_to_base64(image_path: str) -> str:
    if not image_path or not os.path.exists(image_path):
        return ""
    if image_path in _file_image_cache:
        return _file_image_cache[image_path]

    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    suffix = os.path.splitext(image_path)[1].lower()
    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")

    data_uri = f"data:{mime_type};base64,{encoded}"
    _file_image_cache[image_path] = data_uri
    return data_uri


def get_item_image_src(
    item: dict,
    colormap: str = "default",
    y_axis_scale: str = "linear",
    y_axis_min_hz: Optional[float] = None,
    y_axis_max_hz: Optional[float] = None,
    color_min: Optional[float] = None,
    color_max: Optional[float] = None,
    cfg: Optional[dict] = None,
) -> Optional[str]:
    if not item:
        return None

    render_cfg = get_spectrogram_render_settings(cfg)
    source = render_cfg.get("source")
    use_existing = source == SPECTROGRAM_SOURCE_EXISTING

    if source == SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        return build_item_image_request_src(
            item,
            cfg=cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )

    requires_dynamic_render = any(
        value is not None and value != ""
        for value in (y_axis_min_hz, y_axis_max_hz, color_min, color_max)
    ) or colormap != "default" or y_axis_scale != "linear"

    if item.get("image_src") and not requires_dynamic_render:
        return item["image_src"]

    if use_existing and not requires_dynamic_render:
        spectrogram_path = item.get("spectrogram_path")
        if spectrogram_path and os.path.splitext(spectrogram_path)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return image_file_to_base64(spectrogram_path)

    dynamic_src = generate_item_image_cached(
        item,
        cfg,
        colormap=colormap,
        y_axis_scale=y_axis_scale,
        y_axis_min_hz=y_axis_min_hz,
        y_axis_max_hz=y_axis_max_hz,
        color_min=color_min,
        color_max=color_max,
    )
    if dynamic_src:
        return dynamic_src

    mat_path = item.get("mat_path")
    if use_existing and mat_path and os.path.exists(mat_path):
        return generate_image_cached(
            mat_path,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )

    return None
