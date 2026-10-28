"""W8p ``weapons attach-eval``: the default view scores what the default export lists (docs/weapon_attachments.md 13.9 "Eval"; AC127).

A synthetic directory (records with just the fields ``evaluate`` reads) and labels as ids and booleans. Every expected count below is worked out by hand
from the table; the gates are run through ``cmd`` with the directory loader replaced, so the real printing and gating code runs.

  host   in the part's lists          label   default        with_cross_pack   same_pack_only
  LC     compatible, cross_pack_fit   yes     TP             TP                FN
  PC     pending,    cross_pack_fit   yes     FN             TP                FN
  PS     pending,    same_pack_fit    yes     TP             TP                TP
  LT     compatible, twin             yes     TP             TP                TP
  PO     pending,    override         yes     TP             TP                TP
  LCn    compatible, cross_pack_fit   no      FP             FP                TN
  PCn    pending,    cross_pack_fit   no      TN             FP                TN
  PSn    pending,    same_pack_fit    no      FP             FP                FP
  NO     (in no list)                 yes     FN             FN                FN
  NOn    (in no list)                 no      TN             TN                TN
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from synty_inventory.weapons import eval as eval_mod
from synty_inventory.weapons import directory as directory_mod
from synty_inventory.weapons.eval import evaluate

PART = "P/Wep_Part_01"
HOSTS = ["LC", "PC", "PS", "LT", "PO", "LCn", "PCn", "PSn", "NO", "NOn"]


def host_rec(name):
    return {"id": f"Q/{name}", "role": "whole", "kind": "ranged", "hold_class": "long_gun"}


def directory():
    comp = [("LC", "cross_pack_fit"), ("LT", "twin"), ("LCn", "cross_pack_fit")]
    pend = [("PC", "cross_pack_fit"), ("PS", "same_pack_fit"), ("PO", "override"), ("PCn", "cross_pack_fit"), ("PSn", "same_pack_fit")]
    # G1 S9 re-pin (spec 3.10, AC142, Q-G12): the gates read the label-era slots only, and the four geometry slots (magazine among them) are descriptive.
    # The part is a laser_light, so the hand-counted table below is still the one the gates read.
    att = {"slot": "laser_light", "compatible_hosts": [{"host": f"Q/{h}", "tier": t} for h, t in comp],
           "pending_hosts": [{"host": f"Q/{h}", "tier": t} for h, t in pend]}
    return {"weapons": [{"id": PART, "role": "part", "kind": None, "hold_class": "none", "attachment": att}, *(host_rec(h) for h in HOSTS)]}


LABELS = {"LC": True, "PC": True, "PS": True, "LT": True, "PO": True, "LCn": False, "PCn": False, "PSn": False, "NO": True, "NOn": False}
PAIRS = [{"part": PART, "host": f"Q/{h}", "fits": fits} for h, fits in LABELS.items()]


def counts(block):
    return (block["tp"], block["fp"], block["fn"], block["tn"])


def test_ac127_the_three_views_count_the_hand_worked_cells():
    got = evaluate(directory(), PAIRS)
    assert counts(got["default"]) == (4, 2, 2, 2)  # LC LT PS PO / LCn PSn / PC NO / PCn NOn
    assert counts(got["with_cross_pack"]) == (5, 3, 1, 1)  # PC joins the TPs, PCn the FPs
    assert counts(got["same_pack_only"]) == (3, 1, 3, 3)  # LC drops out of the TPs, LCn out of the FPs
    assert (got["pairs"], got["positives"]) == (10, 6)


def test_ac127_a_listed_cross_entry_labelled_yes_is_a_tp_of_default_and_with_cross_pack_and_a_fn_of_same_pack_only():
    one = [{"part": PART, "host": "Q/LC", "fits": True}]
    got = evaluate(directory(), one)
    assert counts(got["default"]) == (1, 0, 0, 0) and counts(got["with_cross_pack"]) == (1, 0, 0, 0) and counts(got["same_pack_only"]) == (0, 0, 1, 0)


def test_ac127_a_pending_cross_entry_labelled_yes_is_a_fn_of_default_and_a_tp_of_with_cross_pack():
    one = [{"part": PART, "host": "Q/PC", "fits": True}]
    got = evaluate(directory(), one)
    assert counts(got["default"]) == (0, 0, 1, 0) and counts(got["with_cross_pack"]) == (1, 0, 0, 0) and counts(got["same_pack_only"]) == (0, 0, 1, 0)


def test_ac127_a_pending_same_pack_entry_labelled_yes_is_a_tp_of_default():
    one = [{"part": PART, "host": "Q/PS", "fits": True}]
    got = evaluate(directory(), one)
    assert all(counts(got[v]) == (1, 0, 0, 0) for v in ("default", "with_cross_pack", "same_pack_only"))


def test_ac127_a_pending_cross_entry_labelled_no_is_a_tn_of_default_and_a_listed_one_a_fp():
    got = evaluate(directory(), [{"part": PART, "host": "Q/PCn", "fits": False}])
    assert counts(got["default"]) == (0, 0, 0, 1) and counts(got["with_cross_pack"]) == (0, 1, 0, 0)
    got = evaluate(directory(), [{"part": PART, "host": "Q/LCn", "fits": False}])
    assert counts(got["default"]) == (0, 1, 0, 0) and counts(got["same_pack_only"]) == (0, 0, 0, 1)


def test_ac127_the_ratios_of_each_view():
    got = evaluate(directory(), PAIRS)
    assert got["default"]["precision"] == 4 / 6 and got["default"]["recall"] == 4 / 6
    assert got["with_cross_pack"]["precision"] == 5 / 8 and got["with_cross_pack"]["recall"] == 5 / 6
    assert got["same_pack_only"]["precision"] == 3 / 4 and got["same_pack_only"]["recall"] == 3 / 6


@pytest.fixture
def run(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(directory_mod, "load_directory", lambda cat: directory())
    monkeypatch.setattr(eval_mod, "_catalogs", lambda args, cfg: Path("."))

    def go(*, min_precision=None, min_recall=None):
        labels = tmp_path / "labels.json"
        labels.write_text(json.dumps({"schema": "weapon-attach-labels/1", "pairs": PAIRS}), encoding="utf-8")
        args = SimpleNamespace(labels=str(labels), min_precision=min_precision, min_recall=min_recall, pack=None)
        code = eval_mod.cmd(args, None)
        return code, json.loads(capsys.readouterr().out)
    return go


def test_ac127_the_json_names_each_view_with_the_tiers_it_reads_and_max_tier_is_gone(run):
    code, out = run()
    assert code == 0 and "max_tier" not in out
    assert out["views"]["default"]["predicted_from"] == {"compatible_hosts": ["override", "twin", "same_pack_fit", "cross_pack_fit"],
                                                         "pending_hosts": ["override", "twin", "same_pack_fit"]}
    assert out["views"]["with_cross_pack"]["predicted_from"] == {"compatible_hosts": ["override", "twin", "same_pack_fit", "cross_pack_fit"],
                                                                 "pending_hosts": ["override", "twin", "same_pack_fit", "cross_pack_fit"]}
    assert out["views"]["same_pack_only"]["predicted_from"] == {"compatible_hosts": ["override", "twin", "same_pack_fit"],
                                                                "pending_hosts": ["override", "twin", "same_pack_fit"]}
    assert set(out["views"]) == {"default", "with_cross_pack", "same_pack_only"}
    assert out["predicted_from"] == ["compatible_hosts", "pending_hosts"]  # the lists read, unchanged
    assert (out["pairs"], out["positives"]) == (10, 6)
    assert (out["default"]["tp"], out["default"]["fp"], out["default"]["fn"], out["default"]["tn"]) == (4, 2, 2, 2)
    assert out["same_pack_only"]["recall"] == 0.5 and out["with_cross_pack"]["recall"] == 0.8333


def test_ac127_the_gates_read_the_default_view(run):
    # default: precision 4/6 = 0.6667, recall 4/6 = 0.6667; same_pack_only: precision 0.75, recall 0.5; with_cross_pack: 0.625 / 0.8333
    code, out = run(min_precision=0.66, min_recall=0.66)
    assert code == 0 and out["ok"] is True and out["failed"] == []
    code, out = run(min_precision=0.67)
    assert code == 4 and [f["gate"] for f in out["failed"]] == ["min_precision"] and out["failed"][0]["got"] == 0.6667
    code, out = run(min_recall=0.67)  # with_cross_pack (0.8333) would pass this, same_pack_only (0.5) and a capped default would fail it
    assert code == 4 and [f["gate"] for f in out["failed"]] == ["min_recall"] and out["failed"][0]["got"] == 0.6667
    code, out = run(min_precision=0.7)  # same_pack_only (0.75) would pass this
    assert code == 4
