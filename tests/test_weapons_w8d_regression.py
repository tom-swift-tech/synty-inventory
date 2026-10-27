"""W8d: no-regression diff against W7 (docs/weapon_attachments.md 13, AC82).

``fixtures/weapons/w8d_w7_directory.json.gz`` is the REAL W7 ``directory.json`` of the W8d world (the ``w8d_world`` packs: the
review_helpers world plus FAKE_Attach / FAKE_Mount / FAKE_CompA / FAKE_CompB, 238 records), written by the untouched W7 tree
(``w8d_gen_reference.py``). The W8 build of the same world must differ from it in exactly the ways the spec allows:

* the counts and the digests that W7 knew (``rules_digest`` 7b9829af37328fe7, ``geometry_version`` 5 (6 since G1), ``overrides_digest``) are equal;
* the only new header fields are ``attach_version`` and ``attach_rules_digest``;
* every pre-existing field of every record is equal, except ``review.confidence`` and ``review.reasons``;
* those two move only by the spec 8 attachment reasons plus the ``low_confidence`` / cap / scale they cause: reasons are only
  ever added, confidence only ever goes down, and it goes down only on an attachment part whose anchor is unmeasured or whose
  forward is unsure (the cases that cap or scale it);
* the only new record fields are ``geometry.mounts`` and ``attachment``.

The comparison is one function, ``regressions(ref, new)``, which returns one line per offending record. The tests assert it is
empty and that a deliberately perturbed copy of the reference is reported (so the check cannot pass by looking at nothing).
"""

