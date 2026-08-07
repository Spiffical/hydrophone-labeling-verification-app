"""Verify-mode data loading callback registration."""

from copy import deepcopy
import os
import time

from dash import Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.services.verify_all_dates_loader import (
    build_all_dates_cache_key,
    cache_all_dates_preview,
    get_all_dates_preview,
    get_all_dates_load,
    load_persisted_all_dates,
    queue_all_dates_load,
    start_queued_all_dates_load,
)
from app.services.verify_modal_cache import (
    ensure_verify_modal_items,
    register_verify_modal_items,
)


_ALL_DATES_PREVIEW_MAX_DATES = 8
_ALL_DATES_PREVIEW_MAX_ITEMS = 50
_ALL_DATES_BACKGROUND_START_DELAY_SECONDS = 3.0
_ALL_DATES_FILTER_TRIGGER_IDS = {
    "global-date-selector",
    "global-device-selector",
}


def _is_all_dates_ready_signal(triggered_props, payload):
    return bool(
        "verify-all-dates-ready-store" in triggered_props
        and isinstance(payload, dict)
        and payload.get("cache_key")
        and payload.get("request_id")
        and payload.get("status") in {"ready", "failed"}
    )


def _is_all_dates_filter_change(triggered_props):
    return bool(set(triggered_props or []) & _ALL_DATES_FILTER_TRIGGER_IDS)


def _is_all_dates_ui_ready(summary, ui_ready):
    request_id = summary.get("all_dates_request_id") if isinstance(summary, dict) else None
    return bool(
        request_id
        and isinstance(ui_ready, dict)
        and ui_ready.get("all_dates_request_id") == request_id
        and ui_ready.get("active_date") == "All"
    )


def _all_dates_preview(
    current_verify_data,
    *,
    active_data_dir,
    effective_cfg,
    requested_device,
    load_dataset,
):
    """Return an immediately renderable subset while the full dataset loads."""
    current_summary = (
        current_verify_data.get("summary", {})
        if isinstance(current_verify_data, dict)
        else {}
    )
    current_device = current_summary.get("active_hydrophone")
    can_reuse_current = bool(
        isinstance(current_verify_data, dict)
        and current_verify_data.get("items")
        and current_summary.get("active_date") not in {None, "All"}
        and (
            requested_device in {None, "__all__"}
            or current_device in {requested_device, "All"}
        )
    )

    if can_reuse_current:
        preview = deepcopy(current_verify_data)
        preview_date = current_summary.get("active_date")
    else:
        configured_date = (effective_cfg.get("verify") or {}).get("date")
        available_dates = []
        if active_data_dir and os.path.isdir(active_data_dir):
            available_dates = sorted(
                (
                    name
                    for name in os.listdir(active_data_dir)
                    if len(name) == 10
                    and name[4] == "-"
                    and os.path.isdir(os.path.join(active_data_dir, name))
                ),
                reverse=True,
            )

        preview_dates = []
        for candidate in [configured_date, *available_dates]:
            if (
                candidate in {None, "", "__all__", "__flat__"}
                or candidate in preview_dates
                or not os.path.isdir(os.path.join(active_data_dir or "", str(candidate)))
            ):
                continue
            preview_dates.append(candidate)

        known_empty_date = (
            current_summary.get("active_date")
            if isinstance(current_verify_data, dict) and not current_verify_data.get("items")
            else None
        )
        if known_empty_date in preview_dates:
            preview_dates.remove(known_empty_date)

        preview = {"items": [], "summary": {"total_items": 0}}
        preview_date = None
        for candidate in preview_dates[:_ALL_DATES_PREVIEW_MAX_DATES]:
            preview_date = candidate
            preview = load_dataset(
                effective_cfg,
                "verify",
                date_str=candidate,
                hydrophone=requested_device,
            )
            if preview.get("items"):
                break

    preview_items = list(preview.get("items") or [])
    preview_source_items = len(preview_items)
    if preview_source_items > _ALL_DATES_PREVIEW_MAX_ITEMS:
        preview_items = preview_items[:_ALL_DATES_PREVIEW_MAX_ITEMS]
        preview["items"] = preview_items

    summary = dict(preview.get("summary") or {})
    summary.update(
        active_date="All",
        active_hydrophone="All" if requested_device == "__all__" else requested_device,
        all_dates_loading=True,
        all_dates_preview=True,
        all_dates_preview_date=preview_date,
        all_dates_preview_items=len(preview_items),
        all_dates_preview_source_items=preview_source_items,
        total_items=len(preview_items),
    )
    preview["summary"] = summary
    preview["source_data_dir"] = active_data_dir
    preview["load_timestamp"] = time.time()
    return preview


