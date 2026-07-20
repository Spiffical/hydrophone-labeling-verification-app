"""Client-side modal bbox callbacks for Plotly draw and edit events."""

from dash import ClientsideFunction, Input, Output, State


def register_modal_bbox_graph_callbacks(app):
    app.clientside_callback(
        ClientsideFunction(
            namespace="bboxInteractions",
            function_name="updateBoxesFromGraph",
        ),
        Output("modal-bbox-store", "data", allow_duplicate=True),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Output("modal-active-box-label", "data", allow_duplicate=True),
        Output("modal-unsaved-store", "data", allow_duplicate=True),
        Output("modal-bbox-interaction-store", "data", allow_duplicate=True),
        Input("modal-image-graph", "relayoutData"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("modal-active-box-label", "data"),
        State("current-filename", "data"),
        State("mode-tabs", "data"),
        State("user-profile-store", "data"),
        State("modal-bbox-interaction-store", "data"),
        prevent_initial_call=True,
    )
