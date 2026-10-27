"""Locator and strip of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.2 "Presets", 3.11, 4.1 ``locator``, 4.3; plan slice S3; errata E1.2).

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring).

``locate_by_translation`` finds ONE part inside a preset host's vertices by translation only. ``strip`` then removes the located parts from the
host mesh, so no host detector reads a fused scope's top as the rail. Both are pure functions over arrays: the caller hands in the host's
vertices (any frame: only translations are compared) and reads the pack; nothing here touches a file.

Readings of the spec chosen here (each is also noted where it is used):

* **One landing test (E1.2).** A point is keyed by its integer cell ``floor(x / grid_m)`` per axis, plain floor with no epsilon. A part vertex
  ``p`` "lands" at translation ``t`` when a host vertex is in the cell of ``p + t`` or in one of the 26 cells around it. ``t`` is the STORED
  translation (rounded to 1e-4 m), so the locator and ``strip`` ask the same question of the same number; the locator once tested whole-cell
  shifts, which disagree with a test on ``t`` at the tolerance edge (``floor(a + b - c)`` against ``floor(a) + floor(b) - floor(c)``) and lost
  copies whose vertices were well inside 0.5 mm. A vertex lands whenever some host vertex is within ``grid_m`` of ``p + t`` on every axis, and
  never when every host vertex is ``2 * grid_m`` or farther on some axis (the cells are then two apart); between the two the grid decides.
  ``strip`` reads the same relation from the host side: it is symmetric (a host cell one step from a part cell is the part cell one step from it).
* **Prefilter.** The ``sample_n`` sampled vertices (evenly spaced over the sorted part, all of them for a smaller part) may miss at most
  ``floor((1 - hit_min) * n)`` times, ``n`` being the part's vertex count: the miss budget of the full test. At ``hit_min`` 1.0 it is "every
  sampled vertex lands"; below 1.0 it never rejects a candidate the full test would accept, so ``hit_min`` is decided in one place.
* **Candidates.** One per occupied host cell: ``t`` is the cell's lexicographically first host vertex minus the part's lexicographically smallest
  vertex, rounded to 1e-4 m, and is tested as it will be stored.
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

# spec 4.3: stored measures are rounded to 1e-4 m. ``Placement.t`` is stored at this precision and the landing test reads the stored value
# (E1.2), so a candidate is rounded before it is tested. The old ``_STRIP_CELL_M`` (strip's own 1e-4 m grid) is retired with it.
_ROUND_DECIMALS = 4

# the 27 cells around (and including) a cell, and the cell itself
_NEIGHBOURS = tuple((dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1))
_EXACT = ((0, 0, 0),)

# a cell triple packs into one int64 (21 bits per axis, biased so negatives sort): a neighbouring cell is the key plus a constant. No set
# or dict is iterated; the keys are looked up with searchsorted over a sorted array.
_BITS = 21
_BIAS = 1 << (_BITS - 1)
_CELL_LIMIT = _BIAS - 2  # |cell| bound: a neighbouring cell (one step further) still packs into the 21 bits


def _cells(points: np.ndarray, cell_m: float) -> np.ndarray:
    cells = np.floor(points / cell_m).astype(np.int64)
    if cells.size and int(np.abs(cells).max()) > _CELL_LIMIT:
        raise ValueError(f"point outside the +-{_CELL_LIMIT * cell_m:.0f} m the {cell_m} m grid can key")
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


def _part_keys(part_points: np.ndarray, t, grid_m: float) -> np.ndarray:
    """The packed cell keys of ``part_points + t`` (``t`` (3,) or (K, 3) broadcast against the (3,) or (N, 3) points). The ONE place a part
    vertex is placed on the host grid: the locator's candidate test and ``strip`` both go through it, so they cannot disagree (INV-29)."""
    return _pack(_cells(part_points + t, grid_m))


