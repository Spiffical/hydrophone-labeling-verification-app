"""Helpers for compact audio URL tokens."""

import base64
import json
import os
from typing import Dict, Optional


def _pad_token(token: str) -> str:
    remainder = len(token) % 4
    if remainder:
        token += "=" * (4 - remainder)
    return token


def encode_audio_request(audio_path: Optional[str]) -> Optional[str]:
    if not audio_path:
        return None
    payload = {"audio_path": os.path.abspath(audio_path)}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_audio_request(token: Optional[str]) -> Optional[Dict[str, str]]:
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(_pad_token(str(token)))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    audio_path = payload.get("audio_path")
    if not isinstance(audio_path, str) or not audio_path:
        return None
    return {"audio_path": os.path.abspath(audio_path)}
