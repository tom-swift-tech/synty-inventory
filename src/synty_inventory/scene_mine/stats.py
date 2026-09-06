"""Placement statistics: histogram, roles, adjacency, spacing, rotation,
scale, ground, density and streets -- the ``stats`` half of ``scene-grammar/1``
(spec §4), plus the Overview-scene heuristic (spec §7).

Every function here is a pure reduction over placement dicts shaped like the
schema's ``placements[]`` rows (``scene``, ``asset_id``, ``pos_m``, ``yaw_deg``,
``scale``, ...); nothing in this module reads a file or touches the catalog.

Adjacency/spacing/ground/density/streets all need nearest-neighbour queries
on XZ position, and two different demo scenes are two different coordinate
spaces -- a "nearest neighbour" can never cross a scene boundary. Those
functions therefore take ``scenes: Sequence[Sequence[Placement]]`` (one list
per non-duplicate scene) and compute within each scene before pooling the
per-instance/per-cell results. Histogram/roles/rotation/scale only look at
one placement at a time, so they take a single flat list.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Mapping, NamedTuple, Sequence

import numpy as np

Placement = Mapping[str, Any]

# D1 (lead, 2026-09-06): the catalog's `module.role` holds building sub-roles
# (floor/roof/corner/...), not this vocabulary -- `type` is the field that
# carries it. building/* -> building; environment/city_layout (the road/kerb/
# ground tile family) -> road; prop, prop/*, environment, weapon -> prop;
# character, character/* -> character; vehicle -> vehicle; fx -> fx; else
# unknown. Catalog-derived only, never guessed from the name (spec §5).
def role_of_type(catalog_type: str | None) -> str:
    t = catalog_type or ""
    if t.startswith("building"):
        return "building"
    if t == "environment/city_layout":
        return "road"
    if t in ("prop", "environment", "weapon") or t.startswith("prop/"):
        return "prop"
    if t == "character" or t.startswith("character/"):
        return "character"
    if t == "vehicle":
        return "vehicle"
    if t == "fx":
        return "fx"
    return "unknown"


def roles_for(asset_ids: Sequence[str], type_by_id: Mapping[str, str | None]) -> dict[str, str]:
    return {aid: role_of_type(type_by_id.get(aid)) for aid in sorted(set(asset_ids))}


def histogram(placements: Sequence[Placement]) -> dict[str, int]:
    """Count of each asset id across every non-duplicate resolved placement."""
    counts: dict[str, int] = {}
    for p in placements:
        counts[p["asset_id"]] = counts.get(p["asset_id"], 0) + 1
    return dict(sorted(counts.items()))


def _pct(values: Sequence[float], q: float) -> float:
    return round(float(np.percentile(np.asarray(values, dtype=float), q, method="linear")), 4)


def _pairwise_dist_xz(placements: Sequence[Placement]) -> tuple[np.ndarray, np.ndarray]:
    xz = np.array([[p["pos_m"][0], p["pos_m"][2]] for p in placements], dtype=float)
    diff = xz[:, None, :] - xz[None, :, :]
    dist = np.sqrt((diff**2).sum(axis=-1))
    return xz, dist


def _rotate_into_yaw_frame(offset_world: Sequence[float], yaw_deg: float) -> tuple[float, float, float]:
    """A world-space (x,y,z) offset expressed in the yaw-aligned local frame
    of an instance rotated ``yaw_deg`` about Y -- D8's convention, where local
    +Z maps to world ``(sin(yaw), cos(yaw))``. Y (height) passes through
    unchanged."""
    theta = math.radians(yaw_deg)
    c, s = math.cos(theta), math.sin(theta)
    wx, wy, wz = offset_world
    return (c * wx - s * wz, wy, s * wx + c * wz)


def adjacency(scenes: Sequence[Sequence[Placement]], radius_m: float, hist: Mapping[str, int]) -> dict:
    """Co-occurrence of asset-id pairs within ``radius_m`` on the XZ plane,
    computed within each scene (never across scenes) and summed. Both
    directions of a pair are counted separately (``(a, b)`` and ``(b, a)``
    are different rows); ``mean_offset_m`` is the mean of every qualifying
    ``b - a`` displacement, expressed in ``a``'s yaw-aligned local frame."""
    pair_count: dict[tuple[str, str], int] = defaultdict(int)
    pair_offset_sum: dict[tuple[str, str], np.ndarray] = {}
    for scene_placements in scenes:
        n = len(scene_placements)
        if n < 2:
            continue
        _xz, dist = _pairwise_dist_xz(scene_placements)
        np.fill_diagonal(dist, np.inf)
        ii, jj = np.where(dist <= radius_m)
        for i, j in zip(ii.tolist(), jj.tolist()):
            pi, pj = scene_placements[i], scene_placements[j]
            key = (pi["asset_id"], pj["asset_id"])
            pair_count[key] += 1
            offset_world = [pj["pos_m"][k] - pi["pos_m"][k] for k in range(3)]
            offset_local = np.array(_rotate_into_yaw_frame(offset_world, pi["yaw_deg"]))
            pair_offset_sum[key] = pair_offset_sum.get(key, np.zeros(3)) + offset_local
    pairs = []
    for (a, b), count in pair_count.items():
        mean_offset = pair_offset_sum[(a, b)] / count
        pairs.append(
            {
                "a": a,
                "b": b,
                "count": count,
                "p_b_given_a": round(count / hist[a], 4) if hist.get(a) else 0.0,
                "mean_offset_m": [round(float(c), 4) for c in mean_offset],
            }
        )
    pairs.sort(key=lambda r: (-r["count"], r["a"], r["b"]))
    return {"radius_m": radius_m, "pairs": pairs}


