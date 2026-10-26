"""W8a: which parts are attachments (AC62), the rules digests (D-10) and the record/header shape.

docs/weapon_attachments.md 3.3. Expected slot/kind pairs are literals in tests/fixtures/weapons/w8a_attach.py.
"""

from __future__ import annotations

import copy
import importlib.util
import subprocess
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8a_attach", FIX / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons.classify import classify_attachment, raw_tokens  # noqa: E402
from synty_inventory.weapons.directory import build_directory, build_directory_report  # noqa: E402
from synty_inventory.weapons.export import export_snapshot  # noqa: E402
from synty_inventory.weapons.rules import (  # noqa: E402
    attach_rules_digest,
    load_rules,
    shadowed_rules,
    validate_rules,
    weapon_rules_digest,
)
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

# digest of every rule section the base commit d32387d hashed (W7's rules_digest of the shipped YAML)
W7_RULES_DIGEST = "7b9829af37328fe7"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return A.build(tmp_path_factory.mktemp("w8a"))


def by_asset(directory):
    return {w["asset_id"]: w for w in directory["weapons"]}


# --- AC62: classification ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("aid", sorted(A.PARTS))
def test_ac62_each_fixture_part_gets_its_stated_slot_and_kind_or_null(built, aid):
    rec = by_asset(built[0])[aid]
    assert rec["role"] == "part"
    expected = A.PARTS[aid][1]
    if expected is None:
        assert rec["attachment"] is None
    else:
        assert (rec["attachment"]["slot"], rec["attachment"]["kind"]) == expected


def test_ac62_every_row_of_the_table_is_the_first_match_of_a_fixture_part():
    rules = load_rules()
    used = set()
    for aid, (_, expected) in A.PARTS.items():
        got = classify_attachment(aid, A.PACK, "part", {"slot": "misc", "fits": None}, rules)
        assert (got["slot"], got["kind"]) == expected if expected else got is None
        used.add(got["rule"] if got else None)
    # A2: the sight rows (and the sight_side_unsure reason row) are covered by the AC87 table of test_weapons_w8h_classify.py
    assert {r["name"] for r in rules["attachment_rules"]["rows"] if not r["name"].startswith("sight_")} <= used


def test_ac62_the_vehicle_part_is_null_only_because_of_the_never_list():
    rules = load_rules()
    aid = "SM_Wep_Veh_Attach_Laser_01"
    comp = {"slot": "misc", "fits": None}
    assert classify_attachment(aid, A.PACK, "part", comp, rules) is None
    no_never = copy.deepcopy(rules)
    no_never["attachment_rules"]["never"] = []
    got = classify_attachment(aid, A.PACK, "part", comp, no_never)
    assert (got["slot"], got["kind"]) == ("laser_light", "laser")


def test_ac62_a_vehicle_pack_family_is_never_an_attachment():
    rules = load_rules()
    comp = {"slot": "optic", "fits": None}
    assert classify_attachment("SM_Wep_Rifle_Scope_01", "FAKE_Vehicles", "part", comp, rules) is None
    assert classify_attachment("SM_Wep_Rifle_Scope_01", "FAKE_Modern", "part", comp, rules) is not None


def test_ac62_only_parts_are_attachments_and_whole_records_carry_no_attachment_key(built):
    rules = load_rules()
    assert classify_attachment("SM_Wep_Rifle_Scope_01", A.PACK, "whole", None, rules) is None
    for rec in built[0]["weapons"]:
        assert ("attachment" in rec) == (rec["role"] == "part")


def test_ac62_torch_and_the_not_lists():
    rules = load_rules()
    comp = {"slot": "misc", "fits": None}
    assert classify_attachment("SM_Wep_Mod_Torch_01", A.PACK, "part", comp, rules)["kind"] == "light"
    assert classify_attachment("SM_Wep_Mod_Mining_Laser_01", A.PACK, "part", comp, rules) is None
    assert classify_attachment("SM_Wep_Sniper_Handle_Scope_01", A.PACK, "part", comp, rules)["kind"] == "carry_handle_scope"


def test_raw_tokens_keep_the_words_the_alias_table_folds_together():
    assert {"scope", "sniper", "reddot", "foregrip"} <= raw_tokens("SM_Wep_Sniper_Scope_RedDot_Fore_Grip_01")
    assert "optic" not in raw_tokens("SM_Wep_Scope_01")


def test_the_attachment_table_validates_and_nothing_in_it_is_shadowed():
    rules = load_rules()
    assert validate_rules(rules) == []
    assert shadowed_rules(rules) == []
    bad = copy.deepcopy(rules)
    bad["attachment_rules"]["rows"][0]["set"] = {"slot": "optic", "kind": "drum"}
    assert any("kind" in e for e in validate_rules(bad))


def test_the_component_of_a_part_is_never_changed_by_the_attachment_table(built):
    rec = by_asset(built[0])["SM_Wep_RedDot_01"]
    assert rec["component"] == {"slot": "optic", "fits": None}  # the part rules' answer, not remapped (D-2)


def test_no_geometry_leaves_the_block_without_an_anchor_and_the_review_untouched(tmp_path):
    cat, _ = A.write_world(tmp_path)
    directory, _ = A.WFX.build(cat, pack_settings=A.PACK_SETTINGS, measure=False)
    rec = by_asset(directory)["SM_Wep_Symmetric_Scope_01"]
    assert rec["attachment"]["anchor"] is None and rec["attachment"]["footprint"] is None
    assert rec["review"]["reasons"] == ["colourway_unknown", "no_geometry"]
    assert rec["review"]["confidence"] == 0.9
    assert validate_directory(directory) == []


