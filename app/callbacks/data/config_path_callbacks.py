"""Data-config sub-browser path callbacks."""

import os

from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate


def _count_spectrograms(folder):
    if not folder or not os.path.isdir(folder):
        return 0, []
    count = 0
    exts = set()
    try:
        for file_name in os.listdir(folder):
            ext = os.path.splitext(file_name)[1].lower()
            if ext in {".mat", ".npy", ".png", ".jpg"}:
                count += 1
                exts.add(ext)
    except Exception:
        pass
    return count, list(exts)


def _count_audio(folder):
    if not folder or not os.path.isdir(folder):
        return 0
    count = 0
    try:
        for file_name in os.listdir(folder):
            if os.path.splitext(file_name)[1].lower() in {".flac", ".wav", ".mp3"}:
                count += 1
    except Exception:
        pass
    return count


def register_data_config_path_callbacks(app, *, create_info_badge, create_predictions_info):
    """Register browse/open and selected-path apply callbacks."""

    @app.callback(
        Output("folder-browser-modal", "is_open", allow_duplicate=True),
        Output("folder-browser-path-store", "data", allow_duplicate=True),
        Output("path-browse-target-store", "data"),
        Input("data-config-spec-browse", "n_clicks"),
        Input("data-config-audio-browse", "n_clicks"),
        Input("data-config-predictions-browse", "n_clicks"),
        Input("label-output-browse-btn", "n_clicks"),
        Input({"type": "predictions-file-browse", "index": ALL}, "n_clicks"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("label-output-input", "value"),
        State("data-root-path-store", "data"),
        State("predictions-files-store", "data"),
        prevent_initial_call=True,
    )
    def open_path_browser(
        spec_clicks,
        audio_clicks,
        predictions_clicks,
        labels_clicks,
        predictions_multi_clicks,
        spec_folder,
        audio_folder,
        labels_path,
        base_path,
        predictions_entries,
    ):
        _ = spec_clicks, audio_clicks, predictions_clicks, labels_clicks, predictions_multi_clicks
        triggered = ctx.triggered_id
        if not ctx.triggered:
            raise PreventUpdate

        triggered_value = ctx.triggered[0].get("value")
        if isinstance(triggered_value, list):
            if not any(v for v in triggered_value):
                raise PreventUpdate
        elif not triggered_value:
            raise PreventUpdate

        if triggered == "data-config-spec-browse":
            start_path = os.path.dirname(spec_folder) if spec_folder else (base_path or os.path.expanduser("~"))
            return True, start_path, {"target": "spectrogram", "type": "folder"}
        if triggered == "data-config-audio-browse":
            start_path = os.path.dirname(audio_folder) if audio_folder else (base_path or os.path.expanduser("~"))
            return True, start_path, {"target": "audio", "type": "folder"}
        if triggered == "data-config-predictions-browse":
            start_path = base_path or os.path.expanduser("~")
            return True, start_path, {"target": "predictions", "type": "file"}
        if triggered == "label-output-browse-btn":
            start_path = os.path.dirname(labels_path) if labels_path else (base_path or os.path.expanduser("~"))
            return True, start_path, {"target": "labels", "type": "file"}
        if isinstance(triggered, dict) and triggered.get("type") == "predictions-file-browse":
            index = triggered.get("index")
            start_path = base_path or os.path.expanduser("~")
            if predictions_entries:
                for entry in predictions_entries:
                    if entry.get("index") == index and entry.get("path"):
                        start_path = os.path.dirname(entry["path"])
                        break
            return True, start_path, {"target": "predictions", "type": "file", "index": index}

        raise PreventUpdate

    @app.callback(
        Output("data-config-spec-folder", "value", allow_duplicate=True),
        Output("data-config-audio-folder", "value", allow_duplicate=True),
        Output("data-config-predictions-file", "value", allow_duplicate=True),
        Output("data-config-spec-info", "children", allow_duplicate=True),
        Output("data-config-audio-info", "children", allow_duplicate=True),
        Output("data-config-predictions-info", "children", allow_duplicate=True),
        Output("data-config-modal", "is_open", allow_duplicate=True),
        Output("folder-browser-modal", "is_open", allow_duplicate=True),
        Output("label-output-input", "value", allow_duplicate=True),
        Output({"type": "predictions-file-input", "index": ALL}, "value"),
        Input("folder-browser-confirm", "n_clicks"),
        State("folder-browser-selected-store", "data"),
        State("path-browse-target-store", "data"),
        State("data-config-spec-folder", "value"),
        State("data-config-audio-folder", "value"),
        State("data-config-predictions-file", "value"),
        State("data-config-modal", "is_open"),
        State("label-output-input", "value"),
        State("mode-tabs", "data"),
        State({"type": "predictions-file-input", "index": ALL}, "value"),
        State({"type": "predictions-file-input", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def update_path_from_browser(
        confirm_clicks,
        selected_path,
        browse_target,
        current_spec,
        current_audio,
        current_predictions,
        config_modal_open,
        current_labels,
        current_mode,
        current_pred_values,
        current_pred_ids,
    ):
        _ = config_modal_open
        if not confirm_clicks or not selected_path:
            raise PreventUpdate

        if not browse_target or not browse_target.get("target"):
            raise PreventUpdate

        target = browse_target.get("target")
        is_label_mode = current_mode == "label"

        if target == "spectrogram":
            spec_count, spec_exts = _count_spectrograms(selected_path)
            spec_info = create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = create_info_badge(_count_audio(current_audio) > 0, _count_audio(current_audio))
            pred_info = create_predictions_info(current_predictions and os.path.isfile(current_predictions), is_label_mode)
            return selected_path, current_audio, current_predictions, spec_info, audio_info, pred_info, True, False, no_update, no_update

        if target == "audio":
            audio_count = _count_audio(selected_path)
            spec_count, spec_exts = _count_spectrograms(current_spec)
            spec_info = create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = create_info_badge(audio_count > 0, audio_count)
            pred_info = create_predictions_info(current_predictions and os.path.isfile(current_predictions), is_label_mode)
            return current_spec, selected_path, current_predictions, spec_info, audio_info, pred_info, True, False, no_update, no_update

        if target == "predictions":
            if browse_target and browse_target.get("index") is not None:
                updated_values = list(current_pred_values or [])
                updated_ids = list(current_pred_ids or [])
                for i, item_id in enumerate(updated_ids):
                    if item_id.get("index") == browse_target.get("index"):
                        if i < len(updated_values):
                            updated_values[i] = selected_path
                        else:
                            updated_values.append(selected_path)
                        break
                return (
                    current_spec,
                    current_audio,
                    current_predictions,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    False,
                    no_update,
                    updated_values,
                )
            pred_path = selected_path
            if os.path.isdir(selected_path):
                pred_file = os.path.join(selected_path, "predictions.json")
                labels_file = os.path.join(selected_path, "labels.json")
                if is_label_mode and os.path.exists(labels_file):
                    pred_path = labels_file
                elif os.path.exists(pred_file):
                    pred_path = pred_file
                elif os.path.exists(labels_file):
                    pred_path = labels_file

            spec_count, spec_exts = _count_spectrograms(current_spec)
            spec_info = create_info_badge(spec_count > 0, spec_count, ", ".join(spec_exts))
            audio_info = create_info_badge(_count_audio(current_audio) > 0, _count_audio(current_audio))
            pred_info = create_predictions_info(os.path.isfile(pred_path), is_label_mode)
            return current_spec, current_audio, pred_path, spec_info, audio_info, pred_info, True, False, no_update, no_update

        if target == "labels":
            labels_path = selected_path
            if os.path.isdir(selected_path):
                labels_path = os.path.join(selected_path, "labels.json")

            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, False, labels_path, no_update

        raise PreventUpdate