from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec_g1 = importlib.util.spec_from_file_location("g1_refs", FIX / "g1_refs.py")
g1_refs = importlib.util.module_from_spec(_spec_g1)
_spec_g1.loader.exec_module(g1_refs)
_spec = importlib.util.spec_from_file_location("w8d_world", FIX / "w8d_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)

ATTACH_REASONS = {  # spec 8
    "anchor_unmeasured", "anchor_forward_unsure", "attach_kind_unknown", "mount_missing", "mount_ambiguous",
    "mount_estimated", "twin_multi", "compat_cross_pack",
    "sight_side_unsure",  # A2
}
CAUSED = {"low_confidence"}  # the cap a reason causes
CONFIDENCE_MOVERS = {"anchor_unmeasured", "anchor_forward_unsure", "sight_side_unsure"}  # the only reasons that cap or scale confidence
NEW_HEADER = {"attach_version", "attach_rules_digest"}
NEW_RECORD = {"attachment"}  # plus geometry.mounts


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _excluded, _cat, _root = X.build(tmp_path_factory.mktemp("w8d_regression"))
    return directory


@pytest.fixture(scope="module")
def reference():
    with gzip.open(FIX / "w8d_w7_directory.json.gz", "rt", encoding="utf-8") as fh:
        return json.loads(g1_refs.as_geometry_v6(fh.read()))  # G1: the header's one number that moved, 5 -> 6


def canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def regressions(ref: dict, new: dict) -> list[str]:
    """One line per way ``new`` differs from the W7 reference beyond what AC82 allows."""
    problems: list[str] = []
    for key in sorted(set(ref) | set(new)):
        if key == "weapons":
            continue
        if key in NEW_HEADER and key not in ref:
            continue
        if canon(ref.get(key)) != canon(new.get(key)):
            problems.append(f"header {key}: {canon(ref.get(key))[:80]} -> {canon(new.get(key))[:80]}")
    ref_by = {w["id"]: w for w in ref["weapons"]}
    new_by = {w["id"]: w for w in new["weapons"]}
    if [w["id"] for w in ref["weapons"]] != [w["id"] for w in new["weapons"]]:
        problems.append("record ids or their order changed: %s" % sorted(set(ref_by) ^ set(new_by))[:10])
        return problems
    for rid, old in ref_by.items():
        cur = new_by[rid]
        added = set(cur) - set(old)
        gone = set(old) - set(cur)
        if added - NEW_RECORD or gone:
            problems.append(f"{rid}: record keys changed (new {sorted(added - NEW_RECORD)}, gone {sorted(gone)})")
        old_geo, cur_geo = old.get("geometry"), cur.get("geometry")
        if (old_geo is None) != (cur_geo is None):
            problems.append(f"{rid}: geometry presence changed")
        elif old_geo is not None:
            extra = set(cur_geo) - set(old_geo)
            if extra - {"mounts"} or set(old_geo) - set(cur_geo):
                problems.append(f"{rid}: geometry keys changed (new {sorted(extra - {'mounts'})})")
        for key in sorted(set(old) & set(cur)):
            if key in ("review", "geometry"):
                continue
            if canon(old[key]) != canon(cur[key]):
                problems.append(f"{rid}: {key} changed")
        if old_geo is not None and cur_geo is not None:
            for key in sorted(set(old_geo) & set(cur_geo)):
                if canon(old_geo[key]) != canon(cur_geo[key]):
                    problems.append(f"{rid}: geometry.{key} changed")
        o_rev, c_rev = old["review"], cur["review"]
        for key in sorted(set(o_rev) | set(c_rev)):
            if key not in ("confidence", "reasons") and canon(o_rev.get(key)) != canon(c_rev.get(key)):
                problems.append(f"{rid}: review.{key} changed")
        o_reasons, c_reasons = set(o_rev["reasons"]), set(c_rev["reasons"])
        if not o_reasons <= c_reasons:
            problems.append(f"{rid}: reasons removed {sorted(o_reasons - c_reasons)}")
        if (c_reasons - o_reasons) - ATTACH_REASONS - CAUSED:
            problems.append(f"{rid}: reasons added outside spec 8 {sorted((c_reasons - o_reasons) - ATTACH_REASONS - CAUSED)}")
        if "low_confidence" in c_reasons - o_reasons and not (c_reasons - o_reasons) & CONFIDENCE_MOVERS:
            problems.append(f"{rid}: low_confidence without an anchor reason")
        if c_rev["confidence"] != o_rev["confidence"]:
            if c_rev["confidence"] > o_rev["confidence"]:
                problems.append(f"{rid}: confidence rose {o_rev['confidence']} -> {c_rev['confidence']}")
            if not (cur.get("attachment") or "sight_side_unsure" in c_reasons) or not (c_reasons - o_reasons) & CONFIDENCE_MOVERS:
                problems.append(f"{rid}: confidence moved without an anchor reason on an attachment part")
    return problems


def test_counts_and_digests_equal_the_w7_report(built, reference):
    assert built["counts"] == reference["counts"]
    assert built["counts"]["by_role"] == {"ammo": 7, "carrier": 4, "emplaced": 10, "part": 56, "whole": 161}  # literals
    assert sum(built["counts"]["by_kind"].values()) == 171 and built["counts"]["by_status"] == {"auto": 238}
    assert built["counts"]["by_archetype"]["unknown"] == 74 and built["counts"]["by_archetype"]["rifle"] == 21
    assert (built["rules_digest"], built["geometry_version"]) == ("7b9829af37328fe7", 6)
    assert built["overrides_digest"] == reference["overrides_digest"]
    assert set(built) - set(reference) == NEW_HEADER and not set(reference) - set(built)
    assert built["attach_version"] == 13 and len(built["attach_rules_digest"]) == 16


def test_every_pre_existing_field_is_equal_and_review_moves_only_by_the_attachment_reasons(built, reference):
    problems = regressions(reference, built)
    assert not problems, "records that differ from W7 beyond AC82:\n  " + "\n  ".join(problems)


def test_the_diff_is_not_vacuous_and_the_new_fields_are_present(built, reference):
    ref_by = {w["id"]: w for w in reference["weapons"]}
    moved = [w["id"] for w in built["weapons"] if w["review"] != ref_by[w["id"]]["review"]]
    assert len(moved) == 77  # records whose reasons gained an attachment reason (12 of them also move in confidence); A2: +39 hosts with a sight probe seat (mount_estimated); A3 (W8i): -3 (the Prop_Pistol, Flare_Gun and Prop_Rifle hosts are slot_disabled, no mount_estimated) and +1 (Pistol_Mount is now seated: its baked laser child is out of the probe mesh); A3 addendum 3 (W8j): -4 (the Alpha, Mount, Shared and Tilt hosts carry a baked Scope body child, so both their sight slots are slot_disabled, no mount_estimated); A4 (W8l): +1 (FAKE_CompA Alpha has no underbarrel seat and the foregrip part now lists it, family-free, so it gains mount_missing; the five FAKE_Modern hosts that gain it already moved by mount_estimated); A6 (W8n): -1 (the FAKE_Modern Nail_Gun host is a tool-class host, slot_disabled on all seven slots, so no mount_estimated); A6 (W8n, Tom's two answers): -2 more (the FAKE_Modern flame thrower and stun gun hosts join the tool class, so they lose their mount_estimated too); A6 (W8n, Tom's minigun rule): -1 more (the FAKE_Modern Minigun_01 host joins the fixed_heavy class and loses its mount_estimated)
    assert sum(1 for w in built["weapons"] if w["review"]["confidence"] != ref_by[w["id"]]["review"]["confidence"]) == 12
    assert sum(1 for w in built["weapons"] if "attachment" in w) == 56  # every part record carries the key
    assert sum(1 for w in built["weapons"] if w.get("attachment")) == 39  # 39 non-null blocks (A2: the iron-sight part is sight_side_unsure, no block)
    assert sum(1 for w in built["weapons"] if (w["geometry"] or {}).get("mounts")) >= 20
    assert all("attachment" not in w for w in reference["weapons"])
    assert all("mounts" not in (w["geometry"] or {}) for w in reference["weapons"])
    # a part without an attachment block (a W7 part the rules do not recognise) is unchanged from W7 in every field
    plain = [w for w in built["weapons"] if w["role"] == "part" and not w.get("attachment")]
    assert len(plain) == 17
    # A2: all of them but the sight_side_unsure part (it moved to low_confidence)
    assert all(w["review"] == ref_by[w["id"]]["review"] for w in plain if "sight_side_unsure" not in w["review"]["reasons"])
    assert sum(1 for w in plain if "sight_side_unsure" in w["review"]["reasons"]) == 1


def test_the_check_reports_a_perturbed_record_and_names_it(built, reference):
    victim = next(w["id"] for w in built["weapons"] if w["role"] == "whole" and w["geometry"])
    for edit, needle in (
        (lambda w: w["geometry"]["item_basis"][0].__setitem__(0, 9), "geometry.item_basis changed"),
        (lambda w: w["files"].__setitem__("glb", "x.glb"), "files changed"),
        (lambda w: w.__setitem__("family", "zzz"), "family changed"),
        (lambda w: w["review"].__setitem__("matched_rule", "zzz"), "review.matched_rule changed"),
        (lambda w: w["review"]["reasons"].append("not_a_spec_reason"), "reasons added outside spec 8"),
        (lambda w: w.__setitem__("novel", 1), "record keys changed"),
        (lambda w: w["review"].__setitem__("confidence", 0.01), "confidence moved without an anchor reason"),
    ):
        mutated = copy.deepcopy(built)
        edit(next(w for w in mutated["weapons"] if w["id"] == victim))
        found = [p for p in regressions(reference, mutated) if p.startswith(victim)]
        assert any(needle in p for p in found), (needle, found)
    mutated = copy.deepcopy(built)
    mutated["counts"]["by_role"]["part"] += 1
    assert any(p.startswith("header counts") for p in regressions(reference, mutated))
