import base64
from io import BytesIO
import logging
import math
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
import scipy.signal as scipy_signal
import soundfile as sf
from cachetools import LRUCache
from concurrent.futures import ThreadPoolExecutor
try:
    import torch
except Exception:  # pragma: no cover - optional dependency at runtime
    torch = None

from app.utils.colmap_hyd import colmap_hyd_py
from app.defaults import DEFAULT_CACHE_MAX_SIZE

logger = logging.getLogger(__name__)

spectrogram_cache = LRUCache(maxsize=DEFAULT_CACHE_MAX_SIZE)
audio_spectrogram_cache = LRUCache(maxsize=DEFAULT_CACHE_MAX_SIZE)
image_cache = LRUCache(maxsize=DEFAULT_CACHE_MAX_SIZE * 2)

SPECTROGRAM_SOURCE_EXISTING = "existing"
SPECTROGRAM_SOURCE_AUDIO_GENERATED = "audio_generated"
MODAL_TRANSPORT_FLOAT64 = "float64"
MODAL_TRANSPORT_FLOAT32 = "float32"
MODAL_TRANSPORT_UINT16 = "uint16"
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
        maxsize = DEFAULT_CACHE_MAX_SIZE
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


def _normalize_modal_transport_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {MODAL_TRANSPORT_FLOAT64, MODAL_TRANSPORT_FLOAT32, MODAL_TRANSPORT_UINT16}:
        return normalized
    if normalized in {"f32", "heatmap-f32", "heatmap_float32"}:
        return MODAL_TRANSPORT_FLOAT32
    if normalized in {"f64", "heatmap-f64", "heatmap_float64"}:
        return MODAL_TRANSPORT_FLOAT64
    if normalized in {"u16", "heatmap-u16", "heatmap_uint16"}:
        return MODAL_TRANSPORT_UINT16
    return MODAL_TRANSPORT_FLOAT32


def get_modal_transport_mode(cfg: Optional[Dict[str, Any]]) -> str:
    display_cfg = (cfg or {}).get("display", {})
    if not isinstance(display_cfg, dict):
        display_cfg = {}
    configured = display_cfg.get("modal_transport")
    if configured:
        return _normalize_modal_transport_mode(configured)
    return _normalize_modal_transport_mode(
        os.getenv("HYDRO_MODAL_TRANSPORT_MODE", MODAL_TRANSPORT_FLOAT32)
    )


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


def _optional_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_limit_cache_token(value: Any) -> Optional[float]:
    parsed = _optional_float(value)
    if parsed is None or not np.isfinite(parsed):
        return None
    return round(float(parsed), 6)


def _prepare_spectrogram_plot_axes(spectrogram_data: Dict[str, np.ndarray]) -> Dict[str, Any]:
    psd = spectrogram_data["psd"]
    freq = spectrogram_data["freq"]
    time = spectrogram_data["time"]

    if len(time) > 0 and time[0] > 1000:
        time_plot = (time - time[0]) * 24 * 60
        x_label = "Time (minutes)"
        x_to_seconds = 60.0
    else:
        time_plot = time - time[0] if len(time) > 0 else time
        x_label = "Time (seconds)"
        x_to_seconds = 1.0

    if len(freq) > 0:
        max_f = float(np.max(freq))
        if max_f > 1000:
            freq_plot = freq / 1000
            y_unit = "kHz"
            y_to_hz = 1000.0
        elif max_f > 2:
            freq_plot = freq
            y_unit = "Hz" if max_f < 1000 else "kHz"
            y_to_hz = 1.0 if y_unit == "Hz" else 1000.0
        else:
            freq_plot = freq
            y_unit = "kHz"
            y_to_hz = 1000.0
    else:
        freq_plot = freq
        y_unit = "Hz"
        y_to_hz = 1.0

    return {
        "psd": psd,
        "time_plot": np.asarray(time_plot),
        "x_label": x_label,
        "x_to_seconds": x_to_seconds,
        "freq_plot": np.asarray(freq_plot),
        "y_unit": y_unit,
        "y_to_hz": y_to_hz,
    }


