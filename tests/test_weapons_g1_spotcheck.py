"""G1 S9 ``weapons attach-spotcheck`` (docs/weapon_attach_geometry.md 3.10, 4.4; AC141, INV-26).

The draw reads only ids, slots and tiers, so the directory here is a literal one (``directory()``: parts with listed and pending entries), not a built world.
Per slot (listed pairs; the draw tiers are ``same_pack_fit`` and ``cross_pack_fit``, a twin or an override is authored and never drawn):

  slot         same  cross  twin  override  pending   the 8 split (hand-worked: 8 * same / (same + cross), half up, 2 minimum, 6 maximum)
  optic         10     10     2      1         3      8 * 10 / 20 = 4.0          -> 4 same, 4 cross
  muzzle        12      4     0      0         0      8 * 12 / 16 = 6.0          -> 6 same, 2 cross
  underbarrel    3     30     0      0         2      8 * 3 / 33  = 0.73 -> 1    -> the minimum of 2 for a non-empty tier: 2 same, 6 cross
  magazine      20      0     1      0         4      one tier only              -> 8 same
  laser_light   (a label-era slot: 5 listed pairs, never drawn)

Three optic and two magazine pairs among the ``LABELLED`` ones are the lowest-hash candidates of their tier: without the exclusion they would be drawn.
Order: ascending ``sha256("spotcheck-1|" + part + "|" + host)``, computed below with ``hashlib`` (this test's own copy of the rule).

Deliberate breaks, on a scratch copy: the draw not sorted by hash (``chosen.sort()`` removed); a labelled pair not excluded; a twin drawn; the file
overwritten by a second draw.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("review_helpers")

from synty_inventory.weapons import guards, spotcheck as SP  # noqa: E402

DIGEST = "0123456789abcdef"
SPEC = {
    "optic": {"same_pack_fit": 10, "cross_pack_fit": 10, "twin": 2, "override": 1},
    "muzzle": {"same_pack_fit": 12, "cross_pack_fit": 4},
    "underbarrel": {"same_pack_fit": 3, "cross_pack_fit": 30},
    "magazine": {"same_pack_fit": 20, "twin": 1},
    "laser_light": {"same_pack_fit": 5},
}
PENDING = {"optic": 3, "underbarrel": 2, "magazine": 4}
SPLIT = {"optic": (4, 4), "muzzle": (6, 2), "underbarrel": (2, 6), "magazine": (8, 0)}


def key(part, host):
    return hashlib.sha256(f"spotcheck-1|{part}|{host}".encode("utf-8")).hexdigest()


def directory(spec=None, pending=None):
    """Two parts per slot; the entries of a slot alternate between them, so a pair is (part, host) with the host unique per entry."""
    weapons = []
    for slot, tiers in (spec or SPEC).items():
        parts = [{"id": f"Q/Part_{slot}_{i}", "role": "part", "attachment": {"slot": slot, "compatible_hosts": [], "pending_hosts": []}} for i in (1, 2)]
        n = 0
        for tier, count in tiers.items():
            for _ in range(count):
                parts[n % 2]["attachment"]["compatible_hosts"].append({"host": f"Q/Host_{slot}_{n:02d}", "tier": tier, "score": 0.5})
                n += 1
        for j in range((pending or PENDING).get(slot, 0)):
            parts[j % 2]["attachment"]["pending_hosts"].append({"host": f"Q/Pending_{slot}_{j}", "tier": "same_pack_fit"})
        weapons += parts
    # S12: the draw refuses a directory that is not a current attach build, so the fixture carries the header (the literal 14, not the package constant)
    return {"schema": "weapon-directory/1", "attach_rules_digest": DIGEST, "attach_version": 16, "fit_digest": "fedcba9876543210", "weapons": weapons}


def listed(d, slot, tier):
    return sorted((key(w["id"], e["host"]), w["id"], e["host"]) for w in d["weapons"] if w["attachment"]["slot"] == slot
                  for e in w["attachment"]["compatible_hosts"] if e["tier"] == tier)


def labelled_pairs(d):
    """Five hand-picked labelled pairs: the three lowest-hash same_pack_fit optics and the two lowest-hash magazines."""
    return {(p, h) for _k, p, h in listed(d, "optic", "same_pack_fit")[:3]} | {(p, h) for _k, p, h in listed(d, "magazine", "same_pack_fit")[:2]}


def expected(d, labelled):
    """This test's own copy of the rule: per slot and tier the lowest hashes not labelled, as many as the hand-worked split; then all in hash order."""
    chosen = []
    for slot, (n_same, n_cross) in SPLIT.items():
        for tier, n in (("same_pack_fit", n_same), ("cross_pack_fit", n_cross)):
            chosen += [(k, p, h, slot, tier) for k, p, h in [c for c in listed(d, slot, tier) if (c[1], c[2]) not in labelled][:n]]
    return sorted(chosen)


