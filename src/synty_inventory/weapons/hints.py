"""Hints: suggestions a game MAY default from, never stats (spec 3.6, INV-9).

``derive_hints(record, group_stats, rules)`` is pure: it reads the record's classification, flags and geometry
block and the tables in ``weapon_rules.yaml``. Lengths are compared as integer ten-thousandths of a metre (the
geometry block is rounded to 1e-4), so ``0.9 / 0.3`` style float noise cannot move a record across a cut.
"""

from __future__ import annotations

import math

from . import NON_WEAPON_ROLES
from .classify import tokenize_id

_UNIT = 10000  # lengths in 1e-4 m
_CELL_M = 0.30  # one inventory cell of length
_THICK_M = 0.12  # a lateral extent at or above this makes the item two cells tall
_MAX_CELLS = 6
_MIN_GROUP = 8  # (archetype, genre) groups smaller than this get no triangle-count term
_WEIGHTS = ("light", "medium", "heavy", "very_heavy")
_SIZES = ("tiny", "small", "medium", "large", "huge")


def _units(metres: float) -> int:
    return int(round(metres * _UNIT))


def _p75(sorted_vals: list[int]) -> float:
    """75th percentile, linear interpolation between closest ranks (fixed method: deterministic)."""
    k = (len(sorted_vals) - 1) * 0.75
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def tier_member(record: dict, rules: dict) -> bool:
    """Whether a record takes part in the triangle-count statistics of its (archetype, genre) group."""
    return (
        record["role"] not in NON_WEAPON_ROLES
        and record["archetype"] in rules["tier_base"]
        and record.get("geometry") is not None
    )


def build_group_stats(records: list[dict], rules: dict) -> dict[tuple[str, str], dict]:
    """(archetype, genre) -> {'n': members, 'p75': triangle-count 75th percentile} for groups of >= 8 members."""
    groups: dict[tuple[str, str], list[int]] = {}
    for rec in records:
        if tier_member(rec, rules):
            groups.setdefault((rec["archetype"], rec["genre"]), []).append(int(rec["geometry"]["triangles"]))
    return {k: {"n": len(v), "p75": _p75(sorted(v))} for k, v in sorted(groups.items()) if len(v) >= _MIN_GROUP}


def _size_class(length_units: int, cuts_m: list[float]) -> str:
    return _SIZES[sum(1 for c in cuts_m if length_units >= _units(c))]


def derive_hints(record: dict, group_stats: dict, rules: dict) -> dict:
    """The spec 4.1 ``hints`` block. Reads ``role``, ``archetype``, ``genre``, ``flags``, ``asset_id``, ``geometry``."""
    geo = record.get("geometry")
    role, archetype = record["role"], record["archetype"]
    tokens = set(tokenize_id(record["asset_id"], rules))

    size_class = size_basis = cells = None
    if geo is not None:
        length = _units(geo["length_m"])
        size_class = _size_class(length, rules["size_class_cuts_m"])
        size_basis = "raw" if "mech_scale" in record["flags"] else "measured"
        lateral = max(s for ax, s in zip("xyz", geo["bounds"]["size"]) if ax != geo["long_axis"])
        cells = [min(max(-(-length // _units(_CELL_M)), 1), _MAX_CELLS), 1 if _units(lateral) < _units(_THICK_M) else 2]

    weight = rules["weight_by_archetype"].get(archetype)
    if weight is not None and size_class is not None:
        step = (size_class == "huge") - (size_class == "tiny")
        weight = _WEIGHTS[min(max(_WEIGHTS.index(weight) + step, 0), len(_WEIGHTS) - 1)]

    tier = None
    base = rules["tier_base"].get(archetype)
    if role not in NON_WEAPON_ROLES and base is not None:
        tt = rules.get("tier_tokens") or {}
        tier = base + bool(tokens & set(tt.get("up", ()))) - bool(tokens & set(tt.get("down", ())))
        stats = group_stats.get((archetype, record["genre"]))
        if geo is not None and stats is not None and geo["triangles"] > stats["p75"]:
            tier += 1
        tier = min(max(tier, 1), 5)

    ammo = None
    if role not in NON_WEAPON_ROLES:
        ammo = rules["ammo_by_archetype"].get(archetype)
        if ammo is not None:  # a plasma sword stays null: the token override only re-labels an ammo user
            for family, words in sorted((rules.get("ammo_token_overrides") or {}).items()):
                if tokens & set(words):
                    ammo = family
                    break

    return {
        "size_class": size_class,
        "size_basis": size_basis,
        "inventory_cells": cells,
        "weight_class": weight,
        "quality_tier": tier,
        "ammo_family": ammo,
    }
