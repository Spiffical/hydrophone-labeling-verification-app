"""Data-config modal discovery/open callbacks."""

from dash import Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from app.callbacks.data.config_modal_helpers import build_modal_open_response
from app.utils.data_discovery import detect_data_structure


def register_data_config_modal_callbacks(
    app,
    *,
    tab_iso_debug,
    build_predictions_entries,
    create_info_badge,
    create_predictions_info,
):
    """Register modal open/discovery callback group."""

    @app.callback(
        Output("data-config-modal", "is_open"),
        Output("data-discovery-store", "data"),
        Output("data-config-structure-type", "children"),
        Output("data-config-structure-message", "children"),
        Output("data-config-spec-folder", "value"),
        Output("data-config-audio-folder", "value"),
        Output("data-config-predictions-file", "value"),
        Output("predictions-files-store", "data"),
        Output("data-config-spec-info", "children"),
        Output("data-config-audio-info", "children"),
        Output("data-config-predictions-info", "children"),
        Output("data-config-predictions-label", "children"),
        Output("data-config-hierarchy-detail", "children"),
        Output("hierarchy-toggle-container", "style"),
        Output("data-config-labels-recommendation", "children"),
        Output("data-config-spec-multi", "children"),
        Output("data-config-audio-multi", "children"),
        Output("data-config-spec-single-container", "style"),
        Output("data-config-audio-single-container", "style"),
        Output("data-config-predictions-multi", "children"),
        Output("data-config-predictions-single-container", "style"),
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Input("folder-browser-confirm", "n_clicks"),
        Input("data-config-cancel", "n_clicks"),
        Input("data-config-close", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def open_data_config(confirm_clicks, cancel_clicks, close_clicks, selected_path, browse_target, current_mode):
        _ = confirm_clicks, cancel_clicks, close_clicks
        triggered = ctx.triggered_id

        if triggered in ["data-config-cancel", "data-config-close"]:
            return (
                False,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                {"display": "none"},
            )

        if triggered != "folder-browser-confirm" or not selected_path:
            raise PreventUpdate

        # Sub-browse mode (specific field) should not open data config modal.
        if browse_target and browse_target.get("target"):
            raise PreventUpdate

        discovery = detect_data_structure(selected_path)
        open_response = build_modal_open_response(
            selected_path=selected_path,
            discovery=discovery,
            current_mode=current_mode,
            build_predictions_entries=build_predictions_entries,
            create_info_badge=create_info_badge,
            create_predictions_info=create_predictions_info,
        )

        return (
            True,
            *open_response,
            {"display": "none"},
        )

    @app.callback(
        Output("data-root-path-store", "data"),
        Input("folder-browser-confirm", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        prevent_initial_call=True,
    )
    def update_data_root_path(confirm_clicks, selected_path, browse_target):
        if not confirm_clicks or not selected_path:
            raise PreventUpdate
        if browse_target and browse_target.get("target"):
            raise PreventUpdate
        tab_iso_debug(
            "data_config_update_root_path",
            confirm_clicks=confirm_clicks,
            selected_path=selected_path,
            browse_target=browse_target,
        )
        return selected_path

    app.clientside_callback(
        """
        function(confirmClicks, browseTarget, selectedPath) {
            var dc = (window.dash_clientside || {});
            if (!confirmClicks) {
                return [dc.no_update, dc.no_update, dc.no_update];
            }
            if (browseTarget && browseTarget.target) {
                return [{display: "none"}, dc.no_update, dc.no_update];
            }
            if (!selectedPath) {
                return [{display: "none"}, dc.no_update, dc.no_update];
            }
            return [
                {display: "flex"},
                "Analyzing data folder...",
                "Detecting structure and files. This can take a moment on mounted drives."
            ];
        }
        """,
        Output("data-config-loading-overlay", "style", allow_duplicate=True),
        Output("data-load-title", "children", allow_duplicate=True),
        Output("data-load-subtitle", "children", allow_duplicate=True),
        Input("folder-browser-confirm", "n_clicks"),
        State("path-browse-target-store", "data"),
        State("folder-browser-selected-store", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("data-config-hierarchy-collapse", "is_open"),
        Output("hierarchy-toggle-icon", "className"),
        Output("data-config-hierarchy-toggle", "children"),
        Input("data-config-hierarchy-toggle", "n_clicks"),
        State("data-config-hierarchy-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_hierarchy_collapse(n_clicks, is_open):
        if n_clicks:
            new_is_open = not is_open
            icon_class = "bi bi-chevron-up me-1" if new_is_open else "bi bi-chevron-down me-1"
            button_text = "Hide Details" if new_is_open else "Show Details"
            return new_is_open, icon_class, [html.I(className=icon_class, id="hierarchy-toggle-icon"), button_text]
        raise PreventUpdate
