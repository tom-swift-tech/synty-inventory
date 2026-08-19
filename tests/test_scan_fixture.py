from pathlib import Path

from synty_inventory.catalog import build_catalog
from synty_inventory.discover import discover
from synty_inventory.scan import scan_extracted, scan_from_package_listing
from synty_inventory.schema import validate_catalog

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "FakePack"


def test_scan_fixture_pack():
    refs = discover(FIXTURE)
    assert len(refs) == 1
    assert refs[0].pack_id == "FakePack"
    assert refs[0].extracted_path == FIXTURE

    doc = build_catalog(refs[0], include_shared=False)
    errs = validate_catalog(doc)
    assert errs == [], errs
    ids = {a["id"] for a in doc["assets"]}
    assert "SM_Prop_Sign_Police_01" in ids
    assert "SM_Prop_Sign_Barber_01" in ids
    assert "SM_Bld_Shop_01" in ids

    police = next(a for a in doc["assets"] if a["id"] == "SM_Prop_Sign_Police_01")
    prefab = (police["paths"]["prefab"] or "").replace("\\", "/")
    assert prefab.endswith("Prefabs/Props/SM_Prop_Sign_Police_01.prefab")
    assert (FIXTURE / police["paths"]["prefab"]).is_file()
    assert police["semantic_role"] == "building_identity"
    assert police["semantic_detail"] == "police_station"
    assert len(police["description"]) > 80
    assert police["guid"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_scan_prefers_pack_over_shared_kit():
    pack_only = {a.id: a for a in scan_extracted(FIXTURE, include_shared=False)}
    assert "SM_Prop_GenericOnly_01" not in pack_only
    twin = pack_only["SM_Prop_SharedTwin_01"]
    assert twin.shared is False
    assert twin.kit == "FakeCity"
    assert "PolygonGeneric" not in (twin.prefab.rel if twin.prefab else "")

    with_shared = {a.id: a for a in scan_extracted(FIXTURE, include_shared=True)}
    assert "SM_Prop_GenericOnly_01" in with_shared
    assert with_shared["SM_Prop_GenericOnly_01"].shared is True
    still = with_shared["SM_Prop_SharedTwin_01"]
    assert still.shared is False
    assert still.kit == "FakeCity"


def test_package_preview_path_includes_pack():
    rows = [
        {
            "pathname": "Assets/Synty/FakeCity/Prefabs/SM_Prop_Sign_Police_01.prefab",
            "guid": "aa",
            "has_preview": True,
        }
    ]
    assets = scan_from_package_listing(rows, pack_id="FakePack")
    assert assets[0].thumbnail == "previews/FakePack/SM_Prop_Sign_Police_01.png"
