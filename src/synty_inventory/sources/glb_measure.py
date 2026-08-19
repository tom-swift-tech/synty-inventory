"""Offline world-space AABB measurement straight from a GLB's JSON chunk.

glTF requires ``min``/``max`` on every POSITION accessor, so the exact mesh
never needs to be decoded — no ``trimesh``/``pygltflib`` dependency, just the
glTF JSON chunk and numpy for the 4x4 transforms. The GLBs here use
``EXT_meshopt_compression`` (vertex/index buffers) and
``KHR_mesh_quantization`` (POSITION stored as normalized int8/int16), which
only affects how the accessor's own min/max need dequantizing before they're
transformed by the node's world matrix.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import numpy as np

from ..naming import should_skip
from ..schema import dimensions_from_bounds, make_bounds, pivot_from_aabb

GLB_MAGIC = 0x46546C67  # b'glTF'
CHUNK_JSON = 0x4E4F534A  # b'JSON'

# componentType -> normalized-int dequantization divisor (glTF spec table).
_NORM_DIVISOR = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}
_SIGNED_TYPES = {5120, 5122}


def _dequantize(values: list[float], component_type: int | None) -> list[float]:
    divisor = _NORM_DIVISOR.get(component_type or 0)
    if divisor is None:
        return [float(v) for v in values]
    out = []
    for v in values:
        f = float(v) / divisor
        if component_type in _SIGNED_TYPES and f < -1.0:
            f = -1.0
        out.append(f)
    return out


def read_glb_json(path: Path) -> dict | None:
    try:
        with open(path, "rb") as fh:
            header = fh.read(12)
            if len(header) < 12:
                return None
            magic, _version, _length = struct.unpack("<III", header)
            if magic != GLB_MAGIC:
                return None
            chunk_header = fh.read(8)
            if len(chunk_header) < 8:
                return None
            chunk_len, chunk_type = struct.unpack("<II", chunk_header)
            if chunk_type != CHUNK_JSON:
                return None
            body = fh.read(chunk_len)
    except OSError:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _quat_to_matrix3(q: list[float]) -> np.ndarray:
    x, y, z, w = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        # glTF stores 16 floats column-major: the first 4 are column 0, etc.
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4, order="F")
    t = node.get("translation") or [0.0, 0.0, 0.0]
    r = node.get("rotation") or [0.0, 0.0, 0.0, 1.0]
    s = node.get("scale") or [1.0, 1.0, 1.0]
    m = np.eye(4, dtype=np.float64)
    m[:3, :3] = _quat_to_matrix3(r) @ np.diag(s)
    m[:3, 3] = t
    return m


def _corners(min_: list[float], max_: list[float]) -> np.ndarray:
    xs, ys, zs = (min_[0], max_[0]), (min_[1], max_[1]), (min_[2], max_[2])
    return np.array([[x, y, z, 1.0] for x in xs for y in ys for z in zs], dtype=np.float64)


def measure_glb(path: Path) -> tuple[list[float], list[float]] | None:
    """World-space (min, max) over every mesh primitive's POSITION accessor
    in the default scene, or None if the GLB has no measurable geometry."""
    doc = read_glb_json(path)
    if not doc:
        return None
    accessors = doc.get("accessors") or []
    meshes = doc.get("meshes") or []
    nodes = doc.get("nodes") or []
    scenes = doc.get("scenes") or []
    scene_idx = doc.get("scene", 0)
    if not (0 <= scene_idx < len(scenes)):
        return None
    roots = scenes[scene_idx].get("nodes") or []

    global_min = np.array([np.inf, np.inf, np.inf])
    global_max = np.array([-np.inf, -np.inf, -np.inf])
    found = False

    def walk(idx: int, parent: np.ndarray) -> None:
        nonlocal found, global_min, global_max
        if not (0 <= idx < len(nodes)):
            return
        node = nodes[idx]
        world = parent @ _node_matrix(node)
        mesh_idx = node.get("mesh")
        if mesh_idx is not None and 0 <= mesh_idx < len(meshes):
            for prim in meshes[mesh_idx].get("primitives") or []:
                pos_idx = (prim.get("attributes") or {}).get("POSITION")
                if pos_idx is None or not (0 <= pos_idx < len(accessors)):
                    continue
                acc = accessors[pos_idx]
                amin, amax = acc.get("min"), acc.get("max")
                if amin is None or amax is None:
                    continue
                if acc.get("normalized"):
                    amin = _dequantize(amin, acc.get("componentType"))
                    amax = _dequantize(amax, acc.get("componentType"))
                corners = _corners(amin, amax) @ world.T
                xyz = corners[:, :3]
                global_min = np.minimum(global_min, xyz.min(axis=0))
                global_max = np.maximum(global_max, xyz.max(axis=0))
                found = True
        for child in node.get("children") or []:
            walk(child, world)

    for r in roots:
        walk(r, np.eye(4, dtype=np.float64))

    if not found:
        return None
    return global_min.tolist(), global_max.tolist()


# --- cache -----------------------------------------------------------------

CACHE_NAME = "_measure_cache.json"


def _cache_key(path: Path) -> str | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return f"{int(st.st_mtime)}:{st.st_size}"


def load_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.is_file():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache_path: Path, cache: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache_path)


def measure_cached(threejs_v2_dir: Path, glb_rel: str, cache: dict[str, Any]) -> tuple[list[float], list[float]] | None:
    """Measure ``<threejs_v2_dir>/<glb_rel>``, using/populating ``cache`` (keyed
    by relative path + mtime + size so edited/re-exported GLBs re-measure)."""
    abs_path = threejs_v2_dir / glb_rel
    key = _cache_key(abs_path)
    if key is None:
        return None
    entry = cache.get(glb_rel)
    if entry and entry.get("key") == key:
        return entry["min"], entry["max"]
    result = measure_glb(abs_path)
    if result is None:
        return None
    mn, mx = result
    cache[glb_rel] = {"key": key, "min": mn, "max": mx}
    return mn, mx


def apply_measured_bounds(
    asset: dict,
    threejs_v2_dir: Path | None,
    cache: dict[str, Any],
    stats: dict[str, int],
    *,
    disagree_tol: float = 2e-3,
) -> None:
    """Set ``asset['bounds']`` from a fresh GLB measurement when available.

    A GLB measurement always wins over a prior viewer-derived ``measured``
    bounds when both exist (it is the authoritative per-file pass run last);
    they are expected to agree within ``disagree_tol`` and a mismatch beyond
    that is only counted in ``stats``, never blocking.
    """
    glb_rel = (asset.get("files") or {}).get("glb")
    if should_skip(glb_rel or asset["id"], asset["id"]):
        stats["skipped"] = stats.get("skipped", 0) + 1
        return
    if not glb_rel or threejs_v2_dir is None:
        stats["missing_glb"] = stats.get("missing_glb", 0) + 1
        return
    result = measure_cached(threejs_v2_dir, glb_rel, cache)
    if result is None:
        stats["measure_failed"] = stats.get("measure_failed", 0) + 1
        return
    mn, mx = result
    old = asset.get("bounds")
    if old and old.get("min") and old.get("max"):
        diff = max(
            max(abs(mn[i] - old["min"][i]) for i in range(3)),
            max(abs(mx[i] - old["max"][i]) for i in range(3)),
        )
        if diff > disagree_tol:
            stats["disagree"] = stats.get("disagree", 0) + 1
    size = [mx[i] - mn[i] for i in range(3)]
    bounds = make_bounds(size, source="measured", min_=mn, max_=mx, pivot=pivot_from_aabb(mn, mx))
    asset["bounds"] = bounds
    asset["dimensions"] = dimensions_from_bounds(bounds)
    stats["measured"] = stats.get("measured", 0) + 1