def spacing(scenes: Sequence[Sequence[Placement]]) -> dict[str, dict]:
    """Per asset id: nearest same-id XZ distance (p50/p90, ``null`` when
    fewer than 2 instances of that id exist anywhere) and nearest any-id XZ
    distance (p50), pooled across scenes."""
    same_by_id: dict[str, list[float]] = defaultdict(list)
    any_by_id: dict[str, list[float]] = defaultdict(list)
    n_by_id: dict[str, int] = defaultdict(int)
    for scene_placements in scenes:
        n = len(scene_placements)
        ids = [p["asset_id"] for p in scene_placements]
        for aid in ids:
            n_by_id[aid] += 1
        if n < 2:
            continue
        _xz, dist = _pairwise_dist_xz(scene_placements)
        for i in range(n):
            row = dist[i].copy()
            row[i] = np.inf
            any_by_id[ids[i]].append(float(row.min()))
            same_mask = np.array([ids[k] == ids[i] for k in range(n)])
            same_mask[i] = False
            if same_mask.any():
                same_by_id[ids[i]].append(float(row[same_mask].min()))
    out = {}
    for aid, n in sorted(n_by_id.items()):
        same_vals = same_by_id.get(aid, [])
        any_vals = any_by_id.get(aid, [])
        out[aid] = {
            "n": n,
            "nn_same_m_p50": _pct(same_vals, 50) if same_vals else None,
            "nn_same_m_p90": _pct(same_vals, 90) if same_vals else None,
            "nn_any_m_p50": _pct(any_vals, 50) if any_vals else None,
        }
    return out


def rotation(placements: Sequence[Placement]) -> dict[str, dict]:
    """Per asset id: fraction of instances within +-1 deg of a cardinal yaw
    (0/90/180/270 -- A5's tolerance, matching ``POI_builder``'s
    ``corner_yaw`` gate), the cardinal histogram, and the sorted unique
    non-cardinal yaws (1 dp)."""
    by_id: dict[str, list[float]] = defaultdict(list)
    for p in placements:
        by_id[p["asset_id"]].append(p["yaw_deg"] % 360.0)
    out = {}
    for aid, yaws in sorted(by_id.items()):
        cardinal_hist = {"0": 0, "90": 0, "180": 0, "270": 0}
        non_cardinal: list[float] = []
        cardinal_n = 0
        for y in yaws:
            matched = None
            for c in (0, 90, 180, 270):
                if min(abs(y - c), 360 - abs(y - c)) <= 1.0:
                    matched = c
                    break
            if matched is not None:
                cardinal_hist[str(matched)] += 1
                cardinal_n += 1
            else:
                non_cardinal.append(round(y, 1))
        out[aid] = {
            "cardinal_frac": round(cardinal_n / len(yaws), 4),
            "yaw_hist_deg": cardinal_hist,
            "non_cardinal_yaws_deg": sorted(set(non_cardinal)),
        }
    return out


def scale_stats(placements: Sequence[Placement]) -> dict[str, dict]:
    """Per asset id: fraction of instances at exactly ``[1,1,1]`` (within
    1e-4), the per-axis min/max scale, and n -- records the non-unit-scale
    finding (spec AC9) without acting on it (A9)."""
    by_id: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for p in placements:
        by_id[p["asset_id"]].append(tuple(p["scale"]))
    out = {}
    for aid, scales in sorted(by_id.items()):
        arr = np.array(scales)
        unit = np.all(np.abs(arr - 1.0) < 1e-4, axis=1)
        out[aid] = {
            "unit_frac": round(float(unit.mean()), 4),
            "min": [round(float(v), 4) for v in arr.min(axis=0)],
            "max": [round(float(v), 4) for v in arr.max(axis=0)],
            "n": len(scales),
        }
    return out


