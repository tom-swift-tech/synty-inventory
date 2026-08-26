"""Ground-plan footprint polygons from a threejs-v2 GLB.

``bounds`` (``glb_measure``) says how big an asset's box is; this module says
what shape its ground plan actually is. An L-plan office, a landing pad with
an overhanging lip and a solid cube all share a box — they do not share a
footprint, and a POI packer that only sees the box degrades every layout to
conservative AABB spacing.

The derivation is deterministic mesh math, no VLM and no render:

1. decode the exact triangles (``glb_geometry.load_triangles``), skipping
   collision subtrees via ``naming.SKIP_STEM_RE``,
2. conservatively rasterise the XZ projection at the pack's ``grid.snap``
   (0.25 m) — cell-rectangle vs triangle SAT, not centre sampling, so a
   0.1 m wall still occupies its cells,
3. label 4-connected components and drop the ones below one cell of area,
4. trace each component's outer boundary on the cell lattice into a CCW
   orthogonal ring, collapse collinear runs,
5. clamp every ring vertex to the mesh AABB and take areas by shoelace.

**Why the clamp matters.** Conservative rasterisation rounds the occupied
region *outward* to whole cells, so a 5.536 m depth becomes 23 cells = 5.75 m
and the raw cell area would exceed the AABB — violating INV-3 on almost every
asset whose extent is not a multiple of the snap. Ring vertices are therefore
clamped to the measured AABB before any area is taken, and areas come from
the clamped polygons rather than a cell count. Only the final row/column can
ever exceed the AABB, so the clamp is exact rather than an approximation.

Rings are outer-only in v1: interior holes (a courtyard, a floor hatch) are
not represented. Holes matter for walkability, not for packing.

All coordinates are local metres in the same space as ``bounds`` (GLB local,
Y-up, origin = the prefab pivot). Everything here is a ``source: measured``
derivation; when the mesh cannot be decoded the caller leaves the field null
rather than substituting a box.
"""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path

import numpy as np

from ..naming import SKIP_STEM_RE
from .glb_geometry import load_triangles

FOOTPRINT_VERSION = 1  # bump to invalidate cached analyses when the algorithm changes

FOOTPRINT_CLASSES = ("point", "thin", "compact", "l_plan", "u_plan", "irregular")

DEFAULT_SNAP = 0.25
DEFAULT_GRADE_BAND_M = 0.5
DEFAULT_MIN_COMPONENT_M2 = 0.0625  # one 0.25 m cell

_MAX_CELLS_PER_AXIS = 4096  # coarsen the snap rather than allocate past this
_POINT_AREA_M2 = 0.0625
_THIN_MIN_M = 0.5
_THIN_MAX_M = 1.0
_COMPACT_FILL = 0.85
_EPS = 1e-9

# Reasons returned alongside a null block. Mirror spec section 7.
REASON_OK = "ok"
REASON_UNDECODABLE = "undecodable"
REASON_NO_TRIANGLES = "no_renderable_triangles"
REASON_NON_FINITE = "non_finite_positions"
REASON_OPEN_RING = "open_ring"
REASON_DEGENERATE = "degenerate_silhouette"


def is_collision_node(name: str) -> bool:
    """True for a GLB node the pack scanner would refuse to catalog.

    Reuses ``naming.SKIP_STEM_RE`` — the collision vocabulary lives in one
    place, so a token added for the scanner is honoured here for free.
    """
    if not name:
        return False
    lowered = name.replace("\\", "/").lower()
    if "/collision" in lowered or lowered.startswith("collision"):
        return True
    return bool(SKIP_STEM_RE.search(name))


# --- rasterisation -----------------------------------------------------------


