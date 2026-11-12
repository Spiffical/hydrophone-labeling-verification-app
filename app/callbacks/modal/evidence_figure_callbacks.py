"""The evidence figure for a clip's labels (config ``evidence_figures``,
app/services/evidence_figures.py): the sidebar's Evidence button opens it in
its own dialog, under the clip's caption. Dashboards without one keep both
hidden.

Clips worth comparing with the one under review (``<item_id>.json`` in the same
folder) become buttons under the Evidence button. Each opens that clip, view
only, in a window that floats beside the review window: its spectrogram (drawn
as the review window draws one), its audio and its caption. Nothing there can
change a review."""

from datetime import datetime
from math import ceil, floor

from dash import ALL, Input, Output, State, ctx, html
from dash.exceptions import PreventUpdate

from app.components.audio_player import _build_audio_src
from app.services.evidence_figures import evidence_caption, evidence_figure_src, evidence_related
from app.services.verify_modal_cache import get_verify_modal_item
from app.utils.image_processing import get_effective_item_spectrogram_render_settings
from app.utils.image_utils import build_modal_image_request_src

# The view-only window's spectrogram, at most this many pixels.
RELATED_IMAGE_WIDTH = 1100
RELATED_IMAGE_HEIGHT = 420


def evidence_figure_view(cfg, modal_item):
    """(image src, link href, caption lines, section hidden) for the clip open
    in the modal."""
    item_id = modal_item.get("item_id") if isinstance(modal_item, dict) else None
    src = evidence_figure_src(cfg, item_id)
    if src is None:
        return "", "", [], True
    caption = [html.Div(line, className="modal-evidence-caption-line") for line in evidence_caption(cfg, item_id)]
    return src, src, caption, False


def evidence_related_buttons(cfg, modal_item):
    """The buttons for the clips to compare with the clip open in the modal
    ([] without any)."""
    item_id = modal_item.get("item_id") if isinstance(modal_item, dict) else None
    related = evidence_related(cfg, item_id)
    if not related:
        return []
    buttons = [
        html.Button(
            entry["label"],
            # Only the clip id: ids with characters outside ASCII lose their clicks on the
            # way to the server (Dash matches the browser's and its own JSON of the id).
            id={"type": "evidence-related-open", "item_id": entry["item_id"]},
            type="button",
            n_clicks=0,
            className="btn btn-sm btn-outline-secondary modal-evidence-related-button",
            title=entry["detail"] or "Open this clip beside the one under review",
        )
        for entry in related
    ]
    return [html.Div("Compare with similar clips:", className="modal-evidence-related-title"),
            html.Div(buttons, className="modal-evidence-related-buttons")]


def _clip_seconds(item):
    """The clip's length: from its start and end times when the item has them,
    else from its audio file's header; None when neither works."""
    try:
        start = datetime.fromisoformat(str(item.get("audio_start_time")).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(item.get("audio_end_time")).replace("Z", "+00:00"))
        seconds = (end - start).total_seconds()
        if seconds > 0:
            return seconds
    except (TypeError, ValueError):
        pass
    try:
        import soundfile

        seconds = float(soundfile.info(item.get("audio_path")).duration)
    except Exception:
        return None
    return seconds if seconds > 0 else None


def _round_ticks(low, high, steps=(1, 2, 5, 10, 20, 50, 100, 200, 500), most=6):
    """Round values between low and high, at most `most` of them."""
    span = high - low
    if span <= 0:
        return []
    step = next((s for s in steps if span / s <= most), steps[-1])
    return [k * step for k in range(int(ceil(low / step)), int(floor(high / step)) + 1)]


