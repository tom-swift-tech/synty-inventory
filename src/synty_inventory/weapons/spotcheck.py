"""``weapons attach-spotcheck``: the one-off spot check of the geometry fit gate (docs/weapon_attach_geometry.md 3.10, 4.4; INV-26, AC141).

``--draw`` runs once, after the first geometry build: it draws 32 LISTED pairs (``compatible_hosts``), 8 per geometry slot, from the two tiers the gate
earns on its own (``same_pack_fit``, ``cross_pack_fit``), never a ``twin`` or ``override`` (authored) and never a pair among the hand labels, and writes
them in ascending ``sha256("spotcheck-1|" + part + "|" + host)`` order to ``weapon_attach_spotcheck.json`` (``weapon-attach-spotcheck/1``: ids, tiers and
two nullable booleans per pair, nothing measured). It refuses (exit 6) to run when the file exists: the draw is made once and never again (INV-26).

Tom answers each pair once, ``fits`` and ``placed_wrong`` (spec 3.9: a fit that is placed wrong counts as a fit). ``--score`` prints
``fits k of 32 (placed wrong m)``. The file is a one-off measurement and never a gate: no rule, tolerance, AC or test reads its answers.

The split inside a slot: the 8 pairs divide between the two tiers in proportion to the slot's LISTED pairs of each tier (spec 3.10: "that slot's listed
counts", the labelled ones counted), rounded half up, with at least 2 for a tier that has them; a tier with fewer candidates left after the exclusions
than its share gives what it has and the other tier takes the rest. A slot with fewer than 8 candidates gives them all (the draw reports it under ``short``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import EXIT_BAD_INPUT, EXIT_OK, InputError, SchemaError, WeaponsError, write_text_lf
from .cli import _catalogs, _emit, _guarded
from .fit_types import FIT_SLOTS

SCHEMA = "weapon-attach-spotcheck/1"
SALT = "spotcheck-1"
PER_SLOT = 8
MIN_PER_TIER = 2
DRAW_TIERS = ("same_pack_fit", "cross_pack_fit")  # twin and override are authored, never drawn
DOC_KEYS = ("drawn_at", "pairs", "salt", "schema")
PAIR_KEYS = ("fits", "host", "part", "placed_wrong", "slot", "tier")
_ANSWERS = ("fits", "placed_wrong")


def default_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "weapon_attach_spotcheck.json"


def default_labels_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "weapon_attach_labels.json"


def pair_hash(part: str, host: str) -> str:
    return hashlib.sha256(f"{SALT}|{part}|{host}".encode("utf-8")).hexdigest()


def candidates(directory: dict, labelled: set[tuple[str, str]]) -> tuple[dict[str, dict[str, list[tuple[str, str, str]]]], dict[str, dict[str, int]]]:
    """``(candidates, listed)``. ``candidates`` is ``{slot: {tier: [(hash, part, host), ...]}}``, hash-ascending: the listed pairs of the draw tiers that
    no label covers. ``listed`` is ``{slot: {tier: n}}``, the same pairs counted before the labels are taken out."""
    out: dict[str, dict[str, list]] = {slot: {tier: [] for tier in DRAW_TIERS} for slot in FIT_SLOTS}
    listed = {slot: {tier: 0 for tier in DRAW_TIERS} for slot in FIT_SLOTS}
    for rec in directory["weapons"]:
        att = rec.get("attachment")
        if not att or att.get("slot") not in out:
            continue
        for entry in att.get("compatible_hosts") or []:
            if entry["tier"] not in DRAW_TIERS:
                continue
            listed[att["slot"]][entry["tier"]] += 1
            if (rec["id"], entry["host"]) not in labelled:
                out[att["slot"]][entry["tier"]].append((pair_hash(rec["id"], entry["host"]), rec["id"], entry["host"]))
    for tiers in out.values():
        for rows in tiers.values():
            rows.sort()
    return out, listed


def quotas(listed: dict[str, int], available: dict[str, int] | None = None) -> dict[str, int]:
    """How many of a slot's ``PER_SLOT`` pairs each tier gives: the share of the ``listed`` counts, capped by the ``available`` ones (default: the same)."""
    first, second = DRAW_TIERS
    c1, c2 = listed[first], listed[second]
    a1, a2 = (available or listed)[first], (available or listed)[second]
    if c1 == 0 or c2 == 0:
        return {first: min(PER_SLOT, a1), second: min(PER_SLOT, a2)}
    q1 = (2 * PER_SLOT * c1 + (c1 + c2)) // (2 * (c1 + c2))  # round half up, integers only
    q1 = max(MIN_PER_TIER, min(PER_SLOT - MIN_PER_TIER, q1))
    q1 = min(q1, a1)
    q2 = min(PER_SLOT - q1, a2)
    q1 = min(PER_SLOT - q2, a1)
    return {first: q1, second: q2}


