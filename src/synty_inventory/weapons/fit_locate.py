"""Locator and strip of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.2 "Presets", 3.11, 4.1 ``locator``, 4.3; plan slice S3).

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring).

``locate_by_translation`` finds ONE part inside a preset host's vertices by translation only. ``strip`` then removes the located parts from the
host mesh, so no host detector reads a fused scope's top as the rail. Both are pure functions over arrays: the caller hands in the host's
vertices (any frame: only translations are compared) and reads the pack; nothing here touches a file.

Readings of the spec chosen here (each is also noted where it is used):

* **Grid and tolerance.** A vertex is keyed by its integer cell ``floor(x / grid_m)`` per axis, plain floor with no epsilon. A candidate
  translation is a whole number of cells (host cell minus the part's smallest vertex cell); a part vertex "lands" when its shifted cell, or any
  of the 26 cells around it, holds a host vertex. The 27 cells are what absorb (a) a translation that is not a whole number of cells (a
  vertex moves by one cell where its fraction wraps), and (b) a vertex that float rounding puts on the other side of a cell edge. A vertex moved
  by 1 mm is 2 cells away on that axis (or 3 across an edge), never 1, so it does not land; one moved by under 0.5 mm does.
* **Prefilter.** The ``sample_n`` sampled vertices (evenly spaced over the sorted part, all of them for a smaller part) may miss at most
  ``floor((1 - hit_min) * n)`` times, ``n`` being the part's vertex count: the miss budget of the full test. At ``hit_min`` 1.0 it is "every
  sampled vertex lands"; below 1.0 it never rejects a candidate the full test would accept, so ``hit_min`` is decided in one place.
* **Representative of a merged cluster.** Accepted candidates sort by (hit descending, vertices landing in their own cell descending,
  translation); one is kept and every other within ``merge_m`` (Euclidean, inclusive) of a kept one is dropped. So the best-fitting
  translation represents its cluster, with the lexicographically smallest on a tie. The result is sorted by translation.
* **``Placement.part``** is ``""``: the signature carries no part id, so the caller labels each placement
  (``dataclasses.replace(p, part=name)``, the dataclass is frozen). ``Placement.t`` is ``host vertex - part's smallest vertex`` of the
  winning candidate, rounded to 1e-4 m (4.3); ``hit`` is landed/total, rounded to 1e-4.
"""

from __future__ import annotations

import numpy as np

from .fit_types import Placement

# spec 4.3: stored measures are rounded to 1e-4 m. ``strip`` has no rules argument, so this storage unit (not a rule value) is also its
# matching cell: ``Placement.t`` is only known to this precision, and a host vertex is on a located part when a translated part vertex is in
# its cell or a neighbouring one (a match within 0.2 mm, finer than the locator grid).
_ROUND_DECIMALS = 4
_STRIP_CELL_M = 10.0**-_ROUND_DECIMALS

# the 27 cells around (and including) a cell, and the cell itself
_NEIGHBOURS = tuple((dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1))
_EXACT = ((0, 0, 0),)

# a cell triple packs into one int64 (21 bits per axis, biased so negatives sort): a neighbouring cell is the key plus a constant. No set
# or dict is iterated; the keys are looked up with searchsorted over a sorted array.
_BITS = 21
_BIAS = 1 << (_BITS - 1)
_LOCATE_CELL_LIMIT = 1 << (_BITS - 3)  # |cell| bound for the locator: a shift plus a cell stays inside the packed range
_STRIP_CELL_LIMIT = _BIAS - 2


def _cells(points: np.ndarray, cell_m: float, limit: int) -> np.ndarray:
    cells = np.floor(points / cell_m).astype(np.int64)
    if cells.size and int(np.abs(cells).max()) > limit:
        raise ValueError(f"vertex outside the +-{limit * cell_m:.0f} m the {cell_m} m grid can key")
    return cells


def _pack(cells: np.ndarray) -> np.ndarray:
    return ((cells[..., 0] + _BIAS) << (2 * _BITS)) + ((cells[..., 1] + _BIAS) << _BITS) + (cells[..., 2] + _BIAS)


def _deltas(offsets) -> list[int]:
    return [(dx << (2 * _BITS)) + (dy << _BITS) + dz for dx, dy, dz in offsets]


def _present(sorted_keys: np.ndarray, keys: np.ndarray) -> np.ndarray:
    """Which of ``keys`` are in ``sorted_keys`` (ascending, unique)."""
    if len(sorted_keys) == 0 or len(keys) == 0:
        return np.zeros(len(keys), dtype=bool)
    pos = np.minimum(np.searchsorted(sorted_keys, keys), len(sorted_keys) - 1)
    return sorted_keys[pos] == keys


def _lands(sorted_keys: np.ndarray, keys: np.ndarray, deltas: list[int]) -> np.ndarray:
    """Which of ``keys`` have a key of ``sorted_keys`` at one of the offsets ``deltas``."""
    found = np.zeros(len(keys), dtype=bool)
    for d in deltas:
        pending = np.flatnonzero(~found)
        if len(pending) == 0:
            break
        found[pending] = _present(sorted_keys, keys[pending] + d)
    return found


def _lex_sorted(points) -> np.ndarray:
    arr = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    return arr[np.lexsort((arr[:, 2], arr[:, 1], arr[:, 0]))]


