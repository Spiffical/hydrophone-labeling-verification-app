"""Long clips in the modal are shown a page at a time (modal_pages.js mirrors this)."""

from app.callbacks.modal.figure_helpers import BBOX_DELETE_TRACE_NAME, BBOX_EDIT_TRACE_NAME, apply_modal_boxes_to_figure
from app.services.modal_boxes import axis_meta_from_figure, modal_page_window_for_rect, modal_page_windows


def test_pages_have_one_width_and_the_last_ends_with_the_clip():
    assert modal_page_windows(0.0, 1394.0, 300.0) == [
        (0.0, 300.0), (300.0, 600.0), (600.0, 900.0), (900.0, 1200.0), (1094.0, 1394.0),
    ]
    assert modal_page_windows(0.0, 340.0, 300.0) == [(0.0, 300.0), (40.0, 340.0)]


def test_short_clips_and_turned_off_paging_are_one_page():
    assert modal_page_windows(0.0, 14.3, 300.0) == [(0.0, 14.3)]
    # Up to 10% over a page is still shown whole.
    assert modal_page_windows(0.0, 320.0, 300.0) == [(0.0, 320.0)]
    assert modal_page_windows(0.0, 1394.0, None) == [(0.0, 1394.0)]
    assert modal_page_windows(0.0, 1394.0, 0) == [(0.0, 1394.0)]


def test_a_box_belongs_to_the_page_that_holds_it():
    pages = modal_page_windows(0.0, 1394.0, 300.0)
    assert modal_page_window_for_rect({"x0": 1150.0, "x1": 1160.0}, pages) == (900.0, 1200.0)
    assert modal_page_window_for_rect({"x0": 1300.0, "x1": 1310.0}, pages) == (1094.0, 1394.0)
    # A box across a page edge goes with its start.
    assert modal_page_window_for_rect({"x0": 295.0, "x1": 305.0}, pages) == (0.0, 300.0)


def _paged_figure(page_seconds=300.0):
    return {
        "data": [],
        "layout": {
            "meta": {"x_min": 0.0, "x_max": 1394.0, "y_min": 5.0, "y_max": 100.0, "x_to_seconds": 1.0,
                     "y_to_hz": 1.0, "page_seconds": page_seconds},
            "shapes": [],
        },
    }


def _box(start, end):
    return {
        "label": "Fin whale",
        "annotation_extent": {"type": "time_freq_box", "time_start_sec": start, "time_end_sec": end,
                              "freq_min_hz": 15.0, "freq_max_hz": 30.0},
        "source": "manual",
        "decision": "added",
    }


def test_axis_meta_carries_the_page_length_in_plot_units():
    assert axis_meta_from_figure(_paged_figure())["page_length"] == 300.0
    assert axis_meta_from_figure(_paged_figure(None))["page_length"] is None


def test_box_handles_sit_beside_their_box_on_its_page():
    figure = apply_modal_boxes_to_figure(_paged_figure(), [_box(296.0, 299.0), _box(1000.0, 1004.0)])
    handles = {trace["name"]: trace for trace in figure["data"]}
    for name in (BBOX_DELETE_TRACE_NAME, BBOX_EDIT_TRACE_NAME):
        first, second = handles[name]["x"]
        # Offsets are a fraction of the page, not the whole 23-minute clip.
        assert 0.0 < first < 300.0 and abs(first - 297.5) < 12.0
        assert 900.0 < second < 1200.0 and abs(second - 1002.0) < 12.0
