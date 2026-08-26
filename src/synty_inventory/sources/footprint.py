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

**Everything here is conservative by up to one cell.** Rasterisation rounds
the occupied region outward, so areas and radii read up to ~0.25 m proud of
the true surface (a 6.00 m tower measures 6.12 m). That bias is deliberate
and deliberately uncorrected: for a packer, over-reporting occupancy fails
safe -- two POIs will be spaced slightly generously rather than allowed to
intersect.

All coordinates are local metres in the same space as ``bounds`` (GLB local,
Y-up, origin = the prefab pivot). Everything here is a ``source: measured``
derivation; when the mesh cannot be decoded the caller leaves the field null
rather than substituting a box.
"""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from ..merge import is_human_field, may_overlay
from ..naming import SKIP_STEM_RE
from ..schema import FOOTPRINT_CLASSES
from .glb_geometry import load_triangles
from .glb_measure import _cache_key

FOOTPRINT_VERSION = 1  # bump to invalidate cached analyses when the algorithm changes
CACHE_NAME = "_footprint_cache.json"

# Decode counter, so a warm run can be asserted to touch no meshes (AC6).
_DECODES = {"count": 0}


def decode_count() -> int:
    return _DECODES["count"]


def reset_decode_count() -> None:
    _DECODES["count"] = 0


FOOTPRINT_CLASSES = FOOTPRINT_CLASSES  # re-exported; the enum lives in schema.py

DEFAULT_SNAP = 0.25
DEFAULT_GRADE_BAND_M = 0.5
DEFAULT_MIN_COMPONENT_M2 = 0.0625  # one 0.25 m cell

_MAX_CELLS_PER_AXIS = 4096  # coarsen the snap rather than allocate past this
_POINT_AREA_M2 = 0.0625
_THIN_MIN_M = 0.5
_THIN_MAX_M = 1.0
_COMPACT_FILL = 0.85
_EPS = 1e-9

# Radial detection. A cylinder spreads its wall area across dozens of
# directions at a constant radius; a box puts ~90 % of it into four. Measured
# on POLYGON_City: OfficeRound top4=0.12 r=0.996, OfficeOctagon 0.60/0.842,
# OfficeSquare 1.00/0.707 (exactly 1/sqrt(2), as a square must be). A round
# tower has no face to name, so its exact silhouette is not information --
# the radius is, and it is what a stacker compares within a kit family.
_RADIAL_R_RATIO = 0.85
_RADIAL_TOP4 = 0.35
_RADIAL_VERTS = 16  # regular ring emitted in place of the lattice staircase
_WALL_UP_COS = 0.25  # |normal.y| below this is a wall, not a roof or floor
_CLOSE_M = 0.5  # gap width the enclosure fill bridges (curtain-wall pane joints)

# Refinement. An axis-aligned box is already exact at the pack's snap: its
# outline lies on cell boundaries. A curved or 45-degree piece is not -- the
# quarter-round SM_Bld_Base_Floor_Round_01 measured 5.375 m2 against a true
# 4.76, because a 7-vertex outline was rasterised at 0.25 m and re-traced
# outward as a staircase. Refining every asset would cost ~64x the cells for
# nothing on the majority; the wall spectrum already tells us which is which,
# so only the pieces that need it pay.
_REFINE_TOP4 = 0.90  # below this share of wall area in 4 headings = not axis-aligned
_REFINE_FACTOR = 8

# Reasons returned alongside a null block. Mirror spec section 7.
REASON_OK = "ok"
REASON_UNDECODABLE = "undecodable"
REASON_NO_TRIANGLES = "no_renderable_triangles"
REASON_NON_FINITE = "non_finite_positions"
REASON_OPEN_RING = "open_ring"
REASON_DEGENERATE = "degenerate_silhouette"
REASON_MISSING_GLB = "glb_missing"


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
    """Occupancy grid.

    Two rasters with different jobs, because one cannot do both. A triangle's
    XZ projection is degenerate for a zero-thickness curtain-wall pane *and*
    for the side face of a solid box, so no per-triangle test separates them.

    - ``solid`` (strict) decides area and the outer boundary. Contact does
      not count, so abutting parts do not inflate each other.
    - ``barrier`` (inclusive) decides enclosure only. It picks up the
      zero-thickness panes that make a Synty curtain wall watertight --
      ``SM_Bld_OfficeSquare_01`` is a hollow glass shaft whose panes strict
      testing drops entirely, leaving a leaky mullion frame.

    Cells enclosed by the barrier are unioned onto the solid. The barrier's
    own one-cell bleed never reaches the result, so the outline stays exact.
    """
    xz = verts[:, [0, 2]]

    def raster(strict: bool) -> np.ndarray:
        grid = np.zeros(shape, dtype=bool)
        for tri in tris:
            hit = _tri_cells(xz[tri], origin, snap, shape, strict=strict)
            if hit is not None:
                grid[hit[0], hit[1]] = True
        return grid

    solid = raster(True)
    barrier = raster(False)
    if not barrier.any():
        return solid
    k = max(1, int(round(_CLOSE_M / snap)))
    interior = _close_and_fill(barrier, k) & ~barrier
    if not solid.any():
        return _resolve_diagonals(barrier | interior)
    return _resolve_diagonals(solid | interior)


def _shift_or(grid: np.ndarray) -> np.ndarray:
    """One step of 4-neighbour dilation."""
    out = grid.copy()
    out[1:, :] |= grid[:-1, :]
    out[:-1, :] |= grid[1:, :]
    out[:, 1:] |= grid[:, :-1]
    out[:, :-1] |= grid[:, 1:]
    return out


def _dilate(grid: np.ndarray, k: int) -> np.ndarray:
    for _ in range(k):
        grid = _shift_or(grid)
    return grid


def _resolve_diagonals(grid: np.ndarray) -> np.ndarray:
    """Break every corner-only contact so boundary tracing is unambiguous.

    Where a 2x2 block holds two occupied cells on a diagonal, the region
    pinches to a point and the lattice vertex there has two outgoing edges --
    the tracer cannot know which continues the ring, and picking wrong
    strands it (``SM_Bld_OfficeSquare_02`` traced to ``open_ring``). Filling
    one of the two empty cells removes the ambiguity entirely rather than
    asking the tracer to resolve it, and errs occupied, consistent with the
    rest of this module.
    """
    for _ in range(16):  # each pass can create new diagonals; converges fast
        a = grid[:-1, :-1]
        b = grid[1:, :-1]
        c = grid[:-1, 1:]
        d = grid[1:, 1:]
        fix_b = a & d & ~b & ~c
        fix_a = b & c & ~a & ~d
        if not fix_b.any() and not fix_a.any():
            break
        grid = grid.copy()
        grid[1:, :-1] |= fix_b
        grid[:-1, :-1] |= fix_a
    return grid


def _flood_border(free: np.ndarray) -> np.ndarray:
    """Cells of ``free`` reachable from the grid border by 4-connected steps."""
    nx, nz = free.shape
    seen = np.zeros_like(free)
    queue: deque[tuple[int, int]] = deque()
    for x in range(nx):
        for z in (0, nz - 1):
            if free[x, z] and not seen[x, z]:
                seen[x, z] = True
                queue.append((x, z))
    for z in range(nz):
        for x in (0, nx - 1):
            if free[x, z] and not seen[x, z]:
                seen[x, z] = True
                queue.append((x, z))
    while queue:
        x, z = queue.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ax, az = x + dx, z + dz
            if 0 <= ax < nx and 0 <= az < nz and free[ax, az] and not seen[ax, az]:
                seen[ax, az] = True
                queue.append((ax, az))
    return seen


def _fill_holes(grid: np.ndarray) -> np.ndarray:
    """Mark every empty cell not reachable from the border as occupied.

    Synty building shells are hollow -- they carry wall planes and no floor
    or roof slab, so ``SM_Bld_OfficeSquare_01`` rasterises to 179 of 3,660
    cells: a wall ribbon, not a ground plan. Enclosed area is what blocks a
    placement, so it is filled before anything is traced or measured.

    This is what spec A3 means by "interior holes are not represented".
    """
    return grid | ~_flood_border(~grid)


def _close_and_fill(grid: np.ndarray, k: int) -> np.ndarray:
    """Fill anything the outside cannot reach through a gap wider than 2k.

    A plain hole fill only works on a watertight ribbon. Synty curtain-wall
    shafts leak at every mullion joint -- ``SM_Bld_OfficeSquare_01`` (a
    hollow shaft, catalogued "open top, no doors") rasterises to 179 cells
    where a complete 15 m perimeter needs ~240, so flood fill escapes
    through the joints and nothing is enclosed.

    This *opens the free space* rather than closing the solid. Morphological
    closing was the obvious move and is wrong: dilating then eroding the
    solid fills concavities smaller than the element, which rounds off the
    notch of an L-plan -- the exact feature this module exists to capture.
    Flooding the dilated free space instead asks "could an agent of radius k
    reach this cell from outside?". A 5 m L-notch is open to the outside and
    survives; a 0.25 m pane joint is not passable and the interior fills.

    Padding is required: the raster is exactly the mesh AABB, so the shape
    touches all four borders and there would otherwise be no outside to
    flood from.
    """
    pad = k + 1
    g = np.pad(grid, pad, constant_values=False)
    outside = _flood_border(~_dilate(g, k))
    unreachable = ~(_dilate(outside, k) & ~g)

    # The opening cannot reach into a 90 degree concave corner either, so it
    # fillets every reflex corner to depth k -- which would round off the
    # notch of an L-plan, the exact feature this module exists to capture.
    # Discriminate by size: a real enclosure (a hollow shaft's interior) runs
    # to thousands of cells, a corner fillet is k(k+1)/2 of them. Only keep
    # additions big enough to be a room.
    added = unreachable & ~g
    if added.any():
        floor_cells = (2 * k + 1) ** 2
        for mask in _components(added):
            if int(mask.sum()) < floor_cells:
                unreachable &= ~mask
    return _resolve_diagonals(unreachable[pad:-pad, pad:-pad])


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


def _rdp(points: list[list[float]], eps: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker on an open polyline; max deviation <= eps."""
    if len(points) < 3:
        return points
    a = np.asarray(points[0], dtype=np.float64)
    b = np.asarray(points[-1], dtype=np.float64)
    seg = b - a
    seg_len = float(np.hypot(seg[0], seg[1]))
    pts = np.asarray(points[1:-1], dtype=np.float64)
    if seg_len < _EPS:
        dist = np.linalg.norm(pts - a, axis=1)
    else:
        # numpy 2.x removed the 2-D cross product; this is the same determinant.
        rel = pts - a
        dist = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / seg_len
    idx = int(np.argmax(dist))
    if float(dist[idx]) <= eps:
        return [points[0], points[-1]]
    split = idx + 1
    left = _rdp(points[: split + 1], eps)
    right = _rdp(points[split:], eps)
    return left[:-1] + right


