"""G1 S9 ``weapons attach-calibrate`` (docs/weapon_attach_geometry.md 3.11, 4.2, errata E1.1; AC137, INV-24).

Two layers. The pure maths (``calibrate.calibrate``) is driven with hand-written observations and a LITERAL ``fit_geometry`` block (``FIT``: this test's own
copy of the literals of spec 4.1, never read from the rules file, so a rules edit cannot loosen a bound here). The verb is run over ``g1_tools_world``, a
synthetic world of boxes, lofts and tubes whose observed values are worked out by hand:

  overhang      the toothed carbine's baked optic: foot 0.196 long, the run 8 teeth at 23.5 mm = 0.188 long          -> 0.196 - 0.188 = 0.008
  ratio         the same foot, 0.02 wide, over the run's 0.017 width (tooth profile half-width 8.5 mm)              -> 0.02 / 0.017 = 1.1765
  depth         the foot underside sits on the crests                                                               -> 0.0
  circ          the hexagonal barrel (circumradius 12 mm) of the preset, proved by a face ring (E1.1)               -> 3 sqrt(3) / (2 pi) = 0.8270
  od_ratio      mate diameter over the barrel OD: the ring device 0.020 over 0.021 (ringed rifle, OD 2 x 10.5 mm)  -> 0.9524
                the plain device (25 mm square, diagonal 0.0354) over 0.021, over the hexagon's 0.024               -> 1.6857, 1.475
                the suppressor (0.0260) over the rod rifle's 0.017                                                  -> 1.5294
  inner_ratio   the ring device's inner ring 0.015 over the ringed rifle's OD 0.021                                 -> 0.7143
  axis_offset, axis_tilt, well_off   every positive is built on its axis / well                                      -> 0.0
  frame ring    the Uzi-type SMG's end ring, inner diameter 2 x 7.5 mm                                              -> 0.015

Deliberate breaks, on a scratch copy: a literal dropped (a ``fit_geometry`` literal lowered under its positives: ``clamp.overhang_max_m`` 0.007, or
``bore.circ_min`` raised over 0.827); the ``bore.circ_min`` row removed from ``_ROWS``.
"""

from __future__ import annotations

import copy
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


T = _load("g1_tools_world")
H = _load("review_helpers")

from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import calibrate as FC  # noqa: E402
from synty_inventory.weapons import guards, rules as rules_mod  # noqa: E402

# this test's own copy of the literals of spec 4.1 (the shipped values at the G1 spec); a change of the rules file does not move it
FIT = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {"window_m": 0.01, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005, "pitch_max_m": 0.04,
             "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85], "default_seat_len_m": 0.2,
             "sight_clear_m": 0.01},
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.06},
    "clamp": {"overhang_max_m": 0.01, "ratio_min": 1.0},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {"end_slab_m": 0.01, "round_min": 0.8, "circ_min": 0.75, "barrel_od_max_m": 0.06, "od_ratio": [0.85, 2.0], "inner_ratio": [0.47, 1.21],
             "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2},
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}
FRAME_MAX = 0.025  # geometry._FRAME_BORE_MAX_M at the spec
ROWS = ["clamp.overhang_max_m", "clamp.ratio_min", "rail.zone", "depth", "bore.od_ratio", "bore.inner_ratio", "bore.axis_offset_max_m",
        "bore.axis_tilt_max_deg", "bore.circ_min", "well.tol", "geometry._FRAME_BORE_MAX_M"]


def block(**changes) -> dict:
    out = copy.deepcopy(FIT)
    for dotted, value in changes.items():
        group, key = dotted.split("__")
        out[group][key] = value
    return out


def obs(key, value, cls="baked", slot="optic", tags=None):
    return {"key": key, "value": value, "cls": cls, "slot": slot, "host": "P/Host", "part": "P/Part", "tags": [f"{slot}:{cls}"] if tags is None else tags}


ALL = [
    obs("overhang", 0.008), obs("ratio", 1.1765), obs("zone", 0.4), obs("depth", 0.0),
    obs("od_ratio", 1.5, slot="muzzle"), obs("inner_ratio", 0.71, slot="muzzle"), obs("axis_offset", 0.0, slot="muzzle"), obs("axis_tilt", 0.0, slot="muzzle"),
    obs("circ", 0.827, cls="preset", slot="muzzle"), obs("well_off", 0.0, slot="magazine"), obs("frame_ring", 0.015, cls="frame", slot=None, tags=[]),
]


