"""Shared debug logging helpers for callbacks."""

import json
import logging
import os

logger = logging.getLogger(__name__)

_BBOX_DEBUG_ENABLED = os.getenv("O3_BBOX_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
_VERIFY_BADGE_DEBUG_ENABLED = os.getenv("O3_VERIFY_BADGE_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}
_TAB_ISO_DEBUG_ENABLED = os.getenv("O3_TAB_ISO_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}


def bbox_debug(event, **payload):
    if not _BBOX_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[BBOX_DEBUG] %s | %s", event, serialized)


def verify_badge_debug(event, **payload):
    if not _VERIFY_BADGE_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[VERIFY_BADGE_DEBUG] %s | %s", event, serialized)


def tab_iso_debug(event, **payload):
    if not _TAB_ISO_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[TAB_ISO_DEBUG] %s | %s", event, serialized)
