"""Weapon directory W7b: the kind contract, kind inference and the explicit export target (AC58, AC59, AC60).

docs/weapon_directory.md 3.4.2 PATCH W7b and 3.10 PATCH W7b. Everything is synthetic: the committed fixture catalogs,
one invented pack with GLBs drawn by make_glbs.py, throwaway catalogs under the pytest tmp dir. Expected values are
literals (here and in fixtures/weapons/w7b_cases.py): nothing is read from the code or the rules under test.

Each rule, alias, hint list and the measured fallback has cases that fail without it; the mutation evidence is in the
W7b build report (a mutation is the entry removed from the shipped rules / source for one run).
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_HERE = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wfx = _load("wfx")
H = _load("review_helpers")
M = _load("make_glbs")
C = _load("make_catalogs")
W = _load("w7b_cases")

from synty_inventory.weapons import REASONS, export as X, to_text  # noqa: E402
from synty_inventory.weapons.classify import classify, tokenize_id  # noqa: E402
from synty_inventory.weapons.geometry import measure_weapon, pass2_inputs  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import kind_hints, load_rules, validate_rules  # noqa: E402
from synty_inventory.weapons.schema import validate_directory, validate_record  # noqa: E402


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def cls(rules, asset_id, pack=W.OTHER, overrides=None, measured=None):
    return classify({"id": asset_id, "type": "weapon"}, pack, rules, overrides or empty_overrides(), None,
                    measured=measured)


# --- AC58: the kind contract ---------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _ = wfx.build(wfx.make_catalogs_dir(tmp_path_factory.mktemp("w7b_build")))
    return directory


def test_ac58_a_full_synthetic_build_has_no_whole_or_emplaced_record_with_a_null_kind(built):
    roles = set()
    for rec in built["weapons"]:
        roles.add(rec["role"])
        if rec["role"] in ("whole", "emplaced"):
            assert rec["kind"] in ("ranged", "melee", "thrown", "shield"), rec["id"]
        else:
            assert rec["kind"] is None, rec["id"]
    assert {"whole", "emplaced", "part"} <= roles  # the build really holds both sides of the iff
    unknown = [r for r in built["weapons"] if r["archetype"] == "unknown" and r["role"] == "whole"]
    assert len(unknown) >= 5  # the fixture has unknown wholes: they are the records the old exemption let through
    assert validate_directory(built) == []


def _record(built, archetype, role="whole"):
    rec = next(r for r in built["weapons"] if r["role"] == role and r["archetype"] == archetype)
    return copy.deepcopy(rec)


def test_ac58_check_record_rejects_a_whole_unknown_record_with_a_null_kind_and_accepts_it_with_a_kind(built):
    rec = _record(built, "unknown")
    assert validate_record(rec) == []
    rec["kind"] = None
    errs = validate_record(rec)
    assert len(errs) == 1 and ".kind" in errs[0] and "whole" in errs[0]
    rec["kind"] = "ranged"
    assert validate_record(rec) == []


def test_ac58_check_record_rejects_an_emplaced_record_with_a_null_kind_and_accepts_it_with_a_kind(built):
    rec = _record(built, "turret", role="emplaced")
    assert validate_record(rec) == []
    rec["kind"] = None
    errs = validate_record(rec)
    assert len(errs) == 1 and ".kind" in errs[0] and "emplaced" in errs[0]
    rec["kind"] = "ranged"
    assert validate_record(rec) == []


def test_ac58_a_part_keeps_a_null_kind_and_a_part_with_a_kind_is_still_rejected(built):
    rec = _record(built, "unknown", role="part")
    assert rec["kind"] is None and validate_record(rec) == []
    rec["kind"] = "melee"
    assert any(".kind" in e for e in validate_record(rec))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fixture catalogs + an unmeasured directory on disk; the checkout seam points elsewhere (tmp sits in the checkout)."""
    cat = H.make_catalogs(tmp_path)
    H.build_and_write(cat)
    monkeypatch.setattr(X, "_repo_root", lambda: None)
    return {"tmp": tmp_path, "cat": cat, "cfg": H.write_config(tmp_path, cat)}