def _simplify_staircase(ring: list[list[float]], eps: float) -> list[list[float]]:
    """Collapse lattice staircases into the straight edge they approximate.

    A facet that is not axis-aligned traces as a stair of half-cell steps --
    an octagon arrives with 174 vertices for its 8 real faces. Simplifying at
    one cell removes the steps while leaving any genuine corner, whose
    deviation from a chord is far larger than a cell.

    This does NOT restore a corner that was filleted away; RDP collapses a
    staircase to a chord, which bevels the corner rather than sharpening it.
    Corner fillets are prevented in ``_close_and_fill`` instead.

    On a refined raster the tolerance is two cells, not one: ``_resolve_
    diagonals`` fills every diagonal contact along a 45-degree edge, turning
    a clean staircase into a sawtooth whose teeth are a full cell deep. One
    cell cannot absorb that -- a right-triangle ceiling came back with 162
    vertices. Two cells is still 6 cm at the refined snap.
    """
    if len(ring) < 5 or eps <= 0:
        return ring
    pts = np.asarray(ring, dtype=np.float64)
    start = int(np.argmin(pts[:, 0] + pts[:, 1] * 1e-6))
    rolled = ring[start:] + ring[:start]
    far = int(np.argmax(np.linalg.norm(np.asarray(rolled) - np.asarray(rolled[0]), axis=1)))
    first = _rdp(rolled[: far + 1], eps)
    second = _rdp(rolled[far:] + [rolled[0]], eps)
    out = first[:-1] + second[:-1]
    return out if len(out) >= 4 else ring


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