def draw(directory: dict, labelled: set[tuple[str, str]] | None = None) -> tuple[dict, dict]:
    """``(document, short)``: the spot-check document of a directory and, per slot, how many pairs short of 8 the draw is (empty when none)."""
    cands, listed = candidates(directory, labelled or set())
    chosen: list[tuple[str, str, str, str, str]] = []
    short: dict[str, int] = {}
    for slot in FIT_SLOTS:
        want = quotas(listed[slot], {tier: len(rows) for tier, rows in cands[slot].items()})
        got = 0
        for tier in DRAW_TIERS:
            for h, part, host in cands[slot][tier][: want[tier]]:
                chosen.append((h, part, host, slot, tier))
                got += 1
        if got < PER_SLOT:
            short[slot] = PER_SLOT - got
    chosen.sort()
    doc = {
        "schema": SCHEMA, "drawn_at": directory.get("attach_rules_digest"), "salt": SALT,
        "pairs": [{"part": part, "host": host, "slot": slot, "tier": tier, "fits": None, "placed_wrong": None}
                  for _h, part, host, slot, tier in chosen],
    }
    return doc, short


def validate(doc) -> list[str]:
    """Every violation of ``weapon-attach-spotcheck/1``: the shape, the hash order and the answers' types."""
    if not isinstance(doc, dict):
        return ["spot check: top level must be an object"]
    errors: list[str] = []
    if sorted(doc) != list(DOC_KEYS):
        errors.append(f"keys must be exactly {', '.join(DOC_KEYS)}")
    if doc.get("schema") != SCHEMA:
        errors.append(f"schema: expected {SCHEMA!r}, got {doc.get('schema')!r}")
    if doc.get("salt") != SALT:
        errors.append(f"salt: expected {SALT!r}, got {doc.get('salt')!r}")
    pairs = doc.get("pairs")
    if not isinstance(pairs, list):
        return errors + ["pairs: must be a list"]
    seen: set[tuple] = set()
    per_slot: dict[str, int] = {}
    last = ""
    for i, pair in enumerate(pairs):
        where = f"pairs[{i}]"
        if not isinstance(pair, dict) or sorted(pair) != list(PAIR_KEYS):
            errors.append(f"{where}: keys must be exactly {', '.join(PAIR_KEYS)}")
            continue
        if pair["slot"] not in FIT_SLOTS:
            errors.append(f"{where}.slot: {pair['slot']!r} is not a geometry slot")
        if pair["tier"] not in DRAW_TIERS:
            errors.append(f"{where}.tier: {pair['tier']!r} is not a drawn tier")
        for key in _ANSWERS:
            if pair[key] is not None and not isinstance(pair[key], bool):
                errors.append(f"{where}.{key}: must be true, false or null")
        if pair["placed_wrong"] is True and pair["fits"] is not True:
            errors.append(f"{where}: placed_wrong is only meaningful for a fit")
        key = (pair["part"], pair["host"])
        if key in seen:
            errors.append(f"{where}: ({pair['part']}, {pair['host']}) is drawn twice")
        seen.add(key)
        per_slot[pair["slot"]] = per_slot.get(pair["slot"], 0) + 1
        h = pair_hash(pair["part"], pair["host"])
        if h < last:
            errors.append(f"{where}: out of hash order")
        last = h
    for slot, n in sorted(per_slot.items()):
        if n > PER_SLOT:
            errors.append(f"{slot}: {n} pairs, at most {PER_SLOT}")
    return errors


