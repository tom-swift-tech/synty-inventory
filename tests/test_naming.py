from synty_inventory.knowledge import infer
from synty_inventory.naming import parse_name, should_skip, title_from_tokens


def test_parse_police_sign():
    p = parse_name("SM_Prop_Sign_Police_01")
    assert p.prefix == "SM"
    assert p.family == "PROP"
    assert p.kind == "sign"
    assert p.variant == "01"
    assert "Police" in p.subject_tokens


def test_parse_scifi_neon():
    p = parse_name("SM_Sign_Neon_Flat_01")
    assert p.kind == "sign"
    assert "Neon" in p.subject_tokens


def test_skip_collision():
    assert should_skip("Assets/Synty/PolygonCity/Models/Collisions/Foo.fbx", "SM_Prop_Box_01_Convex")
    assert not should_skip("Assets/Synty/PolygonCity/Prefabs/Props/SM_Prop_Sign_Police_01.prefab", "SM_Prop_Sign_Police_01")


def test_title():
    assert title_from_tokens(["Sign", "FireDepartment"]) == "Sign Fire Department"


def test_infer_police_quality_bar():
    rec = infer("SM_Prop_Sign_Police_01")
    assert rec["name"] == "Police Channel Letters"
    assert rec["type"] == "prop/signage"
    assert rec["semantic_role"] == "building_identity"
    assert rec["semantic_detail"] == "police_station"
    assert rec["placement"]["mount"] == "wall"
    assert "police_station" in rec["placement"]["preferred_contexts"]
    assert len(rec["description"]) > 80


def test_infer_barber_quality_bar():
    rec = infer("SM_Prop_Sign_Barber_01")
    assert rec["name"] == "Barber Pole"
    assert rec["placement"]["attachment"] == "side_bracket"
    assert rec["placement"]["preferred_floors"] == [1]
    assert rec["semantic_role"] == "building_identity"
    assert rec["semantic_detail"] == "barber_shop"