def _compute_color_limit_summary(psd: np.ndarray) -> Dict[str, float]:
    psd_valid = psd[np.isfinite(psd)]
    if len(psd_valid) > 0:
        data_min = float(np.min(psd_valid))
        data_max = float(np.max(psd_valid))
        auto_min = float(np.percentile(psd_valid, 2))
        auto_max = float(np.percentile(psd_valid, 98))
        if auto_max - auto_min < 0.1:
            auto_min = data_min
            auto_max = data_max
    else:
        data_min, data_max = -60.0, 0.0
        auto_min, auto_max = -60.0, 0.0

    if auto_max <= auto_min:
        auto_max = auto_min + 1.0
    if data_max <= data_min:
        data_max = data_min + 1.0

    return {
        "data_min": data_min,
        "data_max": data_max,
        "auto_min": auto_min,
        "auto_max": auto_max,
    }


def summarize_spectrogram_display_ranges(
    spectrogram_data: Optional[Dict[str, np.ndarray]],
) -> Dict[str, float]:
    if spectrogram_data is None:
        return {}

    plot_axes = _prepare_spectrogram_plot_axes(spectrogram_data)
    freq_plot = np.asarray(plot_axes["freq_plot"], dtype=np.float64)
    finite_freq = freq_plot[np.isfinite(freq_plot)] if freq_plot.size else np.asarray([], dtype=np.float64)

    if finite_freq.size:
        freq_data_min_plot = float(np.min(finite_freq))
        freq_data_max_plot = float(np.max(finite_freq))
    else:
        freq_data_min_plot = 0.0
        freq_data_max_plot = 1.0

    positive_freq = finite_freq[finite_freq > 0]
    if positive_freq.size:
        freq_positive_min_plot = float(np.min(positive_freq))
    else:
        freq_positive_min_plot = 0.001 if plot_axes["y_unit"] == "kHz" else 0.1

    color_summary = _compute_color_limit_summary(np.asarray(plot_axes["psd"]))
    y_to_hz = float(plot_axes["y_to_hz"])

    return {
        "freq_data_min_hz": float(freq_data_min_plot * y_to_hz),
        "freq_data_max_hz": float(freq_data_max_plot * y_to_hz),
        "freq_positive_min_hz": float(freq_positive_min_plot * y_to_hz),
        "color_data_min": float(color_summary["data_min"]),
        "color_data_max": float(color_summary["data_max"]),
        "color_auto_min": float(color_summary["auto_min"]),
        "color_auto_max": float(color_summary["auto_max"]),
    }


def _resolve_color_limits(
    *,
    color_min: Any,
    color_max: Any,
    auto_min: float,
    auto_max: float,
) -> Tuple[float, float]:
    zmin = _optional_float(color_min)
    zmax = _optional_float(color_max)
    if zmin is None:
        zmin = float(auto_min)
    if zmax is None:
        zmax = float(auto_max)
    if zmax <= zmin:
        zmin = float(auto_min)
        zmax = float(auto_max)
    if zmax <= zmin:
        zmax = zmin + 1.0
    return float(zmin), float(zmax)