def _null_the_kind(cat: Path, record_id: str) -> None:
    path = cat / "weapons" / "directory.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    rec = next(w for w in doc["weapons"] if w["id"] == record_id)
    assert rec["role"] in ("whole", "emplaced")
    rec["kind"] = None
    path.write_bytes(to_text(doc).encode("utf-8"))


NULL_KIND_ID = "FAKE_Generic/SM_Wep_Mystery_01"  # a whole record of archetype unknown: the case the old exemption let through
EXPORT = ["weapons", "export", "--game", "w7b", "--packs", "FAKE_Modern"]
EXPORT_GENERIC = ["weapons", "export", "--game", "w7b", "--packs", "FAKE_Generic"]


def tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): (p.is_dir(), p.stat().st_size if p.is_file() else 0)
            for p in sorted(root.rglob("*"))}


def test_ac58_weapons_validate_rejects_a_directory_holding_a_whole_record_with_a_null_kind(world, capsys):
    code, res = H.run(world["cfg"], capsys, ["weapons", "validate"])
    assert code == 0 and res["directory"] == "ok", res
    _null_the_kind(world["cat"], NULL_KIND_ID)
    code, res = H.run(world["cfg"], capsys, ["weapons", "validate"])
    assert code == 6 and res["directory"] == "invalid"
    assert any(".kind" in e for e in res["directory_errors"])


def test_ac58_export_of_a_directory_with_a_null_kind_exits_6_names_the_ids_and_writes_no_file(world, capsys):
    _null_the_kind(world["cat"], NULL_KIND_ID)
    before = tree(world["tmp"])
    code, res = H.run(world["cfg"], capsys, EXPORT_GENERIC)
    assert code == 6 and res["ok"] is False
    assert NULL_KIND_ID in res["error"] and "kind" in res["error"]  # the message names the offending id
    assert res["kind_null_ids"] == [NULL_KIND_ID]
    assert tree(world["tmp"]) == before
    assert not (world["cat"] / "weapons" / "snapshots").exists()


def test_ac58_the_export_message_names_only_the_first_few_ids(world, capsys):
    path = world["cat"] / "weapons" / "directory.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    wholes = [w for w in doc["weapons"] if w["role"] == "whole"]
    assert len(wholes) >= 8
    for w in wholes[:8]:
        w["kind"] = None
    path.write_bytes(to_text(doc).encode("utf-8"))
    code, res = H.run(world["cfg"], capsys, EXPORT_GENERIC)
    assert code == 6
    assert "8 whole/emplaced" in res["error"] and "(8 in all)" in res["error"]
    assert sum(1 for w in wholes[:8] if w["id"] in res["error"]) == 5


# --- AC59: vocabulary and rules ------------------------------------------------------------------------------------


@pytest.mark.parametrize("rule,pack,aid,archetype,kind", W.RULE_CASES)
def test_ac59_each_new_rule_is_the_first_match_of_its_ids(rules, rule, pack, aid, archetype, kind):
    out = cls(rules, aid, pack)
    assert (out["matched_rule"], out["role"], out["archetype"], out["kind"]) == (rule, "whole", archetype, kind), aid
    assert out["provenance"]["kind"] == "rules" and "kind_guessed" not in out["reasons"]


@pytest.mark.parametrize("pack,aid,rule,archetype", W.RULE_KEEP_CASES)
def test_ac59_the_new_rules_leave_other_ids_alone(rules, pack, aid, rule, archetype):
    out = cls(rules, aid, pack)
    assert (out["matched_rule"], out["archetype"]) == (rule, archetype), aid


