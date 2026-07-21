"""Immediate browser-side UI updates for verification decisions."""

from dash import ALL, ClientsideFunction, Input, Output, State


def register_verify_clientside_callbacks(app):
    app.clientside_callback(
        ClientsideFunction(
            namespace="verificationInteractions",
            function_name="optimisticDecision",
        ),
        Output({"type": "verify-label-badge", "target": ALL}, "className"),
        Output({"type": "verify-label-badge", "target": ALL}, "style"),
        Output({"type": "verify-label-state", "target": ALL}, "children"),
        Output({"type": "verify-label-accept", "target": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "verify-label-reject", "target": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "color", allow_duplicate=True),
        Output({"type": "confirm-btn", "item_id": ALL}, "outline", allow_duplicate=True),
        Output({"type": "modal-verify-label-badge", "target": ALL}, "className"),
        Output({"type": "modal-verify-label-row", "target": ALL}, "className"),
        Output({"type": "modal-verify-label-row", "target": ALL}, "style"),
        Output({"type": "modal-verify-label-state", "target": ALL}, "children"),
        Output({"type": "modal-verify-label-accept", "target": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "modal-verify-label-reject", "target": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "modal-action-confirm", "scope": ALL}, "disabled", allow_duplicate=True),
        Output({"type": "modal-action-confirm", "scope": ALL}, "color", allow_duplicate=True),
        Output({"type": "modal-action-confirm", "scope": ALL}, "outline", allow_duplicate=True),
        Input({"type": "verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        State({"type": "verify-label-badge", "target": ALL}, "id"),
        State({"type": "verify-label-state", "target": ALL}, "id"),
        State({"type": "verify-label-accept", "target": ALL}, "id"),
        State({"type": "verify-label-reject", "target": ALL}, "id"),
        State({"type": "confirm-btn", "item_id": ALL}, "id"),
        State({"type": "modal-verify-label-badge", "target": ALL}, "id"),
        State({"type": "modal-verify-label-row", "target": ALL}, "id"),
        State({"type": "modal-verify-label-state", "target": ALL}, "id"),
        State({"type": "modal-verify-label-accept", "target": ALL}, "id"),
        State({"type": "modal-verify-label-reject", "target": ALL}, "id"),
        State({"type": "modal-action-confirm", "scope": ALL}, "id"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(
            namespace="verificationInteractions",
            function_name="optimisticModalFigure",
        ),
        Output("modal-image-graph", "figure", allow_duplicate=True),
        Input({"type": "modal-verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        State("modal-bbox-store", "data"),
        State("modal-image-graph", "figure"),
        State("current-filename", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )


def register_label_clientside_callbacks(app):
    app.clientside_callback(
        ClientsideFunction(
            namespace="verificationInteractions",
            function_name="optimisticLabelDelete",
        ),
        Output({"type": "label-label-badge", "target": ALL}, "style"),
        Output({"type": "label-save-btn", "item_id": ALL}, "disabled"),
        Output({"type": "label-save-btn", "item_id": ALL}, "color"),
        Output({"type": "label-save-btn", "item_id": ALL}, "outline"),
        Input({"type": "label-label-delete", "target": ALL}, "n_clicks"),
        State({"type": "label-label-badge", "target": ALL}, "id"),
        State({"type": "label-save-btn", "item_id": ALL}, "id"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