def calibrate(observations, rules=None, frame=FRAME_MAX):
    return FC.calibrate(observations, rules or block(), frame_bore_max_m=frame)


def row(result, literal):
    return next(r for r in result["rows"] if r["literal"] == literal)


# -- the maths ---------------------------------------------------------------------------------------------------


def test_every_literal_of_4_2_has_a_row_the_frame_constant_and_the_circ_min_row_included():
    result = calibrate(ALL)
    assert [r["literal"] for r in result["rows"]] == ROWS and tuple(ROWS) == FC.ROW_IDS
    assert result["ok"] is True and result["failed"] == []


def test_upper_and_lower_rows_print_the_extreme_the_margin_and_the_literal():
    result = calibrate(ALL)
    over = row(result, "clamp.overhang_max_m")
    assert (over["kind"], over["value"], over["observed"], over["margin"], over["n"]) == ("upper", 0.01, 0.008, 0.002, 1)
    ratio = row(result, "clamp.ratio_min")
    assert (ratio["kind"], ratio["value"], ratio["observed"], ratio["margin"]) == ("lower", 1.0, 1.1765, 0.1765)
    circ = row(result, "bore.circ_min")  # errata E1.1: the lower bound over the evidence-(ii) bore positives
    assert (circ["kind"], circ["value"], circ["observed"], circ["margin"], circ["positives"]) == (
        "lower", 0.75, 0.827, 0.077, {"preset": {"n": 1, "min": 0.827, "max": 0.827}})
    zone = row(result, "rail.zone")
    assert (zone["kind"], zone["value"], zone["observed"], zone["margin"]) == ("band", [0.15, 0.85], [0.4, 0.4], [0.25, 0.45])
    frame = row(result, "geometry._FRAME_BORE_MAX_M")
    assert (frame["value"], frame["observed"], frame["margin"]) == (0.025, 0.015, 0.01)


def test_ac137_a_literal_lowered_under_its_positives_fails_and_is_named():
    result = calibrate(ALL, block(clamp__overhang_max_m=0.007))
    assert result["ok"] is False and result["failed"] == [{"literal": "clamp.overhang_max_m", "reason": "exceeded"}]
    bad = row(result, "clamp.overhang_max_m")
    assert bad["ok"] is False and bad["margin"] == -0.001 and bad["violations_n"] == 1


def test_inv24_a_lower_bound_is_enforced_too_circ_min_over_its_minimum_fails():
    result = calibrate(ALL, block(bore__circ_min=0.83))  # the positive fills 0.827 of its circle
    assert result["failed"] == [{"literal": "bore.circ_min", "reason": "exceeded"}]
    assert calibrate(ALL, block(bore__circ_min=0.827))["ok"] is True  # the literal may equal the extreme


@pytest.mark.parametrize(("literal", "dropped"), [
    ("bore.circ_min", "circ"), ("clamp.overhang_max_m", "overhang"), ("clamp.ratio_min", "ratio"), ("rail.zone", "zone"),
    ("bore.od_ratio", "od_ratio"), ("bore.inner_ratio", "inner_ratio"), ("bore.axis_offset_max_m", "axis_offset"),
    ("bore.axis_tilt_max_deg", "axis_tilt"), ("well.tol", "well_off"), ("geometry._FRAME_BORE_MAX_M", "frame_ring"),
])
def test_a_literal_with_no_positives_fails(literal, dropped):
    result = calibrate([o for o in ALL if o["key"] != dropped])
    assert result["failed"] == [{"literal": literal, "reason": "no_positives"}]
    assert row(result, literal)["covered"] is False


def test_the_depth_row_is_a_review_row_listed_never_enforced():
    outside = calibrate([o for o in ALL if o["key"] != "depth"] + [obs("depth", 0.02)])  # above the review band's 0.003
    assert outside["ok"] is True
    depth = row(outside, "depth")
    assert depth["ok"] is True and depth["outside_n"] == 1 and depth["observed"] == [0.02, 0.02]
    assert calibrate([o for o in ALL if o["key"] != "depth"])["ok"] is True  # no positives is no failure for a review row


