"""Helpers for alternate audio playback transports."""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from typing import Optional


DEFAULT_AUDIO_TRANSPORT = "direct"
DEFAULT_AUDIO_MP3_BITRATE = "128k"
DEFAULT_AUDIO_CACHE_DIR = "/tmp/hydrophone_audio_transport"

_LOCK_REGISTRY: dict[str, threading.Lock] = {}
_LOCK_REGISTRY_GUARD = threading.Lock()


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


def _ensure_cached_mp3(audio_path: str, *, bitrate: str, cache_dir: str) -> Optional[str]:
    source_path = os.path.abspath(audio_path)
    if not os.path.exists(source_path):
        return None

    stat = os.stat(source_path)
    cache_key = hashlib.sha256(
        f"{source_path}|{stat.st_mtime_ns}|{stat.st_size}|{bitrate}".encode("utf-8")
    ).hexdigest()
    target_dir = os.path.abspath(cache_dir)
    target_path = os.path.join(target_dir, f"{cache_key}.mp3")
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        return target_path

    os.makedirs(target_dir, exist_ok=True)
    lock = _get_lock(cache_key)
    with lock:
        if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
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
            str(bitrate),
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