def _finish_all_dates_data(data, *, cache_key, active_data_dir, request_id=None):
    completed = data
    summary = dict(completed.get("summary") or {})
    summary.update(
        all_dates_loading=False,
        all_dates_preview=False,
        all_dates_cache_key=cache_key,
        all_dates_request_id=request_id,
    )
    completed["summary"] = summary
    completed["source_data_dir"] = active_data_dir
    completed["load_timestamp"] = time.time()
    return completed


def _indexed_all_dates_view(
    indexed_data,
    *,
    cache_key,
    active_data_dir,
    request_id,
    updating,
    replace_modal_cache=False,
):
    """Expose full-index counts and filtering while keeping the browser payload small."""
    indexed = deepcopy(indexed_data)
    indexed_items = list(indexed.get("items") or [])
    indexed_summary = dict(indexed.get("summary") or {})
    indexed_summary.update(
        active_date="All",
        all_dates_loading=bool(updating),
        all_dates_preview=False,
        all_dates_index_available=True,
        all_dates_cache_key=cache_key,
        all_dates_request_id=request_id,
        total_items=len(indexed_items),
    )
    indexed["summary"] = indexed_summary
    indexed["source_data_dir"] = active_data_dir
    indexed["load_timestamp"] = f"all-dates-index:{cache_key}"

    if replace_modal_cache:
        modal_cache_key = register_verify_modal_items(indexed)
    else:
        modal_cache_key = ensure_verify_modal_items(indexed)

    compact = dict(indexed)
    compact["items"] = deepcopy(indexed_items[:_ALL_DATES_PREVIEW_MAX_ITEMS])
    compact["summary"] = dict(indexed_summary)
    compact["summary"]["verify_modal_cache_key"] = modal_cache_key
    compact["load_timestamp"] = time.time()
    return compact