def test_a_listed_exception_is_counted_apart_and_bounds_nothing():
    wide = [o for o in ALL if o["key"] != "overhang"] + [obs("overhang", 0.008), obs("overhang", 0.05, cls="preset")]
    assert calibrate(wide, block(clamp__overhang_max_m=0.01))["failed"] == [{"literal": "clamp.overhang_max_m", "reason": "exceeded"}]
    rules = block(clamp__overhang_max_m=0.01)
    rules["exceptions"] = ["optic:preset"]  # class keys `<slot>:<class>`, no asset ids
    result = calibrate(wide, rules)
    assert result["ok"] is True
    over = row(result, "clamp.overhang_max_m")
    assert (over["n"], over["excepted"], over["observed"]) == (1, 1, 0.008)


def test_the_frame_constant_is_calibrated_like_a_rule_literal():
    result = calibrate(ALL, frame=0.014)  # the end ring measured 0.015
    assert result["failed"] == [{"literal": "geometry._FRAME_BORE_MAX_M", "reason": "exceeded"}]


def test_what_could_not_be_measured_is_counted_by_name_not_dropped():
    miss = {"key": "unmeasured", "value": None, "cls": "twin", "slot": "magazine", "host": "P/H", "part": "P/X", "tags": [], "reason": "no_well_reference"}
    assert calibrate(ALL + [miss, dict(miss)])["unmeasured"] == {"magazine:twin:no_well_reference": 2}


def test_observations_round_to_noise_before_they_meet_a_literal():
    # 0.0100000001 - 1e-10 float noise must not read as an overrun of a 0.010 literal
    assert calibrate([o for o in ALL if o["key"] != "overhang"] + [obs("overhang", 0.01 + 1e-10)])["ok"] is True


# -- the verb over the synthetic world ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("g1_calibrate")
    cat, root, directory, _excluded = T.build(tmp)
    return {"tmp": tmp, "cat": cat, "root": root, "directory": directory,
            "cfg": H.write_config(tmp, cat, extra=[f'threejs_v2: "{root.as_posix()}"'])}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    monkeypatch.setattr(export_mod, "_repo_root", lambda: None)  # pytest's tmp dirs sit inside this checkout
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def with_rules(monkeypatch, **changes):
    """The shipped rules with the ``fit_geometry`` block replaced by this test's literal block (plus ``changes``): the verb reads only that block."""
    shipped = rules_mod.load_rules()
    shipped["attachment_rules"]["fit_geometry"] = block(**changes)
    monkeypatch.setattr(rules_mod, "load_rules", lambda path=None: shipped)


def calibrate_cli(world, capsys, *flags):
    return H.run(world["cfg"], capsys, ["weapons", "attach-calibrate", *flags])


def test_ac137_the_verb_exits_0_and_prints_every_row_of_4_2(world, capsys, monkeypatch):
    with_rules(monkeypatch)
    code, out = calibrate_cli(world, capsys)
    assert code == 0 and out["ok"] is True and out["failed"] == [] and out["unmeasured"] == {}
    rows = {r["literal"]: r for r in out["rows"]}
    assert list(rows) == ROWS
    # the maxima and minima of the oracle, worked out by hand in the module docstring
    assert (rows["clamp.overhang_max_m"]["observed"], rows["clamp.overhang_max_m"]["margin"]) == (0.008, 0.002)
    assert (rows["clamp.ratio_min"]["observed"], rows["clamp.ratio_min"]["margin"]) == (1.1765, 0.1765)
    assert rows["depth"]["observed"] == [0.0, 0.0] and rows["depth"]["ok"] is True
    assert rows["bore.od_ratio"]["observed"] == [0.9524, 1.6857]
    assert rows["bore.inner_ratio"]["observed"] == [0.7143, 0.7143]
    assert rows["bore.axis_offset_max_m"]["observed"] == 0.0 and rows["bore.axis_tilt_max_deg"]["observed"] == 0.0
    assert rows["well.tol"]["observed"] == 0.0
    assert rows["geometry._FRAME_BORE_MAX_M"]["observed"] == 0.015 and rows["geometry._FRAME_BORE_MAX_M"]["positives"] == {"frame": {"n": 1, "min": 0.015, "max": 0.015}}
    # errata E1.1: the circ_min row is the lower bound over the evidence-(ii) bore positives: one, the hexagonal barrel, 3 sqrt(3) / (2 pi)
    circ = rows["bore.circ_min"]
    assert (circ["observed"], circ["margin"], circ["value"], circ["n"]) == (0.827, 0.077, 0.75, 1)
    assert circ["positives"] == {"preset": {"n": 1, "min": 0.827, "max": 0.827}}
    zone = rows["rail.zone"]
    assert zone["covered"] is True and zone["n"] >= 4 and 0.15 <= zone["observed"][0] <= zone["observed"][1] <= 0.85
    assert out["positives"]["optic:baked"] == 4 and out["positives"]["optic:preset"] == 1 and out["positives"]["muzzle:preset"] == 2
    assert out["parameters"]["bore"] == {"end_slab_m": 0.01, "round_min": 0.8, "barrel_od_max_m": 0.06}


