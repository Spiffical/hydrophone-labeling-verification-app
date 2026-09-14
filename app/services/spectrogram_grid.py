"""Normalize the user-selectable spectrogram card grid."""

import math

from app.defaults import DEFAULT_ITEMS_PER_PAGE


MIN_GRID_ROWS = 1
MAX_GRID_ROWS = 8
MIN_GRID_COLUMNS = 1
MAX_GRID_COLUMNS = 6


def _bounded_int(value, fallback, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(fallback)
    return max(minimum, min(maximum, parsed))


def infer_spectrogram_grid(items_per_page):
    """Infer a compact rows/columns pair from a legacy page-size value."""
    try:
        item_count = max(1, int(items_per_page))
    except (TypeError, ValueError):
        item_count = DEFAULT_ITEMS_PER_PAGE

    candidates = []
    for columns in range(MIN_GRID_COLUMNS, MAX_GRID_COLUMNS + 1):
        rows = int(math.ceil(item_count / columns))
        if rows > MAX_GRID_ROWS:
            continue
        capacity = rows * columns
        candidates.append(
            (
                capacity - item_count,
                abs(columns - rows),
                0 if columns >= rows else 1,
                -columns,
                rows,
                columns,
            )
        )

    if not candidates:
        return {"rows": MAX_GRID_ROWS, "columns": MAX_GRID_COLUMNS}

    *_, rows, columns = min(candidates)
    return {"rows": rows, "columns": columns}


def normalize_spectrogram_grid(config=None, *, rows=None, columns=None):
    """Return bounded layout values and their exact page capacity."""
    cfg = config or {}
    display_cfg = cfg.get("display", {}) if isinstance(cfg.get("display"), dict) else {}
    inferred = infer_spectrogram_grid(
        display_cfg.get("items_per_page", DEFAULT_ITEMS_PER_PAGE)
    )
    normalized_rows = _bounded_int(
        display_cfg.get("grid_rows") if rows is None else rows,
        inferred["rows"],
        MIN_GRID_ROWS,
        MAX_GRID_ROWS,
    )
    normalized_columns = _bounded_int(
        display_cfg.get("grid_columns") if columns is None else columns,
        inferred["columns"],
        MIN_GRID_COLUMNS,
        MAX_GRID_COLUMNS,
    )
    return {
        "rows": normalized_rows,
        "columns": normalized_columns,
        "items_per_page": normalized_rows * normalized_columns,
    }


def config_with_spectrogram_grid(config, *, rows, columns):
    """Copy a config and apply one normalized grid layout."""
    cfg = dict(config or {})
    display_cfg = dict(cfg.get("display", {}) or {})
    normalized = normalize_spectrogram_grid(
        {"display": display_cfg},
        rows=rows,
        columns=columns,
    )
    display_cfg.update(
        {
            "grid_rows": normalized["rows"],
            "grid_columns": normalized["columns"],
            "items_per_page": normalized["items_per_page"],
        }
    )
    cfg["display"] = display_cfg
    return cfg


def spectrogram_grid_class(columns):
    normalized_columns = _bounded_int(
        columns,
        MIN_GRID_COLUMNS,
        MIN_GRID_COLUMNS,
        MAX_GRID_COLUMNS,
    )
    return (
        "spectrogram-card-grid "
        f"spectrogram-card-grid--columns-{normalized_columns}"
    )
