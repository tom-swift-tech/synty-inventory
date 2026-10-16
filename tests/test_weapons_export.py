"""Weapon directory W4: ``weapons export`` and ``validate --snapshot`` (docs/weapon_directory.md section 3.10).

Covers AC23 to AC26, the export half of AC33 and AC34, and the B-1 refusal. The measured world is built through the
real pipeline from the generated GLBs of ``make_glbs.py`` (sword Y-long, guns Z-long, a three-node shared bow GLB).
All numeric expectations are literals worked out from those meshes, not values read from the code under test.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_helpers", Path(__file__).parent / "fixtures" / "weapons" / "review_helpers.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
wfx = H.wfx

from synty_inventory.weapons import export as X  # noqa: E402
from synty_inventory.weapons.directory import read_json  # noqa: E402

TWO_PACKS = "FAKE_Fantasy,FAKE_Modern"
BAKED = {"bounds", "tip", "butt", "muzzle", "grip", "support", "frame"}  # the geometry fields an item bake may change


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("export")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(X, "_repo_root", lambda: None)  # the pytest tmp dir sits inside this checkout
    cat = H.make_catalogs(tmp, shared=True)
    root = H.make_threejs(tmp, cat)
    directory, excluded = H.build_and_write(cat, threejs_v2_dir=root)
    from synty_inventory.weapons.directory import write_directory

    H.attach_icons(directory, cat / "weapons", [H.SWORD_02, H.SWORD_01, "FAKE_Modern/SM_Wep_Pistol_01"])
    write_directory(cat, directory, excluded)
    out_dir = tmp / "game_repo"
    out_dir.mkdir()
    yield SimpleNamespace(
        tmp=tmp, cat=cat, directory=directory, by_id=wfx.records_by_id(directory), out_dir=out_dir,
        cfg=H.write_config(tmp, cat), public_cfg=H.write_config(tmp, cat, ["weapons_public_icons_approved: true"], "pub.yaml"),
        counter=iter(range(1, 10**6)),
    )
    mp.undo()


def export(world, capsys, *flags, cfg=None, game="district7", name=None):
    """Run ``weapons export``; returns (exit code, stdout JSON, output path)."""
    out = world.out_dir / (name or f"snap_{next(world.counter)}.json")
    code, res = H.run(cfg or world.cfg, capsys, ["weapons", "export", "--game", game, *flags, "--out", str(out)])
    return code, res, out


def load(out: Path) -> dict:
    return json.loads(out.read_text(encoding="utf-8"))


def put(path: Path, doc, indent: int = 1) -> None:
    """Write ``doc`` as JSON with LF endings (``write_text`` would turn them into CRLF on Windows)."""
    path.write_bytes((json.dumps(doc, sort_keys=True, indent=indent, ensure_ascii=False) + "\n").encode("utf-8"))


def by_id(doc) -> dict:
    return {w["id"]: w for w in doc["weapons"]}


# --- AC23 ---------------------------------------------------------------------------------------------------

def test_ac23_two_pack_filter_writes_only_those_packs_whole_weapons_sorted(world, capsys):
    code, res, out = export(world, capsys, "--packs", TWO_PACKS)
    assert code == 0, res
    doc = load(out)
    assert list(doc) == sorted(["schema_version", "generated_from", "weapons"])  # exactly these three keys
    want = sorted(w["id"] for w in world.directory["weapons"]
                  if w["pack"] in ("FAKE_Fantasy", "FAKE_Modern") and w["role"] == "whole")
    assert [w["id"] for w in doc["weapons"]] == want and len(want) >= 20
    assert {w["pack"] for w in doc["weapons"]} == {"FAKE_Fantasy", "FAKE_Modern"}
    assert {w["role"] for w in doc["weapons"]} == {"whole"}
    assert doc["schema_version"] == 1
    assert res["weapons"] == len(want)


def test_ac23_roles_all_includes_parts_ammo_carriers_and_emplaced(world, capsys):
    _, _, out = export(world, capsys, "--packs", "FAKE_Modern", "--roles", "all")
    roles = {w["role"] for w in load(out)["weapons"]}
    assert roles == {"whole", "part", "ammo", "carrier", "emplaced"}
    _, _, out = export(world, capsys, "--packs", "FAKE_Modern", "--roles", "part,ammo")
    doc = load(out)
    assert {w["role"] for w in doc["weapons"]} == {"part", "ammo"}
    assert doc["generated_from"]["filter"]["roles"] == ["ammo", "part"]


def test_ac23_generated_from_is_copied_from_the_directory_and_the_pack_catalogs(world, capsys):
    _, _, out = export(world, capsys, "--packs", TWO_PACKS, "--game", "tiny_game") if False else \
        export(world, capsys, "--packs", TWO_PACKS)
    gf = load(out)["generated_from"]
    d = world.directory
    assert gf["tool"].startswith("synty-inventory ") and re.fullmatch(r"synty-inventory \d+\.\d+\.\d+", gf["tool"])
    assert gf["weapon_version"] == 1 and gf["geometry_version"] == 3
    assert gf["rules_digest"] == d["rules_digest"] and gf["overrides_digest"] == d["overrides_digest"]
    assert re.fullmatch(r"[0-9a-f]{16}", gf["rules_digest"]) and re.fullmatch(r"[0-9a-f]{16}", gf["overrides_digest"])
    assert gf["packs"] == [
        {"pack": "FAKE_Fantasy", "scanned_at": "2026-01-01T00:00:00+00:00", "asset_count": 60},
        {"pack": "FAKE_Modern", "scanned_at": "2026-01-01T00:00:00+00:00", "asset_count": next(
            p["asset_count"] for p in d["packs"] if p["pack"] == "FAKE_Modern")},
    ]
    assert gf["filter"] == {"game": "district7", "roles": ["whole"], "engines": ["all"], "frame": "item"}


def test_ac23_two_runs_with_identical_inputs_are_byte_identical(world, capsys):
    _, _, a = export(world, capsys, "--packs", TWO_PACKS)
    _, _, b = export(world, capsys, "--packs", TWO_PACKS)
    assert a != b and a.read_bytes() == b.read_bytes()
    raw = a.read_bytes()
    assert raw.endswith(b"}\n") and b"\r" not in raw
    assert raw.decode("utf-8") == json.dumps(json.loads(raw), sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    assert raw.decode("utf-8").startswith('{\n "generated_from": {')  # 1-space indent, sorted keys


def test_ac23_no_drive_letter_backslash_path_or_hostname_anywhere(world, capsys):
    _, _, out = export(world, capsys, "--packs", "FAKE_Fantasy,FAKE_Modern,FAKE_Review,FAKE_Shared", "--roles", "all")
    doc = load(out)
    strings: list[str] = []

    def walk(o):
        if isinstance(o, str):
            strings.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                strings.append(k)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(doc)
    assert len(strings) > 1000
    assert not [s for s in strings if re.search(r"[A-Za-z]:[\\/]", s)]
    assert not [s for s in strings if "\\" in s]
    assert not [s for s in strings if s.startswith(("/", "~"))]
    host = socket.gethostname().lower()
    if len(host) >= 4:
        assert host not in out.read_text(encoding="utf-8").lower()
    # a clock would show up as the run date; the only timestamps are the catalogs' own
    stamps = {s for s in strings if re.match(r"\d{4}-\d{2}-\d{2}T", s)}
    assert stamps == {"2026-01-01T00:00:00+00:00"}


def test_ac23_ids_file_exports_exactly_those_ids_and_an_unknown_id_exits_2(world, capsys):
    ids = world.tmp / "ids.txt"
    ids.write_text(f"# a game's list\n{H.SWORD_02}\n\n{H.SWORD_01}\nFAKE_Modern/SM_Wep_Pistol_01\n", encoding="utf-8")
    code, res, out = export(world, capsys, "--ids-file", str(ids))
    assert code == 0, res
    doc = load(out)
    assert [w["id"] for w in doc["weapons"]] == sorted([H.SWORD_02, H.SWORD_01, "FAKE_Modern/SM_Wep_Pistol_01"])
    assert [p["pack"] for p in doc["generated_from"]["packs"]] == ["FAKE_Fantasy", "FAKE_Modern"]
    ids.write_text(f"{H.SWORD_02}\nFAKE_Modern/SM_Wep_Nope_99\nFAKE_Fantasy/SM_Wep_Nada_01\n", encoding="utf-8")
    code, res, out = export(world, capsys, "--ids-file", str(ids))
    assert code == 2 and res["missing"] == ["FAKE_Fantasy/SM_Wep_Nada_01", "FAKE_Modern/SM_Wep_Nope_99"]
    assert not out.exists()  # the snapshot must not silently shrink
    ids.write_text(json.dumps([H.SWORD_02]), encoding="utf-8")
    assert load(export(world, capsys, "--ids-file", str(ids))[2])["weapons"][0]["id"] == H.SWORD_02


def test_an_unknown_pack_or_role_exits_2_and_writes_nothing(world, capsys):
    code, res, out = export(world, capsys, "--packs", "FAKE_Modern,NO_SUCH_PACK")
    assert code == 2 and res["unknown"] == ["NO_SUCH_PACK"] and not out.exists()
    code, res, out = export(world, capsys, "--packs", "FAKE_Modern", "--roles", "whole,gizmo")
    assert code == 2 and not out.exists()


# --- AC24 ---------------------------------------------------------------------------------------------------

def test_ac24_the_default_export_is_in_the_item_frame_with_forward_on_plus_z(world, capsys):
    code, res, out = export(world, capsys, "--packs", "FAKE_Fantasy")
    assert code == 0, res
    doc = load(out)
    assert doc["generated_from"]["filter"]["frame"] == "item"
    sword = by_id(doc)[H.SWORD_02]
    g = sword["geometry"]
    assert g["frame"] == "item"
    # the Y-long fixture sword: butt at y -0.15, tip at y +0.85, item_basis maps asset y to item z
    assert g["item_basis"] == [[0, 0, 1], [1, 0, 0], [0, 1, 0]]
    assert g["tip"][2] > g["butt"][2]
    assert g["tip"] == [0.0, 0.0, 0.85] and g["butt"] == [0.0, 0.0, -0.15]
    assert abs(g["tip"][0]) < 1e-3 and abs(g["tip"][1]) < 1e-3 and abs(g["butt"][0]) < 1e-3 and abs(g["butt"][1]) < 1e-3
    assert g["bounds"]["min"] == [-0.025, -0.1, -0.15] and g["bounds"]["max"] == [0.025, 0.1, 0.85]
    assert g["bounds"]["size"] == [0.05, 0.2, 1.0]
    assert g["grip"] == [0.0, 0.0, -0.01]
    assert g["axes"] == {"forward": "+y", "up": "+x", "forward_source": "pivot", "up_source": "width_axis"}  # kept
    assert g["length_m"] == 1.0 and g["long_axis"] == "y"  # mesh facts, not coordinates: unchanged


def test_ac24_frame_asset_keeps_the_asset_space_with_the_long_extent_on_y(world, capsys):
    code, res, out = export(world, capsys, "--packs", "FAKE_Fantasy", "--frame", "asset")
    assert code == 0, res
    doc = load(out)
    assert doc["generated_from"]["filter"]["frame"] == "asset"
    g = by_id(doc)[H.SWORD_02]["geometry"]
    assert g["frame"] == "asset"
    assert g["tip"] == [0.0, 0.85, 0.0] and g["butt"] == [0.0, -0.15, 0.0]
    assert g["bounds"]["size"] == [0.2, 1.0, 0.05]
    assert g["bounds"]["size"][1] > 4 * g["bounds"]["size"][0]  # the long extent is on y
    assert g["item_basis"] == [[0, 0, 1], [1, 0, 0], [0, 1, 0]]  # kept so a consumer can rotate the mesh itself
    # asset frame is the directory's own geometry, record for record
    for w in doc["weapons"]:
        assert w["geometry"] == world.by_id[w["id"]]["geometry"]
        assert w["geometry"] is None or w["geometry"]["frame"] == "asset"


def test_ac24_the_two_frames_differ_only_in_the_baked_geometry_fields_and_the_frame_values(world, capsys):
    _, _, item_path = export(world, capsys, "--packs", "FAKE_Fantasy,FAKE_Modern,FAKE_Shared", "--roles", "all")
    _, _, asset_path = export(world, capsys, "--packs", "FAKE_Fantasy,FAKE_Modern,FAKE_Shared", "--roles", "all",
                              "--frame", "asset")
    item, asset = load(item_path), load(asset_path)
    ga, gb = copy.deepcopy(item["generated_from"]), copy.deepcopy(asset["generated_from"])
    assert (ga["filter"].pop("frame"), gb["filter"].pop("frame")) == ("item", "asset")
    assert ga == gb  # nothing else in generated_from moves
    ia, ib = by_id(item), by_id(asset)
    assert sorted(ia) == sorted(ib) and len(ia) > 60
    differing: set[str] = set()
    for rid in ia:
        a, b = copy.deepcopy(ia[rid]), copy.deepcopy(ib[rid])
        ga_, gb_ = a.pop("geometry"), b.pop("geometry")
        assert a == b, rid  # every non-geometry field is identical
        if ga_ is None:
            assert gb_ is None
            continue
        assert (ga_.pop("frame"), gb_.pop("frame")) == ("item", "asset")
        differing |= {k for k in ga_ if ga_[k] != gb_[k]}
        assert {k for k in ga_ if ga_[k] != gb_[k]} <= BAKED, rid
        assert {k for k in ga_ if k not in BAKED} == {k for k in gb_ if k not in BAKED}
        for k in ga_.keys() - BAKED:
            assert ga_[k] == gb_[k], (rid, k)  # axes, item_basis, node_offset, length, radii, sources, triangles
    assert differing == BAKED - {"frame"}  # every baked field was exercised by some record
    sword = {k for k in ia[H.SWORD_02]["geometry"] if ia[H.SWORD_02]["geometry"][k] != ib[H.SWORD_02]["geometry"][k]}
    assert sword == {"frame", "bounds", "tip", "butt", "grip"}  # a melee weapon: no muzzle, no support


def test_ac24_every_measured_record_points_forward_along_plus_z_in_the_item_frame(world, capsys):
    _, _, out = export(world, capsys, "--packs", "FAKE_Fantasy,FAKE_Modern,FAKE_SciFi,FAKE_Generic,FAKE_Review",
                       "--roles", "all")
    checked_tip = checked_muzzle = 0
    for w in load(out)["weapons"]:
        g = w["geometry"]
        if g is None:
            continue
        assert g["frame"] == "item" and all(lo <= hi for lo, hi in zip(g["bounds"]["min"], g["bounds"]["max"])), w["id"]
        if g["tip"] is not None:
            assert g["tip"][2] > g["butt"][2], w["id"]
            checked_tip += 1
        if g["muzzle"] is not None:
            assert g["muzzle"][2] > g["butt"][2], w["id"]
            checked_muzzle += 1
    assert checked_tip > 20 and checked_muzzle > 10


def test_ac24_a_z_long_gun_is_already_in_the_item_frame(world, capsys):
    rifle = next(w for w in world.directory["weapons"]
                 if w["archetype"] == "rifle" and w["geometry"] and w["pack"] == "FAKE_Modern"
                 and w["id"] != H.ROTATED_GUN)
    _, _, out = export(world, capsys, "--packs", "FAKE_Modern")
    g = by_id(load(out))[rifle["id"]]["geometry"]
    assert g["item_basis"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert g["muzzle"] == [0.0, 0.055, 0.65]  # literal from the gun mesh (make_glbs LABELS)
    assert g["muzzle"] == world.by_id[rifle["id"]]["geometry"]["muzzle"]


def test_ac24_a_y_long_gun_has_its_muzzle_and_support_baked_onto_plus_z(world, capsys):
    """The rifle mesh with y and z swapped: asset-frame points on y, item-frame points as for the Z-long gun."""
    _, _, item = export(world, capsys, "--packs", "FAKE_Modern")
    _, _, asset = export(world, capsys, "--packs", "FAKE_Modern", "--frame", "asset")
    gi, ga = by_id(load(item))[H.ROTATED_GUN]["geometry"], by_id(load(asset))[H.ROTATED_GUN]["geometry"]
    assert ga["axes"]["forward"] == "+y" and ga["axes"]["up"] == "+z"
    assert ga["item_basis"] == gi["item_basis"] == [[-1, 0, 0], [0, 0, 1], [0, 1, 0]]
    assert ga["muzzle"] == [0.0, 0.65, 0.055]  # long extent on y
    assert gi["muzzle"] == [0.0, 0.055, 0.65]  # baked: forward on +z, the Z-long gun's own value
    assert gi["support"] is not None and ga["support"] is not None
    assert gi["support"][2] == ga["support"][1] == 0.308  # the support point at 0.62 of the length, now on z
    assert gi["bounds"]["size"] == [0.04, 0.1, 0.9] and ga["bounds"]["size"] == [0.04, 0.9, 0.1]
    assert gi["butt"][2] == -0.25 and gi["tip"] is None and ga["tip"] is None


# --- AC34 (export half) -------------------------------------------------------------------------------------

def test_ac34_the_item_frame_leaves_node_offset_byte_equal_to_the_asset_frame(world, capsys):
    _, _, item = export(world, capsys, "--packs", "FAKE_Shared")
    _, _, asset = export(world, capsys, "--packs", "FAKE_Shared", "--frame", "asset")
    gi, ga = by_id(load(item))[H.SHARED_BOW]["geometry"], by_id(load(asset))[H.SHARED_BOW]["geometry"]
    assert gi["node_offset"] == ga["node_offset"] == [2.0, 0.3, 0.5]
    assert json.dumps(gi["node_offset"]) == json.dumps(ga["node_offset"])
    assert gi["item_basis"] == ga["item_basis"] == [[0, 0, -1], [0, 1, 0], [1, 0, 0]]  # a real rotation, not identity
    assert ga["bounds"]["min"] == [1.99, -0.5, 0.49] and ga["bounds"]["max"] == [2.16, 1.1, 0.51]
    # item = (-z, y, x): rotated about the scene origin, no translation, node_offset untouched
    assert gi["bounds"]["min"] == [-0.51, -0.5, 1.99] and gi["bounds"]["max"] == [-0.49, 1.1, 2.16]
    assert gi["bounds"]["size"] == [0.02, 1.6, 0.17]
    assert gi["grip"] == [-0.5, 0.3, 2.075] and ga["grip"] == [2.075, 0.3, 0.5]


# --- AC25 / B-1 ---------------------------------------------------------------------------------------------

PUBLIC_KEYS = {"id", "kind", "role", "archetype", "genre", "family", "hints", "geometry", "visuals"}


@pytest.mark.parametrize("config_line", [None, "weapons_public_icons_approved: false", 'weapons_public_icons_approved: "true"',
                                         "weapons_public_icons_approved: 1"])
def test_ac25_public_without_the_approval_flag_exits_3_and_writes_nothing(world, capsys, tmp_path, config_line):
    cfg = H.write_config(tmp_path, world.cat, [config_line] if config_line else None)
    before = sorted(p.name for p in world.out_dir.iterdir())
    icons = tmp_path / "icons_out"
    code, res, out = export(world, capsys, "--packs", "FAKE_Fantasy", "--profile", "public", "--icons-dir", str(icons),
                            cfg=cfg)
    assert code == 3 and res["ok"] is False and "weapons_public_icons_approved" in res["error"]
    assert not out.exists() and not icons.exists()
    assert sorted(p.name for p in world.out_dir.iterdir()) == before


def test_ac25_public_with_the_flag_has_only_the_public_keys_and_no_files(world, capsys):
    code, res, out = export(world, capsys, "--packs", "FAKE_Fantasy,FAKE_Modern", "--profile", "public",
                            cfg=world.public_cfg)
    assert code == 0, res
    doc = load(out)
    assert doc["weapons"] and list(doc) == sorted(["schema_version", "generated_from", "weapons"])
    for w in doc["weapons"]:
        assert set(w) == PUBLIC_KEYS, w["id"]
        assert set(w["geometry"]) == {"length_m"}
        assert set(w["visuals"]) == {"icon", "thumb"}
    raw = out.read_text(encoding="utf-8")
    body = json.dumps(doc["weapons"])
    for leaked in ('"files"', '"bounds"', '"tip"', '"butt"', '"muzzle"', '"grip"', '"support"', '"item_basis"',
                   '"glb', '"unity_', '"node_offset"', '"pack"', '"asset_id"', '"review"', '"provenance"'):
        assert leaked not in body, leaked
    assert "glb" not in raw and "unity" not in raw
    sword = by_id(doc)[H.SWORD_02]
    assert sword["geometry"] == {"length_m": 1.0} and sword["archetype"] == "sword"
    assert sword["hints"] == world.by_id[H.SWORD_02]["hints"]
    assert X.validate_snapshot(out) == []


def test_ac25_the_private_profile_needs_no_approval(world, capsys):
    assert export(world, capsys, "--packs", "FAKE_Fantasy", "--profile", "private")[0] == 0


# --- AC26 ---------------------------------------------------------------------------------------------------

def _files_keys(doc) -> set[frozenset]:
    return {frozenset(w["files"]) for w in doc["weapons"]}


def test_ac26_godot_keeps_only_godot_scene(world, capsys):
    _, _, out = export(world, capsys, "--packs", "FAKE_Fantasy", "--engine", "godot")
    doc = load(out)
    assert _files_keys(doc) == {frozenset({"godot_scene"})}
    assert doc["generated_from"]["filter"]["engines"] == ["godot"]


def test_ac26_threejs_keeps_only_glb_and_glb_node_when_the_record_has_no_scale(world, capsys):
    _, _, out = export(world, capsys, "--packs", "FAKE_Fantasy,FAKE_Shared", "--engine", "threejs")
    doc = load(out)
    assert _files_keys(doc) == {frozenset({"glb", "glb_node"})}
    w = by_id(doc)
    assert w[H.SWORD_02]["files"] == {"glb": "glb/FAKE_Fantasy/SM_Wep_Sword_02.glb", "glb_node": None}
    assert w[H.SHARED_BOW]["files"] == {"glb": H.SHARED_GLB, "glb_node": "Bow_B"}
    assert doc["generated_from"]["filter"]["engines"] == ["glb"]


def test_ac26_unity_keeps_the_unity_keys(world, capsys):
    _, _, out = export(world, capsys, "--packs", "FAKE_Fantasy", "--engine", "unity")
    assert _files_keys(load(out)) == {frozenset({"unity_prefab", "unity_mesh", "unity_materials"})}


def test_ac26_all_keeps_every_files_key_unchanged(world, capsys):
    for flags in ((), ("--engine", "all")):
        _, _, out = export(world, capsys, "--packs", "FAKE_Fantasy", *flags)
        doc = load(out)
        assert doc["generated_from"]["filter"]["engines"] == ["all"]
        for w in doc["weapons"]:
            assert w["files"] == world.by_id[w["id"]]["files"]
        assert "unreal_uasset" in doc["weapons"][0]["files"]


# --- AC33 (export half) -------------------------------------------------------------------------------------

def test_ac33_renamed_from_is_exported_unchanged(tmp_path, monkeypatch, capsys):
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(X, "_repo_root", lambda: None)
    cat = H.make_catalogs(tmp_path)
    old = "FAKE_Fantasy/SM_Wep_Sword_02_old"
    H.build_and_write(cat, overrides=wfx.overrides_doc(ids={H.SWORD_02: {"renamed_from": [old, "FAKE_Fantasy/a_older"]}}))
    cfg = H.write_config(tmp_path, cat)
    out = tmp_path / "game" / "snap.json"
    code, res = H.run(cfg, capsys, ["weapons", "export", "--game", "g", "--packs", "FAKE_Fantasy", "--out", str(out)])
    assert code == 0, res
    recs = by_id(load(out))
    assert recs[H.SWORD_02]["renamed_from"] == [old, "FAKE_Fantasy/a_older"]
    assert all(w["renamed_from"] == [] for rid, w in recs.items() if rid != H.SWORD_02)
    # it also survives the public profile? no: the public key list has no renamed_from (spec 3.10)
    assert "renamed_from" not in X.PUBLIC_KEYS


# --- refusals, icons ----------------------------------------------------------------------------------------

def test_an_output_path_inside_the_catalogs_dir_or_a_pack_root_is_refused(world, capsys, tmp_path):
    for target in (world.cat / "weapons" / "snapshots" / "x.json", world.cat / "x.json",
                   world.tmp / "unity" / "x.json", world.tmp / "extracted" / "FAKE_Modern" / "x.json"):
        code, res = H.run(world.cfg, capsys, ["weapons", "export", "--game", "g", "--packs", "FAKE_Modern", "--out",
                                              str(target)])
        assert code == 3 and res["ok"] is False, target
        assert not target.exists() and not target.parent.exists() or target.parent == world.cat
    assert not (world.cat / "x.json").exists()


def test_an_output_path_inside_this_repository_is_refused(world, capsys, monkeypatch):
    repo = world.tmp / "pretend_repo"
    repo.mkdir()
    monkeypatch.setattr(X, "_repo_root", lambda: repo)
    target = repo / "snap.json"
    code, res = H.run(world.cfg, capsys, ["weapons", "export", "--game", "g", "--packs", "FAKE_Modern", "--out",
                                          str(target)])
    assert code == 3 and not target.exists()


def test_icons_dir_copies_the_pngs_and_rewrites_paths_relative_to_the_snapshot(world, capsys):
    icons = world.out_dir / "art" / "icons"
    out = world.out_dir / "snaps" / "district7.json"
    code, res = H.run(world.cfg, capsys, ["weapons", "export", "--game", "g", "--packs", "FAKE_Fantasy,FAKE_Modern",
                                          "--icons-dir", str(icons), "--out", str(out)])
    assert code == 0, res
    recs = by_id(load(out))
    sword = recs[H.SWORD_02]["visuals"]
    assert sword["icon"] == "../art/icons/FAKE_Fantasy/SM_Wep_Sword_02.png"
    assert sword["thumb"] == "../art/icons/FAKE_Fantasy/SM_Wep_Sword_02@64.png"
    assert (out.parent / sword["icon"]).read_bytes() == (world.cat / "weapons" / "icons" / "FAKE_Fantasy" / "SM_Wep_Sword_02.png").read_bytes()
    assert (out.parent / sword["thumb"]).is_file()
    assert res["icons_copied"] == 6 and len(list(icons.rglob("*.png"))) == 6
    assert recs[H.SWORD_01]["visuals"]["icon"].startswith("../art/icons/")
    bare = next(w for w in recs.values() if w["id"] not in (H.SWORD_02, H.SWORD_01, "FAKE_Modern/SM_Wep_Pistol_01"))
    assert bare["visuals"]["icon"] is None and bare["visuals"]["thumb"] is None  # never a path to nothing
    assert X.validate_snapshot(out) == []


def test_a_missing_icon_file_becomes_null_with_a_warning(world, capsys, tmp_path):
    cat = H.make_catalogs(tmp_path)
    directory, excluded = H.build_and_write(cat, measure=False)
    directory["weapons"][0]["visuals"]["icon"] = "icons/gone.png"
    from synty_inventory.weapons.directory import write_directory

    write_directory(cat, directory, excluded)
    cfg = H.write_config(tmp_path, cat)
    out = tmp_path / "g" / "s.json"
    code, res = H.run(cfg, capsys, ["weapons", "export", "--game", "g", "--packs", directory["weapons"][0]["pack"],
                                    "--icons-dir", str(tmp_path / "g" / "icons"), "--out", str(out)])
    assert code == 0 and len(res["warnings"]) == 1 and "gone" not in out.read_text(encoding="utf-8")


# --- validate --snapshot ------------------------------------------------------------------------------------

def _snapshot(world, capsys, *flags):
    return export(world, capsys, "--packs", "FAKE_Fantasy,FAKE_Shared", "--roles", "all", *flags)[2]


def test_validate_snapshot_accepts_a_fresh_export_in_both_frames(world, capsys):
    for flags in ((), ("--frame", "asset"), ("--engine", "godot"), ("--engine", "threejs")):
        out = _snapshot(world, capsys, *flags)
        code, res = H.run(world.cfg, capsys, ["weapons", "validate", "--snapshot", str(out)])
        assert code == 0 and res["ok"] is True and res["errors"] == [], (flags, res)
        assert X.validate_snapshot(out) == []


def _write_variant(world, capsys, mutate):
    doc = load(_snapshot(world, capsys))
    mutate(doc)
    path = world.out_dir / f"bad_{next(world.counter)}.json"
    put(path, doc)
    return path


def _first_geom(doc):
    return next(w for w in doc["weapons"] if w["geometry"])["geometry"]


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d.update(extra=1), "top-level keys"),
    (lambda d: d.update(schema_version=2), "schema_version"),
    (lambda d: d["generated_from"].pop("rules_digest"), "generated_from"),
    (lambda d: d["generated_from"].update(rules_digest="XYZ"), "rules_digest"),
    (lambda d: d["generated_from"]["filter"].update(frame="world"), "filter.frame"),
    (lambda d: _first_geom(d).update(frame="asset"), "geometry.frame"),  # snapshot says item, a record says asset
    (lambda d: d["weapons"].reverse(), "sorted by id"),
    (lambda d: d["weapons"].append(copy.deepcopy(d["weapons"][0])), "duplicate"),
    (lambda d: d["weapons"][0]["files"].update(glb="C:\\packs\\x.glb"), "drive-letter"),
    (lambda d: d["weapons"][0]["files"].update(glb="a\\b.glb"), "backslash"),
    (lambda d: d["weapons"][0]["files"].update(glb="/home/tom/x.glb"), "absolute"),
    (lambda d: d["weapons"][0]["hints"].update(damage=5), "damage"),
    (lambda d: d["weapons"][0].update(role="gizmo"), "role"),
    (lambda d: _first_geom(d).update(item_basis=[[1, 0, 0], [0, 1, 0], [0, 1, 0]]), "item_basis"),
    (lambda d: _first_geom(d).update(item_basis=[[0, 1, 0], [1, 0, 0], [0, 0, 1]]), "rotation"),
    (lambda d: d["generated_from"]["filter"].update(roles=["whole"]), "filter.roles"),  # records of other roles remain
])
def test_validate_snapshot_rejects_each_violation(world, capsys, mutate, needle):
    path = _write_variant(world, capsys, mutate)
    errors = X.validate_snapshot(path)
    assert errors and any(needle in e for e in errors), errors
    code, res = H.run(world.cfg, capsys, ["weapons", "validate", "--snapshot", str(path)])
    assert code == 6 and res["ok"] is False and res["errors"]


def test_validate_snapshot_rejects_an_item_frame_that_points_backwards(world, capsys):
    def flip(doc):
        g = by_id(doc)[H.SWORD_02]["geometry"]
        g["tip"], g["butt"] = g["butt"], g["tip"]

    errors = X.validate_snapshot(_write_variant(world, capsys, flip))
    assert any("+Z" in e for e in errors)


def test_validate_snapshot_rejects_files_outside_the_engine_filter(world, capsys):
    out = _snapshot(world, capsys, "--engine", "godot")
    doc = load(out)
    doc["weapons"][0]["files"]["glb"] = "glb/x.glb"
    put(out, doc)
    assert any("engine filter" in e for e in X.validate_snapshot(out))


def test_validate_snapshot_rejects_non_canonical_bytes(world, capsys):
    out = _snapshot(world, capsys)
    doc = load(out)
    put(out, doc, indent=2)
    assert any("canonical" in e for e in X.validate_snapshot(out))
    out.write_bytes(json.dumps(doc, sort_keys=True, indent=1).replace("\n", "\r\n").encode() + b"\r\n")
    assert any("LF" in e for e in X.validate_snapshot(out))
    out.write_text("{not json", encoding="utf-8")
    assert any("unreadable" in e for e in X.validate_snapshot(out))


def test_validate_snapshot_cli_missing_file_exits_2(world, capsys):
    code, res = H.run(world.cfg, capsys, ["weapons", "validate", "--snapshot", str(world.tmp / "nope.json")])
    assert code == 2 and res["ok"] is False


def test_mixed_public_and_full_records_are_rejected(world, capsys):
    out = export(world, capsys, "--packs", "FAKE_Fantasy", "--profile", "public", cfg=world.public_cfg)[2]
    doc = load(out)
    full = by_id(load(export(world, capsys, "--packs", "FAKE_Fantasy")[2]))
    doc["weapons"][0] = full[doc["weapons"][0]["id"]]
    put(out, doc)
    assert any("mixed" in e for e in X.validate_snapshot(out))


# --- the bake itself ----------------------------------------------------------------------------------------

def test_bake_item_frame_is_a_pure_signed_permutation():
    geom = {
        "frame": "asset", "item_basis": [[0, 0, -1], [0, 1, 0], [1, 0, 0]], "node_offset": [1.0, 2.0, 3.0],
        "bounds": {"min": [1.0, -2.0, 3.0], "max": [4.0, 5.0, 9.0], "size": [3.0, 7.0, 6.0], "pivot": "other"},
        "tip": [1.0, 2.0, 3.0], "butt": [0.0, 0.0, 0.0], "muzzle": None, "grip": [-1.0, 0.0, 2.0], "support": None,
        "length_m": 7.0,
    }
    before = copy.deepcopy(geom)
    out = X.bake_item_frame(geom)
    assert geom == before  # the input is not modified
    assert out["frame"] == "item" and out["node_offset"] == [1.0, 2.0, 3.0]
    assert out["tip"] == [-3.0, 2.0, 1.0]  # (-z, y, x)
    assert out["bounds"]["min"] == [-9.0, -2.0, 1.0] and out["bounds"]["max"] == [-3.0, 5.0, 4.0]
    assert out["bounds"]["size"] == [6.0, 7.0, 3.0]
    assert out["butt"] == [0.0, 0.0, 0.0] and str(out["butt"][0]) == "0.0"  # never -0.0
    assert out["muzzle"] is None and out["support"] is None
    with pytest.raises(ValueError):
        X.bake_item_frame({**geom, "item_basis": [[1, 1, 0], [0, 1, 0], [0, 0, 1]]})
