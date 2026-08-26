"""T1 acceptance tests for sources.footprint (spec AC1-AC4 + invariants).

Geometry is composed from ``tests/fixtures/glb/build_glb.box_mesh`` boxes
merged into one mesh; the analyser derives connectivity from the raster, not
from mesh topology, so a merged mesh is a faithful stand-in for a real pack
GLB with several parts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "glb"))

from build_glb import box_mesh, write_mesh_glb  # noqa: E402

from synty_inventory.sources.footprint import (  # noqa: E402
    FOOTPRINT_VERSION,
    analyze_footprint,
    analyze_footprint_detail,
    check_invariants,
    is_collision_node,
)


def merge(*boxes):
    """Merge (mn, mx) boxes into one vertex/triangle list."""
    verts: list[list[float]] = []
    tris: list[list[int]] = []
    for mn, mx in boxes:
        v, t = box_mesh(mn, mx)
        base = len(verts)
        verts.extend(v)
        tris.extend([[i + base for i in tri] for tri in t])
    return verts, tris


def write(tmp_path: Path, name: str, *boxes) -> Path:
    verts, tris = merge(*boxes)
    path = tmp_path / f"{name}.glb"
    write_mesh_glb(path, verts, tris)
    return path


# --- AC1 ---------------------------------------------------------------------


def test_ac1_single_box(tmp_path):
    path = write(tmp_path, "box", ([0, 0, 0], [5, 3, 5]))
    fp = analyze_footprint(path)
    assert fp is not None
    assert len(fp["polygon_m"]) == 4
    assert fp["area_m2"] == pytest.approx(25.0, abs=0.01)
    assert fp["class"] == "compact"
    assert fp["fill_ratio"] >= 0.99
    assert fp["components"] == 1
    assert fp["version"] == FOOTPRINT_VERSION
    assert fp["source"] == "measured"


# --- AC2 ---------------------------------------------------------------------


def test_ac2_l_plan(tmp_path):
    # 10x10 with the +x/+z 5x5 quadrant removed: an L of area 75.
    path = write(
        tmp_path,
        "ell",
        ([0, 0, 0], [5, 3, 10]),
        ([5, 0, 0], [10, 3, 5]),
    )
    fp = analyze_footprint(path)
    assert fp is not None
    assert len(fp["polygon_m"]) == 6
    assert fp["area_m2"] == pytest.approx(75.0, abs=0.05)
    assert fp["class"] == "l_plan"
    # the notch corner is a real vertex of the ring
    assert any(p == [5.0, 5.0] for p in fp["polygon_m"]), fp["polygon_m"]


# --- AC3 ---------------------------------------------------------------------


def test_ac3_overhang(tmp_path):
    # 4x4 base, roof slab overhanging 1 m on +x, sitting above the grade band.
    path = write(
        tmp_path,
        "overhang",
        ([0, 0, 0], [4, 3, 4]),
        ([0, 3, 0], [5, 3.4, 4]),
    )
    fp = analyze_footprint(path)
    assert fp is not None
    assert fp["overhang_ratio"] > 0.15
    assert fp["grade_area_m2"] < fp["area_m2"]


# --- AC4 ---------------------------------------------------------------------


def test_ac4_disjoint_components(tmp_path):
    path = write(
        tmp_path,
        "disjoint",
        ([0, 0, 0], [2, 2, 2]),
        ([5, 0, 0], [7, 2, 2]),
    )
    fp = analyze_footprint(path)
    assert fp is not None
    assert fp["components"] == 2
    # polygon describes one component (4 m2); area covers both (8 m2)
    ring = fp["polygon_m"]
    xs = [p[0] for p in ring]
    assert max(xs) - min(xs) == pytest.approx(2.0, abs=0.01)
    assert fp["area_m2"] == pytest.approx(8.0, abs=0.05)


# --- rasterisation trap ------------------------------------------------------


def test_thin_wall_survives_rasterisation(tmp_path):
    """A 0.1 m wall is narrower than the 0.25 m cell. Centre sampling would
    drop it entirely; conservative SAT must keep it."""
    path = write(tmp_path, "wall", ([0, 0, 0], [0.1, 3, 5]))
    fp = analyze_footprint(path)
    assert fp is not None
    assert fp["area_m2"] > 0
    assert fp["class"] == "thin"
    assert len(fp["polygon_m"]) >= 4


def test_u_plan(tmp_path):
    path = write(
        tmp_path,
        "you",
        ([0, 0, 0], [10, 3, 3]),
        ([0, 0, 3], [3, 3, 10]),
        ([7, 0, 3], [10, 3, 10]),
    )
    fp = analyze_footprint(path)
    assert fp is not None
    assert fp["class"] == "u_plan"
    assert len(fp["polygon_m"]) == 8


# --- invariants --------------------------------------------------------------


def test_polygon_never_escapes_bounds(tmp_path):
    """INV-1 on an extent that is not a multiple of the snap - the case that
    conservative rasterisation would otherwise round outward."""
    path = write(tmp_path, "odd", ([0, 0, -5.0], [5.0, 3.054, 0.536]))
    fp = analyze_footprint(path)
    assert fp is not None
    xs = [p[0] for p in fp["polygon_m"]]
    zs = [p[1] for p in fp["polygon_m"]]
    assert min(xs) >= -1e-3 and max(xs) <= 5.0 + 1e-3
    assert min(zs) >= -5.0 - 1e-3 and max(zs) <= 0.536 + 1e-3
    assert fp["area_m2"] <= 5.0 * 5.536 + 1e-3
    assert fp["fill_ratio"] <= 1.0


def test_check_invariants_catches_escape():
    block = {
        "polygon_m": [[0, 0], [9, 0], [9, 9], [0, 9]],
        "area_m2": 81.0,
        "fill_ratio": 1.0,
        "grade_area_m2": 81.0,
        "overhang_ratio": 0.0,
    }
    assert check_invariants(block, [0.0, 0.0], [5.0, 5.0]) == "invariant_1"


def test_check_invariants_catches_clockwise():
    block = {
        "polygon_m": [[0, 0], [0, 5], [5, 5], [5, 0]],
        "area_m2": 25.0,
        "fill_ratio": 1.0,
        "grade_area_m2": 25.0,
        "overhang_ratio": 0.0,
    }
    assert check_invariants(block, [0.0, 0.0], [5.0, 5.0]) == "invariant_2"


def test_check_invariants_clean():
    block = {
        "polygon_m": [[0, 0], [5, 0], [5, 5], [0, 5]],
        "area_m2": 25.0,
        "fill_ratio": 1.0,
        "grade_area_m2": 25.0,
        "overhang_ratio": 0.0,
    }
    assert check_invariants(block, [0.0, 0.0], [5.0, 5.0]) is None


# --- INV-5 determinism -------------------------------------------------------


def test_deterministic(tmp_path):
    path = write(tmp_path, "det", ([0, 0, 0], [5, 3, 10]), ([5, 0, 0], [10, 3, 5]))
    a = analyze_footprint(path)
    b = analyze_footprint(path)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --- failure paths -----------------------------------------------------------


def test_undecodable_returns_reason(tmp_path):
    path = tmp_path / "not.glb"
    path.write_bytes(b"nope")
    block, reason = analyze_footprint_detail(path)
    assert block is None
    assert reason == "undecodable"


def test_non_finite_positions(tmp_path):
    verts, tris = box_mesh([0, 0, 0], [5, 3, 5])
    verts[0] = [float("nan"), 0.0, 0.0]
    path = tmp_path / "nan.glb"
    write_mesh_glb(path, verts, tris)
    block, reason = analyze_footprint_detail(path)
    assert block is None
    assert reason == "non_finite_positions"


# --- INV-8 collision filtering ----------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("SM_Bld_Shop_01", False),
        ("SM_Bld_Shop_01_Glass", False),
        ("SM_Bld_Shop_01_Convex", True),
        ("SM_Prop_Crate_01_Collision", True),
        ("SM_Prop_Crate_01_Collider", True),
        ("SM_Prop_Crate_01_Col", True),
        ("SM_Prop_Crate_01_ColMesh", True),
        ("SM_Prop_Crate_01_LOD1", True),
        ("Collisions/SM_Prop_Crate_01", True),
        ("", False),
    ],
)
def test_is_collision_node(name, expected):
    assert is_collision_node(name) is expected


def test_collision_node_excluded_from_footprint(tmp_path):
    """A collision hull twice the size of the render mesh must not widen the
    footprint. Node names come from the GLB, so the two boxes go in as
    separate nodes."""
    render_v, render_t = box_mesh([0, 0, 0], [4, 3, 4])
    hull_v, hull_t = box_mesh([0, 0, 0], [12, 3, 12])
    verts = render_v + hull_v
    tris = render_t + [[i + len(render_v) for i in t] for t in hull_t]

    path = tmp_path / "with_collision.glb"
    write_mesh_glb(path, verts, tris)
    both = analyze_footprint(path)
    assert both is not None
    assert both["area_m2"] == pytest.approx(144.0, abs=0.5)  # hull dominates

    # Same geometry, hull in its own named node: excluded.
    import struct

    import numpy as np  # noqa: F401

    doc_path = tmp_path / "split.glb"
    _write_two_node_glb(doc_path, render_v, render_t, hull_v, hull_t, "SM_Test_01", "SM_Test_01_Convex")
    only_render = analyze_footprint(doc_path)
    assert only_render is not None
    assert only_render["area_m2"] == pytest.approx(16.0, abs=0.05)
    assert struct  # keep the import meaningful for linters


def _write_two_node_glb(path, v0, t0, v1, t1, name0, name1):
    """Two named nodes, one mesh each, sharing one BIN chunk."""
    import itertools
    import json as _json
    import struct as _struct

    GLB_MAGIC = 0x46546C67
    CHUNK_JSON = 0x4E4F534A
    CHUNK_BIN = 0x004E4942

    chunks = []
    offset = 0
    views = []
    accessors = []
    meshes = []
    for verts, tris in ((v0, t0), (v1, t1)):
        pos = _struct.pack(f"<{len(verts) * 3}f", *itertools.chain.from_iterable(verts))
        flat = list(itertools.chain.from_iterable(tris))
        idx = _struct.pack(f"<{len(flat)}H", *flat)
        idx += b"\0" * ((-len(idx)) % 4)
        mins = [min(x[i] for x in verts) for i in range(3)]
        maxs = [max(x[i] for x in verts) for i in range(3)]
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(pos)})
        views.append({"buffer": 0, "byteOffset": offset + len(pos), "byteLength": len(flat) * 2})
        accessors.append(
            {"bufferView": len(views) - 2, "componentType": 5126, "count": len(verts), "type": "VEC3", "min": mins, "max": maxs}
        )
        accessors.append({"bufferView": len(views) - 1, "componentType": 5123, "count": len(flat), "type": "SCALAR"})
        meshes.append(
            {"primitives": [{"attributes": {"POSITION": len(accessors) - 2}, "indices": len(accessors) - 1, "mode": 4}]}
        )
        chunks.append(pos + idx)
        offset += len(pos) + len(idx)

    blob = b"".join(chunks)
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [{"mesh": 0, "name": name0}, {"mesh": 1, "name": name1}],
        "meshes": meshes,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    body = _json.dumps(doc).encode("utf-8")
    body += b" " * ((-len(body)) % 4)
    total = 12 + 8 + len(body) + 8 + len(blob)
    path.write_bytes(
        _struct.pack("<III", GLB_MAGIC, 2, total)
        + _struct.pack("<II", len(body), CHUNK_JSON)
        + body
        + _struct.pack("<II", len(blob), CHUNK_BIN)
        + blob
    )
