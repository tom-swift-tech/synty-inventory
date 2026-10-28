"""E3.6: the receiver-bottom plane is taken with every magazine node removed (F1; docs/weapon_attach_geometry.md 3.7 step 1, errata E3.6; AC133, AC136, AC138).

The worlds are the synthetic hosts of ``fixtures/weapons/e3_well_meshes.py`` (one receiver block, a drum and a stick magazine; see its docstring for the
numbers). They are built as real GLBs and go through the directory build, so the references come from ``fit_geometry.host_features`` and the verdicts from
``compat.pair_verdict`` (recorded by a spy), never from a hand-set feature. The oracle of ``attach-calibrate`` (``cli._gather_oracle``) is run over the same
directory. Every expected number is a LITERAL worked out by hand from the fixture (receiver bottom u = 0, plane 0 - 0.002 = -0.002, drum section
0.10 x 0.08, stick section 0.05 x 0.024), never read from the rules file or from a constant under test.

Deliberate breaks, on a scratch copy (reported with the slice):

* only the reference node removed (today's ``well(node)``): ``test_two_seat_host_gets_a_reference_when_the_plane_would_miss_the_drum`` and the
  directory / calibrate agreement go red;
* only the reference child removed from the oracle's ``ref_host`` (today's ``well_pos``): ``test_oracle_reference_removes_every_magazine_node`` goes red;
* every node of the host removed (the receiver goes too): the two guards (one seat, two seats without overlap) go red.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "weapons"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load("e3_well_meshes")

from synty_inventory.weapons import calibrate as fc  # noqa: E402
from synty_inventory.weapons import cli as wcli  # noqa: E402
from synty_inventory.weapons import compat  # noqa: E402
from synty_inventory.weapons import directory as dirmod  # noqa: E402
from synty_inventory.weapons import rules as rules_mod  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402

ABS = 1e-4  # stored measures are rounded to 1e-4 m

# this test's own copy of the well literals of spec 4.1 (the oracle reads nothing else of the block that these worlds use)
FIT = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {"window_m": 0.010, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005, "pitch_max_m": 0.040,
             "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85], "default_seat_len_m": 0.20,
             "sight_clear_m": 0.010},
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.060},
    "clamp": {"overhang_max_m": 0.010, "ratio_min": 1.0},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {"end_slab_m": 0.010, "round_min": 0.8, "circ_min": 0.75, "barrel_od_max_m": 0.060, "od_ratio": [0.85, 2.00], "inner_ratio": [0.47, 1.21],
             "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2},
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}
TOL = 0.15  # well.tol, the literal the agreement test compares the oracle's reading with

TWO, ONE, APART = E.pid(E.TWO_SEAT), E.pid(E.ONE_SEAT), E.pid(E.APART)
STICK, DRUM, ODD = E.pid(E.TWIN_STICK), E.pid(E.TWIN_DRUM), E.pid(E.ODD)
DRUM_NODE = {h: f"{h.split('/', 1)[1]}_Mag_Drum" for h in (TWO, ONE, APART)}
STICK_NODE = {h: f"{h.split('/', 1)[1]}_Mag_Stick" for h in (TWO, APART)}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The world built once: the directory, the host features, every pair verdict ``compat`` computed, and the oracle's positives and observations."""
    world = E.world()
    cat, root = E.W.write_world(tmp_path_factory.mktemp("e3_well"), world)
    shipped = rules_mod.load_rules()
    verdicts: dict[tuple, str] = {}
    positives: list[dict] = []
    mp = pytest.MonkeyPatch()
    real_verdict, real_observe = compat.pair_verdict, fc.observe_positive

    def spy_verdict(part, host, fit_rules, seat=None):
        got = real_verdict(part, host, fit_rules, seat)
        if part["slot"] == "magazine":
            verdicts[(part["id"], host["id"])] = got.value
        return got

    def spy_observe(pos, rules):
        if pos["slot"] == "magazine":
            positives.append(pos)
        return real_observe(pos, rules)

    mp.setattr(compat, "pair_verdict", spy_verdict)
    mp.setattr(fc, "observe_positive", spy_observe)
    try:
        feats: dict = {}
        directory, _ex, _report = dirmod.build_directory_report(
            cat, overrides=empty_overrides(), pack_settings=E.W.pack_settings(world), rules=E.W.sight_rules(), threejs_v2_dir=root,
            geometry_cache={}, host_feats=feats)
        shipped["attachment_rules"]["fit_geometry"] = FIT
        oracle = wcli._gather_oracle(directory, root, shipped, None)
    finally:
        mp.undo()
    return SimpleNamespace(directory=directory, feats=feats, verdicts=verdicts, positives=positives, oracle=oracle)


def magazine(b, host):
    return b.feats[host]["slots"]["magazine"]


def measured(b, host, part):
    """The oracle's ``well_off`` of the twin ``part`` on ``host`` (None when it left an ``unmeasured`` record instead)."""
    got = [o for o in b.oracle["observations"] if o["host"] == host and o["part"] == part and o["slot"] == "magazine"]
    assert len(got) == 1, got
    return got[0]["value"] if got[0]["key"] == "well_off" else None


# -- F1: the plane is taken with every magazine node removed ------------------------------------------------------------


