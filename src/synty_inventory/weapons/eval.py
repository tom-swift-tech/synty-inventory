"""``weapons attach-eval``: precision and recall of the inferred compatibility against hand labels (docs/weapon_attachments.md 7, 8, AC79).

``--labels`` names a ``weapon-attach-labels/1`` file (``{"schema": ..., "pairs": [{"part", "host", "fits"}]}``, ids and
booleans only, INV-17). Two optional, additive parts (S12; an old file stays valid): a pair may carry ``part2`` (a front+rear sight pair answered as
one: it is predicted to fit in a view only when BOTH (part, host) and (part2, host) are, its slot is the part's, and it is skipped unless both parts are
attachment records), and a top-level ``excluded`` list of ``{"part", "host"}`` / ``{"part", "part2", "host"}`` (pairs that are not labels: the spot-check
draw skips them, attach-eval ignores them). Every labelled pair is judged against the built directory:

* a pair is PREDICTED to fit by a VIEW, a rule over the two lists (A8, AC127; ``VIEWS`` names each rule and the JSON repeats it, with the tiers each
  list is read at, as ``views.<name>.predicted_from``). ``pending_hosts`` counts on purpose: they are the compatibility the inference found, only the
  gun's seat is unknown (D-8), and a label says whether the part fits the gun, not whether the directory can place it.
    - ``default``: what the default export lists: ``compatible_hosts`` at any tier (``compat.DEFAULT_TIERS``) or ``pending_hosts`` at
      ``compat.DEFAULT_PENDING_TIERS`` (override, twin, same_pack_fit). The ``--min-precision`` / ``--min-recall`` gates read it.
    - ``with_cross_pack``: every tier of both lists. Reported, never gated (AC80c).
    - ``same_pack_only``: ``same_pack_fit`` or better in either list (what ``default`` was before A8).
* precision = TP / (TP + FP) over the predicted pairs, recall = TP / (TP + FN) over the labelled positives. A ratio with an
  empty denominator is ``null`` and fails any gate supplied for it (nothing was proved).

A pair whose part is not an attachment record, or whose host is not an eligible host of the directory, is listed under
``skipped`` and counted nowhere. Exit 0 when every supplied gate holds, 4 below one (``--min-precision``, ``--min-recall``),
2 for an unreadable labels file or a missing directory, 6 for a labels file that breaks its schema.

G1 (spec 3.10, AC142): for the four geometry slots (``fit_types.FIT_SLOTS``) the labels are DESCRIPTIVE. ``slots`` is the agreement table, per slot: the
labelled pairs by the state the directory gives them (``listed`` in ``compatible_hosts`` at any tier, ``pending`` in ``pending_hosts``, ``absent``
from both) against the label. No exit code depends on it, so the gates read only the ``label_era`` block: the pairs of the other slots (``laser_light``
and the sight slots, which keep the label-era rules, Q-G12). The ``views`` over all pairs stay as they were, printed and never gated.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import EXIT_COVERAGE, EXIT_OK, InputError, SchemaError
from .cli import _catalogs, _emit, _guarded
from . import COMPAT_TIERS
from .compat import DEFAULT_PENDING_TIERS, DEFAULT_TIERS
from .fit_types import FIT_SLOTS
from .mounts import eligible
from .overrides import well_formed_id

LABELS_SCHEMA = "weapon-attach-labels/1"
STATES = ("listed", "pending", "absent")  # what the directory says of a labelled geometry-slot pair
PAIR_KEYS = ("fits", "host", "part")
PAIR2_KEYS = ("fits", "host", "part", "part2")  # a two-part pair (S12)
EXCLUDED_KEYS = ("host", "part")
EXCLUDED2_KEYS = ("host", "part", "part2")
# A8 (AC127): view -> the tiers a pair is predicted at, per list. The default view reads the export's own cuts (compat.DEFAULT_TIERS for the
# compatible list, compat.DEFAULT_PENDING_TIERS for the pending one), so a change of the export moves the gated view with it.
VIEWS = {
    "default": {"compatible_hosts": tuple(DEFAULT_TIERS), "pending_hosts": tuple(DEFAULT_PENDING_TIERS)},
    "with_cross_pack": {"compatible_hosts": tuple(COMPAT_TIERS), "pending_hosts": tuple(COMPAT_TIERS)},
    "same_pack_only": {"compatible_hosts": tuple(DEFAULT_PENDING_TIERS), "pending_hosts": tuple(DEFAULT_PENDING_TIERS)},
}


def validate_labels(doc) -> list[str]:
    """Every violation of ``weapon-attach-labels/1``: ids and booleans only, one entry per (part, part2 or none, host) across ``pairs`` and ``excluded``."""
    if not isinstance(doc, dict):
        return ["labels: top level must be an object"]
    errors: list[str] = []
    if doc.get("schema") != LABELS_SCHEMA:
        errors.append(f"schema: expected {LABELS_SCHEMA!r}, got {doc.get('schema')!r}")
    for key in doc:
        if key not in ("schema", "pairs", "excluded"):
            errors.append(f"{key}: unknown top-level key")
    pairs = doc.get("pairs")
    if not isinstance(pairs, list):
        return errors + ["pairs: must be a list"]
    excluded = doc.get("excluded", [])
    if not isinstance(excluded, list):
        errors.append("excluded: must be a list")
        excluded = []
    seen: dict[tuple, str] = {}  # (part, part2 or None, host) -> the list that holds it

    def entry(where: str, item, keys: tuple, keys2: tuple, listname: str, shape: str) -> None:
        if not isinstance(item, dict):
            errors.append(f"{where}: must be an object")
            return
        if sorted(item) not in (list(keys), list(keys2)):
            errors.append(f"{where}: keys must be exactly {shape}")
            return
        bad = False
        for name in ("part", "host", "part2"):
            if name in item and not well_formed_id(item[name]):
                errors.append(f"{where}.{name}: must be '<pack>/<asset_id>'")
                bad = True
        if "part2" in item and not bad and item["part2"] == item["part"]:
            errors.append(f"{where}.part2: must differ from part")
        if "fits" in item and not isinstance(item["fits"], bool):
            errors.append(f"{where}.fits: must be true or false")
        key = (item["part"], item.get("part2"), item["host"])
        if key in seen:
            what = "in both pairs and excluded" if seen[key] != listname else "labelled twice" if listname == "pairs" else "listed twice"
            errors.append(f"{where}: ({', '.join(str(x) for x in key if x is not None)}) is {what}")
        seen.setdefault(key, listname)

    for i, pair in enumerate(pairs):
        entry(f"pairs[{i}]", pair, PAIR_KEYS, PAIR2_KEYS, "pairs",
              "part, host, fits, or part, part2, host, fits (ids and a boolean, nothing measured)")
    for i, item in enumerate(excluded):
        entry(f"excluded[{i}]", item, EXCLUDED_KEYS, EXCLUDED2_KEYS, "excluded", "part, host, or part, part2, host (ids only)")
    return errors


def load_labels_doc(path: Path) -> dict:
    """The validated labels document: ``pairs`` and, when the file has one, ``excluded``."""
    if not path.is_file():
        raise InputError(f"labels file not found: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"labels file is not readable JSON: {exc}") from exc
    errors = validate_labels(doc)
    if errors:
        raise SchemaError("the labels violate weapon-attach-labels/1:\n  " + "\n  ".join(errors[:25]), details={"errors": errors})
    return doc


def load_labels(path: Path) -> list[dict]:
    return load_labels_doc(path)["pairs"]


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def _scores(counts: dict) -> dict:
    precision = _ratio(counts["tp"], counts["tp"] + counts["fp"])
    recall = _ratio(counts["tp"], counts["tp"] + counts["fn"])
    return {**counts, "precision": precision, "recall": recall}


def _empty_slot_row() -> dict:
    return {"pairs": 0, **{state: {"labelled_fit": 0, "labelled_no_fit": 0} for state in STATES}}


def _slot_row(row: dict) -> dict:
    """The derived columns of one slot's table: agreement over the decided pairs (``pending`` is undecided, not counted either way)."""
    agree = row["listed"]["labelled_fit"] + row["absent"]["labelled_no_fit"]
    disagree = row["listed"]["labelled_no_fit"] + row["absent"]["labelled_fit"]
    undecided = row["pending"]["labelled_fit"] + row["pending"]["labelled_no_fit"]
    return {**row, "agree": agree, "disagree": disagree, "undecided": undecided,
            "agreement": _ratio(agree, agree + disagree)}