# -- the rule --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("same", "cross", "want"), [
    (10, 10, (4, 4)), (12, 4, (6, 2)), (3, 30, (2, 6)), (20, 0, (8, 0)), (0, 20, (0, 8)), (1, 30, (1, 7)), (30, 1, (7, 1)),
    (2, 2, (2, 2)), (1, 1, (1, 1)), (0, 0, (0, 0)), (5, 5, (4, 4)), (7, 3, (6, 2)),
])
def test_the_split_of_a_slot_is_proportional_with_two_at_least_for_a_tier_that_has_two(same, cross, want):
    got = SP.quotas({"same_pack_fit": same, "cross_pack_fit": cross})
    assert (got["same_pack_fit"], got["cross_pack_fit"]) == want


def test_a_tier_short_of_candidates_after_the_exclusions_gives_what_it_has_and_the_other_takes_the_rest():
    both = {"same_pack_fit": 10, "cross_pack_fit": 10}
    got = SP.quotas(both, {"same_pack_fit": 1, "cross_pack_fit": 10})  # nine of the same-pack pairs are labelled: share 4, left 1
    assert (got["same_pack_fit"], got["cross_pack_fit"]) == (1, 7)
    got = SP.quotas(both, {"same_pack_fit": 10, "cross_pack_fit": 0})  # every cross-pack pair is labelled
    assert (got["same_pack_fit"], got["cross_pack_fit"]) == (8, 0)


def test_the_share_is_of_the_listed_counts_the_labelled_pairs_counted():
    # 10 same + 10 cross listed, three same labelled: the share stays 4 / 4 (7 / 10 left would give 3 / 5)
    d = directory()
    doc, _ = SP.draw(d, labelled_pairs(d))
    assert sum(1 for p in doc["pairs"] if p["slot"] == "optic" and p["tier"] == "same_pack_fit") == 4


def test_ac141_the_draw_gives_32_pairs_8_per_slot_with_the_hand_worked_split_and_none_short():
    doc, short = SP.draw(directory(), labelled_pairs(directory()))
    assert len(doc["pairs"]) == 32 and short == {}
    for slot, (n_same, n_cross) in SPLIT.items():
        mine = [p for p in doc["pairs"] if p["slot"] == slot]
        assert len(mine) == 8
        assert (sum(p["tier"] == "same_pack_fit" for p in mine), sum(p["tier"] == "cross_pack_fit" for p in mine)) == (n_same, n_cross)
    assert {p["slot"] for p in doc["pairs"]} == {"optic", "muzzle", "underbarrel", "magazine"}  # laser_light is a label-era slot: never drawn


def test_ac141_every_non_empty_tier_has_at_least_two_pairs():
    doc, _ = SP.draw(directory(), set())
    for slot in SPLIT:
        for tier in ("same_pack_fit", "cross_pack_fit"):
            have = len(listed(directory(), slot, tier))
            got = sum(1 for p in doc["pairs"] if p["slot"] == slot and p["tier"] == tier)
            assert got >= min(2, have), (slot, tier)


def test_ac141_no_twin_override_pending_or_labelled_pair_is_drawn():
    d = directory()
    labelled = labelled_pairs(d)
    doc, _ = SP.draw(d, labelled)
    drawn = {(p["part"], p["host"]) for p in doc["pairs"]}
    by_pair = {(w["id"], e["host"]): e["tier"] for w in d["weapons"] for e in w["attachment"]["compatible_hosts"]}
    assert drawn <= set(by_pair) and {by_pair[k] for k in drawn} == {"same_pack_fit", "cross_pack_fit"}  # listed, and never twin or override
    assert not drawn & labelled and len(labelled) == 5
    assert not any("Pending" in host for _p, host in drawn)
    assert not drawn & {(w["id"], e["host"]) for w in d["weapons"] for e in w["attachment"]["compatible_hosts"] if e["tier"] in ("twin", "override")}
    # the five labelled pairs are exactly the ones the unlabelled draw would have taken first
    plain, _ = SP.draw(d, set())
    assert labelled <= {(p["part"], p["host"]) for p in plain["pairs"]}


