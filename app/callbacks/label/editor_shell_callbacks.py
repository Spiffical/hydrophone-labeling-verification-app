"""Callbacks for label-editor shell state and tab display restoration."""

from dash import Input, Output, State
from dash.exceptions import PreventUpdate


def register_label_editor_shell_callbacks(
    app,
    *,
    _create_folder_display,
):
    @app.callback(
        Output("label-editor-modal", "is_open", allow_duplicate=True),
        Output("label-editor-body", "children", allow_duplicate=True),
        Output("active-item-store", "data", allow_duplicate=True),
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def close_editor_on_tab_switch(_mode):
        return False, [], None

    @app.callback(
        Output("label-data-store", "data", allow_duplicate=True),
        Input("label-output-input", "value"),
        State("label-data-store", "data"),
        prevent_initial_call=True,
    )
    def sync_label_output_path_to_store(path_value, label_data):
        """Sync manual edits to the labels output path back to the data store."""
        if not label_data or path_value is None:
            raise PreventUpdate

        summary = label_data.get("summary", {})
        if summary.get("labels_file") == path_value:
            raise PreventUpdate

        new_data = dict(label_data)
        new_data["summary"] = dict(summary)
        new_data["summary"]["labels_file"] = path_value
        return new_data

    @app.callback(
        Output("label-spec-folder-display", "children", allow_duplicate=True),
        Output("label-audio-folder-display", "children", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Input("mode-tabs", "data"),
        State("label-data-store", "data"),
        prevent_initial_call=True,
    )
    def reset_label_displays_on_tab_switch(mode, label_data):
        """Restore Label tab folder displays from label data when tab is activated."""
        if mode != "label":
            raise PreventUpdate

        if not label_data or not label_data.get("items"):
            return "Not set", "Not set", ""

        summary = label_data.get("summary", {})
        data_root = summary.get("data_root", "")
        spec_display = _create_folder_display(
            summary.get("spectrogram_folder") or "Not set",
            summary.get("spectrogram_folders_list", []),
            data_root,
            "label-spec-popover-tab",
        )
        audio_display = _create_folder_display(
            summary.get("audio_folder") or "Not set",
            summary.get("audio_folders_list", []),
            data_root,
            "label-audio-popover-tab",
        )
        labels_file = summary.get("labels_file") or ""
        return spec_display, audio_display, labels_file
