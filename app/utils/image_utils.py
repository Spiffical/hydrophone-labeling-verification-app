import base64
import os
from typing import Optional

from cachetools import LRUCache

from app.utils.image_processing import generate_image_cached

_file_image_cache = LRUCache(maxsize=256)


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


def get_item_image_src(item: dict, colormap: str = "default", y_axis_scale: str = "linear") -> Optional[str]:
    if not item:
        return None

    if item.get("image_src"):
        return item["image_src"]

    spectrogram_path = item.get("spectrogram_path")
    if spectrogram_path and os.path.splitext(spectrogram_path)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return image_file_to_base64(spectrogram_path)

    mat_path = item.get("mat_path")
    if mat_path and os.path.exists(mat_path):
        return generate_image_cached(mat_path, colormap=colormap, y_axis_scale=y_axis_scale)

    return None