# --- radial detection --------------------------------------------------------


def wall_spectrum(verts: np.ndarray, tris: np.ndarray) -> float | None:
    """Fraction of near-vertical face area in the four heaviest 5-degree
    heading bins: ~1.0 for a box, ~0.1 for a cylinder.

    This is the same normal-binning primitive pass 2 needs to find a glazed
    facade, built once here.
    """
    if not len(tris):
        return None
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    raw = np.cross(b - a, c - a)
    mag = np.linalg.norm(raw, axis=1)
    ok = mag > 1e-9
    if not ok.any():
        return None
    normals = raw[ok] / mag[ok, None]
    areas = mag[ok] / 2.0

    walls = np.abs(normals[:, 1]) < _WALL_UP_COS
    if not walls.any():
        return None
    heading = np.degrees(np.arctan2(normals[walls, 2], normals[walls, 0])) % 360.0
    hist, _ = np.histogram(heading, bins=72, range=(0.0, 360.0), weights=areas[walls])
    total = float(hist.sum())
    if total <= _EPS:
        return None
    return float(np.sort(hist / total)[-4:].sum())


def ring_radii(ring: list[list[float]]) -> tuple[float, list[float]] | None:
    """``(p5/p95 radius ratio, centre)`` of a traced ring.

    Percentiles, not min/max: a circle traced on a 0.25 m lattice is a
    staircase whose radii spread by roughly a cell either way, which drives a
    min/max ratio to 0.93 on a perfect cylinder. Measured on the ring rather
    than on raw vertices because a tiered plinth like
    ``SM_Bld_OfficeRound_Base_01`` carries interior geometry that drags a
    vertex-based ratio to 0.56 and splits a kit family in two.

    This is only a sanity guard. ``wall_spectrum`` is the discriminator: it
    reads the mesh, so the lattice cannot blur it.
    """
    if len(ring) < 4:
        return None
    pts = np.asarray(ring, dtype=np.float64)
    centre = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
    radii = np.linalg.norm(pts - centre, axis=1)
    hi = float(np.percentile(radii, 95))
    if hi <= _EPS:
        return None
    return float(np.percentile(radii, 5) / hi), [float(centre[0]), float(centre[1])]