def test_ac141_the_pairs_are_the_lowest_hashes_of_each_tier_in_ascending_hash_order():
    d = directory()
    labelled = labelled_pairs(d)
    doc, _ = SP.draw(d, labelled)
    want = expected(d, labelled)
    assert [(p["part"], p["host"], p["slot"], p["tier"]) for p in doc["pairs"]] == [(p, h, s, t) for _k, p, h, s, t in want]
    keys = [key(p["part"], p["host"]) for p in doc["pairs"]]
    assert keys == sorted(keys) and len(set(keys)) == 32


def test_ac141_the_draw_is_a_function_of_the_directory_alone():
    d = directory()
    first, _ = SP.draw(d, set())
    again, _ = SP.draw(copy.deepcopy(d), set())
    assert first == again
    shuffled = copy.deepcopy(d)
    shuffled["weapons"].reverse()
    assert SP.draw(shuffled, set())[0]["pairs"] == first["pairs"]  # the order of the directory is not an input


def test_the_document_is_the_weapon_attach_spotcheck_1_shape_with_every_answer_null():
    doc, _ = SP.draw(directory(), set())
    assert list(doc) == ["schema", "drawn_at", "salt", "pairs"]
    assert (doc["schema"], doc["drawn_at"], doc["salt"]) == ("weapon-attach-spotcheck/1", DIGEST, "spotcheck-1")
    assert all(list(p) == ["part", "host", "slot", "tier", "fits", "placed_wrong"] and p["fits"] is None and p["placed_wrong"] is None for p in doc["pairs"])
    assert SP.validate(doc) == []


def test_a_slot_with_fewer_than_eight_candidates_gives_them_all_and_is_reported_short():
    d = directory({"optic": {"same_pack_fit": 3, "cross_pack_fit": 2}, "muzzle": {"same_pack_fit": 9}})
    doc, short = SP.draw(d, set())
    assert short == {"underbarrel": 8, "magazine": 8, "optic": 3}
    assert sum(1 for p in doc["pairs"] if p["slot"] == "optic") == 5 and sum(1 for p in doc["pairs"] if p["slot"] == "muzzle") == 8


# -- validation and INV-26 ---------------------------------------------------------------------------------------


def drawn():
    return SP.draw(directory(), set())[0]


def test_validate_catches_a_draw_out_of_hash_order():
    doc = drawn()
    doc["pairs"][0], doc["pairs"][1] = doc["pairs"][1], doc["pairs"][0]
    assert any("hash order" in e for e in SP.validate(doc))


@pytest.mark.parametrize(("name", "mutate"), [
    ("schema", lambda d: d.update(schema="weapon-attach-spotcheck/2")),
    ("extra top key", lambda d: d.update(note="x")),
    ("answer not boolean", lambda d: d["pairs"][0].update(fits="yes")),
    ("a number in a pair", lambda d: d["pairs"][0].update(score=0.5)),
    ("twin tier", lambda d: d["pairs"][0].update(tier="twin")),
    ("slot of the label era", lambda d: d["pairs"][0].update(slot="laser_light")),
    ("placed wrong without a fit", lambda d: d["pairs"][0].update(fits=False, placed_wrong=True)),
    ("pair drawn twice", lambda d: d["pairs"].append(dict(d["pairs"][-1]))),
])
def test_validate_catches(name, mutate):
    doc = drawn()
    mutate(doc)
    assert SP.validate(doc), name


def test_inv26_fits_and_placed_wrong_change_only_from_null():
    base = drawn()
    now = copy.deepcopy(base)
    now["pairs"][0].update(fits=True, placed_wrong=False)
    now["pairs"][1].update(fits=True, placed_wrong=True)
    now["pairs"][2].update(fits=False)
    assert SP.check_update(base, now) == []  # an answer given once, from null
    assert SP.check_update(base, base) == []
    later = copy.deepcopy(now)
    later["pairs"][3].update(fits=False)  # the next answer, also from null
    assert SP.check_update(now, later) == []


