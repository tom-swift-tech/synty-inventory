"""sources/mech.py: prefab parsing against a small synthetic fixture (not
the real 3 MB Unity files -- see tests/fixtures/mech/), attachment-stem
slot resolution against the naming convention table, and the
apply_mech_catalog overlay end to end."""

from pathlib import Path

from synty_inventory.sources import mech

FIXTURE = Path(__file__).parent / "fixtures" / "mech"


def test_discover_vehicle_prefabs_and_attachment_fbx():
    prefabs = mech.discover_vehicle_prefabs(FIXTURE)
    assert [p.name for p in prefabs] == ["SM_Veh_Mech_01.prefab", "SM_Veh_Mech_02.prefab"]
    attach = mech.discover_attachment_fbx(FIXTURE)
    assert {p.name for p in attach} == {
        "SM_Mech_01_Attach_Saddlebag_01.fbx",
        "SM_Mech_Head_01_Armor_Helmet_01.fbx",
        "SM_Mech_Leg_01_Armor_Kneepad_03.fbx",
        "SM_Mech_Unknown_01_Widget_01.fbx",
    }


def test_parse_prefab_reads_active_flag_and_root_bone():
    rows = mech.parse_prefab(FIXTURE / "Prefabs" / "Vehicles" / "SM_Veh_Mech_01.prefab")
    by_node = {r["node"]: r for r in rows}
    assert by_node["geo_l_ankle"]["active"] is True
    assert by_node["geo_l_ankle"]["root_bone"] == "Ankle_L"
    assert by_node["geo_r_chest_attach_weapon_01"]["active"] is False
    assert by_node["geo_r_chest_attach_weapon_01"]["root_bone"] == "Spine_01"
    assert by_node["geo_c_cockpit_door_01"]["root_bone"] == "CockpitDoor"


def test_build_body_mech_aggregates_slots_and_variants():
    prefabs = mech.discover_vehicle_prefabs(FIXTURE)
    guid_fbx = mech._read_guid_fbx_map(FIXTURE)
    assert guid_fbx == {"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": "SM_Veh_Mech_01.fbx"}
    body = mech.build_body_mech(prefabs, guid_fbx)
    assert body["_master_fbx"] == ["SM_Veh_Mech_01.fbx"]
    assert sorted(body["skeleton"]) == ["Ankle_L", "CockpitDoor", "Spine_01"]
    by_key = {(s["region"], s["side"], s["bone"]): s["geo_nodes"] for s in body["slots"]}
    assert by_key[("ankle", "l", "Ankle_L")] == ["geo_l_ankle"]
    assert by_key[("chest", "r", "Spine_01")] == ["geo_r_chest_attach_weapon_01"]
    assert by_key[("cockpit", "c", "CockpitDoor")] == ["geo_c_cockpit_door_01"]
    # active-flag toggle differs between the two synthetic prefabs
    assert body["variants"]["SM_Veh_Mech_01"] == ["geo_c_cockpit_door_01", "geo_l_ankle"]
    assert body["variants"]["SM_Veh_Mech_02"] == ["geo_r_chest_attach_weapon_01"]


def test_build_body_mech_empty_input():
    assert mech.build_body_mech([]) is None


# --- attachment-stem slot resolution ----------------------------------------------


def test_resolve_attachment_slot_bilateral_defaults_to_left_with_real_bone():
    # confirmed via the body's own geo_lowerleg_knee_armor_* nodes (region
    # "lowerleg", not a separate "knee" region)
    assert mech.resolve_attachment_slot("SM_Mech_Leg_01_Armor_Kneepad_03") == ("lowerleg", "l", "LowerLeg_L")
    assert mech.resolve_attachment_slot("SM_Mech_Arm_01_Weapon_Forearm_02") == ("elbow", "l", "Elbow_L")
    assert mech.resolve_attachment_slot("SM_Mech_Foot_01_Armor_Toes_01") == ("ball", "l", "Ball_L")
    assert mech.resolve_attachment_slot("SM_Mech_Foot_01_Armor_Heel_01") == ("ankle", "l", "AnkleReverse_L")