def ground(scenes: Sequence[Sequence[Placement]], roles: Mapping[str, str]) -> dict[str, dict]:
    """Per asset id, instance y minus the y of the nearest road-role instance
    in the same scene (XZ nearest -- "top of the tile" per spec §4); ``{}``
    when the pack has no road role at all."""
    if not any(r == "road" for r in roles.values()):
        return {}
    by_id: dict[str, list[float]] = defaultdict(list)
    for scene_placements in scenes:
        road = [p for p in scene_placements if roles.get(p["asset_id"]) == "road"]
        if not road:
            continue
        road_xz = np.array([[p["pos_m"][0], p["pos_m"][2]] for p in road])
        road_y = np.array([p["pos_m"][1] for p in road])
        for p in scene_placements:
            xz = np.array([p["pos_m"][0], p["pos_m"][2]])
            d = np.linalg.norm(road_xz - xz, axis=1)
            nearest = int(d.argmin())
            by_id[p["asset_id"]].append(p["pos_m"][1] - float(road_y[nearest]))
    return {aid: {"y_rel_p50": _pct(vs, 50), "y_rel_p90": _pct(vs, 90)} for aid, vs in sorted(by_id.items())}


def density(scenes: Sequence[Sequence[Placement]], cell_m: float, roles: Mapping[str, str]) -> dict:
    """Occupied-cell placement counts on an XZ grid of ``cell_m``. Each cell
    key is scoped to its scene index so two scenes' grids never collide even
    though both start at their own local origin; percentiles/max are taken
    over the pooled occupied-cell counts."""
    counts: dict[tuple[int, int, int], int] = defaultdict(int)
    role_counts: dict[tuple[int, int, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for si, scene_placements in enumerate(scenes):
        for p in scene_placements:
            cx = math.floor(p["pos_m"][0] / cell_m)
            cz = math.floor(p["pos_m"][2] / cell_m)
            key = (si, cx, cz)
            counts[key] += 1
            role_counts[key][roles.get(p["asset_id"], "unknown")] += 1
    per_cell = list(counts.values())
    by_role_lists: dict[str, list[int]] = defaultdict(list)
    for rc in role_counts.values():
        for role, c in rc.items():
            by_role_lists[role].append(c)
    return {
        "cell_m": cell_m,
        "cells": len(counts),
        "per_cell_p50": _pct(per_cell, 50) if per_cell else 0.0,
        "per_cell_p90": _pct(per_cell, 90) if per_cell else 0.0,
        "per_cell_max": int(max(per_cell)) if per_cell else 0,
        "by_role_per_cell_p50": {r: _pct(vs, 50) for r, vs in sorted(by_role_lists.items())},
    }


def streets(scenes: Sequence[Sequence[Placement]], roles: Mapping[str, str]) -> dict | None:
    """v1 street-cadence *estimate* from road-role placements -- ``null``
    when the pack has no road role. These are heuristic proxies, not
    measured kerb-to-kerb numbers (spec: "document the exact definitions"):

    - ``axis_deg``: the modal yaw (rounded to the nearest degree) of every
      road-role instance.
    - ``module_m``: the modal nearest-same-id XZ distance among road-role
      instances (1 dp) -- the repeat spacing of one road tile.
    - ``run_lengths_*``: within each scene, road instances are projected onto
      ``axis_deg`` and sorted; consecutive tiles within +-10% of ``module_m``
      of each other extend the current run, anything else starts a new one.
      p50/p90 are taken over every run's tile count, pooled across scenes.
    - ``width_m_p50`` / ``building_setback_m_p50``: p50 of the nearest
      building-role instance's XZ distance from a road-role instance, pooled
      across scenes -- the same measurement used for both numbers in v1 (a
      proxy for "how far back do buildings sit from the road", not a
      kerb-to-kerb width).
    """
    if not any(r == "road" for r in roles.values()):
        return None
    road_ids = sorted(aid for aid, r in roles.items() if r == "road")
    yaws: list[float] = []
    same_nn: list[float] = []
    all_road: list[list[Placement]] = []
    for scene_placements in scenes:
        road = [p for p in scene_placements if roles.get(p["asset_id"]) == "road"]
        all_road.append(road)
        for p in road:
            yaws.append(round(p["yaw_deg"] % 360.0))
        # Same-id only: different road-role ids (a base tile, its lane-line
        # decal, an adjoining sidewalk edge, ...) are routinely stacked at
        # the *identical* XZ position (observed on POLYGON_SciFi_City: 185/364
        # road-role instances there have a same-position, different-id
        # neighbour) -- an any-id nearest-neighbour pass lets those 0 m
        # "distances" dominate the mode and reports a nonsensical module_m
        # of 0. Grouping by id first measures the actual repeat spacing of
        # one road tile, matching this stat's own docstring.
        by_id: dict[str, list[Placement]] = defaultdict(list)
        for p in road:
            by_id[p["asset_id"]].append(p)
        for same_id_road in by_id.values():
            if len(same_id_road) < 2:
                continue
            _xz, dist = _pairwise_dist_xz(same_id_road)
            np.fill_diagonal(dist, np.inf)
            # A same-id pair can still be stacked at the identical XZ position
            # (e.g. a decal duplicated in place with a different yaw/scale) --
            # a 0 m "repeat spacing" is meaningless for module_m and would also
            # violate the schema's `module_m > 0` constraint. Drop exact
            # coincident pairs; module_m falls back to None (schema-nullable)
            # if every same-id nearest-neighbour turns out to be coincident.
            same_nn.extend(round(float(v), 1) for v in dist.min(axis=1) if v > 1e-6)

    if not yaws:
        return {
            "road_asset_ids": road_ids,
            "axis_deg": None,
            "module_m": None,
            "run_lengths_p50": None,
            "run_lengths_p90": None,
            "width_m_p50": None,
            "building_setback_m_p50": None,
        }

    axis_deg = float(Counter(yaws).most_common(1)[0][0])
    module_m = float(Counter(same_nn).most_common(1)[0][0]) if same_nn else None

    run_lengths: list[int] = []
    if module_m:
        axis_rad = math.radians(axis_deg)
        direction = np.array([math.sin(axis_rad), math.cos(axis_rad)])  # D8 convention: yaw 0 = +Z
        tol = 0.1 * module_m
        for road in all_road:
            if not road:
                continue
            xz = np.array([[p["pos_m"][0], p["pos_m"][2]] for p in road])
            proj = np.sort(xz @ direction)
            run = 1
            for k in range(1, len(proj)):
                step = proj[k] - proj[k - 1]
                if abs(step) <= tol or abs(step - module_m) <= tol:
                    run += 1
                else:
                    run_lengths.append(run)
                    run = 1
            run_lengths.append(run)

    setback: list[float] = []
    for scene_placements, road in zip(scenes, all_road):
        building = [p for p in scene_placements if roles.get(p["asset_id"]) == "building"]
        if not road or not building:
            continue
        road_xz = np.array([[p["pos_m"][0], p["pos_m"][2]] for p in road])
        bld_xz = np.array([[p["pos_m"][0], p["pos_m"][2]] for p in building])
        for rp in road_xz:
            d = np.linalg.norm(bld_xz - rp, axis=1)
            setback.append(float(d.min()))

    return {
        "road_asset_ids": road_ids,
        "axis_deg": axis_deg,
        "module_m": module_m,
        "run_lengths_p50": _pct(run_lengths, 50) if run_lengths else None,
        "run_lengths_p90": _pct(run_lengths, 90) if run_lengths else None,
        "width_m_p50": _pct(setback, 50) if setback else None,
        "building_setback_m_p50": _pct(setback, 50) if setback else None,
    }


# Fewer resolved placements than this and a scene is not a layout: it cannot be a catalogue grid (the Overview
# rule below needs the count) and it contributes nothing to the layout statistics (``mine_pack`` marks it
# ``stats_excluded``; it still supplies look and cameras). Set from the 2026-09-06 measurement of the five real
# scenes (map_builder ``tasks/s9_review/sg_overview_heuristic_measured.json``): the catalogue Overviews have
# 333 / 602 placements, the one small authored scene (Sci-Fi City ``Demo_TriplanarDirt``) has 16.
MIN_LAYOUT_PLACEMENTS = 100
# Overview grids place one of each asset: distinct ids / placements was 1.000 on both real Overviews and
# 0.048 / 0.155 on the two Demo layouts.
OVERVIEW_DISTINCT_RATIO = 0.9


class OverviewCheck(NamedTuple):
    is_overview: bool
    placements: int
    distinct: int

    @property
    def distinct_ratio(self) -> float:
        return self.distinct / self.placements if self.placements else 0.0


def is_overview_scene(placements: Sequence[Placement]) -> OverviewCheck:
    """spec §7 as re-set on 2026-09-06 (todo D10): a scene is a catalogue grid
    when it has at least :data:`MIN_LAYOUT_PLACEMENTS` placements AND its
    distinct-asset count is at least :data:`OVERVIEW_DISTINCT_RATIO` of the
    placement count -- ``Overview.unity`` places one of each asset. The
    spec's original nearest-neighbour spacing term is gone: measured on the
    real packs, only 16-24 % of an Overview's placements sit at the modal
    spacing (the grids are not uniform), while the Demo layouts' modal
    spacing is 0.0 m from stacked pieces -- it separated nothing."""
    n = len(placements)
    distinct = len({p["asset_id"] for p in placements})
    is_overview = n >= MIN_LAYOUT_PLACEMENTS and distinct >= OVERVIEW_DISTINCT_RATIO * n
    return OverviewCheck(is_overview, n, distinct)