def locate_by_translation(host_verts, part_verts, rules: dict) -> list[Placement]:
    """Spec 3.2 "Presets": find ``part_verts`` inside ``host_verts`` by translation only (the landing test of E1.2: 0.5 mm grid, 27-neighbour
    tolerance, on the stored translation; accepted at hit fraction ``rules['locator']['hit_min']``, placements within ``merge_m`` merged).

    ``host_verts`` and ``part_verts`` are (N, 3) and (M, 3) arrays in the same frame and units (metres). Returns the placements sorted by
    translation, each with ``part=""`` (the caller labels it) and ``hit`` >= ``hit_min``; ``[]`` for an empty host or part. Candidate
    translations come from the part's lexicographically smallest vertex: one per occupied host cell, rounded to 1e-4 m.
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

    host_keys, first = np.unique(_pack(_cells(host, grid)), return_index=True)
    near, own = _deltas(_NEIGHBOURS), _deltas(_EXACT)[0]

    # one candidate per occupied host cell; np.unique keeps the first host vertex of a cell, which is the lexicographically smallest because the
    # host is sorted. The candidate is rounded to the precision it is stored at (4.3) BEFORE it is tested, so what lands is what strip is handed.
    cands = np.round(host[first] - part[0], _ROUND_DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0

    # prefilter: the sampled vertices, with the miss budget of the full test
    sample = np.unique(np.round(np.linspace(0, n_part - 1, min(int(cfg["sample_n"]), n_part))).astype(np.int64))
    miss = np.zeros(len(cands), dtype=np.int64)
    alive = np.arange(len(cands))
    for i in sample:
        landed = _lands(host_keys, _part_keys(part[i], cands[alive], grid), near)
        miss[alive] += ~landed
        alive = alive[miss[alive] <= max_miss]
        if len(alive) == 0:
            return []

    # full test on the survivors: vertices that miss, and (the tie-break) vertices landing in their own cell
    cands = cands[alive]
    miss = np.zeros(len(alive), dtype=np.int64)
    own_hits = np.zeros(len(alive), dtype=np.int64)
    for i in range(n_part):
        keys = _part_keys(part[i], cands, grid)
        own_hits += _present(host_keys, keys + own)
        miss += ~_lands(host_keys, keys, near)

    accepted = []
    for k in np.flatnonzero(miss <= max_miss):
        accepted.append((int(miss[k]), -int(own_hits[k]), tuple(float(c) for c in cands[k])))
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


def strip(host_verts, host_tris, placements: list[Placement], part_meshes: dict, rules: dict) -> tuple:
    """Spec 3.2 "strip": drop the host triangles whose three vertices all lie on a located part.

    ``part_meshes`` maps each ``Placement.part`` to that part's (M, 3) vertex array, or to a ``(verts, tris)`` tuple (only the vertices are
    read); a placement whose part is missing raises ``KeyError``. A host vertex lies on a located part when a vertex of the part translated
    by ``Placement.t`` is in its cell or a neighbouring cell of the ``rules['locator']['grid_m']`` grid: the landing test of the locator
    (E1.2), read from the host side, so a placement the locator returns at hit 1.0 is removed whole (INV-29). Which placements to pass
    (the ones that fill a slot, E1.3) is the caller's call.

    Returns ``(verts, tris)``: the host without the stripped triangles, ``tris`` a (K, 3) int64 array indexing ``verts``. The vertices that
    are on a located part and no longer used by a surviving triangle are removed too (otherwise the part's points would still reach the
    detectors that read vertices alone); every other vertex stays, in order, even if unused. A base vertex shared with a part (a fused seam)
    stays, because a surviving triangle uses it. The inputs are not modified.
    """
    verts = np.asarray(host_verts, dtype=np.float64).reshape(-1, 3)
    tris = np.asarray(host_tris, dtype=np.int64).reshape(-1, 3)
    on_part = np.zeros(len(verts), dtype=bool)
    if len(verts) and placements:
        grid = float(rules["locator"]["grid_m"])
        host_keys = _pack(_cells(verts, grid))
        near = _deltas(_NEIGHBOURS)
        for pl in placements:
            try:
                mesh = part_meshes[pl.part]
            except KeyError:
                raise KeyError(f"strip: no part mesh for the placement of {pl.part!r}") from None
            pv = np.asarray(mesh[0] if isinstance(mesh, tuple) else mesh, dtype=np.float64).reshape(-1, 3)
            part_keys = np.unique(_part_keys(pv, np.asarray(pl.t, dtype=np.float64), grid))
            on_part |= _lands(part_keys, host_keys, near)

    survivors = tris[~on_part[tris].all(axis=1)] if len(tris) else tris
    used = np.zeros(len(verts), dtype=bool)
    used[survivors.ravel()] = True
    keep = used | ~on_part
    remap = np.cumsum(keep) - 1
    return verts[keep].copy(), remap[survivors].astype(np.int64).reshape(-1, 3)