def test_resolve_attachment_slot_centre_bones_use_side_c():
    assert mech.resolve_attachment_slot("SM_Mech_Head_01_Armor_Helmet_01") == ("head", "c", "Head")
    assert mech.resolve_attachment_slot("SM_Mech_Cockpit_01_Monitor_01") == ("cockpit", "c", "CockpitDoor")
    assert mech.resolve_attachment_slot("SM_Mech_Hips_01_Armor_Belt_02") == ("hips", "c", "Hips")


def test_resolve_attachment_slot_slot_token_wins_over_a_same_bone_detail_token():
    # "Neck_..._Collar" must resolve to the Neck slot, not the generic
    # torso "collar" (Spine_01) detail token further right in the stem.
    assert mech.resolve_attachment_slot("SM_Mech_Neck_01_Armor_Collar_02") == ("neck", "c", "Neck")


def test_resolve_attachment_slot_no_slot_falls_through_to_a_detail_token():
    # "01_Attach_Saddlebag": no named slot, "attach" is the first
    # recognised token.
    assert mech.resolve_attachment_slot("SM_Mech_01_Attach_Saddlebag_01") == ("attach", "c", "Spine_01")


def test_resolve_attachment_slot_unresolvable_stem_returns_none():
    assert mech.resolve_attachment_slot("SM_Mech_Unknown_01_Widget_01") is None
    assert mech.resolve_attachment_slot("SM_Prop_Barrel_01") is None


def test_resolve_attachment_slot_all_real_fbx_stems_from_the_pack():
    """Ground truth: every one of the 104 real MechAttachments FBX stems
    resolves (mined 2026-08-19, see sources/mech.py docstring). This list
    is the mined stem set, not a filesystem read -- it stays valid even
    when the extracted pack isn't on the test machine."""
    stems = [
        "SM_Mech_01_Attach_Saddlebag_01", "SM_Mech_01_Attach_Saddlebag_02",
        "SM_Mech_Ankle_01_Frame_01",
        "SM_Mech_Arm_01_Armor_Forearm_01", "SM_Mech_Arm_01_Armor_Shoulder_01",
        "SM_Mech_Arm_01_Weapon_Forearm_06_Empty",
        "SM_Mech_Back_01_Attach_Jetpack_01", "SM_Mech_Back_01_Attach_Radio_01", "SM_Mech_Back_01_Battery_01",
        "SM_Mech_Chest_01_Armor_Collar_01", "SM_Mech_Chest_01_Weapon_Collar_02_Empty",
        "SM_Mech_Cockpit_01_Armor_Door_01", "SM_Mech_Cockpit_01_Monitor_01", "SM_Mech_Cockpit_01_Shell_01",
        "SM_Mech_Exhaust_01_Frame_01",
        "SM_Mech_Foot_01_Armor_Heel_01", "SM_Mech_Foot_01_Armor_Toes_01",
        "SM_Mech_Forearm_01_Frame_01",
        "SM_Mech_Hand_01_Armor_Wrist_01", "SM_Mech_Hand_01_Frame_01",
        "SM_Mech_Head_01_Armor_Helmet_01",
        "SM_Mech_Hips_01_Armor_01", "SM_Mech_Hips_01_Armor_Belt_01", "SM_Mech_Hips_01_Frame_01",
        "SM_Mech_Leg_01_Armor_Kneepad_01", "SM_Mech_Leg_01_Armor_Shinpad_01",
        "SM_Mech_Leg_01_Armor_Thigh_01", "SM_Mech_Leg_01_Armor_Uppershin_01",
        "SM_Mech_LowerLeg_01_Frame_01",
        "SM_Mech_Neck_01_Armor_Collar_01", "SM_Mech_Neck_01_Frame_01",
        "SM_Mech_Shoulder_01_Frame_01", "SM_Mech_Thigh_01_Frame_01",
    ]
    unresolved = [s for s in stems if mech.resolve_attachment_slot(s) is None]
    assert unresolved == []


