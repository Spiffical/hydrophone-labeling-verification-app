"""Helpers for alternate audio playback transports."""

from __future__ import annotations

import functools
import hashlib
import os
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Optional, Tuple


DEFAULT_AUDIO_TRANSPORT = "direct"
DEFAULT_AUDIO_MP3_BITRATE = "128k"
# flac_resampled: a lossless FLAC at this rate, which keeps 0-7 kHz unchanged
# (fin whale calls and knocks) at about the size of a 128k MP3. Not for clicks
# or whistles, which need the full band.
DEFAULT_AUDIO_FLAC_SAMPLE_RATE = 16000
DEFAULT_AUDIO_CACHE_DIR = "/tmp/hydrophone_audio_transport"
AUDIO_TRANSPORTS = ("direct", "mp3_cached", "flac_resampled")
# Rates flac_resampled accepts, from the config or a request.
_FLAC_RATES = (8000, 16000, 22050, 24000, 32000, 44100, 48000)

_LOCK_REGISTRY: dict[str, threading.Lock] = {}
_LOCK_REGISTRY_GUARD = threading.Lock()
_PREFETCH_MAX_WORKERS = max(1, min(2, ((os.cpu_count() or 2) // 2) or 1))
_PREFETCH_MAX_PENDING = max(2, _PREFETCH_MAX_WORKERS * 4)
_PREFETCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=_PREFETCH_MAX_WORKERS,
    thread_name_prefix="audio-prefetch",
)
_PREFETCH_PENDING_KEYS: set[str] = set()
_PREFETCH_PENDING_GUARD = threading.Lock()
_PREFETCH_PENDING_SLOTS = threading.BoundedSemaphore(_PREFETCH_MAX_PENDING)


def normalize_audio_transport(transport: Optional[str]) -> str:
    candidate = str(transport or DEFAULT_AUDIO_TRANSPORT).strip().lower()
    if candidate in AUDIO_TRANSPORTS:
        return candidate
    return DEFAULT_AUDIO_TRANSPORT


def normalize_flac_sample_rate(sample_rate) -> int:
    try:
        rate = int(float(sample_rate))
    except (TypeError, ValueError):
        return DEFAULT_AUDIO_FLAC_SAMPLE_RATE
    return rate if rate in _FLAC_RATES else DEFAULT_AUDIO_FLAC_SAMPLE_RATE


def build_audio_transport_query(
    *,
    transport: Optional[str],
    mp3_bitrate: Optional[str] = None,
    flac_sample_rate: Optional[int] = None,
) -> str:
    normalized_transport = normalize_audio_transport(transport)
    if normalized_transport == DEFAULT_AUDIO_TRANSPORT:
        return ""

    query_parts = [f"transport={normalized_transport}"]
    bitrate = str(mp3_bitrate or DEFAULT_AUDIO_MP3_BITRATE).strip()
    if normalized_transport == "mp3_cached" and bitrate:
        query_parts.append(f"mp3_bitrate={bitrate}")
    if normalized_transport == "flac_resampled":
        query_parts.append(f"sample_rate={normalize_flac_sample_rate(flac_sample_rate)}")

    return "?" + "&".join(query_parts)


def resolve_audio_delivery_path(
    audio_path: Optional[str],
    *,
    transport: Optional[str],
    mp3_bitrate: Optional[str] = None,
    flac_sample_rate: Optional[int] = None,
    cache_dir: Optional[str] = None,
) -> Optional[str]:
    if not audio_path or not os.path.exists(audio_path):
        return None

    cached = _cached_transport(transport, mp3_bitrate=mp3_bitrate, flac_sample_rate=flac_sample_rate)
    if not cached:
        return os.path.abspath(audio_path)
    variant, extension, encode = cached
    return _ensure_cached(
        audio_path,
        variant=variant,
        extension=extension,
        cache_dir=cache_dir or DEFAULT_AUDIO_CACHE_DIR,
        encode=encode,
    )


def prewarm_audio_delivery_path(
    audio_path: Optional[str],
    *,
    transport: Optional[str],
    mp3_bitrate: Optional[str] = None,
    flac_sample_rate: Optional[int] = None,
    cache_dir: Optional[str] = None,
) -> bool:
    """Warm the playback transport for a single item without blocking the caller."""
    if not audio_path:
        return False

    cached = _cached_transport(transport, mp3_bitrate=mp3_bitrate, flac_sample_rate=flac_sample_rate)
    if not cached:
        return False

    variant, extension, encode = cached
    resolved_cache_dir = cache_dir or DEFAULT_AUDIO_CACHE_DIR
    target_info = _build_cached_target(audio_path, variant=variant, extension=extension, cache_dir=resolved_cache_dir)
    if not target_info:
        return False

    source_path, target_path, cache_key = target_info
    if _is_ready_cached(target_path):
        return False

    if not _PREFETCH_PENDING_SLOTS.acquire(blocking=False):
        return False

    with _PREFETCH_PENDING_GUARD:
        if cache_key in _PREFETCH_PENDING_KEYS:
            _PREFETCH_PENDING_SLOTS.release()
            return False
        _PREFETCH_PENDING_KEYS.add(cache_key)

    try:
        future = _PREFETCH_EXECUTOR.submit(
            _ensure_cached,
            source_path,
            variant=variant,
            extension=extension,
            cache_dir=resolved_cache_dir,
            encode=encode,
        )
    except Exception:
        with _PREFETCH_PENDING_GUARD:
            _PREFETCH_PENDING_KEYS.discard(cache_key)
        _PREFETCH_PENDING_SLOTS.release()
        return False

    def _release(_future) -> None:
        with _PREFETCH_PENDING_GUARD:
            _PREFETCH_PENDING_KEYS.discard(cache_key)
        _PREFETCH_PENDING_SLOTS.release()

    future.add_done_callback(_release)
    return True


def prewarm_audio_delivery_paths(
    audio_paths: Iterable[Optional[str]],
    *,
    transport: Optional[str],
    mp3_bitrate: Optional[str] = None,
    flac_sample_rate: Optional[int] = None,
    cache_dir: Optional[str] = None,
) -> int:
    """Best-effort warmup for a small batch of candidate audio paths."""
    scheduled = 0
    seen_paths: set[str] = set()
    for audio_path in audio_paths or []:
        if not audio_path:
            continue
        normalized_path = os.path.abspath(audio_path)
        if normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        if prewarm_audio_delivery_path(
            normalized_path,
            transport=transport,
            mp3_bitrate=mp3_bitrate,
            flac_sample_rate=flac_sample_rate,
            cache_dir=cache_dir,
        ):
            scheduled += 1
    return scheduled


def _cached_transport(
    transport: Optional[str],
    *,
    mp3_bitrate: Optional[str],
    flac_sample_rate: Optional[int],
) -> Optional[Tuple[str, str, Callable[[str, str], bool]]]:
    """(cache variant, file extension, encode) for a transport that serves a cached
    copy of the audio, or None to serve the source file."""
    normalized_transport = normalize_audio_transport(transport)
    if normalized_transport == "mp3_cached":
        bitrate = str(mp3_bitrate or DEFAULT_AUDIO_MP3_BITRATE).strip()
        return bitrate, "mp3", functools.partial(_encode_mp3, bitrate=bitrate)
    if normalized_transport == "flac_resampled":
        rate = normalize_flac_sample_rate(flac_sample_rate)
        return f"flac@{rate}", "flac", functools.partial(_encode_resampled_flac, sample_rate=rate)
    return None


def _build_cached_target(
    audio_path: str,
    *,
    variant: str,
    extension: str,
    cache_dir: str,
) -> Optional[Tuple[str, str, str]]:
    source_path = os.path.abspath(audio_path)
    if not os.path.exists(source_path):
        return None

    stat = os.stat(source_path)
    cache_key = hashlib.sha256(
        f"{source_path}|{stat.st_mtime_ns}|{stat.st_size}|{variant}".encode("utf-8")
    ).hexdigest()
    target_path = os.path.join(os.path.abspath(cache_dir), f"{cache_key}.{extension}")
    return source_path, target_path, cache_key


def _is_ready_cached(target_path: str) -> bool:
    try:
        return os.path.exists(target_path) and os.path.getsize(target_path) > 0
    except OSError:
        return False


def _ensure_cached(
    audio_path: str,
    *,
    variant: str,
    extension: str,
    cache_dir: str,
    encode: Callable[[str, str], bool],
) -> Optional[str]:
    """The cached copy of the audio, made once with encode(source, tmp_path). An
    encode that returns False or fails leaves the source to be served as it is."""
    target_info = _build_cached_target(audio_path, variant=variant, extension=extension, cache_dir=cache_dir)
    if not target_info:
        return None

    source_path, target_path, cache_key = target_info
    if _is_ready_cached(target_path):
        return target_path

    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)
    lock = _get_lock(cache_key)
    with lock:
        if _is_ready_cached(target_path):
            return target_path

        tmp_path = os.path.join(target_dir, f"{cache_key}.tmp.{extension}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        try:
            if not encode(source_path, tmp_path):
                raise RuntimeError("not encoded")
            os.replace(tmp_path, target_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            return source_path

    return target_path if os.path.exists(target_path) else source_path


def _encode_mp3(source_path: str, target_path: str, *, bitrate: str) -> bool:
    if not shutil.which("ffmpeg"):
        return _encode_mp3_with_soundfile(source_path, target_path, bitrate=bitrate)
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        source_path,
        "-vn",
        "-map_metadata",
        "-1",
        "-c:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        target_path,
    ]
    subprocess.run(command, check=True, timeout=300)
    return True


# Sample rates MPEG layer III allows.
_MP3_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)
# Longer files are served as they are rather than read whole into memory.
_SOUNDFILE_MAX_SECONDS = 900.0


def _bitrate_kbps(bitrate: str) -> float:
    try:
        return float(str(bitrate).strip().lower().rstrip("k"))
    except ValueError:
        return 128.0


def _encode_mp3_with_soundfile(source_path: str, target_path: str, *, bitrate: str) -> bool:
    """MP3 without ffmpeg (hosts like oncvm have none): libsndfile 1.1+ encodes
    MPEG layer III. Audio above 48 kHz is resampled to 48 kHz first. At constant
    bitrate libsndfile's compression level runs from about 320 kb/s (0.0) down
    by about 320 kb/s per unit, so the level follows the requested bitrate."""
    import numpy as np
    import soundfile as sf
    from fractions import Fraction
    from scipy import signal

    if "MP3" not in sf.available_formats():
        return False
    info = sf.info(source_path)
    if info.frames / max(info.samplerate, 1) > _SOUNDFILE_MAX_SECONDS:
        return False
    audio, rate = sf.read(source_path, dtype="float32", always_2d=True)
    if rate not in _MP3_RATES:
        target_rate = 48000 if rate > 48000 else max((r for r in _MP3_RATES if r <= rate), default=8000)
        ratio = Fraction(target_rate, rate).limit_denominator(1000)
        audio = signal.resample_poly(audio, ratio.numerator, ratio.denominator, axis=0).astype("float32")
        rate = target_rate
    np.clip(audio, -1.0, 1.0, out=audio)
    level = min(1.0, max(0.0, (320.0 - _bitrate_kbps(bitrate)) / 320.0))
    sf.write(target_path, audio, rate, format="MP3", subtype="MPEG_LAYER_III",
             compression_level=level, bitrate_mode="CONSTANT")
    return True


def _resampling_filter(rate: int, sample_rate: int):
    """Low-pass FIR filter at `rate` (the source rate times the upsampling factor)
    for resampling to `sample_rate`: flat (within 0.0001 dB) up to 7/8 of the new
    Nyquist frequency and at least 100 dB down from the new Nyquist frequency on,
    so nothing above it folds back into what is kept."""
    from scipy import signal

    nyquist = sample_rate / 2.0
    width = nyquist / 8.0
    numtaps, beta = signal.kaiserord(100.0, width / (rate / 2.0))
    numtaps |= 1  # odd, so the filter is centred on a sample: no time shift
    return signal.firwin(numtaps, nyquist - width / 2.0, window=("kaiser", beta), fs=rate)


def _encode_resampled_flac(source_path: str, target_path: str, *, sample_rate: int) -> bool:
    """A lossless copy at a lower sample rate: the audio low-passed and resampled to
    `sample_rate`, as 24-bit FLAC. Files already at or below that rate are served
    as they are."""
    import numpy as np
    import soundfile as sf
    from fractions import Fraction
    from scipy import signal

    info = sf.info(source_path)
    if info.samplerate <= sample_rate or info.frames / info.samplerate > _SOUNDFILE_MAX_SECONDS:
        return False
    audio, rate = sf.read(source_path, dtype="float32", always_2d=True)
    ratio = Fraction(sample_rate, rate)
    taps = _resampling_filter(rate * ratio.numerator, sample_rate)
    audio = signal.resample_poly(audio, ratio.numerator, ratio.denominator, axis=0, window=taps)
    np.clip(audio, -1.0, 1.0 - 2.0 ** -23, out=audio)
    sf.write(target_path, audio, sample_rate, format="FLAC", subtype="PCM_24")
    return True


def _get_lock(cache_key: str) -> threading.Lock:
    with _LOCK_REGISTRY_GUARD:
        lock = _LOCK_REGISTRY.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _LOCK_REGISTRY[cache_key] = lock
        return lock
