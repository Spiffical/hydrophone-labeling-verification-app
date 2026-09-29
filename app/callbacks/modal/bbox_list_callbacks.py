"""Client-side callbacks for the modal box list and the tag given to new boxes."""

from dash import ClientsideFunction, Input, Output, State


def register_modal_bbox_list_callbacks(app):
    # Render the box list and tag toolbar in the browser. The list keeps its own
    # DOM (and scroll position) instead of being rebuilt with modal-item-actions.
    app.clientside_callback(
        ClientsideFunction(namespace="bboxList", function_name="render"),
        Output("modal-bbox-list-render-sink", "data"),
        Input("modal-bbox-store", "data"),
        Input("modal-bbox-active-tag-store", "data"),
        Input("mode-tabs", "data"),
        Input("current-filename", "data"),
        Input("user-profile-store", "data"),
        Input("image-modal", "is_open"),
        State("modal-bbox-list-config-store", "data"),
    )

    # Tag edits from the list: update boxes, figure overlays and unsaved state
    # without a server round trip.
    app.clientside_callback(
        ClientsideFunction(namespace="bboxList", function_name="applyCommand"),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Input("modal-bbox-command-store", "data"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )

    # The box editor's tag list follows the label chosen in it (tags are per species).
    app.clientside_callback(
        ClientsideFunction(namespace="bboxList", function_name="editorTagOptions"),
        Output("bbox-editor-tag-dropdown", "options"),
        Input("bbox-editor-label-dropdown", "value"),
        Input("bbox-editor-tag-dropdown", "value"),
        State("modal-bbox-list-config-store", "data"),
    )

    # "Delete box" in the box editor removes the box being edited (bbox_list.js).
    app.clientside_callback(
        ClientsideFunction(namespace="bboxList", function_name="deleteFromEditor"),
        Output("bbox-editor-modal", "is_open", allow_duplicate=True),
        Input("bbox-editor-delete", "n_clicks"),
        State("bbox-editor-index-store", "data"),
        State("current-filename", "data"),
        prevent_initial_call=True,
    )
