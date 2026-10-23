"""``weapons attach-eval``: precision and recall of the inferred compatibility against hand labels (docs/weapon_attachments.md 7, 8, AC79).

``--labels`` names a ``weapon-attach-labels/1`` file (``{"schema": ..., "pairs": [{"part", "host", "fits"}]}``, ids and
booleans only, INV-17). Every labelled pair is judged against the built directory:

* a pair is PREDICTED to fit when its host is in the part's ``compatible_hosts`` or ``pending_hosts`` with a tier at or
  above ``same_pack_fit`` (the default-export tiers, D-11). ``pending_hosts`` counts on purpose: they are the compatibility
  the inference found, only the gun's seat is unknown (D-8), and a label says whether the part fits the gun, not whether the
  directory can place it. The JSON names both lists in ``predicted_from``.
* precision = TP / (TP + FP) over the predicted pairs, recall = TP / (TP + FN) over the labelled positives. A ratio with an
  empty denominator is ``null`` and fails any gate supplied for it (nothing was proved).
* ``with_cross_pack`` repeats the numbers with ``cross_pack_fit`` counted as predicted. It is reported, never gated (AC80c).

A pair whose part is not an attachment record, or whose host is not an eligible host of the directory, is listed under
``skipped`` and counted nowhere. Exit 0 when every supplied gate holds, 4 below one (``--min-precision``, ``--min-recall``),
2 for an unreadable labels file or a missing directory, 6 for a labels file that breaks its schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import EXIT_COVERAGE, EXIT_OK, InputError, SchemaError
from .cli import _catalogs, _emit, _guarded
from .compat import tier_rank
from .mounts import eligible
from .overrides import well_formed_id

LABELS_SCHEMA = "weapon-attach-labels/1"
PAIR_KEYS = ("fits", "host", "part")
DEFAULT_MAX_TIER = "same_pack_fit"


def validate_labels(doc) -> list[str]:
    """Every violation of ``weapon-attach-labels/1``: ids and booleans only, one entry per (part, host)."""
    if not isinstance(doc, dict):
        return ["labels: top level must be an object"]
    errors: list[str] = []
    if doc.get("schema") != LABELS_SCHEMA:
        errors.append(f"schema: expected {LABELS_SCHEMA!r}, got {doc.get('schema')!r}")
    for key in doc:
        if key not in ("schema", "pairs"):
            errors.append(f"{key}: unknown top-level key")
    pairs = doc.get("pairs")
    if not isinstance(pairs, list):
        return errors + ["pairs: must be a list"]
    seen: set[tuple] = set()
    for i, pair in enumerate(pairs):
        where = f"pairs[{i}]"
        if not isinstance(pair, dict):
            errors.append(f"{where}: must be an object")
            continue
        if sorted(pair) != list(PAIR_KEYS):
            errors.append(f"{where}: keys must be exactly part, host, fits (ids and a boolean, nothing measured)")
            continue
        for key in ("part", "host"):
            if not well_formed_id(pair[key]):
                errors.append(f"{where}.{key}: must be '<pack>/<asset_id>'")
        if not isinstance(pair["fits"], bool):
            errors.append(f"{where}.fits: must be true or false")
        key = (pair["part"], pair["host"])
        if key in seen:
            errors.append(f"{where}: ({pair['part']}, {pair['host']}) is labelled twice")
        seen.add(key)
    return errors


def load_labels(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"labels file not found: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"labels file is not readable JSON: {exc}") from exc
    errors = validate_labels(doc)
    if errors:
        raise SchemaError("the labels violate weapon-attach-labels/1:\n  " + "\n  ".join(errors[:25]), details={"errors": errors})
    return doc["pairs"]


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def _scores(counts: dict) -> dict:
    precision = _ratio(counts["tp"], counts["tp"] + counts["fp"])
    recall = _ratio(counts["tp"], counts["tp"] + counts["fn"])
    return {**counts, "precision": precision, "recall": recall}


def evaluate(directory: dict, pairs: list[dict], *, packs: set[str] | None = None) -> dict:
    """The metrics of ``pairs`` against the directory (pure). Ratios are exact floats; ``cmd`` rounds them for printing."""
    by_id = {w["id"]: w for w in directory["weapons"]}
    default = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    cross = dict(default)
    skipped: list[dict] = []
    used = 0
    for pair in sorted(pairs, key=lambda p: (p["part"], p["host"])):
        part, host = by_id.get(pair["part"]), by_id.get(pair["host"])
        if packs is not None and pair["part"].split("/", 1)[0] not in packs:
            continue
        if part is None or not part.get("attachment"):
            skipped.append({"part": pair["part"], "host": pair["host"], "reason": "part_not_an_attachment"})
            continue
        if host is None or not eligible(host["role"], host["kind"], host["hold_class"]):
            skipped.append({"part": pair["part"], "host": pair["host"], "reason": "host_not_an_eligible_host"})
            continue
        att = part["attachment"]
        tiers = [e["tier"] for e in att["compatible_hosts"] + att["pending_hosts"] if e["host"] == pair["host"]]
        used += 1
        for counts, limit in ((default, DEFAULT_MAX_TIER), (cross, "cross_pack_fit")):
            predicted = any(tier_rank(t) <= tier_rank(limit) for t in tiers)
            key = ("tp" if pair["fits"] else "fp") if predicted else ("fn" if pair["fits"] else "tn")
            counts[key] += 1
    return {"pairs": used, "positives": default["tp"] + default["fn"], "skipped": skipped,
            "default": _scores(default), "with_cross_pack": _scores(cross)}


def _shown(block: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in block.items()}


@_guarded
def cmd(args, cfg) -> int:
    """``attach-eval --labels FILE [--min-precision X] [--min-recall Y] [--pack A,B]``; JSON on stdout."""
    from .directory import load_directory

    if not getattr(args, "labels", None):
        raise InputError("attach-eval needs --labels <weapon-attach-labels/1 file>")
    pairs = load_labels(Path(args.labels))
    directory = load_directory(_catalogs(args, cfg))
    packs = set(args.pack.split(",")) if getattr(args, "pack", None) else None
    result = evaluate(directory, pairs, packs=packs)
    gates = {"min_precision": getattr(args, "min_precision", None), "min_recall": getattr(args, "min_recall", None)}
    failed = []
    for gate, metric in (("min_precision", "precision"), ("min_recall", "recall")):
        if gates[gate] is None:
            continue
        got = result["default"][metric]
        if got is None or got < gates[gate]:
            failed.append({"gate": gate, "wanted": gates[gate], "got": None if got is None else round(got, 4)})
    _emit({
        "ok": not failed, "labels": Path(args.labels).name, "pairs": result["pairs"], "positives": result["positives"],
        "max_tier": DEFAULT_MAX_TIER, "predicted_from": ["compatible_hosts", "pending_hosts"],
        "default": _shown(result["default"]), "with_cross_pack": _shown(result["with_cross_pack"]),
        "gates": {k: v for k, v in gates.items() if v is not None}, "failed": failed, "skipped": result["skipped"],
    })
    return EXIT_COVERAGE if failed else EXIT_OK