def _resolve_y_axis_window(
    *,
    freq_plot: np.ndarray,
    y_to_hz: float,
    y_unit: str,
    y_axis_scale: str,
    y_axis_min_hz: Any,
    y_axis_max_hz: Any,
) -> Dict[str, float]:
    if len(freq_plot):
        finite_freq = np.asarray(freq_plot[np.isfinite(freq_plot)], dtype=np.float64)
    else:
        finite_freq = np.asarray([], dtype=np.float64)

    if finite_freq.size:
        data_min_plot = float(np.min(finite_freq))
        data_max_plot = float(np.max(finite_freq))
    else:
        data_min_plot = 0.0
        data_max_plot = 1.0

    min_allowed_plot = data_min_plot
    if y_axis_scale == "log":
        positive_freq = finite_freq[finite_freq > 0]
        if positive_freq.size:
            min_allowed_plot = float(np.min(positive_freq))
        else:
            min_allowed_plot = 0.001 if y_unit == "kHz" else 0.1
        data_min_plot = max(min_allowed_plot, data_min_plot)
        data_max_plot = max(min_allowed_plot, data_max_plot)

    default_min_hz = data_min_plot * y_to_hz
    default_max_hz = data_max_plot * y_to_hz
    requested_min_hz = _optional_float(y_axis_min_hz)
    requested_max_hz = _optional_float(y_axis_max_hz)

    lower_plot = data_min_plot if requested_min_hz is None else requested_min_hz / y_to_hz
    upper_plot = data_max_plot if requested_max_hz is None else requested_max_hz / y_to_hz

    lower_plot = max(min_allowed_plot, min(data_max_plot, float(lower_plot)))
    upper_plot = max(min_allowed_plot, min(data_max_plot, float(upper_plot)))

    if upper_plot <= lower_plot:
        lower_plot = data_min_plot
        upper_plot = data_max_plot
    if upper_plot <= lower_plot:
        upper_plot = lower_plot * 10.0 if y_axis_scale == "log" else lower_plot + 1.0

    return {
        "data_min_hz": float(default_min_hz),
        "data_max_hz": float(default_max_hz),
        "positive_min_hz": float(min_allowed_plot * y_to_hz),
        "display_min_hz": float(lower_plot * y_to_hz),
        "display_max_hz": float(upper_plot * y_to_hz),
        "display_min_plot": float(lower_plot),
        "display_max_plot": float(upper_plot),
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
        "torch_cpu_stft_v2",
    )


def _downsample_audio_for_requested_band(
    audio: np.ndarray,
    sample_rate: int,
    *,
    freq_max_hz: float,
) -> Tuple[np.ndarray, int]:
    if sample_rate <= 0:
        return audio, sample_rate

    # The fin whale review defaults only need the low-frequency band. Reducing
    # the sample rate before STFT avoids computing thousands of unused bins.
    target_rate = int(min(sample_rate, max(512, math.ceil(float(freq_max_hz) * 4.0))))
    if target_rate <= 0 or target_rate >= sample_rate:
        return audio, sample_rate

    common = math.gcd(int(sample_rate), target_rate)
    up = target_rate // common
    down = int(sample_rate) // common
    try:
        downsampled = scipy_signal.resample_poly(audio, up, down)
    except Exception as exc:
        logger.warning("Audio downsampling failed for spectrogram generation: %s", exc)
        return audio, sample_rate

    return np.asarray(downsampled, dtype=np.float32), target_rate


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
    audio, sr = _downsample_audio_for_requested_band(
        audio,
        sr,
        freq_max_hz=float(freq_max_hz),
    )
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
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
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
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )
        if image_key is None or image_key not in image_cache:
            status["pending"] += 1

    return status


def _item_spectrogram_generation_key(
    item: Any,
    cfg: Optional[Dict[str, Any]],
) -> Optional[Tuple[Any, ...]]:
    if not isinstance(item, dict):
        return None

    render_cfg = get_spectrogram_render_settings(cfg)
    source = str(render_cfg.get("source", SPECTROGRAM_SOURCE_EXISTING))
    if source == SPECTROGRAM_SOURCE_AUDIO_GENERATED:
        audio_key = _item_audio_generation_key(item, render_cfg=render_cfg)
        if audio_key is not None:
            return ("audio", audio_key)

    mat_path = item.get("mat_path")
    if mat_path and os.path.exists(mat_path):
        return ("mat", os.path.abspath(mat_path))

    audio_path = item.get("audio_path")
    if audio_path and os.path.exists(audio_path):
        try:
            audio_key = _audio_spectrogram_cache_key(
                audio_path,
                win_dur_s=float(render_cfg["win_dur_s"]),
                overlap=float(render_cfg["overlap"]),
                freq_min_hz=float(render_cfg["freq_min_hz"]),
                freq_max_hz=float(render_cfg["freq_max_hz"]),
            )
        except Exception:
            return None
        return ("audio-fallback", audio_key)

    return None


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
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
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
        _display_limit_cache_token(y_axis_min_hz),
        _display_limit_cache_token(y_axis_max_hz),
        _display_limit_cache_token(color_min),
        _display_limit_cache_token(color_max),
    )


