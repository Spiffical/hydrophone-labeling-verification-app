import json
from copy import deepcopy

from app.services.annotation_times import (
    AUDIO_START,
    TIME_REFERENCE_KEY,
    legacy_box_time_offset,
    normalize_item,
    normalize_review_json,
)
from app.services.modal_boxes import build_modal_boxes_from_item
from app.utils.data_loading import load_whale_mode
from app.utils.persistence import save_verify_predictions

FIN = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
# The fin whale dashboards: 1 s windows generated from audio.
FIN_CONFIG = {"spectrogram_render": {"source": "audio_generated", "win_dur_s": 1.0, "overlap": 0.9,
                                     "freq_min_hz": 5.0, "freq_max_hz": 100.0}}


def box_decision(start, end, tag="20Hz"):
    return {
        "label": FIN,
        "decision": "accepted",
        "threshold_used": 0.5,
        "annotation_extent": {"type": "time_freq_box", "time_start_sec": start, "time_end_sec": end,
                              "freq_min_hz": 15.0, "freq_max_hz": 30.0},
        "tag": tag,
        "tag_source": "human",
        "tag_scope": "time_freq_box",
    }


def lynn_item():
    """A clip as Lynn's rounds were saved: box times on the old plot axis."""
    return {
        "item_id": "fw-clip-1",
        "audio_start_time": "2025-04-01T04:36:40.300Z",
        "model_outputs": [{"class_hierarchy": FIN, "score": 0.97}],
        "verifications": [
            {"verified_at": "2026-09-01T10:00:00", "verified_by": "Lynn", "verification_round": 1,
             "label_decisions": [box_decision(71.8, 78.7)]},
            {"verified_at": "2026-09-02T10:00:00", "verified_by": "Lynn", "verification_round": 2,
             "label_decisions": [box_decision(71.8, 78.7), box_decision(104.5, 110.8, "30Hz"),
                                 {"label": FIN, "decision": "accepted", "threshold_used": 0.5,
                                  "annotation_extent": {"type": "clip"}}]},
        ],
    }


def test_old_rounds_move_to_clip_time_by_half_the_window():
    assert legacy_box_time_offset(None, FIN_CONFIG) == 0.5
    # Existing spectrogram files keep their axis, so their boxes do not move.
    assert legacy_box_time_offset(None, {"spectrogram_render": {"source": "existing"}}) == 0.0
    assert legacy_box_time_offset(None, None) == 0.0

    item = lynn_item()
    before = deepcopy(item)
    out = normalize_item(item, FIN_CONFIG)
    assert item == before, "the item read from disk is not changed"
    latest = out["verifications"][-1]
    assert latest[TIME_REFERENCE_KEY] == AUDIO_START
    extents = [decision["annotation_extent"] for decision in latest["label_decisions"]]
    assert [(e.get("time_start_sec"), e.get("time_end_sec")) for e in extents] == [
        (72.3, 79.2), (105.0, 111.3), (None, None),
    ]
    assert extents[0]["freq_min_hz"] == 15.0 and latest["label_decisions"][1]["tag"] == "30Hz"
    assert out["verifications"][0]["label_decisions"][0]["annotation_extent"]["time_start_sec"] == 72.3
    # Rounds already in clip time are left alone, so nothing moves twice.
    assert normalize_item(out, FIN_CONFIG) == out


def test_label_files_in_the_older_layout_move_too():
    labels = {"clip-a.mat": {"labels": [FIN], "box_annotations": [
        {"label": FIN, "annotation_extent": {"type": "time_freq_box", "time_start_sec": 1.0, "time_end_sec": 2.0,
                                             "freq_min_hz": 15, "freq_max_hz": 30}}]}}
    out = normalize_review_json(labels, FIN_CONFIG)
    extent = out["clip-a.mat"]["box_annotations"][0]["annotation_extent"]
    assert (extent["time_start_sec"], extent["time_end_sec"]) == (1.5, 2.5)
    assert normalize_review_json(out, FIN_CONFIG) == out


def test_loaded_boxes_stay_on_their_calls_and_saving_leaves_old_rounds_untouched(tmp_path):
    predictions = tmp_path / "predictions.json"
    data = {"schema_version": "2.1", "task_type": "verification", "items": [lynn_item()]}
    predictions.write_text(json.dumps(data))
    on_disk_before = json.loads(predictions.read_text())

    loaded = load_whale_mode({"whale": {"predictions_json": str(predictions)}}, annotation_config=FIN_CONFIG)
    item = loaded["items"][0]
    boxes = build_modal_boxes_from_item(item)
    assert [(b["annotation_extent"]["time_start_sec"], b["tag"]) for b in boxes] == [(72.3, "20Hz"), (105.0, "30Hz")]

    # A new round saved from those boxes is in clip time and says so; the old
    # rounds on disk keep their original values.
    save_verify_predictions(str(predictions), "fw-clip-1", {
        "verified_at": "2026-09-30T10:00:00", "verified_by": "Tester",
        "label_decisions": [dict(box_decision(0, 0), annotation_extent=boxes[0]["annotation_extent"])],
    })
    on_disk = json.loads(predictions.read_text())
    rounds = on_disk["items"][0]["verifications"]
    assert rounds[:2] == on_disk_before["items"][0]["verifications"]
    assert rounds[2][TIME_REFERENCE_KEY] == AUDIO_START
    assert rounds[2]["label_decisions"][0]["annotation_extent"]["time_start_sec"] == 72.3

    # Reading it back does not move the new round again.
    reloaded = load_whale_mode({"whale": {"predictions_json": str(predictions)}}, annotation_config=FIN_CONFIG)
    assert build_modal_boxes_from_item(reloaded["items"][0])[0]["annotation_extent"]["time_start_sec"] == 72.3


def test_a_pinned_window_keeps_old_boxes_in_place_when_the_window_changes():
    # PMO-1312's older rounds were drawn on a 1 s window. Viewing it with a
    # 2 s window later must not move them.
    wider = {"spectrogram_render": dict(FIN_CONFIG["spectrogram_render"], win_dur_s=2.0)}
    assert legacy_box_time_offset(None, wider) == 1.0
    pinned = dict(wider, annotation_times={"legacy_window_s": 1.0})
    assert legacy_box_time_offset(None, pinned) == 0.5
    out = normalize_item(lynn_item(), pinned)
    assert out["verifications"][-1]["label_decisions"][0]["annotation_extent"]["time_start_sec"] == 72.3


def test_the_config_passes_the_pinned_window_through(tmp_path):
    from app.config import _annotation_times_config

    assert _annotation_times_config({"legacy_window_s": 1}) == {"legacy_window_s": 1.0}
    assert _annotation_times_config({"legacy_window_s": "bad"}) == {"legacy_window_s": None}
    assert _annotation_times_config(None) == {"legacy_window_s": None}