def _rounded(x: float) -> float:
    return round(float(x), _ROUND_DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0


def locate_by_translation(host_verts, part_verts, rules: dict) -> list[Placement]:
    """Spec 3.2 "Presets": find ``part_verts`` inside ``host_verts`` by translation only (0.5 mm grid, 27-neighbour tolerance, accepted at
    hit fraction ``rules['locator']['hit_min']``, placements within ``merge_m`` merged).

    ``host_verts`` and ``part_verts`` are (N, 3) and (M, 3) arrays in the same frame and units (metres). Returns the placements sorted by
    translation, each with ``part=""`` (the caller labels it) and ``hit`` >= ``hit_min``; ``[]`` for an empty host or part. Candidate
    translations come from the part's lexicographically smallest vertex: one per distinct cell shift that puts it on a host vertex.
    """
    cfg = rules["locator"]
    grid, hit_min, merge_m = float(cfg["grid_m"]), float(cfg["hit_min"]), float(cfg["merge_m"])
    host, part = _lex_sorted(host_verts), _lex_sorted(part_verts)
    n_part = len(part)
    if len(host) == 0 or n_part == 0:
        return []
    max_miss = int(np.floor((1.0 - hit_min) * n_part + 1e-9))
    if max_miss < 0:
        return []

    host_cells = _cells(host, grid, _LOCATE_CELL_LIMIT)
    part_cells = _cells(part, grid, _LOCATE_CELL_LIMIT)
    host_keys = np.unique(_pack(host_cells))
    near, own = _deltas(_NEIGHBOURS), _deltas(_EXACT)[0]

    # one candidate per distinct cell shift; np.unique keeps the first host vertex of a shift, which is the lexicographically smallest
    # because the host is sorted. A shift is whole cells: the part's smallest vertex lands in the cell of that host vertex.
    shifts, first = np.unique(host_cells - part_cells[0], axis=0, return_index=True)

    # prefilter: the sampled vertices, with the miss budget of the full test
    sample = np.unique(np.round(np.linspace(0, n_part - 1, min(int(cfg["sample_n"]), n_part))).astype(np.int64))
    miss = np.zeros(len(shifts), dtype=np.int64)
    alive = np.arange(len(shifts))
    for i in sample:
        landed = _lands(host_keys, _pack(part_cells[i] + shifts[alive]), near)
        miss[alive] += ~landed
        alive = alive[miss[alive] <= max_miss]
        if len(alive) == 0:
            return []

    # full test on the survivors: vertices that miss, and (the tie-break) vertices landing in their own cell
    shifts, first = shifts[alive], first[alive]
    miss = np.zeros(len(alive), dtype=np.int64)
    own_hits = np.zeros(len(alive), dtype=np.int64)
    for i in range(n_part):
        keys = _pack(part_cells[i] + shifts)
        own_hits += _present(host_keys, keys + own)
        miss += ~_lands(host_keys, keys, near)

    accepted = []
    for k in np.flatnonzero(miss <= max_miss):
        t = host[first[k]] - part[0]
        accepted.append((int(miss[k]), -int(own_hits[k]), tuple(float(c) for c in t)))
    accepted.sort()  # fewest misses, then most own-cell hits, then smallest translation

    kept: list[tuple[int, tuple[float, float, float]]] = []
    for n_miss, _, t in accepted:
        if all(float(np.linalg.norm(np.subtract(t, kt))) > merge_m for _, kt in kept):
            kept.append((n_miss, t))
    out = [
        Placement(part="", t=(_rounded(t[0]), _rounded(t[1]), _rounded(t[2])), hit=round((n_part - n_miss) / n_part, 4))
        for n_miss, t in kept
    ]
    return sorted(out, key=lambda p: p.t)


def strip(host_verts, host_tris, placements: list[Placement], part_meshes: dict) -> tuple:
    """Spec 3.2 "strip": drop the host triangles whose three vertices all lie on a located part.

    ``part_meshes`` maps each ``Placement.part`` to that part's (M, 3) vertex array, or to a ``(verts, tris)`` tuple (only the vertices are
    read); a placement whose part is missing raises ``KeyError``. A host vertex lies on a located part when a vertex of the part translated
    by ``Placement.t`` is in its cell or a neighbouring cell of the 1e-4 m grid (the precision ``t`` is stored at, see ``_STRIP_CELL_M``).

    Returns ``(verts, tris)``: the host without the stripped triangles, ``tris`` a (K, 3) int64 array indexing ``verts``. The vertices that
    are on a located part and no longer used by a surviving triangle are removed too (otherwise the part's points would still reach the
    detectors that read vertices alone); every other vertex stays, in order, even if unused. A base vertex shared with a part (a fused seam)
    stays, because a surviving triangle uses it. The inputs are not modified.
    """
    verts = np.asarray(host_verts, dtype=np.float64).reshape(-1, 3)
    tris = np.asarray(host_tris, dtype=np.int64).reshape(-1, 3)
    on_part = np.zeros(len(verts), dtype=bool)
    if len(verts) and placements:
        host_keys = _pack(_cells(verts, _STRIP_CELL_M, _STRIP_CELL_LIMIT))
        near = _deltas(_NEIGHBOURS)
        for pl in placements:
            try:
                mesh = part_meshes[pl.part]
            except KeyError:
                raise KeyError(f"strip: no part mesh for the placement of {pl.part!r}") from None
            pv = np.asarray(mesh[0] if isinstance(mesh, tuple) else mesh, dtype=np.float64).reshape(-1, 3)
            part_keys = np.unique(_pack(_cells(pv + np.asarray(pl.t, dtype=np.float64), _STRIP_CELL_M, _STRIP_CELL_LIMIT)))
            on_part |= _lands(part_keys, host_keys, near)

    survivors = tris[~on_part[tris].all(axis=1)] if len(tris) else tris
    used = np.zeros(len(verts), dtype=bool)
    used[survivors.ravel()] = True
    keep = used | ~on_part
    remap = np.cumsum(keep) - 1
    return verts[keep].copy(), remap[survivors].astype(np.int64).reshape(-1, 3)