def _prefetch_item_image(
    item: dict,
    *,
    cfg: Optional[Dict[str, Any]],
    colormap: str,
    y_axis_scale: str,
    y_axis_min_hz: Any,
    y_axis_max_hz: Any,
    color_min: Any,
    color_max: Any,
    dedupe_key: Tuple[Any, ...],
) -> None:
    try:
        generate_item_image_cached(
            item,
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
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
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
) -> int:
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
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
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
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
            dedupe_key=dedupe_key,
        )
        submitted += 1

    return submitted


def _prefetch_item_modal_spectrogram(
    item: dict,
    *,
    cfg: Optional[Dict[str, Any]],
    dedupe_key: Tuple[Any, ...],
) -> None:
    try:
        resolve_item_spectrogram(item, cfg)
    except Exception:
        logger.exception("Background modal spectrogram prefetch failed for item=%s", item.get("item_id"))
    finally:
        with _PREFETCH_LOCK:
            _PREFETCH_PENDING_KEYS.discard(dedupe_key)


def prefetch_page_modal_spectrograms_in_background(
    page_items: Any,
    cfg: Optional[Dict[str, Any]],
) -> int:
    submitted = 0
    items = page_items if isinstance(page_items, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue

        spectrogram_key = _item_spectrogram_generation_key(item, cfg)
        if spectrogram_key is None:
            continue

        dedupe_key = ("modal_spectrogram", spectrogram_key)
        with _PREFETCH_LOCK:
            if dedupe_key in _PREFETCH_PENDING_KEYS:
                continue
            _PREFETCH_PENDING_KEYS.add(dedupe_key)

        _PREFETCH_EXECUTOR.submit(
            _prefetch_item_modal_spectrogram,
            item,
            cfg=cfg,
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
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
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
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
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
        submitted += prefetch_page_images_in_background(
            items[start_idx:end_idx],
            cfg,
            colormap=colormap,
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
            color_min=color_min,
            color_max=color_max,
        )
    return submitted


def schedule_modal_prefetch_for_future_pages(
    all_items: Any,
    *,
    current_page: int,
    items_per_page: int,
    cfg: Optional[Dict[str, Any]],
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
        submitted += prefetch_page_modal_spectrograms_in_background(
            items[start_idx:end_idx],
            cfg,
        )

    return submitted


def generate_image_cached(
    mat_path: str,
    colormap: str = "default",
    y_axis_scale: str = "linear",
    *,
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
):
    cache_key = (
        "mat",
        mat_path,
        colormap,
        y_axis_scale,
        _display_limit_cache_token(y_axis_min_hz),
        _display_limit_cache_token(y_axis_max_hz),
        _display_limit_cache_token(color_min),
        _display_limit_cache_token(color_max),
    )
    with _IMAGE_CACHE_LOCK:
        if cache_key in image_cache:
            return image_cache[cache_key]

    result = _generate_image(
        mat_path,
        colormap,
        y_axis_scale,
        y_axis_min_hz=y_axis_min_hz,
        y_axis_max_hz=y_axis_max_hz,
        color_min=color_min,
        color_max=color_max,
    )
    with _IMAGE_CACHE_LOCK:
        image_cache[cache_key] = result
    return result


def _generate_image(
    mat_path: str,
    colormap: str = "default",
    y_axis_scale: str = "linear",
    *,
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
):
    spectrogram = load_spectrogram_cached(mat_path)
    if spectrogram is None:
        return None
    return _generate_image_from_spectrogram_data(
        spectrogram,
        colormap=colormap,
        y_axis_scale=y_axis_scale,
        y_axis_min_hz=y_axis_min_hz,
        y_axis_max_hz=y_axis_max_hz,
        color_min=color_min,
        color_max=color_max,
    )


def generate_item_image_cached(
    item: Optional[Dict[str, Any]],
    cfg: Optional[Dict[str, Any]],
    *,
    colormap: str = "default",
    y_axis_scale: str = "linear",
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
) -> Optional[str]:
    spectrogram, source_key = resolve_item_spectrogram_with_key(item, cfg)
    if spectrogram is None:
        return None
    cache_key = (
        "item",
        source_key,
        colormap,
        y_axis_scale,
        _display_limit_cache_token(y_axis_min_hz),
        _display_limit_cache_token(y_axis_max_hz),
        _display_limit_cache_token(color_min),
        _display_limit_cache_token(color_max),
    )
    with _IMAGE_CACHE_LOCK:
        if cache_key in image_cache:
            return image_cache[cache_key]
    result = _generate_image_from_spectrogram_data(
        spectrogram,
        colormap=colormap,
        y_axis_scale=y_axis_scale,
        y_axis_min_hz=y_axis_min_hz,
        y_axis_max_hz=y_axis_max_hz,
        color_min=color_min,
        color_max=color_max,
    )
    with _IMAGE_CACHE_LOCK:
        image_cache[cache_key] = result
    return result


def _generate_image_from_spectrogram_data(
    spectrogram: Dict[str, np.ndarray],
    colormap: str = "default",
    y_axis_scale: str = "linear",
    *,
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
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

        plot_axes = _prepare_spectrogram_plot_axes(spectrogram)
        psd = plot_axes["psd"]
        time_plot = plot_axes["time_plot"]
        freq_plot = np.asarray(plot_axes["freq_plot"], dtype=np.float64)
        color_summary = _compute_color_limit_summary(psd)
        vmin, vmax = _resolve_color_limits(
            color_min=color_min,
            color_max=color_max,
            auto_min=color_summary["auto_min"],
            auto_max=color_summary["auto_max"],
        )
        y_window = _resolve_y_axis_window(
            freq_plot=freq_plot,
            y_to_hz=plot_axes["y_to_hz"],
            y_unit=plot_axes["y_unit"],
            y_axis_scale=y_axis_scale,
            y_axis_min_hz=y_axis_min_hz,
            y_axis_max_hz=y_axis_max_hz,
        )

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
                min_freq = float(freq_for_plot[0])
                max_freq = float(freq_for_plot[-1])
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
                ax.set_ylim(y_window["display_min_plot"], y_window["display_max_plot"])
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
            ax.set_ylim(y_window["display_min_plot"], y_window["display_max_plot"])

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


def _build_modal_heatmap_transport(
    psd: np.ndarray,
    zmin: float,
    zmax: float,
    transport_mode: str,
) -> Tuple[np.ndarray, float, float, Dict[str, Any]]:
    mode = _normalize_modal_transport_mode(transport_mode)
    if mode == MODAL_TRANSPORT_UINT16:
        max_level = np.iinfo(np.uint16).max
        span = max(1e-9, float(zmax) - float(zmin))
        normalized = (np.asarray(psd, dtype=np.float32) - float(zmin)) / span
        normalized = np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0)
        normalized = np.clip(normalized, 0.0, 1.0)
        quantized = np.rint(normalized * max_level).astype(np.uint16)
        tickvals = np.linspace(0, max_level, num=6, dtype=np.float32)
        ticktext = [
            f"{(float(zmin) + (float(val) / max_level) * span):.1f}"
            for val in tickvals
        ]
        return (
            quantized,
            0.0,
            float(max_level),
            {
                "title": "dB/Hz",
                "tickvals": tickvals,
                "ticktext": ticktext,
            },
        )
    if mode == MODAL_TRANSPORT_FLOAT32:
        return np.asarray(psd, dtype=np.float32), float(zmin), float(zmax), {"title": "dB/Hz"}
    return np.asarray(psd), float(zmin), float(zmax), {"title": "dB/Hz"}


def create_spectrogram_figure(
    spectrogram_data,
    colormap_value,
    y_axis_scale="linear",
    *,
    cfg: Optional[Dict[str, Any]] = None,
    transport_mode: Optional[str] = None,
    y_axis_min_hz: Any = None,
    y_axis_max_hz: Any = None,
    color_min: Any = None,
    color_max: Any = None,
):
    if spectrogram_data is None:
        return go.Figure()

    plot_axes = _prepare_spectrogram_plot_axes(spectrogram_data)
    psd = plot_axes["psd"]
    time_plot = plot_axes["time_plot"]
    x_label = plot_axes["x_label"]
    x_to_seconds = plot_axes["x_to_seconds"]
    freq_plot = np.asarray(plot_axes["freq_plot"], dtype=np.float64)
    y_unit = plot_axes["y_unit"]
    y_to_hz = plot_axes["y_to_hz"]
    resolved_transport_mode = _normalize_modal_transport_mode(
        transport_mode if transport_mode is not None else get_modal_transport_mode(cfg)
    )

    axis_dtype = np.float32 if resolved_transport_mode in {MODAL_TRANSPORT_FLOAT32, MODAL_TRANSPORT_UINT16} else None
    if axis_dtype is not None:
        time_plot = np.asarray(time_plot, dtype=axis_dtype)
        freq_plot = np.asarray(freq_plot, dtype=axis_dtype)
    else:
        time_plot = np.asarray(time_plot)
        freq_plot = np.asarray(freq_plot)

    color_summary = _compute_color_limit_summary(psd)
    zmin, zmax = _resolve_color_limits(
        color_min=color_min,
        color_max=color_max,
        auto_min=color_summary["auto_min"],
        auto_max=color_summary["auto_max"],
    )

    if colormap_value == "hydrophone":
        cmap_array = colmap_hyd_py(36, 3)
        colorscale = [[i / (len(cmap_array) - 1),
                       f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"]
                      for i, (r, g, b) in enumerate(cmap_array)]
    else:
        colorscale = "Viridis"

    y_window = _resolve_y_axis_window(
        freq_plot=np.asarray(freq_plot, dtype=np.float64),
        y_to_hz=y_to_hz,
        y_unit=y_unit,
        y_axis_scale=y_axis_scale,
        y_axis_min_hz=y_axis_min_hz,
        y_axis_max_hz=y_axis_max_hz,
    )
    if y_axis_scale == "log":
        y_axis_type = "log"
        y_axis_title = f"Frequency ({y_unit}) - Log Scale"
        positive_floor = y_window["display_min_plot"]
        freq_plot = np.maximum(freq_plot, positive_floor)
        y_axis_range = [
            float(np.log10(y_window["display_min_plot"])),
            float(np.log10(y_window["display_max_plot"])),
        ]
    else:
        y_axis_type = "linear"
        y_axis_title = f"Frequency ({y_unit})"
        y_axis_range = [y_window["display_min_plot"], y_window["display_max_plot"]]

    heatmap_z, heatmap_zmin, heatmap_zmax, colorbar = _build_modal_heatmap_transport(
        psd,
        zmin,
        zmax,
        resolved_transport_mode,
    )

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
    y_min = float(y_window["display_min_plot"])
    y_max = float(y_window["display_max_plot"])
    render_signature = (
        f"{render_source}|{render_reason}|{resolved_transport_mode}|"
        f"{x_min:.6f}|{x_max:.6f}|{y_min:.6f}|{y_max:.6f}|"
        f"{zmin:.6f}|{zmax:.6f}|{psd.shape[0]}x{psd.shape[1]}"
    )

    fig.update_layout(
        title=dict(text=""),
        xaxis=dict(title=x_label, showgrid=True, tickformat=".2f"),
        yaxis=dict(title=y_axis_title, showgrid=True, type=y_axis_type, range=y_axis_range),
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
            "data_y_min_hz": y_window["data_min_hz"],
            "data_y_max_hz": y_window["data_max_hz"],
            "positive_y_min_hz": y_window["positive_min_hz"],
            "display_y_min_hz": y_window["display_min_hz"],
            "display_y_max_hz": y_window["display_max_hz"],
            "auto_color_min": color_summary["auto_min"],
            "auto_color_max": color_summary["auto_max"],
            "data_color_min": color_summary["data_min"],
            "data_color_max": color_summary["data_max"],
            "display_color_min": zmin,
            "display_color_max": zmax,
            "x_unit": "minutes" if x_to_seconds == 60.0 else "seconds",
            "y_unit": y_unit,
            "transport_mode": resolved_transport_mode,
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