def _is_radial(top4: float | None, ratio: float | None) -> bool:
    if top4 is None or ratio is None:
        return False
    return ratio >= _RADIAL_R_RATIO and top4 < _RADIAL_TOP4


def _regular_ring(centre: list[float], radius: float, lo: np.ndarray, hi: np.ndarray) -> list[list[float]]:
    """CCW regular ring of ``_RADIAL_VERTS`` vertices, clamped to the AABB.

    Every vertex sits at ``radius`` from the centre and a cylinder's AABB is
    ``2r`` on both axes, so the clamp is a no-op in the normal case and only
    bites on an eccentric mesh.
    """
    ring: list[list[float]] = []
    for k in range(_RADIAL_VERTS):
        theta = 2.0 * math.pi * k / _RADIAL_VERTS
        x = min(max(centre[0] + radius * math.cos(theta), lo[0]), hi[0])
        z = min(max(centre[1] + radius * math.sin(theta), lo[1]), hi[1])
        ring.append([round(float(x), 4), round(float(z), 4)])
    return ring


# --- classification ----------------------------------------------------------


def _right_angle_corners(ring: list[list[float]]) -> int:
    """Corners within ~15 degrees of square.

    ``l_plan`` and ``u_plan`` describe buildings with real corners. Matching
    on vertex count and reflex count alone let a staircased arc through --
    the quarter-round floor wedge classified ``u_plan`` on an 8-vertex ring
    whose "corners" were raster steps. A shape without square corners is
    ``irregular``, which is honest.
    """
    n = len(ring)
    square = 0
    for i in range(n):
        prev = ring[(i - 1) % n]
        cur = ring[i]
        nxt = ring[(i + 1) % n]
        ax, az = cur[0] - prev[0], cur[1] - prev[1]
        bx, bz = nxt[0] - cur[0], nxt[1] - cur[1]
        la = math.hypot(ax, az)
        lb = math.hypot(bx, bz)
        if la < _EPS or lb < _EPS:
            continue
        cos = abs((ax * bx + az * bz) / (la * lb))
        if cos < 0.26:  # ~75-105 degrees
            square += 1
    return square


