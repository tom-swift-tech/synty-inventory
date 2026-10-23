"""W8e: a hand-written weapon directory for ``preview.plan_pairs`` (no GLBs, no packs; only the fields the planner reads).

The point of the world is a slot in which a ``cross_pack_fit`` attachment sorts BEFORE a ``same_pack_fit`` one by part id, so a
sampler that orders by part id alone picks differently from one that takes the better tier first. Every id is invented.

Attachments (slot; part id order within a slot is the alphabetical order of the names):

    optic        Optic_A_Cross   cross_pack_fit on Host_X
                 Optic_B_Same    same_pack_fit  on Host_A
                 Optic_C_Same    same_pack_fit  on Host_A, and a twin of Host_B
    muzzle       Muzzle_A_Mixed  lists Host_X (cross_pack_fit) BEFORE Host_A (same_pack_fit): the best-tier host is the second entry
                 Muzzle_B_Cross  cross_pack_fit on Host_X
    underbarrel  Under_A_Twin    a twin of Host_B and nothing else (no non-twin candidate)
    magazine     Mag_A_Cross     cross_pack_fit on Host_X
    laser_light  Laser_A_Same    same_pack_fit on Host_A

Per attachment, the best non-twin pair: Optic_A cross, Optic_B same, Optic_C same, Muzzle_A same (Host_A), Muzzle_B cross,
Mag_A cross, Laser_A same; Under_A has none.
"""

from __future__ import annotations

SLOTS = ("optic", "muzzle", "underbarrel", "magazine", "laser_light")
PACK = "W8E_Plan"


def _host(name: str) -> dict:
    mounts = {s: {"point": [0.0, 0.0, 0.0], "forward": [0.0, 0.0, 1.0], "up": [0.0, 1.0, 0.0], "source": "child_node"} for s in SLOTS}
    return {"id": f"{PACK}/{name}", "pack": PACK, "files": {"glb": f"{name}.glb"}, "geometry": {"mounts": mounts}}


def _part(name: str, slot: str, hosts: list[tuple[str, str]]) -> dict:
    return {"id": f"{PACK}/{name}", "pack": PACK, "files": {"glb": f"{name}.glb"}, "geometry": {"mounts": {}},
            "attachment": {"slot": slot, "anchor": {"point": [0.0, 0.0, 0.0], "forward": [0.0, 0.0, 1.0], "up": [0.0, 1.0, 0.0]},
                           "compatible_hosts": [{"host": f"{PACK}/{h}", "tier": tier, "score": 0.5} for h, tier in hosts]}}


def directory() -> dict:
    """A fresh directory dict (callers may mutate it)."""
    weapons = [
        _host("Host_A"), _host("Host_B"), _host("Host_X"),
        _part("Optic_A_Cross", "optic", [("Host_X", "cross_pack_fit")]),
        _part("Optic_B_Same", "optic", [("Host_A", "same_pack_fit")]),
        _part("Optic_C_Same", "optic", [("Host_B", "twin"), ("Host_A", "same_pack_fit")]),
        _part("Muzzle_A_Mixed", "muzzle", [("Host_X", "cross_pack_fit"), ("Host_A", "same_pack_fit")]),
        _part("Muzzle_B_Cross", "muzzle", [("Host_X", "cross_pack_fit")]),
        _part("Under_A_Twin", "underbarrel", [("Host_B", "twin")]),
        _part("Mag_A_Cross", "magazine", [("Host_X", "cross_pack_fit")]),
        _part("Laser_A_Same", "laser_light", [("Host_A", "same_pack_fit")]),
    ]
    return {"weapons": weapons}
