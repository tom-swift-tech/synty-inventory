"""E3.24: one forward override for underbarrel part 23 (docs/weapon_attach_geometry_errata.md E3.24d; attach version 17).

Tom picked from the a/b composites (2026-11-11): a for parts 02, 03, 04 and 22, b for part 23. Step 3c stays as built; part 23 gets an id-only
``forward`` override in ``weapon_overrides.json``. Part numbering is the index in the sorted list of the 24 underbarrel parts of the directory.

Every expected value is a LITERAL from the errata (part 23: a = forward -z from the free end, b = forward +z), never read from the overrides file.
The tests name no pack id: the new entry is found by its note, which starts with ``E3.24``.

* ``test_the_shipped_overrides_carry_one_e324_forward_plus_z``: red on attach 16 (the entry is missing).
* ``test_live_part_23_faces_b_and_the_rest_keep_their_source``: reads the cold copy-catalog directory named by ``SIT_E324_DIRECTORY``, else skips. Red
  on an attach-16 directory (no override source, version 16).
* the fixture test is a control: the override machinery already forces the sign on a part step 3c turns, green on the base.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from synty_inventory.weapons import WEAPON_ATTACH_VERSION, attach
from synty_inventory.weapons.overrides import default_overrides_path

PLUS_Z, MINUS_Z = [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]
LIVE = "SIT_E324_DIRECTORY"


def _e324_entries():
    ids = json.loads(default_overrides_path().read_text(encoding="utf-8"))["ids"]
    return {i: e for i, e in ids.items() if str(e.get("note", "")).startswith("E3.24")}


def test_the_shipped_overrides_carry_one_e324_forward_plus_z():
    found = _e324_entries()
    assert len(found) == 1, sorted(found)
    (entry,) = found.values()
    assert entry["forward"] == "+z"
    assert set(entry) == {"forward", "note"}  # an id-only forward and its note: no set, no confidence cap, no mounts


def test_the_attach_version_is_17():
    assert WEAPON_ATTACH_VERSION == 17


def _box(x0, x1, y0, y1, z0, z1):
    return np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)


def test_control_a_forward_override_turns_a_part_step_3c_pointed_at_minus_z():
    """The fixture of E3.23's AC154: a foregrip-shaped mesh leaning to +z with its larger end at +z. Step 3c turns it to -z from the free end;
    the override wins over it and gives +z with source override."""
    plate = _box(-0.01, 0.01, 0.036, 0.040, -0.015, 0.015)
    neck = _box(-0.004, 0.004, 0.030, 0.036, -0.005, 0.005)
    narrow = _box(-0.004, 0.004, -0.040, 0.030, 0.0, 0.0105)
    wide = _box(-0.012, 0.012, -0.040, 0.030, 0.0105, 0.030)
    v = np.vstack([plate, neck, narrow, wide])
    natural = attach.measure_anchor(v, "underbarrel", None, kind="foregrip")["anchor"]
    assert (natural["forward"], natural["forward_source"]) == (MINUS_Z, "free_end")
    forced = attach.measure_anchor(v, "underbarrel", "+z", kind="foregrip")["anchor"]
    assert (forced["forward"], forced["forward_source"], forced["symmetric"]) == (PLUS_Z, "override", False)


def _live():
    p = os.environ.get(LIVE)
    if not p or not Path(p).is_file():
        pytest.skip(f"{LIVE} names the cold copy-catalog directory file")
    return json.loads(Path(p).read_text(encoding="utf-8"))


def test_live_part_23_faces_b_and_the_rest_keep_their_source():
    d = _live()
    assert d["attach_version"] == 17
    parts = {r["id"]: r["attachment"] for r in d["weapons"] if (r.get("attachment") or {}).get("slot") == "underbarrel"}
    assert len(parts) == 24
    overridden = {i: a for i, a in parts.items() if a["anchor"]["forward_source"] == "override"}
    assert len(overridden) == 1, sorted(overridden)
    (a,) = overridden.values()
    assert a["kind"] == "foregrip" and a["anchor"]["forward"] == PLUS_Z and a["anchor"]["symmetric"] is False
    # E3.22's seven step-3c flips, less part 23 which is now an override: six remain, none of them a bipod
    flips = [i for i, a in parts.items() if a["kind"] != "bipod" and a["anchor"]["forward_source"] == "free_end"]
    assert len(flips) == 6, flips