def test_ac59_the_stated_archetypes_of_the_spec_examples(rules):
    assert cls(rules, "SM_Wep_Assault_01", W.OTHER)["archetype"] == "rifle"
    assert cls(rules, "SM_Wep_Heavy_01", W.WORLDS)["archetype"] == "heavy_gun"
    assert cls(rules, "SM_Wep_Alien_01", W.WORLDS)["archetype"] == "rifle"
    assert cls(rules, "SM_Wep_Heavy_01", W.OTHER)["archetype"] == "unknown"
    assert cls(rules, "SM_Wep_Alien_01", W.OTHER)["archetype"] == "unknown"


@pytest.mark.parametrize("aid,role,archetype,slot,rule", W.ALIAS_CASES)
def test_ac59_the_new_aliases_and_the_battery_token_classify(rules, aid, role, archetype, slot, rule):
    out = cls(rules, aid)
    assert (out["role"], out["archetype"], out["matched_rule"]) == (role, archetype, rule), aid
    assert (out["component"] or {}).get("slot") == slot, aid


def test_ac59_the_joined_spellings_reach_one_canonical_token(rules):
    assert tokenize_id("SM_Wep_FlameThrower_01", rules) == tokenize_id("SM_Wep_Flame_Thrower_01", rules)
    assert "flamethrower" in tokenize_id("SM_Wep_Flame_Thrower_01", rules)
    assert tokenize_id("SM_Wep_ChainSaw_01", rules) == tokenize_id("SM_Wep_Chain_Saw_01", rules)
    assert "chainsaw" in tokenize_id("SM_Wep_Chain_Saw_01", rules)
    assert "shotgun" in tokenize_id("SM_Wep_Blunderbuss_01", rules)
    assert "utilgun" in tokenize_id("SM_Wep_Stungun_01", rules)
    assert "stock" in tokenize_id("SM_Wep_Gunstock_01", rules)
    assert "knife" in tokenize_id("SM_Wep_Cleaver_01", rules)


# --- AC59: kind hints ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("aid,kind", W.HINT_CASES)
def test_ac59_the_named_hint_examples(rules, aid, kind):
    out = cls(rules, aid)
    assert (out["kind"], out["archetype"], out["role"]) == (kind, "unknown", "whole"), aid
    assert out["provenance"]["kind"] == "rules"  # the schema's provenance enum spells the spec's `rule` as `rules`
    assert "kind_guessed" not in out["reasons"]


@pytest.mark.parametrize("kind", ["ranged", "melee", "thrown"])
def test_ac59_every_token_of_a_hint_list_gives_its_kind_without_a_guess(rules, kind):
    for token in W.HINT_TOKENS[kind]:
        out = cls(rules, f"SM_Wep_{token.capitalize()}_01")
        assert (out["kind"], out["archetype"]) == (kind, "unknown"), token
        assert out["provenance"]["kind"] == "rules" and "kind_guessed" not in out["reasons"], token


def test_ac59_the_shipped_hint_lists_hold_exactly_the_documented_tokens(rules):
    got = {k: sorted(v) for k, v in kind_hints(rules)}
    assert got == {k: sorted(v) for k, v in W.HINT_TOKENS.items()}


def test_ac59_the_first_kind_with_a_shared_token_wins_in_the_order_ranged_melee_thrown(rules):
    assert cls(rules, "SM_Wep_Laser_Sickle_01")["kind"] == "ranged"
    assert cls(rules, "SM_Wep_Sickle_Rock_01")["kind"] == "melee"


def test_ac59_an_unhinted_unmeasured_unknown_is_a_melee_guess(rules):
    out = cls(rules, "SM_Wep_Zorb_01")
    assert (out["kind"], out["archetype"], out["provenance"]["kind"]) == ("melee", "unknown", "rules")
    assert "kind_guessed" in out["reasons"]


def test_ac59_a_kind_hint_never_overrides_a_kind_a_rule_set(rules):
    out = cls(rules, "SM_Wep_Pistol_Rock_01")
    assert (out["archetype"], out["kind"]) == ("pistol", "ranged") and "kind_guessed" not in out["reasons"]


