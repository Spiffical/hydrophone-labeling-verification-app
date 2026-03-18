import base64
from io import BytesIO
import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.colors as mcolors
from matplotlib.figure import Figure
import numpy as np
import plotly.graph_objects as go
import scipy.io as sio
import soundfile as sf
from cachetools import LRUCache
from concurrent.futures import ThreadPoolExecutor
try:
    import torch
except Exception:  # pragma: no cover - optional dependency at runtime
    torch = None

from app.utils.colmap_hyd import colmap_hyd_py

logger = logging.getLogger(__name__)

spectrogram_cache = LRUCache(maxsize=400)
audio_spectrogram_cache = LRUCache(maxsize=400)
image_cache = LRUCache(maxsize=800)

SPECTROGRAM_SOURCE_EXISTING = "existing"
SPECTROGRAM_SOURCE_AUDIO_GENERATED = "audio_generated"
DEFAULT_SPECTROGRAM_RENDER_SETTINGS: Dict[str, Any] = {
    "source": SPECTROGRAM_SOURCE_EXISTING,
    "win_dur_s": 1.0,
    "overlap": 0.9,
    "freq_min_hz": 5.0,
    "freq_max_hz": 100.0,
}
_TORCH_MISSING_WARNED = False
_AUDIO_FALLBACK_WARNED = set()
_PREFETCH_MAX_WORKERS = max(1, min(4, (os.cpu_count() or 2) // 2))
_PREFETCH_EXECUTOR = ThreadPoolExecutor(max_workers=_PREFETCH_MAX_WORKERS, thread_name_prefix="specgen-prefetch")
_PREFETCH_PENDING_KEYS = set()
_PREFETCH_LOCK = threading.Lock()
_AUDIO_SPECTROGRAM_CACHE_LOCK = threading.Lock()
_SPECTROGRAM_CACHE_LOCK = threading.Lock()
_IMAGE_CACHE_LOCK = threading.Lock()
_MATPLOTLIB_RENDER_LOCK = threading.Lock()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except (TypeError, ValueError):
        return int(default)


_DISPLAY_MAX_TIME_BINS = max(1, _env_int("HYDRO_MODAL_MAX_TIME_BINS", 360))
_DISPLAY_MAX_FREQ_BINS = max(1, _env_int("HYDRO_MODAL_MAX_FREQ_BINS", 320))
_MODAL_HEATMAP_LEVELS = _env_int("HYDRO_MODAL_HEATMAP_LEVELS", 256)


def _resize_cache(cache: LRUCache, maxsize: int) -> None:
    cache.clear()
    if hasattr(cache, "_Cache__maxsize"):
        cache._Cache__maxsize = maxsize
        return
    if hasattr(cache, "_LRUCache__maxsize"):
        cache._LRUCache__maxsize = maxsize
        return
    try:
        cache.maxsize = maxsize
    except AttributeError:
        pass


def set_cache_sizes(maxsize: int) -> None:
    try:
        maxsize = int(maxsize)
    except (TypeError, ValueError):
        maxsize = 400
    maxsize = max(1, maxsize)
    _resize_cache(spectrogram_cache, maxsize)
    _resize_cache(audio_spectrogram_cache, maxsize)
    _resize_cache(image_cache, maxsize * 2)


def _coerce_float(value: Any, fallback: float, *, minimum: Optional[float] = None, maximum: Optional[float] = None) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = float(fallback)
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return float(value)


def _downsample_indices(length: int, max_points: int) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=np.int64)
    if max_points <= 0 or length <= max_points:
        return np.arange(length, dtype=np.int64)
    return np.linspace(0, length - 1, num=max_points, dtype=np.int64)


def _downsample_for_modal_display(
    psd: np.ndarray,
    freq: np.ndarray,
    time: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if psd is None:
        return psd, freq, time
    if getattr(psd, "ndim", 0) != 2:
        return psd, freq, time

    freq_len, time_len = psd.shape
    if freq_len <= 0 or time_len <= 0:
        return psd, freq, time

    freq_idx = _downsample_indices(freq_len, _DISPLAY_MAX_FREQ_BINS)
    time_idx = _downsample_indices(time_len, _DISPLAY_MAX_TIME_BINS)
    reduced_psd = psd[np.ix_(freq_idx, time_idx)]

    reduced_freq = freq
    if isinstance(freq, np.ndarray) and len(freq) == freq_len:
        reduced_freq = freq[freq_idx]

    reduced_time = time
    if isinstance(time, np.ndarray) and len(time) == time_len:
        reduced_time = time[time_idx]

    return reduced_psd, reduced_freq, reduced_time


def _quantize_modal_heatmap(
    psd: np.ndarray,
    zmin: float,
    zmax: float,
) -> Tuple[np.ndarray, float, float, Dict[str, Any]]:
    if _MODAL_HEATMAP_LEVELS <= 1:
        return np.asarray(psd, dtype=np.float32), float(zmin), float(zmax), {}

    level_count = max(2, int(_MODAL_HEATMAP_LEVELS))
    max_level = level_count - 1
    if max_level <= np.iinfo(np.uint8).max:
        dtype = np.uint8
    elif max_level <= np.iinfo(np.uint16).max:
        dtype = np.uint16
    else:
        return np.asarray(psd, dtype=np.float32), float(zmin), float(zmax), {}

    span = max(1e-9, float(zmax) - float(zmin))
    normalized = (np.asarray(psd, dtype=np.float32) - float(zmin)) / span
    normalized = np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0)
    normalized = np.clip(normalized, 0.0, 1.0)
    quantized = np.rint(normalized * max_level).astype(dtype)

    tick_count = min(6, level_count)
    tickvals = np.linspace(0, max_level, num=tick_count, dtype=np.float32)
    ticktext = [
        f"{(float(zmin) + (float(val) / max_level) * span):.1f}"
        for val in tickvals
    ]
    colorbar = {
        "title": "dB/Hz",
        "tickvals": tickvals,
        "ticktext": ticktext,
    }
    return quantized, 0.0, float(max_level), colorbar


def get_spectrogram_render_settings(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = dict(DEFAULT_SPECTROGRAM_RENDER_SETTINGS)
    section = (cfg or {}).get("spectrogram_render", {})
    if not isinstance(section, dict):
        section = {}

    source = str(section.get("source", base["source"])).strip().lower()
    if source not in {SPECTROGRAM_SOURCE_EXISTING, SPECTROGRAM_SOURCE_AUDIO_GENERATED}:
        source = base["source"]

    win_dur_s = _coerce_float(section.get("win_dur_s"), base["win_dur_s"], minimum=0.05, maximum=30.0)
    overlap = _coerce_float(section.get("overlap"), base["overlap"], minimum=0.0, maximum=0.99)
    freq_min_hz = _coerce_float(section.get("freq_min_hz"), base["freq_min_hz"], minimum=0.0, maximum=200000.0)
    freq_max_hz = _coerce_float(section.get("freq_max_hz"), base["freq_max_hz"], minimum=0.01, maximum=200000.0)
    if freq_max_hz <= freq_min_hz:
        freq_max_hz = max(freq_min_hz + 1.0, float(base["freq_max_hz"]))

    return {
        "source": source,
        "win_dur_s": win_dur_s,
        "overlap": overlap,
        "freq_min_hz": freq_min_hz,
        "freq_max_hz": freq_max_hz,
    }


def _load_mat(mat_path: str):
    try:
        mat_data = sio.loadmat(mat_path)
    except Exception as exc:
        logger.error("Error loading %s: %s", mat_path, exc)
        return None

    # Try new format first (from whale-call-analysis download script)
    if "PdB_norm" in mat_data or "P" in mat_data:
        psd = mat_data.get("PdB_norm", mat_data.get("P"))
        freq = mat_data.get("F", np.array([[0]]))
        time = mat_data.get("T", np.array([[0]]))
        
        # Handle different array shapes
        psd = np.squeeze(psd)
        freq = np.squeeze(freq)
        time = np.squeeze(time)
        
        # Handle NaN and inf values
        psd = np.nan_to_num(psd, nan=0.0, neginf=0.0, posinf=0.0)
        
        return {"psd": psd, "freq": freq, "time": time}

    # Try ONC SpectData format
    if "SpectData" in mat_data:
        data = mat_data["SpectData"]
        psd = data["PSD"][0, 0]
        freq = data["frequency"][0, 0].flatten()
        time = data["time"][0, 0].flatten()

        valid_mask = (psd != -np.inf)
        psd[~valid_mask] = 0
        psd = np.nan_to_num(psd, nan=0.0)

        return {"psd": psd, "freq": freq, "time": time}
    
    logger.warning("Unknown MAT format for %s, keys: %s", mat_path, list(mat_data.keys()))
    return None


def _audio_cache_signature(audio_path: str) -> Tuple[str, int, int]:
    st = os.stat(audio_path)
    return (os.path.abspath(audio_path), int(st.st_mtime_ns), int(st.st_size))


def _audio_spectrogram_cache_key(
    audio_path: str,
    *,
    win_dur_s: float,
    overlap: float,
    freq_min_hz: float,
    freq_max_hz: float,
) -> Tuple[Any, ...]:
    return (
        _audio_cache_signature(audio_path),
        float(win_dur_s),
        float(overlap),
        float(freq_min_hz),
        float(freq_max_hz),
        "torch_cpu_stft_v1",
    )


def _load_audio_spectrogram_torch(
    audio_path: str,
    *,
    win_dur_s: float,
    overlap: float,
    freq_min_hz: float,
    freq_max_hz: float,
) -> Optional[Dict[str, np.ndarray]]:
    global _TORCH_MISSING_WARNED
    if torch is None:
        if not _TORCH_MISSING_WARNED:
            logger.warning(
                "PyTorch is not available in this environment. "
                "Install torch to enable on-the-fly audio spectrogram generation."
            )
            _TORCH_MISSING_WARNED = True
        return None

    try:
        audio, sample_rate = sf.read(audio_path, dtype="float32", always_2d=False)
    except Exception as exc:
        logger.error("Error reading audio %s: %s", audio_path, exc)
        return None

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1, dtype=np.float32)
    if audio.size == 0 or sample_rate <= 0:
        return None

    sr = int(sample_rate)
    win_len = max(8, int(round(float(win_dur_s) * float(sr))))
    hop_len = int(round((1.0 - float(overlap)) * float(win_len)))
    hop_len = max(1, hop_len)
    if audio.size < win_len:
        audio = np.pad(audio, (0, win_len - audio.size), mode="constant", constant_values=0.0)

    audio_t = torch.from_numpy(audio).to(dtype=torch.float32, device="cpu")
    window_t = torch.hann_window(win_len, periodic=True, dtype=torch.float32, device="cpu")

    with torch.inference_mode():
        spec_complex = torch.stft(
            audio_t,
            n_fft=win_len,
            hop_length=hop_len,
            win_length=win_len,
            window=window_t,
            center=False,
            return_complex=True,
        )
        power = torch.abs(spec_complex).pow(2.0)
        max_power = float(power.max().item()) if power.numel() else 0.0
        if max_power > 0.0:
            pdB = 10.0 * torch.log10(torch.clamp(power / max_power, min=1e-10))
        else:
            pdB = torch.full_like(power, -100.0)

    freq = torch.fft.rfftfreq(win_len, d=1.0 / float(sr)).cpu().numpy().astype(np.float64)
    frames = pdB.shape[1]
    time = ((np.arange(frames, dtype=np.float64) * float(hop_len)) + (0.5 * float(win_len))) / float(sr)

    freq_mask = (freq >= float(freq_min_hz)) & (freq <= float(freq_max_hz))
    if not np.any(freq_mask):
        logger.warning(
            "No frequency bins in requested range [%.2f, %.2f] Hz for %s",
            float(freq_min_hz),
            float(freq_max_hz),
            audio_path,
        )
        return None

    return {
        "psd": pdB.cpu().numpy()[freq_mask, :].astype(np.float32),
        "freq": freq[freq_mask].astype(np.float64),
        "time": time.astype(np.float64),
    }


def _with_render_source(
    spec: Optional[Dict[str, np.ndarray]],
    *,
    source: str,
    reason: Optional[str] = None,
) -> Optional[Dict[str, np.ndarray]]:
    if spec is None:
        return None
    out = dict(spec)
    out["_render_source"] = str(source)
    if reason:
        out["_render_reason"] = str(reason)
    return out


def _warn_audio_fallback_once(reason: str) -> None:
    reason = str(reason or "unknown")
    if reason in _AUDIO_FALLBACK_WARNED:
        return
    _AUDIO_FALLBACK_WARNED.add(reason)
    logger.warning(
        "Audio-generated spectrogram requested but falling back to existing spectrogram (%s).",
        reason,
    )


def load_audio_spectrogram_cached(
    audio_path: str,
    *,
    win_dur_s: float,
    overlap: float,
    freq_min_hz: float,
    freq_max_hz: float,
) -> Optional[Dict[str, np.ndarray]]:
    if not audio_path or not os.path.exists(audio_path):
        return None
    key = _audio_spectrogram_cache_key(
        audio_path,
        win_dur_s=win_dur_s,
        overlap=overlap,
        freq_min_hz=freq_min_hz,
        freq_max_hz=freq_max_hz,
    )
    with _AUDIO_SPECTROGRAM_CACHE_LOCK:
        if key in audio_spectrogram_cache:
            return audio_spectrogram_cache[key]
    result = _load_audio_spectrogram_torch(
        audio_path,
        win_dur_s=win_dur_s,
        overlap=overlap,
        freq_min_hz=freq_min_hz,
        freq_max_hz=freq_max_hz,
    )
    with _AUDIO_SPECTROGRAM_CACHE_LOCK:
        audio_spectrogram_cache[key] = result
    return result


def load_spectrogram_cached(mat_path: str):
    if not mat_path or not os.path.exists(mat_path):
        return None
    key = os.path.abspath(mat_path)
    with _SPECTROGRAM_CACHE_LOCK:
        if key in spectrogram_cache:
            return spectrogram_cache[key]
    result = _load_mat(mat_path)
    with _SPECTROGRAM_CACHE_LOCK:
        spectrogram_cache[key] = result
    return result


def resolve_item_spectrogram_with_key(
    item: Optional[Dict[str, Any]],
    cfg: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, np.ndarray]], Optional[Tuple[Any, ...]]]:
    if not isinstance(item, dict):
        return None, None

    render_cfg = get_spectrogram_render_settings(cfg)
    source = render_cfg.get("source", SPECTROGRAM_SOURCE_EXISTING)
    mat_path = item.get("mat_path")
    audio_path = item.get("audio_path")

    if source == SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        if audio_path and os.path.exists(audio_path):
            key = _audio_spectrogram_cache_key(
                audio_path,
                win_dur_s=float(render_cfg["win_dur_s"]),
                overlap=float(render_cfg["overlap"]),
                freq_min_hz=float(render_cfg["freq_min_hz"]),
                freq_max_hz=float(render_cfg["freq_max_hz"]),
            )
            spec = load_audio_spectrogram_cached(
                audio_path,
                win_dur_s=float(render_cfg["win_dur_s"]),
                overlap=float(render_cfg["overlap"]),
                freq_min_hz=float(render_cfg["freq_min_hz"]),
                freq_max_hz=float(render_cfg["freq_max_hz"]),
            )
            if spec is not None:
                return _with_render_source(spec, source="audio_generated"), ("audio", key)
        if mat_path and os.path.exists(mat_path):
            spec = load_spectrogram_cached(mat_path)
            fallback_reason = "audio_unavailable_or_torch_missing"
            _warn_audio_fallback_once(fallback_reason)
            return (
                _with_render_source(spec, source="existing_fallback", reason=fallback_reason),
                ("mat", os.path.abspath(mat_path), fallback_reason),
            )
        _warn_audio_fallback_once("no_audio_no_mat")
        return None, None

    # Default: use existing spectrogram first.
    if mat_path and os.path.exists(mat_path):
        spec = load_spectrogram_cached(mat_path)
        return _with_render_source(spec, source="existing"), ("mat", os.path.abspath(mat_path))
    if audio_path and os.path.exists(audio_path):
        key = _audio_spectrogram_cache_key(
            audio_path,
            win_dur_s=float(render_cfg["win_dur_s"]),
            overlap=float(render_cfg["overlap"]),
            freq_min_hz=float(render_cfg["freq_min_hz"]),
            freq_max_hz=float(render_cfg["freq_max_hz"]),
        )
        spec = load_audio_spectrogram_cached(
            audio_path,
            win_dur_s=float(render_cfg["win_dur_s"]),
            overlap=float(render_cfg["overlap"]),
            freq_min_hz=float(render_cfg["freq_min_hz"]),
            freq_max_hz=float(render_cfg["freq_max_hz"]),
        )
        return _with_render_source(spec, source="audio_fallback"), ("audio-fallback", key)
    return None, None