def test_ac137_with_overhang_0_007_the_verb_exits_6_and_names_the_literal(world, capsys, monkeypatch):
    with_rules(monkeypatch, clamp__overhang_max_m=0.007)
    code, out = calibrate_cli(world, capsys)
    assert code == 6 and out["ok"] is False
    assert out["failed"] == [{"literal": "clamp.overhang_max_m", "reason": "exceeded"}]  # the toothed optic overhangs its run by 0.008
    assert row(out, "clamp.overhang_max_m")["observed"] == 0.008


def test_the_verb_exits_6_when_circ_min_is_over_its_positives(world, capsys, monkeypatch):
    with_rules(monkeypatch, bore__circ_min=0.83)
    code, out = calibrate_cli(world, capsys)
    assert code == 6 and out["failed"] == [{"literal": "bore.circ_min", "reason": "exceeded"}]


def test_the_verb_exits_6_for_a_literal_with_no_positives(world, capsys, monkeypatch):
    with_rules(monkeypatch)
    code, out = calibrate_cli(world, capsys, "--pack", "FAKE_G1_OTHER")  # a pack of parts only: no host, so no positive anywhere
    assert code == 6 and out["hosts"] == 0
    assert {f["literal"] for f in out["failed"]} == set(ROWS) - {"depth"} and {f["reason"] for f in out["failed"]} == {"no_positives"}


def test_the_verb_exits_2_without_a_directory_and_6_without_a_fit_block(world, capsys, monkeypatch, tmp_path):
    with_rules(monkeypatch)
    code, out = calibrate_cli(world, capsys, "--directory", str(tmp_path / "nope.json"))
    assert code == 2 and "directory file not found" in out["error"]
    shipped = rules_mod.load_rules()
    del shipped["attachment_rules"]["fit_geometry"]
    monkeypatch.setattr(rules_mod, "load_rules", lambda path=None: shipped)
    code, out = calibrate_cli(world, capsys)
    assert code == 6 and out["ok"] is False


def test_the_json_report_carries_the_two_sheets_and_is_written_outside_the_repo(world, capsys, monkeypatch, tmp_path):
    with_rules(monkeypatch)
    target = tmp_path / "calibrate.json"
    code, out = calibrate_cli(world, capsys, "--json", str(target))
    assert code == 0 and out["json"] == "calibrate.json" and out["sheets"] == {"frame": 1, "toothed": 3}
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert [r["literal"] for r in doc["rows"]] == ROWS and doc["ok"] is True
    pack = T.PACK
    # sheets.toothed: one pair per toothed host. Notched and Notched_Scoped list the scope at rail_teeth; the low-rail host lists nothing for it,
    # so its best pending pair is shown (same_pack_fit before cross_pack_fit)
    assert doc["sheets"]["toothed"] == [
        {"part": f"{pack}/{T.GW.SCOPE}", "host": f"{pack}/{T.GW.LOWRAIL}"},
        {"part": f"{pack}/{T.GW.SCOPE}", "host": f"{pack}/{T.GW.CARBINE}"},
        {"part": f"{pack}/{T.GW.SCOPE}", "host": f"{pack}/{T.SCOPED_RAIL}"},
    ]
    # sheets.frame: one muzzle pair per frame-changed host (the Uzi-type SMG, whose magazine is its longest extent)
    assert doc["sheets"]["frame"] == [{"part": f"{pack}/{T.GW.SILENCER}", "host": f"{pack}/{T.GW.UZI}"}]
    assert doc["attach_rules_digest"] == world["directory"]["attach_rules_digest"] and doc["weapon_attach_version"] == 14


def test_the_json_report_is_refused_inside_the_repository_with_exit_3(world, capsys, monkeypatch, tmp_path):
    with_rules(monkeypatch)
    monkeypatch.setattr(export_mod, "_repo_root", lambda: tmp_path)  # the report would land in "this checkout"
    target = tmp_path / "calibrate.json"
    code, out = calibrate_cli(world, capsys, "--json", str(target))
    assert code == 3 and out["ok"] is False and not target.exists()

