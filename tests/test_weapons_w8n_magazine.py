"""W8n item 2: magazines (docs/weapon_attachments.md 13.7 A6-3), as G1 leaves them (S8; docs/weapon_attach_geometry.md 3.7, 3.8).

The two A6-3 rules are RETIRED: the drum-by-shape affinity row (``attach_compat.drum_min_m`` stays in the table as a dead key, kept by 3.8) and the
``attach_compat.fit_span_min`` lower bound (rejected by ``rules.py`` now). The magazine is a geometry slot: the tier is the pack relation and the listing is
the well-entry verdict (3.7), so a thick magazine, a short one and a thin one are judged by their entry section against the well and by nothing else.

Pure ``compat.candidate`` cases first (a host with no recorded features is ``not_judged``: a pending entry, so no foot, span or body size can veto or list
a pair any more), then a built directory (``w8n_world.mag_world``: three hosts with a 0.15 m well, four magazines). Every expected value is a LITERAL.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8n_world", FIX / "w8n_world.py")
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)
W = N.W

from synty_inventory.weapons import compat  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules, validate_rules  # noqa: E402

TABLES = attachment_rules(load_rules())
PARAMS = compat._params(TABLES)
AFFINITY = TABLES["attach_affinity"]
SAME, CROSS = "same_pack_fit", "cross_pack_fit"
PENDING_SAME = {"host": "P/Zulu_Host_01", "tier": SAME, "listed": False}


def part(foot=0.12, body_min=0.02, pack="P", **kw):
    base = {"id": f"{pack}/Zulu_Mag_01", "pack": pack, "slot": "magazine", "kind": "standard", "flags": set(), "tokens": frozenset({"zulu"}),
            "foot_length_m": foot, "mate_d_m": None, "setting": ("setting", "s"), "body_min_m": body_min}
    return {**base, **kw}


def host(span=0.15, archetype="rifle", pack="P", **kw):
    seat = {"source": "child_node", "span_m": span, "span_source": "child_foot", "bore_d_m": None, "bore_source": None, "occupied_by": ["Mag"],
            "reason": None}
    base = {"id": f"{pack}/Zulu_Host_01", "pack": pack, "archetype": archetype, "flags": set(), "mounts": {"magazine": seat},
            "tokens": frozenset({"zulu"}), "setting": ("setting", "s")}
    return {**base, **kw}


def cand(p, h, *, verdict=None, twin=False, params=PARAMS):
    return compat.candidate(p, h, verdict=verdict, twin=twin, affinity=AFFINITY, params=params)


def test_the_shipped_numbers_are_the_specified_literals():
    # G1 3.8 (S8): drum_min_m stays in the table (a dead key, kept for the kind classification); fit_span_min is gone
    assert TABLES["attach_compat"]["drum_min_m"] == 0.11 and "fit_span_min" not in TABLES["attach_compat"]
    assert "drum_min_m" not in PARAMS and "fit_span_min" not in PARAMS  # compat reads neither
    assert validate_rules(load_rules()) == []


# -- (ii) the lower bound is retired, pure -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("foot", "span"), [(0.09, 0.15), (0.10, 0.15), (0.1124, 0.15), (0.12, 0.15), (0.15, 0.15), (0.375, 0.50), (None, 0.15), (0.045, None)])
def test_a_same_pack_magazine_is_a_pending_entry_whatever_its_foot_against_the_well(foot, span):
    # G1 3.7/3.8: the foot-to-well ratio (0.60 ... 1.0 here) vetoes and lists nothing; with no recorded host features the pair is not_judged: bare pending
    assert cand(part(foot=foot), host(span=span)) == PENDING_SAME


def test_a_cross_pack_magazine_is_a_pending_cross_entry_whatever_its_foot():
    want = {"host": "P/Zulu_Host_01", "tier": CROSS, "listed": False}
    assert cand(part(foot=0.09, pack="Q"), host(span=0.15)) == want  # A8-1 parks a cross-pack magazine in pending; the bound that dropped it is retired
    assert cand(part(foot=0.12, pack="Q"), host(span=0.15)) == want


def test_a_twin_and_an_override_are_never_vetoed():
    assert cand(part(foot=0.045), host(span=0.15), twin=True)["tier"] == "twin"   # 0.30
    assert cand(part(foot=0.045), host(span=0.15), verdict="add")["tier"] == "override"
    assert cand(part(foot=0.045, pack="Q"), host(span=0.15), verdict="add")["tier"] == "override"


def test_a_pair_without_a_seat_is_pending():
    no_seat = host(span=None)
    no_seat["mounts"]["magazine"] = {"source": "none", "reason": "no_child_no_probe", "span_m": None}
    assert cand(part(foot=0.045), no_seat) == PENDING_SAME  # pending as before


def test_the_removed_bound_is_not_a_parameter_any_more():
    for value in (0.5, 0.9):
        assert cand(part(foot=0.09), host(span=0.15), params=dict(PARAMS, fit_span_min=value)) == PENDING_SAME  # a stale key in the params changes nothing


# -- (i) the drum by shape is retired, pure ----------------------------------------------------------------------------------


@pytest.mark.parametrize("archetype", ["pistol", "rifle", "sniper"])
@pytest.mark.parametrize("body_min", [0.02, 0.10, 0.1099, 0.11, 0.12, None])
def test_a_magazine_thick_on_both_sides_reads_no_drum_row_any_more(archetype, body_min):
    # G1 3.8: the `drum` row of attach_affinity and its 0.11 threshold are retired; a thick body (the drum shape) is judged by its entry section like any
    assert cand(part(foot=0.15, body_min=body_min), host(archetype=archetype)) == PENDING_SAME


def test_the_drum_number_is_not_read():
    assert cand(part(foot=0.15, body_min=0.12), host(archetype="pistol"), params=dict(PARAMS, drum_min_m=0.2)) == PENDING_SAME
    assert cand(part(foot=0.15, body_min=0.12), host(archetype="pistol"), params=dict(PARAMS, drum_min_m=0.01)) == PENDING_SAME


# -- a built directory ------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _, _, _ = W.build(tmp_path_factory.mktemp("w8n_mag"), N.mag_world())
    return W.by_id(directory)


def listed(by, name) -> dict:
    att = by[N.pid(name)]["attachment"]
    return {"compatible": {e["host"].split("/", 1)[1]: (e["tier"], e["score"], e["signals"]) for e in att["compatible_hosts"]},
            "pending": [e["host"].split("/", 1)[1] for e in att["pending_hosts"]]}


def test_the_fixture_is_what_the_comments_say(built):
    for host_name, archetype in ((N.MAG_RIFLE, "rifle"), (N.MAG_PISTOL, "pistol"), (N.MAG_SNIPER, "sniper")):
        m = built[N.pid(host_name)]["geometry"]["mounts"]["magazine"]
        assert built[N.pid(host_name)]["archetype"] == archetype
        assert m["source"] == "child_node" and m["span_m"] == pytest.approx(0.15, abs=0.001) and m["span_source"] == "child_foot"
    for name, foot, body_min in ((N.MAG_DRUM, 0.13, 0.12), (N.MAG_SLIM, 0.13, 0.02), (N.MAG_BOARD, 0.09, 0.02), (N.MAG_FAIR, 0.12, 0.02)):
        fp = built[N.pid(name)]["attachment"]["footprint"]
        assert fp["foot_length_m"] == pytest.approx(foot, abs=0.0006) and min(fp["length_m"], fp["width_m"]) == pytest.approx(body_min, abs=0.0006)


def test_the_drum_shaped_magazine_fits_every_well_whose_entry_it_matches_and_keeps_its_kind(built):
    # the wells of this world are the thick body's size (the baked magazine child), so the well-entry section of the 0.12 magazine matches all three hosts:
    # the pistol and the sniper no longer refuse it by archetype (G1 3.8). Tier base 0.7, signals `well_entry` (3.1 step 5, 3.7)
    assert built[N.pid(N.MAG_DRUM)]["attachment"]["kind"] == "standard"  # the record is unchanged
    assert listed(built, N.MAG_DRUM) == {
        "compatible": {N.MAG_PISTOL: ("same_pack_fit", 0.7, ["well_entry"]), N.MAG_RIFLE: ("same_pack_fit", 0.7, ["well_entry"]),
                       N.MAG_SNIPER: ("same_pack_fit", 0.7, ["well_entry"])}, "pending": []}


@pytest.mark.parametrize("name", [N.MAG_SLIM, N.MAG_BOARD, N.MAG_FAIR])
def test_the_thin_magazines_do_not_match_the_thick_well_and_list_nowhere(built, name):
    # no_fit (3.7): the 0.02 thin entry section is far off the well's 0.12; neither listed nor pending. Their foot (0.09, 0.12, 0.13 of 0.15) decides nothing
    assert listed(built, name) == {"compatible": {}, "pending": []}


def test_a_stale_fit_span_min_in_the_rules_changes_nothing_in_the_directory(tmp_path):
    rules = W.sight_rules()
    rules["attachment_rules"]["attach_compat"]["fit_span_min"] = 0.0
    assert validate_rules(rules) != []  # rejected as retired, so the world is built with the table as shipped and the key is read by nothing
    rules["attachment_rules"]["attach_compat"].pop("fit_span_min")
    by = W.by_id(W.build(tmp_path, N.mag_world(), rules=rules)[0])
    assert listed(by, N.MAG_BOARD) == {"compatible": {}, "pending": []}


def test_an_override_still_lists_the_board_magazine_on_a_host(tmp_path):
    ovr = W.overrides_doc(ids={N.pid(N.MAG_BOARD): {"compatible": {"add": [N.pid(N.MAG_PISTOL)]}}})
    by = W.by_id(W.build(tmp_path, N.mag_world(), overrides=ovr)[0])
    assert listed(by, N.MAG_BOARD)["compatible"] == {N.MAG_PISTOL: ("override", 1.0, ["override"])}


def test_the_rules_validation_rejects_a_malformed_drum_number_and_any_fit_span_min():
    for key, bad in (("drum_min_m", 0.0), ("drum_min_m", 1.5), ("drum_min_m", "big"), ("fit_span_min", 0.75), ("fit_span_min", -0.1), ("fit_span_min", True)):
        rules = deepcopy(load_rules())
        rules["attachment_rules"]["attach_compat"][key] = bad
        errors = validate_rules(rules)
        assert errors and any(key in e for e in errors), (key, bad, errors)
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_compat"]["fit_span_min"] = 0.75
    assert any("fit_span_min" in e and "retired" in e for e in validate_rules(rules))  # G1 3.8: a retired key, not a number out of range