def resolve_item_spectrogram(item: Optional[Dict[str, Any]], cfg: Optional[Dict[str, Any]]) -> Optional[Dict[str, np.ndarray]]:
    spec, _ = resolve_item_spectrogram_with_key(item, cfg)
    return spec


def estimate_page_audio_generation_work(
    items: Any,
    cfg: Optional[Dict[str, Any]],
    *,
    colormap: str = "default",
    y_axis_scale: str = "linear",
) -> Dict[str, Any]:
    render_cfg = get_spectrogram_render_settings(cfg)
    source = str(render_cfg.get("source", SPECTROGRAM_SOURCE_EXISTING))
    page_items = items if isinstance(items, list) else []
    total = len(page_items)

    status: Dict[str, Any] = {
        "source": source,
        "total": int(total),
        "eligible": 0,
        "pending": 0,
        "params": {
            "win_dur_s": float(render_cfg["win_dur_s"]),
            "overlap": float(render_cfg["overlap"]),
            "freq_min_hz": float(render_cfg["freq_min_hz"]),
            "freq_max_hz": float(render_cfg["freq_max_hz"]),
        },
    }

    if source != SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        return status
    if torch is None:
        return status

    for item in page_items:
        audio_key = _item_audio_generation_key(
            item,
            render_cfg=render_cfg,
        )
        if audio_key is None:
            continue
        status["eligible"] += 1
        image_key = _item_image_generation_key(
            item,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        if image_key is None or image_key not in image_cache:
            status["pending"] += 1

    return status


def _item_audio_generation_key(
    item: Any,
    *,
    render_cfg: Dict[str, Any],
) -> Optional[Tuple[Any, ...]]:
    if not isinstance(item, dict):
        return None

    source = str(render_cfg.get("source", SPECTROGRAM_SOURCE_EXISTING))
    audio_path = item.get("audio_path")
    if source != SPECTROGRAM_SOURCE_AUDIO_GENERATED or torch is None:
        return None
    if not audio_path or not os.path.exists(audio_path):
        return None
    try:
        return _audio_spectrogram_cache_key(
            audio_path,
            win_dur_s=float(render_cfg["win_dur_s"]),
            overlap=float(render_cfg["overlap"]),
            freq_min_hz=float(render_cfg["freq_min_hz"]),
            freq_max_hz=float(render_cfg["freq_max_hz"]),
        )
    except Exception:
        return None


def _item_image_generation_key(
    item: Any,
    cfg: Optional[Dict[str, Any]],
    *,
    colormap: str = "default",
    y_axis_scale: str = "linear",
) -> Optional[Tuple[Any, ...]]:
    if not isinstance(item, dict):
        return None

    render_cfg = get_spectrogram_render_settings(cfg)
    source = str(render_cfg.get("source", SPECTROGRAM_SOURCE_EXISTING))
    source_key: Optional[Tuple[Any, ...]] = None

    if source == SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        audio_key = _item_audio_generation_key(
            item,
            render_cfg=render_cfg,
        )
        if audio_key is not None:
            source_key = ("audio", audio_key)
    else:
        mat_path = item.get("mat_path")
        if mat_path and os.path.exists(mat_path):
            source_key = ("mat", os.path.abspath(mat_path))

    if source_key is None:
        return None

    return (
        "item",
        source_key,
        str(colormap or "default"),
        str(y_axis_scale or "linear"),
    )


def _prefetch_item_image(
    item: dict,
    *,
    cfg: Optional[Dict[str, Any]],
    colormap: str,
    y_axis_scale: str,
    dedupe_key: Tuple[Any, ...],
) -> None:
    try:
        generate_item_image_cached(
            item,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
    except Exception:
        logger.exception("Background image prefetch failed for item=%s", item.get("item_id"))
    finally:
        with _PREFETCH_LOCK:
            _PREFETCH_PENDING_KEYS.discard(dedupe_key)


def prefetch_page_images_in_background(
    page_items: Any,
    cfg: Optional[Dict[str, Any]],
    *,
    colormap: str = "default",
    y_axis_scale: str = "linear",
) -> int:
    render_cfg = get_spectrogram_render_settings(cfg)
    source = str(render_cfg.get("source", SPECTROGRAM_SOURCE_EXISTING))
    if source != SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        return 0
    if torch is None:
        return 0

    submitted = 0
    items = page_items if isinstance(page_items, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue

        image_key = _item_image_generation_key(
            item,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
        if image_key is None:
            continue
        if image_key in image_cache:
            continue

        dedupe_key = ("item_image", image_key)
        with _PREFETCH_LOCK:
            if dedupe_key in _PREFETCH_PENDING_KEYS:
                continue
            _PREFETCH_PENDING_KEYS.add(dedupe_key)

        _PREFETCH_EXECUTOR.submit(
            _prefetch_item_image,
            item,
            cfg=cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            dedupe_key=dedupe_key,
        )
        submitted += 1

    return submitted


def _prefetch_item_audio_spectrogram(
    item: dict,
    *,
    render_cfg: Dict[str, Any],
    dedupe_key: Tuple[Any, ...],
) -> None:
    try:
        audio_path = item.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            return
        load_audio_spectrogram_cached(
            audio_path,
            win_dur_s=float(render_cfg["win_dur_s"]),
            overlap=float(render_cfg["overlap"]),
            freq_min_hz=float(render_cfg["freq_min_hz"]),
            freq_max_hz=float(render_cfg["freq_max_hz"]),
        )
    except Exception:
        logger.exception("Background spectrogram prefetch failed for item=%s", item.get("item_id"))
    finally:
        with _PREFETCH_LOCK:
            _PREFETCH_PENDING_KEYS.discard(dedupe_key)


def prefetch_page_items_in_background(
    page_items: Any,
    cfg: Optional[Dict[str, Any]],
    *,
    colormap: str = "default",
    y_axis_scale: str = "linear",
) -> int:
    render_cfg = get_spectrogram_render_settings(cfg)
    source = str(render_cfg.get("source", SPECTROGRAM_SOURCE_EXISTING))
    if source != SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        return 0
    if torch is None:
        return 0

    submitted = 0
    items = page_items if isinstance(page_items, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue

        audio_key = _item_audio_generation_key(
            item,
            render_cfg=render_cfg,
        )
        if audio_key is None:
            continue
        if audio_key in audio_spectrogram_cache:
            continue

        dedupe_key = ("audio_spec", audio_key)
        with _PREFETCH_LOCK:
            if dedupe_key in _PREFETCH_PENDING_KEYS:
                continue
            _PREFETCH_PENDING_KEYS.add(dedupe_key)

        _PREFETCH_EXECUTOR.submit(
            _prefetch_item_audio_spectrogram,
            item,
            render_cfg=render_cfg,
            dedupe_key=dedupe_key,
        )
        submitted += 1

    return submitted


def schedule_prefetch_for_future_pages(
    all_items: Any,
    *,
    current_page: int,
    items_per_page: int,
    cfg: Optional[Dict[str, Any]],
    colormap: str = "default",
    y_axis_scale: str = "linear",
    pages_ahead: int = 1,
) -> int:
    items = all_items if isinstance(all_items, list) else []
    if not items:
        return 0
    if items_per_page <= 0:
        return 0
    if pages_ahead <= 0:
        return 0

    total_items = len(items)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    page_index = max(0, min(int(current_page or 0), total_pages - 1))
    last_page = min(total_pages - 1, page_index + int(pages_ahead))
    submitted = 0

    for idx in range(page_index + 1, last_page + 1):
        start_idx = idx * items_per_page
        end_idx = start_idx + items_per_page
        submitted += prefetch_page_items_in_background(
            items[start_idx:end_idx],
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
        )
    return submitted


def generate_image_cached(mat_path: str, colormap: str = "default", y_axis_scale: str = "linear"):
    cache_key = ("mat", mat_path, colormap, y_axis_scale)
    with _IMAGE_CACHE_LOCK:
        if cache_key in image_cache:
            return image_cache[cache_key]

    result = _generate_image(mat_path, colormap, y_axis_scale)
    with _IMAGE_CACHE_LOCK:
        image_cache[cache_key] = result
    return result


def _generate_image(mat_path: str, colormap: str = "default", y_axis_scale: str = "linear"):
    spectrogram = load_spectrogram_cached(mat_path)
    if spectrogram is None:
        return None
    return _generate_image_from_spectrogram_data(spectrogram, colormap=colormap, y_axis_scale=y_axis_scale)


def generate_item_image_cached(
    item: Optional[Dict[str, Any]],
    cfg: Optional[Dict[str, Any]],
    *,
    colormap: str = "default",
    y_axis_scale: str = "linear",
) -> Optional[str]:
    spectrogram, source_key = resolve_item_spectrogram_with_key(item, cfg)
    if spectrogram is None:
        return None
    cache_key = ("item", source_key, colormap, y_axis_scale)
    with _IMAGE_CACHE_LOCK:
        if cache_key in image_cache:
            return image_cache[cache_key]
    result = _generate_image_from_spectrogram_data(spectrogram, colormap=colormap, y_axis_scale=y_axis_scale)
    with _IMAGE_CACHE_LOCK:
        image_cache[cache_key] = result
    return result


def _generate_image_from_spectrogram_data(
    spectrogram: Dict[str, np.ndarray],
    colormap: str = "default",
    y_axis_scale: str = "linear",
) -> Optional[str]:
    if spectrogram is None:
        return None

    with _MATPLOTLIB_RENDER_LOCK:
        fig = Figure(figsize=(1.5, 1.5), facecolor="none")
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)

        if colormap == "hydrophone":
            cmap_array = colmap_hyd_py(36, 3)
            cmap = mcolors.ListedColormap(cmap_array)
        else:
            cmap = "viridis"

        psd = spectrogram["psd"]
        freq = spectrogram["freq"]
        time = spectrogram["time"]

        if len(time) > 0 and time[0] > 1000:
            time_plot = (time - time[0]) * 24 * 60
        else:
            time_plot = time - time[0] if len(time) > 0 else time

        if len(freq) > 0 and freq[-1] > 500:
            freq_plot = freq
        else:
            if len(freq) == 0:
                freq_plot = freq
            else:
                freq_plot = freq * 1000 if np.max(freq) < 1 else freq

        psd_valid = psd[np.isfinite(psd)]
        if len(psd_valid) > 0:
            vmin = np.percentile(psd_valid, 2)
            vmax = np.percentile(psd_valid, 98)
            if vmax - vmin < 0.1:
                vmin = np.min(psd_valid)
                vmax = np.max(psd_valid)
        else:
            vmin, vmax = -60, 0

        if y_axis_scale == "log":
            valid_freq_mask = freq_plot > 0
            if not np.any(valid_freq_mask):
                ax.imshow(
                    psd,
                    extent=[time_plot[0], time_plot[-1], freq_plot[0], freq_plot[-1]],
                    aspect="auto",
                    origin="lower",
                    cmap=cmap,
                    vmin=vmin,
                    vmax=vmax,
                )
            else:
                freq_for_plot = freq_plot[valid_freq_mask]
                psd_for_plot = psd[valid_freq_mask, :]
                min_freq = max(freq_for_plot[0], 0.1)
                max_freq = freq_for_plot[-1]
                ax.imshow(
                    psd_for_plot,
                    extent=[time_plot[0], time_plot[-1], min_freq, max_freq],
                    aspect="auto",
                    origin="lower",
                    cmap=cmap,
                    vmin=vmin,
                    vmax=vmax,
                )
                ax.set_yscale("log")
                ax.set_ylim(min_freq, max_freq)
        else:
            extent = [
                time_plot[0] if len(time_plot) > 0 else 0,
                time_plot[-1] if len(time_plot) > 0 else 1,
                freq_plot[0] if len(freq_plot) > 0 else 0,
                freq_plot[-1] if len(freq_plot) > 0 else 1,
            ]
            ax.imshow(
                psd,
                extent=extent,
                aspect="auto",
                origin="lower",
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
            )

        ax.axis("off")
        ax.set_position([0, 0, 1, 1])

        buf = BytesIO()
        fig.savefig(
            buf,
            format="png",
            bbox_inches="tight",
            pad_inches=0,
            facecolor="none",
            edgecolor="none",
            dpi=72,
        )
        data = base64.b64encode(buf.getbuffer()).decode("utf8")
        return f"data:image/png;base64,{data}"


def create_spectrogram_figure(spectrogram_data, colormap_value, y_axis_scale="linear"):
    if spectrogram_data is None:
        return go.Figure()

    psd = spectrogram_data["psd"]
    freq = spectrogram_data["freq"]
    time = spectrogram_data["time"]
    psd, freq, time = _downsample_for_modal_display(psd, freq, time)

    # Normalize time to start from 0 for better visualization.
    # This shows clip-relative duration on x-axis, which aligns with annotation_extent seconds.
    if len(time) > 0 and time[0] > 1000:
        # Julian days - convert to minutes relative to start
        time_plot = (time - time[0]) * 24 * 60
        x_label = "Time (minutes)"
        x_to_seconds = 60.0
    else:
        # Seconds - normalize to start from 0
        time_plot = time - time[0] if len(time) > 0 else time
        x_label = "Time (seconds)"
        x_to_seconds = 1.0

    # Intelligent frequency unit detection and scaling
    if len(freq) > 0:
        max_f = np.max(freq)
        if max_f > 1000:
            # Data is in Hz and has a high range -> convert to kHz for better readability
            freq_plot = freq / 1000
            y_unit = "kHz"
            y_to_hz = 1000.0
        elif max_f > 2:
            # Data is likely already in the correct range (e.g., 0-100 Hz or 0-100 kHz)
            # For low-frequency baleen whale data (5-100), we show it as Hz
            # If it were high frequency already in kHz, 100 kHz is also a common range.
            # We'll use Hz as the unit if max_f is between 2 and 1000, 
            # assuming baleen whale context or that the values represent the actual Hz.
            freq_plot = freq
            y_unit = "Hz" if max_f < 1000 else "kHz"
            y_to_hz = 1.0 if y_unit == "Hz" else 1000.0
        else:
            # Very small values -> likely already in kHz
            freq_plot = freq
            y_unit = "kHz"
            y_to_hz = 1000.0
    else:
        freq_plot = freq
        y_unit = "Hz"
        y_to_hz = 1.0

    time_plot = np.asarray(time_plot, dtype=np.float32)
    freq_plot = np.asarray(freq_plot, dtype=np.float32)

    # Determine appropriate color limits
    psd_valid = psd[np.isfinite(psd)]
    if len(psd_valid) > 0:
        zmin = np.percentile(psd_valid, 2)
        zmax = np.percentile(psd_valid, 98)
    else:
        zmin, zmax = -60, 0

    if colormap_value == "hydrophone":
        cmap_array = colmap_hyd_py(36, 3)
        colorscale = [[i / (len(cmap_array) - 1),
                       f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"]
                      for i, (r, g, b) in enumerate(cmap_array)]
    else:
        colorscale = "Viridis"

    if y_axis_scale == "log":
        y_axis_type = "log"
        y_axis_title = f"Frequency ({y_unit}) - Log Scale"
        # Ensure values for log scale are positive
        freq_plot = np.maximum(freq_plot, 0.001 if y_unit == "kHz" else 0.1).astype(np.float32)
    else:
        y_axis_type = "linear"
        y_axis_title = f"Frequency ({y_unit})"

    heatmap_z, heatmap_zmin, heatmap_zmax, colorbar = _quantize_modal_heatmap(psd, zmin, zmax)

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        z=heatmap_z,
        x=time_plot,
        y=freq_plot,
        colorscale=colorscale,
        zmin=heatmap_zmin,
        zmax=heatmap_zmax,
        colorbar=colorbar,
    ))

    # Add invisible playback position marker (will be controlled via JavaScript)
    fig.add_shape(
        type="line",
        x0=0, x1=0,
        y0=0, y1=1,
        yref="paper",
        editable=False,
        name="playback-marker",
        line=dict(
            color="rgba(255, 0, 0, 0)",
            width=2,
            dash="solid"
        )
    )
    
    render_source = str(spectrogram_data.get("_render_source", "existing")) if isinstance(spectrogram_data, dict) else "existing"
    render_reason = str(spectrogram_data.get("_render_reason", "")) if isinstance(spectrogram_data, dict) else ""
    source_label = {
        "existing": "Source: existing spectrogram",
        "audio_generated": "Source: generated from audio",
        "audio_fallback": "Source: generated from audio (fallback)",
        "existing_fallback": "Source: existing spectrogram (fallback)",
    }.get(render_source, f"Source: {render_source}")
    if render_reason:
        source_label = f"{source_label} [{render_reason}]"

    if len(time_plot):
        x_min = float(np.min(time_plot))
        x_max = float(np.max(time_plot))
    else:
        x_min = 0.0
        x_max = 1.0
    if len(freq_plot):
        y_min = float(np.min(freq_plot))
        y_max = float(np.max(freq_plot))
    else:
        y_min = 0.0
        y_max = 1.0
    render_signature = f"{render_source}|{render_reason}|{x_min:.6f}|{x_max:.6f}|{y_min:.6f}|{y_max:.6f}|{psd.shape[0]}x{psd.shape[1]}"

    fig.update_layout(
        title=dict(text=""),
        xaxis=dict(title=x_label, showgrid=True, tickformat=".2f"),
        yaxis=dict(title=y_axis_title, showgrid=True, type=y_axis_type),
        margin=dict(l=40, r=20, t=20, b=40),
        height=500,
        dragmode="pan",
        clickmode="event+select",
        template="plotly_white",
        # Needed to convert drawn/edited plot coordinates back to schema units.
        meta={
            "x_to_seconds": x_to_seconds,
            "y_to_hz": y_to_hz,
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "x_unit": "minutes" if x_to_seconds == 60.0 else "seconds",
            "y_unit": y_unit,
            "render_source": render_source,
            "render_reason": render_reason,
        },
        uirevision=render_signature,
    )

    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.01,
        y=0.99,
        xanchor="left",
        yanchor="top",
        showarrow=False,
        text=source_label,
        font=dict(size=11, color="#8b949e"),
        bgcolor="rgba(0,0,0,0.25)",
        bordercolor="rgba(120,120,120,0.4)",
        borderwidth=1,
        borderpad=4,
    )

    return fig