@pytest.mark.parametrize(("name", "mutate", "needle"), [
    ("an answer changed", lambda d: d["pairs"][0].update(fits=False), "pairs[0].fits"),
    ("an answer withdrawn", lambda d: d["pairs"][0].update(fits=None), "pairs[0].fits"),
    ("placed_wrong flipped", lambda d: d["pairs"][1].update(placed_wrong=False), "pairs[1].placed_wrong"),
    ("a host rewritten", lambda d: d["pairs"][2].update(host="Q/Elsewhere"), "pairs[2].host"),
    ("a tier rewritten", lambda d: d["pairs"][2].update(tier="cross_pack_fit" if d["pairs"][2]["tier"] != "cross_pack_fit" else "same_pack_fit"), "pairs[2].tier"),
    ("a pair removed", lambda d: d["pairs"].pop(), "pairs:"),
    ("the digest rewritten", lambda d: d.update(drawn_at="ffffffffffffffff"), "drawn_at"),
])
def test_inv26_anything_else_is_a_violation(name, mutate, needle):
    base = drawn()
    base["pairs"][0].update(fits=True, placed_wrong=False)
    base["pairs"][1].update(fits=True, placed_wrong=True)
    now = copy.deepcopy(base)
    mutate(now)
    errors = SP.check_update(base, now)
    assert errors and any(needle in e for e in errors), (name, errors)


# -- the verb ----------------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    for key_ in H.ENV_KEYS:
        monkeypatch.delenv(key_, raising=False)


@pytest.fixture
def files(tmp_path):
    d = directory()
    dpath = tmp_path / "directory.json"
    dpath.write_text(json.dumps(d), encoding="utf-8")
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"schema": "weapon-attach-labels/1",
                                  "pairs": [{"part": p, "host": h, "fits": True} for p, h in sorted(labelled_pairs(d))]}), encoding="utf-8")
    return {"dir": dpath, "labels": labels, "out": tmp_path / "spotcheck.json", "cfg": H.write_config(tmp_path, tmp_path), "tmp": tmp_path}


def spot(files, capsys, *flags, with_labels=True):
    argv = ["weapons", "attach-spotcheck", "--directory", str(files["dir"]), "--file", str(files["out"]), *flags]
    if with_labels:
        argv += ["--labels", str(files["labels"])]
    return H.run(files["cfg"], capsys, argv)


def test_ac141_draw_writes_the_32_pairs_and_a_second_draw_exits_6_leaving_the_file_alone(files, capsys):
    code, out = spot(files, capsys, "--draw")
    assert code == 0 and out["ok"] is True and out["drawn"] == 32 and out["file"] == "spotcheck.json" and out["short"] == {}
    assert out["per_slot"] == {"optic": 8, "muzzle": 8, "underbarrel": 8, "magazine": 8} and out["labelled_skipped"] == 5
    assert out["per_tier"]["muzzle"] == {"same_pack_fit": 6, "cross_pack_fit": 2} and out["per_tier"]["underbarrel"] == {"same_pack_fit": 2, "cross_pack_fit": 6}
    first = files["out"].read_bytes()
    assert b"\r" not in first and first.endswith(b"\n")
    doc = json.loads(first)
    d = directory()
    assert [(p["part"], p["host"]) for p in doc["pairs"]] == [(p, h) for _k, p, h, _s, _t in expected(d, labelled_pairs(d))]
    code, out = spot(files, capsys, "--draw")
    assert code == 6 and out["ok"] is False and "drawn once" in out["error"]
    assert files["out"].read_bytes() == first  # never overwritten (INV-26)


def test_ac141_the_labels_file_is_what_the_draw_skips(files, capsys, monkeypatch):
    # S12: the committed labels file is the default of a bare --draw (its absence is a refusal, tests/test_weapons_s12_labels.py), so it is pointed at the fixture's
    monkeypatch.setattr(SP, "default_labels_path", lambda: files["labels"])
    code, out = spot(files, capsys, "--draw", with_labels=False)
    assert code == 0 and out["labelled_skipped"] == 5
    doc = json.loads(files["out"].read_text(encoding="utf-8"))
    assert not labelled_pairs(directory()) & {(p["part"], p["host"]) for p in doc["pairs"]}


def test_draw_exits_2_for_a_missing_directory_and_writes_nothing(files, capsys):
    files["dir"].unlink()
    code, out = spot(files, capsys, "--draw")
    assert code == 2 and not files["out"].exists()