# --- apply_mech_catalog overlay ----------------------------------------------------


def _catalog(extracted_root: Path) -> dict:
    return {
        "pack_id": "POLYGON_Mech",
        "source": {"extracted": str(extracted_root)},
        "assets": [
            {"id": "SM_Veh_Mech_01", "part": {}},
            {"id": "SM_Veh_Mech_02", "part": {}},
            {"id": "SM_Mech_Leg_01_Armor_Kneepad_03", "part": {}},
            {"id": "SM_Mech_Unknown_01_Widget_01", "part": {}},
            {"id": "SM_Prop_Barrel_01", "part": {}},  # not a mech asset, must stay untouched
        ],
    }


def test_apply_mech_catalog_fills_body_and_attachment_fields():
    cache: dict = {}
    stats: dict = {}
    catalog = _catalog(FIXTURE)
    mech.apply_mech_catalog(catalog, cache, stats)
    by_id = {a["id"]: a for a in catalog["assets"]}

    body = by_id["SM_Veh_Mech_01"]
    assert sorted(body["mech"]["skeleton"]) == ["Ankle_L", "CockpitDoor", "Spine_01"]
    assert body["provenance"]["mech"] == "measured"
    assert by_id["SM_Veh_Mech_02"]["mech"]["variants"]["SM_Veh_Mech_02"] == ["geo_r_chest_attach_weapon_01"]

    kneepad = by_id["SM_Mech_Leg_01_Armor_Kneepad_03"]
    assert kneepad["part"]["slot"] == {"region": "lowerleg", "side": "l"}
    assert kneepad["part"]["attach_bone"] == "LowerLeg_L"

    unknown = by_id["SM_Mech_Unknown_01_Widget_01"]
    assert unknown["part"]["slot"] is None
    assert unknown["part"]["attach_bone"] is None

    assert "mech" not in by_id["SM_Prop_Barrel_01"]
    assert by_id["SM_Prop_Barrel_01"]["part"] == {}  # never touched: no matching fbx/prefab

    assert stats["mech_body_assets"] == 2
    assert stats["mech_attach_resolved"] == 1
    assert stats["mech_attach_unresolved"] == 1
    assert stats["mech_master_fbx_mismatch"] == 0


def test_apply_mech_catalog_caches_the_body_parse(monkeypatch):
    cache: dict = {}
    stats: dict = {}
    catalog = _catalog(FIXTURE)
    mech.apply_mech_catalog(catalog, cache, stats)
    assert any(k.startswith("mech:POLYGON_Mech:body") for k in cache)

    calls = []
    real = mech.parse_prefab

    def spy(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(mech, "parse_prefab", spy)
    catalog2 = _catalog(FIXTURE)
    mech.apply_mech_catalog(catalog2, cache, dict(stats))
    assert calls == []  # cache hit: parse_prefab not called again


def test_apply_mech_catalog_no_op_without_extracted_source():
    catalog = {"pack_id": "POLYGON_City", "source": {}, "assets": [{"id": "SM_Bld_Door_01", "part": {}}]}
    cache: dict = {}
    stats: dict = {}
    mech.apply_mech_catalog(catalog, cache, stats)
    assert catalog["assets"][0]["part"] == {}
    assert "mech" not in catalog["assets"][0]
    assert stats == {}


def test_apply_mech_catalog_no_op_when_no_mech_prefabs(tmp_path: Path):
    (tmp_path / "Prefabs" / "Vehicles").mkdir(parents=True)
    (tmp_path / "Prefabs" / "Vehicles" / "SM_Veh_Car_01.prefab").write_text("x", encoding="utf-8")
    catalog = {"pack_id": "POLYGON_City", "source": {"extracted": str(tmp_path)}, "assets": [{"id": "SM_Veh_Car_01", "part": {}}]}
    cache: dict = {}
    stats: dict = {}
    mech.apply_mech_catalog(catalog, cache, stats)
    assert "mech" not in catalog["assets"][0]
    assert stats == {}
