"""Background loading and in-process caching for Verify mode's All Dates view."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
import time
from typing import Any, Callable, Dict
from uuid import uuid4


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="verify-all-dates")
_LOCK = RLock()
_ENTRIES: Dict[str, Dict[str, Any]] = {}
_PREVIEWS: Dict[str, Dict[str, Any]] = {}
_MAX_ENTRIES = 4
_PERSISTED_CACHE_VERSION = 1
_PERSISTED_CACHE_DIR = Path(
    os.environ.get(
        "HYDROPHONE_ALL_DATES_CACHE_DIR",
        "~/.cache/hydrophone-labeling-verification/all-dates",
    )
).expanduser()
_DATASET_CONFIG_KEYS = (
    "data_dir",
    "structure_type",
    "predictions_file",
    "spectrogram_folder",
    "audio_folder",
    "predictions_overrides",
    "spectrogram_folder_names",
    "audio_folder_names",
)


def build_all_dates_cache_key(config: Dict[str, Any], hydrophone: str | None) -> str:
    """Return a stable key for the inputs that determine an All Dates dataset."""
    config = config if isinstance(config, dict) else {}
    data_config = config.get("data") if isinstance(config.get("data"), dict) else {}
    verify_config = config.get("verify") if isinstance(config.get("verify"), dict) else {}
    payload = {
        "data": {
            key: data_config.get(key)
            for key in _DATASET_CONFIG_KEYS
            if key in data_config
        },
        "dashboard_root": verify_config.get("dashboard_root"),
        "fallback_hydrophone": verify_config.get("hydrophone") if hydrophone is None else None,
        "hydrophone": hydrophone,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def load_persisted_all_dates(cache_key: str) -> Dict[str, Any] | None:
    """Load the last complete index for this dataset from local VM storage."""
    cache_path = _persisted_cache_path(cache_key)
    if not cache_path.is_file():
        return None
    try:
        with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError) as exc:
        print(
            f"[verify-all-dates] persisted cache read failed key={cache_key[:12]} error={exc}",
            flush=True,
        )
        return None

    if (
        not isinstance(payload, dict)
        or payload.get("version") != _PERSISTED_CACHE_VERSION
        or payload.get("cache_key") != cache_key
        or not isinstance(payload.get("data"), dict)
    ):
        return None
    return deepcopy(payload["data"])


def get_all_dates_preview(cache_key: str) -> Dict[str, Any] | None:
    """Return a copy of the shared first-page preview for this dataset."""
    with _LOCK:
        preview = _PREVIEWS.get(cache_key)
        return deepcopy(preview) if preview is not None else None


def cache_all_dates_preview(cache_key: str, preview: Dict[str, Any]) -> None:
    """Cache a first-page preview so concurrent sessions avoid another mount scan."""
    with _LOCK:
        _PREVIEWS[cache_key] = deepcopy(preview)
        while len(_PREVIEWS) > _MAX_ENTRIES:
            removable_key = next((key for key in _PREVIEWS if key != cache_key), None)
            if removable_key is None:
                break
            _PREVIEWS.pop(removable_key, None)


def get_all_dates_load(cache_key: str, *, include_data: bool = True) -> Dict[str, Any]:
    """Return a snapshot of a background load's state and completed data."""
    with _LOCK:
        entry = _ENTRIES.get(cache_key)
        if not entry:
            return {"status": "missing", "data": None, "error": None}
        return {
            "status": entry["status"],
            "data": (
                deepcopy(entry.get("data"))
                if include_data and entry.get("data") is not None
                else None
            ),
            "error": entry.get("error"),
        }


def queue_all_dates_load(
    cache_key: str,
    loader: Callable[[], Dict[str, Any]],
    *,
    force: bool = False,
    persist: bool = False,
) -> Dict[str, Any]:
    """Queue a full load without starting it, allowing the preview to render first."""
    with _LOCK:
        existing = _ENTRIES.get(cache_key)
        if existing and existing["status"] in {"pending", "loading"}:
            return {"status": existing["status"]}
        if existing and not force and existing["status"] == "ready":
            return {"status": "ready"}

        _ENTRIES[cache_key] = {
            "status": "pending",
            "data": None,
            "error": None,
            "loader": loader,
            "persist": bool(persist),
        }
        _trim_entries_locked(keep_key=cache_key)
    print(f"[verify-all-dates] queued key={cache_key[:12]}", flush=True)
    return {"status": "pending"}


