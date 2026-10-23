"""Sight sets: ``attachment.pair`` (docs/weapon_attachments.md 3.5, amendment A2, INV-20).

A front and a rear iron sight of one set are two parts that mount together. The relation is derived from names only and
stored on BOTH members (nowhere else, so a host record never changes); an id override (``ids[<part>].pair``) pairs or
unpairs two parts the names do not match. A pair is a *set candidate* on a host only when both members list that host
(``set_candidates``); the directory keeps no pair-level compatibility list.
"""

from __future__ import annotations

import re

from . import SIGHT_SLOTS, SchemaError
from .classify import split_tokens
from .compat import tier_rank
from .overrides import pair_overrides

# Dropped from the plain token sequence to get the `variant` of a sight (spec 3.5). NOT `attach_compat.generic_tokens`: that list
# also strips `front` / `rear` (and size words), which would merge unrelated variants.
_NOISE = frozenset({"wep", "sm", "mod", "attach", "attachment", "a", "ironsight", "iron", "sight", "front", "rear"})
_DIGITS_RE = re.compile(r"\d+")


def variant_key(asset_id: str) -> tuple[str, ...]:
    """The part's tokens minus the noise words, sorted (``canted``, ``post``, ``hood`` ... stay in the variant)."""
    return tuple(sorted(t for t in split_tokens(asset_id) if t not in _NOISE))


def number_key(asset_id: str) -> str:
    """The last digit group of the id (``"01"``), or the empty string."""
    groups = _DIGITS_RE.findall(asset_id)
    return groups[-1] if groups else ""


def _sight_records(records: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in records
            if r.get("role") == "part" and (r.get("attachment") or {}).get("slot") in SIGHT_SLOTS}


def _name_pairs(sights: dict[str, dict]) -> dict[str, str]:
    """id -> partner id for every front/rear pair the names give (same pack, variant and number, unique on both sides)."""
    groups: dict[tuple, dict[str, list[str]]] = {}
    for rid in sorted(sights):
        rec = sights[rid]
        key = (rec["pack"], variant_key(rec["asset_id"]), number_key(rec["asset_id"]))
        groups.setdefault(key, {"sight_front": [], "sight_rear": []})[rec["attachment"]["slot"]].append(rid)
    pairs: dict[str, str] = {}
    for sides in groups.values():
        if len(sides["sight_front"]) == 1 and len(sides["sight_rear"]) == 1:
            front, rear = sides["sight_front"][0], sides["sight_rear"][0]
            pairs[front], pairs[rear] = rear, front
    return pairs


def _override_assignments(overrides: dict | None, sights: dict[str, dict]) -> dict[str, str | None]:
    """The explicit pair of every member an override names: ``{id: partner or None}``, symmetric, conflicts refused.

    A key that is not a sight record is skipped (a stale override, reported by the build's stale-override list); a partner
    that is not a record, is not a sight, is in another pack or shares the key's slot is a SchemaError (exit 6).
    """
    assign: dict[str, str | None] = {}

    def put(rid: str, value: str | None, source: str) -> None:
        if rid in assign and assign[rid] != value:
            raise SchemaError(f"pair overrides disagree about {rid!r}: {assign[rid]!r} and {value!r} (from {source})")
        assign[rid] = value

    for key, partner in pair_overrides(overrides).items():
        if key not in sights:
            continue
        if partner is None:
            put(key, None, key)
            continue
        if partner not in sights:
            raise SchemaError(f"{key}: pair {partner!r} is not a sight part of the directory (unknown id)")
        a, b = sights[key], sights[partner]
        if a["pack"] != b["pack"]:
            raise SchemaError(f"{key}: pair {partner!r} is in another pack (a pair is one pack's set, INV-20)")
        if a["attachment"]["slot"] == b["attachment"]["slot"]:
            raise SchemaError(f"{key}: pair {partner!r} is also a {a['attachment']['slot']} (a pair is one front and one rear)")
        put(key, partner, key)
        put(partner, key, key)
    return assign


def apply_pairs(records: list[dict], overrides: dict | None = None) -> None:
    """Fill ``attachment.pair`` on every attachment record (null outside the sight slots), in place.

    Name pairs first (``_name_pairs``), then the id overrides, which win over the names on both members: pairing A with B
    unpairs the partners A and B had, and a ``null`` unpairs A and its partner. The result is symmetric by construction;
    a final check refuses an inconsistent relation rather than store half of it (INV-20).
    """
    sights = _sight_records(records)
    pair = _name_pairs(sights)
    for rid, value in sorted(_override_assignments(overrides, sights).items()):
        old = pair.get(rid)
        if old is not None and old != value and pair.get(old) == rid:
            pair[old] = None  # the former partner is left alone unless an assignment of its own says otherwise
        if value is None:
            pair.pop(rid, None)
        else:
            pair[rid] = value
    for rid, partner in sorted(pair.items()):
        if partner is not None and pair.get(partner) != rid:
            raise SchemaError(f"{rid}: pair {partner!r} does not name it back (INV-20)")
    for rec in records:
        block = rec.get("attachment")
        if block is not None:
            block["pair"] = pair.get(rec["id"]) if rec["id"] in sights else None


def set_candidates(records: list[dict]) -> list[dict]:
    """Every host where both members of a pair are compatible: ``{front, rear, host, tier}`` sorted by ``(front, host)``.

    The tier is the lower rank (the larger number) of the two entries. Where only one member lists a host that member
    mounts alone, so it is not here.
    """
    by_id = {r["id"]: r for r in records if r.get("attachment")}
    out = []
    for rid in sorted(by_id):
        block = by_id[rid]["attachment"]
        partner = block.get("pair")
        if block["slot"] != "sight_front" or partner not in by_id:
            continue
        mine = {e["host"]: e for e in block["compatible_hosts"]}
        theirs = {e["host"]: e for e in by_id[partner]["attachment"]["compatible_hosts"]}
        for host in sorted(set(mine) & set(theirs)):
            tier = max((mine[host]["tier"], theirs[host]["tier"]), key=tier_rank)
            out.append({"front": rid, "rear": partner, "host": host, "tier": tier})
    return out
