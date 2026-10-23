"""W8l: versions, the cache keys, the three new rule tables and the order of twin and free end (docs/weapon_attachments.md A4; AC105 (vi), AC110).

The expected values are LITERALS from the spec (attach version 9 since A5, geometry version 5, rules digest 7b9829af37328fe7), never read from the
constants under test.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8h_world", FIX / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

import synty_inventory.weapons as pkg  # noqa: E402
from synty_inventory.weapons import geometry as geo  # noqa: E402
from synty_inventory.weapons.rules import attach_rules_digest, load_rules, validate_rules, weapon_rules_digest  # noqa: E402

G = W.G
PACK = "FAKE_W8L"
HOST = "SM_Wep_Rifle_Alpha_01"


# --- AC110: versions -------------------------------------------------------------------------------------------------


def test_ac110_the_versions_and_the_rules_digest():
    assert pkg.WEAPON_ATTACH_VERSION == 9 and pkg.WEAPON_GEOMETRY_VERSION == 5
    assert weapon_rules_digest(load_rules()) == "7b9829af37328fe7"  # the three new tables sit inside attachment_rules: rules_digest never moves
    assert len(attach_rules_digest(load_rules())) == 16


def test_ac110_the_new_tables_move_the_attach_digest_and_never_the_rules_digest():
    base, rules = load_rules(), deepcopy(load_rules())
    rules["attachment_rules"]["family_free_slots"] = ["muzzle"]
    assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)
    rules = deepcopy(base)
    rules["attachment_rules"]["anchor"]["foot_depths_m"] = [0.004, 0.008]
    assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)


def test_ac110_the_directory_header_records_attach_version_9(tmp_path):
    directory = W.build(tmp_path, {PACK: {"hosts": {HOST: W.host_node(HOST, W.box_rifle())}}})[0]
    assert directory["attach_version"] == 9 and directory["geometry_version"] == 5


# --- AC110: the geometry cache keys follow the new inputs and the new code --------------------------------------------------


def part_fp(rules=None, kind="standard", slot="magazine"):
    return geo._inputs_fingerprint("unknown", None, "part", "none", None, rules or W.sight_rules(), attach_slot=slot, attach_kind=kind)


def host_fp(rules=None):
    return geo._inputs_fingerprint("rifle", "ranged", "whole", "long_gun", "modern", rules or W.sight_rules(), host_id=f"{PACK}/{HOST}")


def test_ac110_a_part_fingerprint_follows_its_kind_and_the_anchor_table():
    base = part_fp()
    assert part_fp() == base
    assert part_fp(kind="drum") != base  # the free-end rule is kind-driven
    rules = W.sight_rules()
    rules["attachment_rules"]["anchor"]["free_end"]["min_displacement_m"] = 0.005
    assert part_fp(rules) != base
    rules = W.sight_rules()
    rules["attachment_rules"]["anchor"]["foot_depths_m"] = [0.004, 0.008]
    assert part_fp(rules) != base


def test_ac110_a_host_fingerprint_follows_the_anchor_table():
    base = host_fp()
    assert host_fp() == base
    rules = W.sight_rules()
    rules["attachment_rules"]["anchor"]["lip_growth"] = 3.0
    assert host_fp(rules) != base


def test_ac110_the_cache_misses_when_the_anchor_or_mounts_code_changes(tmp_path, monkeypatch):
    world = W.write_world(tmp_path, {PACK: {"hosts": {HOST: W.host_node(HOST, W.box_rifle())}}})[1]

    def measure(cache):
        return geo.measure_cached(world, f"glb/{PACK}/{HOST}.glb", None, 1.0, "rifle", "ranged", "whole", W.sight_rules(), cache,
                                  hold_class="long_gun", genre="modern", host_id=f"{PACK}/{HOST}")[1]

    cache: dict = {}
    assert measure(cache) is False and measure(cache) is True
    monkeypatch.setattr(geo, "_MOUNTS_CODE_DIGEST", "0" * 16)  # as if mounts.py had changed (the mirrored pair lives there)
    assert measure(cache) is False
    monkeypatch.undo()
    assert measure(cache) is True
    monkeypatch.setattr(geo, "_ATTACH_CODE_DIGEST", "0" * 16)  # as if attach.py had changed (the ladder and the free end live there)
    assert measure(cache) is False


def test_ac110_a_part_entry_misses_when_the_anchor_code_or_the_kind_changes(tmp_path, monkeypatch):
    root = W.write_world(tmp_path, {PACK: {"parts": {"SM_Wep_Alpha_Mag_01": W.A.mag_box(0.01, 0.12, 0.02)}}})[1]

    def measure(cache, kind="standard"):
        return geo.measure_cached(root, f"glb/{PACK}/SM_Wep_Alpha_Mag_01.glb", None, 1.0, "unknown", None, "part", W.sight_rules(), cache,
                                  hold_class="none", genre=None, attach_slot="magazine", attach_kind=kind)[1]

    cache: dict = {}
    assert measure(cache) is False and measure(cache) is True
    assert measure(cache, "drum") is False  # another kind is another measurement
    monkeypatch.setattr(geo, "_ATTACH_CODE_DIGEST", "0" * 16)
    assert measure(cache) is False


# --- the three new rule tables validate -------------------------------------------------------------------------------------


def broken(mutate):
    rules = deepcopy(load_rules())
    mutate(rules["attachment_rules"])
    return validate_rules(rules)


def test_the_shipped_rules_validate_with_the_three_tables():
    assert validate_rules(load_rules()) == []


@pytest.mark.parametrize(("mutate", "needle"), [
    (lambda t: t["anchor"].update(foot_depths_m=[0.008, 0.004]), "strictly increasing"),
    (lambda t: t["anchor"].update(foot_depths_m=[]), "foot_depths_m"),
    (lambda t: t["anchor"].update(lip_min_m=0.01, lip_max_m=0.002), "lip_min_m must not exceed"),
    (lambda t: t["anchor"].update(lip_growth=0.5), "lip_growth"),
    (lambda t: t["anchor"].pop("lip_growth"), "lip_growth"),
    (lambda t: t["anchor"].update(surprise=1), "surprise"),
    (lambda t: t["anchor"]["free_end"].update(min_displacement_m=0), "min_displacement_m"),
    (lambda t: t["anchor"]["free_end"]["kinds"].update(muzzle=["suppressor"]), "foot slot"),
    (lambda t: t["anchor"]["free_end"]["kinds"].update(magazine=["no_such_kind"]), "kinds of that slot"),
    (lambda t: t["anchor"]["free_end"]["kinds"].update(nonsense=["standard"]), "nonsense"),
    (lambda t: t.update(family_free_slots=["muzzle", "muzzle"]), "distinct"),
    (lambda t: t.update(family_free_slots=["barrel"]), "family_free_slots"),
    (lambda t: t.update(family_free_slots="muzzle"), "family_free_slots"),
    (lambda t: t.update(optic_seat={"lift_cap_m": 0.04}), "optic_seat"),  # A5 retired the table: a leftover key is an unknown key
])
def test_the_new_tables_reject_a_malformed_value(mutate, needle):
    errors = broken(mutate)
    assert errors and any(needle in e for e in errors), errors


def test_an_empty_family_free_slots_list_is_valid():
    assert broken(lambda t: t.update(family_free_slots=[])) == []


# --- twin evidence against the free end (AC105 vi) ---------------------------------------------------------------------------


def banana(lean: float):
    """The magazine of the anchor tests as a real mesh: foot slab, upper body, a back plate at -z and a lower box leaning ``lean`` toward +z."""
    return G.merge(G.box((-0.010, -0.004, -0.010), (0.010, 0.0, 0.010)), G.box((-0.010, -0.140, -0.010), (0.010, -0.004, 0.010)),
                   G.box((-0.030, -0.140, -0.050), (0.030, -0.010, -0.040)), G.box((-0.010, -0.200, lean - 0.010), (0.010, -0.140, lean + 0.010)))


def mirrored(mesh):
    """The mesh flipped in z (winding kept): the plate at +z and the lower box leaning toward -z. The section prior reads +z, the free end -z."""
    v, t = mesh
    return v * [1.0, 1.0, -1.0], t[:, [0, 2, 1]]


@pytest.fixture(scope="module")
def parts(tmp_path_factory):
    # The twin evidence of spec 3.4 step 3a is the host mount's forward (+z, the gun's forward) for a part whose mesh is oriented like the baked
    # child it twins. One host whose Mag child is the same mirrored mesh as two of the parts (the evidence says +z where the free end says -z),
    # and a third part 1.2 times as big, which twins nothing (20 % is far outside the twin tolerance) and leans 36 mm toward -z.
    host = "SM_Wep_Rifle_Alpha_01"

    def big():
        v, t = mirrored(banana(0.030))
        return v * 1.2, t

    world = {PACK: {
        "hosts": {host: W.host_node(host, W.box_rifle(), [W.kid(host, "Mag", mirrored(banana(0.030)), (0.0, 0.0, 0.0))])},
        "parts": {"SM_Wep_Alpha_Mag_01": lambda: mirrored(banana(0.030)), "SM_Wep_Alpha_DrumMag_01": lambda: mirrored(banana(0.030)),
                  "SM_Wep_Beta_Mag_01": big},
    }}
    directory = W.build(tmp_path_factory.mktemp("w8l_versions"), world)[0]
    return {w["asset_id"]: w for w in directory["weapons"]}


def anchor(parts, name):
    return parts[name]["attachment"]["anchor"]


def test_ac105_a_standard_magazine_without_twin_evidence_takes_the_free_end(parts):
    a = anchor(parts, "SM_Wep_Beta_Mag_01")
    assert (a["forward"], a["forward_source"], a["symmetric"]) == ([0.0, 0.0, -1.0], "free_end", False)
    assert "anchor_forward_unsure" not in parts["SM_Wep_Beta_Mag_01"]["review"]["reasons"]


def test_ac105_twin_evidence_of_the_opposite_sign_beats_the_free_end(parts):
    twin = parts["SM_Wep_Alpha_Mag_01"]["attachment"]
    a = twin["anchor"]
    assert twin["compatible_hosts"][0]["tier"] == "twin"
    assert (a["forward"], a["forward_source"], a["symmetric"]) == ([0.0, 0.0, 1.0], "twin", False)  # the free end said -z; the baked child says +z


def test_ac105_a_drum_of_the_same_shape_takes_no_free_end(parts):
    a = anchor(parts, "SM_Wep_Alpha_DrumMag_01")
    assert (a["forward"], a["forward_source"]) == ([0.0, 0.0, 1.0], "section")  # the kind is not in the pair table: the section prior (+z) stands
