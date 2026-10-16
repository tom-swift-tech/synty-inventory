"""Weapon directory W1: overrides precedence, validation and the build half of AC33.

Overrides live in ``weapon_overrides.json`` (``weapon-overrides/1``). Precedence per field: exact id, then the
longest matching glob, then the rules. Fixtures are synthetic; every expected value is a literal.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("wfx", Path(__file__).parent / "fixtures" / "weapons" / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)

from synty_inventory.cli import main  # noqa: E402
from synty_inventory.weapons import InputError, SchemaError  # noqa: E402
from synty_inventory.weapons import overrides as ovr  # noqa: E402
from synty_inventory.weapons.directory import build_directory, build_directory_report  # noqa: E402

SWORD_02 = "FAKE_Fantasy/SM_Wep_Sword_02"
SWORD_01 = "FAKE_Fantasy/SM_Wep_Sword_01"
AXE_01 = "FAKE_Fantasy/SM_Wep_Axe_01"
WHIP_01 = "FAKE_Fantasy/SM_Wep_Whip_01"
PICKAXE_PROP = "FAKE_Modern/SM_Prop_Pickaxe_01"
BARREL_PROP = "FAKE_Modern/SM_Prop_Barrel_01"
FINGERGUN = "FAKE_Generic/A_Emote_FingerGun_01"


@pytest.fixture()
def cdir(tmp_path):
    return wfx.make_catalogs_dir(tmp_path)


def _build(cdir, ids=None, globs=None, **kw):
    return build_directory_report(cdir, overrides=wfx.overrides_doc(ids, globs), pack_settings=wfx.pack_settings(), **kw)


def _recs(directory):
    return wfx.records_by_id(directory)


# --- precedence --------------------------------------------------------------------------------------------

def test_exact_id_set_overrides_the_rules(cdir):
    directory, _, _ = _build(cdir, ids={SWORD_02: {"set": {"archetype": "axe", "genre": "other"}}})
    rec = _recs(directory)[SWORD_02]
    assert (rec["archetype"], rec["kind"], rec["genre"], rec["genre_source"]) == ("axe", "melee", "other", "override")
    assert rec["review"]["status"] == "overridden"
    assert rec["review"]["confidence"] == 1.0
    assert rec["provenance"]["archetype"] == "override" and rec["provenance"]["genre"] == "override"
    assert rec["hold_class"] == "melee_one"  # re-derived from the overridden archetype
    # a neighbour with no entry is untouched
    other = _recs(directory)[SWORD_01]
    assert (other["archetype"], other["review"]["status"], other["genre_source"]) == ("sword", "auto", "pack")


def test_exact_id_beats_every_glob(cdir):
    directory, _, _ = _build(
        cdir,
        ids={SWORD_02: {"set": {"genre": "other"}}},
        globs={"FAKE_Fantasy/SM_Wep_Sword_*": {"set": {"genre": "western"}}, "FAKE_Fantasy/*": {"set": {"genre": "scifi"}}},
    )
    recs = _recs(directory)
    assert recs[SWORD_02]["genre"] == "other"
    assert recs[SWORD_01]["genre"] == "western"  # longest glob
    assert recs[AXE_01]["genre"] == "scifi"  # only the short glob matches
    assert recs["FAKE_Modern/SM_Wep_Pistol_01"]["genre"] == "modern"  # no override at all


def test_globs_merge_per_field_longest_wins_each_field(cdir):
    directory, _, _ = _build(
        cdir,
        globs={
            "FAKE_Fantasy/SM_Wep_Sword_*": {"set": {"genre": "western"}},
            "FAKE_Fantasy/*": {"set": {"genre": "scifi", "hold_class": "melee_two"}},
        },
    )
    rec = _recs(directory)[SWORD_01]
    assert rec["genre"] == "western"  # longer glob decides genre
    assert rec["hold_class"] == "melee_two"  # shorter glob still supplies the field the longer one leaves alone


def test_equal_length_conflicting_globs_are_an_error(cdir):
    globs = {
        "FAKE_Fantasy/SM_Wep_Sword_0*": {"set": {"genre": "western"}},
        "FAKE_Fantasy/SM_Wep_Sword_*1": {"set": {"genre": "scifi"}},
    }
    assert len("FAKE_Fantasy/SM_Wep_Sword_0*") == len("FAKE_Fantasy/SM_Wep_Sword_*1")
    with pytest.raises(SchemaError) as exc:
        ovr.effective_override(SWORD_01, wfx.overrides_doc(globs=globs))
    assert exc.value.code == 6
    assert "SM_Wep_Sword_0*" in str(exc.value) and "SM_Wep_Sword_*1" in str(exc.value)
    with pytest.raises(SchemaError):
        _build(cdir, globs=globs)
    # equal-length globs that agree are fine, and so is a conflict an exact id settles
    agree = {k: {"set": {"genre": "western"}} for k in globs}
    assert ovr.effective_override(SWORD_01, wfx.overrides_doc(globs=agree))["set"] == {"genre": "western"}
    ids = {SWORD_01: {"set": {"genre": "other"}}}
    assert ovr.effective_override(SWORD_01, wfx.overrides_doc(ids=ids, globs=globs))["set"] == {"genre": "other"}


def test_effective_override_none_when_nothing_applies():
    assert ovr.effective_override(SWORD_01, None) is None
    assert ovr.effective_override(SWORD_01, wfx.overrides_doc()) is None
    assert ovr.effective_override(SWORD_01, wfx.overrides_doc(globs={"FAKE_Modern/*": {"confirm": True}})) is None


# --- confirm / exclude / restore / admit -------------------------------------------------------------------

def test_confirm_marks_reviewed_and_keeps_the_classification(cdir):
    base, _, _ = _build(cdir)
    directory, _, _ = _build(cdir, ids={"FAKE_Fantasy/SM_Wep_Mace_01": {"confirm": True}})
    rec, before = _recs(directory)["FAKE_Fantasy/SM_Wep_Mace_01"], _recs(base)["FAKE_Fantasy/SM_Wep_Mace_01"]
    assert rec["review"]["status"] == "reviewed"
    assert rec["review"]["confidence"] == 1.0
    for key in ("archetype", "kind", "role", "hold_class", "genre"):
        assert rec[key] == before[key]


def test_exclude_by_id_and_by_glob_lands_in_excluded_with_reason_override(cdir):
    directory, excluded, _ = _build(
        cdir, ids={WHIP_01: {"exclude": True}}, globs={"FAKE_Fantasy/SM_Wep_Wand_*": {"exclude": True}},
    )
    recs = _recs(directory)
    rows = {e["id"]: e for e in excluded["excluded"]}
    for gone, by in ((WHIP_01, WHIP_01), ("FAKE_Fantasy/SM_Wep_Wand_01", "FAKE_Fantasy/SM_Wep_Wand_*"),
                     ("FAKE_Fantasy/SM_Wep_Wand_02", "FAKE_Fantasy/SM_Wep_Wand_*")):
        assert gone not in recs
        assert rows[gone]["reason"] == "override"
        assert rows[gone]["matched"] == f"override:{by}"
    pack = next(p for p in directory["packs"] if p["pack"] == "FAKE_Fantasy")
    assert pack["candidates"] == pack["records"] + pack["excluded"]  # INV-3 still holds


def test_exact_id_confirm_restores_a_pattern_rejected_asset(cdir):
    _, excluded, _ = _build(cdir)
    assert PICKAXE_PROP in {e["id"] for e in excluded["excluded"]}
    directory, excluded, _ = _build(cdir, ids={PICKAXE_PROP: {"confirm": True}})
    assert PICKAXE_PROP not in {e["id"] for e in excluded["excluded"]}
    rec = _recs(directory)[PICKAXE_PROP]
    assert rec["review"]["status"] == "reviewed"
    assert rec["review"]["candidate_source"] == "name_token"


def test_a_glob_cannot_restore_but_an_id_override_is_not_needed_for_plain_sets(cdir):
    directory, excluded, _ = _build(cdir, globs={"FAKE_Modern/SM_Prop_Pickaxe_*": {"confirm": True}})
    assert PICKAXE_PROP in {e["id"] for e in excluded["excluded"]}  # restore is exact-id only
    assert PICKAXE_PROP not in _recs(directory)


def test_nonplaceable_assets_stay_excluded_even_with_an_override(cdir):
    directory, excluded, _ = _build(cdir, ids={FINGERGUN: {"confirm": True}})
    rows = {e["id"]: e for e in excluded["excluded"]}
    assert rows[FINGERGUN]["reason"] == "nonplaceable"
    assert FINGERGUN not in _recs(directory)


def test_exact_id_set_admits_an_asset_the_patterns_missed(cdir):
    directory, excluded, _ = _build(cdir)
    assert BARREL_PROP not in _recs(directory)
    assert BARREL_PROP not in {e["id"] for e in excluded["excluded"]}
    directory, excluded, _ = _build(cdir, ids={BARREL_PROP: {"set": {"role": "whole", "archetype": "bomb"}}})
    rec = _recs(directory)[BARREL_PROP]
    assert (rec["role"], rec["kind"], rec["archetype"], rec["hold_class"]) == ("whole", "thrown", "bomb", "thrown")
    assert rec["review"]["status"] == "overridden"
    assert BARREL_PROP not in {e["id"] for e in excluded["excluded"]}


def test_overrides_change_the_overrides_digest_only(cdir):
    plain, _ = build_directory(cdir, overrides=wfx.overrides_doc(), pack_settings=wfx.pack_settings())
    changed, _ = build_directory(cdir, overrides=wfx.overrides_doc(ids={WHIP_01: {"confirm": True}}),
                                 pack_settings=wfx.pack_settings())
    assert plain["overrides_digest"] != changed["overrides_digest"]
    assert plain["rules_digest"] == changed["rules_digest"]
    assert len(plain["weapons"]) == len(changed["weapons"])


# --- AC33 (build half) -------------------------------------------------------------------------------------

OLD = "FAKE_Fantasy/SM_Wep_Sword_02_old"


def test_ac33_renamed_from_is_carried_onto_the_record(cdir):
    directory, _, _ = _build(cdir, ids={SWORD_02: {"renamed_from": [OLD]}})
    recs = _recs(directory)
    assert recs[SWORD_02]["renamed_from"] == [OLD]
    for rid, rec in recs.items():
        if rid != SWORD_02:
            assert rec["renamed_from"] == []


def test_ac33_no_entry_gives_an_empty_list_and_the_list_is_sorted_and_deduped(cdir):
    plain, _, _ = _build(cdir)
    assert all(r["renamed_from"] == [] for r in plain["weapons"])
    multi, _, _ = _build(cdir, ids={SWORD_02: {"renamed_from": ["FAKE_Fantasy/b_old", "FAKE_Fantasy/a_old", "FAKE_Fantasy/b_old"]}})
    assert _recs(multi)[SWORD_02]["renamed_from"] == ["FAKE_Fantasy/a_old", "FAKE_Fantasy/b_old"]


def test_ac33_a_renamed_id_equal_to_a_live_id_is_a_schema_error(cdir):
    with pytest.raises(SchemaError) as exc:
        _build(cdir, ids={SWORD_02: {"renamed_from": [SWORD_01]}})
    assert exc.value.code == 6
    assert SWORD_01 in str(exc.value)


def test_a_renamed_id_claimed_by_two_records_is_a_schema_error(cdir):
    with pytest.raises(SchemaError):
        _build(cdir, ids={SWORD_02: {"renamed_from": [OLD]}, SWORD_01: {"renamed_from": [OLD]}})


def _cli(tmp_path, monkeypatch, capsys, argv, overrides_doc=None):
    """Run ``synty-inventory --config <cfg> <argv>`` against the fixture catalogs; returns (code, parsed stdout)."""
    for key in ("SYNTI_CONFIG", "SYNTI_CATALOGS"):
        monkeypatch.delenv(key, raising=False)
    cat = wfx.make_catalogs_dir(tmp_path)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "\n".join([f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
                   f'catalogs: "{cat.as_posix()}"']) + "\n", encoding="utf-8")
    if overrides_doc is not None:
        path = tmp_path / "overrides.json"
        path.write_text(json.dumps(overrides_doc), encoding="utf-8")
        monkeypatch.setattr(ovr, "default_overrides_path", lambda: path)
    capsys.readouterr()
    code = main(["--config", str(cfg), *argv])
    return code, json.loads(capsys.readouterr().out), cat


def test_ac33_cli_build_with_a_live_renamed_id_exits_6_and_writes_nothing(tmp_path, monkeypatch, capsys):
    doc = wfx.overrides_doc(ids={SWORD_02: {"renamed_from": [SWORD_01]}})
    code, out, cat = _cli(tmp_path, monkeypatch, capsys, ["weapons", "build"], doc)
    assert code == 6
    assert out["ok"] is False
    assert not (cat / "weapons").exists()


def test_ac33_cli_build_carries_renamed_from(tmp_path, monkeypatch, capsys):
    doc = wfx.overrides_doc(ids={SWORD_02: {"renamed_from": [OLD]}})
    code, out, cat = _cli(tmp_path, monkeypatch, capsys, ["weapons", "build"], doc)
    assert code == 0, out
    written = json.loads((cat / "weapons" / "directory.json").read_text(encoding="utf-8"))
    assert wfx.records_by_id(written)[SWORD_02]["renamed_from"] == [OLD]


# --- stale overrides / strict ------------------------------------------------------------------------------

STALE_DOC = wfx.overrides_doc(
    ids={"FAKE_Fantasy/Nope_01": {"confirm": True}, WHIP_01: {"confirm": True}},
    globs={"FAKE_Nope/*": {"exclude": True}, "FAKE_Fantasy/SM_Wep_Whip_*": {"set": {"genre": "other"}}},
)


def test_stale_overrides_are_reported_not_fatal(cdir):
    directory, _, report = _build(cdir, ids=STALE_DOC["ids"], globs=STALE_DOC["globs"])
    assert report["stale_overrides"] == [
        {"key": "FAKE_Fantasy/Nope_01", "kind": "id"},
        {"key": "FAKE_Nope/*", "kind": "glob"},
    ]
    assert len(directory["weapons"]) > 100


def test_strict_turns_stale_overrides_into_exit_3(tmp_path, monkeypatch, capsys):
    code, out, cat = _cli(tmp_path, monkeypatch, capsys, ["weapons", "build", "--strict"], STALE_DOC)
    assert code == 3
    assert out["ok"] is False
    assert any("stale" in n for n in out["notes"])
    code, out, _ = _cli(tmp_path / "again", monkeypatch, capsys, ["weapons", "build"], STALE_DOC)
    assert code == 0
    assert out["report"]["stale_overrides"]


# --- file validation ---------------------------------------------------------------------------------------

def test_committed_override_file_is_valid_and_empty():
    path = ovr.default_overrides_path()
    raw = path.read_bytes().replace(b"\r\n", b"\n")  # an autocrlf checkout holds CRLF
    assert raw.endswith(b"\n")
    doc = ovr.load_overrides()
    assert doc == {"schema": "weapon-overrides/1", "ids": {}, "globs": {}}


@pytest.mark.parametrize(
    "doc",
    [
        {"schema": "weapon-overrides/2", "ids": {}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {}, "globs": {}, "extra": 1},
        {"schema": "weapon-overrides/1", "ids": [], "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"no_slash": {"confirm": True}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B/C": {"confirm": True}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"set": {"archetype": "laser_sword"}}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"set": {"role": "whole", "mass_kg": 3}}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"set": {"genre": "steampunk"}}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confirm": "yes"}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"unknown": 1}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"set": {"role": "carrier"}}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"set": {"role": "ammo"}}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"renamed_from": ["A/B"]}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"renamed_from": ["nope"]}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {}, "globs": {"A/*": {"renamed_from": ["A/C"]}}},
        {"schema": "weapon-overrides/1", "ids": {}, "globs": {"A/*": {"note": 5}}},
        # W2e: forward / confidence_cap are id-only and strictly typed
        {"schema": "weapon-overrides/1", "ids": {}, "globs": {"A/*": {"forward": "+z"}}},
        {"schema": "weapon-overrides/1", "ids": {}, "globs": {"A/*": {"confidence_cap": 0.5}}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"forward": "z"}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"forward": "+w"}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"forward": "++z"}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"forward": None}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"forward": ["+z"]}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confidence_cap": 0.6}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confidence_cap": 0.7}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confidence_cap": 0.04}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confidence_cap": 0}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confidence_cap": True}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confidence_cap": "0.5"}}, "globs": {}},
        {"schema": "weapon-overrides/1", "ids": {"A/B": {"confidence_cap": None}}, "globs": {}},
    ],
)
def test_malformed_override_documents_are_rejected(doc, tmp_path):
    assert ovr.validate_overrides(doc)
    with pytest.raises(SchemaError) as exc:
        ovr.checked_overrides(doc)
    assert exc.value.code == 6
    path = tmp_path / "o.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SchemaError):
        ovr.load_overrides(path)


def test_wellformed_documents_pass():
    doc = wfx.overrides_doc(
        ids={
            "A/B": {"set": {"archetype": "sword", "genre": "fantasy", "hold_class": "melee_two", "kind": "melee"},
                    "confirm": True, "note": "ok", "renamed_from": ["A/C"]},
            "A/Q": {"set": {"role": "carrier", "carrier": "quiver"}},
            "A/R": {"set": {"role": "ammo", "ammo": {"projectile": "arrow"}}},
            "A/P": {"set": {"role": "part", "component": {"slot": "optic", "fits": ["rifle"]}}},
        },
        globs={"A/S_*": {"exclude": True}},
    )
    assert ovr.validate_overrides(doc) == []


def test_forward_and_confidence_cap_errors_name_the_key():
    def errors(**sections):
        return ovr.validate_overrides({"schema": "weapon-overrides/1", "ids": sections.get("ids", {}),
                                       "globs": sections.get("globs", {})})

    assert any("globs[A/*].forward" in e and "exact ids only" in e for e in errors(globs={"A/*": {"forward": "+z"}}))
    assert any("globs[A/*].confidence_cap" in e for e in errors(globs={"A/*": {"confidence_cap": 0.5}}))
    assert any("ids[A/B].forward" in e for e in errors(ids={"A/B": {"forward": "up"}}))
    assert any("ids[A/B].confidence_cap" in e for e in errors(ids={"A/B": {"confidence_cap": 0.6}}))
    assert any("ids[A/B].confidence_cap" in e for e in errors(ids={"A/B": {"confidence_cap": True}}))


def test_forward_and_confidence_cap_are_valid_on_ids_at_the_edges_and_alone():
    ids = {"A/B": {"forward": "-x"}, "A/C": {"confidence_cap": 0.05}, "A/D": {"confidence_cap": 0.59, "forward": "+y"},
           "A/E": {"confidence_cap": 1 / 2, "set": {"genre": "fantasy"}, "note": "n"}}
    for fwd in ("+x", "-x", "+y", "-y", "+z", "-z"):
        ids[f"A/F_{fwd}"] = {"forward": fwd}
    assert ovr.validate_overrides(wfx.overrides_doc(ids=ids)) == []


def test_effective_override_exposes_forward_and_cap_from_the_id_entry_only():
    doc = wfx.overrides_doc(ids={"A/B": {"forward": "-y", "confidence_cap": 0.4}, "A/C": {"note": "x"}},
                            globs={"A/*": {"note": "g"}})
    assert ovr.effective_override("A/B", doc)["forward"] == "-y"
    assert ovr.effective_override("A/B", doc)["confidence_cap"] == 0.4
    plain = ovr.effective_override("A/C", doc)  # id entry without them, and a glob that matches: None
    assert plain["forward"] is None and plain["confidence_cap"] is None
    only_glob = ovr.effective_override("A/Z", doc)
    assert only_glob["forward"] is None and only_glob["confidence_cap"] is None


def test_missing_or_unreadable_override_file_is_exit_2(tmp_path):
    with pytest.raises(InputError) as exc:
        ovr.load_overrides(tmp_path / "absent.json")
    assert exc.value.code == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(InputError):
        ovr.load_overrides(bad)


def test_cli_validate_exits_6_on_a_malformed_override_file(tmp_path, monkeypatch, capsys):
    doc = {"schema": "weapon-overrides/1", "ids": {"A/B": {"set": {"archetype": "laser_sword"}}}, "globs": {}}
    code, out, _ = _cli(tmp_path, monkeypatch, capsys, ["weapons", "validate"], doc)
    assert code == 6
    assert out["ok"] is False
    assert "laser_sword" in out["error"]