def related_plot(image_src, freq_min_hz, freq_max_hz, seconds):
    """The spectrogram image stretched over a fixed height (its rows are frequency
    bins), with kHz labels up its side and seconds along the bottom."""
    children = [html.Img(src=image_src, className="modal-related-image", alt="Spectrogram of the similar clip")]
    if freq_min_hz is not None and freq_max_hz and freq_max_hz > freq_min_hz:
        # kHz for dolphin-style ranges, Hz for low ones such as 5-100 Hz.
        scale, unit = (1000.0, "kHz") if freq_max_hz >= 2000.0 else (1.0, "Hz")
        low, high = freq_min_hz / scale, freq_max_hz / scale
        children.append(html.Div(
            [html.Span(f"{tick:g}", className="modal-related-tick", style={"bottom": f"{(tick - low) / (high - low) * 100:.2f}%"})
             for tick in _round_ticks(low, high, most=7)] + [html.Span(unit, className="modal-related-unit")],
            className="modal-related-yaxis",
        ))
    if seconds:
        children.append(html.Div(
            [html.Span(f"{tick:g} s", className="modal-related-tick", style={"left": f"{tick / seconds * 100:.2f}%"})
             for tick in _round_ticks(0.0, seconds, most=5)],
            className="modal-related-xaxis",
        ))
    return html.Div(children, className="modal-related-plot")


def related_clip_view(cfg, config, cache_key, item_id, label):
    """(title, spectrogram, audio src, caption, evidence href) for a clip opened
    from a related-clip button. A clip that is not in the loaded queue shows only
    a note."""
    title = label or item_id
    item = get_verify_modal_item(cache_key, item_id)
    if not isinstance(item, dict):
        return title, [], "", [html.Div("This clip is not in the loaded queue.", className="modal-evidence-caption-line")], ""
    audio_cfg = (config or {}).get("audio", {}) if isinstance(config, dict) else {}
    image_src = build_modal_image_request_src(
        item,
        cfg=config,
        max_width=RELATED_IMAGE_WIDTH,
        max_height=RELATED_IMAGE_HEIGHT,
    )
    render = get_effective_item_spectrogram_render_settings(item, config)
    plot = related_plot(image_src, render.get("freq_min_hz"), render.get("freq_max_hz"), _clip_seconds(item))
    audio_src = _build_audio_src(
        item.get("audio_path"),
        transport=audio_cfg.get("transport", "direct"),
        mp3_bitrate=audio_cfg.get("mp3_bitrate"),
        flac_sample_rate=audio_cfg.get("flac_sample_rate"),
    ) or ""
    caption = [html.Div(line, className="modal-evidence-caption-line") for line in evidence_caption(cfg, item_id)]
    return title, plot, audio_src, caption, evidence_figure_src(cfg, item_id) or ""


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

    @app.callback(
        Output("modal-evidence-related", "children"),
        Input("modal-item-store", "data"),
    )
    def render_modal_evidence_related(modal_item):
        return evidence_related_buttons(cfg, modal_item)

    # Opens (or switches) the view-only window; it closes itself (Esc, ×).
    @app.callback(
        Output("modal-related-viewer", "is_open"),
        Output("modal-related-title", "children"),
        Output("modal-related-plot", "children"),
        Output("modal-related-audio", "src"),
        Output("modal-related-caption", "children"),
        Output("modal-related-evidence-link", "href"),
        Input({"type": "evidence-related-open", "item_id": ALL}, "n_clicks"),
        State("modal-item-store", "data"),
        State("verify-data-cache-key-store", "data"),
        prevent_initial_call=True,
    )
    def open_related_clip(_n_clicks, modal_item, cache_key):
        # New buttons (another clip opened in the review window) fire this with
        # no click; only a real click opens the window.
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not any(t.get("value") for t in ctx.triggered):
            raise PreventUpdate
        item_id = triggered.get("item_id")
        current = modal_item.get("item_id") if isinstance(modal_item, dict) else None
        label = next((entry["label"] for entry in evidence_related(cfg, current) if entry["item_id"] == item_id), item_id)
        title, plot, audio_src, caption, evidence_href = related_clip_view(cfg, config, cache_key, item_id, label)
        return True, title, plot, audio_src, caption, evidence_href
