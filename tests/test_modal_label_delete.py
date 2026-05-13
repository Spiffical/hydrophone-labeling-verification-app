from app.callbacks.modal.label_callbacks import _resolve_modal_delete_active_item


def test_modal_delete_uses_live_modal_item_when_page_store_is_stale():
    items = [
        {
            "item_id": "clip-1",
            "annotations": {"labels": ["Existing label"]},
        }
    ]
    modal_item = {
        "item_id": "clip-1",
        "annotations": {
            "labels": ["Existing label", "Modal-only label"],
            "pending_save": True,
        },
    }

    active_item = _resolve_modal_delete_active_item(items, "clip-1", modal_item)

    assert active_item["annotations"]["labels"] == ["Existing label", "Modal-only label"]
    assert items[0]["annotations"]["labels"] == ["Existing label", "Modal-only label"]
    assert items[0] is not modal_item
