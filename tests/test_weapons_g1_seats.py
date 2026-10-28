"""G1 S7: host features wired into the mounts (docs/weapon_attach_geometry.md 3.3 step 4, 3.4 steps 3 and 4, 3.8, 3.11, INV-27; AC139, AC147, AC148).

World: ``fixtures/weapons/g1_world.py`` (``FAKE_G1``: toothed, flat-top, scoped, stepped, preset, both-rings and Uzi hosts; its docstring says what each
host is for). Every expected number is a LITERAL worked out by hand from the mesh dimensions written there; the one value the tests read from the
code under test is the A0 probe's front sight (a base behaviour that the sight clip reads), and it is bounded by literals.

* seats (AC148): a toothed top rail, a toothed bottom rail, a flat top, authored seats confirmed by a detector (``seat_ref``, ``well_ref``), the sight
  clip against gate 6(c) of A 4.6 (the test keeps its own twin of that check), the muzzle ``feature``;
* the frame conflict (AC147, INV-27) and the verdict on it (fold-in 7);
* presets (AC139 item 1, Q-G11): the fused scope and silencer refuse their slots, the magazine stays open, a fused magazine with no baked child gets no reference (E2-Q3);
* the number of hosts per ``feature`` value;
* the caches: ``_fit_cache.json`` (miss on each key component, a hit equals a recompute) and the ``mv`` fingerprint of ``_geometry_cache.json``;
* the fold-ins: 1 (``frame_vote``), 2 (a bow or shield on a gun hold), 3 (re-exports), 4 (retired by E2-Q3: a located magazine is no reference),
  5 (the run read as is), 6 (the shapes ``verdict`` reads), 7 (a conflict host and the magazine).
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("g1_world", FIX / "g1_world.py")
GW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GW)
W = GW.W

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons import directory as dirmod  # noqa: E402
from synty_inventory.weapons import fit_geometry as FG  # noqa: E402
from synty_inventory.weapons import fit_rails, geometry  # noqa: E402
from synty_inventory.weapons.mounts import none_mount  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules  # noqa: E402
from synty_inventory.weapons.schema import validate_directory, validate_record  # noqa: E402

RULES = attachment_rules(load_rules())["fit_geometry"]
N_HOSTS = 15  # the eligible hosts of the world (whole + ranged + a gun hold): the 15 host assets of g1_world.world(); its parts are assets too
FOUR = ("optic", "muzzle", "underbarrel", "magazine")


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    world = GW.world()
    cat, root = W.write_world(tmp_path_factory.mktemp("g1_seats"), world)
    return SimpleNamespace(cat=cat, root=root, settings=W.pack_settings(world))


def build(tree, *, fit_cache=None, geometry_cache=None, rules=None, host_feats=None):
    """``(directory, excluded, report)`` of the world. ``fit_cache`` and ``host_feats`` are passed only when given."""
    kw = {}
    if fit_cache is not None:
        kw["fit_cache"] = fit_cache
    if host_feats is not None:
        kw["host_feats"] = host_feats
    return dirmod.build_directory_report(
        tree.cat, overrides=empty_overrides(), pack_settings=tree.settings, rules=rules if rules is not None else W.sight_rules(),
        threejs_v2_dir=tree.root, geometry_cache={} if geometry_cache is None else geometry_cache, **kw)


@pytest.fixture(scope="module")
def built(tree):
    d, _ex, report = build(tree)
    return SimpleNamespace(directory=d, report=report, by_id=W.by_id(d))


@pytest.fixture(scope="module")
def featured(tree):
    """The same build with the host features collected (``host_feats``: host id -> what ``host_features`` returned)."""
    hf: dict = {}
    d, _ex, report = build(tree, host_feats=hf)
    return SimpleNamespace(directory=d, report=report, by_id=W.by_id(d), feats=hf)


def mounts(b, name):
    return b.by_id[GW.pid(name)]["geometry"]["mounts"]


def close(got, want, tol=1e-3):
    assert len(got) == len(want) and all(abs(g - w) <= tol for g, w in zip(got, want)), (got, want)


def gate_6c(m):
    """The sight seats the optic span covers: a twin of gate 6(c) of A 4.6 (``test_weapons_w8h_probe.gate_violations``), +z forward hosts. The span
    covers [run start, run start + span_m]; a rail seat is the centre of the rearmost min(run, 0.20) m of the clipped run and span_m is the whole run
    (src fit_rails.py:446-451, fit_geometry.py:447-448), so the run starts at point - min(span_m, 0.20) / 2."""
    opt = m["optic"]
    lo = opt["point"][2] - min(opt["span_m"], 0.20) / 2
    return [n for n in ("sight_front", "sight_rear") if lo <= m[n]["point"][2] <= lo + opt["span_m"]]


def part(**kw):
    return {"anchor_measured": True, **kw}


# --- AC148: rail seats, flat seats, authored seats ------------------------------------------------------------------------------


def test_the_world_builds_and_validates(built):
    assert validate_directory(built.directory) == []
    assert len([w for w in built.directory["weapons"] if w["geometry"] and w["geometry"]["mounts"] is not None]) == N_HOSTS


def test_ac148_a_toothed_top_rail_gives_a_rail_teeth_optic_seat_that_ends_before_the_front_sight(built):
    m = mounts(built, GW.CARBINE)
    opt, front = m["optic"], m["sight_front"]
    assert (opt["source"], opt["feature"], opt["span_source"], opt["confidence"], opt["reason"]) == ("probe", "rail_teeth", "probe", 0.5, None)
    assert opt["forward"] == [0.0, 0.0, 1.0] and opt["up"] == [0.0, 1.0, 0.0] and opt["child_node"] is None and opt["occupied_by"] == []
    front_f = front["point"][2]
    assert 0.085 <= front_f <= 0.100  # the A0 probe's front sight, inside the last 15 mm of the receiver (z 0.10): inside the rail run
    # the rail run is z -0.088 .. 0.100 (8 teeth, pitch 0.0235; the docstring of g1_world); the clip ends it 10 mm behind the front sight
    span = front_f - 0.010 + 0.088
    assert opt["span_m"] == pytest.approx(span, abs=2e-3) and 0.16 <= opt["span_m"] <= 0.18
    close(opt["point"], [0.0, 0.105, -0.088 + span / 2], 2e-3)  # x = s, y = u (the crest), z = the centre of the clipped run
    assert "mount_estimated" in built.by_id[GW.pid(GW.CARBINE)]["review"]["reasons"]


def test_ac148_gate_6c_holds_on_the_railed_host_with_a_front_sight_and_only_because_of_the_clip(built):
    m = mounts(built, GW.CARBINE)
    assert m["sight_front"]["source"] == "probe" and m["sight_rear"]["source"] == "probe"
    assert gate_6c(m) == []
    # without the clip the seat would be the whole run: span 0.188 centred on z 0.006 (= -0.088 + 0.094), which covers the front sight
    front_f = m["sight_front"]["point"][2]
    assert abs(front_f - 0.006) <= 0.094
    # and with it the span's front edge is 10 mm behind the sight
    assert m["optic"]["point"][2] + m["optic"]["span_m"] / 2 == pytest.approx(front_f - 0.010, abs=2e-3)


def test_ac148_gate_6c_covers_a_front_sight_past_the_centred_window_on_a_long_toothed_run():
    # E3.19, a hand-built record: a toothed run 0.12 .. 0.449 (0.329 m) has its seat point at 0.22 (centre of the rearmost 0.20 m) and span 0.329. A
    # window centred on the point reaches 0.22 + 0.1645 = 0.3845; the span from the run's rear reaches 0.12 + 0.329 = 0.449.
    seat = {"point": [0.0, 0.105, 0.22], "span_m": 0.329}
    m = {"optic": seat, "sight_rear": {"point": [0.0, 0.1, -0.3]}, "sight_front": {"point": [0.0, 0.1, 0.40]}}
    assert abs(0.40 - 0.22) > 0.329 / 2  # the centred window misses it
    assert gate_6c(m) == ["sight_front"]
    m["sight_front"]["point"][2] = 0.46  # past the run's front: not covered
    assert gate_6c(m) == []
    m["sight_front"]["point"][2] = 0.40
    seat["span_m"] = 0.18  # a run under 0.20 m is centred on its point: 0.22 +- 0.09 does not reach 0.40
    assert gate_6c(m) == []


def test_ac148_a_toothed_bottom_rail_gives_a_rail_teeth_underbarrel_seat_with_up_minus_u_and_no_clip(built):
    m = mounts(built, GW.LOWRAIL)
    ub = m["underbarrel"]
    assert (ub["source"], ub["feature"], ub["span_source"]) == ("probe", "rail_teeth", "probe")
    assert ub["forward"] == [0.0, 0.0, 1.0] and ub["up"] == [0.0, -1.0, 0.0]
    close(ub["point"], [0.0, -0.005, 0.006])  # crest y -0.005; the whole run z -0.088 .. 0.100, centred (an underbarrel never covers a sight)
    assert ub["span_m"] == pytest.approx(0.188, abs=1e-3)
    assert m["optic"]["feature"] == "rail_flat"  # the top of this host is smooth


def test_ac148_a_smooth_top_gives_a_rail_flat_optic_seat_and_a_smooth_bottom_gives_nothing(built):
    m = mounts(built, GW.FLATTOP)
    opt, front = m["optic"], m["sight_front"]
    assert (opt["source"], opt["feature"], opt["span_source"], opt["confidence"]) == ("probe", "rail_flat", "probe", 0.5)
    assert opt["up"] == [0.0, 1.0, 0.0] and opt["forward"] == [0.0, 0.0, 1.0]
    front_f = front["point"][2]
    assert 0.19 <= front_f <= 0.20
    # the flat run starts at the detector zone (15 % of the 0.60 m host from the rear: z -0.11) and is clipped 10 mm behind the front sight; the
    # seat is centred on the rearmost 0.20 m of the run (z -0.01), its span is the whole run
    assert opt["span_m"] == pytest.approx(front_f - 0.010 + 0.110, abs=2e-3)
    close(opt["point"], [0.0, 0.10, -0.010], 2e-3)
    assert gate_6c(m) == []
    assert m["underbarrel"]["source"] == "none" and m["underbarrel"]["reason"] == "no_child_no_probe" and "feature" not in m["underbarrel"]


def test_ac148_a_flat_optic_seat_is_for_the_optic_slot_only_and_never_overwrites_an_authored_seat(built):
    for name in (GW.FLATTOP, GW.FLAT, GW.UZI):
        m = mounts(built, name)
        assert [s for s, x in m.items() if x.get("feature") == "rail_flat"] == ["optic"], name
    for name in (GW.SCOPED, GW.STEPPED):  # a baked scope child: its own seat stays, confirmed
        optic = mounts(built, name)["optic"]
        assert optic["source"] == "child_node" and optic["feature"] == "seat_ref" and optic["child_node"].endswith("_Scope")


def test_ac148_authored_optic_seats_keep_their_numbers_and_get_seat_ref(built):
    scoped = mounts(built, GW.SCOPED)["optic"]
    close(scoped["point"], [0.005, 0.10, -0.05])  # unchanged: the foot of the scope child on the receiver top (the W8h child rung)
    assert scoped["span_m"] == pytest.approx(0.06, abs=1e-3) and scoped["confidence"] == 0.9
    stepped = mounts(built, GW.STEPPED)["optic"]
    assert stepped["source"] == "child_node" and stepped["feature"] == "seat_ref" and stepped["span_m"] == pytest.approx(0.06, abs=1e-3)


def test_ac148_the_muzzle_seat_stays_the_probes_and_only_gets_its_feature(built, featured):
    expected = {GW.UZI: ("barrel_ring", [0.0, 0.04, 0.2]), GW.RIFLE_PLAIN: ("barrel_ring", [0.0, 0.05, 0.6]),
                GW.CARBINE: ("barrel_ring", [0.0, 0.05, 0.2]), GW.FLATTOP: ("barrel_ring", [0.0, 0.05, 0.4]),
                GW.FLAT: ("barrel_round", [0.0, 0.046, 0.65]), GW.SCOPED: ("barrel_round", [0.0, 0.046, 0.65])}  # E2-Q2: the rod is one radius
    for name, (feature, point) in expected.items():
        muz = mounts(built, name)["muzzle"]
        assert (muz["source"], muz["feature"]) == ("probe", feature), name
        close(muz["point"], point)
        assert muz["point"] == built.by_id[GW.pid(name)]["geometry"]["muzzle"]  # AC67 parity: the same point as geometry.muzzle
    assert featured.feats[GW.pid(GW.UZI)]["slots"]["muzzle"]["barrel_end"]["evidence"] == "ring"
    # E2-Q2: the rod rifle's solid 32-gon end has one radius, so the A0 probe finds no ring bore (face_extent): the pipeline's evidence is (iii)
    assert featured.feats[GW.pid(GW.FLAT)]["slots"]["muzzle"]["barrel_end"]["evidence"] == "round_section"


def test_ac148_the_uzi_in_the_voted_frame_has_its_muzzle_at_the_ring_not_at_the_magazine(built):
    # the Uzi's body axis is z but its bounding box says y (the magazine is longer than the barrel): the record frame is the voted one, so the muzzle
    # is at the ring end (z 0.20) and the flat optic seat lies along z; in the bounding-box frame the muzzle would sit at the magazine end (y -0.30)
    m = mounts(built, GW.UZI)
    close(m["muzzle"]["point"], [0.0, 0.04, 0.2])
    assert m["muzzle"]["feature"] == "barrel_ring" and m["optic"]["feature"] == "rail_flat"
    assert m["optic"]["point"][1] == pytest.approx(0.08, abs=1e-3) and abs(m["optic"]["point"][2]) < 0.1
    assert built.by_id[GW.pid(GW.UZI)]["geometry"]["axes"]["forward"] == "+z"


def test_ac148_the_magazine_child_seat_stays_and_gets_well_ref_where_a_well_is_measured(built):
    for name in (GW.UZI, GW.RIFLE_PLAIN, GW.CARBINE):
        mag = mounts(built, name)["magazine"]
        assert (mag["source"], mag["feature"]) == ("child_node", "well_ref"), name
    close(mounts(built, GW.CARBINE)["magazine"]["point"], [0.0, 0.0, -0.045])  # the baked magazine's own seat: unchanged
    assert mounts(built, GW.CARBINE)["magazine"]["span_m"] == pytest.approx(0.03, abs=1e-3)


def test_ac148_no_feature_on_a_slot_no_detector_confirmed(built):
    assert mounts(built, GW.CARBINE)["optic"]["feature"] == "rail_teeth"  # a positive control: the key is written where a detector confirmed
    for name in (GW.NAILGUN, GW.MINIGUN, GW.ROCKET):
        assert not [s for s, x in mounts(built, name).items() if "feature" in x], name
    for w in built.directory["weapons"]:
        if w["geometry"] and w["geometry"]["mounts"] is None:
            assert "mounts" in w["geometry"]  # a part or a non-host: no mounts block and so no feature


def test_ac148_a_sight_slot_never_carries_a_feature(built):
    assert mounts(built, GW.CARBINE)["optic"]["feature"] == "rail_teeth"  # a positive control: features exist on this build
    for w in built.directory["weapons"]:
        for slot in ("sight_front", "sight_rear", "laser_light"):
            m = ((w["geometry"] or {}).get("mounts") or {}).get(slot)
            assert m is None or "feature" not in m, (w["id"], slot)


# --- the schema ---------------------------------------------------------------------------------------------------------------


def test_the_schema_admits_the_six_features_and_nothing_else(built):
    rec = copy.deepcopy(built.by_id[GW.pid(GW.CARBINE)])
    assert rec["geometry"]["mounts"]["optic"]["feature"] == "rail_teeth" and validate_record(rec) == []
    rec["geometry"]["mounts"]["optic"]["feature"] = "rail_teeth_x"
    assert validate_record(rec)


@pytest.mark.parametrize(("slot", "feature"), [("muzzle", "rail_teeth"), ("optic", "barrel_ring"), ("magazine", "seat_ref"), ("optic", "well_ref")])
def test_inv27_a_feature_on_the_wrong_slot_is_a_schema_error(built, slot, feature):
    rec = copy.deepcopy(built.by_id[GW.pid(GW.CARBINE)])
    rec["geometry"]["mounts"][slot]["feature"] = feature
    errors = validate_record(rec)
    assert errors and any("INV-27" in e for e in errors), errors


def test_inv27_a_feature_on_a_none_mount_is_a_schema_error(built):
    rec = copy.deepcopy(built.by_id[GW.pid(GW.FLATTOP)])
    rec["geometry"]["mounts"]["underbarrel"]["feature"] = "rail_teeth"
    assert any("INV-27" in e for e in validate_record(rec))


# --- AC147 and INV-27: the frame conflict ---------------------------------------------------------------------------------------


def test_ac147_a_frame_conflict_host_gets_no_detector_seat_and_keeps_the_build_frame(built):
    rec = built.by_id[GW.pid(GW.BOTH)]
    m = rec["geometry"]["mounts"]
    for slot in ("optic", "muzzle", "underbarrel"):
        got = m[slot]
        assert (got["source"], got["reason"], got["point"], got["span_m"]) == ("none", "probe_unavailable", None, None), slot
        assert "feature" not in got and got["occupied_by"] == []
    assert rec["geometry"]["axes"]["forward"] == "-y" and rec["geometry"]["axes"]["up"] == "+z"  # the build frame, not a voted one
    assert not [s for s, x in m.items() if x.get("feature")]  # not one feature on the host, the magazine included


def test_inv27_the_conflict_host_magazine_child_seat_is_not_a_detector_seat_and_stays(built):
    mag = mounts(built, GW.BOTH)["magazine"]
    assert mag["source"] == "child_node" and mag["child_node"] == f"{GW.BOTH}_Mag" and mag["point"] is not None and "feature" not in mag


def test_inv27_the_frame_vote_reports_the_conflict_and_a_voted_host_does_not(tree):
    def detail(name):
        return geometry.measure_weapon_detail(
            tree.root / "glb" / GW.PACK / f"{name}.glb", None, 1.0, "smg", "ranged", "whole", load_rules(), hold_class="long_gun", genre="modern",
            with_mounts=True, host_id=name, host_pack=GW.PACK)

    both, uzi = detail(GW.BOTH), detail(GW.UZI)
    assert both["frame_vote"]["conflict"] is True and both["frame_vote"]["changed"] is False
    assert both["host_feats"]["slots"] == {s: {"frame_conflict": True} for s in FOUR} and both["host_feats"]["located"] == []
    assert uzi["frame_vote"]["conflict"] is False and uzi["frame_vote"]["changed"] is True
    assert all(uzi["host_feats"]["slots"][s].get("frame_body") is True for s in FOUR)  # the voted frame marks every slot


def test_fold_in_7_a_frame_conflict_is_not_judged_on_all_four_slots_the_magazine_included(featured):
    slots = featured.feats[GW.pid(GW.BOTH)]["slots"]
    p = part(foot_length_m=0.06, foot_width_m=0.03, mate_d_m=0.024, device_inner_d=None, entry_section=(0.04, 0.02))
    for slot in FOUR:
        v = FG.verdict(slot, slots[slot], p, None, RULES)
        assert (v.value, v.signals) == ("not_judged", ()), slot
    # the authored magazine seat is on the record all the same, and a voted host with the same child is judged
    assert mounts(featured, GW.BOTH)["magazine"]["source"] == "child_node"
    assert FG.verdict("magazine", featured.feats[GW.pid(GW.UZI)]["slots"]["magazine"], part(entry_section=(0.04, 0.02)), None, RULES).value == "fit"


# --- AC139 item 1 and Q-G11: presets ----------------------------------------------------------------------------------------------


def test_q_g11_the_fused_scope_and_silencer_of_a_preset_refuse_their_slots_and_the_magazine_stays_open(built, featured):
    m = mounts(built, GW.PRESET)
    for slot in ("optic", "muzzle"):
        got = m[slot]
        assert (got["source"], got["reason"], got["point"], got["occupied_by"]) == ("none", "slot_disabled", None, []), slot
    mag = m["magazine"]
    assert mag["source"] == "child_node" and mag["reason"] is None and mag["point"] is not None  # attach_filled_open
    located = {p["part"]: p for p in featured.feats[GW.pid(GW.PRESET)]["located"]}
    # the host mesh is the whole render, the baked Mag child included: the locator finds the magazine part where the child stands (t (0, 0, -0.1))
    assert sorted(located) == [GW.MAG_RIFLE, GW.SCOPE, GW.SILENCER]
    assert (located[GW.SCOPE]["slot"], located[GW.SILENCER]["slot"], located[GW.MAG_RIFLE]["slot"]) == ("optic", "muzzle", "magazine")
    close(located[GW.MAG_RIFLE]["t"], [0.0, 0.0, -0.1], 1e-3)
    close(located[GW.SCOPE]["t"], GW.PRESET_SCOPE_AT, 1e-3)  # the part's own mesh moved by exactly the translation the fixture fused it with
    close(located[GW.SILENCER]["t"], GW.PRESET_SILENCER_AT, 1e-3)
    assert located[GW.SCOPE]["hit"] == 1.0 and located[GW.SILENCER]["hit"] == 1.0


def test_q_g11_a_preset_with_no_fused_scope_or_silencer_keeps_those_slots_open(built, featured):
    m = mounts(built, GW.PRESET_MAG)
    assert m["optic"]["source"] == "probe" and m["optic"]["feature"] == "rail_flat"
    assert m["muzzle"]["source"] == "probe" and m["muzzle"]["feature"] == "barrel_round"  # E2-Q2: the rod rifle's end is one radius
    assert [p["part"] for p in featured.feats[GW.pid(GW.PRESET_MAG)]["located"]] == [GW.MAG_RIFLE]


def test_q_g11_only_presets_run_the_locator(featured):
    for name in (GW.CARBINE, GW.FLAT, GW.SCOPED, GW.UZI, GW.BOTH):
        assert featured.feats[GW.pid(name)]["located"] == [], name


def test_e2_q3_a_fused_magazine_with_no_baked_child_gets_no_well_reference_and_its_pairs_are_not_judged(built, featured):
    # G1 errata E2-Q3 (E2.4): S7 fold-in 4 is retired. Before it, this host's fused magazine was the reference (source "located", 0.04 x 0.02) and a
    # magazine part of that section got `fit`. Now the locator still finds the magazine (and the strip still removes it), but it is no reference.
    slots = featured.feats[GW.pid(GW.PRESET_MAG)]["slots"]
    assert "well_ref" not in slots["magazine"]
    mag = mounts(built, GW.PRESET_MAG)["magazine"]
    assert (mag["source"], mag["reason"]) == ("none", "no_child_no_probe") and "feature" not in mag
    # a literal rules dict (the verdict reads only "slots" before it returns not_judged)
    rules = {"slots": ["optic", "muzzle", "underbarrel", "magazine"], "well": {"entry_depth_m": 0.002, "tol": 0.15}}
    v = FG.verdict("magazine", slots["magazine"], part(entry_section=(0.04, 0.02)), None, rules)
    assert (v.value, v.signals) == ("not_judged", ())
    assert [p["part"] for p in featured.feats[GW.pid(GW.PRESET_MAG)]["located"]] == [GW.MAG_RIFLE]  # the locator and `located` are unchanged
    assert featured.feats[GW.pid(GW.CARBINE)]["slots"]["magazine"]["well_ref"]["source"] == "child"  # an authored child's reference is unchanged


# --- the feature counts -------------------------------------------------------------------------------------------------------------


def test_the_number_of_hosts_per_feature_value_on_fake_g1(built):
    # by hand, host by host (g1_world): barrel_ring Uzi, Plain, Carbine, Lowrail, FlatTop; barrel_round Flat, Scoped, Shotgun, PresetMag (E2-Q2: the rod
    # rifles' solid round barrels have one radius, so the A0 probe finds no ring bore and (iii) calls them round sections);
    # rail_flat Uzi, Flat, FlatTop, Lowrail, PresetMag, Shotgun; rail_teeth Carbine (optic) and Lowrail (underbarrel); seat_ref Scoped, Stepped;
    # well_ref Uzi, Plain, Carbine, Preset. Both (a frame conflict), Preset's optic and muzzle, and the Rocket, Nailgun and Minigun carry none.
    want = {"barrel_ring": 5, "barrel_round": 4, "rail_flat": 6, "rail_teeth": 2, "seat_ref": 2, "well_ref": 4}
    assert built.report["feature_counts"] == want
    counted: dict[str, set] = {}
    for w in built.directory["weapons"]:
        for m in ((w["geometry"] or {}).get("mounts") or {}).values():
            if m.get("feature"):
                counted.setdefault(m["feature"], set()).add(w["id"])
    assert {k: len(v) for k, v in sorted(counted.items())} == want


# --- the caches -----------------------------------------------------------------------------------------------------------------


@pytest.fixture()
def computes(monkeypatch):
    """The number of times ``host_features`` computed (a cache hit does not)."""
    calls: list[int] = []
    real = FG._compute

    def spy(rules, **kw):
        calls.append(1)
        return real(rules, **kw)

    monkeypatch.setattr(FG, "_compute", spy)
    return calls


def dump(d) -> str:
    return json.dumps(d, sort_keys=True)


def test_the_fit_cache_a_hit_equals_a_recompute_and_survives_a_json_round_trip(tree, computes):
    fit: dict = {}
    d1, _, _ = build(tree, fit_cache=fit)
    assert len(computes) == N_HOSTS and len(fit) == N_HOSTS
    del computes[:]
    d2, _, _ = build(tree, fit_cache=json.loads(json.dumps(fit)))  # a fresh geometry cache: the geometry is measured again, the features are not
    assert computes == [] and dump(d2) == dump(d1)
    d3, _, _ = build(tree)  # no fit cache at all
    assert dump(d3) == dump(d1)


def test_the_fit_cache_holds_the_entry_key_and_one_result_per_inputs(tree):
    fit: dict = {}
    build(tree, fit_cache=fit)
    entry = fit[f"glb/{GW.PACK}/{GW.CARBINE}.glb"] if f"glb/{GW.PACK}/{GW.CARBINE}.glb" in fit else next(iter(fit.values()))
    assert sorted(entry) == ["by_inputs", "key"] and 1 <= len(entry["by_inputs"]) <= 8


def test_the_fit_cache_misses_when_the_geometry_version_changes(tree, computes, monkeypatch):
    fit: dict = {}
    build(tree, fit_cache=fit)
    del computes[:]
    monkeypatch.setattr(pkg, "WEAPON_GEOMETRY_VERSION", pkg.WEAPON_GEOMETRY_VERSION + 1)
    build(tree, fit_cache=fit)
    assert len(computes) == N_HOSTS


def test_the_fit_cache_misses_when_the_attach_version_changes(tree, computes, monkeypatch):
    fit: dict = {}
    build(tree, fit_cache=fit)
    del computes[:]
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", pkg.WEAPON_ATTACH_VERSION + 1)
    build(tree, fit_cache=fit)
    assert len(computes) == N_HOSTS


def test_the_fit_cache_misses_when_the_fit_geometry_block_is_edited(tree, computes):
    fit: dict = {}
    build(tree, fit_cache=fit)
    del computes[:]
    rules = W.sight_rules()
    rules["attachment_rules"]["fit_geometry"]["depth"]["hi_m"] = 0.004  # a review-list bound (0.003 shipped): no mount moves, the key does
    build(tree, fit_cache=fit, rules=rules)
    assert len(computes) == N_HOSTS


def test_the_fit_cache_misses_when_the_code_of_a_fit_module_changes(tree, computes, monkeypatch):
    fit: dict = {}
    build(tree, fit_cache=fit)
    del computes[:]
    changed = dict(FG.FIT_CODE_DIGESTS)
    changed["fit_rails"] = "0" * 12
    monkeypatch.setattr(FG, "FIT_CODE_DIGESTS", changed)
    build(tree, fit_cache=fit)
    assert len(computes) == N_HOSTS


def test_the_fit_cache_hits_when_nothing_changed_even_with_a_different_geometry_cache(tree, computes):
    fit: dict = {}
    build(tree, fit_cache=fit)
    del computes[:]
    build(tree, fit_cache=fit, geometry_cache={})
    build(tree, fit_cache=fit, geometry_cache={})
    assert computes == []


def test_the_fit_code_digests_are_the_fit_modules_and_the_ring_estimator():
    # The deliberate pin (G1 S9b): `_fit_code_digests` globs fit_*.py, so a seventh fit_*.py (or a rename into the glob) invalidates every fit cache and the
    # geometry cache fingerprint. Adding one must be a conscious re-pin of this literal; a tool that is not a detector lives outside the glob (calibrate.py).
    assert sorted(FG.FIT_CODE_DIGESTS) == ["fit_bore", "fit_geometry", "fit_locate", "fit_rails", "fit_types", "fit_well", "mount_probe"]
    assert all(len(v) == 12 and set(v) <= set("0123456789abcdef") for v in FG.FIT_CODE_DIGESTS.values())


def eligible_args():
    return ("rifle", "ranged", "whole", "long_gun", "modern")


def test_the_geometry_cache_fingerprint_carries_the_fit_block_and_the_fit_code(monkeypatch):
    rules = load_rules()
    base = geometry._inputs_fingerprint(*eligible_args()[:4], eligible_args()[4], rules)
    edited = copy.deepcopy(rules)
    edited["attachment_rules"]["fit_geometry"]["depth"]["hi_m"] = 0.004
    assert geometry._inputs_fingerprint(*eligible_args()[:4], eligible_args()[4], edited) != base
    changed = dict(FG.FIT_CODE_DIGESTS)
    changed["fit_bore"] = "f" * 12
    monkeypatch.setattr(FG, "FIT_CODE_DIGESTS", changed)
    assert geometry._inputs_fingerprint(*eligible_args()[:4], eligible_args()[4], rules) != base


def test_the_geometry_cache_fingerprint_of_a_part_and_of_a_non_host_does_not_move(monkeypatch):
    rules = load_rules()
    others = [("sword", "melee", "whole", "melee_one", "modern"), ("unknown", None, "part", "none", "modern"),
              ("rifle", "ranged", "emplaced", "none", "modern")]
    before = [geometry._inputs_fingerprint(*a[:4], a[4], rules) for a in others]
    edited = copy.deepcopy(rules)
    edited["attachment_rules"]["fit_geometry"]["depth"]["hi_m"] = 0.004
    changed = dict(FG.FIT_CODE_DIGESTS)
    changed["fit_well"] = "e" * 12
    monkeypatch.setattr(FG, "FIT_CODE_DIGESTS", changed)
    assert [geometry._inputs_fingerprint(*a[:4], a[4], edited) for a in others] == before


def test_the_geometry_cache_remeasures_exactly_the_eligible_hosts_when_the_fit_block_or_fit_code_changes(tree, monkeypatch):
    cache: dict = {}
    _, _, r1 = build(tree, geometry_cache=cache)
    total = r1["geometry_stats"]["decoded"]
    assert r1["geometry_stats"] == {"decoded": total, "cached": 0} and total > N_HOSTS  # the parts are assets too
    _, _, r2 = build(tree, geometry_cache=cache)
    assert r2["geometry_stats"] == {"decoded": 0, "cached": total}
    rules = W.sight_rules()
    rules["attachment_rules"]["fit_geometry"]["depth"]["hi_m"] = 0.004
    _, _, r3 = build(tree, geometry_cache=cache, rules=rules)
    assert r3["geometry_stats"] == {"decoded": N_HOSTS, "cached": total - N_HOSTS}
    changed = dict(FG.FIT_CODE_DIGESTS)
    changed["fit_locate"] = "d" * 12
    monkeypatch.setattr(FG, "FIT_CODE_DIGESTS", changed)
    _, _, r4 = build(tree, geometry_cache=cache)
    assert r4["geometry_stats"] == {"decoded": N_HOSTS, "cached": total - N_HOSTS}


def test_a_geometry_cache_hit_equals_a_recompute_with_the_features(tree):
    cache: dict = {}
    d1, _, _ = build(tree, geometry_cache=cache)
    d2, _, r2 = build(tree, geometry_cache=json.loads(json.dumps(cache)))
    assert r2["geometry_stats"]["decoded"] == 0 and dump(d2) == dump(d1)
    assert d2["weapons"] and any(m.get("feature") for w in d2["weapons"] for m in ((w["geometry"] or {}).get("mounts") or {}).values())


def test_the_versions_and_digests_are_those_of_the_base():
    assert pkg.WEAPON_ATTACH_VERSION == 14 and pkg.WEAPON_GEOMETRY_VERSION == 6  # S7 bumps neither (the lead decides the bump)
    from synty_inventory.weapons.rules import attach_rules_digest, weapon_rules_digest
    rules = load_rules()
    assert weapon_rules_digest(rules) == "7b9829af37328fe7" and attach_rules_digest(rules) == "2fa41961e3c387b0"  # G1 4.6/AC146 (S8): the retired rules leave the four slots (was 1dacc105674aff85); E1.4: bore.circ_min moved it before (was 59268363ae44fd9e); E3.8 (clamp.ratio_min 1.0 to 0.69, Tom 2026-10-28) re-pinned it; S11 finding 12


# --- fold-ins -------------------------------------------------------------------------------------------------------------------


def test_fold_in_1_the_detail_key_is_frame_vote_and_geometry_frame_is_still_asset(tree):
    d = geometry.measure_weapon_detail(
        tree.root / "glb" / GW.PACK / f"{GW.UZI}.glb", None, 1.0, "smg", "ranged", "whole", load_rules(), hold_class="long_gun", genre="modern",
        with_mounts=True, host_id=GW.UZI, host_pack=GW.PACK)
    assert "frame" not in d and sorted(d["frame_vote"]) == ["axes_unexpected", "changed", "conflict", "forward_by_fallback", "length_m"]
    assert d["geometry"]["frame"] == "asset"


@pytest.mark.parametrize("archetype", ["bow", "shield"])
def test_fold_in_2_a_bow_or_shield_on_a_gun_hold_does_not_raise_and_does_not_vote(tree, archetype):
    # an id override can force a gun hold onto a bow or shield archetype: an eligible host that never votes
    d = geometry.measure_weapon_detail(
        tree.root / "glb" / GW.PACK / f"{GW.UZI}.glb", None, 1.0, archetype, "ranged", "whole", load_rules(), hold_class="long_gun", genre="modern",
        with_mounts=True, host_id=GW.UZI, host_pack=GW.PACK)
    assert d["frame_vote"] == {"changed": False, "conflict": False}
    p2 = geometry.pass2_inputs(d)
    assert sorted(p2) == ["axes_unexpected", "forward_by_fallback", "length_m", "long_axis"]
    assert p2["length_m"] == d["geometry"]["length_m"] and p2["long_axis"] == d["geometry"]["long_axis"]  # the measured ones: nothing was voted


def test_fold_in_3_clip_run_and_seat_point_are_re_exported_from_the_facade():
    assert FG.clip_run is fit_rails.clip_run and FG.seat_point is fit_rails.seat_point
    assert {"clip_run", "seat_point"} <= set(FG.__all__)


def test_fold_in_5_the_run_is_read_as_is_f_and_u_from_seat_point_and_s_from_the_centreline(featured):
    feats = featured.feats[GW.pid(GW.CARBINE)]
    assert sorted(feats) == ["located", "s0", "slots"] and feats["s0"] == 0.0  # the seats are consumed by the mounts, not carried out
    seat = mounts(featured, GW.CARBINE)["optic"]
    run = feats["slots"]["optic"]["toothed_run"]
    assert run["width_m"] == pytest.approx(0.017, abs=1e-3)  # the rail prism is 17 mm wide
    assert run["length_m"] == pytest.approx(0.17, abs=2e-3) and seat["span_m"] == pytest.approx(run["length_m"], abs=1e-4)  # the clipped run
    # seat_point returns (f, u): the centre of the rearmost min(run, 0.20) m at the crest; the caller adds s0 (asset x = s, y = u, z = f here)
    close(seat["point"], [0.0 + feats["s0"], 0.105, -0.088 + run["length_m"] / 2], 2e-3)


def test_fold_in_6_what_host_features_emits_is_what_verdict_reads(featured):
    scope = part(foot_length_m=0.06, foot_width_m=0.02)
    cases = [
        (GW.CARBINE, "optic", scope, "fit", ("rail_teeth",)),
        (GW.CARBINE, "optic", part(foot_length_m=0.06, foot_width_m=0.01), "no_fit", ("rail_teeth",)),  # narrower than the 17 mm rail
        (GW.CARBINE, "optic", part(foot_length_m=0.20, foot_width_m=0.02), "no_fit", ("rail_teeth",)),  # longer than the 0.17 m run + 10 mm
        (GW.LOWRAIL, "underbarrel", scope, "fit", ("rail_teeth",)),
        (GW.FLATTOP, "optic", scope, "unverified", ("rail_flat",)),  # a flat seat lists nothing
        (GW.SCOPED, "optic", scope, "fit", ("seat_ref",)),
        (GW.STEPPED, "optic", scope, "fit", ("seat_ref",)),
        (GW.STEPPED, "optic", part(foot_length_m=0.09, foot_width_m=0.02), "no_fit", ("seat_ref",)),  # by the child's own 0.06 foot: no flat run
        (GW.FLATTOP, "underbarrel", scope, "not_judged", ()),
        (GW.CARBINE, "magazine", part(entry_section=(0.03, 0.02)), "fit", ("well_entry",)),
        (GW.CARBINE, "magazine", part(entry_section=(0.03, 0.04)), "no_fit", ("well_entry",)),
        (GW.CARBINE, "magazine", part(entry_section=None), "unverified", ("drum",)),
        (GW.UZI, "muzzle", part(mate_d_m=0.024, device_inner_d=None), "fit", ("barrel_ring", "frame_body")),
        (GW.UZI, "muzzle", part(mate_d_m=0.012, device_inner_d=None), "no_fit", ("barrel_ring", "frame_body")),
        (GW.FLAT, "muzzle", part(mate_d_m=0.017), "fit", ("barrel_round",)),  # E2-Q2: the rod rifle's end is one radius
    ]
    for name, slot, p, value, signals in cases:
        v = FG.verdict(slot, featured.feats[GW.pid(name)]["slots"][slot], p, None, RULES)
        assert (v.value, v.signals) == (value, signals), (name, slot, p)
    # neither authored seat has a flat run under its contact: the stepped one is a staircase, and the scoped one's longest flat run is the handguard
    assert featured.feats[GW.pid(GW.STEPPED)]["slots"]["optic"]["ref"]["flat_run_m"] is None
    assert featured.feats[GW.pid(GW.SCOPED)]["slots"]["optic"]["ref"]["flat_run_m"] is None
    # every host, every slot, a generic part: verdict accepts the shapes unchanged
    generic = part(foot_length_m=0.06, foot_width_m=0.02, mate_d_m=0.02, device_inner_d=None, entry_section=(0.03, 0.02))
    for pid, hf in featured.feats.items():
        assert sorted(hf) == ["located", "s0", "slots"] and sorted(hf["slots"]) == sorted(FOUR), pid
        for slot in FOUR:
            assert FG.verdict(slot, hf["slots"][slot], generic, None, RULES).value in FG.VERDICT_VALUES, (pid, slot)


# --- barrel_round, and the strip scope (G1 errata E1.1 and E1.3) ----------------------------------------------------------------------


def fit_mounts(muzzle_point, *, bore_source):
    """The four mounts ``host_features`` reads, for a hand-built host: a probe muzzle and three empty slots."""
    muz = {**none_mount("x"), "source": "probe", "point": muzzle_point, "reason": None, "bore_source": bore_source}
    return {"muzzle": muz, **{slot: none_mount("no_child_no_probe") for slot in ("optic", "underbarrel", "magazine")}}


AXES = {"forward": "+z", "up": "+y"}


def test_a_round_rod_barrel_without_a_ring_bore_is_barrel_round_and_a_square_one_is_not_asserted():
    # G1 errata E1.1: S7 stands on no square barrel. The rod (32 sides, solid, radius 8.5 mm) with a muzzle mount that found no ring bore
    # (bore_source face_extent) is a round section: barrel_round, OD 0.017, centre y 0.046, face z 0.65
    rod = GW.rod_rifle()
    feats = FG.host_features(RULES, axes=AXES, mounts=fit_mounts([0.0, 0.046, 0.65], bore_source="face_extent"), mesh=lambda drop: rod,
                             child_mesh=lambda name: None)
    end = feats["slots"]["muzzle"]["barrel_end"]
    assert (end["evidence"], feats["seats"]["muzzle"]) == ("round_section", {"feature": "barrel_round"})
    assert end["od_m"] == pytest.approx(0.017, abs=5e-4) and end["face_f"] == pytest.approx(0.65, abs=1e-4)
    assert end["centre_su"] == pytest.approx([0.0, 0.046], abs=5e-4)
    # the same mount with a ring bore is a ring
    ringed = FG.host_features(RULES, axes=AXES, mounts=fit_mounts([0.0, 0.046, 0.65], bore_source="ring"), mesh=lambda drop: rod,
                              child_mesh=lambda name: None)
    assert ringed["seats"]["muzzle"] == {"feature": "barrel_ring"}


def test_e1_3_the_strip_removes_only_the_parts_that_fill_a_slot_not_the_bodys_own_parts(monkeypatch):
    """G1 errata E1.3: "the host minus the located parts" is the host minus the located parts that fill an attachment slot.

    A preset assembled from separate pack parts (receiver, rail, barrel: no slot) plus a fused scope (slot optic): the locator finds all four,
    but only the scope is stripped. Stripping all four (the S7 first reading) empties the body: the rail and the barrel the detectors measure
    would be gone. The strip is spied on to read which placements it is given; the detectors' results show what is left."""
    host, parts = GW.body_preset()
    given: list[list[str]] = []
    real = FG.strip

    def spy(verts, tris, placements, part_meshes, rules):  # E1.2: strip takes the rules
        given.append(sorted(pl.part for pl in placements))
        return real(verts, tris, placements, part_meshes, rules)

    monkeypatch.setattr(FG, "strip", spy)
    feats = FG.host_features(RULES, axes=AXES, mounts=fit_mounts([0.0, 0.05, 0.2], bore_source="ring"), mesh=lambda drop: host,
                             child_mesh=lambda name: None, fused_parts=("body-preset", lambda: parts))
    assert sorted(p["part"] for p in feats["located"]) == ["barrel", "rail", "receiver", "scope"]  # all four are located
    assert given and all(g == ["scope"] for g in given), given  # and only the slot part is stripped
    run = feats["slots"]["optic"]["toothed_run"]  # the rail is still there: CARBINE's 8-tooth run, 0.188 long and 17 mm wide
    assert run["length_m"] == pytest.approx(0.188, abs=2e-3) and run["width_m"] == pytest.approx(0.017, abs=1e-3)
    end = feats["slots"]["muzzle"]["barrel_end"]  # and the barrel: its ring face at z 0.20
    assert end["face_f"] == pytest.approx(0.20, abs=1e-4) and end["od_m"] == pytest.approx(0.024, abs=5e-4)
    assert feats["seats"]["optic"]["feature"] == "rail_teeth"
