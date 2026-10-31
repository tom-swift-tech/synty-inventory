"""E3.23: step 3 takes the authored z axis on every foot slot (docs/weapon_attach_geometry_errata.md E3.23, ACs 153 and 154).

Pure synthetic fixtures. Every expected value is a LITERAL worked out from the fixture dimensions below, never read from the module under test. The
fixture extents clear the x-versus-z tie by 20 mm (60 against 40), well over the 5 mm the errata asks for, and are not measured from any part.

AC153 (step 3 takes z). Step 3 picks the along-rail axis of a foot slot by the longer horizontal extent of the whole mesh. A body wider than long
(x 60 mm, z 40 mm) is read as x-forward and mounts turned 90 degrees ("sight is sideways"). The rule takes z on every foot slot.
  (a) an optic, foot at the bottom, x 60 mm, z 40 mm: the anchor's forward is along z (today along x), the foot is 40 mm long (today 60);
  (b) the control optic, x 40 mm, z 60 mm: keeps z, foot 60 mm long, on the base and after the fix;
  (c) a magazine, foot at the top, x 60 mm, z 40 mm: forward along z, foot 40 mm;
  (d) a host whose bore runs +z, with a baked magazine child of x 60 mm, z 40 mm: that mount's span_m is 0.040 m within 1 mm (today it reads the x
      extent, 0.060 m). A host's baked child is measured by the same step 3 without a kind, so the fix reaches it; a "parts only" fix (z only when a
      kind is passed) leaves (d) red.
(Measured on the base, attach 15: (a), (c) and (d) are red, (b) is the green control.)

AC154 (fix 2 on top of fix 1). The E3.22 step-3c check over the 24 underbarrel parts of the live directory: exactly 7 flips and 0 pair changes
against attach 15. E3.23 reaches baked children for the axis pick only; step 3c stays parts-only (a kind is passed and it is not a bipod), so a
host's baked child, measured without a kind, keeps step 3's sign. On the base this is a GUARD, not a red: the value there is 7 flips, 0 pair
changes. The directory check needs the live copy-catalog directory and reads its paths from the environment (see ``_live``); without them it skips.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("g1_world", FIX / "g1_world.py")
GW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GW)
W, A = GW.W, GW.A

from synty_inventory.weapons import attach  # noqa: E402
from synty_inventory.weapons import directory as dirmod  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402

PLUS_Z, MINUS_Z = [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]


# --- AC153 -----------------------------------------------------------------------------------------------------------


def _box(x0, x1, y0, y1, z0, z1, d=0.002):
    g = lambda a, b: np.linspace(a, b, max(2, int(round((b - a) / d)) + 1))  # noqa: E731
    X, Y, Z = np.meshgrid(g(x0, x1), g(y0, y1), g(z0, z1), indexing="ij")
    return np.c_[X.ravel(), Y.ravel(), Z.ravel()]


def block(x_mm, z_mm):
    """A solid block ``x_mm`` wide (x) and ``z_mm`` long (z), 40 mm tall (y 0 to 0.040), centred on x = z = 0: its foot is the whole bottom
    face, or the whole top face for a magazine."""
    hx, hz = x_mm / 2000.0, z_mm / 2000.0
    return _box(-hx, hx, 0.0, 0.040, -hz, hz)


def _measured(v, slot, kind):
    got = attach.measure_anchor(v, slot, None, kind=kind)
    return got["anchor"]["forward"], got["footprint"]["foot_length_m"]


def _along_z(forward):
    return forward in (PLUS_Z, MINUS_Z)


def test_ac153_a_wide_optic_x60_z40_takes_forward_along_z_and_a_40_mm_foot():
    forward, foot = _measured(block(60, 40), "optic", "scope")
    assert _along_z(forward), forward  # base: [+-1, 0, 0]
    assert foot == pytest.approx(0.040, abs=0.001)  # base: 0.060


def test_ac153_the_control_optic_x40_z60_keeps_forward_along_z_and_a_60_mm_foot():
    forward, foot = _measured(block(40, 60), "optic", "scope")
    assert _along_z(forward), forward
    assert foot == pytest.approx(0.060, abs=0.001)


def test_ac153_a_wide_magazine_x60_z40_foot_at_the_top_takes_forward_along_z_and_a_40_mm_foot():
    forward, foot = _measured(block(60, 40), "magazine", "standard")
    assert _along_z(forward), forward  # base: [+-1, 0, 0]
    assert foot == pytest.approx(0.040, abs=0.001)  # base: 0.060


PACK, HOST = "FAKE_E323", "Rifle_Wide_01"


@pytest.fixture(scope="module")
def host_built(tmp_path_factory):
    """One host (the rod rifle: receiver, handguard and a round barrel, bore +z) with a baked magazine child ``Mag`` of x 60 mm, y -0.12..0, z 40 mm."""
    mag = A.mag_box(0.030, 0.12, 0.020)  # x +-0.030, y -0.12..0, z +-0.020
    world = {PACK: {"hosts": {HOST: W.host_node(HOST, GW.rod_rifle(), [W.kid(HOST, "Mag", mag, (0.0, 0.0, -0.05))])}, "parts": {}}}
    cat, root = W.write_world(tmp_path_factory.mktemp("e323_host"), world)
    directory, _ex, _report = dirmod.build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=W.pack_settings(world), rules=W.sight_rules(),
        threejs_v2_dir=root, geometry_cache={})
    return W.by_id(directory)[f"{PACK}/{HOST}"]["geometry"]["mounts"]


def test_ac153_a_host_with_a_baked_magazine_child_x60_z40_has_the_mount_span_040_not_060(host_built):
    m = host_built["magazine"]
    assert (m["source"], m["span_source"], m["occupied_by"]) == ("child_node", "child_foot", [f"{HOST}_Mag"]), m
    assert m["forward"] == PLUS_Z  # the host's bore runs +z, so the mount's forward is the host's
    assert m["span_m"] == pytest.approx(0.040, abs=0.001)  # base: 0.060, the across-bore x extent


# --- AC154 -----------------------------------------------------------------------------------------------------------

LIVE_DIR, LIVE_REF = "SIT_E323_DIRECTORY", "SIT_E323_REF_ATTACH15"


def _live():
    """``(directory under test, attach-15 reference directory)`` from the files named by the two environment variables, else skip. Both are
    directory JSONs of the cold copy-catalog build (``directory build``); on the base they are the same file."""
    paths = [os.environ.get(k) for k in (LIVE_DIR, LIVE_REF)]
    if not all(paths) or not all(Path(p).is_file() for p in paths):
        pytest.skip(f"{LIVE_DIR} and {LIVE_REF} name the live directory files")
    return [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]


def _underbarrel(d):
    return {r["id"]: r["attachment"] for r in d["weapons"] if (r.get("attachment") or {}).get("slot") == "underbarrel"}


def test_ac154_step_3c_flips_exactly_7_of_24_underbarrel_parts_and_changes_no_pair_against_attach_15():
    cur, ref = (_underbarrel(d) for d in _live())
    assert len(cur) == 24 and set(cur) == set(ref)
    # a flip is a non-bipod underbarrel part whose forward comes from the free end: step 3b applies to bipods only, so step 3c is the only other source
    flips = sorted(i for i, a in cur.items() if a["kind"] != "bipod" and a["anchor"]["forward_source"] == "free_end")
    assert len(flips) == 7, flips
    pairs = lambda a: ({h["host"] for h in a.get("compatible_hosts") or []}, {h["host"] for h in a.get("pending_hosts") or []})  # noqa: E731
    assert [i for i in cur if pairs(cur[i]) != pairs(ref[i])] == []  # 0 pair changes (listed and pending)


def test_ac154_step_3c_stays_parts_only_a_baked_child_measured_without_a_kind_keeps_step_3():
    """Fixture form of the same boundary, no directory needed: a foregrip-shaped mesh with a 15 mm lean to +z and its larger end at +z. With a
    kind (a foregrip part) step 3c turns it to -z from the free end; a bipod part and a host's baked child (no kind) keep +z."""
    plate = _box(-0.01, 0.01, 0.036, 0.040, -0.015, 0.015)
    neck = _box(-0.004, 0.004, 0.030, 0.036, -0.005, 0.005)
    narrow = _box(-0.004, 0.004, -0.040, 0.030, 0.0, 0.0105)
    wide = _box(-0.012, 0.012, -0.040, 0.030, 0.0105, 0.030)
    v = np.vstack([plate, neck, narrow, wide])
    get = lambda kind: attach.measure_anchor(v, "underbarrel", None, kind=kind)["anchor"]  # noqa: E731
    assert (get("foregrip")["forward"], get("foregrip")["forward_source"]) == (MINUS_Z, "free_end")
    assert (get("bipod")["forward"], get("bipod")["forward_source"]) == (PLUS_Z, "free_end")
    assert (get(None)["forward"], get(None)["forward_source"]) == (PLUS_Z, "section")