def _classify(ring: list[list[float]], area_m2: float, fill_ratio: float, radial: bool = False) -> str:
    if area_m2 < _POINT_AREA_M2:
        return "point"
    xs = [p[0] for p in ring]
    zs = [p[1] for p in ring]
    span = sorted((max(xs) - min(xs), max(zs) - min(zs)))
    if span[0] < _THIN_MIN_M and span[1] >= _THIN_MAX_M:
        return "thin"
    if radial:
        return "radial"
    verts = len(ring)
    reflex = _reflex_count(ring)
    if verts == 4 and fill_ratio >= _COMPACT_FILL:
        return "compact"
    square = _right_angle_corners(ring)
    if verts == 6 and reflex == 1 and square == 6:
        return "l_plan"
    if verts == 8 and reflex == 2 and square == 8:
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
    _DECODES["count"] += 1
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
    # Refine only where the mesh is not axis-aligned; see _REFINE_TOP4.
    # A flat slab (ceiling, floor, road tile, decal) has no vertical faces at
    # all, so the spectrum is None -- and its outline is the whole asset, so
    # it refines too. SM_Bld_Base_Ceiling_45_01 is a 45-degree triangle that
    # read 10 % over at the pack snap for exactly this reason.
    top4 = wall_spectrum(verts, tris)
    refined = top4 is None or top4 < _REFINE_TOP4
    if refined:
        effective_snap = float(snap) / _REFINE_FACTOR
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
    # One cell of the raster actually in use, never a constant: at the pack
    # snap 0.0625 m2 IS one cell, but at the refined snap it is 64 of them,
    # and small props (SM_Env_Flower_01 is 0.234 x 0.218 m) fall under their
    # own minimum. The coarse raster was inflating them past it.
    min_component = max(min_component_m2 if effective_snap >= snap else 0.0, cell_area)
    masks = [m for m in _components(grid) if int(m.sum()) * cell_area >= min_component - _EPS]
    if not masks:
        return None, REASON_DEGENERATE

    total_area = 0.0
    outer: list[list[float]] | None = None
    outer_area = 0.0
    for i, mask in enumerate(masks):
        rings = _trace_rings(mask)
        if rings is None:
            return None, REASON_OPEN_RING
        best: list[list[float]] | None = None
        best_area = 0.0
        for lattice in rings:
            ring = _simplify_staircase(
                _orient_ccw(_simplify(_to_metres(lattice, lo, effective_snap, lo, hi))),
                effective_snap * (2.0 if refined else 1.0),
            )
            ring = _orient_ccw(_simplify(ring))
            area = abs(_shoelace(ring))
            if area > best_area:
                best_area, best = area, ring
        if best is None:
            return None, REASON_OPEN_RING
        total_area += best_area
        if i == 0:
            outer, outer_area = best, best_area
    if outer is None or total_area <= _EPS:
        return None, REASON_DEGENERATE

    # A round tower has no face to name and its lattice staircase is noise,
    # not shape: 200-odd vertices that no packer or stacker reads. Replace it
    # with a regular ring and record the radius, which is the number that
    # actually compares across a kit family.
    # Already computed above to pick the raster resolution.
    measured = ring_radii(outer)
    radial = _is_radial(top4, measured[0] if measured else None)
    radius_m: float | None = None
    if radial and measured is not None:
        # Area-equivalent radius, not the circumradius: the outermost
        # staircase corner sits a diagonal half-cell proud of the true
        # surface and overstates a 6.00 m tower as 6.31 m.
        radius = math.sqrt(outer_area / math.pi)
        centre = measured[1]
        radius_m = round(radius, 4)
        ring = _regular_ring(centre, radius, lo, hi)
        ring_area = abs(_shoelace(ring))
        total_area = total_area - outer_area + ring_area
        outer = ring
        if total_area <= _EPS:
            return None, REASON_DEGENERATE

    grade_hi = float(lo3[1]) + grade_band_m
    grade_sel = verts[:, 1] <= grade_hi + _EPS
    grade_tris = tris[grade_sel[tris].any(axis=1)]
    grade_area = 0.0
    if len(grade_tris):
        grade_grid = _rasterise(verts, grade_tris, lo, effective_snap, shape)
        for mask in _components(grade_grid):
            if int(mask.sum()) * cell_area < min_component - _EPS:
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
        "class": _classify(outer, total_area, fill_ratio, radial),
        "radius_m": radius_m,
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
    # 1.0 is legitimate: a hanging sign or a pole-mounted fixture has nothing
    # at all within the grade band.
    if not 0.0 <= block.get("overhang_ratio", 0.0) <= 1.0:
        return "invariant_4"
    return None


