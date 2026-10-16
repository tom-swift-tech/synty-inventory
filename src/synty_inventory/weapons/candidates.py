"""Candidate selection and exclusion (spec 3.4.1).

An asset is a candidate when a catalog signal (``type`` / ``semantic_role`` / ``gear.kind`` = weapon) or a
``candidates.include`` name pattern matches it. Every candidate then yields exactly one outcome (INV-3): it is
accepted, or it is rejected with a closed reason. The order is: match -> exclude patterns (first match wins,
reason from the pattern) -> non-placeable. Non-placeable assets still count as candidates-by-match, so the
review page can list them under "Excluded".
"""

from __future__ import annotations

from .classify import tokenize_id
from .rules import match_conditions


def catalog_signals(asset: dict) -> list[str]:
    """Catalog fields that declare a weapon, in a fixed order. VLM-written tags/names are never read."""
    signals = []
    if asset.get("type") == "weapon":
        signals.append("type")
    if asset.get("semantic_role") == "weapon":
        signals.append("semantic_role")
    if (asset.get("gear") or {}).get("kind") == "weapon":
        signals.append("gear.kind")
    return signals


def evaluate_candidate(asset: dict, pack_id: str, rules: dict) -> dict:
    """Full outcome for one asset.

    ``{"candidate", "accepted", "source", "reason", "matched", "include"}``:
    ``candidate`` is false when nothing matched (the asset is not weapon-like and gets no row);
    ``reason``/``matched`` name the exclude pattern (or ``nonplaceable``'s triggering signal) on a rejection;
    ``include`` is the name_token include entry that fired (None for catalog-signal candidates).
    """
    cand = rules["candidates"]
    ctx = {
        "id": asset["id"],
        "tokens": set(tokenize_id(asset["id"], rules)),
        "pack": pack_id,
        "gear_two_handed": None,
        "long_m": None,
        "asset_kind": asset.get("kind"),
    }
    signals = catalog_signals(asset)
    include = None
    if not signals:
        include = next((row for row in cand["include"] if match_conditions(row["match"], ctx)), None)
        if include is None:
            return {"candidate": False, "accepted": False, "source": None, "reason": None, "matched": None,
                    "include": None}
    source = "catalog" if signals else "name_token"
    matched_by = f"catalog:{signals[0]}" if signals else include["name"]

    for row in cand["exclude"]:
        if match_conditions(row["match"], ctx):
            return {"candidate": True, "accepted": False, "source": source, "reason": row["reason"],
                    "matched": row["name"], "include": include and include["name"]}
    if asset.get("placeable") is False:
        return {"candidate": True, "accepted": False, "source": source, "reason": "nonplaceable",
                "matched": matched_by, "include": include and include["name"]}
    return {"candidate": True, "accepted": True, "source": source, "reason": None, "matched": matched_by,
            "include": include and include["name"]}


def select_candidates(asset: dict, pack_id: str, rules: dict) -> tuple[bool, str | None, str | None]:
    """``(is_candidate, source, reject_reason)`` (spec 3.3).

    ``is_candidate`` is true only for an accepted candidate. A rejected candidate returns
    ``(False, source, reason)``; an asset nothing matched returns ``(False, None, None)``.
    """
    out = evaluate_candidate(asset, pack_id, rules)
    return out["accepted"], out["source"], out["reason"]
