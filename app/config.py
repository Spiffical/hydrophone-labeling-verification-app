import argparse
import os
from typing import Any, Dict

import yaml


def get_repo_root() -> str:
    """Find repository root by walking up until README.md or .git is found."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while current_dir != os.path.dirname(current_dir):
        if any(os.path.exists(os.path.join(current_dir, marker)) for marker in [".git", "README.md"]):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return os.getcwd()


def resolve_path(path: str, repo_root: str) -> str:
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(repo_root, path)


def load_config_file(config_path: str) -> Dict[str, Any]:
    if not config_path:
        return {}

    # If config_path is relative, check repo_root/config
    if not os.path.isabs(config_path):
        repo_root = get_repo_root()
        candidate = os.path.join(repo_root, config_path)
        if os.path.exists(candidate):
            config_path = candidate

    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r") as file:
        return yaml.safe_load(file) or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified Spectrogram Labeling & Verification App")
    parser.add_argument("--config", type=str, default="config/default.yaml", help="Path to config YAML")
    parser.add_argument("--mode", type=str, choices=["label", "verify", "explore"], help="Initial mode")

    # Label mode
    parser.add_argument("--label-folder", type=str, help="Folder with MAT spectrograms")
    parser.add_argument("--audio-folder", type=str, help="Folder with audio files")
    parser.add_argument("--output-file", type=str, help="Output labels.json path")

    # Verify mode
    parser.add_argument("--dashboard-root", type=str, help="Hydrophone dashboard root")
    parser.add_argument("--date", type=str, help="Date folder (YYYY-MM-DD)")
    parser.add_argument("--hydrophone", type=str, help="Hydrophone folder")

    # Whale-call predictions
    parser.add_argument("--predictions-json", type=str, help="Predictions JSON path")

    # Display
    parser.add_argument("--items-per-page", type=int, help="Items per page")
    parser.add_argument("--colormap", type=str, choices=["default", "hydrophone"], help="Default colormap")
    parser.add_argument("--y-axis-scale", type=str, choices=["linear", "log"], help="Y axis scale")
    parser.add_argument("--reset-mock", action="store_true", help="Regenerate mock data before launch")

    return parser.parse_args()


def get_config() -> Dict[str, Any]:
    args = parse_args()
    config = load_config_file(args.config)
    repo_root = get_repo_root()

    mode = args.mode or config.get("data", {}).get("mode", "label")

    label_cfg = config.get("data", {}).get("label", {})
    verify_cfg = config.get("data", {}).get("verify", {})
    whale_cfg = config.get("data", {}).get("whale", {})

    label_folder = args.label_folder or label_cfg.get("folder")
    audio_folder = args.audio_folder or label_cfg.get("audio_folder")
    output_file = args.output_file or label_cfg.get("output_file")

    dashboard_root = args.dashboard_root or verify_cfg.get("dashboard_root")
    date_str = args.date or verify_cfg.get("date")
    hydrophone = args.hydrophone or verify_cfg.get("hydrophone")

    predictions_json = args.predictions_json or whale_cfg.get("predictions_json")

    display_cfg = config.get("display", {})
    items_per_page = args.items_per_page or display_cfg.get("items_per_page", 25)
    colormap = args.colormap or display_cfg.get("colormap", "default")
    y_axis_scale = args.y_axis_scale or display_cfg.get("y_axis_scale", "linear")

    cache_cfg = config.get("cache", {})
    cache_max_size = cache_cfg.get("max_size", 400)

    return {
        "mode": mode,
        "reset_mock": args.reset_mock,
        "paths": {
            "repo_root": repo_root,
            "config_path": resolve_path(args.config, repo_root),
        },
        "label": {
            "folder": resolve_path(label_folder, repo_root) if label_folder else None,
            "audio_folder": resolve_path(audio_folder, repo_root) if audio_folder else None,
            "output_file": resolve_path(output_file, repo_root) if output_file else None,
        },
        "verify": {
            "dashboard_root": resolve_path(dashboard_root, repo_root) if dashboard_root else None,
            "date": date_str,
            "hydrophone": hydrophone,
        },
        "whale": {
            "predictions_json": resolve_path(predictions_json, repo_root) if predictions_json else None,
        },
        "display": {
            "items_per_page": items_per_page,
            "colormap": colormap,
            "y_axis_scale": y_axis_scale,
        },
        "cache": {
            "max_size": cache_max_size,
        },
    }
