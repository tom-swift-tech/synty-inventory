"""GLB AABB measurement: synthetic fixtures (always run) + a real-pack
cross-check against asset-viewer aabb (skipped when the machine paths in
config.yaml/env aren't set up)."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "glb"))
from build_glb import (  # noqa: E402
    make_parent_child_doc,
    make_single_node_doc,
    plain_position_accessor,
    quantized_position_accessor,
    write_glb,
)

from synty_inventory.sources.glb_measure import measure_glb


def test_measure_quantized_translated_scaled_cube(tmp_path: Path):
    node = {"translation": [10.0, 0.0, 0.0], "scale": [2.0, 2.0, 2.0]}
    acc = quantized_position_accessor([-32767, -32767, -32767], [32767, 32767, 32767])
    doc = make_single_node_doc(node, acc)
    path = tmp_path / "cube.glb"
    write_glb(path, doc)

    result = measure_glb(path)
    assert result is not None
    mn, mx = result
    assert mn == pytest.approx([8.0, -2.0, -2.0], abs=1e-4)
    assert mx == pytest.approx([12.0, 2.0, 2.0], abs=1e-4)


def test_measure_hierarchy_with_rotation_and_translation(tmp_path: Path):
    # Parent: translated +100 on X, identity rotation/scale.
    parent = {"translation": [100.0, 0.0, 0.0]}
    # Child: rotated 90 degrees about +Y (quaternion x,y,z,w), no translation.
    half = math.sin(math.radians(45))
    child = {"rotation": [0.0, half, 0.0, math.cos(math.radians(45))]}
    # A non-cubic box (x extent 4, y extent 1, z extent 0.5) makes axis swap
    # from the rotation observable: new_x=old_z, new_y=old_y, new_z=-old_x.
    acc = plain_position_accessor([-2.0, -0.5, -0.25], [2.0, 0.5, 0.25])
    doc = make_parent_child_doc(parent, child, acc)
    path = tmp_path / "hierarchy.glb"
    write_glb(path, doc)

    result = measure_glb(path)
    assert result is not None
    mn, mx = result
    assert mn == pytest.approx([99.75, -0.5, -2.0], abs=1e-4)
    assert mx == pytest.approx([100.25, 0.5, 2.0], abs=1e-4)


def test_measure_missing_or_invalid_glb_returns_none(tmp_path: Path):
    assert measure_glb(tmp_path / "does_not_exist.glb") is None
    junk = tmp_path / "junk.glb"
    junk.write_bytes(b"not a glb")
    assert measure_glb(junk) is None


def test_measure_node_with_no_mesh_returns_none(tmp_path: Path):
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"translation": [1.0, 2.0, 3.0]}],
    }
    path = tmp_path / "empty.glb"
    write_glb(path, doc)
    assert measure_glb(path) is None


def _load_config_paths():
    from synty_inventory.paths import ConfigError, load_config

    try:
        return load_config(require=False)
    except ConfigError:
        return {}


def test_measure_matches_viewer_aabb_for_real_pack():
    """Cross-check 10 POLYGON_City GLBs against asset-viewer's own aabb.

    Skips outright when threejs_v2 / viewer_data aren't configured on this
    machine (CI / other contributors) rather than failing.
    """
    import json

    cfg = _load_config_paths()
    threejs_v2 = cfg.get("threejs_v2")
    viewer_data = cfg.get("viewer_data")
    if not threejs_v2 or not viewer_data:
        pytest.skip("threejs_v2 / viewer_data not configured")
    pack_json = viewer_data / "packs" / "POLYGON_City.json"
    if not pack_json.is_file():
        pytest.skip("POLYGON_City viewer profile not present")
    doc = json.loads(pack_json.read_text(encoding="utf-8"))
    pieces = doc.get("pieces") or {}

    checked = 0
    for asset_id, piece in pieces.items():
        rel = piece.get("file")
        aabb = piece.get("aabb") or {}
        if not rel or not aabb.get("min") or not aabb.get("max"):
            continue
        glb_path = threejs_v2 / "POLYGON_City" / rel
        if not glb_path.is_file():
            continue
        result = measure_glb(glb_path)
        assert result is not None, asset_id
        mn, mx = result
        for i in range(3):
            assert mn[i] == pytest.approx(aabb["min"][i], abs=2e-3), f"{asset_id} min[{i}]"
            assert mx[i] == pytest.approx(aabb["max"][i], abs=2e-3), f"{asset_id} max[{i}]"
        checked += 1
        if checked >= 10:
            break
    assert checked >= 1
