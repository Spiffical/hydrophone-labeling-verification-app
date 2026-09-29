"""Controls on each spectrogram shown in the modal (the main plot and other ranges)."""

from dash import html


def panel_controls(label, remove_id, *, remove_disabled=False):
    """Minimize (modal_range_layout.js) and remove (a Dash callback) for one spectrogram."""
    name = label or "this spectrogram"
    return html.Div(
        [
            html.Button(
                html.I(className="bi bi-dash-lg", **{"aria-hidden": "true"}),
                type="button",
                className="spectrogram-panel-btn",
                title="Minimize",
                **{
                    "data-panel-action": "minimize",
                    "aria-label": f"Minimize {name}",
                    "aria-expanded": "true",
                },
            ),
            html.Button(
                html.I(className="bi bi-x-lg", **{"aria-hidden": "true"}),
                id=remove_id,
                n_clicks=0,
                type="button",
                className="spectrogram-panel-btn spectrogram-panel-btn--remove",
                title="Remove this spectrogram (the last one stays)",
                disabled=remove_disabled,
                **{"aria-label": f"Remove {name}"},
            ),
        ],
        className="spectrogram-panel-controls",
    )
