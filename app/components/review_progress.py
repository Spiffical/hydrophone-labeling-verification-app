"""The review page's progress chart and total."""

import math

from dash import html

from app.services.review_view import PROGRESS_STATES, bin_range, progress_segment_position

_STATE_WORDS = {"verified": "verified", "unverified": "not yet verified"}


def _compact_count(value):
    if value < 1000:
        return str(value)
    return f"{value / 1000:.1f}K".replace(".0K", "K")


def _segment_summary(segment):
    start, end = bin_range(segment["bin"])
    return f"{segment['category']} {start}–{end}%, {_STATE_WORDS[segment['state']]}"


def _segment(index, category, state, count, picked):
    position = {"bin": index, "category": category, "state": state}
    is_picked = picked is not None and progress_segment_position(picked) == progress_segment_position(position)
    picked_class = " review-bar-segment--picked" if is_picked else ""
    clips = "clip" if count == 1 else "clips"
    return html.Button(
        id={"type": "verify-progress-segment", **position},
        n_clicks=0,
        type="button",
        className=(
            f"review-bar-segment review-bar-segment--{state} "
            f"review-bar-segment--{category.lower()}{picked_class}"
        ),
        style={"flexGrow": count},
        title=f"{_segment_summary(position)}: {count:,} {clips}",
        **{"aria-pressed": "true" if is_picked else "false"},
    )


def _tooltip(progress_bin):
    rows = [
        html.Div(
            [
                html.Span(className=f"review-tip-key review-tip-key--{entry['category'].lower()}"),
                html.Strong(f"{entry['verified'] + entry['unverified']:,}"),
                html.Span(entry["category"]),
                html.Span(f"{entry['verified']:,} verified", className="review-tip-muted"),
            ],
            className="review-tip-row",
        )
        for entry in reversed(progress_bin["categories"])
    ]
    return html.Div(
        [
            html.Div(
                f"{progress_bin['start']}–{progress_bin['end']}% confidence",
                className="review-tip-title",
            ),
            *rows,
        ],
        className="review-tip",
    )


def _bar(index, progress_bin, peak, picked, *, tip_opens_left):
    total = progress_bin["total"]
    # Square-root heights: a day is mostly near-zero clips, and on a straight scale
    # the handful of confident ones this page exists for would not show at all.
    height = math.sqrt(total / peak) * 100 if total and peak else 0
    segments = []
    for entry in progress_bin["categories"]:
        for state in PROGRESS_STATES:
            if entry[state]:
                segments.append(_segment(index, entry["category"], state, entry[state], picked))
    tip_class = " review-bar--tip-left" if tip_opens_left else ""
    label = (
        f"{progress_bin['start']} to {progress_bin['end']} percent confidence: "
        f"{total} clips, {progress_bin['verified']} verified"
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Span(_compact_count(total) if total else "", className="review-bar-count"),
                    html.Div(segments, className="review-bar-stack", style={"height": f"{height:.1f}%"}),
                ],
                className="review-bar-plot",
            ),
            html.Span(f"{progress_bin['start']}%", className="review-bar-tick"),
            _tooltip(progress_bin) if total else None,
        ],
        className=f"review-bar{tip_class}",
        role="group",
        **{"aria-label": label},
    )


def _chart_note(picked):
    if picked is None:
        return html.Span(
            "Clips by top model confidence. Click part of a bar to show those clips.",
            className="review-key-note",
        )
    return html.Span(
        [
            html.Span(_segment_summary(picked), className="review-key-picked"),
            html.Button(
                "Clear",
                id={"type": "verify-segment-clear", "chart": "progress"},
                n_clicks=0,
                type="button",
                className="review-selection-clear",
            ),
        ],
        className="review-key-note",
    )


def create_progress_chart(progress, picked=None):
    bins = progress.get("bins") or []
    peak = max((progress_bin["total"] for progress_bin in bins), default=0)
    return [
        html.Div(
            [
                _bar(index, progress_bin, peak, picked, tip_opens_left=index >= len(bins) // 2)
                for index, progress_bin in enumerate(bins)
            ],
            className="review-bars review-bars--picked" if picked else "review-bars",
        ),
        html.Div(
            [
                html.Span([html.Span(className="review-key-swatch"), "Verified"]),
                html.Span(
                    [html.Span(className="review-key-swatch review-key-swatch--dim"), "Not yet"],
                ),
                _chart_note(picked),
            ],
            className="review-chart-key",
        ),
    ]


def create_progress_total(progress, *, scoped):
    total = int(progress.get("total") or 0)
    verified = int(progress.get("verified") or 0)
    percent = round(verified / total * 100) if total else 0
    # Never round a started review up to 100% or an unstarted one's sliver away.
    if verified and verified < total:
        percent = min(99, max(1, percent))
    return [
        html.Div("Selected" if scoped else "Total", className="review-total-title"),
        html.Div(
            html.Span(f"{percent}%", className="review-total-percent"),
            className="review-total-ring",
            style={"--review-progress": f"{verified / total * 100 if total else 0:.1f}%"},
            role="img",
            **{"aria-label": f"{verified} of {total} clips verified"},
        ),
        html.Div(f"{verified:,}/{total:,}", className="review-total-count"),
    ]
