"""The review page's progress chart and total."""

import math

from dash import html


def _compact_count(value):
    if value < 1000:
        return str(value)
    return f"{value / 1000:.1f}K".replace(".0K", "K")


def _segment(category, state, count):
    return html.Span(
        className=f"review-bar-segment review-bar-segment--{state} review-bar-segment--{category.lower()}",
        style={"flexGrow": count},
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


def _bar(progress_bin, peak, *, tip_opens_left):
    total = progress_bin["total"]
    # Square-root heights: a day is mostly near-zero clips, and on a straight scale
    # the handful of confident ones this page exists for would not show at all.
    height = math.sqrt(total / peak) * 100 if total and peak else 0
    segments = []
    for entry in progress_bin["categories"]:
        for state in ("verified", "unverified"):
            if entry[state]:
                segments.append(_segment(entry["category"], state, entry[state]))
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
        tabIndex=0 if total else None,
        role="img",
        **{"aria-label": label},
    )


def create_progress_chart(progress):
    bins = progress.get("bins") or []
    peak = max((progress_bin["total"] for progress_bin in bins), default=0)
    return [
        html.Div(
            [
                _bar(progress_bin, peak, tip_opens_left=index >= len(bins) - 3)
                for index, progress_bin in enumerate(bins)
            ],
            className="review-bars",
        ),
        html.Div(
            [
                html.Span([html.Span(className="review-key-swatch"), "Verified"]),
                html.Span(
                    [html.Span(className="review-key-swatch review-key-swatch--dim"), "Not yet"],
                ),
                html.Span("Clips by top model confidence", className="review-key-note"),
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
