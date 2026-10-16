"""Weapon directory W4: ``apply-corrections`` (docs/weapon_directory.md section 3.9, 4.5).

Covers AC21, AC22, the corrections half of AC33 and INV-10 / INV-13. Every run is aimed at a tmp overrides file
(``ovr.default_overrides_path`` is patched), so the committed ``data/weapon_overrides.json`` is never touched.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_helpers", Path(__file__).parent / "fixtures" / "weapons" / "review_helpers.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
wfx = H.wfx

from synty_inventory.weapons import corrections as C  # noqa: E402
from synty_inventory.weapons import overrides as ovr  # noqa: E402

OLD = "FAKE_Fantasy/SM_Wep_Sword_02_old"
SHIELD_02 = H.SHIELD_SET[1]
SHIELD_GLOB = "FAKE_Review/SM_Wep_Shield_Set_*"
EXCLUDE_ID = H.KNIFE_SET[2]
CONFIRM_ID = H.KNIFE_SET[3]


def corr(*items) -> dict:
    return {"schema": "weapon-corrections/1", "corrections": list(items)}


class Env:
    """One tmp world: built fixture directory on disk, a config, a tmp overrides file and a corrections file."""

    def __init__(self, tmp_path, monkeypatch, capsys):
        for key in H.ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        self.tmp, self.capsys = tmp_path, capsys
        self.cat = H.make_catalogs(tmp_path)
        H.build_and_write(self.cat)
        self.cfg = H.write_config(tmp_path, self.cat)
        self.ovr_path = tmp_path / "weapon_overrides.json"
        self.ovr_path.write_text(json.dumps(wfx.overrides_doc()), encoding="utf-8")
        monkeypatch.setattr(ovr, "default_overrides_path", lambda: self.ovr_path)
        self.n = 0

    def apply(self, doc, *extra):
        self.n += 1
        path = self.tmp / f"corrections_{self.n}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return H.run(self.cfg, self.capsys, ["weapons", "apply-corrections", str(path), *extra])

    def bytes(self) -> bytes:
        return self.ovr_path.read_bytes()

    def table(self) -> dict:
        return json.loads(self.ovr_path.read_text(encoding="utf-8"))

    def rebuild(self):
        directory, excluded = H.build(self.cat, overrides=ovr.load_overrides(self.ovr_path), measure=False)
        return wfx.records_by_id(directory), {e["id"]: e for e in excluded["excluded"]}


@pytest.fixture()
def env(tmp_path, monkeypatch, capsys):
    return Env(tmp_path, monkeypatch, capsys)


AC21_FILE = corr(
    {"target": {"id": H.SWORD_REVIEW}, "set": {"archetype": "mace", "hold_class": "melee_bat"}, "note": "was a sword",
     "renamed_from": ["FAKE_Review/SM_Wep_Sword_Review_00"]},
    {"target": {"glob": SHIELD_GLOB}, "set": {"genre": "scifi"}},
    {"target": {"id": SHIELD_02}, "set": {"genre": "modern"}},  # an exact id beats the glob that also matches it
    {"target": {"id": EXCLUDE_ID}, "exclude": True},
    {"target": {"id": CONFIRM_ID}, "confirm": True},
)


# --- AC21 ---------------------------------------------------------------------------------------------------

def test_ac21_apply_then_rebuild_gives_the_corrected_directory(env):
    base, _ = env.rebuild()
    code, out = env.apply(AC21_FILE)
    assert code == 0 and out["ok"] is True and out["wrote"] is True
    recs, excluded = env.rebuild()

    sword = recs[H.SWORD_REVIEW]
    assert sword["archetype"] == "mace" and sword["hold_class"] == "melee_bat"
    assert sword["review"]["status"] == "overridden"
    assert sword["provenance"]["archetype"] == "override"
    assert base[H.SWORD_REVIEW]["archetype"] == "sword"
    assert sword["renamed_from"] == ["FAKE_Review/SM_Wep_Sword_Review_00"]

    for rid in H.SHIELD_SET:
        assert base[rid]["genre"] == "fantasy"  # before: from the pack's setting
        assert recs[rid]["genre"] == ("modern" if rid == SHIELD_02 else "scifi"), rid  # id > glob
        assert recs[rid]["review"]["status"] == "overridden"

    assert EXCLUDE_ID not in recs
    assert excluded[EXCLUDE_ID]["reason"] == "override"

    confirmed = recs[CONFIRM_ID]
    assert confirmed["review"]["status"] == "reviewed"
    for field in ("archetype", "kind", "role", "hold_class", "genre", "family"):
        assert confirmed[field] == base[CONFIRM_ID][field]
    # an untouched sibling stays automatic
    assert recs[H.KNIFE_SET[4]]["review"]["status"] == "auto"


def test_ac21_applying_the_same_file_twice_leaves_the_overrides_byte_identical(env):
    assert env.apply(AC21_FILE)[0] == 0
    first = env.bytes()
    code, out = env.apply(AC21_FILE)
    assert code == 0
    assert out["changed"] is False and out["wrote"] is False and out["diff"] == []
    assert env.bytes() == first


def test_ac21_the_file_is_written_in_canonical_form(env):
    env.apply(AC21_FILE)
    raw = env.bytes()
    assert b"\r" not in raw and raw.endswith(b"}\n")
    text = raw.decode("utf-8")
    assert text == json.dumps(json.loads(text), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert text.startswith('{\n  "globs": {')  # sorted keys, 2-space indent
    table = env.table()
    assert table["ids"][H.SWORD_REVIEW]["set"] == {"archetype": "mace", "hold_class": "melee_bat"}
    assert table["ids"][EXCLUDE_ID] == {"exclude": True}
    assert table["ids"][CONFIRM_ID] == {"confirm": True}
    assert table["globs"][SHIELD_GLOB] == {"set": {"genre": "scifi"}}


def test_a_later_correction_for_the_same_target_replaces_the_earlier(env):
    env.apply(corr({"target": {"id": H.SWORD_REVIEW}, "set": {"archetype": "mace"}, "note": "first"}))
    env.apply(corr({"target": {"id": H.SWORD_REVIEW}, "set": {"genre": "scifi"}}))
    assert env.table()["ids"][H.SWORD_REVIEW] == {"set": {"genre": "scifi"}}  # replaced, not merged
    # ... also inside one file, last one wins
    env.apply(corr({"target": {"id": H.SWORD_REVIEW}, "exclude": True},
                   {"target": {"id": H.SWORD_REVIEW}, "confirm": True}))
    assert env.table()["ids"][H.SWORD_REVIEW] == {"confirm": True}


def test_restore_is_a_confirm_that_replaces_an_earlier_exclude(env):
    env.apply(corr({"target": {"id": EXCLUDE_ID}, "exclude": True}))
    recs, excluded = env.rebuild()
    assert EXCLUDE_ID not in recs and excluded[EXCLUDE_ID]["reason"] == "override"
    env.apply(corr({"target": {"id": EXCLUDE_ID}, "confirm": True}))
    recs, excluded = env.rebuild()
    assert EXCLUDE_ID in recs and EXCLUDE_ID not in excluded
    assert recs[EXCLUDE_ID]["review"]["status"] == "reviewed"


def test_restore_re_admits_a_name_pattern_rejection(env):
    _, excluded = env.rebuild()
    trap = next(i for i, e in excluded.items() if e["reason"] == "scenery" and e["source"] == "name_token")
    env.apply(corr({"target": {"id": trap}, "confirm": True}))
    recs, excluded = env.rebuild()
    assert trap in recs and trap not in excluded


def test_dry_run_prints_the_diff_and_writes_nothing(env):
    before = env.bytes()
    code, out = env.apply(AC21_FILE, "--dry-run")
    assert code == 0 and out["dry_run"] is True and out["wrote"] is False
    assert env.bytes() == before
    keys = {(r["section"], r["key"]) for r in out["diff"]}
    assert ("ids", H.SWORD_REVIEW) in keys and ("globs", SHIELD_GLOB) in keys and len(out["diff"]) == 5
    assert all(r["change"] == "added" and r["before"] is None for r in out["diff"])


def test_glob_conflict_of_equal_length_exits_6_naming_both(env):
    code, out = env.apply(corr(
        {"target": {"glob": "FAKE_Review/SM_Wep_Shield_Set_0*"}, "set": {"genre": "scifi"}},
        {"target": {"glob": "FAKE_Review/SM_Wep_Shield_Set_?1"}, "set": {"genre": "modern"}},
    ))
    assert code == 6 and out["ok"] is False
    assert "SM_Wep_Shield_Set_0*" in out["error"] and "SM_Wep_Shield_Set_?1" in out["error"]
    assert env.table() == wfx.overrides_doc()


# --- AC22 ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {"target": {"id": H.SWORD_REVIEW}, "set": {"archetype": "laser_pistol"}},
    {"target": {"id": H.SWORD_REVIEW}, "set": {"genre": "steampunk"}},
    {"target": {"id": H.SWORD_REVIEW}, "set": {"hold_class": "two_hand"}},
    {"target": {"id": H.SWORD_REVIEW}, "set": {"role": "gizmo"}},
    {"target": {"id": H.SWORD_REVIEW}, "set": {"kind": None}},
    {"target": {"id": H.SWORD_REVIEW}, "set": {"damage": 12}},
    {"target": {"id": H.SWORD_REVIEW}, "set": {"role": "carrier"}},  # a carrier needs its kind in the same set
])
def test_ac22_an_unknown_enum_value_exits_6_and_changes_nothing(env, bad):
    good = {"target": {"id": H.SHIELD_SET[0]}, "set": {"genre": "fantasy"}}
    before = env.bytes()
    code, out = env.apply(corr(good, bad))  # the valid correction before it must not be applied either
    assert code == 6 and out["ok"] is False
    assert env.bytes() == before


def test_ac22_a_target_pack_that_is_not_cataloged_warns_and_is_stored(env):
    code, out = env.apply(corr({"target": {"id": "NO_SUCH_PACK/SM_Wep_X_01"}, "set": {"genre": "other"}},
                               {"target": {"glob": "ALSO_MISSING_*/SM_Wep_*"}, "confirm": True},
                               {"target": {"id": H.SWORD_REVIEW}, "confirm": True}))
    assert code == 0, out
    assert len(out["warnings"]) == 2
    assert any("NO_SUCH_PACK" in w for w in out["warnings"]) and any("ALSO_MISSING_" in w for w in out["warnings"])
    assert not any("FAKE_Review" in w for w in out["warnings"])
    table = env.table()
    assert table["ids"]["NO_SUCH_PACK/SM_Wep_X_01"] == {"set": {"genre": "other"}}
    assert table["globs"]["ALSO_MISSING_*/SM_Wep_*"] == {"confirm": True}


@pytest.mark.parametrize("doc", [
    {"schema": "weapon-corrections/2", "corrections": []},
    {"schema": "weapon-corrections/1"},
    {"schema": "weapon-corrections/1", "corrections": {}},
    corr({"target": {"id": "no_slash"}, "confirm": True}),
    corr({"target": {"id": H.SWORD_REVIEW, "glob": "a/b*"}, "confirm": True}),
    corr({"target": {}, "confirm": True}),
    corr({"target": {"id": H.SWORD_REVIEW}}),  # no action
    corr({"target": {"id": H.SWORD_REVIEW}, "note": "just a note"}),
    corr({"target": {"id": H.SWORD_REVIEW}, "confirm": "yes"}),
    corr({"target": {"id": H.SWORD_REVIEW}, "exclude": True, "confirm": True}),
    corr({"target": {"id": H.SWORD_REVIEW}, "confirm": True, "price": 3}),
    corr({"target": {"glob": SHIELD_GLOB}, "renamed_from": [OLD]}),  # renamed_from needs an exact id
    corr({"target": {"id": H.SWORD_REVIEW}, "renamed_from": ["not an id"]}),
    corr({"target": {"id": H.SWORD_REVIEW}, "renamed_from": [H.SWORD_REVIEW]}),
    corr("not an object"),
])
def test_malformed_corrections_exit_6_and_write_nothing(env, doc):
    before = env.bytes()
    code, out = env.apply(doc)
    assert code == 6 and out["ok"] is False
    assert env.bytes() == before


def test_unreadable_or_missing_input_exits_2(env):
    capsys = env.capsys
    code, out = H.run(env.cfg, capsys, ["weapons", "apply-corrections", str(env.tmp / "nope.json")])
    assert code == 2 and out["ok"] is False
    bad = env.tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code, out = H.run(env.cfg, capsys, ["weapons", "apply-corrections", str(bad)])
    assert code == 2 and out["ok"] is False


# --- AC33 (corrections half) and INV-13 ---------------------------------------------------------------------

def test_ac33_renamed_from_is_stored_sorted_deduplicated_and_idempotent(env):
    older = "FAKE_Fantasy/SM_Wep_Sword_02_older"
    file1 = corr({"target": {"id": H.SWORD_02}, "renamed_from": [OLD]})
    assert env.apply(file1)[0] == 0
    first = env.bytes()
    assert env.table()["ids"][H.SWORD_02] == {"renamed_from": [OLD]}
    assert env.apply(file1)[0] == 0
    assert env.bytes() == first  # applying the same renamed-target correction twice: byte-identical
    assert env.apply(corr({"target": {"id": H.SWORD_02}, "renamed_from": [OLD, older, older]}))[0] == 0
    assert env.table()["ids"][H.SWORD_02]["renamed_from"] == sorted([OLD, older])


def test_ac33_the_rename_reaches_the_rebuilt_record(env):
    env.apply(corr({"target": {"id": H.SWORD_02}, "renamed_from": [OLD]}))
    recs, _ = env.rebuild()
    assert recs[H.SWORD_02]["renamed_from"] == [OLD]
    assert recs[H.SWORD_02]["review"]["status"] == "auto"  # a rename-only entry changes no classification
    assert recs[H.SWORD_01]["renamed_from"] == []


def test_ac33_renamed_from_and_set_do_not_wipe_each_other(env):
    env.apply(corr({"target": {"id": H.SWORD_02}, "set": {"genre": "scifi"}, "note": "n"}))
    env.apply(corr({"target": {"id": H.SWORD_02}, "renamed_from": [OLD]}))
    assert env.table()["ids"][H.SWORD_02] == {"set": {"genre": "scifi"}, "note": "n", "renamed_from": [OLD]}
    env.apply(corr({"target": {"id": H.SWORD_02}, "confirm": True}))  # a later classification keeps the rename
    assert env.table()["ids"][H.SWORD_02] == {"confirm": True, "renamed_from": [OLD]}


def test_w2e_a_later_correction_keeps_forward_and_confidence_cap_on_the_entry(env):
    # the two fields are written by hand (a correction cannot create them) and must survive every merge
    env.ovr_path.write_text(json.dumps(wfx.overrides_doc(ids={
        H.SWORD_02: {"set": {"genre": "scifi"}, "forward": "-y", "confidence_cap": 0.55, "note": "old"}})),
        encoding="utf-8")
    code, _ = env.apply(corr({"target": {"id": H.SWORD_02}, "set": {"genre": "modern"}, "note": "new"}))
    assert code == 0
    assert env.table()["ids"][H.SWORD_02] == {"set": {"genre": "modern"}, "note": "new", "forward": "-y",
                                              "confidence_cap": 0.55}
    code, _ = env.apply(corr({"target": {"id": H.SWORD_02}, "confirm": True}))
    assert code == 0
    assert env.table()["ids"][H.SWORD_02] == {"confirm": True, "forward": "-y", "confidence_cap": 0.55}
    code, _ = env.apply(corr({"target": {"id": H.SWORD_02}, "renamed_from": [OLD]}))  # the renamed_from-only branch
    assert code == 0
    assert env.table()["ids"][H.SWORD_02] == {"confirm": True, "forward": "-y", "confidence_cap": 0.55,
                                              "renamed_from": [OLD]}


def test_w2e_a_correction_file_cannot_carry_forward_or_confidence_cap(env):
    before = env.bytes()
    code, out = env.apply(corr({"target": {"id": H.SWORD_02}, "set": {"genre": "scifi"}, "forward": "+z"}))
    assert code == 6 and "forward" in out["error"] and env.bytes() == before


def test_ac33_renamed_from_equal_to_a_live_record_id_exits_6_and_writes_nothing(env):
    before = env.bytes()
    code, out = env.apply(corr({"target": {"id": H.SWORD_02}, "renamed_from": [H.SWORD_01]}))
    assert code == 6 and out["ok"] is False
    assert H.SWORD_01 in out["error"] and "live" in out["error"]
    assert env.bytes() == before


def test_an_old_id_claimed_by_two_records_exits_6(env):
    env.apply(corr({"target": {"id": H.SWORD_02}, "renamed_from": [OLD]}))
    before = env.bytes()
    code, out = env.apply(corr({"target": {"id": H.SWORD_01}, "renamed_from": [OLD]}))
    assert code == 6 and "claimed by both" in out["error"]
    assert H.SWORD_01 in out["error"] and H.SWORD_02 in out["error"]
    assert env.bytes() == before


def test_a_rename_without_a_built_directory_cannot_be_checked_and_exits_2(env):
    import shutil

    shutil.rmtree(env.cat / "weapons")
    before = env.bytes()
    code, out = env.apply(corr({"target": {"id": H.SWORD_02}, "renamed_from": [OLD]}))
    assert code == 2 and "weapons build" in out["error"]
    assert env.bytes() == before
    # everything else goes through, with a warning that the pack check was skipped
    code, out = env.apply(corr({"target": {"id": H.SWORD_02}, "confirm": True}))
    assert code == 0 and len(out["warnings"]) == 1


# --- the library surface ------------------------------------------------------------------------------------

def test_apply_corrections_is_pure_and_returns_warnings():
    start = wfx.overrides_doc(ids={H.SWORD_02: {"confirm": True}})
    snapshot = json.dumps(start, sort_keys=True)
    new, warnings = C.apply_corrections(
        corr({"target": {"id": H.SWORD_02}, "set": {"genre": "scifi"}}), start, known_packs={"FAKE_Fantasy"})
    assert json.dumps(start, sort_keys=True) == snapshot  # the input table is not modified
    assert new["ids"][H.SWORD_02] == {"set": {"genre": "scifi"}} and warnings == []
    again, _ = C.apply_corrections(corr({"target": {"id": H.SWORD_02}, "set": {"genre": "scifi"}}), new)
    assert again == new


def test_the_committed_overrides_file_is_not_touched_by_these_tests():
    real = Path(__file__).resolve().parents[1] / "src" / "synty_inventory" / "data" / "weapon_overrides.json"
    assert json.loads(real.read_text(encoding="utf-8")) == wfx.overrides_doc()
