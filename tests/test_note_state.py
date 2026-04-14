from app.services.note_state import stage_label_note_edit


def test_stage_label_note_edit_preserves_existing_labels_and_sets_note():
    data = {
        "items": [
            {
                "item_id": "clip-1",
                "predictions": {"labels": ["Existing > Prediction"]},
                "annotations": {
                    "labels": ["Human > Label"],
                    "notes": "",
                    "pending_save": False,
                },
            }
        ],
        "summary": {"annotated": 1, "verified": 0},
    }

    updated, changed = stage_label_note_edit(data, "clip-1", "Needs a second pass", user_name="tester")

    assert changed is True
    annotations = updated["items"][0]["annotations"]
    assert annotations["labels"] == ["Human > Label"]
    assert annotations["notes"] == "Needs a second pass"
    assert annotations["pending_save"] is True
    assert annotations["annotated_by"] == "tester"


def test_stage_label_note_edit_promotes_visible_labels_when_starting_from_predictions():
    data = {
        "items": [
            {
                "item_id": "clip-2",
                "predictions": {"labels": ["Prediction > Label"]},
                "annotations": {"notes": ""},
            }
        ],
        "summary": {"annotated": 0, "verified": 0},
    }

    updated, changed = stage_label_note_edit(data, "clip-2", "Transient vessel sound")

    assert changed is True
    annotations = updated["items"][0]["annotations"]
    assert annotations["labels"] == ["Prediction > Label"]
    assert annotations["notes"] == "Transient vessel sound"
    assert annotations["pending_save"] is True
    assert updated["summary"]["annotated"] == 1
