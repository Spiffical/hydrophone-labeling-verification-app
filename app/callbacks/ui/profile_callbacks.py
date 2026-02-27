"""Profile and profile-guard UI callbacks."""

import logging

from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

logger = logging.getLogger(__name__)


def register_ui_callbacks(
    app,
    *,
    reset_profile_on_start,
    profile_required_message,
    profile_name_email,
    is_profile_complete,
    is_valid_email,
):
    """Register profile and profile-guard callbacks."""

    @app.callback(
        Output("user-profile-store", "data", allow_duplicate=True),
        Output("profile-reset-applied-store", "data"),
        Input("mode-tabs", "data"),
        State("profile-reset-applied-store", "data"),
        State("user-profile-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def maybe_reset_profile_on_start(mode, reset_applied, current_profile):
        _ = mode
        if not reset_profile_on_start:
            raise PreventUpdate
        if reset_applied:
            raise PreventUpdate
        profile = current_profile if isinstance(current_profile, dict) else {}
        if not profile.get("name") and not profile.get("email"):
            return no_update, True
        logger.warning("[PROFILE_RESET] reset_profile_on_start_applied=true")
        return {"name": "", "email": ""}, True

    @app.callback(
        Output("profile-modal", "is_open", allow_duplicate=True),
        Output("profile-name", "value", allow_duplicate=True),
        Output("profile-email", "value", allow_duplicate=True),
        Output("profile-name", "invalid", allow_duplicate=True),
        Output("profile-email", "invalid", allow_duplicate=True),
        Output("profile-required-message", "children", allow_duplicate=True),
        Input({"type": "edit-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-action-edit", "scope": ALL}, "n_clicks"),
        Input("label-editor-save", "n_clicks"),
        Input({"type": "confirm-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "modal-action-confirm", "scope": ALL}, "n_clicks"),
        Input({"type": "label-label-delete", "target": ALL}, "n_clicks"),
        Input({"type": "label-save-btn", "item_id": ALL}, "n_clicks"),
        Input({"type": "verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-accept", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-reject", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "verify-label-delete", "item_id": ALL, "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "target": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-accept", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-reject", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-verify-label-delete", "label": ALL}, "n_clicks_timestamp"),
        Input({"type": "modal-label-add-box", "label": ALL}, "n_clicks"),
        Input({"type": "modal-label-delete-btn", "label": ALL}, "n_clicks"),
        Input("unsaved-save-btn", "n_clicks"),
        Input("modal-image-graph", "relayoutData"),
        Input("modal-image-graph", "clickData"),
        State("user-profile-store", "data"),
        State("mode-tabs", "data"),
        prevent_initial_call=True,
    )
    def prompt_profile_for_blocked_actions(
        edit_clicks,
        modal_edit_clicks,
        label_editor_save_clicks,
        confirm_clicks,
        modal_confirm_clicks,
        label_delete_clicks,
        label_save_clicks,
        verify_accept_clicks,
        verify_reject_clicks,
        verify_delete_clicks,
        verify_accept_clicks_legacy,
        verify_reject_clicks_legacy,
        verify_delete_clicks_legacy,
        modal_verify_accept_clicks,
        modal_verify_reject_clicks,
        modal_verify_delete_clicks,
        modal_verify_accept_clicks_legacy,
        modal_verify_reject_clicks_legacy,
        modal_verify_delete_clicks_legacy,
        modal_add_box_clicks,
        modal_delete_label_clicks,
        unsaved_save_clicks,
        modal_graph_relayout,
        modal_graph_click,
        profile,
        mode,
    ):
        _ = (
            edit_clicks,
            modal_edit_clicks,
            label_editor_save_clicks,
            confirm_clicks,
            modal_confirm_clicks,
            label_delete_clicks,
            label_save_clicks,
            verify_accept_clicks,
            verify_reject_clicks,
            verify_delete_clicks,
            verify_accept_clicks_legacy,
            verify_reject_clicks_legacy,
            verify_delete_clicks_legacy,
            modal_verify_accept_clicks,
            modal_verify_reject_clicks,
            modal_verify_delete_clicks,
            modal_verify_accept_clicks_legacy,
            modal_verify_reject_clicks_legacy,
            modal_verify_delete_clicks_legacy,
            modal_add_box_clicks,
            modal_delete_label_clicks,
            unsaved_save_clicks,
            modal_graph_relayout,
            modal_graph_click,
        )
        if not ctx.triggered:
            raise PreventUpdate
        if is_profile_complete(profile):
            raise PreventUpdate
        if (mode or "label") == "explore":
            raise PreventUpdate

        prop_id = (ctx.triggered[0] or {}).get("prop_id", "")
        if prop_id.endswith(".relayoutData"):
            relayout = modal_graph_relayout if isinstance(modal_graph_relayout, dict) else {}
            keys = set(relayout.keys())
            has_shape_edit = bool(
                "shapes" in relayout
                or any(str(key).startswith("shapes[") for key in keys)
            )
            if not has_shape_edit:
                raise PreventUpdate
        elif prop_id.endswith(".clickData"):
            click_data = modal_graph_click if isinstance(modal_graph_click, dict) else {}
            points = click_data.get("points")
            if not (isinstance(points, list) and points):
                raise PreventUpdate

        name, email = profile_name_email(profile)
        return (
            True,
            name,
            email,
            not bool(name),
            not is_valid_email(email),
            profile_required_message,
        )

    @app.callback(
        Output("profile-modal", "is_open"),
        Output("profile-name", "value"),
        Output("profile-email", "value"),
        Output("profile-name", "invalid"),
        Output("profile-email", "invalid"),
        Output("profile-required-message", "children"),
        Input("profile-btn", "n_clicks"),
        Input("profile-cancel", "n_clicks"),
        State("user-profile-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_profile_modal(open_clicks, cancel_clicks, profile):
        triggered = ctx.triggered_id
        if triggered == "profile-btn":
            profile = profile or {}
            name, email = profile_name_email(profile)
            return True, name, email, False, False, profile_required_message
        if triggered == "profile-cancel":
            return False, no_update, no_update, False, False, profile_required_message
        raise PreventUpdate

    @app.callback(
        Output("user-profile-store", "data"),
        Output("profile-modal", "is_open", allow_duplicate=True),
        Output("profile-name", "invalid", allow_duplicate=True),
        Output("profile-email", "invalid", allow_duplicate=True),
        Output("profile-required-message", "children", allow_duplicate=True),
        Input("profile-save", "n_clicks"),
        State("profile-name", "value"),
        State("profile-email", "value"),
        prevent_initial_call=True,
    )
    def save_profile(n_clicks, name, email):
        if not n_clicks:
            raise PreventUpdate
        normalized_name = str(name or "").strip()
        normalized_email = str(email or "").strip()
        name_invalid = not bool(normalized_name)
        email_invalid = not is_valid_email(normalized_email)
        if name_invalid or email_invalid:
            return (
                no_update,
                True,
                name_invalid,
                email_invalid,
                profile_required_message,
            )
        return (
            {"name": normalized_name, "email": normalized_email},
            False,
            False,
            False,
            profile_required_message,
        )

    @app.callback(
        Output("profile-name-display", "children"),
        Output("profile-email-display", "children"),
        Input("user-profile-store", "data"),
        prevent_initial_call=False,
    )
    def update_profile_display(profile):
        profile = profile or {}
        name = profile.get("name") or "Anonymous"
        email = profile.get("email") or "email not set"
        return name, email

    @app.callback(
        Output("profile-required-banner", "children"),
        Output("profile-required-banner", "style"),
        Output("profile-btn", "className"),
        Input("user-profile-store", "data"),
        Input("mode-tabs", "data"),
        prevent_initial_call=False,
    )
    def render_profile_requirement_banner(profile, mode):
        base_profile_class = "profile-summary"
        mode = (mode or "label").strip()
        profile_complete = is_profile_complete(profile)

        if mode == "explore" or profile_complete:
            return (
                no_update,
                {"display": "none"},
                base_profile_class,
            )

        banner = html.Div(
            [
                html.I(className="bi bi-exclamation-triangle-fill"),
                html.Span("Set your profile (name and email) using the top-right profile button before labeling or verifying."),
            ],
            className="profile-required-banner-inner",
        )
        return (
            banner,
            {"display": "block"},
            f"{base_profile_class} profile-summary--required",
        )
