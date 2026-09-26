"""files.glb_scale: per-GLB unit corrections (data/glb_scale_overrides.json).

The SciFi Space asteroids / planets / capital ships ship as threejs-v2 GLBs
100x too small (a 249 m asteroid measured 2.49 m and got scattered as a
ground rock). Every geometry reader must see the corrected size, and the
correction must be part of each cache id.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "glb"))

from build_glb import box_mesh, write_mesh_glb  # noqa: E402

from synty_inventory.project import slim_row  # noqa: E402
from synty_inventory.sources.footprint import apply_footprint  # noqa: E402
from synty_inventory.sources.glb_measure import apply_measured_bounds  # noqa: E402
from synty_inventory.sources.glb_scale import apply_glb_scale, glb_scale_for  # noqa: E402
from synty_inventory.sources.sockets import apply_prop_contact  # noqa: E402

SPACE = "POLYGON_SciFi_Space"

# The 2026-09-26 audit: every SciFi Space GLB whose size is exactly 100x off
# the synty-convert (Blender) GLB of the same FBX.
X100 = (
    [f"SM_Env_Asteroid_0{i}" for i in range(1, 8)]
    + [f"SM_Env_Planet_{i:02d}" for i in range(1, 15)]
    + [f"SM_Ship_Station_0{i}" for i in range(1, 6)]
    + [
        "SM_Ship_Galactic_Carrier_01",
        "SM_Ship_Massive_Transport_01",
        "SM_Ship_Colossal_01",
        "SM_Veh_WarpGate_Glow_01",
        "SM_Veh_WarpGate_Inner_01",
        "SM_Veh_WarpGate_Outer_01",
    ]
)


def _rel(stem: str) -> str:
    return f"{SPACE}/models/Models/{stem}.glb"


def test_table_covers_exactly_the_audited_glbs():
    assert len(X100) == 32
    for stem in X100:
        assert glb_scale_for(SPACE, _rel(stem)) == 100.0, stem
    assert glb_scale_for(SPACE, _rel("SM_Chr_Attach_Mask_Medic_01")) == 0.01


@pytest.mark.parametrize(
    "stem",
    ["SM_Ship_Station_06", "SM_Ship_Galactic_Carrier_Armor_01", "SM_Prop_Crate_01", "SM_Env_Asteroid_Belt_01"],
)
def test_right_sized_neighbours_are_not_matched(stem):
    assert glb_scale_for(SPACE, _rel(stem)) == 1.0


def test_other_packs_and_missing_glb_are_unscaled():
    assert glb_scale_for("POLYGON_SciFi_Worlds", "POLYGON_SciFi_Worlds/models/Models/SM_Env_Asteroid_01.glb") == 1.0
    assert glb_scale_for(SPACE, None) == 1.0


def test_keyed_by_glb_so_duplicate_records_inherit():
    """SM_Env_Planet_010 is a second record rendering SM_Env_Planet_10.glb."""
    a = {"id": "SM_Env_Planet_010", "files": {"glb": _rel("SM_Env_Planet_10")}}
    apply_glb_scale(a, SPACE)
    assert a["files"]["glb_scale"] == 100.0


def test_apply_drops_a_stale_scale():
    a = {"id": "X", "files": {"glb": _rel("SM_Prop_Crate_01"), "glb_scale": 100.0}}
    apply_glb_scale(a, SPACE)
    assert "glb_scale" not in a["files"]


@pytest.fixture
def root(tmp_path):
    models = tmp_path / "PACK" / "models"
    models.mkdir(parents=True)
    verts, tris = box_mesh([0, 0, 0], [2, 1, 2])
    write_mesh_glb(models / "SM_Test_01.glb", verts, tris)
    return tmp_path


def _asset(scale=None):
    files = {"glb": "PACK/models/SM_Test_01.glb"}
    if scale is not None:
        files["glb_scale"] = scale
    return {
        "id": "SM_Test_01",
        "type": "prop",
        "placeable": True,
        "files": files,
        "placement": {"mount": "ground", "constraints": []},
    }


def test_bounds_scale_and_do_not_reuse_the_unscaled_cache_entry(root):
    cache: dict = {}
    plain = _asset()
    apply_measured_bounds(plain, root, cache, {})
    scaled = _asset(100.0)
    apply_measured_bounds(scaled, root, cache, {})
    for p, s in zip(plain["bounds"]["size"], scaled["bounds"]["size"]):
        assert s == pytest.approx(p * 100.0, rel=1e-3)
    assert len(cache) == 2  # separate ids: a scale change re-measures


def test_footprint_is_measured_in_true_metres(root):
    plain, scaled = _asset(), _asset(10.0)
    apply_footprint(plain, root, {}, {})
    apply_footprint(scaled, root, {}, {})
    assert scaled["footprint"]["area_m2"] == pytest.approx(plain["footprint"]["area_m2"] * 100.0, rel=0.05)


def test_prop_contact_scales(root):
    plain, scaled = _asset(), _asset(100.0)
    apply_prop_contact(plain, root, {}, {})
    apply_prop_contact(scaled, root, {}, {})
    p = plain["placement"]["contact"]["position"]
    s = scaled["placement"]["contact"]["position"]
    for a, b in zip(p, s):
        assert b == pytest.approx(a * 100.0, abs=1e-3)


def test_projection_row_carries_the_scale():
    assert slim_row(SPACE, _asset(100.0))["glb_scale"] == 100.0
    assert "glb_scale" not in slim_row(SPACE, _asset())
