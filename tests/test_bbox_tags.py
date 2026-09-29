from app.config import get_repo_root, load_config_file
from app.services.bbox_tags import load_bbox_tag_options


def test_default_bbox_tag_config_loads_fin_whale_options():
    repo_root = get_repo_root()
    config = load_config_file("config/default.yaml")

    tags = load_bbox_tag_options(repo_root, config.get("bounding_box_tags"))

    assert tags["active_set"] == "fin_whale"
    values = [option["value"] for option in tags["options"]]
    assert values == ["20Hz", "30Hz", "40Hz"]


FIN_WHALE = "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
HUMPBACK = "Biophony > Marine mammal > Cetacean > Baleen whale > Humpback whale"


def test_default_fin_whale_tags_apply_only_to_fin_whale_boxes():
    from app.services.bbox_tags import tag_options_for_label

    tags = load_bbox_tag_options(get_repo_root(), load_config_file("config/default.yaml").get("bounding_box_tags"))

    assert [(tag_set["name"], tag_set["label"]) for tag_set in tags["tag_sets"]] == [("fin_whale", FIN_WHALE)]
    values = lambda label: [option["value"] for option in tag_options_for_label(tags["tag_sets"], label)]
    assert values(FIN_WHALE) == ["20Hz", "30Hz", "40Hz"]
    assert values(FIN_WHALE + " > Song") == ["20Hz", "30Hz", "40Hz"]
    assert values("Fin whale") == ["20Hz", "30Hz", "40Hz"]
    assert values(HUMPBACK) == []
    assert values("Biophony > Marine mammal > Cetacean > Baleen whale") == []


def test_tag_sets_per_species_from_a_file(tmp_path):
    from app.services.bbox_tags import get_bbox_tag_options, tag_options_for_label

    tags_file = tmp_path / "tags.yaml"
    tags_file.write_text(
        "tag_sets:\n"
        "  fin_whale:\n"
        "    label: Fin whale\n"
        "    options: [20Hz, 40Hz]\n"
        "  humpback:\n"
        f"    label: {HUMPBACK}\n"
        "    options: [{label: Song unit, value: song_unit}]\n"
        "  old_style:\n"
        "    - {label: Any, value: any}\n"
    )

    tags = load_bbox_tag_options(str(tmp_path), {"options_file": "tags.yaml", "active_set": ["fin_whale", "humpback"]})
    assert tags["active_set"] == "fin_whale"
    assert [tag_set["label"] for tag_set in tags["tag_sets"]] == [FIN_WHALE, HUMPBACK]
    assert [option["value"] for option in tags["options"]] == ["20Hz", "40Hz", "song_unit"]
    assert tag_options_for_label(tags["tag_sets"], HUMPBACK) == [{"label": "Song unit", "value": "song_unit"}]
    assert get_bbox_tag_options({"bounding_box_tags": tags}) == tags["options"]

    # A set in the older list format has no species, so it applies to every box.
    old = load_bbox_tag_options(str(tmp_path), {"options_file": "tags.yaml", "active_set": "old_style"})
    assert old["tag_sets"][0]["label"] is None
    assert tag_options_for_label(old["tag_sets"], HUMPBACK) == [{"label": "Any", "value": "any"}]
