"""Reproducible local CPU and payload benchmark; no user dataset is modified.

Run: python scripts/benchmark_performance.py --repeats 7
These timings exclude network latency and Plotly's browser rendering work.
"""

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dash._utils import to_json
from app.utils import image_processing as ip
from app.callbacks.modal.figure_helpers import apply_modal_boxes_to_figure, patch_modal_boxes
from app.callbacks.common.register_helpers import build_grid
from app.components.spectrogram_card import create_spectrogram_card
from app.services.grid_updates import grid_render_state, incremental_grid


def median_ms(function, repeats):
    function()  # warm imports, allocator and Plotly validators
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        samples.append(1000 * (time.perf_counter() - started))
    return round(statistics.median(samples), 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    repeats = max(1, args.repeats)
    rng = np.random.default_rng(42)
    spec = ip._prepare_cached_spectrogram({
        "psd": rng.normal(-50, 12, (512, 3000)).astype(np.float32),
        "freq": np.linspace(5, 100, 512), "time": np.linspace(0, 300, 3000),
    })
    box = {"label": "Whale", "source": "manual", "annotation_extent": {
        "type": "time_freq_box",
        "time_start_sec": 20, "time_end_sec": 40, "freq_min_hz": 10, "freq_max_hz": 20,
    }}
    figure = apply_modal_boxes_to_figure(ip.create_spectrogram_figure(spec, "default"), [box])
    context = {
        "item_id": "benchmark",
        "layout": {key: figure["layout"][key] for key in (
            "meta", "shapes", "annotations", "xaxis", "yaxis", "editrevision", "uirevision")},
        "data": [{"type": t["type"], "name": t.get("name")} for t in figure["data"]],
    }
    items = [{"item_id": f"clip-{i}", "annotations": {"labels": ["Whale"]}} for i in range(25)]

    def make_grid(page_items):
        return build_grid(
            page_items, "label", "default", "linear", None, None, None, None, 25, {},
            get_item_image_src=lambda *a, **kw: "/item-image/benchmark",
            create_spectrogram_card=create_spectrogram_card,
        )

    before = grid_render_state(items, {})
    items[0]["annotations"]["labels"] = []
    after = grid_render_state(items, {})
    def make_card_update():
        updates = {}
        incremental_grid(
            before, after, lambda: make_grid(items),
            lambda i: make_grid([items[i]]).children[0],
            update_card=lambda column: updates.update({
                json.dumps(column.id, sort_keys=True, separators=(",", ":")): {"children": column.children},
            }),
        )
        return updates
    results = {
        "matrix_shape": list(spec["psd"].shape), "repeats": repeats,
        "contrast_compute_ms": median_ms(lambda: ip._compute_color_limit_summary(spec["psd"]), repeats),
        "contrast_cached_ms": median_ms(lambda: ip._spectrogram_color_summary(spec), repeats),
        "figure_build_ms": median_ms(lambda: ip.create_spectrogram_figure(spec, "default"), repeats),
        "thumbnail_render_ms": median_ms(lambda: ip._generate_image_from_spectrogram_data(spec), repeats),
        "full_figure_json_bytes": len(to_json(figure).encode()),
        "overlay_context_json_bytes": len(to_json(context).encode()),
        "display_meta_json_bytes": len(to_json({"item_id": "benchmark", "layout": {"meta": figure["layout"]["meta"]}}).encode()),
        "box_patch_json_bytes": len(to_json(patch_modal_boxes(context, [dict(box, tag="Repeated")])).encode()),
        "grid_full_ms": median_ms(lambda: make_grid(items), repeats),
        "grid_one_card_ms": median_ms(make_card_update, repeats),
        "grid_full_json_bytes": len(to_json(make_grid(items)).encode()),
        "grid_one_card_json_bytes": len(to_json(make_card_update()).encode()),
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
