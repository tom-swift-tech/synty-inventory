"""W8c overrides and corrections: AC74 (``compatible``, ``mounts``, ``set.attachment_*``), the mount-override reach into the
geometry cache, and the AC75 half "adding a measured mount by override moves the pending host".

docs/weapon_attachments.md 6. The overrides are ids, globs, node names and enums only (INV-17); every expectation is a literal
worked out by hand on the w8c_compat.py world (see its docstring and test_weapons_w8c_compat.py for the tier arithmetic).
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8c_compat", FIX / "w8c_compat.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
_spec2 = importlib.util.spec_from_file_location("review_helpers", FIX / "review_helpers.py")
H = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(H)

from synty_inventory.weapons import SchemaError, guards  # noqa: E402
from synty_inventory.weapons import overrides as ovr  # noqa: E402
from synty_inventory.weapons.corrections import apply_corrections, overrides_text, validate_corrections  # noqa: E402
from synty_inventory.weapons.directory import to_text  # noqa: E402
from synty_inventory.weapons.overrides import compatible_verdict, effective_override, empty_overrides, validate_overrides  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

A_, B_, G_, E_, D_ = (W.H[n] for n in (W.ALPHA, W.BETA, W.GAMMA, W.EPSILON, W.DELTA))
TWIN, SAME, CROSS, OVERRIDE = "twin", "same_pack_fit", "cross_pack_fit", "override"
AUX = "SM_Wep_Rifle_Beta_01_Aux"
P_SCOPE = W.P[W.SCOPE]
O = W.overrides_doc


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def run(tmp_path, overrides, **kw):
    """``(by id, report)`` of the fixture world built with ``overrides``."""
    directory, _, report, *_ = W.build_report(tmp_path, overrides=overrides, **kw)
    assert validate_directory(directory) == []
    return W.by_id(directory), report


def lists(recs, part):
    rec = recs[W.P[part]]
    return W.hosts_of(rec), [(e["host"], e["tier"]) for e in rec["attachment"]["pending_hosts"]]


# --- validation: ids, globs and enums only (INV-17) ---------------------------------------------------------------------


@pytest.mark.parametrize("extra", [{"point": [0, 0, 0]}, {"up": [0, 1, 0]}, {"span_m": 0.05}, {"offset": 0.01}, {"x": 1}])
def test_ac74_a_mounts_entry_with_any_key_but_source_and_child_is_rejected(extra):
    doc = O(ids={B_: {"mounts": {"optic": {"source": "child_node", "child": AUX, **extra}}}})
    errors = validate_overrides(doc)
    assert errors and any(next(iter(extra)) in e for e in errors), errors


def test_ac74_the_exact_same_entry_without_the_extra_key_is_accepted():
    assert validate_overrides(O(ids={B_: {"mounts": {"optic": {"source": "child_node", "child": AUX}}}})) == []
    assert validate_overrides(O(ids={B_: {"mounts": {"optic": {"source": "none"}, "magazine": {"source": "none"}}}})) == []


@pytest.mark.parametrize("mounts", [
    {"optic": {"source": "probe"}},  # not a selectable source
    {"optic": {"source": "child_node"}},  # needs the node name
    {"optic": {"source": "none", "child": AUX}},  # none takes no child
    {"scope": {"source": "none"}},  # not a slot
    {"optic": "child_node"}, {}, [],
])
def test_ac74_malformed_mounts_are_rejected(mounts):
    assert validate_overrides(O(ids={B_: {"mounts": mounts}}))


def test_ac74_mounts_belong_to_an_exact_id_and_not_to_a_glob():
    errors = validate_overrides(O(globs={"FAKE_CompA/SM_Wep_Rifle_*": {"mounts": {"optic": {"source": "none"}}}}))
    assert errors and any("exact ids only" in e for e in errors)


@pytest.mark.parametrize("compatible", [{"add": [3]}, {"add": "x/y"}, {"keep": ["P/a"]}, {}, {"add": ["no_slash"]}, ["P/a"]])
def test_ac74_malformed_compatible_blocks_are_rejected(compatible):
    assert validate_overrides(O(ids={P_SCOPE: {"compatible": compatible}}))



def test_ac74_a_compatible_block_is_allowed_on_a_glob_and_on_an_id():
    assert validate_overrides(O(globs={"FAKE_CompA/SM_Wep_Rifle_Scope_*": {"compatible": {"add": ["FAKE_CompA/SM_Wep_Pistol_*"]}}},
                                ids={P_SCOPE: {"compatible": {"remove": [A_]}}})) == []


@pytest.mark.parametrize("set_", [{"attachment_slot": "scope"}, {"attachment_kind": "bogus"},
                                  {"attachment_slot": "optic", "attachment_kind": "drum"}])
def test_ac74_attachment_set_values_are_enums(set_):
    assert validate_overrides(O(ids={P_SCOPE: {"set": set_}}))


def test_ac74_a_bad_mounts_key_in_the_committed_file_is_exit_6_for_a_build(tmp_path, monkeypatch, capsys):
    path = tmp_path / "weapon_overrides.json"
    path.write_text(json.dumps(O(ids={B_: {"mounts": {"optic": {"source": "child_node", "child": AUX, "point": [0, 0.1, 0]}}}})),
                    encoding="utf-8")
    monkeypatch.setattr(ovr, "default_overrides_path", lambda: path)
    cat = tmp_path / "catalogs"
    cat.mkdir()
    code, out = H.run(H.write_config(tmp_path, cat), capsys, ["weapons", "build"])
    assert code == 6 and out["ok"] is False and "point" in out["error"]
    with pytest.raises(SchemaError):
        ovr.load_overrides(path)


# --- precedence of the compatible verdict ---------------------------------------------------------------------------------


def sources(doc, part_id):
    return effective_override(part_id, doc)["compat_sources"]


def test_ac74_precedence_exact_id_over_longest_glob_over_shorter_glob():
    doc = O(globs={"FAKE_CompA/SM_Wep_Rifle_Scope_*": {"compatible": {"add": ["FAKE_CompA/SM_Wep_Pistol_*"]}},
                   "FAKE_CompA/SM_Wep_Rifle_Scope_G*": {"compatible": {"remove": ["FAKE_CompA/SM_Wep_Pistol_*"]}}},
            ids={W.P[W.SCOPE_WIDE]: {"compatible": {"remove": [G_]}}})
    verdict = {part: compatible_verdict(sources(doc, W.P[part]), W.P[part], G_)
               for part in (W.SCOPE, W.SCOPE_TIGHT, W.SCOPE_WIDE, W.SCOPE_GIANT)}
    assert verdict == {W.SCOPE: "add", W.SCOPE_TIGHT: "add", W.SCOPE_WIDE: "remove", W.SCOPE_GIANT: "remove"}
    assert compatible_verdict(sources(doc, W.P[W.SCOPE]), W.P[W.SCOPE], A_) is None  # no entry names ALPHA


def test_ac74_inside_one_entry_the_more_specific_host_pattern_wins_and_remove_wins_a_tie():
    doc = O(ids={P_SCOPE: {"compatible": {"add": ["FAKE_CompA/*"], "remove": ["FAKE_CompA/SM_Wep_Rifle_*"]}}})
    assert compatible_verdict(sources(doc, P_SCOPE), P_SCOPE, A_) == "remove"  # the longer glob
    assert compatible_verdict(sources(doc, P_SCOPE), P_SCOPE, G_) == "add"
    tie = O(ids={P_SCOPE: {"compatible": {"add": [A_], "remove": [A_]}}})
    assert compatible_verdict(sources(tie, P_SCOPE), P_SCOPE, A_) == "remove"
    exact = O(ids={P_SCOPE: {"compatible": {"add": [A_], "remove": ["FAKE_CompA/SM_Wep_Rifle_*"]}}})
    assert compatible_verdict(sources(exact, P_SCOPE), P_SCOPE, A_) == "add"  # the exact host id beats the glob


def test_ac74_two_equal_length_globs_that_disagree_are_a_schema_error():
    doc = O(globs={"FAKE_CompA/SM_Wep_Rifle_Scope_*": {"compatible": {"add": [G_]}},
                   "FAKE_CompA/SM_Wep_Rifle_Scop?_*": {"compatible": {"remove": [G_]}}})
    with pytest.raises(SchemaError, match="equal length"):
        compatible_verdict(sources(doc, P_SCOPE), P_SCOPE, G_)


# --- the overrides at work in a build ------------------------------------------------------------------------------------


def test_ac74_compatible_add_and_remove_by_id(tmp_path):
    recs, report = run(tmp_path, O(ids={P_SCOPE: {"compatible": {"remove": [A_], "add": [G_]}}}))
    # S7 (spec 3.4 step 3): GAMMA, BETA and DELTA have a flat optic seat now, so none of them is pending; GAMMA is listed by the override (1.0)
    assert lists(recs, W.SCOPE) == ([(G_, OVERRIDE, 1.0), (E_, TWIN, 0.95), (B_, SAME, 0.8), (D_, CROSS, 0.5)], [])
    assert "twin_multi" not in recs[P_SCOPE]["review"]["reasons"]  # ALPHA was the second twin
    assert "mount_missing" not in recs[G_]["review"]["reasons"]  # the added host has an (estimated) optic seat since S7
    assert report["warnings"] == []


def test_ac74_compatible_by_glob_with_longest_glob_and_exact_id_precedence(tmp_path):
    doc = O(globs={"FAKE_CompA/SM_Wep_Rifle_Scope_*": {"compatible": {"add": ["FAKE_CompA/SM_Wep_Pistol_*"]}},
                   "FAKE_CompA/SM_Wep_Rifle_Scope_G*": {"compatible": {"remove": ["FAKE_CompA/SM_Wep_Pistol_*"]}}},
            ids={W.P[W.SCOPE_WIDE]: {"compatible": {"remove": [G_]}}})
    recs, _ = run(tmp_path, doc)
    # S7 (spec 3.4 step 3): GAMMA has a flat optic seat, so the override entry is in compatible_hosts, not pending_hosts
    has_gamma = {part: G_ in {e["host"] for e in recs[W.P[part]]["attachment"]["compatible_hosts"]}
                 for part in (W.SCOPE, W.SCOPE_TIGHT, W.SCOPE_WIDE, W.SCOPE_GIANT)}
    assert has_gamma == {W.SCOPE: True, W.SCOPE_TIGHT: True, W.SCOPE_WIDE: False, W.SCOPE_GIANT: False}


def test_ac74_a_missing_host_and_a_missing_node_are_reported_not_dropped(tmp_path):
    doc = O(ids={P_SCOPE: {"compatible": {"add": ["FAKE_CompA/SM_Wep_Nowhere_01"]}},
                 B_: {"mounts": {"optic": {"source": "child_node", "child": "NoSuchNode"}}}})
    recs, report = run(tmp_path, doc)
    assert report["warnings"] == [
        "FAKE_CompA/SM_Wep_Rifle_Beta_01: mount child_not_found: optic: NoSuchNode",
        "FAKE_CompA/SM_Wep_Rifle_Scope_01: child_not_found: compatible.add FAKE_CompA/SM_Wep_Nowhere_01 (no eligible host)"]
    assert recs[B_]["geometry"]["mounts"]["optic"]["source"] == "probe"  # the unusable override changed nothing (S7: the flat seat stays)
    assert lists(recs, W.SCOPE)[0] == [(A_, TWIN, 0.95), (E_, TWIN, 0.95), (B_, SAME, 0.8), (D_, CROSS, 0.5)]


def test_ac74_a_glob_that_matches_no_host_is_reported_too(tmp_path):
    _, report = run(tmp_path, O(ids={P_SCOPE: {"compatible": {"remove": ["FAKE_CompA/SM_Wep_Smg_*"]}}}))
    assert any("child_not_found: compatible.remove FAKE_CompA/SM_Wep_Smg_*" in w for w in report["warnings"])


def test_ac74_a_disabled_slot_vetoes_inferred_tiers_but_an_override_add_still_lists_the_host(tmp_path):
    off = O(ids={A_: {"mounts": {"optic": {"source": "none"}}}})
    recs, _ = run(tmp_path / "a", off)
    assert recs[A_]["geometry"]["mounts"]["optic"]["source"] == "none" and recs[A_]["geometry"]["mounts"]["optic"]["reason"] == "slot_disabled"
    # ALPHA gone, and with it the twin evidence (S7: BETA and DELTA are compatible on their flat optic seats, not pending)
    assert lists(recs, W.SCOPE) == ([(E_, TWIN, 0.95), (B_, SAME, 0.8), (D_, CROSS, 0.5)], [])
    on = O(ids={A_: {"mounts": {"optic": {"source": "none"}}}, P_SCOPE: {"compatible": {"add": [A_]}}})
    recs, _ = run(tmp_path / "b", on)
    assert lists(recs, W.SCOPE) == ([(E_, TWIN, 0.95), (B_, SAME, 0.8), (D_, CROSS, 0.5)], [(A_, OVERRIDE)])  # the disabled slot has no seat


def test_ac75_a_measured_mount_by_override_moves_the_pending_host_to_compatible(tmp_path):
    # S7 (spec 3.4 step 3): BETA's optic is an estimated flat seat now, not a pending slot, so the pending -> compatible half runs on the
    # underbarrel (the GRIP part); the optic override then swaps the estimated seat for the Aux child's measured one.
    P_GRIP = W.P[W.GRIP]
    base, _ = run(tmp_path / "a", O())
    assert lists(base, W.GRIP) == ([(G_, TWIN, 0.95)], [(A_, SAME), (B_, SAME), (E_, SAME), (D_, CROSS)])
    assert lists(base, W.SCOPE) == ([(A_, TWIN, 0.95), (E_, TWIN, 0.95), (B_, SAME, 0.8), (D_, CROSS, 0.5)], [])
    doc = O(ids={B_: {"mounts": {"underbarrel": {"source": "child_node", "child": AUX}}}})
    recs, report = run(tmp_path / "b", doc)
    mount = recs[B_]["geometry"]["mounts"]["underbarrel"]
    assert (mount["source"], mount["child_node"], mount["span_m"], mount["span_source"]) == ("override", AUX, 0.066, "child_foot")
    # Aux is optic() x1.1, so the seat span is 0.066 and the 0.06 GRIP foot fits it
    assert lists(recs, W.GRIP) == ([(G_, TWIN, 0.95), (B_, SAME, 0.8)], [(A_, SAME), (E_, SAME), (D_, CROSS)])
    entry = next(e for e in recs[P_GRIP]["attachment"]["compatible_hosts"] if e["host"] == B_)
    assert entry["replaces"] == [AUX] and "mount_available" in entry["signals"]
    assert report["warnings"] == []
    assert "mount_missing" in recs[B_]["review"]["reasons"]  # its magazine is still without a seat and has candidates
    # the optic override replaces BETA's estimated flat seat (span 0.181) by the Aux child (span 0.066): the 1.0 x scope fits it (0.06 / 0.066)
    # and keeps its 0.8, the 1.2 x one is neutral (1.09) and drops from the 0.8 of the long flat seat to 0.7
    recs, report = run(tmp_path / "c", O(ids={B_: {"mounts": {"optic": {"source": "child_node", "child": AUX}}}}))
    mount = recs[B_]["geometry"]["mounts"]["optic"]
    assert (mount["source"], mount["child_node"], mount["span_m"], mount["span_source"]) == ("override", AUX, 0.066, "child_foot")
    assert lists(recs, W.SCOPE) == ([(A_, TWIN, 0.95), (E_, TWIN, 0.95), (B_, SAME, 0.8), (D_, CROSS, 0.5)], [])
    assert lists(recs, W.SCOPE_WIDE)[0] == [(A_, SAME, 0.7), (B_, SAME, 0.7), (E_, SAME, 0.7), (D_, CROSS, 0.5)]
    assert lists(recs, W.ALT_SCOPE) == ([(A_, TWIN, 0.95), (E_, TWIN, 0.95), (B_, CROSS, 0.5)], [])
    entry = next(e for e in recs[P_SCOPE]["attachment"]["compatible_hosts"] if e["host"] == B_)
    assert entry["replaces"] == [AUX] and "mount_available" in entry["signals"]
    assert report["warnings"] == []


def test_ac74_the_mount_override_reaches_the_geometry_cache_key(tmp_path):
    cache: dict = {}
    # S7 (spec 3.4 step 3): the underbarrel is the slot of BETA that has no seat (its optic is a flat seat now)
    first, _ = run(tmp_path, O(), cache=cache)
    assert first[B_]["geometry"]["mounts"]["underbarrel"]["source"] == "none"
    second, _ = run(tmp_path, O(ids={B_: {"mounts": {"underbarrel": {"source": "child_node", "child": AUX}}}}), cache=cache)
    assert second[B_]["geometry"]["mounts"]["underbarrel"]["source"] == "override"  # not a stale hit of the first build
    third, _ = run(tmp_path, O(), cache=cache)
    assert third[B_]["geometry"]["mounts"]["underbarrel"]["source"] == "none"


def test_ac74_set_attachment_slot_and_kind_replace_the_rule_answer(tmp_path):
    giant = W.P[W.SCOPE_GIANT]
    base, _ = run(tmp_path / "0", O())
    recs, _ = run(tmp_path / "a", O(ids={giant: {"set": {"attachment_slot": "sight_front", "attachment_kind": "post"}}}))
    assert (base[giant]["attachment"]["slot"], base[giant]["attachment"]["kind"]) == ("optic", "scope")
    assert (recs[giant]["attachment"]["slot"], recs[giant]["attachment"]["kind"]) == ("sight_front", "post")  # A2: `iron` left optic
    assert recs[giant]["component"] == base[giant]["component"]  # the attachment override never changes `component` (3.3)
    recs, _ = run(tmp_path / "b", O(ids={giant: {"set": {"attachment_slot": "magazine", "attachment_kind": "drum"}}}))
    att = recs[giant]["attachment"]
    assert (att["slot"], att["kind"]) == ("magazine", "drum")
    assert lists(recs, W.SCOPE_GIANT)[0] == [(A_, SAME, 0.7)]  # a magazine now: only ALPHA has a magazine seat
    recs, _ = run(tmp_path / "c", O(ids={giant: {"set": {"attachment_slot": "muzzle"}}}))
    assert (recs[giant]["attachment"]["slot"], recs[giant]["attachment"]["kind"]) == ("muzzle", "other")


def test_ac74_an_attachment_kind_that_does_not_fit_the_rule_slot_is_a_schema_error(tmp_path):
    with pytest.raises(SchemaError, match="not a kind of slot optic"):
        run(tmp_path, O(ids={W.P[W.SCOPE_GIANT]: {"set": {"attachment_kind": "drum"}}}))


def test_ac74_an_attachment_only_set_does_not_declare_a_new_weapon(tmp_path):
    recs, _ = run(tmp_path, O(ids={W.P[W.SCOPE_GIANT]: {"set": {"attachment_kind": "reflex"}}}))
    assert recs[W.P[W.SCOPE_GIANT]]["role"] == "part"


# --- apply-corrections round trip ----------------------------------------------------------------------------------------


CORRECTIONS = {"schema": "weapon-corrections/1", "corrections": [
    {"target": {"id": P_SCOPE}, "compatible": {"add": [G_, B_, G_], "remove": [A_]}},
    {"target": {"id": B_}, "mounts": {"optic": {"source": "child_node", "child": AUX}}},
    {"target": {"glob": "FAKE_CompA/SM_Wep_Rifle_Scope_*"}, "compatible": {"add": ["FAKE_CompA/SM_Wep_Pistol_*"]}},
    {"target": {"id": W.P[W.SCOPE_GIANT]}, "set": {"attachment_slot": "sight_front", "attachment_kind": "post"}},
]}
MERGED = {
    "schema": "weapon-overrides/1",
    "ids": {P_SCOPE: {"compatible": {"add": [G_, B_], "remove": [A_]}},  # sorted: Pistol_Gamma before Rifle_Beta
            B_: {"mounts": {"optic": {"source": "child_node", "child": AUX}}},
            W.P[W.SCOPE_GIANT]: {"set": {"attachment_slot": "sight_front", "attachment_kind": "post"}}},
    "globs": {"FAKE_CompA/SM_Wep_Rifle_Scope_*": {"compatible": {"add": ["FAKE_CompA/SM_Wep_Pistol_*"]}}},
}


def test_ac74_corrections_merge_into_the_hand_written_overrides_and_apply_twice_is_a_no_op():
    merged, warnings = apply_corrections(CORRECTIONS, empty_overrides())
    assert merged == MERGED and warnings == []  # the add list is sorted and de-duplicated
    again, _ = apply_corrections(CORRECTIONS, merged)
    assert again == merged and overrides_text(again) == overrides_text(merged)
    assert validate_overrides(merged) == []


def test_ac74_a_later_reclassification_keeps_the_compatible_and_mounts_and_a_later_compatible_replaces_them():
    first, _ = apply_corrections(CORRECTIONS, empty_overrides())
    later = {"schema": "weapon-corrections/1", "corrections": [
        {"target": {"id": P_SCOPE}, "set": {"attachment_kind": "reflex"}}, {"target": {"id": B_}, "set": {"role": "whole"}}]}
    merged, _ = apply_corrections(later, first)
    assert merged["ids"][P_SCOPE] == {"set": {"attachment_kind": "reflex"}, "compatible": {"add": [G_, B_], "remove": [A_]}}
    assert merged["ids"][B_]["mounts"] == MERGED["ids"][B_]["mounts"] and merged["ids"][B_]["set"] == {"role": "whole"}
    replace = {"schema": "weapon-corrections/1", "corrections": [{"target": {"id": P_SCOPE}, "compatible": {"remove": [G_]}}]}
    replaced, _ = apply_corrections(replace, merged)
    assert replaced["ids"][P_SCOPE] == {"set": {"attachment_kind": "reflex"}, "compatible": {"remove": [G_]}}  # replaces, not unions
    only_set = {"schema": "weapon-corrections/1", "corrections": [{"target": {"id": P_SCOPE}, "compatible": {"add": [A_]}}]}
    assert apply_corrections(only_set, merged)[0]["ids"][P_SCOPE]["set"] == {"attachment_kind": "reflex"}  # the stored set stays


@pytest.mark.parametrize("item", [
    {"target": {"id": B_}, "mounts": {"optic": {"source": "child_node", "child": AUX, "point": [0, 0, 0]}}},
    {"target": {"glob": "FAKE_CompA/SM_Wep_Rifle_*"}, "mounts": {"optic": {"source": "none"}}},
    {"target": {"id": B_}, "compatible": {"add": [7]}},
    {"target": {"id": B_}, "compatible": {}},
])
def test_ac74_corrections_that_break_the_override_schema_are_exit_6(item):
    doc = {"schema": "weapon-corrections/1", "corrections": [item]}
    assert validate_corrections(doc)
    with pytest.raises(SchemaError):
        apply_corrections(doc, empty_overrides())


def test_ac74_apply_corrections_through_the_cli_writes_once_and_a_second_run_changes_nothing(tmp_path, monkeypatch, capsys):
    path = tmp_path / "weapon_overrides.json"
    path.write_text(json.dumps(empty_overrides()), encoding="utf-8")
    monkeypatch.setattr(ovr, "default_overrides_path", lambda: path)
    cfg = H.write_config(tmp_path, tmp_path / "catalogs")
    src = tmp_path / "corrections.json"
    src.write_text(json.dumps(CORRECTIONS), encoding="utf-8")
    code, out = H.run(cfg, capsys, ["weapons", "apply-corrections", str(src)])
    assert code == 0 and out["wrote"] is True and out["changed"] is True
    assert json.loads(path.read_text(encoding="utf-8")) == MERGED
    before = path.read_bytes()
    code, out = H.run(cfg, capsys, ["weapons", "apply-corrections", str(src)])
    assert code == 0 and out["wrote"] is False and out["changed"] is False and path.read_bytes() == before
    bad = copy.deepcopy(CORRECTIONS)
    bad["corrections"][1]["mounts"]["optic"]["span_m"] = 0.05
    src.write_text(json.dumps(bad), encoding="utf-8")
    code, out = H.run(cfg, capsys, ["weapons", "apply-corrections", str(src)])
    assert code == 6 and out["ok"] is False
    assert path.read_bytes() == before  # nothing written on a violation


def test_ac74_a_build_with_the_merged_corrections_equals_a_build_with_the_hand_written_overrides(tmp_path):
    merged, _ = apply_corrections(CORRECTIONS, empty_overrides())
    a, _, _, *_ = W.build_report(tmp_path / "a", overrides=merged)
    b, _, _, *_ = W.build_report(tmp_path / "b", overrides=copy.deepcopy(MERGED))
    assert to_text(a) == to_text(b)