def evaluate(directory: dict, pairs: list[dict], *, packs: set[str] | None = None) -> dict:
    """The metrics of ``pairs`` against the directory (pure). Ratios are exact floats; ``cmd`` rounds them for printing."""
    by_id = {w["id"]: w for w in directory["weapons"]}
    counts = {name: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for name in VIEWS}
    era = {name: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for name in VIEWS}  # the pairs of the label-era slots: what the gates read
    table = {slot: _empty_slot_row() for slot in FIT_SLOTS}
    era_pairs = 0
    skipped: list[dict] = []
    used = 0
    for pair in sorted(pairs, key=lambda p: (p["part"], p.get("part2", ""), p["host"])):
        part, host = by_id.get(pair["part"]), by_id.get(pair["host"])
        part2 = by_id.get(pair["part2"]) if "part2" in pair else None
        if packs is not None and pair["part"].split("/", 1)[0] not in packs:
            continue
        if part is None or not part.get("attachment") or ("part2" in pair and (part2 is None or not part2.get("attachment"))):
            skipped.append({"part": pair["part"], "host": pair["host"], "reason": "part_not_an_attachment"})
            continue
        if host is None or not eligible(host["role"], host["kind"], host["hold_class"]):
            skipped.append({"part": pair["part"], "host": pair["host"], "reason": "host_not_an_eligible_host"})
            continue
        att = part["attachment"]
        found = {lst: [e["tier"] for e in att[lst] if e["host"] == pair["host"]] for lst in ("compatible_hosts", "pending_hosts")}
        found2 = None if part2 is None else {lst: [e["tier"] for e in part2["attachment"][lst] if e["host"] == pair["host"]]
                                             for lst in ("compatible_hosts", "pending_hosts")}
        used += 1
        slot = att.get("slot")
        geometry = slot in FIT_SLOTS
        if geometry:
            state = "listed" if found["compatible_hosts"] else "pending" if found["pending_hosts"] else "absent"
            row = table[slot]
            row["pairs"] += 1
            row[state]["labelled_fit" if pair["fits"] else "labelled_no_fit"] += 1
        else:
            era_pairs += 1
        for name, cuts in VIEWS.items():
            # a two-part pair is predicted only when both of its parts are
            predicted = all(any(t in cuts[lst] for lst, tiers in f.items() for t in tiers) for f in (found, found2) if f is not None)
            key = ("tp" if pair["fits"] else "fp") if predicted else ("fn" if pair["fits"] else "tn")
            counts[name][key] += 1
            if not geometry:
                era[name][key] += 1
    default = counts["default"]
    return {"pairs": used, "positives": default["tp"] + default["fn"], "skipped": skipped,
            **{name: _scores(c) for name, c in counts.items()},
            "slots": {slot: _slot_row(row) for slot, row in table.items()},
            "label_era": {"pairs": era_pairs, "positives": era["default"]["tp"] + era["default"]["fn"],
                          **{name: _scores(c) for name, c in era.items()}}}


