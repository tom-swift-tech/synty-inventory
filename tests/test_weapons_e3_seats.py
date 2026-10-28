"""C1: the calibrate rows count seats beside observations (errata E3.10 item 1, plan 9.4 C1 and ruling 5; spec 4.2 states ``n`` as seats).

A seat is the distinct (host, slot, seat node). A baked child is its own seat node; a twin sits on the baked child it twins, so it SHARES that child's
seat; a preset's fused part stands at its own spot, which is its seat (a fused part has no baked sibling; two variants of one fitting located at the
same spot are one seat). ``cli`` supplies the node (``seat_node`` on a positive and on its
observations); ``calibrate`` stays pure and only counts. ``seats`` is additive: every other field of a row is untouched (``test_weapons_g1_calibrate``).

Two layers. The pure ``calibrate.calibrate`` is driven with hand-written observations and a LITERAL ``fit_geometry`` block (this test's own copy of the
spec 4.1 literals). The oracle (``cli._gather_oracle``) is run over ``g1_population_world``; every count is a LITERAL worked out by hand from that
fixture, not read from the code under test:

  optic     5 baked children (Notched_Scoped, Sheeted, Scoped, Stepped, Launcher); the Scoped and Stepped hosts each carry 2 twins on their baked child;
            2 presets (Rifle_01, Heavy_01) fuse a scope                                              -> zone n 11, seats 5 + 2 = 7
  toothed   only the Notched_Scoped and Sheeted baked scopes sit on a toothed run                      -> ratio n 2, seats 2
  muzzle    1 baked silencer + 2 twins on the Ringed host, 4 presets with a fused device               -> od_ratio n 7, seats 1 + 4 = 5
  magazine  2 twin magazines on the one baked magazine seat of Preset_Rifle_01                         -> well_off n 2, seats 1
  frame     1 frame-changed host                                                                       -> n 1, seats 1
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
SRC = Path(__file__).resolve().parents[1] / "src" / "synty_inventory" / "weapons"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("review_helpers")
P = _load("g1_population_world")

from synty_inventory.weapons import calibrate as FC  # noqa: E402
from synty_inventory.weapons import cli as wcli  # noqa: E402
from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import guards, rules as rules_mod  # noqa: E402

# this test's own copy of the literals of spec 4.1 (as test_weapons_g1_calibrate's FIT)
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
FRAME_MAX = 0.025


def obs(key, value, node, cls="baked", slot="optic", host="host_a", part=None):
    """One hand-written observation carrying a seat node, shaped as ``calibrate._obs`` builds it."""
    return {"key": key, "value": value, "cls": cls, "slot": slot, "host": host, "part": part or f"part_{cls}_{node}", "tags": [f"{slot}:{cls}"],
            "seat_node": node}


def row(result, literal):
    return next(r for r in result["rows"] if r["literal"] == literal)


def calibrate(observations):
    return FC.calibrate(observations, copy.deepcopy(FIT), frame_bore_max_m=FRAME_MAX)


# -- the pure layer -----------------------------------------------------------------------------------------------


def test_a_twin_shares_its_baked_siblings_seat_so_three_positives_are_two_seats():
    got = calibrate([obs("ratio", 1.1, "child_a", cls="baked"), obs("ratio", 1.2, "child_a", cls="twin"), obs("ratio", 1.3, "child_b", cls="baked")])
    ratio = row(got, "clamp.ratio_min")
    assert ratio["n"] == 3 and ratio["seats"] == 2


def test_a_preset_keeps_its_own_seat_beside_a_baked_child_and_its_twin():
    got = calibrate([obs("ratio", 1.1, "child_a", cls="baked"), obs("ratio", 1.2, "child_a", cls="twin"), obs("ratio", 1.3, "fused_c", cls="preset")])
    ratio = row(got, "clamp.ratio_min")
    assert ratio["n"] == 3 and ratio["seats"] == 2


def test_the_same_node_name_on_another_host_or_another_slot_is_another_seat():
    got = calibrate([obs("ratio", 1.1, "node_x", host="host_a"), obs("ratio", 1.2, "node_x", host="host_b"),
                     obs("ratio", 1.3, "node_x", host="host_a", slot="underbarrel")])
    assert row(got, "clamp.ratio_min")["seats"] == 3


def test_one_seat_is_one_seat_in_every_row_its_observations_feed():
    # the optic seat of a toothed host feeds the overhang, ratio, zone and depth rows
    both = [obs(k, 0.5, "child_a", cls=c) for k in ("overhang", "ratio", "zone", "depth") for c in ("baked", "twin")]
    got = calibrate(both)
    for literal in ("clamp.overhang_max_m", "clamp.ratio_min", "rail.zone", "depth"):
        assert (row(got, literal)["n"], row(got, literal)["seats"]) == (2, 1)


def test_an_excepted_observation_is_no_seat_of_the_row():
    rules = copy.deepcopy(FIT)
    rules["exceptions"] = ["optic:preset"]
    got = FC.calibrate([obs("ratio", 1.1, "child_a"), obs("ratio", 1.2, "fused_c", cls="preset")], rules, frame_bore_max_m=FRAME_MAX)
    ratio = row(got, "clamp.ratio_min")
    assert (ratio["n"], ratio["excepted"], ratio["seats"]) == (1, 1, 1)


def test_a_row_with_no_observations_has_zero_seats():
    assert row(calibrate([]), "clamp.ratio_min")["seats"] == 0


def test_an_observation_without_a_seat_node_counts_by_its_part_so_seats_never_exceed_n():
    # a hand-built observation (no cli) has no node: its part stands in, one seat per distinct part
    bare = [{"key": "ratio", "value": 1.1, "cls": "baked", "slot": "optic", "host": "host_a", "part": f"part_{i}", "tags": ["optic:baked"]}
            for i in (1, 1, 2)]
    ratio = row(calibrate(bare), "clamp.ratio_min")
    assert (ratio["n"], ratio["seats"]) == (3, 2)


def test_the_frame_row_counts_one_seat_per_host():
    got = calibrate([FC.frame_observation("host_a", 0.015), FC.frame_observation("host_b", 0.016)])
    frame = row(got, "geometry._FRAME_BORE_MAX_M")
    assert (frame["n"], frame["seats"]) == (2, 2)


def test_calibrate_stays_free_of_cli():
    # the AC144 dependency rule: the pure layer takes plain data and imports nothing from cli
    tree = ast.parse((SRC / "calibrate.py").read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = f"{'.' * node.level}{node.module or ''}"
            names += [base] + [f"{base}.{a.name}" for a in node.names]
    assert names and not [n for n in names if n.rsplit(".", 1)[-1] == "cli"], names


def test_fused_parts_at_one_spot_share_a_node_and_parts_a_few_millimetres_apart_do_not():
    # the live Military presets locate two scope variants at the very same place: one seat. Points are literal (f, s, u) triples in metres
    assert wcli._fused_node((0.1000, 0.0, 0.0500)) == wcli._fused_node((0.10004, 0.0, 0.05004))
    assert wcli._fused_node((0.1000, 0.0, 0.0500)) != wcli._fused_node((0.1050, 0.0, 0.0500))
    assert wcli._fused_node((0.1000, 0.0, 0.0500)) != wcli._fused_node((0.1000, 0.0, -0.0500))


# -- the oracle over the population world -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pop(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("c1_seats")
    cat, root, directory, _excluded = P.build(tmp)
    return {"tmp": tmp, "root": root, "directory": directory, "cfg": H.write_config(tmp, cat, extra=[f'threejs_v2: "{root.as_posix()}"'])}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    monkeypatch.setattr(export_mod, "_repo_root", lambda: None)  # pytest's tmp dirs sit inside this checkout
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def shipped_with_literal_block():
    shipped = rules_mod.load_rules()
    shipped["attachment_rules"]["fit_geometry"] = copy.deepcopy(FIT)
    return shipped


def oracle(pop):
    return wcli._gather_oracle(pop["directory"], pop["root"], shipped_with_literal_block(), None)


def test_every_oracle_observation_names_its_seat_node(pop):
    measured = [o for o in oracle(pop)["observations"] if o["key"] != "frame_ring"]
    assert measured and all(o.get("seat_node") for o in measured)


def test_the_oracle_rows_count_seats_not_observations(pop):
    rows = FC.calibrate(oracle(pop)["observations"], copy.deepcopy(FIT), frame_bore_max_m=FRAME_MAX)
    got = {r["literal"]: (r["n"], r["seats"]) for r in rows["rows"]}
    assert got["rail.zone"] == (11, 7)  # 5 baked + 4 twins on baked seats + 2 presets
    assert got["clamp.ratio_min"] == (2, 2) and got["clamp.overhang_max_m"] == (2, 2)  # the two toothed baked scopes only
    assert got["bore.od_ratio"] == (7, 5)  # 1 baked + 2 twins on it + 4 presets
    assert got["well.tol"] == (2, 1)  # two twin magazines on the one baked magazine seat
    assert got["geometry._FRAME_BORE_MAX_M"] == (1, 1)


def test_a_twin_has_its_baked_siblings_node_and_a_preset_has_its_own(pop):
    zones = [o for o in oracle(pop)["observations"] if o["key"] == "zone"]
    by_host: dict[str, list[dict]] = {}
    for o in zones:
        by_host.setdefault(o["host"], []).append(o)
    # the Scoped and Stepped hosts each carry 1 baked scope and 2 twins: three observations, one node
    triple = [v for v in by_host.values() if len(v) == 3]
    assert len(triple) == 2
    for v in triple:
        assert sorted(o["cls"] for o in v) == ["baked", "twin", "twin"] and len({o["seat_node"] for o in v}) == 1
    # a preset's node is its fused part, never one of the baked nodes
    presets = [o for o in zones if o["cls"] == "preset"]
    assert len(presets) == 2
    assert not {o["seat_node"] for o in presets} & {o["seat_node"] for o in zones if o["cls"] != "preset"}


def test_the_verb_json_carries_seats_beside_the_older_fields(pop, capsys, monkeypatch, tmp_path):
    shipped = shipped_with_literal_block()  # before the patch: it reads load_rules too
    monkeypatch.setattr(rules_mod, "load_rules", lambda path=None: shipped)
    target = tmp_path / "cal.json"
    code, out = H.run(pop["cfg"], capsys, ["weapons", "attach-calibrate", "--json", str(target)])
    assert code == 0 and out["failed"] == []
    doc = json.loads(target.read_text(encoding="utf-8"))
    zone = next(r for r in doc["rows"] if r["literal"] == "rail.zone")
    assert zone["n"] == 11 and zone["seats"] == 7 and zone["spec_n"] is None
    assert all("seats" in r and r["seats"] <= r["n"] for r in doc["rows"])