def start_queued_all_dates_load(
    cache_key: str,
    *,
    startup_delay_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Start a previously queued full load once the preview response is delivered."""
    with _LOCK:
        entry = _ENTRIES.get(cache_key)
        if not entry:
            return {"status": "missing"}
        if entry["status"] != "pending":
            return {"status": entry["status"]}

        loader = entry.pop("loader")
        persist = bool(entry.get("persist"))
        run_token = uuid4().hex
        entry.update(status="loading", run_token=run_token)

    delay = max(0.0, float(startup_delay_seconds or 0.0))

    def run() -> None:
        if delay:
            time.sleep(delay)
        with _LOCK:
            current = _ENTRIES.get(cache_key)
            if not current or current.get("run_token") != run_token:
                return

        started_at = time.monotonic()
        print(
            f"[verify-all-dates] starting key={cache_key[:12]} delay={delay:.1f}s",
            flush=True,
        )
        try:
            data = loader()
        except Exception as exc:
            with _LOCK:
                current = _ENTRIES.get(cache_key)
                if current is not None and current.get("run_token") == run_token:
                    current.update(status="failed", data=None, error=str(exc))
            print(
                f"[verify-all-dates] failed key={cache_key[:12]} error={exc}",
                flush=True,
            )
            return

        if persist:
            _persist_all_dates(cache_key, data)

        elapsed = time.monotonic() - started_at
        with _LOCK:
            current = _ENTRIES.get(cache_key)
            if current is not None and current.get("run_token") == run_token:
                current.update(status="ready", data=data, error=None)
        print(
            f"[verify-all-dates] ready key={cache_key[:12]} "
            f"items={len(data.get('items') or [])} elapsed={elapsed:.1f}s",
            flush=True,
        )

    _EXECUTOR.submit(run)
    return {"status": "loading"}


def start_all_dates_load(
    cache_key: str,
    loader: Callable[[], Dict[str, Any]],
    *,
    force: bool = False,
    persist: bool = False,
    startup_delay_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Start one background load unless this key is already loading or ready."""
    queued = queue_all_dates_load(
        cache_key,
        loader,
        force=force,
        persist=persist,
    )
    if queued["status"] != "pending":
        return queued
    return start_queued_all_dates_load(
        cache_key,
        startup_delay_seconds=startup_delay_seconds,
    )


def clear_all_dates_loads() -> None:
    """Clear cached entries. Intended for tests and explicit service resets."""
    with _LOCK:
        _ENTRIES.clear()
        _PREVIEWS.clear()


def _trim_entries_locked(*, keep_key: str) -> None:
    while len(_ENTRIES) > _MAX_ENTRIES:
        removable_key = next(
            (
                key
                for key, entry in _ENTRIES.items()
                if key != keep_key and entry.get("status") != "loading"
            ),
            None,
        )
        if removable_key is None:
            break
        _ENTRIES.pop(removable_key, None)


def _persisted_cache_path(cache_key: str) -> Path:
    return _PERSISTED_CACHE_DIR / f"{cache_key}.json.gz"


def _persist_all_dates(cache_key: str, data: Dict[str, Any]) -> None:
    cache_path = _persisted_cache_path(cache_key)
    temp_path = cache_path.with_name(f".{cache_path.name}.{uuid4().hex}.tmp")
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _PERSISTED_CACHE_VERSION,
            "cache_key": cache_key,
            "saved_at": time.time(),
            "data": data,
        }
        with gzip.open(temp_path, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), default=str)
        os.replace(temp_path, cache_path)
        print(
            f"[verify-all-dates] persisted key={cache_key[:12]} path={cache_path}",
            flush=True,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(
            f"[verify-all-dates] persisted cache write failed "
            f"key={cache_key[:12]} error={exc}",
            flush=True,
        )
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