def test_ac59_the_loader_accepts_a_rules_file_without_kind_hints_and_rejects_bad_ones(rules):
    bare = copy.deepcopy(rules)
    del bare["kind_hints"]
    assert validate_rules(bare) == [] and kind_hints(bare) == []

    def errors(table):
        bad = copy.deepcopy(rules)
        bad["kind_hints"] = table
        return validate_rules(bad)

    assert errors({"ranged": ["laser"], "melee": ["laser"]}) == ["kind_hints: token 'laser' is in both 'ranged' and 'melee'"]
    assert any("kind_hints.shield" in e and "unknown kind" in e for e in errors({"shield": ["buckler"]}))
    assert any("kind_hints.ranged" in e and "list" in e for e in errors({"ranged": "laser"}))
    assert any("lower-case" in e for e in errors({"ranged": ["Laser"]}))
    assert any("alias variant" in e and "'nailgun'" in e for e in errors({"ranged": ["nailgun"]}))
    assert errors({"ranged": ["laser"], "thrown": ["rock"]}) == []


# --- AC59: the measured fallback -----------------------------------------------------------------------------------

PACK = "FAKE_W7b"
SCIFI = {"setting": "scifi_city", "era": "near_future"}


def _make_world(tmp_path: Path, meshes: dict, unmeasured=()):
    """A catalogs dir with the invented pack ``FAKE_W7b``: one asset per mesh (with its GLB) and ``unmeasured`` ids."""
    cat = wfx.make_catalogs_dir(tmp_path)
    head = json.loads((_HERE / "review_FAKE_Review.json").read_text(encoding="utf-8"))
    assets = [C._asset(PACK, aid) for aid in meshes] + [C._asset(PACK, aid, glb=None) for aid in unmeasured]
    head.update(pack_id=PACK, assets=assets, asset_count=len(assets))
    (cat / f"{PACK}.json").write_text(json.dumps(head, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    root = tmp_path / "threejs"
    for aid, mesh in meshes.items():
        M.write_glb(root / "glb" / PACK / f"{aid}.glb", [{"name": aid, "mesh": mesh}])
    return cat, root


def _build(cat, root, overrides=None):
    return wfx.build(cat, threejs_v2_dir=root, overrides=overrides or empty_overrides(),
                     pack_settings={**wfx.pack_settings(), PACK: SCIFI})[0]


def _rec(directory, aid):
    return next(w for w in directory["weapons"] if w["id"] == f"{PACK}/{aid}")


Z_LONG = "SM_Wep_Zorb_Long_01"
Y_LONG = "SM_Wep_Zorb_Tall_01"
HINTED_MELEE_Z = "SM_Wep_Sickle_Long_01"  # a z-long mesh, but the vocabulary says melee
NO_GLB = "SM_Wep_Zorb_Blind_01"


@pytest.fixture(scope="module")
def measured_world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w7b_measured")
    meshes = {Z_LONG: M.gun(), Y_LONG: M.sword(), HINTED_MELEE_Z: M.gun()}
    cat, root = _make_world(tmp, meshes, unmeasured=[NO_GLB])
    return {"cat": cat, "root": root, "directory": _build(cat, root)}


def test_ac59_a_measured_unknown_with_long_axis_z_is_ranged_and_measured_for_that_kind(measured_world):
    rec = _rec(measured_world["directory"], Z_LONG)
    assert (rec["archetype"], rec["kind"], rec["provenance"]["kind"]) == ("unknown", "ranged", "measured")
    assert "kind_guessed" in rec["review"]["reasons"] and "unmeasured" not in rec["flags"]
    geo = rec["geometry"]
    assert geo["long_axis"] == "z"
    assert geo["muzzle"] is not None and geo["tip"] is None  # a ranged record: muzzle, no tip
    glb = measured_world["root"] / "glb" / PACK / f"{Z_LONG}.glb"
    want = measure_weapon(glb, None, 1.0, "unknown", "ranged", "whole", load_rules(), hold_class="none",
                          genre=rec["genre"])
    assert geo == want  # the stored geometry is the one measured for the FINAL kind
    assert validate_record(rec) == []


def test_ac59_a_measured_unknown_with_long_axis_y_is_melee_and_measured_for_that_kind(measured_world):
    rec = _rec(measured_world["directory"], Y_LONG)
    assert (rec["archetype"], rec["kind"], rec["provenance"]["kind"]) == ("unknown", "melee", "measured")
    assert "kind_guessed" in rec["review"]["reasons"]
    geo = rec["geometry"]
    assert geo["long_axis"] == "y"
    assert geo["tip"] is not None and geo["muzzle"] is None
    glb = measured_world["root"] / "glb" / PACK / f"{Y_LONG}.glb"
    want = measure_weapon(glb, None, 1.0, "unknown", "melee", "whole", load_rules(), hold_class="none",
                          genre=rec["genre"])
    assert geo == want
    assert validate_record(rec) == []


def test_ac59_an_unmeasured_unknown_without_a_hint_is_melee_with_kind_guessed(measured_world):
    rec = _rec(measured_world["directory"], NO_GLB)
    assert (rec["archetype"], rec["kind"], rec["provenance"]["kind"]) == ("unknown", "melee", "rules")
    assert rec["geometry"] is None and "unmeasured" in rec["flags"]
    assert "kind_guessed" in rec["review"]["reasons"]
    assert validate_record(rec) == []


def test_ac59_a_kind_hint_beats_the_measured_axis(measured_world):
    rec = _rec(measured_world["directory"], HINTED_MELEE_Z)
    assert rec["geometry"]["long_axis"] == "z"  # the mesh is z-long, which alone would have said ranged
    assert (rec["archetype"], rec["kind"], rec["provenance"]["kind"]) == ("unknown", "melee", "rules")
    assert "kind_guessed" not in rec["review"]["reasons"]
    assert rec["geometry"]["muzzle"] is None and rec["geometry"]["tip"] is not None


def test_ac59_pass2_inputs_exposes_the_long_axis_of_the_measurement():
    detail = {"geometry": {"length_m": 0.9, "long_axis": "z"}, "flags": [], "reasons": []}
    assert pass2_inputs(detail) == {"length_m": 0.9, "long_axis": "z", "forward_by_fallback": False,
                                    "axes_unexpected": False}
    assert pass2_inputs({"geometry": None, "flags": [], "reasons": ["no_geometry"]}) is None


def test_ac59_classify_takes_the_guess_from_the_measured_long_axis(rules):
    base = {"length_m": 0.5, "forward_by_fallback": False, "axes_unexpected": False}
    z = cls(rules, "SM_Wep_Zorb_01", measured={**base, "long_axis": "z"})
    y = cls(rules, "SM_Wep_Zorb_01", measured={**base, "long_axis": "y"})
    x = cls(rules, "SM_Wep_Zorb_01", measured={**base, "long_axis": "x"})
    assert (z["kind"], z["provenance"]["kind"]) == ("ranged", "measured")
    assert (y["kind"], y["provenance"]["kind"]) == ("melee", "measured")
    assert (x["kind"], x["provenance"]["kind"]) == ("melee", "measured")
    assert all("kind_guessed" in o["reasons"] for o in (z, y, x))


@pytest.mark.parametrize("y_size,z_size,kind,axis", [
    (1.00, 1.50, "ranged", "z"),   # z clearly longest
    (1.00, 1.04, "melee", "y"),    # a tie within the 5 % band: the melee default (y) keeps its own kind
    (1.00, 1.00, "melee", "y"),    # an exact tie
    (1.04, 1.00, "melee", "y"),
    (1.50, 1.00, "melee", "y"),    # y clearly longest
])
def test_ac59_the_kind_guess_is_stable_on_near_ties_and_geometry_follows_the_final_kind(tmp_path, y_size, z_size,
                                                                                         kind, axis):
    aid = "SM_Wep_Zorb_Tie_01"
    mesh = M.box((-0.03, -y_size / 2, -z_size / 2), (0.03, y_size / 2, z_size / 2))
    cat, root = _make_world(tmp_path, {aid: mesh})
    first = _rec(_build(cat, root), aid)
    second = _rec(_build(cat, root), aid)
    assert first == second  # deterministic
    assert first["kind"] == kind and first["geometry"]["long_axis"] == axis
    # the measurement was made for the final kind: a ranged record has a muzzle and no tip, any other the reverse
    assert (first["geometry"]["muzzle"] is not None) == (kind == "ranged")
    assert (first["geometry"]["tip"] is None) == (kind == "ranged")


# --- AC59: an override clears the guess -----------------------------------------------------------------------------


def _override(aid, **fields):
    return wfx.overrides_doc(ids={f"{PACK}/{aid}": {"set": fields}})


@pytest.mark.parametrize("fields,kind,arch", [
    ({"kind": "thrown"}, "thrown", "unknown"),
    ({"kind": "ranged"}, "ranged", "unknown"),
    ({"archetype": "club"}, "melee", "club"),
])
def test_ac59_an_id_override_of_kind_or_archetype_clears_kind_guessed(tmp_path, fields, kind, arch):
    cat, root = _make_world(tmp_path, {Z_LONG: M.gun()}, unmeasured=[NO_GLB])
    directory = _build(cat, root, overrides=wfx.overrides_doc(ids={
        f"{PACK}/{Z_LONG}": {"set": fields}, f"{PACK}/{NO_GLB}": {"set": fields}}))
    for aid in (Z_LONG, NO_GLB):
        rec = _rec(directory, aid)
        assert (rec["kind"], rec["archetype"], rec["provenance"]["kind"]) == (kind, arch, "override"), aid
        assert "kind_guessed" not in rec["review"]["reasons"], aid
        assert validate_record(rec) == [], aid


def test_ac59_a_role_override_that_leaves_no_kind_still_gets_one(rules):
    # a part promoted to `whole` by an override has no kind from the rules: the contract still holds
    ovr = wfx.overrides_doc(ids={f"{W.OTHER}/SM_Wep_Gunstock_01": {"set": {"role": "whole"}}})
    out = cls(rules, "SM_Wep_Gunstock_01", overrides=ovr)
    assert out["role"] == "whole" and out["kind"] == "melee" and "kind_guessed" in out["reasons"]


def test_ac59_the_build_report_lists_each_kind_guessed_record_with_its_kind(tmp_path):
    from synty_inventory.weapons.directory import build_directory_report
    from synty_inventory.weapons.overrides import empty_overrides as empty

    cat, root = _make_world(tmp_path, {Z_LONG: M.gun(), Y_LONG: M.sword(), HINTED_MELEE_Z: M.gun()},
                            unmeasured=[NO_GLB])
    directory, _, report = build_directory_report(
        cat, threejs_v2_dir=root, overrides=empty(), pack_settings={**wfx.pack_settings(), PACK: SCIFI})
    mine = {r["id"]: r["kind"] for r in report["kind_guessed"] if r["id"].startswith(f"{PACK}/")}
    assert mine == {f"{PACK}/{Z_LONG}": "ranged", f"{PACK}/{Y_LONG}": "melee", f"{PACK}/{NO_GLB}": "melee"}
    guessed = {w["id"] for w in directory["weapons"] if "kind_guessed" in w["review"]["reasons"]}
    assert guessed == {r["id"] for r in report["kind_guessed"]}


def test_ac59_kind_guessed_is_a_review_reason_the_schema_accepts(built):
    assert "kind_guessed" in REASONS
    guessed = [w for w in built["weapons"] if "kind_guessed" in w["review"]["reasons"]]
    assert guessed and all(w["archetype"] == "unknown" and w["provenance"]["kind"] == "rules" for w in guessed)
    assert all(validate_record(copy.deepcopy(w)) == [] for w in guessed)


# --- AC60: the explicit export target -----------------------------------------------------------------------------


@pytest.fixture
def exp_world(tmp_path, monkeypatch):
    cat = H.make_catalogs(tmp_path, shared=True)
    root = H.make_threejs(tmp_path, cat)
    H.build_and_write(cat, threejs_v2_dir=root)
    monkeypatch.setattr(X, "_repo_root", lambda: None)
    return {"tmp": tmp_path, "cat": cat, "cfg": H.write_config(tmp_path, cat)}


def test_ac60_an_explicit_out_under_the_snapshots_folder_is_accepted_and_written(exp_world, capsys):
    snaps = exp_world["cat"] / "weapons" / "snapshots"
    code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", str(snaps / "x.json")])
    assert code == 0, res
    assert (snaps / "x.json").is_file() and X.validate_snapshot(snaps / "x.json") == []
    nested = snaps / "deep" / "er" / "y.json"
    code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", str(nested)])
    assert code == 0, res
    assert nested.is_file() and X.validate_snapshot(nested) == []


def test_ac60_elsewhere_in_the_catalogs_dir_is_still_refused_with_nothing_written(exp_world, capsys):
    cat = exp_world["cat"]
    before = tree(exp_world["tmp"])
    for target in (cat / "weapons" / "x.json", cat / "x.json", cat / "weapons" / "snapshots_other" / "x.json",
                   cat / "weapons" / "icons" / "x.json"):
        code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", str(target)])
        assert code == 3 and res["ok"] is False, target
        assert tree(exp_world["tmp"]) == before, target


def test_ac60_a_dot_dot_path_that_resolves_out_of_the_snapshots_folder_is_refused(exp_world, capsys):
    cat = exp_world["cat"]
    before = tree(exp_world["tmp"])
    snaps = cat / "weapons" / "snapshots"
    for raw in (f"{snaps}/../x.json", f"{snaps}/deep/../../x.json", f"{snaps}/../../x.json"):
        code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", raw])
        assert code == 3 and res["ok"] is False, raw
        assert tree(exp_world["tmp"]) == before, raw
    # a `..` that stays inside the folder is fine
    code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", f"{snaps}/deep/../ok.json"])
    assert code == 0, res
    assert (snaps / "ok.json").is_file()


def test_ac60_a_pack_root_and_this_checkout_are_still_refused(exp_world, capsys, monkeypatch):
    tmp = exp_world["tmp"]
    (tmp / "extracted").mkdir()
    before = tree(tmp)
    code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", str(tmp / "extracted" / "x.json")])
    assert code == 3 and res["ok"] is False
    assert tree(tmp) == before
    lib = tmp / "pretend_library"
    lib.mkdir()
    monkeypatch.setattr(X, "_repo_root", lambda: lib)
    before = tree(tmp)
    code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", str(lib / "deep" / "x.json")])
    assert code == 3 and tree(tmp) == before
    # and a snapshots path below the pretend checkout is refused too: the checkout rule is not skipped
    monkeypatch.setattr(X, "_repo_root", lambda: tmp)
    code, res = H.run(exp_world["cfg"], capsys, [*EXPORT, "--out", str(exp_world["cat"] / "weapons" / "snapshots" / "x.json")])
    assert code == 3 and not (exp_world["cat"] / "weapons" / "snapshots").exists()


def test_ac60_the_default_target_is_unchanged(exp_world, capsys):
    code, res = H.run(exp_world["cfg"], capsys, EXPORT)
    assert code == 0, res
    assert (exp_world["cat"] / "weapons" / "snapshots" / "w7b.json").is_file()
