"""W8n: the per-id overrides Tom asked for on 2026-10-24, read from the SHIPPED ``weapon_overrides.json`` (not from a test doc).

* ``POLYGON_BattleRoyale/SM_Wep_Sniper_Heavy_01`` takes no barrel attachments ("takes no barrel attachments"): its ``muzzle`` slot is refused. The
  underbarrel and laser seats are NOT touched (listed for Tom to confirm);
* ``POLYGON_Military/SM_Wep_Preset_A_Sniper_01`` takes no attachment but a magazine ("built in scope and silencer so no attachments needed"; then "preset
  guns can take other magazines (size rule still applies). Keep refusing extra scopes and sights where one is built in"): six slots are refused, the magazine
  is left to the build (the override file carries no magazine entry). The B preset beside it is the control and keeps its slots;
* ``POLYGON_SciFi_Worlds/SM_Wep_Scope_Sniper_03`` is forward ``-z`` (Tom marked the as-placed scope "backwards" and the flipped one "ok", draw #2 o1/o2): the
  override beats the authored twin, so the part's exported anchor forward is the flipped one.

The worlds are synthetic (packs named like the real ones so the shipped ids hit). Every expected value is a LITERAL.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


W = _load("w8h_world")
M = _load("w8m_world")
GW = _load("g1_world")
A = W.A

from synty_inventory.weapons.overrides import empty_overrides, load_overrides  # noqa: E402

BR, MIL, SFW = "POLYGON_BattleRoyale", "POLYGON_Military", "POLYGON_SciFi_Worlds"
HEAVY = "SM_Wep_Sniper_Heavy_01"
PRESET_A, PRESET_B = "SM_Wep_Preset_A_Sniper_01", "SM_Wep_Preset_B_Sniper_01"
SNIPER3, SCOPE3 = "SM_Wep_Sniper_03", "SM_Wep_Scope_Sniper_03"
ALL = ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]


def world() -> dict:
    # G1 3.6 (S8): the sniper hosts get the rod rifle (the box rifle with a round rod barrel) so the silencer has a barrel end to fit: on the box rifle's
    # square barrel it is no_fit on every host, and the muzzle-refusal tests below would pass with the override removed
    rod = GW.rod_rifle
    return {
        BR: {"hosts": {HEAVY: W.host_node(HEAVY, rod())},
             "parts": {"SM_Wep_Attachment_Silencer_01": A.suppressor, "SM_Wep_Attachment_Foregrip_01": M.grip_part}},
        MIL: {"hosts": {PRESET_A: W.host_node(PRESET_A, rod()), PRESET_B: W.host_node(PRESET_B, rod())},
              "parts": {"SM_Wep_Mod_Silencer_01": A.suppressor, "SM_Wep_Mod_Foregrip_01": M.grip_part}},
        # the reversed scope (flare toward -z) and a host that bakes the same mesh as its scope child: a twin whose own forward is the host's +z
        SFW: {"hosts": {SNIPER3: W.host_node(SNIPER3, W.box_rifle(), [W.kid(SNIPER3, "Scope", A.flip_z(A.optic()), (0.0, 0.10, 0.10))])},
              "parts": {SCOPE3: lambda: A.flip_z(A.optic())}},
    }


def build(tmp_path, overrides):
    directory, _, _, _ = W.build(tmp_path, world(), overrides=overrides)
    return W.by_id(directory)


@pytest.fixture(scope="module")
def shipped(tmp_path_factory):
    return build(tmp_path_factory.mktemp("w8n_shipped"), load_overrides())


@pytest.fixture(scope="module")
def bare(tmp_path_factory):
    return build(tmp_path_factory.mktemp("w8n_bare"), empty_overrides())


def refused(m) -> bool:
    return m["source"] == "none" and m["reason"] == "slot_disabled"


def refused_slots(by, pack, host) -> list[str]:
    m = by[f"{pack}/{host}"]["geometry"]["mounts"]
    return [s for s in ALL if refused(m[s])]


def listed(by, pack, part) -> list[str]:
    att = by[f"{pack}/{part}"]["attachment"]
    return sorted(e["host"].split("/", 1)[1] for e in att["compatible_hosts"] + att["pending_hosts"])


def test_the_heavy_sniper_refuses_the_muzzle_and_only_the_muzzle(shipped, bare):
    assert "muzzle" not in refused_slots(bare, BR, HEAVY)
    assert "muzzle" in refused_slots(shipped, BR, HEAVY)
    assert [s for s in refused_slots(shipped, BR, HEAVY) if s != "muzzle"] == [s for s in refused_slots(bare, BR, HEAVY)]  # nothing else moves
    assert listed(shipped, BR, "SM_Wep_Attachment_Silencer_01") == []
    assert listed(bare, BR, "SM_Wep_Attachment_Silencer_01") == [HEAVY]


def test_the_heavy_sniper_keeps_the_underbarrel_seat_it_had(shipped):
    assert listed(shipped, BR, "SM_Wep_Attachment_Foregrip_01") == [HEAVY]  # Tom confirms whether the underbarrel goes too; this override leaves it


def test_the_a_sniper_preset_refuses_every_slot_but_the_magazine(shipped, bare):
    assert refused_slots(shipped, MIL, PRESET_A) == ["optic", "muzzle", "underbarrel", "laser_light", "sight_front", "sight_rear"]
    assert refused_slots(bare, MIL, PRESET_A) == []
    mag = lambda by: by[f"{MIL}/{PRESET_A}"]["geometry"]["mounts"]["magazine"]  # noqa: E731
    assert mag(shipped) == mag(bare) and mag(shipped)["source"] != "override"  # the override file leaves the magazine slot as the build made it
    assert listed(shipped, MIL, "SM_Wep_Mod_Silencer_01") == [PRESET_B]
    assert listed(shipped, MIL, "SM_Wep_Mod_Foregrip_01") == [PRESET_B]


def test_the_b_sniper_preset_beside_it_keeps_its_slots(shipped):
    assert refused_slots(shipped, MIL, PRESET_B) == []


def test_the_sniper_03_scope_is_forward_minus_z_though_its_twin_child_says_plus_z(shipped, bare):
    anchor = lambda by: by[f"{SFW}/{SCOPE3}"]["attachment"]["anchor"]  # noqa: E731
    assert (anchor(bare)["forward"], anchor(bare)["forward_source"]) == ([0.0, 0.0, 1.0], "twin")  # as Synty placed it: the host's own +z
    assert (anchor(shipped)["forward"], anchor(shipped)["forward_source"]) == ([0.0, 0.0, -1.0], "override")  # Tom: the flipped one is "ok"
    twin = [e for e in shipped[f"{SFW}/{SCOPE3}"]["attachment"]["compatible_hosts"] if e["host"] == f"{SFW}/{SNIPER3}"]
    assert [e["tier"] for e in twin] == ["twin"]  # the pair stays a twin; the part's exported forward is the flipped one
