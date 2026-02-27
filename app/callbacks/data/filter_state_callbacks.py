"""Tab-specific filter-state persistence callbacks."""

from copy import deepcopy

from dash import Input, Output, State, ctx
from dash.exceptions import PreventUpdate


def register_filter_state_callbacks(app, *, tab_iso_debug):
    """Persist date/device filters per active tab."""

    @app.callback(
        Output("tab-filter-state-store", "data"),
        Input("global-date-selector", "value"),
        Input("global-device-selector", "value"),
        State("mode-tabs", "data"),
        State("tab-filter-state-store", "data"),
        prevent_initial_call=True,
    )
    def persist_active_tab_filters(selected_date, selected_device, mode, tab_filter_state):
        mode = (mode or "").strip()
        if mode not in {"label", "verify", "explore"}:
            tab_iso_debug(
                "persist_filters_skip_invalid_mode",
                mode=mode,
                selected_date=selected_date,
                selected_device=selected_device,
            )
            raise PreventUpdate

        state = deepcopy(tab_filter_state or {})
        for tab in ("label", "verify", "explore"):
            if not isinstance(state.get(tab), dict):
                state[tab] = {"date": None, "device": None}

        current = state.get(mode, {})
        next_entry = dict(current)
        triggered = ctx.triggered_id
        if triggered == "global-date-selector":
            next_entry["date"] = selected_date
        elif triggered == "global-device-selector":
            next_entry["device"] = selected_device
        else:
            next_entry["date"] = selected_date
            next_entry["device"] = selected_device

        if current == next_entry:
            tab_iso_debug(
                "persist_filters_nochange",
                mode=mode,
                triggered=str(triggered),
                selected_date=selected_date,
                selected_device=selected_device,
            )
            raise PreventUpdate

        state[mode] = next_entry
        tab_iso_debug(
            "persist_filters_update",
            mode=mode,
            triggered=str(triggered),
            selected_date=selected_date,
            selected_device=selected_device,
            next_entry=next_entry,
        )
        return state
