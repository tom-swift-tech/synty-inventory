"""FAKE_G1 population world: the three populations of ``attach-calibrate`` that ``g1_tools_world`` does not exercise (docs/weapon_attach_geometry.md
3.2, 4.2; plan slice S10a). Nothing is from a real pack: every mesh is a box, a loft or a tube built from the literals below, and every expected count in
a test is a LITERAL worked out by hand from them, never read from the code under test. Y-up, metres, +z forward.

It is ``g1_tools_world.tools_world()`` plus three hosts and one part, so the S9 world keeps its own counts (``test_weapons_g1_calibrate`` pins them):

  GLASS_HOST    the toothed carbine (8 teeth, run z -0.088 .. 0.100) with a baked scope body child (the long-foot optic of SCOPED_RAIL) AND a baked glass
                sheet, ``<host>_Sight_Glass``: a 4 mm wide, 3.2 mm tall sheet standing on the crests inside the run. The rules call a child whose name
                holds a ``baked_sights.glass_tokens`` word (``glass``) a glass sheet: a 3 mm foot that is no clamp and no optic positive. The scope body is
                the host's one optic positive; the sheet is dropped from the host mesh (a child) but bounds no row.
  BRAKE_PRESET  a preset (``Preset`` token): a box receiver, a ring tube barrel (the CARBINE's, ring face at z 0.20) and a muzzle brake FUSED
                onto its end: the pack's ``BRAKE`` part (a 20 mm square loft, z -0.1 .. 0.1) moved by ``MUZZLE_AT``. The part is a ``role == part`` record
                with NO attachment block (the classifier files it as ``part_misc``, G1 spec Q-G9) whose name the child vocabulary reads as a muzzle device
                (``brake``), as the real Military brake.
  HEAVY_PRESET  a preset that is NOT a host (``Heavy``: the classifier gives it hold class ``none``, so ``mounts.eligible`` is false and its record carries
                axes but no mounts), with the scope and the silencer of the pack FUSED into the rod rifle (``g1_world.preset_body``). The locator finds
                both parts on it, as it does on the real Heavy and Complex presets.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T = _load("g1_tools_world")
GW, FW, W, G = T.GW, T.FW, T.W, T.G

PACK = T.PACK
GLASS_HOST = "SM_Wep_Rifle_Notched_Sheeted_01"
BRAKE_PRESET = "SM_Wep_Preset_Carbine_03"
HEAVY_PRESET = "SM_Wep_Preset_Heavy_01"
BRAKE = "SM_Wep_Zulu_MuzzleBrake_01"

GLASS_AT = (0.0, 0.105, -0.04)  # the sheet's origin: its underside on the crests (y 0.105), 0.04 behind the origin of the run's middle, inside the run


def glass_sheet():
    """A 4 mm wide, 3.2 mm tall, 20 mm long sheet: the foot of a glass child is its width, 4 mm, against the rail's 17 mm."""
    return G.box((-0.002, 0.0, -0.01), (0.002, 0.0032, 0.01))


def brake_mesh():
    """A 20 mm square loft along z, -0.1 .. 0.1: its mating face is the one at -0.1 (the pack's other devices are 25 mm)."""
    return G.loft(2, [(-0.1, 0.01, 0.01), (0.1, 0.01, 0.01)])


def brake_preset_body():
    barrel = FW.tube(2, 0.10, 0.20, (0.0, 0.05))
    brake = brake_mesh()
    import numpy as np

    return G.merge(G.box((-0.02, 0.0, -0.12), (0.02, 0.10, 0.10)), barrel, (brake[0] + np.array(T.MUZZLE_AT), brake[1]))


def population_world() -> dict:
    """``tools_world()`` plus the hosts and the brake part above."""
    both = T.tools_world()
    hosts, parts = both[PACK]["hosts"], both[PACK]["parts"]
    hosts[GLASS_HOST] = W.host_node(GLASS_HOST, GW.carbine_body(), [
        W.kid(GLASS_HOST, "Mag", T.short_mag(), (0.0, 0.0, 0.0)), W.kid(GLASS_HOST, "Scope", T.long_foot_optic(), T.SCOPE_ON_RAIL),
        W.kid(GLASS_HOST, "Sight_Glass", glass_sheet(), GLASS_AT)])
    hosts[BRAKE_PRESET] = W.host_node(BRAKE_PRESET, brake_preset_body())
    hosts[HEAVY_PRESET] = W.host_node(HEAVY_PRESET, GW.preset_body())
    parts[BRAKE] = brake_mesh
    return both


def build(tmp: Path):
    """``(catalogs dir, threejs_v2 root, directory, excluded)``: the world written under ``tmp``, its directory built (cold caches) and stored."""
    from synty_inventory.weapons import directory as D
    from synty_inventory.weapons.overrides import empty_overrides

    world = population_world()
    cat, root = W.write_world(tmp, world)
    directory, excluded, _report = D.build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=W.pack_settings(world), rules=T.tools_rules(), threejs_v2_dir=root, geometry_cache={})
    D.write_directory(cat, directory, excluded)
    return cat, root, directory, excluded