# --- enrichment --------------------------------------------------------------


def footprint_cache_path(catalogs_dir: Path) -> Path:
    """``<catalogs>/_footprint_cache.json`` — sibling of the measure cache."""
    return catalogs_dir / CACHE_NAME


def analyze_cached(
    threejs_v2_dir: Path,
    glb_rel: str,
    cache: dict[str, Any],
    node_name: str | None = None,
    *,
    snap: float = DEFAULT_SNAP,
    tile_m: float | None = None,
    force: bool = False,
) -> tuple[dict | None, str, bool]:
    """``(block, reason, was_cached)``.

    Keyed like ``glb_measure.measure_cached`` (relative path + node + mtime +
    size) with ``FOOTPRINT_VERSION`` folded in, so a re-exported GLB or an
    algorithm change both re-analyse. Failures are cached too: an undecodable
    mesh stays undecodable, and re-decoding it on every scan would cost the
    most on exactly the assets that can never succeed.
    """
    abs_path = threejs_v2_dir / glb_rel
    key = _cache_key(abs_path)
    if key is None:
        return None, REASON_MISSING_GLB, False
    cache_id = f"{glb_rel}#{node_name}" if node_name else glb_rel
    entry = cache.get(cache_id)
    if (
        not force
        and entry
        and entry.get("key") == key
        and entry.get("version") == FOOTPRINT_VERSION
    ):
        return entry.get("footprint"), entry.get("reason", REASON_OK), True
    block, reason = analyze_footprint_detail(abs_path, node_name, snap=snap, tile_m=tile_m)
    cache[cache_id] = {
        "key": key,
        "version": FOOTPRINT_VERSION,
        "footprint": block,
        "reason": reason,
    }
    return block, reason, False


def apply_footprint(
    asset: dict,
    threejs_v2_dir: Path | None,
    cache: dict[str, Any],
    stats: dict[str, int],
    *,
    snap: float = DEFAULT_SNAP,
    tile_m: float | None = None,
    force: bool = False,
) -> str:
    """Set ``asset['footprint']`` from the GLB; leave it null otherwise.

    Returns one of ``measured | cached | skipped | missing_glb |
    undecodable | degenerate``. Runs after ``apply_measured_bounds`` because
    ``fill_ratio`` is relative to the measured box.

    Non-placeable records (animation clips, HUD sprites, skeletons) have no
    ground plan and are skipped rather than reported as failures.
    """

    def done(kind: str) -> str:
        stats[f"footprint_{kind}"] = stats.get(f"footprint_{kind}", 0) + 1
        return kind

    if is_human_field(asset, "footprint") or not may_overlay(asset, "footprint", "measured"):
        return done("skipped")
    if not asset.get("placeable"):
        return done("skipped")

    files = asset.get("files") or {}
    glb_rel = files.get("glb")
    if not glb_rel or threejs_v2_dir is None:
        return done("missing_glb")

    block, reason, was_cached = analyze_cached(
        threejs_v2_dir,
        glb_rel,
        cache,
        files.get("glb_node"),
        snap=snap,
        tile_m=tile_m,
        force=force,
    )
    if block is None:
        asset["footprint"] = None
        return done("degenerate" if reason.startswith(("degenerate", "invariant", "open_ring")) else reason)

    asset["footprint"] = block
    asset.setdefault("provenance", {})["footprint"] = "measured"
    return done("cached" if was_cached else "measured")