def register_verify_data_loading_callback(
    app,
    *,
    load_dataset,
    resolve_tab_data_dir,
    config_default_data_dir,
    tab_iso_debug,
    tab_data_snapshot,
):
    app.clientside_callback(
        """
        function(data) {
            if (!data || typeof data !== "object") return null;
            var summary = data.summary || {};
            if (summary.active_date !== "All" || !summary.all_dates_cache_key) return null;
            return {
                active_date: summary.active_date,
                active_hydrophone: summary.active_hydrophone || null,
                all_dates_cache_key: summary.all_dates_cache_key,
                all_dates_request_id: summary.all_dates_request_id || null,
                all_dates_loading: !!summary.all_dates_loading,
                all_dates_preview: !!summary.all_dates_preview
            };
        }
        """,
        Output("verify-all-dates-request-store", "data"),
        Input("verify-data-store", "data"),
    )

    @app.callback(
        Output("verify-all-dates-poll", "disabled"),
        Output("verify-all-dates-ready-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        Input("verify-all-dates-poll", "n_intervals"),
        State("verify-all-dates-request-store", "data"),
        State("verify-all-dates-ready-store", "data"),
        State("verify-ui-ready-store", "data"),
    )
    def control_all_dates_poll(
        date_val,
        device_val,
        all_dates_poll,
        all_dates_request,
        last_ready,
        verify_ui_ready,
    ):
        _ = device_val
        _ = all_dates_poll
        if date_val != "__all__":
            return True, no_update
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}
        if _is_all_dates_filter_change(triggered_props):
            return False, no_update

        summary = all_dates_request if isinstance(all_dates_request, dict) else {}
        cache_key = summary.get("all_dates_cache_key")
        request_id = summary.get("all_dates_request_id")
        if not summary.get("all_dates_loading") or not cache_key:
            is_completed = bool(
                summary.get("active_date") == "All"
                and cache_key
                and not summary.get("all_dates_preview")
            )
            return is_completed, no_update

        if (
            isinstance(last_ready, dict)
            and last_ready.get("cache_key") == cache_key
            and last_ready.get("request_id") == request_id
        ):
            return True, no_update

        cached = get_all_dates_load(cache_key, include_data=False)
        if cached["status"] == "pending":
            if not _is_all_dates_ui_ready(summary, verify_ui_ready):
                return False, no_update
            start_queued_all_dates_load(
                cache_key,
                startup_delay_seconds=_ALL_DATES_BACKGROUND_START_DELAY_SECONDS,
            )
            return False, no_update
        if cached["status"] in {"missing", "loading"}:
            return False, no_update

        return True, {
            "cache_key": cache_key,
            "request_id": request_id,
            "status": cached["status"],
            "error": cached.get("error"),
            "timestamp": time.time(),
        }

    @app.callback(
        Output("verify-data-store", "data"),
        Input("verify-reload", "n_clicks"),
        Input("data-load-trigger-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        Input("verify-all-dates-ready-store", "data"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("verify-data-store", "data"),
    )
    def load_verify_data(
        reload_clicks,
        config_load_trigger,
        date_val,
        device_val,
        all_dates_ready,
        cfg,
        mode,
        current_verify_data,
    ):
        """Load data specifically for Verify mode."""
        _ = reload_clicks
        triggered_props = {t["prop_id"].split(".")[0] for t in ctx.triggered}

        trigger_mode = None
        trigger_source = None
        if isinstance(config_load_trigger, dict):
            trigger_mode = config_load_trigger.get("mode")
            trigger_source = config_load_trigger.get("source")

        trigger_cfg_snapshot = (
            config_load_trigger.get("config")
            if isinstance(config_load_trigger, dict) and isinstance(config_load_trigger.get("config"), dict)
            else None
        )
        tab_iso_debug(
            "load_verify_start",
            mode=mode,
            trigger_mode=trigger_mode,
            trigger_source=trigger_source,
            triggered_props=sorted(triggered_props),
            date_val=date_val,
            device_val=device_val,
            cfg_data_dir=config_default_data_dir(cfg or {}, mode),
            trigger_cfg_data_dir=config_default_data_dir(trigger_cfg_snapshot, mode),
            current_verify_snapshot=tab_data_snapshot(current_verify_data),
        )

        if mode != "verify":
            raise PreventUpdate

        all_dates_ready_triggered = _is_all_dates_ready_signal(triggered_props, all_dates_ready)
        current_summary = (
            current_verify_data.get("summary", {})
            if isinstance(current_verify_data, dict)
            else {}
        )
        if all_dates_ready_triggered:
            cache_key = current_summary.get("all_dates_cache_key")
            signaled_key = (
                all_dates_ready.get("cache_key")
                if isinstance(all_dates_ready, dict)
                else None
            )
            current_request_id = current_summary.get("all_dates_request_id")
            signaled_request_id = (
                all_dates_ready.get("request_id")
                if isinstance(all_dates_ready, dict)
                else None
            )
            if (
                date_val != "__all__"
                or not current_summary.get("all_dates_loading")
                or not cache_key
                or signaled_key != cache_key
                or signaled_request_id != current_request_id
            ):
                raise PreventUpdate

            cached = get_all_dates_load(cache_key)
            if cached["status"] == "ready" and cached["data"] is not None:
                completed = _indexed_all_dates_view(
                    cached["data"],
                    cache_key=cache_key,
                    active_data_dir=current_verify_data.get("source_data_dir"),
                    request_id=current_request_id,
                    updating=False,
                    replace_modal_cache=True,
                )
                from app.main import set_audio_roots

                set_audio_roots(completed.get("audio_roots", []))
                return completed
            if cached["status"] == "failed":
                failed = deepcopy(current_verify_data)
                failed_summary = dict(failed.get("summary") or {})
                failed_summary.update(
                    all_dates_loading=False,
                    all_dates_preview=True,
                    all_dates_error=cached.get("error") or "All Dates loading failed.",
                )
                failed["summary"] = failed_summary
                failed["load_timestamp"] = time.time()
                return failed
            raise PreventUpdate

        filter_triggered = triggered_props & {"global-date-selector", "global-device-selector"}
        has_source = bool(current_verify_data and current_verify_data.get("source_data_dir"))

        config_panel_trigger = "data-load-trigger-store" in triggered_props and trigger_source == "data-config-load"
        should_load = (
            "verify-reload" in triggered_props
            or trigger_mode == "verify"
            or config_panel_trigger
            or (filter_triggered and has_source)
        )
        tab_iso_debug(
            "load_verify_decision",
            filter_triggered=bool(filter_triggered),
            has_source=bool(has_source),
            config_panel_trigger=config_panel_trigger,
            should_load=should_load,
        )

        if should_load:
            try:
                trigger_cfg = None
                requested_date = date_val
                requested_device = device_val
                if isinstance(config_load_trigger, dict) and "data-load-trigger-store" in triggered_props:
                    trigger_cfg = config_load_trigger.get("config")
                    requested_date = config_load_trigger.get("date_value", requested_date)
                    requested_device = config_load_trigger.get("device_value", requested_device)

                effective_cfg = trigger_cfg.copy() if trigger_cfg else (cfg.copy() if cfg else {})
                data_cfg = dict(effective_cfg.get("data", {}))
                active_data_dir = resolve_tab_data_dir(
                    cfg,
                    current_tab_data=current_verify_data,
                    trigger_cfg=trigger_cfg,
                    trigger_source=trigger_source,
                    mode=mode,
                )
                tab_iso_debug(
                    "load_verify_resolved_root",
                    active_data_dir=active_data_dir,
                    cfg_data_dir=config_default_data_dir(cfg or {}, mode),
                    trigger_cfg_data_dir=config_default_data_dir(trigger_cfg or {}, mode),
                    current_source_data_dir=(current_verify_data or {}).get("source_data_dir")
                    if isinstance(current_verify_data, dict)
                    else None,
                )
                if active_data_dir:
                    data_cfg["data_dir"] = active_data_dir

                effective_cfg["data"] = data_cfg

                if requested_date == "__all__":
                    cache_key = build_all_dates_cache_key(effective_cfg, requested_device)
                    force_reload = "verify-reload" in triggered_props
                    request_id = str(time.time_ns())
                    cached = get_all_dates_load(cache_key)
                    indexed_data = (
                        cached.get("data")
                        if cached["status"] == "ready" and cached.get("data") is not None
                        else load_persisted_all_dates(cache_key)
                    )
                    should_refresh = bool(
                        force_reload
                        or cached["status"] in {"missing", "failed"}
                        or (
                            indexed_data is not None
                            and cached["status"] not in {"ready", "pending", "loading"}
                        )
                    )
                    is_updating = bool(
                        should_refresh or cached["status"] in {"pending", "loading"}
                    )

                    if indexed_data is not None:
                        data = _indexed_all_dates_view(
                            indexed_data,
                            cache_key=cache_key,
                            active_data_dir=active_data_dir,
                            request_id=request_id,
                            updating=is_updating,
                        )
                    else:
                        data = get_all_dates_preview(cache_key)
                        if data is None:
                            data = _all_dates_preview(
                                current_verify_data,
                                active_data_dir=active_data_dir,
                                effective_cfg=effective_cfg,
                                requested_device=requested_device,
                                load_dataset=load_dataset,
                            )
                            cache_all_dates_preview(cache_key, data)
                        data["summary"]["all_dates_index_available"] = False
                        data["summary"]["all_dates_cache_key"] = cache_key
                        data["summary"]["all_dates_request_id"] = request_id

                    if should_refresh:
                        loader_cfg = deepcopy(effective_cfg)
                        queue_all_dates_load(
                            cache_key,
                            lambda: load_dataset(
                                loader_cfg,
                                "verify",
                                date_str="__all__",
                                hydrophone=requested_device,
                            ),
                            force=force_reload,
                            persist=True,
                        )
                else:
                    data = load_dataset(
                        effective_cfg,
                        "verify",
                        date_str=requested_date,
                        hydrophone=requested_device,
                    )

                if "data-load-trigger-store" in triggered_props and isinstance(config_load_trigger, dict):
                    data["load_timestamp"] = config_load_trigger.get("timestamp")
                elif filter_triggered:
                    data["load_timestamp"] = time.time()
                else:
                    data["load_timestamp"] = time.time()

                data["source_data_dir"] = active_data_dir
                from app.main import set_audio_roots

                set_audio_roots(data.get("audio_roots", []))
                tab_iso_debug(
                    "load_verify_success",
                    requested_date=requested_date,
                    requested_device=requested_device,
                    effective_predictions_file=(effective_cfg.get("data") or {}).get("predictions_file"),
                    loaded_verify_snapshot=tab_data_snapshot(data),
                )
                return data
            except Exception as e:
                tab_iso_debug("load_verify_error", error=str(e))
                print(f"Error loading verify dataset: {e}")
                return {
                    "items": [],
                    "summary": {"total_items": 0, "error": str(e)},
                    "load_timestamp": (config_load_trigger or {}).get("timestamp") or time.time(),
                }

        raise PreventUpdate
