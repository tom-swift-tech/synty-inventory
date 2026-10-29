"""The hand-labels normalizer (S12): an export of per-card answers -> one ``weapon-attach-labels/1`` file.

    python -m synty_inventory.weapons.labels_store --export DIR --out FILE

``DIR`` holds the export: ``*.json`` files directly in it (not below), each exactly one JSON object, one per card:
``{"at": ISO-8601 UTC, "card": str, "fits": "yes"|"no"|"skip", "host_id": id, "part_id": id, "slot": str}`` and, for a front+rear sight pair answered
as one, ``"part2_id": id`` (a null ``part2_id`` reads as absent). Other keys are dropped. Rules (Tom, S12 decision 3 and Q1-Q3):

* the key of a record is ``(part_id, part2_id or None, host_id)``; a two-part record is ONE pair and its answer covers both parts together;
* arrival order is the records sorted by ``(at, card)``, indexed from 0 (the report cites those indices, never an id);
* a key whose records all say "yes" (or all "no") is one pair, the identical duplicates collapsed; ``fits`` becomes true / false;
* a key whose records are all "skip" is excluded (reason ``skip``); a key whose records differ at all is excluded (reason ``conflict``; a "skip" counts as
  an answer). Excluded entries are not labels: the spot-check draw skips them, attach-eval ignores them;
* a record that lacks ``part_id`` / ``host_id`` / ``fits`` / ``at`` / ``card`` (the last two fix the order), holds a ``fits`` outside yes / no / skip, or a
  malformed id, is refused with a non-zero exit and nothing is written: a label is never guessed. So is a ``.json`` file that is not one object.

The document is ``{"schema", "pairs", "excluded"}`` with both lists sorted by ``(part, part2 or "", host)`` and ``part2`` only where present, written with
LF endings and a trailing newline (``write_text_lf``), so two runs on one export give identical bytes. The record's ``slot`` is counted in the report
and never written. The report (stdout JSON) holds counts and indices only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import EXIT_BAD_INPUT, EXIT_OK, InputError, SchemaError, WeaponsError, write_text_lf
from .eval import LABELS_SCHEMA, validate_labels
from .overrides import well_formed_id

ANSWERS = ("yes", "no", "skip")


def _record(n: int, rec) -> tuple:
    """``(at, card, key, fits, slot)`` of one export record, or an ``InputError`` (the position ``n`` in the input, no ids)."""
    where = f"record {n}"
    if not isinstance(rec, dict):
        raise InputError(f"{where}: must be an object")
    for name in ("part_id", "host_id", "fits", "at", "card"):
        if name not in rec:
            raise InputError(f"{where}: no {name!r}")
    if not isinstance(rec["fits"], str) or rec["fits"] not in ANSWERS:
        raise InputError(f"{where}: fits must be one of {', '.join(ANSWERS)}")
    for name in ("at", "card"):
        if not isinstance(rec[name], str):
            raise InputError(f"{where}: {name!r} must be a string")
    part2 = rec.get("part2_id")  # null reads as absent
    for name, value in (("part_id", rec["part_id"]), ("host_id", rec["host_id"]), ("part2_id", part2)):
        if (value is not None or name != "part2_id") and not well_formed_id(value):
            raise InputError(f"{where}: {name!r} is not a well-formed '<pack>/<asset_id>'")
    if part2 is not None and part2 == rec["part_id"]:
        raise InputError(f"{where}: part2_id equals part_id")
    slot = rec.get("slot")
    return rec["at"], rec["card"], (rec["part_id"], part2, rec["host_id"]), rec["fits"], slot if isinstance(slot, str) else "none"


def normalize(records) -> tuple[dict, dict]:
    """``(doc, report)`` of the export ``records`` (pure). Raises ``InputError`` for a record that cannot be read, ``SchemaError`` for a document that
    would not validate."""
    rows = [_record(n, rec) for n, rec in enumerate(records)]
    rows.sort(key=lambda r: (r[0], r[1]))  # arrival order; a tie keeps the input order
    groups: dict[tuple, list[tuple[int, str, str]]] = {}
    for index, (_at, _card, key, fits, slot) in enumerate(rows):
        groups.setdefault(key, []).append((index, fits, slot))
    pairs: list[dict] = []
    excluded: list[dict] = []
    pair_slots: dict[str, int] = {}
    excluded_slots: dict[str, int] = {}
    reasons = {"skip": 0, "conflict": 0}
    conflicts: list[dict] = []
    collapsed = 0
    yes = no = two_part = 0
    for (part, part2, host), members in groups.items():
        values = [m[1] for m in members]
        slot = members[0][2]  # the slot of the first arrival (counted, never written)
        base = {"part": part, **({"part2": part2} if part2 is not None else {}), "host": host}
        if len(set(values)) > 1:
            reasons["conflict"] += 1
            conflicts.append({"indices": [m[0] for m in members], "values": values})
            excluded.append(base)
            excluded_slots[slot] = excluded_slots.get(slot, 0) + 1
            continue
        collapsed += len(members) - 1
        if values[0] == "skip":
            reasons["skip"] += 1
            excluded.append(base)
            excluded_slots[slot] = excluded_slots.get(slot, 0) + 1
            continue
        pairs.append({**base, "fits": values[0] == "yes"})
        pair_slots[slot] = pair_slots.get(slot, 0) + 1
        yes += values[0] == "yes"
        no += values[0] == "no"
        two_part += part2 is not None
    order = lambda item: (item["part"], item.get("part2", ""), item["host"])  # noqa: E731
    pairs.sort(key=order)
    excluded.sort(key=order)
    conflicts.sort(key=lambda c: c["indices"][0])
    doc = {"schema": LABELS_SCHEMA, "pairs": pairs, "excluded": excluded}
    errors = validate_labels(doc)
    if errors:
        raise SchemaError("the normalized labels violate weapon-attach-labels/1:\n  " + "\n  ".join(errors[:25]), details={"errors": errors})
    report = {
        "records": len(rows), "distinct_keys": len(groups), "identical_duplicates_collapsed": collapsed,
        "pairs": {"total": len(pairs), "yes": yes, "no": no, "two_part": two_part, "per_slot": dict(sorted(pair_slots.items()))},
        "excluded": {"total": len(excluded), "by_reason": reasons, "per_slot": dict(sorted(excluded_slots.items()))},
        "conflicts": conflicts,
    }
    return doc, report


def read_export(folder: Path) -> list:
    """The record of every ``*.json`` file directly in ``folder``, in file-name order. A file that is not exactly one JSON object is refused."""
    if not folder.is_dir():
        raise InputError(f"export folder not found: {folder}")
    records: list = []
    for path in sorted(folder.glob("*.json"), key=lambda p: p.name):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"export file {path.name} is not readable JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise InputError(f"export file {path.name} is not one JSON object")
        records.append(data)
    if not records:
        raise InputError(f"no *.json records in {folder}")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m synty_inventory.weapons.labels_store",
                                     description="Normalize an export of hand-label answers into a weapon-attach-labels/1 file (report on stdout).")
    parser.add_argument("--export", required=True, metavar="DIR", help="folder of the export, one JSON object per card")
    parser.add_argument("--out", required=True, metavar="FILE", help="the labels file to write (its folder must exist)")
    args = parser.parse_args(argv)
    out = Path(args.out)
    try:
        if not out.parent.is_dir():
            raise InputError(f"--out folder does not exist: {out.parent}")
        doc, report = normalize(read_export(Path(args.export)))
        try:
            write_text_lf(out, json.dumps(doc, indent=1) + "\n")
        except OSError as exc:
            raise InputError(f"cannot write {out}: {exc}") from exc
    except WeaponsError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return exc.code or EXIT_BAD_INPUT
    print(json.dumps({"ok": True, **report}, indent=1))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