def test_two_seat_host_gets_a_reference_when_the_plane_would_miss_the_drum(built):
    # The drum (the mount's own seat) is the reference. With the host minus the drum only, the stick is still there: it stands lower than the drum (bottom
    # -0.155 against the drum's -0.10) and covers the drum's centre line, so the lowest crossing is the stick's bottom, the plane (-0.157) lies under the
    # whole drum and meets no edge: no reference. With the stick removed too the lowest crossing is the receiver bottom, 0.
    ref = magazine(built, TWO).get("well_ref")
    assert ref is not None
    assert ref["source"] == "child"
    assert (ref["length_m"], ref["width_m"]) == pytest.approx((0.10, 0.08), abs=ABS)  # the drum's cross-section: 0.10 along f, 0.08 across
    assert ref["u_rb"] == pytest.approx(0.0, abs=ABS)  # the receiver bottom, not the stick's bottom (-0.155)
    plane = ref["u_rb"] - 0.002
    assert -0.10 + 0.005 <= plane <= 0.02 - 0.005  # inside the drum's u range (-0.10..0.02) by at least 5 mm at both ends


def test_the_stick_seat_reference_follows_the_same_plane(built):
    # the stick's own seat reference (A1) is taken with the drum removed as well: with the drum still in the host its centre line meets the drum's bottom
    # (u -0.10) first and the plane would be -0.102; the stick section there (0.05 x 0.024, a prism) does not move, the plane does
    refs = magazine(built, TWO)["well_refs"]
    assert sorted(refs) == [DRUM_NODE[TWO], STICK_NODE[TWO]]
    for node, want in ((DRUM_NODE[TWO], (0.10, 0.08)), (STICK_NODE[TWO], (0.05, 0.024))):
        assert refs[node]["u_rb"] == pytest.approx(0.0, abs=ABS), node
        assert (refs[node]["length_m"], refs[node]["width_m"]) == pytest.approx(want, abs=ABS), node


def test_a_non_twin_part_is_judged_on_the_two_seat_host(built):
    # today the host has no reference, so every part of its magazine slot is not_judged; the odd part (0.030 x 0.020 against a 0.10 x 0.08 well) is no_fit
    assert built.verdicts[(ODD, TWO)] == "no_fit"


# -- guards: green before and after -----------------------------------------------------------------------------------


def test_one_seat_host_unchanged(built):
    mag = magazine(built, ONE)
    assert "well_refs" not in mag  # one listed child: no seats
    assert mag["well_ref"]["u_rb"] == pytest.approx(0.0, abs=ABS)
    assert (mag["well_ref"]["length_m"], mag["well_ref"]["width_m"]) == pytest.approx((0.10, 0.08), abs=ABS)
    assert built.verdicts[(DRUM, ONE)] == "fit"


def test_two_seat_host_without_overlap_unchanged(built):
    # the stick stands 0.08 ahead of the drum's centre line and is not on it: the host minus the drum alone already meets the receiver bottom
    mag = magazine(built, APART)
    for ref in (mag["well_ref"], mag["well_refs"][DRUM_NODE[APART]]):
        assert ref["u_rb"] == pytest.approx(0.0, abs=ABS)
        assert (ref["length_m"], ref["width_m"]) == pytest.approx((0.10, 0.08), abs=ABS)
    stick = mag["well_refs"][STICK_NODE[APART]]
    assert stick["u_rb"] == pytest.approx(0.0, abs=ABS)
    assert (stick["length_m"], stick["width_m"]) == pytest.approx((0.05, 0.024), abs=ABS)
    assert built.verdicts[(STICK, APART)] == "fit" and built.verdicts[(DRUM, APART)] == "fit"


# -- the oracle: the same reference host as the directory -----------------------------------------------------------------


def test_oracle_reference_removes_every_magazine_node(built):
    # the host of the oracle's reference is the host minus EVERY magazine node of the mount: only the receiver block and its barrel tube are left (lowest
    # vertex u = 0, the receiver bottom). Today it drops the twinned child alone, so the other magazine is still there (stick bottom -0.155 under the
    # drum twin's reference, drum bottom -0.10 under the stick twin's)
    lowest = {p["part"]: float(p["ref_host"][0][:, 2].min()) for p in built.positives if p["host"] == TWO}
    assert lowest == pytest.approx({DRUM: 0.0, STICK: 0.0}, abs=ABS)
    # and the same on a host whose seats do not overlap, and on the one-seat host (nothing else to drop)
    for host in (ONE, APART):
        for pos in (p for p in built.positives if p["host"] == host):
            assert float(pos["ref_host"][0][:, 2].min()) == pytest.approx(0.0, abs=ABS), (host, pos["part"])


def test_directory_and_calibrate_agree_on_the_standard_twin(built):
    # the stick twin on the two-seat host: `fit` in the directory (signals name the evidence), 0.000 in calibrate. Today the directory leaves it
    # unverified (the mount has no well reference, so the pair pass cuts no section) while calibrate reads 0.000 from the per-node reference
    assert built.verdicts[(STICK, TWO)] == "fit"
    off = measured(built, TWO, STICK)
    assert off == pytest.approx(0.0, abs=ABS)
    assert off <= TOL
    entry = next(e for w in built.directory["weapons"] if w["id"] == STICK for e in w["attachment"]["compatible_hosts"] if e["host"] == TWO)
    assert entry["tier"] == "twin" and entry["signals"] == ["twin", "well_entry"]


def test_drum_twin_is_judged(built):
    # the drum twin was not_judged (no reference) on the directory side and unmeasured (`no_well_reference`) on the oracle side. This asserts only that
    # it is judged now, never fit: E3.12 owns what the live drum twin reads
    assert built.verdicts[(DRUM, TWO)] != "not_judged"
    assert measured(built, TWO, DRUM) is not None
    assert built.oracle["observations"] and not [o for o in built.oracle["observations"] if o["key"] == "unmeasured" and o["host"] == TWO]
