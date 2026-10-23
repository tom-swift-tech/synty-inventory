"""W8c ``weapons attach-eval`` (AC79) and ``weapons validate`` on the compatibility lists (INV-14, exit 0 / 6).

docs/weapon_attachments.md 7 and 11. The labels are ids and booleans only (``weapon-attach-labels/1``). Every number below is
counted by hand from the tiers worked out in test_weapons_w8c_compat.py; "predicted" means the host is in the part's
``compatible_hosts`` or ``pending_hosts`` at ``same_pack_fit`` or better.

  pair                     label   predicted                      outcome
  Scope - Alpha            fits    yes (twin)                     TP
  Scope - Epsilon          fits    yes (twin)                     TP
  Scope - Beta             fits    yes (same_pack_fit, pending)   TP
  Scope - Gamma            no      no                             TN
  Scope - Delta            fits    no (cross_pack_fit only)       FN      (TP when cross-pack counts)
  Mag - Alpha              fits    yes (twin)                     TP
  Mag - Beta               no      yes (same_pack_fit, pending)   FP
  Mag - Epsilon            fits    yes (same_pack_fit, pending)   TP
  Mag - Gamma              no      no                             TN
  Mag - Delta              fits    no (cross_pack_fit only)       FN      (TP when cross-pack counts)
  Scope_Tight - Alpha      fits    yes (same_pack_fit)            TP
  Scope_Tight - Gamma      fits    no                             FN
  Scope_Tight - Epsilon    no      yes (same_pack_fit)            FP

  TP 6, FP 2, FN 3, TN 2: precision 6/8 = 0.75, recall 6/9 = 0.6667. With cross-pack: TP 8, FN 1: precision 8/10, recall 8/9.
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
from synty_inventory.weapons.directory import write_directory  # noqa: E402
from synty_inventory.weapons.eval import evaluate, load_labels, validate_labels  # noqa: E402

A_, B_, G_, E_, D_ = (W.H[n] for n in (W.ALPHA, W.BETA, W.GAMMA, W.EPSILON, W.DELTA))
SCOPE, TIGHT, MAG, ALT = W.P[W.SCOPE], W.P[W.SCOPE_TIGHT], W.P[W.MAG], W.P[W.ALT_SCOPE]

PAIRS = [
    (SCOPE, A_, True), (SCOPE, E_, True), (SCOPE, B_, True), (SCOPE, G_, False), (SCOPE, D_, True),
    (MAG, A_, True), (MAG, B_, False), (MAG, E_, True), (MAG, G_, False), (MAG, D_, True),
    (TIGHT, A_, True), (TIGHT, G_, True), (TIGHT, E_, False),
]
# not counted anywhere: a host used as the part, a part used as the host, an id that is nowhere
SKIPPED = [(A_, B_, True), (SCOPE, W.P[W.GRIP], True), (f"{W.PACK_A}/SM_Wep_Nowhere_01", A_, True)]
ALT_PAIRS = [(ALT, A_, True), (ALT, B_, True), (ALT, G_, False)]  # TP, FN (cross_pack_fit only), TN


def labels_doc(pairs) -> dict:
    return {"schema": "weapon-attach-labels/1", "pairs": [{"part": p, "host": h, "fits": f} for p, h, f in pairs]}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w8c_eval")
    directory, excluded, cat, _ = W.build(tmp)
    write_directory(cat, directory, excluded)
    return directory, excluded, cat, tmp


def cli(world, capsys, tmp_path, pairs, *flags, doc=None):
    _, _, cat, _ = world
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(doc if doc is not None else labels_doc(pairs)), encoding="utf-8")
    return H.run(H.write_config(tmp_path, cat), capsys, ["weapons", "attach-eval", "--labels", str(labels), *flags])


# --- AC79 ---------------------------------------------------------------------------------------------------------------


def test_ac79_the_reported_precision_and_recall_equal_the_hand_counted_values_exactly(world):
    result = evaluate(world[0], load_labels_from(labels_doc(PAIRS + SKIPPED)))
    d = result["default"]
    assert (d["tp"], d["fp"], d["fn"], d["tn"]) == (6, 2, 3, 2)
    assert d["precision"] == 6 / 8 == 0.75 and d["recall"] == 6 / 9
    assert (result["pairs"], result["positives"]) == (13, 9)
    cross = result["with_cross_pack"]
    assert (cross["tp"], cross["fp"], cross["fn"], cross["tn"]) == (8, 2, 1, 2)
    assert cross["precision"] == 8 / 10 and cross["recall"] == 8 / 9


def test_ac79_the_pairs_that_cannot_be_judged_are_listed_not_counted(world):
    result = evaluate(world[0], load_labels_from(labels_doc(PAIRS + SKIPPED)))
    assert result["skipped"] == [
        {"part": f"{W.PACK_A}/SM_Wep_Nowhere_01", "host": A_, "reason": "part_not_an_attachment"},  # sorted by (part, host)
        {"part": A_, "host": B_, "reason": "part_not_an_attachment"},
        {"part": SCOPE, "host": W.P[W.GRIP], "reason": "host_not_an_eligible_host"},
    ]


def test_ac79_a_ratio_with_an_empty_denominator_is_null(world):
    result = evaluate(world[0], load_labels_from(labels_doc([(SCOPE, G_, False)])))
    assert result["default"]["precision"] is None and result["default"]["recall"] is None
    assert result["default"]["tn"] == 1


def test_ac79_the_cli_prints_the_values_and_exits_0_at_the_gates(world, capsys, tmp_path):
    code, out = cli(world, capsys, tmp_path, PAIRS + SKIPPED, "--min-precision", "0.75", "--min-recall", "0.66")
    assert code == 0 and out["ok"] is True and out["failed"] == []
    assert out["default"] == {"tp": 6, "fp": 2, "fn": 3, "tn": 2, "precision": 0.75, "recall": 0.6667}
    assert out["with_cross_pack"]["precision"] == 0.8 and out["with_cross_pack"]["recall"] == 0.8889
    assert out["pairs"] == 13 and out["positives"] == 9 and out["max_tier"] == "same_pack_fit"
    assert out["predicted_from"] == ["compatible_hosts", "pending_hosts"]
    assert out["gates"] == {"min_precision": 0.75, "min_recall": 0.66}
    assert len(out["skipped"]) == 3


@pytest.mark.parametrize(("flags", "failing"), [
    (["--min-recall", "0.67"], ["min_recall"]),  # 0.6667 is below
    (["--min-precision", "0.76"], ["min_precision"]),
    (["--min-precision", "0.9", "--min-recall", "0.9"], ["min_precision", "min_recall"]),
])
def test_ac79_the_cli_exits_4_below_a_gate(world, capsys, tmp_path, flags, failing):
    code, out = cli(world, capsys, tmp_path, PAIRS, *flags)
    assert code == 4 and out["ok"] is False
    assert [f["gate"] for f in out["failed"]] == failing
    assert out["default"]["precision"] == 0.75  # the numbers are printed on a failure too


def test_ac79_without_gates_the_exit_is_0(world, capsys, tmp_path):
    assert cli(world, capsys, tmp_path, PAIRS)[0] == 0


def test_ac79_the_pack_flag_restricts_the_parts_judged(world, capsys, tmp_path):
    code, out = cli(world, capsys, tmp_path, PAIRS + ALT_PAIRS, "--pack", "FAKE_CompB")
    assert code == 0 and out["pairs"] == 3
    assert out["default"] == {"tp": 1, "fp": 0, "fn": 1, "tn": 1, "precision": 1.0, "recall": 0.5}
    assert out["with_cross_pack"]["recall"] == 1.0  # ALT - BETA is a cross_pack_fit pending host
    code, out = cli(world, capsys, tmp_path, PAIRS + ALT_PAIRS, "--pack", "FAKE_CompA")
    assert out["pairs"] == 13 and out["default"]["precision"] == 0.75
    code, out = cli(world, capsys, tmp_path, ALT_PAIRS, "--pack", "FAKE_CompA", "--min-recall", "0.1")
    assert code == 4 and out["default"]["recall"] is None  # nothing judged proves nothing


def test_ac79_a_missing_labels_file_is_exit_2_and_a_broken_one_exit_6(world, capsys, tmp_path):
    _, _, cat, _ = world
    cfg = H.write_config(tmp_path, cat)
    code, out = H.run(cfg, capsys, ["weapons", "attach-eval", "--labels", str(tmp_path / "nope.json")])
    assert code == 2 and out["ok"] is False
    code, out = H.run(cfg, capsys, ["weapons", "attach-eval"])
    assert code == 2 and "--labels" in out["error"]
    bad = copy.deepcopy(labels_doc(PAIRS))
    bad["pairs"][0]["score"] = 0.9  # a measured number has no place in a labels file (INV-17)
    code, out = cli(world, capsys, tmp_path, PAIRS, doc=bad)
    assert code == 6 and out["ok"] is False


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(schema="weapon-attach-labels/2"),
    lambda d: d.update(extra=1),
    lambda d: d.update(pairs={}),
    lambda d: d["pairs"][0].update(fits="yes"),
    lambda d: d["pairs"][0].pop("fits"),
    lambda d: d["pairs"][0].update(part="no_slash"),
    lambda d: d["pairs"].append(dict(d["pairs"][0])),  # the same pair labelled twice
    lambda d: d["pairs"].append("x"),
])
def test_ac79_labels_violations(mutate):
    doc = labels_doc(PAIRS)
    mutate(doc)
    assert validate_labels(doc)
    assert validate_labels(labels_doc(PAIRS)) == []


def test_ac79_load_labels_raises_schema_error_with_the_violations(tmp_path):
    path = tmp_path / "l.json"
    path.write_text(json.dumps({"schema": "x", "pairs": []}), encoding="utf-8")
    with pytest.raises(SchemaError):
        load_labels(path)


def load_labels_from(doc) -> list[dict]:
    assert validate_labels(doc) == []
    return doc["pairs"]


# --- weapons validate on the W8c directory --------------------------------------------------------------------------------


def validate_via_cli(world, capsys, tmp_path, doc):
    folder = tmp_path / "v"
    folder.mkdir(exist_ok=True)
    (folder / "directory.json").write_text(json.dumps(doc), encoding="utf-8")
    (folder / "excluded.json").write_text(json.dumps(world[1]), encoding="utf-8")
    return H.run(H.write_config(tmp_path, world[2]), capsys, ["weapons", "validate", "--directory", str(folder / "directory.json")])


def test_the_built_directory_with_its_compatibility_lists_validates_with_exit_0(world, capsys, tmp_path):
    code, out = validate_via_cli(world, capsys, tmp_path, world[0])
    assert code == 0 and out["ok"] is True and out["directory"] == "ok", out


@pytest.mark.parametrize(("name", "mutate", "message"), [
    ("host_twice", lambda a: a["compatible_hosts"].append(copy.deepcopy(a["compatible_hosts"][0])), "listed twice"),
    ("tier_of_nowhere", lambda a: a["compatible_hosts"][0].update(tier="maybe"), "attachment"),  # a schema error, quoted as the block
    ("pending_unsorted", lambda a: a["pending_hosts"].reverse(), "pending_hosts"),
    ("pending_as_ids", lambda a: a.update(pending_hosts=[e["host"] for e in a["pending_hosts"]]), "attachment"),
    ("host_not_eligible", lambda a: a["compatible_hosts"][0].update(host=W.P[W.GRIP]), "not an eligible host"),
])
def test_a_hand_broken_compatibility_list_exits_6(world, capsys, tmp_path, name, mutate, message):
    doc = copy.deepcopy(world[0])
    mutate(next(r for r in doc["weapons"] if r["id"] == MAG)["attachment"])
    code, out = validate_via_cli(world, capsys, tmp_path, doc)
    assert code == 6 and out["directory"] == "invalid", name
    assert any(message in e for e in out["directory_errors"]), out["directory_errors"]
