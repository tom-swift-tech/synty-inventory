"""W8a: the attachment block in the directory schema (AC61; docs/weapon_attachments.md 3.2, INV-14, INV-18).

``weapons validate --directory`` exits 0 on the good fixture directory and 6 on each hand-broken variant. The enum and
hold-class lists below are literals, not imports of the constants under test.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8a_attach", Path(__file__).parent / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

from synty_inventory.cli import main  # noqa: E402
from synty_inventory.weapons import guards  # noqa: E402
from synty_inventory.weapons.schema import check_record, validate_directory, validate_record  # noqa: E402

RIFLE, PISTOL = f"{A.PACK}/SM_Wep_Rifle_Assault_01", f"{A.PACK}/SM_Wep_Pistol_01"
GRENADE, SWORD = f"{A.PACK}/SM_Wep_Grenade_Frag_01", f"{A.PACK}/SM_Wep_Sword_Long_01"
SCOPE = f"{A.PACK}/SM_Wep_Rifle_Scope_01"
SILENCER = f"{A.PACK}/SM_Wep_Silencer_01"
MAG = f"{A.PACK}/SM_Wep_Rifle_Mag_01"


@pytest.fixture(autouse=True)
def _no_other_inventory_runner(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return A.build(tmp_path_factory.mktemp("w8a_schema"))


def rec_of(doc, rid):
    return next(w for w in doc["weapons"] if w["id"] == rid)


def good_directory(built):
    """The built fixture directory with hosts listed on the scope, the silencer and the magazine."""
    directory = copy.deepcopy(built[0])
    rec_of(directory, SCOPE)["attachment"]["compatible_hosts"] = [
        {"host": RIFLE, "tier": "twin", "score": 0.95, "signals": ["twin"], "replaces": []},
        {"host": PISTOL, "tier": "same_pack_fit", "score": 0.7, "signals": ["fit"], "replaces": []},
    ]
    rec_of(directory, SCOPE)["attachment"]["pending_hosts"] = [{"host": PISTOL, "tier": "cross_pack_fit"}]
    return directory


def clear_env(monkeypatch):
    for key in ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
                "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT"):
        monkeypatch.delenv(key, raising=False)


def validate_via_cli(tmp_path, monkeypatch, capsys, doc, excluded):
    """``weapons validate --directory <file>`` on a directory written beside its excluded.json; (exit code, output)."""
    clear_env(monkeypatch)
    folder = tmp_path / "v"
    folder.mkdir(exist_ok=True)
    (folder / "directory.json").write_text(json.dumps(doc), encoding="utf-8")
    (folder / "excluded.json").write_text(json.dumps(excluded), encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("\n".join([f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
                              f'catalogs: "{(tmp_path / "cat").as_posix()}"']) + "\n", encoding="utf-8")
    capsys.readouterr()
    code = main(["--config", str(cfg), "weapons", "validate", "--directory", str(folder / "directory.json")])
    return code, json.loads(capsys.readouterr().out)


# --- the good directory ---------------------------------------------------------------------------------------------


def test_ac61_the_eligible_hosts_of_the_fixture_are_what_the_variants_assume(built):
    d = built[0]
    assert (rec_of(d, RIFLE)["role"], rec_of(d, RIFLE)["kind"], rec_of(d, RIFLE)["hold_class"]) == ("whole", "ranged", "long_gun")
    assert rec_of(d, PISTOL)["hold_class"] == "one_hand" and rec_of(d, GRENADE)["hold_class"] == "thrown"
    assert rec_of(d, SWORD)["kind"] == "melee"


def test_ac61_the_good_directory_validates_with_exit_0(built, tmp_path, monkeypatch, capsys):
    code, out = validate_via_cli(tmp_path, monkeypatch, capsys, good_directory(built), built[1])
    assert code == 0 and out["ok"] is True and out["directory"] == "ok", out


# --- six hand-broken variants, each exit 6 --------------------------------------------------------------------------


def break_non_part(d):
    rec_of(d, RIFLE)["attachment"] = copy.deepcopy(rec_of(d, SCOPE)["attachment"])


def break_slot(d):
    rec_of(d, SCOPE)["attachment"]["slot"] = "scope"


def break_kind_of_other_slot(d):
    rec_of(d, SCOPE)["attachment"]["kind"] = "drum"


def break_anchor_without_footprint(d):
    rec_of(d, SCOPE)["attachment"]["footprint"] = None


def break_host_not_eligible(d):
    rec_of(d, SCOPE)["attachment"]["compatible_hosts"] = [
        {"host": GRENADE, "tier": "twin", "score": 0.9, "signals": [], "replaces": []}]


def break_pending_as_bare_ids(d):
    rec_of(d, SCOPE)["attachment"]["pending_hosts"] = [PISTOL]


VARIANTS = {
    "attachment_on_a_non_part": (break_non_part, "non-null only for role part"),
    "unknown_slot": (break_slot, "slot"),
    "kind_of_another_slot": (break_kind_of_other_slot, "is not a kind of slot optic"),
    "anchor_without_footprint": (break_anchor_without_footprint, "null together"),
    "ineligible_host": (break_host_not_eligible, "not an eligible host"),
    "pending_hosts_as_bare_ids": (break_pending_as_bare_ids, "attachment"),  # a schema error, quoted as the block
}


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_ac61_each_hand_broken_variant_exits_6_with_its_own_message(name, built, tmp_path, monkeypatch, capsys):
    mutate, message = VARIANTS[name]
    doc = good_directory(built)
    mutate(doc)
    code, out = validate_via_cli(tmp_path, monkeypatch, capsys, doc, built[1])
    assert code == 6 and out["ok"] is False and out["directory"] == "invalid", out
    assert any(message in e for e in out["directory_errors"]), out["directory_errors"]


def test_ac61_a_host_that_is_not_in_the_directory_exits_6(built, tmp_path, monkeypatch, capsys):
    doc = good_directory(built)
    rec_of(doc, SCOPE)["attachment"]["compatible_hosts"] = [
        {"host": f"{A.PACK}/SM_Wep_Nowhere_01", "tier": "twin", "score": 0.9, "signals": [], "replaces": []}]
    code, out = validate_via_cli(tmp_path, monkeypatch, capsys, doc, built[1])
    assert code == 6 and any("is not in the directory" in e for e in out["directory_errors"])


def test_ac61_a_bad_tier_or_a_melee_host_exits_6(built, tmp_path, monkeypatch, capsys):
    doc = good_directory(built)
    rec_of(doc, SCOPE)["attachment"]["pending_hosts"] = [{"host": PISTOL, "tier": "maybe"}]
    assert validate_via_cli(tmp_path, monkeypatch, capsys, doc, built[1])[0] == 6
    doc = good_directory(built)
    rec_of(doc, SCOPE)["attachment"]["pending_hosts"] = [{"host": SWORD, "tier": "twin"}]
    code, out = validate_via_cli(tmp_path, monkeypatch, capsys, doc, built[1])
    assert code == 6 and any("not an eligible host" in e for e in out["directory_errors"])


# --- the cross-field rules at record level -------------------------------------------------------------------------


def attachment_of(built, rid):
    return copy.deepcopy(rec_of(built[0], rid))


def test_ac61_the_built_part_records_pass_the_record_check(built):
    for rec in built[0]["weapons"]:
        assert validate_record(rec) == [], rec["id"]


def test_ac61_an_attachment_on_a_whole_record_is_refused_at_record_level(built):
    rec = attachment_of(built, RIFLE)
    rec["attachment"] = copy.deepcopy(rec_of(built[0], SCOPE)["attachment"])
    assert any("non-null only for role part" in e for e in check_record(rec, "r"))


def test_ac61_a_null_attachment_on_a_part_and_a_missing_key_on_a_whole_are_both_valid(built):
    assert validate_record(attachment_of(built, f"{A.PACK}/SM_Wep_Mod_Rail_01")) == []
    rec = attachment_of(built, f"{A.PACK}/SM_Wep_Mod_Rail_01")
    assert rec["attachment"] is None
    assert "attachment" not in rec_of(built[0], RIFLE)
    assert validate_record(attachment_of(built, RIFLE)) == []


def test_ac61_a_frame_that_is_not_unit_or_not_orthogonal_is_refused(built):
    rec = attachment_of(built, SCOPE)
    rec["attachment"]["anchor"]["up"] = [0.0, 2.0, 0.0]
    assert any("not a unit vector" in e for e in check_record(rec, "r"))
    rec = attachment_of(built, SCOPE)
    rec["attachment"]["anchor"]["forward"] = [0.0, 0.7071, 0.7071]
    assert any("not orthogonal" in e for e in check_record(rec, "r"))
    rec = attachment_of(built, SCOPE)
    rec["attachment"]["anchor"]["forward"] = [0.0, 0.0, 1.0004]  # inside the 1e-3 tolerance
    assert check_record(rec, "r") == []


def test_ac61_mate_d_is_set_exactly_for_the_muzzle_slot(built):
    rec = attachment_of(built, SILENCER)
    assert rec["attachment"]["footprint"]["mate_d_m"] is not None and check_record(rec, "r") == []
    rec["attachment"]["footprint"]["mate_d_m"] = None
    assert any("mate_d_m" in e for e in check_record(rec, "r"))
    rec = attachment_of(built, SCOPE)
    rec["attachment"]["footprint"]["mate_d_m"] = 0.02
    assert any("mate_d_m" in e for e in check_record(rec, "r"))


def test_ac61_compatible_hosts_must_be_sorted_by_tier_then_score_then_host(built):
    rec = attachment_of(built, SCOPE)
    a = {"host": RIFLE, "tier": "twin", "score": 0.95, "signals": [], "replaces": []}
    b = {"host": PISTOL, "tier": "same_pack_fit", "score": 0.7, "signals": [], "replaces": []}
    rec["attachment"]["compatible_hosts"] = [a, b]
    assert check_record(rec, "r") == []
    rec["attachment"]["compatible_hosts"] = [b, a]
    assert any("sorted" in e for e in check_record(rec, "r"))
    c = dict(a, host=GRENADE.replace("Grenade_Frag", "Aaa"))
    rec["attachment"]["compatible_hosts"] = [a, c]  # same tier and score: host order decides
    assert any("sorted" in e for e in check_record(rec, "r"))


def test_ac61_validate_directory_reports_the_same_errors_as_the_cli(built):
    doc = good_directory(built)
    assert validate_directory(doc, built[1]) == []
    break_kind_of_other_slot(doc)
    assert any("is not a kind of slot optic" in e for e in validate_directory(doc, built[1]))


def test_a_w7_directory_without_the_attachment_header_still_validates(built):
    doc = copy.deepcopy(built[0])
    for key in ("attach_version", "attach_rules_digest"):
        doc.pop(key)
    for rec in doc["weapons"]:
        rec.pop("attachment", None)
    assert validate_directory(doc, built[1]) == []
