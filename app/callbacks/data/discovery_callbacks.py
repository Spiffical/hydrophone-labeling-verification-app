"""Tab-specific date/device filter and active-selection callbacks."""

import os

from dash import Input, Output, State
from dash.exceptions import PreventUpdate
from app.utils.data_discovery import detect_data_structure


def register_tab_state_callbacks(
    app,
    *,
    tab_iso_debug,
    config_default_data_dir,
    tab_data_snapshot,
):
    """Register callbacks for tab-isolated filter persistence and discovery."""

    @app.callback(
        Output("global-date-selector", "options", allow_duplicate=True),
        Output("global-date-selector", "value", allow_duplicate=True),
        Input("mode-tabs", "data"),
        State("config-store", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("tab-filter-state-store", "data"),
        State("global-date-selector", "value"),
        prevent_initial_call="initial_duplicate",
    )
    def discover_dates(mode, cfg, label_data, verify_data, explore_data, tab_filter_state, global_date_value):
        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        configured_data_dir = config_default_data_dir(cfg or {})
        tab_data_dir = tab_data.get("source_data_dir") if tab_data else None
        data_dir = tab_data_dir or configured_data_dir
        tab_iso_debug(
            "discover_dates_start",
            mode=mode,
            tab_data_dir=tab_data_dir,
            configured_data_dir=configured_data_dir,
            resolved_data_dir=data_dir,
            global_date_value=global_date_value,
        )
        if not data_dir or not os.path.exists(data_dir):
            tab_iso_debug("discover_dates_no_dir", mode=mode, resolved_data_dir=data_dir)
            return [], None

        tab_state = (tab_filter_state or {}).get(mode, {}) if isinstance(tab_filter_state, dict) else {}
        saved_date = tab_state.get("date") if isinstance(tab_state, dict) else None
        current_date = global_date_value

        try:
            summary = tab_data.get("summary", {}) if isinstance(tab_data, dict) else {}
            available_dates = (
                tab_data.get("available_dates")
                if isinstance(tab_data, dict)
                else None
            ) or summary.get("available_dates")
            if available_dates:
                dates = sorted({d for d in available_dates if d}, reverse=True)
                options = [{"label": "All Dates", "value": "__all__"}] + [
                    {"label": d, "value": d} for d in dates
                ]
                option_values = {"__all__", *dates}
                default_val = "__all__"

                config_date = None
                if mode == "verify" and isinstance(cfg, dict):
                    verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
                    config_date = verify_cfg.get("date")
                if saved_date in option_values:
                    default_val = saved_date
                elif current_date in option_values:
                    default_val = current_date
                elif config_date in dates:
                    default_val = config_date

                tab_iso_debug(
                    "discover_dates_return_available",
                    mode=mode,
                    options_count=len(options),
                    default_val=default_val,
                    saved_date=saved_date,
                    current_date=current_date,
                    config_date=config_date,
                )
                return options, default_val

            base_name = os.path.basename(data_dir.rstrip(os.sep))
            if len(base_name) == 10 and base_name[4] == "-" and base_name[7] == "-":
                tab_iso_debug("discover_dates_return_base_date", mode=mode, base_name=base_name)
                return [{"label": base_name, "value": base_name}], base_name

            dates = [d for d in os.listdir(data_dir) if len(d) == 10 and os.path.isdir(os.path.join(data_dir, d))]
            dates.sort(reverse=True)

            options = [{"label": "All Dates", "value": "__all__"}] + [
                {"label": d, "value": d} for d in dates
            ]
            option_values = {"__all__", *dates}
            default_val = dates[0] if dates else None

            config_date = None
            if mode == "verify" and isinstance(cfg, dict):
                verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
                config_date = verify_cfg.get("date")
            if saved_date in option_values:
                default_val = saved_date
            elif current_date in option_values:
                default_val = current_date
            elif config_date in dates:
                default_val = config_date

            if dates:
                tab_iso_debug(
                    "discover_dates_return_dates",
                    mode=mode,
                    options_count=len(options),
                    default_val=default_val,
                    saved_date=saved_date,
                    current_date=current_date,
                    config_date=config_date,
                )
                return options, default_val

            discovery = detect_data_structure(data_dir)
            inferred_dates = discovery.get("dates") or []
            if inferred_dates:
                dates = sorted({d for d in inferred_dates if d}, reverse=True)
                options = [{"label": "All Dates", "value": "__all__"}] + [
                    {"label": d, "value": d} for d in dates
                ]
                option_values = {"__all__", *dates}
                default_val = "__all__"
                if saved_date in option_values:
                    default_val = saved_date
                elif current_date in option_values:
                    default_val = current_date
                elif config_date in dates:
                    default_val = config_date
                tab_iso_debug(
                    "discover_dates_return_inferred",
                    mode=mode,
                    options_count=len(options),
                    default_val=default_val,
                    structure_type=discovery.get("structure_type"),
                )
                return options, default_val

            devices = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
            if devices:
                device_only_val = "__device_only__"
                if saved_date == device_only_val:
                    tab_iso_debug("discover_dates_return_device_only_saved", mode=mode, default_val=saved_date)
                    return [{"label": "Device folders", "value": device_only_val}], saved_date
                if current_date == device_only_val:
                    tab_iso_debug("discover_dates_return_device_only_current", mode=mode, default_val=current_date)
                    return [{"label": "Device folders", "value": device_only_val}], current_date
                tab_iso_debug("discover_dates_return_device_only_default", mode=mode, default_val=device_only_val)
                return [{"label": "Device folders", "value": device_only_val}], device_only_val

            tab_iso_debug("discover_dates_return_empty", mode=mode)
            return [], None
        except Exception as e:
            tab_iso_debug("discover_dates_error", mode=mode, error=str(e))
            return [], None

    @app.callback(
        Output("global-device-selector", "options"),
        Output("global-device-selector", "value"),
        Input("global-date-selector", "value"),
        State("config-store", "data"),
        State("mode-tabs", "data"),
        State("label-data-store", "data"),
        State("verify-data-store", "data"),
        State("explore-data-store", "data"),
        State("tab-filter-state-store", "data"),
        State("global-device-selector", "value"),
    )
    def discover_devices(selected_date, cfg, mode, label_data, verify_data, explore_data, tab_filter_state, global_device_value):
        if not selected_date:
            tab_iso_debug("discover_devices_no_selected_date", mode=mode)
            return [], None

        if selected_date == "__flat__":
            tab_iso_debug("discover_devices_skip_flat", mode=mode)
            return [], None

        tab_data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode)
        configured_data_dir = config_default_data_dir(cfg or {})
        tab_data_dir = tab_data.get("source_data_dir") if tab_data else None
        data_dir = tab_data_dir or configured_data_dir
        tab_iso_debug(
            "discover_devices_start",
            mode=mode,
            selected_date=selected_date,
            tab_data_dir=tab_data_dir,
            configured_data_dir=configured_data_dir,
            resolved_data_dir=data_dir,
            global_device_value=global_device_value,
        )
        if not data_dir:
            tab_iso_debug("discover_devices_no_dir", mode=mode)
            return [], None

        tab_state = (tab_filter_state or {}).get(mode, {}) if isinstance(tab_filter_state, dict) else {}
        saved_device = tab_state.get("device") if isinstance(tab_state, dict) else None
        current_device = global_device_value

        try:
            summary = tab_data.get("summary", {}) if isinstance(tab_data, dict) else {}
            available_devices = (
                tab_data.get("available_devices")
                if isinstance(tab_data, dict)
                else None
            ) or summary.get("available_devices")
            if available_devices:
                devices = sorted({d for d in available_devices if d})
                options = [{"label": "All Devices", "value": "__all__"}] + [
                    {"label": d, "value": d} for d in devices
                ]
                option_values = {"__all__", *devices}
                default_val = "__all__"

                config_dev = None
                if mode == "verify" and isinstance(cfg, dict):
                    verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
                    config_dev = verify_cfg.get("hydrophone")
                if saved_device in option_values:
                    default_val = saved_device
                elif current_device in option_values:
                    default_val = current_device
                elif config_dev in devices:
                    default_val = config_dev

                tab_iso_debug(
                    "discover_devices_return_available",
                    mode=mode,
                    selected_date=selected_date,
                    devices_count=len(devices),
                    default_val=default_val,
                    saved_device=saved_device,
                    current_device=current_device,
                    config_dev=config_dev,
                )
                return options, default_val

            devices = set()
            base_name = os.path.basename(data_dir.rstrip(os.sep))
            is_base_date = len(base_name) == 10 and base_name[4] == "-" and base_name[7] == "-"

            if selected_date == "__device_only__" or (is_base_date and selected_date in {base_name, "__all__"}):
                devices = {d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))}
            elif selected_date == "__all__":
                for date_folder in os.listdir(data_dir):
                    date_path = os.path.join(data_dir, date_folder)
                    if os.path.isdir(date_path) and len(date_folder) == 10 and date_folder[4] == "-":
                        for d in os.listdir(date_path):
                            if os.path.isdir(os.path.join(date_path, d)):
                                devices.add(d)
            else:
                date_path = os.path.join(data_dir, selected_date)
                if os.path.exists(date_path):
                    devices = {d for d in os.listdir(date_path) if os.path.isdir(os.path.join(date_path, d))}

            devices = sorted(devices)
            if not devices:
                discovery = detect_data_structure(data_dir)
                inferred_devices = discovery.get("devices") or []
                if inferred_devices:
                    devices = sorted({d for d in inferred_devices if d})
            options = [{"label": "All Devices", "value": "__all__"}] + [
                {"label": d, "value": d} for d in devices
            ]
            option_values = {"__all__", *devices}
            default_val = devices[0] if devices else None

            config_dev = None
            if mode == "verify" and isinstance(cfg, dict):
                verify_cfg = cfg.get("verify") if isinstance(cfg.get("verify"), dict) else {}
                config_dev = verify_cfg.get("hydrophone")
            if saved_device in option_values:
                default_val = saved_device
            elif current_device in option_values:
                default_val = current_device
            elif config_dev in devices:
                default_val = config_dev

            tab_iso_debug(
                "discover_devices_return",
                mode=mode,
                selected_date=selected_date,
                devices_count=len(devices),
                default_val=default_val,
                saved_device=saved_device,
                current_device=current_device,
                config_dev=config_dev,
            )
            return options, default_val
        except Exception as e:
            tab_iso_debug("discover_devices_error", mode=mode, selected_date=selected_date, error=str(e))
            return [], None

    @app.callback(
        Output("global-active-selection", "children"),
        Output("global-data-dir-display", "children", allow_duplicate=True),
        Input("label-data-store", "data"),
        Input("verify-data-store", "data"),
        Input("explore-data-store", "data"),
        Input("mode-tabs", "data"),
        Input("config-store", "data"),
        prevent_initial_call=True,
    )
    def update_active_selection_display(label_data, verify_data, explore_data, mode, cfg):
        data = {"label": label_data, "verify": verify_data, "explore": explore_data}.get(mode) or {}
        configured_data_dir = config_default_data_dir(cfg or {})
        data_dir = (data.get("source_data_dir") if data else None) or configured_data_dir
        data_dir_display = data_dir or "Not selected"
        tab_iso_debug(
            "active_selection_display",
            mode=mode,
            data_dir_display=data_dir_display,
            selected_snapshot=tab_data_snapshot(data),
        )

        if not data:
            return "No data loaded", data_dir_display

        summary = data.get("summary", {})
        date_str = summary.get("active_date")
        device = summary.get("active_hydrophone")

        if date_str and device:
            return f"{date_str} / {device}", data_dir_display
        return "Not selected", data_dir_display
