"""Tab-specific state snapshot and data-root resolution helpers."""


def tab_data_snapshot(data):
    if not isinstance(data, dict):
        return {"loaded": False}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return {
        "loaded": True,
        "source_data_dir": data.get("source_data_dir"),
        "summary_data_root": summary.get("data_root"),
        "summary_active_date": summary.get("active_date"),
        "summary_active_hydrophone": summary.get("active_hydrophone"),
        "summary_predictions_file": summary.get("predictions_file"),
        "summary_labels_file": summary.get("labels_file"),
        "items_count": len(items),
    }


def config_default_data_dir(cfg, mode=None):
    if not isinstance(cfg, dict):
        return None
    data_cfg = cfg.get("data") if isinstance(cfg.get("data"), dict) else {}
    label_cfg = cfg.get("label") if isinstance(cfg.get("label"), dict) else {}
    verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
    if data_cfg.get("data_dir"):
        return data_cfg["data_dir"]

    active_mode = mode or cfg.get("mode") or data_cfg.get("mode")
    if active_mode == "label":
        return data_cfg.get("spectrogram_folder") or label_cfg.get("folder")
    if active_mode in {"verify", "explore"}:
        return verify_cfg.get("dashboard_root")
    return verify_cfg.get("dashboard_root") or data_cfg.get("spectrogram_folder") or label_cfg.get("folder")


def resolve_tab_data_dir(cfg, current_tab_data=None, trigger_cfg=None, trigger_source=None, mode=None):
    current_source = None
    if isinstance(current_tab_data, dict):
        current_source = current_tab_data.get("source_data_dir")

    trigger_data_dir = config_default_data_dir(trigger_cfg, mode)
    configured_data_dir = config_default_data_dir(cfg, mode)

    if trigger_source == "data-config-load":
        return trigger_data_dir or current_source or configured_data_dir

    return current_source or trigger_data_dir or configured_data_dir
