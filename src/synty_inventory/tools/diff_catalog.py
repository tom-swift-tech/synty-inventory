"""Structural diff of two catalog sets, for the footprint pass (spec AC7 / INV-6).

The footprint pass is additive by contract: it may add ``footprint``,
``provenance.footprint`` and ``_auto.footprint`` to a record and touch
nothing else. Across 13,745 records that is not a claim you verify by
reading a git diff of a 39 MB JSON file -- you verify it by walking both
record sets key path by key path.

Reads the "before" side directly out of the operator's backup zip rather
than an extracted copy: an extracted working directory is one ``--rebuild``
away from being silently stale, and the archive streams fine.

Usage::

    python -m synty_inventory.tools.diff_catalog \\
        --before <backup>.zip \\
        --after  <catalogs dir>

Exit 0 when every delta is an allowed addition, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

DEFAULT_ALLOWED = ("footprint", "provenance.footprint", "_auto.footprint")

# The archive carries an older v1 snapshot alongside the current catalogs.
# Diffing against it would produce thousands of false deltas.
SKIP_ZIP_PARTS = ("_baseline_v1/",)
SKIP_STEMS = ("index", "search", "_measure_cache", "_footprint_cache")


def _is_catalog_name(name: str) -> bool:
    if not name.endswith(".json"):
        return False
    if any(part in name for part in SKIP_ZIP_PARTS):
        return False
    return Path(name).stem not in SKIP_STEMS


def load_side(path: Path) -> dict[str, dict]:
    """``{pack_id: catalog}`` from a directory or a zip of catalogs."""
    out: dict[str, dict] = {}
    if path.is_file() and path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not _is_catalog_name(name):
                    continue
                with z.open(name) as fh:
                    doc = json.load(fh)
                if isinstance(doc, dict) and doc.get("pack_id"):
                    out[doc["pack_id"]] = doc
        return out
    for f in sorted(path.glob("*.json")):
        if f.stem in SKIP_STEMS:
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("pack_id"):
            out[doc["pack_id"]] = doc
    return out


def walk(node: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every leaf key path in a record. Lists compare whole -- a reordered
    list is a change, which is what we want here."""
    if isinstance(node, dict):
        if not node:
            yield prefix, {}
            return
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                yield from walk(value, path)
            else:
                yield path, value
    else:
        yield prefix, node


def diff_asset(before: dict, after: dict) -> list[dict]:
    a = dict(walk(before))
    b = dict(walk(after))
    deltas: list[dict] = []
    for key in sorted(set(a) | set(b)):
        if key not in b:
            deltas.append({"path": key, "kind": "removed", "before": a[key]})
        elif key not in a:
            deltas.append({"path": key, "kind": "added"})
        elif a[key] != b[key]:
            deltas.append({"path": key, "kind": "changed", "before": a[key], "after": b[key]})
    return deltas


def _allowed(path: str, allowed: tuple[str, ...]) -> bool:
    return any(path == a or path.startswith(a + ".") for a in allowed)


def diff_catalogs(
    before: dict[str, dict],
    after: dict[str, dict],
    allowed: tuple[str, ...] = DEFAULT_ALLOWED,
) -> dict:
    """Compare two catalog sets. Only *additions* under ``allowed`` paths are
    permitted; a change or a removal there is still a violation."""
    report: dict = {
        "packs": [],
        "records": 0,
        "allowed_additions": 0,
        "violations": [],
        "packs_only_before": sorted(set(before) - set(after)),
        "packs_only_after": sorted(set(after) - set(before)),
    }
    for pack in sorted(set(before) & set(after)):
        b_assets = {a["id"]: a for a in before[pack].get("assets") or [] if isinstance(a, dict)}
        a_assets = {a["id"]: a for a in after[pack].get("assets") or [] if isinstance(a, dict)}
        pack_row = {
            "pack_id": pack,
            "records": len(b_assets),
            "allowed_additions": 0,
            "violations": 0,
            "ids_only_before": sorted(set(b_assets) - set(a_assets)),
            "ids_only_after": sorted(set(a_assets) - set(b_assets)),
        }
        for aid in sorted(set(b_assets) & set(a_assets)):
            for delta in diff_asset(b_assets[aid], a_assets[aid]):
                if delta["kind"] == "added" and _allowed(delta["path"], allowed):
                    pack_row["allowed_additions"] += 1
                else:
                    pack_row["violations"] += 1
                    if len(report["violations"]) < 50:
                        report["violations"].append({"pack": pack, "id": aid, **delta})
        report["records"] += pack_row["records"]
        report["allowed_additions"] += pack_row["allowed_additions"]
        report["packs"].append(pack_row)
    report["ok"] = (
        not report["violations"]
        and not report["packs_only_before"]
        and not report["packs_only_after"]
        and not any(p["ids_only_before"] or p["ids_only_after"] for p in report["packs"])
    )
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Structural diff of two catalog sets (AC7).")
    p.add_argument("--before", required=True, help="catalogs dir or backup .zip")
    p.add_argument("--after", required=True, help="catalogs dir or backup .zip")
    p.add_argument(
        "--allow-added",
        default=",".join(DEFAULT_ALLOWED),
        help="comma list of key paths that may be ADDED (default: the footprint pass's three)",
    )
    p.add_argument("--report", default=None, help="also write the JSON report here")
    args = p.parse_args(argv)

    allowed = tuple(x.strip() for x in args.allow_added.split(",") if x.strip())
    report = diff_catalogs(load_side(Path(args.before)), load_side(Path(args.after)), allowed)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        dest = Path(args.report)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
