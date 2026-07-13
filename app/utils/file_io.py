import json
import os
import tempfile
from typing import Any, Dict, Optional

from filelock import FileLock

_lock_file = os.path.join(tempfile.gettempdir(), "unified_labels_lock.lock")
_file_lock = FileLock(_lock_file)


def read_json(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def write_json(
    path: str,
    data: Dict[str, Any],
    *,
    indent: Optional[int] = 2,
    sort_keys: bool = True,
) -> None:
    if not path:
        raise ValueError("path is required")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dump_kwargs = {"sort_keys": sort_keys}
    if indent is None:
        dump_kwargs["separators"] = (",", ":")
    else:
        dump_kwargs["indent"] = indent
    with _file_lock:
        with open(path, "w") as f:
            json.dump(data, f, **dump_kwargs)