def check_update(baseline: dict, current: dict) -> list[str]:
    """INV-26: what differs between the file as drawn and the file now. Only ``fits`` and ``placed_wrong`` may change, and only from null."""
    errors: list[str] = []
    for key in ("schema", "drawn_at", "salt"):
        if baseline.get(key) != current.get(key):
            errors.append(f"{key}: changed after the draw")
    old, new = baseline.get("pairs") or [], current.get("pairs") or []
    if len(old) != len(new):
        errors.append(f"pairs: {len(old)} drawn, {len(new)} now")
        return errors
    for i, (a, b) in enumerate(zip(old, new)):
        for key in PAIR_KEYS:
            if key in _ANSWERS:
                if a.get(key) is not None and a.get(key) != b.get(key):
                    errors.append(f"pairs[{i}].{key}: changed from {a.get(key)!r} to {b.get(key)!r} (an answer is given once)")
            elif a.get(key) != b.get(key):
                errors.append(f"pairs[{i}].{key}: changed after the draw")
    return errors


def score(doc: dict) -> dict:
    pairs = doc["pairs"]
    fits = sum(1 for p in pairs if p["fits"] is True)
    wrong = sum(1 for p in pairs if p["placed_wrong"] is True)
    answered = sum(1 for p in pairs if p["fits"] is not None)
    return {"fits": fits, "placed_wrong": wrong, "pairs": len(pairs), "answered": answered,
            "summary": f"fits {fits} of {len(pairs)} (placed wrong {wrong})"}


def _read(path: Path) -> dict:
    if not path.is_file():
        raise InputError(f"spot-check file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"spot-check file is not readable JSON: {exc}") from exc


def _labelled(args) -> set[tuple[str, str]]:
    from .eval import load_labels

    path = Path(args.labels) if getattr(args, "labels", None) else default_labels_path()
    if not getattr(args, "labels", None) and not path.is_file():
        return set()  # no committed labels: nothing to skip
    return {(p["part"], p["host"]) for p in load_labels(path)}


@_guarded
def cmd(args, cfg) -> int:
    """``attach-spotcheck --draw | --score [--directory PATH] [--file PATH] [--labels FILE] [--baseline FILE]``; JSON on stdout.

    ``--draw``: exit 6 when the file exists (never overwritten), 2 for a missing directory. ``--score``: exit 6 for a file that breaks the schema or,
    with ``--baseline`` (the file as drawn), changes anything but an answer from null (INV-26); the line to read is ``summary``."""
    from .directory import DIRECTORY_NAME, read_json, weapons_dir

    path = Path(args.file) if getattr(args, "file", None) else default_path()
    if args.draw:
        if path.exists():
            raise SchemaError(f"{path.name} exists: the spot check is drawn once and never again (INV-26)", details={"file": str(path.name)})
        dpath = Path(args.directory) if args.directory else weapons_dir(_catalogs(args, cfg)) / DIRECTORY_NAME
        if not dpath.is_file():
            raise WeaponsError(f"directory file not found: {dpath}", EXIT_BAD_INPUT)
        labelled = _labelled(args)
        doc, short = draw(read_json(dpath), labelled)
        write_text_lf(path, json.dumps(doc, indent=1) + "\n")
        per_slot = {slot: sum(1 for p in doc["pairs"] if p["slot"] == slot) for slot in FIT_SLOTS}
        tiers = {slot: {t: sum(1 for p in doc["pairs"] if p["slot"] == slot and p["tier"] == t) for t in DRAW_TIERS} for slot in FIT_SLOTS}
        _emit({"ok": True, "drawn": len(doc["pairs"]), "per_slot": per_slot, "per_tier": tiers, "short": short,
               "labelled_skipped": len(labelled), "file": path.name, "drawn_at": doc["drawn_at"]})
        return EXIT_OK
    doc = _read(path)
    errors = validate(doc)
    if not errors and getattr(args, "baseline", None):
        errors = check_update(_read(Path(args.baseline)), doc)
    if errors:
        raise SchemaError("the spot-check file is not valid:\n  " + "\n  ".join(errors[:25]), details={"errors": errors})
    _emit({"ok": True, **score(doc)})
    return EXIT_OK