def test_a_fully_built_directory_validates_and_lists_only_the_eligible_hosts(built):
    # W8a listed no host at all (the compatibility pass did not exist); W8c fills the lists, so the check now is that every
    # listed host is one of the two eligible guns of this fixture (the grenade and the sword are never hosts, INV-14)
    assert validate_directory(built[0]) == []
    eligible_hosts = {f"{A.PACK}/SM_Wep_Rifle_Assault_01", f"{A.PACK}/SM_Wep_Pistol_01"}
    for rec in built[0]["weapons"]:
        if rec.get("attachment"):
            listed = {h["host"] for h in rec["attachment"]["compatible_hosts"] + rec["attachment"]["pending_hosts"]}
            assert listed <= eligible_hosts


# --- the rules digests (D-10): attachment rules do not move rules_digest --------------------------------------------


def test_rules_digest_of_the_shipped_yaml_is_the_one_w7_computed():
    assert weapon_rules_digest(load_rules()) == W7_RULES_DIGEST


def test_rules_digest_equals_the_digest_the_base_commit_computes_for_its_own_yaml():
    import yaml

    from synty_inventory.weapons import digest

    repo = Path(__file__).resolve().parents[1]
    try:
        old = subprocess.run(
            ["git", "show", "d32387d:src/synty_inventory/data/weapon_rules.yaml"], cwd=repo, capture_output=True,
            check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("the base commit is not available in this checkout")
    assert digest(yaml.safe_load(old)) == weapon_rules_digest(load_rules())


def test_editing_an_attachment_row_moves_only_the_attach_digest():
    rules = load_rules()
    edited = copy.deepcopy(rules)
    edited["attachment_rules"]["rows"][1]["set"]["kind"] = "sniper_scope"
    assert weapon_rules_digest(edited) == weapon_rules_digest(rules) == W7_RULES_DIGEST
    assert attach_rules_digest(edited) != attach_rules_digest(rules)


def test_editing_a_w7_rule_moves_rules_digest_and_not_the_attach_digest():
    rules = load_rules()
    edited = copy.deepcopy(rules)
    edited["rules"][0]["confidence"] = 0.5
    assert weapon_rules_digest(edited) != weapon_rules_digest(rules)
    assert attach_rules_digest(edited) == attach_rules_digest(rules)


def test_the_directory_header_records_both_digests_and_the_attach_version(built):
    d = built[0]
    assert d["rules_digest"] == W7_RULES_DIGEST
    assert d["attach_version"] == 13 and d["attach_rules_digest"] == attach_rules_digest(load_rules())


def test_a_changed_attachment_row_moves_the_attach_digest_but_not_the_export_digest(tmp_path):
    rules = load_rules()
    edited = copy.deepcopy(rules)
    edited["attachment_rules"]["rows"][1]["set"]["kind"] = "sniper_scope"
    d1, _, _, _ = A.build(tmp_path / "a", rules=rules)
    d2, _, _, _ = A.build(tmp_path / "b", rules=edited)
    assert d1["rules_digest"] == d2["rules_digest"]
    assert d1["attach_rules_digest"] != d2["attach_rules_digest"]
    kw = dict(game="g", pack_ids=None, ids=None, roles={"whole"}, engines={"all"}, frame="item", profile="private",
              pack_meta={}, overrides_digest=d1["overrides_digest"])
    assert (export_snapshot(d1, rules_digest=d1["rules_digest"], **kw)["generated_from"]
            == export_snapshot(d2, rules_digest=d2["rules_digest"], **kw)["generated_from"])


def test_a_partial_build_refuses_a_base_made_with_other_attachment_rules(tmp_path):
    import shutil

    from synty_inventory.weapons import InputError
    from synty_inventory.weapons.overrides import empty_overrides

    cat = A.WFX.make_catalogs_dir(tmp_path / "m")  # the committed packs, plus FAKE_Attach beside them
    acat, root = A.write_world(tmp_path / "a")
    shutil.copy(acat / f"{A.PACK}.json", cat / f"{A.PACK}.json")
    settings = A.WFX.pack_settings() | A.PACK_SETTINGS
    common = dict(overrides=empty_overrides(), pack_settings=settings, measure=False)
    d, e = build_directory(cat, **common)
    edited = copy.deepcopy(load_rules())
    edited["attachment_rules"]["rows"][1]["set"]["kind"] = "sniper_scope"
    d2, e2, _ = build_directory_report(cat, packs=[A.PACK], base=(d, e), **common)  # same rules: merges
    assert d2["attach_rules_digest"] == d["attach_rules_digest"]
    with pytest.raises(InputError, match="other rules"):
        build_directory_report(cat, packs=[A.PACK], rules=edited, base=(d, e), **common)
    stale_version = dict(d, attach_version=0)
    with pytest.raises(InputError, match="other rules"):
        build_directory_report(cat, packs=[A.PACK], base=(stale_version, e), **common)


def test_the_gate_treats_a_changed_attachment_row_or_attach_version_as_stale(tmp_path, monkeypatch):
    from synty_inventory.weapons import gate
    from synty_inventory.weapons.directory import write_directory
    from synty_inventory.weapons.overrides import empty_overrides

    rules = load_rules()
    directory, excluded, cat, _ = A.build(tmp_path)
    write_directory(cat, directory, excluded)

    def current(**kw):
        r = gate.check_weapons_directory(cat, overrides=empty_overrides(), **kw)
        return next(c for c in r["checks"] if c["check"] == "directory_current")["ok"]

    assert current(rules=rules) is True
    edited = copy.deepcopy(rules)
    edited["attachment_rules"]["rows"][1]["set"]["kind"] = "sniper_scope"
    assert current(rules=edited) is False
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", pkg.WEAPON_ATTACH_VERSION + 1)
    assert current(rules=rules) is False
