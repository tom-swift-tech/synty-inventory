import pytest

from synty_inventory.catalog import build_catalog
from synty_inventory.discover import discover
from synty_inventory.paths import ConfigError, load_config
from synty_inventory.schema import validate_catalog


@pytest.mark.live
def test_scan_polygon_city_if_present():
    try:
        cfg = load_config(require=False)
    except ConfigError:
        pytest.skip("POLYGON_City not on this machine")
    extracted = cfg.get("extracted_root")
    if extracted is None:
        pytest.skip("POLYGON_City not on this machine")
    root = extracted / "POLYGON_City"
    if not root.is_dir():
        pytest.skip("POLYGON_City not on this machine")
    refs = discover(root)
    assert refs and refs[0].pack_id == "POLYGON_City"
    doc = build_catalog(refs[0], include_shared=False)
    errs = validate_catalog(doc)
    assert errs == [], errs
    ids = {a["id"] for a in doc["assets"]}
    assert "SM_Prop_Sign_Police_01" in ids
    assert "SM_Prop_Sign_Barber_01" in ids
    police = next(a for a in doc["assets"] if a["id"] == "SM_Prop_Sign_Police_01")
    assert police["paths"]["prefab"]
    assert police["paths"]["prefab"].replace("\\", "/").endswith(
        "Prefabs/Props/SM_Prop_Sign_Police_01.prefab"
    )
    assert (root / police["paths"]["prefab"]).is_file()
    assert police["semantic_role"] == "building_identity"
    assert police["semantic_detail"] == "police_station"
    assert len(police["description"]) > 80