def _shown(block: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in block.items()}


@_guarded
def cmd(args, cfg) -> int:
    """``attach-eval --labels FILE [--min-precision X] [--min-recall Y] [--pack A,B]``; JSON on stdout.

    The gates read ``label_era`` (laser_light and the sight slots, Q-G12) and nothing else: the agreement table of the four geometry slots (``slots``,
    AC142) never moves the exit code."""
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
        got = result["label_era"]["default"][metric]
        if got is None or got < gates[gate]:
            failed.append({"gate": gate, "wanted": gates[gate], "got": None if got is None else round(got, 4)})
    _emit({
        "ok": not failed, "labels": Path(args.labels).name, "pairs": result["pairs"], "positives": result["positives"],
        "views": {name: {"predicted_from": {lst: list(tiers) for lst, tiers in cuts.items()}} for name, cuts in VIEWS.items()},
        "predicted_from": ["compatible_hosts", "pending_hosts"],  # the lists read (unchanged); the tiers per view are in views.<name>.predicted_from
        **{name: _shown(result[name]) for name in VIEWS},
        "slots": {slot: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()} for slot, row in result["slots"].items()},
        "label_era": {"pairs": result["label_era"]["pairs"], "positives": result["label_era"]["positives"],
                      **{name: _shown(result["label_era"][name]) for name in VIEWS}},
        "gated": "label_era",  # the block the gates read; the geometry slots (slots) are descriptive only (spec 3.10)
        "gates": {k: v for k, v in gates.items() if v is not None}, "failed": failed, "skipped": result["skipped"],
    })
    return EXIT_COVERAGE if failed else EXIT_OK
