"""Shared helpers for data configuration callbacks."""

import json
import logging
import os
import re

import dash_bootstrap_components as dbc
from dash import html

logger = logging.getLogger(__name__)
_TAB_ISO_DEBUG_ENABLED = os.getenv("O3_TAB_ISO_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}


def tab_iso_debug(event, **payload):
    if not _TAB_ISO_DEBUG_ENABLED:
        return
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        serialized = str(payload)
    logger.warning("[TAB_ISO_DEBUG] %s | %s", event, serialized)


def build_predictions_entries(predictions_locations: list, base_path: str) -> list:
    """Build editable entries for predictions files in subfolders."""
    entries = []
    if not predictions_locations:
        return entries

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for idx, file_path in enumerate(predictions_locations):
        rel_path = file_path
        if base_path:
            try:
                rel_path = os.path.relpath(file_path, base_path)
            except ValueError:
                rel_path = file_path

        scope = {"date": None, "device": None}
        label = rel_path

        if not os.path.isabs(rel_path) and not rel_path.startswith(".."):
            parts = rel_path.split(os.sep)
            if parts and date_pattern.match(parts[0]):
                scope["date"] = parts[0]
                if len(parts) > 2:
                    scope["device"] = parts[1]
            elif parts:
                scope["device"] = parts[0]

            if scope["date"] and scope["device"]:
                label = f"{scope['date']} / {scope['device']}"
            elif scope["date"]:
                label = scope["date"]
            elif scope["device"]:
                label = scope["device"]

        entries.append(
            {
                "index": idx,
                "path": file_path,
                "relative_path": rel_path,
                "scope": scope,
                "label": label,
            }
        )

    return entries


def create_info_badge(found: bool, count: int = 0, ext_info: str = "") -> html.Div:
    """Create an info badge showing what was found."""
    if found and count > 0:
        file_word = "file" if count == 1 else "files"
        return html.Div(
            [
                dbc.Badge("✓ Found", color="success", className="me-2"),
                html.Small(
                    f"{count} {file_word}" + (f" ({ext_info})" if ext_info else ""),
                    className="text-muted",
                ),
            ]
        )
    if found:
        return html.Div([dbc.Badge("✓ Found", color="success")])

    return html.Div(
        [
            dbc.Badge("Not found", color="warning", className="me-2"),
            html.Small("Optional - enter path or click Browse", className="text-muted"),
        ]
    )


def create_predictions_info(found: bool, is_label_mode: bool = False) -> html.Div:
    """Create info badge for predictions/labels file."""
    if found:
        return html.Div([dbc.Badge("✓ Found", color="success")])

    if is_label_mode:
        # In Label mode, the labels file is optional (will be created on save)
        return html.Div(
            [
                dbc.Badge("Not found", color="info", className="me-2"),
                html.Small("Optional - will be created on save", className="text-muted"),
            ]
        )

    # In Verify mode, predictions file is required
    return html.Div(
        [
            dbc.Badge("Not found", color="warning", className="me-2"),
            html.Small("Required for Verify mode", className="text-muted text-warning"),
        ]
    )

