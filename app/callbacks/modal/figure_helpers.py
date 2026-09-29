"""Modal figure overlay helpers (box shapes, edit and delete handles)."""

from copy import deepcopy

from dash import Patch

from app.services.modal_boxes import (
    axis_meta_from_figure,
    box_style,
    extent_to_shape,
    modal_box_edit_revision,
    modal_page_window_for_rect,
    modal_page_windows,
)


BBOX_DELETE_TRACE_NAME = "__bbox_delete_handle__"
BBOX_EDIT_TRACE_NAME = "__bbox_edit_handle__"


def patch_modal_boxes(figure_context, boxes, *, apply_boxes=None, **kwargs):
    """Update overlays without uploading or returning the spectrogram matrix."""
    context = deepcopy(figure_context) if isinstance(figure_context, dict) else {}
    previous_traces = context.get("data") or []
    updated = (apply_boxes or apply_modal_boxes_to_figure)(context, boxes, **kwargs)
    patch = Patch()
    for key in ("shapes", "annotations", "editrevision"):
        patch["layout"][key] = updated["layout"][key]
    overlay_names = {BBOX_DELETE_TRACE_NAME, BBOX_EDIT_TRACE_NAME}
    # Delete backwards to keep the indices of remaining traces stable.
    for index in range(len(previous_traces) - 1, -1, -1):
        if previous_traces[index].get("name") in overlay_names:
            del patch["data"][index]
    for trace in updated.get("data", []):
        if trace.get("name") in overlay_names:
            patch["data"].append(trace)
    return patch


