"""W8e (a): the default attach-preview sample takes ``same_pack_fit`` pairs before ``cross_pack_fit`` ones.

Run on the hand-written world of ``fixtures/weapons/w8e_plan_directory.py`` (see its docstring for the hand-derived bests).
Before W8e the sample was one best pair per attachment, round-robin over the slots in part-id order, so a slot whose
cross-pack part sorted first showed that one and never a same-pack one. Hand-derived expectation, tier first then slot
round-robin (slot order optic, muzzle, underbarrel, magazine, laser_light), part id inside a slot:

* same_pack_fit bests: optic [B, C], muzzle [A (on Host_A)], laser_light [Laser_A]. Round 1: Optic_B, Muzzle_A, Laser_A; round 2:
  Optic_C (muzzle and laser_light are used up).
* then cross_pack_fit bests: optic [A], muzzle [B], magazine [Mag_A]: Optic_A, Muzzle_B, Mag_A.
"""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

from synty_inventory.weapons import preview

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8e_plan_directory", _FIX / "w8e_plan_directory.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

P = "W8E_Plan/"
SAME, CROSS = "same_pack_fit", "cross_pack_fit"
TWINS = [(P + "Optic_C_Same", P + "Host_B"), (P + "Under_A_Twin", P + "Host_B")]
# (part, host, tier) of the whole non-twin sample, in order
SAMPLE = [
    (P + "Optic_B_Same", P + "Host_A", SAME),
    (P + "Muzzle_A_Mixed", P + "Host_A", SAME),  # its best host is listed second
    (P + "Laser_A_Same", P + "Host_A", SAME),
    (P + "Optic_C_Same", P + "Host_A", SAME),
    (P + "Optic_A_Cross", P + "Host_X", CROSS),
    (P + "Muzzle_B_Cross", P + "Host_X", CROSS),
    (P + "Mag_A_Cross", P + "Host_X", CROSS),
]


def others_of(pairs):
    return [(p["part"], p["host"], p["tier"]) for p in pairs if not p["twin"]]


def test_same_pack_fit_pairs_come_before_cross_pack_fit_pairs_in_the_sample():
    pairs, skipped = preview.plan_pairs(W.directory())
    assert skipped == {}
    assert others_of(pairs) == SAMPLE
    tiers = [t for _, _, t in SAMPLE]
    assert tiers == ["same_pack_fit"] * 4 + ["cross_pack_fit"] * 3  # no cross_pack_fit pair ahead of a same_pack_fit pair


def test_a_cut_sample_keeps_the_better_tier_and_still_round_robins_the_slots():
    # with 4 others the old part-id order would have taken Optic_A_Cross (cross_pack_fit) first and cut Optic_C_Same
    pairs, _ = preview.plan_pairs(W.directory(), others=4)
    assert others_of(pairs) == SAMPLE[:4]
    assert [p["slot"] for p in pairs if not p["twin"]] == ["optic", "muzzle", "laser_light", "optic"]
    assert others_of(preview.plan_pairs(W.directory(), others=1)[0]) == SAMPLE[:1]
    # 5 others reach into the cross tier by one pair
    assert others_of(preview.plan_pairs(W.directory(), others=5)[0]) == SAMPLE[:5]


def test_the_best_host_of_an_attachment_is_its_best_tier_not_its_first_listed():
    pairs, _ = preview.plan_pairs(W.directory())
    muzzle = [p for p in pairs if p["part"] == P + "Muzzle_A_Mixed"]
    assert [(p["host"], p["tier"]) for p in muzzle] == [(P + "Host_A", SAME)]  # Host_X (cross) was listed first


def test_twins_come_first_and_every_slot_with_a_candidate_is_in_the_plan():
    pairs, _ = preview.plan_pairs(W.directory())
    assert [(p["part"], p["host"]) for p in pairs[:2]] == TWINS and all(p["twin"] for p in pairs[:2])
    assert not any(p["twin"] for p in pairs[2:])
    assert {p["slot"] for p in pairs} == {"optic", "muzzle", "underbarrel", "magazine", "laser_light"}  # underbarrel via its twin
    assert {p["slot"] for p in pairs if not p["twin"]} == {"optic", "muzzle", "magazine", "laser_light"}  # slot coverage kept
    assert len({(p["part"], p["host"]) for p in pairs}) == len(pairs)


def test_the_sample_is_deterministic_and_independent_of_the_directory_order():
    want = preview.plan_pairs(W.directory())[0]
    assert preview.plan_pairs(W.directory())[0] == want
    for seed in (1, 2, 3):
        shuffled = W.directory()
        random.Random(seed).shuffle(shuffled["weapons"])
        assert preview.plan_pairs(shuffled)[0] == want


def test_ids_still_renders_every_usable_pair_in_the_listed_order_and_the_default_count_is_twelve():
    pairs, _ = preview.plan_pairs(W.directory(), ids={P + "Muzzle_A_Mixed"})
    assert [(p["host"], p["tier"]) for p in pairs] == [(P + "Host_X", CROSS), (P + "Host_A", SAME)]  # unchanged: all pairs
    assert preview.DEFAULT_OTHERS == 12


@pytest.mark.parametrize("limit", [1, 2, 3, 5])
def test_limit_cuts_the_list_twins_first(limit):
    pairs, _ = preview.plan_pairs(W.directory(), limit=limit)
    assert [(p["part"], p["host"]) for p in pairs[:2]] == TWINS[:limit]
    assert len(pairs) == limit