def _tri_cells(
    tri_xz: np.ndarray,
    origin: np.ndarray,
    snap: float,
    shape: tuple[int, int],
    strict: bool = True,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Indices of every cell whose square intersects one triangle (2D SAT).

    ``strict`` requires genuine overlap rather than mere contact. It must be
    on for real geometry: a box face lying exactly on a cell boundary would
    otherwise claim the cell on the far side, and every pair of abutting
    parts in a multi-part asset would inflate its neighbour by one cell.
    A closed mesh's top and bottom faces cover the true footprint, so
    dropping the edge-on side faces costs nothing.

    ``strict=False`` is the fallback for genuinely planar assets (a decal or
    facade card with zero thickness in XZ), whose projection is a segment
    and which would otherwise rasterise to nothing.
    """
    nx, nz = shape
    lo = np.floor((tri_xz.min(axis=0) - origin) / snap).astype(np.int64)
    hi = np.floor((tri_xz.max(axis=0) - origin) / snap).astype(np.int64)
    lo = np.maximum(lo, 0)
    hi = np.minimum(hi, [nx - 1, nz - 1])
    if hi[0] < lo[0] or hi[1] < lo[1]:
        return None

    ix = np.arange(lo[0], hi[0] + 1, dtype=np.int64)
    iz = np.arange(lo[1], hi[1] + 1, dtype=np.int64)
    gx, gz = np.meshgrid(ix, iz, indexing="ij")
    gx = gx.reshape(-1)
    gz = gz.reshape(-1)

    half = snap / 2.0
    cx = origin[0] + (gx + 0.5) * snap
    cz = origin[1] + (gz + 0.5) * snap
    centres = np.stack([cx, cz], axis=1)

    # Two box axes plus the three edge normals. The box axes cannot be
    # skipped even though candidates come from the triangle's bbox: a cell
    # at the bbox edge may only touch it.
    axes = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    for a, b in ((0, 1), (1, 2), (2, 0)):
        edge = tri_xz[b] - tri_xz[a]
        normal = np.array([-edge[1], edge[0]], dtype=np.float64)
        length = math.hypot(normal[0], normal[1])
        if length < _EPS:
            continue  # degenerate edge: not a separating axis
        axes.append(normal / length)

    slack = -_EPS if strict else _EPS
    keep = np.ones(len(centres), dtype=bool)
    for normal in axes:
        tri_proj = tri_xz @ normal
        t_min, t_max = tri_proj.min(), tri_proj.max()
        radius = half * (abs(normal[0]) + abs(normal[1]))
        cell_proj = centres @ normal
        keep &= (cell_proj + radius >= t_min - slack) & (cell_proj - radius <= t_max + slack)
        if not keep.any():
            return None
    if not keep.any():
        return None
    return gx[keep], gz[keep]


def _rasterise(
    verts: np.ndarray,
    tris: np.ndarray,
    origin: np.ndarray,
    snap: float,
    shape: tuple[int, int],
) -> np.ndarray:
    """Occupancy grid, strict first; inclusive only if strict finds nothing
    (a planar asset whose XZ projection is a segment)."""
    for strict in (True, False):
        grid = np.zeros(shape, dtype=bool)
        xz = verts[:, [0, 2]]
        for tri in tris:
            hit = _tri_cells(xz[tri], origin, snap, shape, strict=strict)
            if hit is not None:
                grid[hit[0], hit[1]] = True
        if grid.any():
            return grid
    return grid


# --- components --------------------------------------------------------------


def _components(grid: np.ndarray) -> list[np.ndarray]:
    """4-connected components, largest first, each as a boolean mask."""
    nx, nz = grid.shape
    seen = np.zeros_like(grid)
    out: list[np.ndarray] = []
    for sx in range(nx):
        for sz in range(nz):
            if not grid[sx, sz] or seen[sx, sz]:
                continue
            mask = np.zeros_like(grid)
            queue = deque([(sx, sz)])
            seen[sx, sz] = True
            while queue:
                x, z = queue.popleft()
                mask[x, z] = True
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ax, az = x + dx, z + dz
                    if 0 <= ax < nx and 0 <= az < nz and grid[ax, az] and not seen[ax, az]:
                        seen[ax, az] = True
                        queue.append((ax, az))
            out.append(mask)
    out.sort(key=lambda m: int(m.sum()), reverse=True)
    return out


# --- boundary tracing --------------------------------------------------------


def _boundary_edges(mask: np.ndarray) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Lattice edges of the region, oriented so the interior is on the left.

    Points are integer lattice coordinates (cell corners). Walking with the
    interior on the left yields a shoelace-positive (CCW) ring in (x, z).
    """
    nx, nz = mask.shape
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def add(p0: tuple[int, int], p1: tuple[int, int]) -> None:
        edges.setdefault(p0, []).append(p1)

    for x in range(nx):
        for z in range(nz):
            if not mask[x, z]:
                continue
            if z == 0 or not mask[x, z - 1]:
                add((x, z), (x + 1, z))          # -z edge, walk +x
            if z == nz - 1 or not mask[x, z + 1]:
                add((x + 1, z + 1), (x, z + 1))  # +z edge, walk -x
            if x == 0 or not mask[x - 1, z]:
                add((x, z + 1), (x, z))          # -x edge, walk -z
            if x == nx - 1 or not mask[x + 1, z]:
                add((x + 1, z), (x + 1, z + 1))  # +x edge, walk +z
    return edges


def _trace_rings(mask: np.ndarray) -> list[list[tuple[int, int]]] | None:
    """Every closed ring of the region in lattice coordinates, or None when
    a ring fails to close (spec section 7 ``open_ring``)."""
    edges = _boundary_edges(mask)
    rings: list[list[tuple[int, int]]] = []
    guard = sum(len(v) for v in edges.values()) + 1

    while edges:
        start = next(iter(edges))
        ring = [start]
        cur = start
        steps = 0
        while True:
            steps += 1
            if steps > guard:
                return None
            outgoing = edges.get(cur)
            if not outgoing:
                return None
            nxt = outgoing.pop()
            if not outgoing:
                del edges[cur]
            if nxt == start:
                break
            ring.append(nxt)
            cur = nxt
        if len(ring) >= 4:
            rings.append(ring)
    return rings or None


def _to_metres(ring: list[tuple[int, int]], origin: np.ndarray, snap: float, lo: np.ndarray, hi: np.ndarray) -> list[list[float]]:
    """Lattice ring to clamped metric ring. See the module docstring on why
    the clamp is exact rather than an approximation."""
    out: list[list[float]] = []
    for x, z in ring:
        mx = min(max(origin[0] + x * snap, lo[0]), hi[0])
        mz = min(max(origin[1] + z * snap, lo[1]), hi[1])
        out.append([round(float(mx), 4), round(float(mz), 4)])
    return out


def _dedupe(ring: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for pt in ring:
        if not out or (abs(pt[0] - out[-1][0]) > _EPS or abs(pt[1] - out[-1][1]) > _EPS):
            out.append(pt)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) <= _EPS and abs(out[0][1] - out[-1][1]) <= _EPS:
        out.pop()
    return out


def _simplify(ring: list[list[float]]) -> list[list[float]]:
    """Collapse collinear runs (INV-2)."""
    ring = _dedupe(ring)
    n = len(ring)
    if n < 4:
        return ring
    keep: list[list[float]] = []
    for i in range(n):
        prev = ring[(i - 1) % n]
        cur = ring[i]
        nxt = ring[(i + 1) % n]
        cross = (cur[0] - prev[0]) * (nxt[1] - cur[1]) - (cur[1] - prev[1]) * (nxt[0] - cur[0])
        if abs(cross) > 1e-7:
            keep.append(cur)
    return keep if len(keep) >= 4 else ring


def _shoelace(ring: list[list[float]]) -> float:
    total = 0.0
    n = len(ring)
    for i in range(n):
        x0, z0 = ring[i]
        x1, z1 = ring[(i + 1) % n]
        total += x0 * z1 - x1 * z0
    return total / 2.0


def _orient_ccw(ring: list[list[float]]) -> list[list[float]]:
    return ring if _shoelace(ring) >= 0 else list(reversed(ring))


def _reflex_count(ring: list[list[float]]) -> int:
    """Corners turning clockwise in a CCW ring — the notches."""
    n = len(ring)
    count = 0
    for i in range(n):
        prev = ring[(i - 1) % n]
        cur = ring[i]
        nxt = ring[(i + 1) % n]
        cross = (cur[0] - prev[0]) * (nxt[1] - cur[1]) - (cur[1] - prev[1]) * (nxt[0] - cur[0])
        if cross < -1e-7:
            count += 1
    return count


# --- classification ----------------------------------------------------------


def _classify(ring: list[list[float]], area_m2: float, fill_ratio: float) -> str:
    if area_m2 < _POINT_AREA_M2:
        return "point"
    xs = [p[0] for p in ring]
    zs = [p[1] for p in ring]
    span = sorted((max(xs) - min(xs), max(zs) - min(zs)))
    if span[0] < _THIN_MIN_M and span[1] >= _THIN_MAX_M:
        return "thin"
    verts = len(ring)
    reflex = _reflex_count(ring)
    if verts == 4 and fill_ratio >= _COMPACT_FILL:
        return "compact"
    if verts == 6 and reflex == 1:
        return "l_plan"
    if verts == 8 and reflex == 2:
        return "u_plan"
    return "irregular"


def _tile_cells(ring: list[list[float]], tile_m: float | None, snap: float) -> list[int] | None:
    if not tile_m or tile_m <= 0 or len(ring) != 4:
        return None
    xs = [p[0] for p in ring]
    zs = [p[1] for p in ring]
    out: list[int] = []
    for span in (max(xs) - min(xs), max(zs) - min(zs)):
        cells = span / tile_m
        nearest = round(cells)
        if nearest < 1 or abs(cells - nearest) * tile_m > snap:
            return None
        out.append(int(nearest))
    return out


# --- public ------------------------------------------------------------------


def analyze_footprint_detail(
    path: Path,
    node_name: str | None = None,
    *,
    snap: float = DEFAULT_SNAP,
    grade_band_m: float = DEFAULT_GRADE_BAND_M,
    min_component_m2: float = DEFAULT_MIN_COMPONENT_M2,
    tile_m: float | None = None,
) -> tuple[dict | None, str]:
    """``(footprint block, reason)``. The block is None on any failure and the
    reason names it — callers report the reason and leave the field null."""
    got = load_triangles(path, node_name, exclude=is_collision_node)
    if got is None:
        return None, REASON_UNDECODABLE
    verts, tris = got
    if not len(tris) or not len(verts):
        return None, REASON_NO_TRIANGLES
    if not np.isfinite(verts).all():
        return None, REASON_NON_FINITE

    lo3 = verts.min(axis=0)
    hi3 = verts.max(axis=0)
    lo = np.array([lo3[0], lo3[2]], dtype=np.float64)
    hi = np.array([hi3[0], hi3[2]], dtype=np.float64)
    extent = hi - lo
    if extent[0] <= _EPS and extent[1] <= _EPS:
        return None, REASON_DEGENERATE

    effective_snap = float(snap)
    while max(math.ceil(extent[0] / effective_snap), math.ceil(extent[1] / effective_snap)) > _MAX_CELLS_PER_AXIS:
        effective_snap *= 2.0

    shape = (
        max(int(math.ceil(extent[0] / effective_snap)), 1),
        max(int(math.ceil(extent[1] / effective_snap)), 1),
    )

    grid = _rasterise(verts, tris, lo, effective_snap, shape)
    if not grid.any():
        return None, REASON_DEGENERATE

    cell_area = effective_snap * effective_snap
    masks = [m for m in _components(grid) if int(m.sum()) * cell_area >= min_component_m2 - _EPS]
    if not masks:
        return None, REASON_DEGENERATE

    total_area = 0.0
    outer: list[list[float]] | None = None
    for i, mask in enumerate(masks):
        rings = _trace_rings(mask)
        if rings is None:
            return None, REASON_OPEN_RING
        best: list[list[float]] | None = None
        best_area = 0.0
        for lattice in rings:
            ring = _orient_ccw(_simplify(_to_metres(lattice, lo, effective_snap, lo, hi)))
            area = abs(_shoelace(ring))
            if area > best_area:
                best_area, best = area, ring
        if best is None:
            return None, REASON_OPEN_RING
        total_area += best_area
        if i == 0:
            outer = best
    if outer is None or total_area <= _EPS:
        return None, REASON_DEGENERATE

    grade_hi = float(lo3[1]) + grade_band_m
    grade_sel = verts[:, 1] <= grade_hi + _EPS
    grade_tris = tris[grade_sel[tris].any(axis=1)]
    grade_area = 0.0
    if len(grade_tris):
        grade_grid = _rasterise(verts, grade_tris, lo, effective_snap, shape)
        for mask in _components(grade_grid):
            if int(mask.sum()) * cell_area < min_component_m2 - _EPS:
                continue
            rings = _trace_rings(mask)
            if rings is None:
                continue
            grade_area += max(abs(_shoelace(_orient_ccw(_simplify(_to_metres(r, lo, effective_snap, lo, hi))))) for r in rings)
    grade_area = min(grade_area, total_area)

    box_area = float(extent[0] * extent[1])
    fill_ratio = min(total_area / box_area, 1.0) if box_area > _EPS else 1.0

    block = {
        "polygon_m": outer,
        "components": len(masks),
        "area_m2": round(total_area, 4),
        "grade_area_m2": round(grade_area, 4),
        "overhang_ratio": round(max(0.0, 1.0 - (grade_area / total_area)), 4),
        "fill_ratio": round(fill_ratio, 4),
        "class": _classify(outer, total_area, fill_ratio),
        "tile_cells": _tile_cells(outer, tile_m, effective_snap),
        "snap_m": effective_snap,
        "grade_band_m": [round(float(lo3[1]), 5), round(grade_hi, 5)],
        "source": "measured",
        "version": FOOTPRINT_VERSION,
    }

    bad = check_invariants(block, [float(lo3[0]), float(lo3[2])], [float(hi3[0]), float(hi3[2])])
    if bad:
        return None, bad
    return block, REASON_OK


def analyze_footprint(
    path: Path,
    node_name: str | None = None,
    *,
    snap: float = DEFAULT_SNAP,
    grade_band_m: float = DEFAULT_GRADE_BAND_M,
    min_component_m2: float = DEFAULT_MIN_COMPONENT_M2,
    tile_m: float | None = None,
) -> dict | None:
    """Ground-plan polygon for a threejs-v2 GLB, local metres, Y-up.

    ``node_name`` selects one node inside a bundle GLB (catalog ``glb_node``);
    None analyses the whole scene. Returns the footprint block, or None when
    the mesh cannot be decoded (caller leaves the field null).
    """
    block, _ = analyze_footprint_detail(
        path,
        node_name,
        snap=snap,
        grade_band_m=grade_band_m,
        min_component_m2=min_component_m2,
        tile_m=tile_m,
    )
    return block


def check_invariants(block: dict, box_min_xz: list[float], box_max_xz: list[float]) -> str | None:
    """INV-1..4 as a self-check. Returns ``invariant_<n>`` on the first
    violation, None when clean. A bad polygon is worse than no polygon, so
    the analyser rejects its own output rather than writing it.
    """
    ring = block.get("polygon_m") or []
    if len(ring) < 4:
        return "invariant_2"
    tol = 1e-3
    for x, z in ring:
        if x < box_min_xz[0] - tol or x > box_max_xz[0] + tol:
            return "invariant_1"
        if z < box_min_xz[1] - tol or z > box_max_xz[1] + tol:
            return "invariant_1"
    for i in range(len(ring)):
        if abs(ring[i][0] - ring[i - 1][0]) <= _EPS and abs(ring[i][1] - ring[i - 1][1]) <= _EPS:
            return "invariant_2"
    if _shoelace(ring) < 0:
        return "invariant_2"
    box_area = (box_max_xz[0] - box_min_xz[0]) * (box_max_xz[1] - box_min_xz[1])
    area = block.get("area_m2", 0.0)
    if area <= 0 or area > box_area + tol:
        return "invariant_3"
    if not 0.0 < block.get("fill_ratio", 0.0) <= 1.0:
        return "invariant_3"
    if block.get("grade_area_m2", 0.0) > area + tol:
        return "invariant_4"
    if not 0.0 <= block.get("overhang_ratio", 0.0) < 1.0:
        return "invariant_4"
    return None