def apply_modal_boxes_to_figure(
    fig,
    boxes,
    revision_bump=None,
    bbox_delete_trace_name=BBOX_DELETE_TRACE_NAME,
    bbox_edit_trace_name=BBOX_EDIT_TRACE_NAME,
):
    if hasattr(fig, "to_dict"):
        fig = fig.to_dict()
    if not isinstance(fig, dict):
        return fig
    layout = fig.get("layout") or {}
    if not isinstance(layout, dict):
        return fig

    axis_meta = axis_meta_from_figure(fig)
    x_span = max(1e-9, axis_meta.get("x_max", 1.0) - axis_meta.get("x_min", 0.0))
    y_span = max(1e-9, axis_meta.get("y_max", 1.0) - axis_meta.get("y_min", 0.0))

    existing_shapes = layout.get("shapes") or []
    marker_shape = None
    if isinstance(existing_shapes, list):
        for candidate in existing_shapes:
            if isinstance(candidate, dict) and candidate.get("name") == "playback-marker":
                marker_shape = candidate
                break
            if isinstance(candidate, dict) and candidate.get("type") == "line" and candidate.get("yref") == "paper":
                marker_shape = candidate
                break

    if marker_shape is None:
        marker_shape = {
            "type": "line",
            "x0": 0,
            "x1": 0,
            "y0": 0,
            "y1": 1,
            "yref": "paper",
            "editable": False,
            "name": "playback-marker",
            "line": {"color": "rgba(255, 0, 0, 0)", "width": 2, "dash": "solid"},
        }

    shape_list = [marker_shape]
    existing_annotations = layout.get("annotations") or []
    annotations = [
        annotation
        for annotation in existing_annotations
        if isinstance(annotation, dict)
        and (
            annotation.get("name") == "__spectrogram_source__"
            or str(annotation.get("text") or "").startswith("Source:")
        )
    ]
    delete_x = []
    delete_y = []
    delete_indices = []
    edit_x = []
    edit_y = []
    edit_indices = []

    prepared_boxes = []
    for box_idx, box in enumerate(boxes or []):
        if not isinstance(box, dict):
            continue
        shape_base = extent_to_shape(box.get("annotation_extent"), axis_meta)
        if not shape_base:
            continue
        style = box_style(box.get("source"), box.get("decision"), box.get("label"))
        rect = {
            "x0": min(shape_base["x0"], shape_base["x1"]),
            "x1": max(shape_base["x0"], shape_base["x1"]),
            "y0": min(shape_base["y0"], shape_base["y1"]),
            "y1": max(shape_base["y0"], shape_base["y1"]),
        }
        prepared_boxes.append(
            {
                "box_idx": box_idx,
                "box": box,
                "style": style,
                "rect": rect,
            }
        )

    all_rects = [entry["rect"] for entry in prepared_boxes]
    placed_handles = []
    x_min = axis_meta.get("x_min", 0.0)
    x_max = axis_meta.get("x_max", 1.0)
    y_min = axis_meta.get("y_min", 0.0)
    y_max = axis_meta.get("y_max", 1.0)
    # On long clips shown a page at a time, handles sit near their box at page
    # zoom and stay on the box's page. Mirrors applyBoxesToFigure in bbox_clientside.js.
    page_windows = modal_page_windows(x_min, x_max, axis_meta.get("page_length"))
    if len(page_windows) > 1:
        x_span = page_windows[0][1] - page_windows[0][0]
    edge_pad_x = max(1e-6, 0.012 * x_span)
    edge_pad_y = max(1e-6, 0.014 * y_span)
    y_bound_min = y_min + edge_pad_y
    y_bound_max = y_max - edge_pad_y
    if y_bound_max <= y_bound_min:
        y_bound_min, y_bound_max = y_min, y_max

    def _x_bounds(rect):
        page_start, page_end = modal_page_window_for_rect(rect, page_windows)
        lower, upper = page_start + edge_pad_x, page_end - edge_pad_x
        return (lower, upper) if upper > lower else (page_start, page_end)

    def _point_in_rect(x_val, y_val, rect, pad_x=0.0, pad_y=0.0):
        return (
            (rect["x0"] - pad_x) <= x_val <= (rect["x1"] + pad_x)
            and (rect["y0"] - pad_y) <= y_val <= (rect["y1"] + pad_y)
        )

    def _choose_delete_handle(rect, box_index):
        x_bound_min, x_bound_max = _x_bounds(rect)
        candidates = [
            (rect["x1"] + 0.012 * x_span, rect["y1"] + 0.012 * y_span),
            (rect["x0"] - 0.012 * x_span, rect["y1"] + 0.012 * y_span),
            (rect["x1"] + 0.012 * x_span, rect["y0"] - 0.012 * y_span),
            (rect["x0"] - 0.012 * x_span, rect["y0"] - 0.012 * y_span),
            (rect["x1"] - 0.008 * x_span, rect["y1"] + 0.010 * y_span),
            (rect["x0"] + 0.008 * x_span, rect["y1"] + 0.010 * y_span),
        ]
        pad_x = 0.002 * x_span
        pad_y = 0.002 * y_span
        min_dx = 0.020 * x_span
        min_dy = 0.030 * y_span

        for raw_x, raw_y in candidates:
            x_val = max(x_bound_min, min(x_bound_max, raw_x))
            y_val = max(y_bound_min, min(y_bound_max, raw_y))
            if any(_point_in_rect(x_val, y_val, r, pad_x=pad_x, pad_y=pad_y) for r in all_rects):
                continue
            if any(abs(x_val - hx) <= min_dx and abs(y_val - hy) <= min_dy for hx, hy in placed_handles):
                continue
            return x_val, y_val

        x_candidates = [x_bound_max - i * 0.06 * x_span for i in range(0, 12)]
        y_candidates = [y_bound_max - j * 0.08 * y_span for j in range(0, 10)]
        row_offset = box_index % 3
        for y_val in y_candidates[row_offset:] + y_candidates[:row_offset]:
            y_val = max(y_bound_min, min(y_bound_max, y_val))
            for x_val in x_candidates:
                x_val = max(x_bound_min, min(x_bound_max, x_val))
                if any(_point_in_rect(x_val, y_val, r, pad_x=pad_x, pad_y=pad_y) for r in all_rects):
                    continue
                if any(abs(x_val - hx) <= min_dx and abs(y_val - hy) <= min_dy for hx, hy in placed_handles):
                    continue
                return x_val, y_val

        base_x = max(x_bound_min, min(x_bound_max, rect["x1"] - 0.006 * x_span))
        base_y = max(y_bound_min, min(y_bound_max, rect["y1"] - 0.006 * y_span))
        stagger = (box_index % 6) * 0.022 * y_span
        return base_x, max(y_bound_min, min(y_bound_max, base_y - stagger))

    def _choose_edit_handle(rect):
        x_bound_min, x_bound_max = _x_bounds(rect)
        mid_y = rect["y0"] + ((rect["y1"] - rect["y0"]) / 2.0)
        candidates = [
            (rect["x1"] + 0.018 * x_span, mid_y),
            (rect["x1"] - 0.026 * x_span, rect["y0"] - 0.022 * y_span),
            (rect["x0"] + 0.026 * x_span, rect["y0"] - 0.022 * y_span),
            (rect["x0"] - 0.018 * x_span, mid_y),
            (rect["x1"] - 0.026 * x_span, rect["y1"] + 0.022 * y_span),
            (rect["x0"] + 0.026 * x_span, rect["y1"] + 0.022 * y_span),
        ]
        pad_x = 0.004 * x_span
        pad_y = 0.004 * y_span
        min_dx = 0.020 * x_span
        min_dy = 0.030 * y_span

        for raw_x, raw_y in candidates:
            x_val = max(x_bound_min, min(x_bound_max, raw_x))
            y_val = max(y_bound_min, min(y_bound_max, raw_y))
            if _point_in_rect(x_val, y_val, rect, pad_x=pad_x, pad_y=pad_y):
                continue
            if any(abs(x_val - hx) <= min_dx and abs(y_val - hy) <= min_dy for hx, hy in placed_handles):
                continue
            return x_val, y_val

        return (
            max(x_bound_min, min(x_bound_max, rect["x0"] + ((rect["x1"] - rect["x0"]) / 2.0))),
            max(y_bound_min, min(y_bound_max, rect["y0"] + ((rect["y1"] - rect["y0"]) / 2.0))),
        )

    for entry in prepared_boxes:
        box_idx = entry["box_idx"]
        box = entry["box"]
        style = entry["style"]
        rect = entry["rect"]

        # Box details are shown on hover (bbox_hover_affordances.js) rather than
        # as text on the plot; the name maps the shape back to its box.
        shape_list.append(
            {
                "type": "rect",
                "name": f"bbox-{box_idx}",
                "x0": rect["x0"],
                "x1": rect["x1"],
                "y0": rect["y0"],
                "y1": rect["y1"],
                "line": {"color": style["line_color"], "width": 2, "dash": style["line_dash"]},
                "fillcolor": style["fillcolor"],
                "editable": True,
                "layer": "above",
            }
        )

        x_handle, y_handle = _choose_delete_handle(rect, box_idx)
        placed_handles.append((x_handle, y_handle))
        delete_x.append(x_handle)
        delete_y.append(y_handle)
        delete_indices.append(box_idx)

        x_edit, y_edit = _choose_edit_handle(rect)
        edit_x.append(x_edit)
        edit_y.append(y_edit)
        edit_indices.append(box_idx)

    layout["shapes"] = shape_list
    layout["annotations"] = annotations
    layout["editrevision"] = modal_box_edit_revision(boxes, bump=revision_bump)
    fig_data = fig.get("data") or []
    if not isinstance(fig_data, list):
        fig_data = []
    fig_data = [
        trace
        for trace in fig_data
        if not (
            isinstance(trace, dict)
            and trace.get("name") in {bbox_delete_trace_name, bbox_edit_trace_name}
        )
    ]
    if edit_indices:
        fig_data.append(
            {
                "type": "scatter",
                "mode": "markers+text",
                "name": bbox_edit_trace_name,
                "showlegend": False,
                "x": edit_x,
                "y": edit_y,
                "customdata": edit_indices,
                "text": ["✎"] * len(edit_indices),
                "textposition": "middle center",
                "textfont": {"size": 12, "color": "#ffffff"},
                "marker": {
                    "size": 22,
                    "opacity": 0.95,
                    "color": "rgba(13, 110, 253, 0.94)",
                    "line": {"color": "#ffffff", "width": 1},
                    "symbol": "square",
                },
                "opacity": 1.0,
                "selectedpoints": [],
                "selected": {
                    "marker": {
                        "opacity": 0.92,
                        "color": "rgba(13, 110, 253, 0.96)",
                        "line": {"color": "#ffffff", "width": 1},
                    },
                    "textfont": {"color": "#ffffff"},
                },
                "unselected": {
                    "marker": {
                        "opacity": 0.95,
                        "color": "rgba(13, 110, 253, 0.94)",
                        "line": {"color": "#ffffff", "width": 1},
                    },
                    "textfont": {"color": "#ffffff"},
                },
                # Clicks still register, but no Plotly hover label: box details
                # show in the hover tooltip from bbox_hover_affordances.js.
                "hoverinfo": "none",
                "cliponaxis": True,
            }
        )
    if delete_indices:
        fig_data.append(
            {
                "type": "scatter",
                "mode": "markers+text",
                "name": bbox_delete_trace_name,
                "showlegend": False,
                "x": delete_x,
                "y": delete_y,
                "customdata": delete_indices,
                "text": ["×"] * len(delete_indices),
                "textposition": "middle center",
                "textfont": {"size": 12, "color": "#ffffff"},
                "marker": {
                    "size": 18,
                    "opacity": 1.0,
                    "color": "rgba(220, 53, 69, 0.98)",
                    "line": {"color": "#ffffff", "width": 1},
                    "symbol": "square",
                },
                "opacity": 1.0,
                "selectedpoints": [],
                "selected": {
                    "marker": {
                        "opacity": 1.0,
                        "color": "rgba(220, 53, 69, 0.98)",
                        "line": {"color": "#ffffff", "width": 1},
                    },
                    "textfont": {"color": "#ffffff"},
                },
                "unselected": {
                    "marker": {
                        "opacity": 1.0,
                        "color": "rgba(220, 53, 69, 0.98)",
                        "line": {"color": "#ffffff", "width": 1},
                    },
                    "textfont": {"color": "#ffffff"},
                },
                "hoverinfo": "none",
                "cliponaxis": True,
            }
        )
    fig["data"] = fig_data
    fig["layout"] = layout
    return fig
