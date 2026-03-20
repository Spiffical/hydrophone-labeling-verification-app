"""Helpers for alternate audio playback transports."""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional, Tuple


DEFAULT_AUDIO_TRANSPORT = "direct"
DEFAULT_AUDIO_MP3_BITRATE = "128k"
DEFAULT_AUDIO_CACHE_DIR = "/tmp/hydrophone_audio_transport"

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
    if candidate in {"direct", "mp3_cached"}:
        return candidate
    return DEFAULT_AUDIO_TRANSPORT


def build_audio_transport_query(
    *,
    transport: Optional[str],
    mp3_bitrate: Optional[str] = None,
) -> str:
    normalized_transport = normalize_audio_transport(transport)
    if normalized_transport == DEFAULT_AUDIO_TRANSPORT:
        return ""

    query_parts = [f"transport={normalized_transport}"]
    bitrate = str(mp3_bitrate or DEFAULT_AUDIO_MP3_BITRATE).strip()
    if normalized_transport == "mp3_cached" and bitrate:
        query_parts.append(f"mp3_bitrate={bitrate}")

    return "?" + "&".join(query_parts)


def resolve_audio_delivery_path(
    audio_path: Optional[str],
    *,
    transport: Optional[str],
    mp3_bitrate: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> Optional[str]:
    if not audio_path or not os.path.exists(audio_path):
        return None

    normalized_transport = normalize_audio_transport(transport)
    if normalized_transport == "mp3_cached":
        return _ensure_cached_mp3(
            audio_path,
            bitrate=mp3_bitrate or DEFAULT_AUDIO_MP3_BITRATE,
            cache_dir=cache_dir or DEFAULT_AUDIO_CACHE_DIR,
        )
    return os.path.abspath(audio_path)


def prewarm_audio_delivery_path(
    audio_path: Optional[str],
    *,
    transport: Optional[str],
    mp3_bitrate: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> bool:
    """Warm the playback transport for a single item without blocking the caller."""
    if not audio_path:
        return False

    normalized_transport = normalize_audio_transport(transport)
    if normalized_transport != "mp3_cached":
        return False

    target_info = _build_cached_mp3_target(
        audio_path,
        bitrate=mp3_bitrate or DEFAULT_AUDIO_MP3_BITRATE,
        cache_dir=cache_dir or DEFAULT_AUDIO_CACHE_DIR,
    )
    if not target_info:
        return False

    source_path, target_path, cache_key, bitrate, resolved_cache_dir = target_info
    if _is_ready_cached_mp3(target_path):
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
            _ensure_cached_mp3,
            source_path,
            bitrate=bitrate,
            cache_dir=resolved_cache_dir,
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
            cache_dir=cache_dir,
        ):
            scheduled += 1
    return scheduled


def _build_cached_mp3_target(
    audio_path: str,
    *,
    bitrate: str,
    cache_dir: str,
) -> Optional[Tuple[str, str, str, str, str]]:
    source_path = os.path.abspath(audio_path)
    if not os.path.exists(source_path):
        return None

    stat = os.stat(source_path)
    resolved_bitrate = str(bitrate or DEFAULT_AUDIO_MP3_BITRATE).strip()
    resolved_cache_dir = os.path.abspath(cache_dir)
    cache_key = hashlib.sha256(
        f"{source_path}|{stat.st_mtime_ns}|{stat.st_size}|{resolved_bitrate}".encode("utf-8")
    ).hexdigest()
    target_path = os.path.join(resolved_cache_dir, f"{cache_key}.mp3")
    return source_path, target_path, cache_key, resolved_bitrate, resolved_cache_dir


def _is_ready_cached_mp3(target_path: str) -> bool:
    try:
        return os.path.exists(target_path) and os.path.getsize(target_path) > 0
    except OSError:
        return False


def _ensure_cached_mp3(audio_path: str, *, bitrate: str, cache_dir: str) -> Optional[str]:
    target_info = _build_cached_mp3_target(audio_path, bitrate=bitrate, cache_dir=cache_dir)
    if not target_info:
        return None

    source_path, target_path, cache_key, resolved_bitrate, target_dir = target_info
    if _is_ready_cached_mp3(target_path):
        return target_path

    os.makedirs(target_dir, exist_ok=True)
    lock = _get_lock(cache_key)
    with lock:
        if _is_ready_cached_mp3(target_path):
            return target_path

        tmp_path = os.path.join(target_dir, f"{cache_key}.tmp.mp3")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

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
            resolved_bitrate,
            tmp_path,
        ]

        try:
            subprocess.run(command, check=True, timeout=300)
            os.replace(tmp_path, target_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            return source_path

    return target_path if os.path.exists(target_path) else source_path


def _get_lock(cache_key: str) -> threading.Lock:
    with _LOCK_REGISTRY_GUARD:
        lock = _LOCK_REGISTRY.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _LOCK_REGISTRY[cache_key] = lock
        return lock