def test_ac141_score_prints_fits_k_of_32_placed_wrong_m(files, capsys):
    spot(files, capsys, "--draw")
    code, out = spot(files, capsys, "--score")
    assert code == 0 and out["summary"] == "fits 0 of 32 (placed wrong 0)" and out["answered"] == 0
    doc = json.loads(files["out"].read_text(encoding="utf-8"))
    for i, pair in enumerate(doc["pairs"]):
        pair["fits"] = i < 20  # 20 fit, the other 12 do not
        pair["placed_wrong"] = (i in (2, 5, 9)) or None if i < 20 else None
    files["out"].write_text(json.dumps(doc), encoding="utf-8")
    code, out = spot(files, capsys, "--score")
    assert code == 0 and out["summary"] == "fits 20 of 32 (placed wrong 3)" and out["fits"] == 20 and out["placed_wrong"] == 3 and out["answered"] == 32


def test_inv26_score_against_a_baseline_exits_6_when_more_than_an_answer_changed(files, capsys):
    spot(files, capsys, "--draw")
    baseline = files["tmp"] / "as_drawn.json"
    baseline.write_bytes(files["out"].read_bytes())
    doc = json.loads(files["out"].read_text(encoding="utf-8"))
    doc["pairs"][0]["fits"] = True
    files["out"].write_text(json.dumps(doc), encoding="utf-8")
    code, out = spot(files, capsys, "--score", "--baseline", str(baseline))
    assert code == 0 and out["summary"] == "fits 1 of 32 (placed wrong 0)"  # an answer from null
    baseline.write_bytes(files["out"].read_bytes())  # the file as last saved: that answer is now given
    doc["pairs"][0]["fits"] = False  # changed once given
    files["out"].write_text(json.dumps(doc), encoding="utf-8")
    code, out = spot(files, capsys, "--score", "--baseline", str(baseline))
    assert code == 6 and any("pairs[0].fits" in e for e in out["errors"])
    doc["pairs"][0]["fits"] = True
    doc["pairs"][1]["host"] = "Q/Rewritten"
    files["out"].write_text(json.dumps(doc), encoding="utf-8")
    code, out = spot(files, capsys, "--score", "--baseline", str(baseline))
    assert code == 6 and out["errors"]  # a schema case, not INV-26: a rewritten host also breaks the hash order, which the schema check reports first


def test_inv26_a_given_answer_flipped_on_a_schema_valid_file_is_the_only_error_reported(files, capsys):
    # the write-once diff alone: the file is a valid draw (schema and hash order hold), one given answer goes from one boolean to the other
    spot(files, capsys, "--draw")
    doc = json.loads(files["out"].read_text(encoding="utf-8"))
    doc["pairs"][0]["fits"] = True
    files["out"].write_text(json.dumps(doc), encoding="utf-8")
    baseline = files["tmp"] / "as_saved.json"
    baseline.write_bytes(files["out"].read_bytes())  # the file as last saved: pairs[0].fits is given
    doc["pairs"][0]["fits"] = False
    files["out"].write_text(json.dumps(doc), encoding="utf-8")
    assert SP.validate(doc) == []  # the flipped file is schema-valid
    code, out = spot(files, capsys, "--score", "--baseline", str(baseline))
    assert code == 6 and out["ok"] is False
    assert out["errors"] == ["pairs[0].fits: changed from True to False (an answer is given once)"]  # nothing of the schema or hash order alongside
    assert out["error"] == "the spot-check file is not valid:\n  pairs[0].fits: changed from True to False (an answer is given once)"


def test_score_exits_2_for_a_missing_file_and_6_for_a_broken_one(files, capsys):
    assert spot(files, capsys, "--score")[0] == 2
    files["out"].write_text(json.dumps({"schema": "weapon-attach-spotcheck/1", "pairs": "x"}), encoding="utf-8")
    assert spot(files, capsys, "--score")[0] == 6


def test_the_committed_file_is_not_written_by_a_draw_into_another_path(files, capsys):
    real = SP.default_path()
    before = real.read_bytes() if real.exists() else None
    spot(files, capsys, "--draw")
    assert (real.read_bytes() if real.exists() else None) == before  # S12 writes the committed file, nothing here does
    assert real.name == "weapon_attach_spotcheck.json" and real.parent.name == "data"
