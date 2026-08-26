"""Mesh decoding (meshopt codecs, GLB triangle loading) and ship-part
socket / mount analysis. Synthetic fixtures always run; the meshopt codec
check reads one small real SciFi_Space GLB and skips when it is absent."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "glb"))
from build_glb import box_mesh, write_mesh_glb  # noqa: E402

from synty_inventory.schema import validate_socket
from synty_inventory.sources import sockets as sk
from synty_inventory.sources.glb_geometry import load_triangles
from synty_inventory.sources.meshopt import MeshoptError, decode_index_buffer, decode_vertex_buffer

def _real_part_glb() -> Path:
    """One small real SciFi_Space greeble (meshopt-compressed) — skipped when
    the machine paths in config.yaml/env aren't set up. No mesh data is
    committed: Synty geometry stays on the local disk."""
    from synty_inventory.paths import ConfigError, load_config

    try:
        cfg = load_config(require=False)
    except ConfigError:
        pytest.skip("config not loadable")
    root = cfg.get("threejs_v2")
    if not root:
        pytest.skip("threejs_v2 not configured")
    path = Path(root) / "POLYGON_SciFi_Space" / "models" / "Models" / "SM_Veh_Part_Misc_04.glb"
    if not path.is_file():
        pytest.skip("POLYGON_SciFi_Space GLBs not present")
    return path


# --- meshopt codecs ---------------------------------------------------------


def test_meshopt_decode_real_part_matches_accessor_min_max():
    """Decoded POSITION ints must hit the accessor's own min/max exactly and
    every index must address a vertex — an encoder-independent check."""
    from synty_inventory.sources.glb_geometry import _read_accessor, read_glb

    doc, blob = read_glb(_real_part_glb())
    prim = doc["meshes"][0]["primitives"][0]
    pos_acc = doc["accessors"][prim["attributes"]["POSITION"]]
    view = doc["bufferViews"][pos_acc["bufferView"]]["extensions"]["EXT_meshopt_compression"]
    stream = blob[view["byteOffset"]:view["byteOffset"] + view["byteLength"]]
    assert stream[0] == 0xA0, "fixture assumes the v0 vertex codec"
    raw = decode_vertex_buffer(stream, view["count"], view["byteStride"])
    assert len(raw) == view["count"] * view["byteStride"]
    pos = _read_accessor(doc, blob, prim["attributes"]["POSITION"])
    assert pos.min(axis=0).tolist() == [float(v) for v in pos_acc["min"]]
    assert pos.max(axis=0).tolist() == [float(v) for v in pos_acc["max"]]

    idx_acc = doc["accessors"][prim["indices"]]
    iview = doc["bufferViews"][idx_acc["bufferView"]]["extensions"]["EXT_meshopt_compression"]
    idx = decode_index_buffer(blob[iview["byteOffset"]:iview["byteOffset"] + iview["byteLength"]], iview["count"])
    assert len(idx) == iview["count"] == idx_acc["count"]
    assert min(idx) >= 0 and max(idx) < len(pos)
    assert len(set(idx)) == len(pos), "every vertex referenced"


def test_meshopt_rejects_foreign_streams():
    with pytest.raises(MeshoptError):
        decode_vertex_buffer(bytes(64), 4, 8)  # not a vertex header
    with pytest.raises(MeshoptError):
        decode_index_buffer(bytes([0xA0]) + bytes(32), 3)  # vertex header on an index stream
    with pytest.raises(MeshoptError):
        decode_vertex_buffer(bytes([0xA1]) + bytes(64), 4, 8)  # v1 vertex codec unsupported


# --- GLB triangle loading ---------------------------------------------------


def test_load_triangles_applies_node_transform(tmp_path: Path):
    v, t = box_mesh([-1, -1, -1], [1, 1, 1])
    path = tmp_path / "box.glb"
    write_mesh_glb(path, v, t, node={"translation": [10.0, 0.0, 0.0], "scale": [2.0, 2.0, 2.0]})
    got = load_triangles(path)
    assert got is not None
    verts, tris = got
    assert verts.shape == (8, 3) and tris.shape == (12, 3)
    assert verts.min(axis=0).tolist() == pytest.approx([8.0, -2.0, -2.0])
    assert verts.max(axis=0).tolist() == pytest.approx([12.0, 2.0, 2.0])


def test_load_triangles_none_for_junk(tmp_path: Path):
    junk = tmp_path / "junk.glb"
    junk.write_bytes(b"nope")
    assert load_triangles(junk) is None
    assert load_triangles(tmp_path / "missing.glb") is None


# --- socket / mount analysis ------------------------------------------------


def _box(mn, mx):
    v, t = box_mesh(mn, mx)
    return np.array(v, dtype=np.float64), np.array(t, dtype=np.int64)


def test_body_box_gets_six_measured_sockets_at_face_centres():
    verts, tris = _box([-1.0, 0.0, -2.0], [1.0, 1.0, 2.0])
    res = sk.analyse_part(verts, tris, "body", "any")
    assert res["mount"] is None
    by_role = {s["role"]: s for s in res["sockets"]}
    assert set(by_role) == {"front", "rear", "left", "right", "top", "bottom"}
    assert by_role["front"]["position"] == pytest.approx([0.0, 0.5, 2.0])
    assert by_role["front"]["normal"] == [0.0, 0.0, 1.0]
    assert by_role["rear"]["position"] == pytest.approx([0.0, 0.5, -2.0])
    assert by_role["bottom"]["position"] == pytest.approx([0.0, 0.0, 0.0])
    assert by_role["right"]["axis"] == "+x" and by_role["left"]["axis"] == "-x"
    for s in by_role.values():
        assert s["source"] == "measured"
        assert s["fit"] == pytest.approx(1.0)
    assert by_role["front"]["area"] == pytest.approx(2.0)
    assert by_role["front"]["extent"] == pytest.approx([2.0, 1.0])


def test_cockpit_mount_is_its_rear_cap():
    # Cockpit: pivot at the rear, nose along +z. mates_axis "+z" (the body's
    # front socket) -> its own mount cap faces -z.
    verts, tris = _box([-0.5, -0.5, 0.0], [0.5, 0.5, 3.0])
    res = sk.analyse_part(verts, tris, "cockpit", "+z")
    m = res["mount"]
    assert m["axis"] == "-z" and m["source"] == "measured"
    assert m["position"] == pytest.approx([0.0, 0.0, 0.0])
    assert m["normal"] == [0.0, 0.0, -1.0]
    assert m["parent_role"] == "front"
    assert res["sockets"] == []
    # centred pivot: still the class axis
    verts, tris = _box([-0.5, -0.5, -1.5], [0.5, 0.5, 1.5])
    assert sk.analyse_part(verts, tris, "cockpit", "+z")["mount"]["axis"] == "-z"


def test_engine_and_gear_mounts_follow_mates_axis():
    verts, tris = _box([-0.5, -0.5, -3.0], [0.5, 0.5, 0.0])
    assert sk.analyse_part(verts, tris, "engine", "-z")["mount"]["axis"] == "+z"
    verts, tris = _box([-0.2, -1.0, -0.2], [0.2, 0.0, 0.2])
    gear = sk.analyse_part(verts, tris, "landing_gear", "-y")["mount"]
    assert gear["axis"] == "+y" and gear["position"] == pytest.approx([0.0, 0.0, 0.0])


def _two_boxes(b1, b2):
    v1, t1 = box_mesh(*b1)
    v2, t2 = box_mesh(*b2)
    verts = np.array(v1 + v2, dtype=np.float64)
    tris = np.array(t1 + [[a + 8, b + 8, c + 8] for a, b, c in t2], dtype=np.int64)
    return verts, tris


def test_wing_root_is_the_dominant_x_cap_even_with_centred_pivot():
    # Synty wings are single pieces, pivot centred: thick root block at -x,
    # thin tip at +x -> the larger x cap is the root, regardless of pivot.
    verts, tris = _two_boxes(([-2.0, -0.3, -1.0], [0.0, 0.3, 1.0]), ([0.0, -0.05, -0.5], [2.0, 0.05, 0.5]))
    m = sk.analyse_part(verts, tris, "wing", "±x")["mount"]
    assert m["axis"] == "-x" and m["source"] == "measured"
    assert m["position"] == pytest.approx([-2.0, 0.0, 0.0])
    assert m["parent_role"] == "right"  # a -x root sits on the hull's +x side
    # Fin: two equal side faces are not root/tip -> mounts by its larger y cap.
    verts, tris = _box([-0.2, 0.0, -1.0], [0.2, 2.0, 1.0])
    m = sk.analyse_part(verts, tris, "wing", "±x")["mount"]
    assert m["axis"] == "-y" and m["parent_role"] == "top"


def test_wing_root_with_dihedral_is_found_and_keeps_its_tilt():
    # Root face rotated 20 deg about z (dihedral): outside the 10 deg cap
    # cone, inside the wing-root cone. The mount reports the real normal.
    ang = np.radians(20.0)
    rot = np.array([[np.cos(ang), -np.sin(ang), 0.0], [np.sin(ang), np.cos(ang), 0.0], [0.0, 0.0, 1.0]])
    v, t = box_mesh([0.0, -0.1, -0.5], [3.0, 0.1, 0.5])
    verts = np.array(v, dtype=np.float64) @ rot.T
    tris = np.array(t, dtype=np.int64)
    # make the +x end non-flat so only the -x root can be the mount
    verts = np.vstack([verts, [[3.5, 0.0, 0.0]]])
    m = sk.analyse_part(verts, tris, "wing", "±x")["mount"]
    assert m["axis"] == "-x" and m["source"] == "measured"
    assert m["normal"] == pytest.approx([-np.cos(ang), -np.sin(ang), 0.0], abs=1e-3)
    assert m["position"] == pytest.approx([0.0, 0.0, 0.0], abs=1e-6)
    # nothing flat within 30 deg of any axis (an octahedron: every face is
    # ~55 deg off every axis) -> AABB root at -x
    verts = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], dtype=np.float64) + [0, 2, 0]
    tris = np.array(
        [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]], dtype=np.int64
    )
    m = sk.analyse_part(verts, tris, "wing", "±x")["mount"]
    assert m["source"] == "aabb" and m["axis"] == "-x" and m["parent_role"] == "right"


def test_pivot_at_the_mating_plane_beats_the_class_axis():
    # Pylon engine pod (Engine_08/09): long pod off to -x, pivot on the +x
    # plate -> mount is the +x face (fits the hull's left socket unrotated),
    # not the tiny nozzle-end cap on the class axis.
    verts, tris = _two_boxes(([-5.0, -1.0, -4.0], [0.0, 1.0, 4.0]), ([0.0, -0.5, -2.0], [0.5, 0.5, 2.0]))
    m = sk.analyse_part(verts, tris, "engine", "-z")["mount"]
    assert m["axis"] == "+x" and m["source"] == "measured"
    assert m["position"] == pytest.approx([0.0, 0.0, 0.0])  # the pod's +x plate, on the pivot plane
    assert m["parent_role"] == "left"
    # The same pod with a centred pivot keeps the class axis.
    verts2 = verts - verts.mean(axis=0)
    assert sk.analyse_part(verts2, tris, "engine", "-z")["mount"]["axis"] == "+z"
    # A small foot on the pivot plane does not outrank a big flat face
    # (greeble wedge Misc_017): foot fit ~0.03 vs the block's z faces ~0.7.
    verts, tris = _two_boxes(([-1.0, 0.5, 0.2], [1.0, 2.0, 1.2]), ([-0.15, -0.1, 0.3], [0.15, 0.0, 0.5]))
    m = sk.analyse_part(verts, tris, "greeble", "any")["mount"]
    assert m["axis"] in ("+z", "-z") and m["fit"] > 0.5


def test_greeble_mounts_by_largest_flat_face():
    verts, tris = _box([-1.0, 1.0, -0.5], [1.0, 1.5, 0.5])  # base 2x1 is the biggest face
    m = sk.analyse_part(verts, tris, "greeble", "any")["mount"]
    assert m["axis"] == "-y"
    assert m["normal"] == [0.0, -1.0, 0.0]
    assert m["parent_role"] == "top"


def test_greeble_prefers_axis_true_face_over_sloped_panel():
    # A 2x1 base at -y plus a bigger top panel sloping 8 deg (inside the
    # 10 deg cone): the sloped panel is a body surface, the flat base mounts.
    v, t = box_mesh([-1.0, 1.0, -0.5], [1.0, 1.5, 0.5])
    verts = np.array(v, dtype=np.float64)
    # lift the +y face's far-z edge -> the top slopes about x (~8 deg over 1 m)
    verts[[6, 7], 1] += 0.14
    tris = np.array(t, dtype=np.int64)
    m = sk.analyse_part(verts, tris, "greeble", "any")["mount"]
    assert m["axis"] == "-y"


def test_no_flat_cap_falls_back_to_aabb_face():
    # A pyramid (square base at -y, apex up), floated off the pivot plane so
    # the base does not count as "pivot at the mating plane": nothing faces
    # -z within 10 deg, so a cockpit's mount falls back to the AABB -z face.
    verts = np.array([[-1, 1, -1], [1, 1, -1], [1, 1, 1], [-1, 1, 1], [0, 3, 0]], dtype=np.float64)
    tris = np.array([[0, 1, 2], [0, 2, 3], [0, 4, 1], [1, 4, 2], [2, 4, 3], [3, 4, 0]], dtype=np.int64)
    m = sk.analyse_part(verts, tris, "cockpit", "+z")["mount"]
    assert m["source"] == "aabb" and m["axis"] == "-z"
    assert m["position"] == pytest.approx([0.0, 2.0, -1.0])
    assert m["area"] is None and m["fit"] == 0.0
    assert m["parent_role"] == "front"
    body = sk.analyse_part(verts, tris, "body", "any")
    assert len(body["sockets"]) == 6
    assert {s["role"]: s["source"] for s in body["sockets"]}["bottom"] == "measured"
    assert {s["role"]: s["source"] for s in body["sockets"]}["front"] == "aabb"


def test_prop_contact_wall_is_minus_z_cap(tmp_path: Path):
    v, t = box_mesh([-0.5, 0.0, -0.05], [0.5, 1.0, 0.05])
    pack = tmp_path / "POLYGON_City"
    glb = pack / "models" / "Models" / "SM_Prop_Sign_Police_01.glb"
    glb.parent.mkdir(parents=True)
    write_mesh_glb(glb, v, t)
    asset = {
        "id": "SM_Prop_Sign_Police_01",
        "type": "prop/signage",
        "placeable": True,
        "placement": {"mount": "wall", "constraints": []},
        "files": {"glb": "POLYGON_City/models/Models/SM_Prop_Sign_Police_01.glb"},
        "part": {"class": None},
    }
    stats: dict = {}
    sk.apply_prop_contact(asset, tmp_path, {}, stats)
    contact = asset["placement"]["contact"]
    assert contact["axis"] == "-z"
    assert contact["normal"][2] < -0.5
    assert contact["position"][2] == pytest.approx(-0.05)
    assert "seat_on_contact" in asset["placement"]["constraints"]
    assert stats.get("contact_measured") == 1


def test_prop_contact_skips_buildings_and_ship_parts():
    stats: dict = {}
    bld = {"type": "building/module", "placeable": True, "placement": {"mount": "ground"}, "files": {"glb": "x"}}
    sk.apply_prop_contact(bld, None, {}, stats)
    assert "contact" not in (bld.get("placement") or {}) or bld["placement"].get("contact") is None
    ship = {
        "type": "vehicle/part",
        "placeable": True,
        "part": {"class": "engine"},
        "placement": {"mount": "socket"},
        "files": {"glb": "x"},
    }
    sk.apply_prop_contact(ship, None, {}, stats)
    assert ship["placement"].get("contact") is None


def test_apply_part_sockets_uses_cache_and_stats(tmp_path: Path, monkeypatch):
    v, t = box_mesh([-1.0, 0.0, -2.0], [1.0, 1.0, 2.0])
    rel = "Pack/models/SM_Veh_Part_Body_01.glb"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    write_mesh_glb(path, v, t)
    asset = {"id": "SM_Veh_Part_Body_01", "files": {"glb": rel}, "part": {"class": "body", "mates_axis": "any"}}
    cache: dict = {}
    stats: dict = {}
    sk.apply_part_sockets(asset, tmp_path, cache, stats)
    assert len(asset["part"]["sockets"]) == 6 and asset["part"]["mount"] is None
    assert stats == {"sockets_analysed": 1}
    assert f"{rel}#sockets" in cache

    calls = []
    monkeypatch.setattr(sk, "load_triangles", lambda *a, **k: calls.append(a) or None)
    asset2 = {"id": "SM_Veh_Part_Body_01", "files": {"glb": rel}, "part": {"class": "body", "mates_axis": "any"}}
    sk.apply_part_sockets(asset2, tmp_path, cache, stats)
    assert not calls, "second pass served from cache"
    assert len(asset2["part"]["sockets"]) == 6

    # no GLB -> stays null, counted
    asset3 = {"id": "SM_Veh_Part_Cockpit_01", "files": {"glb": None}, "part": {"class": "cockpit", "mates_axis": "+z"}}
    sk.apply_part_sockets(asset3, tmp_path, cache, stats)
    assert asset3["part"]["mount"] is None and asset3["part"]["sockets"] is None
    assert stats["sockets_missing_glb"] == 1
    # non-parts untouched
    prop = {"id": "SM_Prop_Crate", "files": {"glb": rel}, "part": {"class": None}}
    sk.apply_part_sockets(prop, tmp_path, cache, stats)
    assert "mount" not in prop["part"]


def test_validate_socket_rules():
    errors: list[str] = []
    good = {"axis": "+z", "position": [0, 0, 1], "normal": [0, 0, 1], "source": "measured", "role": "front"}
    validate_socket(good, "x", errors, need_role=True)
    assert errors == []
    validate_socket(dict(good, parent_role="nowhere"), "x", errors, need_role=False)
    assert any(".parent_role" in e for e in errors)
    errors.clear()
    bad = {"axis": "up", "position": [0, 0], "normal": [0, 0, 1], "source": "guess"}
    validate_socket(bad, "x", errors, need_role=True)
    assert any(".axis" in e for e in errors)
    assert any(".position" in e for e in errors)
    assert any(".source" in e for e in errors)
    assert any(".role" in e for e in errors)
