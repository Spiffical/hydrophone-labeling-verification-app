from app.config import get_repo_root, load_config_file
from app.services.bbox_tags import load_bbox_tag_options


def test_default_bbox_tag_config_loads_fin_whale_options():
    repo_root = get_repo_root()
    config = load_config_file("config/default.yaml")

    tags = load_bbox_tag_options(repo_root, config.get("bounding_box_tags"))

    assert tags["active_set"] == "fin_whale"
    assert [option["value"] for option in tags["options"]] == ["20Hz", "30Hz", "40Hz"]
