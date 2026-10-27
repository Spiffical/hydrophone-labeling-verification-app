"""The evidence figure for a clip's labels (config ``evidence_figures``,
app/services/evidence_figures.py): the sidebar's Evidence button opens it in
its own dialog, under the clip's caption. Dashboards without one keep both
hidden."""

from dash import Input, Output, html

from app.services.evidence_figures import evidence_caption, evidence_figure_src


def evidence_figure_view(cfg, modal_item):
    """(image src, link href, caption lines, section hidden) for the clip open
    in the modal."""
    item_id = modal_item.get("item_id") if isinstance(modal_item, dict) else None
    src = evidence_figure_src(cfg, item_id)
    if src is None:
        return "", "", [], True
    caption = [html.Div(line, className="modal-evidence-caption-line") for line in evidence_caption(cfg, item_id)]
    return src, src, caption, False


def register_modal_evidence_figure_callbacks(app, *, config):
    cfg = config.get("evidence_figures") if isinstance(config, dict) else None
    if not cfg:
        return

    @app.callback(
        Output("modal-evidence-image", "src"),
        Output("modal-evidence-link", "href"),
        Output("modal-evidence-caption", "children"),
        Output("modal-evidence", "hidden"),
        Input("modal-item-store", "data"),
    )
    def render_modal_evidence_figure(modal_item):
        return evidence_figure_view(cfg, modal_item)

    # The dialog closes itself (Esc, ×, a click outside).
    @app.callback(
        Output("modal-evidence-viewer", "is_open"),
        Input("modal-evidence-open", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_modal_evidence_figure(n_clicks):
        return bool(n_clicks)
