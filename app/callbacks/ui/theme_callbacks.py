"""Theme callbacks."""

from dash import Input, Output, State, html
from dash.exceptions import PreventUpdate


def register_theme_callbacks(app):
    """Register theme toggle and shell styling callbacks."""

    @app.callback(
        Output("theme-store", "data"),
        Input("theme-toggle", "n_clicks"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_theme_store(n_clicks, theme):
        if not n_clicks:
            raise PreventUpdate
        theme = theme or "light"
        return "dark" if theme == "light" else "light"

    @app.callback(
        Output("theme-toggle", "children"),
        Output("theme-toggle", "className"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def sync_theme_toggle(theme):
        theme = theme or "light"
        is_dark = theme == "dark"
        icon_class = "bi bi-sun" if is_dark else "bi bi-moon-stars"
        btn_class = "icon-btn theme-btn"
        if is_dark:
            btn_class += " icon-btn--active"
        return html.I(className=icon_class), btn_class

    @app.callback(
        Output("app-shell", "className"),
        Output("app-shell", "style"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def apply_theme(theme):
        theme = theme or "light"
        return f"app-shell theme-{theme}", {}

    app.clientside_callback(
        """
        function(theme) {
            theme = theme || 'light';
            document.body.classList.remove('theme-light', 'theme-dark');
            document.body.classList.add('theme-' + theme);
            return '';
        }
        """,
        Output("dummy-output", "data"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
