"""``weapons review``: the static review page (spec 3.9).

``write_review_page`` renders ``review_template.html`` around server-side rendered tiles, so the page is readable
without JavaScript and every tile is a plain element a test can count. The inline script only adds the correction
panel; it holds its state in a guarded ``localStorage``, makes no request of any kind and writes nothing (the
reviewer downloads or copies a ``weapon-corrections/1`` file and runs ``weapons apply-corrections`` on it).

Section placement (a record is on exactly one tile, so the placement is a precedence, not a filter):
confidence < 0.6 -> **Low confidence**; else role ``part`` / ``ammo`` / ``carrier`` -> **Parts** / **Ammo** /
**Carriers** (an arrow or a holster is not an unclassified weapon, whatever its archetype); else archetype
``unknown`` (whole or emplaced weapons only) -> **Unknown**; else its archetype's section. The section order is Low
confidence, Unknown, the archetype sections (alphabetical), Parts, Ammo, Carriers, Excluded.
Rejected candidates from ``excluded.json`` form the last section so a false rejection can be restored.
"""

from __future__ import annotations

import html
import json
import os
import re
from bisect import bisect_left
from pathlib import Path
from urllib.parse import quote

from . import (
    AMMO_PROJECTILES,
    ARCHETYPES,
    CARRIER_KINDS,
    EXIT_OK,
    GENRES,
    HOLD_CLASSES,
    KINDS,
    ROLES,
    InputError,
    write_text_lf,
)
from .classify import family_of
from .cli import _catalogs, _csv, _emit, _guarded
from .corrections import apply_corrections  # noqa: F401  (spec 3.3 lists it in this module's surface)

ROLE_SECTIONS = (("part", "Parts"), ("ammo", "Ammo"), ("carrier", "Carriers"))  # role -> section title
LOW_CONFIDENCE = 0.6  # review.confidence below this lands in the Low confidence section (spec 3.9)
FAMILY_COLLAPSE_OVER = 12  # a family with more members than this in one section collapses to one tile
TEMPLATE = Path(__file__).with_name("review_template.html")


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def _glob_literal(text: str) -> str:
    """Escape fnmatch metacharacters so an asset-id prefix can sit in a glob verbatim."""
    return re.sub(r"([*?\[])", r"[\1]", text)


def _family_globs(directory: dict, excluded: dict | None) -> dict[tuple[str, str], tuple[str, int]]:
    """(pack, family) -> (glob, ids it matches) for every record family.

    The glob is the longest common prefix of the family's asset ids, cut back to a ``_`` boundary (a one-member
    family drops its numbering suffix), then ``*``. It always matches every member of the family; the count says
    how many ids of the pack it matches in all, so a reviewer sees an over-wide glob before emitting it.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for w in directory["weapons"]:
        groups.setdefault((w["pack"], w["family"]), []).append(w["asset_id"])
    pack_ids: dict[str, list[str]] = {}
    for w in directory["weapons"]:
        pack_ids.setdefault(w["pack"], []).append(w["asset_id"])
    for row in (excluded or {}).get("excluded", []):
        pack, _, aid = row["id"].partition("/")
        pack_ids.setdefault(pack, []).append(aid)
    for ids in pack_ids.values():
        ids.sort()
    out: dict[tuple[str, str], tuple[str, int]] = {}
    for (pack, family), aids in groups.items():
        if len(set(aids)) > 1:
            prefix = os.path.commonprefix(aids)
            cut = prefix.rfind("_")
            prefix = prefix[: cut + 1] if cut >= 0 else ""
        else:
            prefix = re.sub(r"\d+$", "", aids[0])
            prefix = prefix if prefix != aids[0] else ""
        if not prefix:
            continue
        ids = pack_ids[pack]
        lo = bisect_left(ids, prefix)
        n = 0
        while lo + n < len(ids) and ids[lo + n].startswith(prefix):
            n += 1
        out[(pack, family)] = (f"{pack}/{_glob_literal(prefix)}*", n)
    return out


def _thumb_src(rec: dict, base_dir: Path, out_dir: Path) -> str | None:
    """Relative URL of the 64 px thumbnail when it exists on disk, else None (a text-only tile)."""
    thumb = (rec.get("visuals") or {}).get("thumb")
    if not thumb:
        return None
    path = base_dir / thumb
    if not path.is_file():
        return None
    try:
        rel = os.path.relpath(path, out_dir)
    except ValueError:  # another drive: no relative path exists, so no absolute one is emitted either
        return None
    return quote(Path(rel).as_posix(), safe="/@")


def _conf_class(conf: float) -> str:
    return "conf-low" if conf < LOW_CONFIDENCE else ("conf-mid" if conf < 0.8 else "conf-ok")


def _record_tile(rec: dict, idx: int, globs: dict, base_dir: Path, out_dir: Path) -> str:
    rv = rec["review"]
    glob, globn = globs.get((rec["pack"], rec["family"]), ("", 0))
    src = _thumb_src(rec, base_dir, out_dir)
    thumb = (f'<img class="thumb" src="{_e(src)}" width="64" height="64" alt="" loading="lazy">' if src
             else '<div class="thumb none">no icon</div>')
    flags = ", ".join(rec["flags"])
    attrs = {
        "id": f"t{idx}", "data-id": rec["id"], "data-pack": rec["pack"], "data-family": rec["family"],
        "data-role": rec["role"], "data-kind": rec["kind"] or "", "data-archetype": rec["archetype"],
        "data-hold_class": rec["hold_class"], "data-genre": rec["genre"], "data-status": rv["status"],
        "data-conf": f"{rv['confidence']:.2f}", "data-reasons": ", ".join(rv["reasons"]), "data-glob": glob,
        "data-globn": str(globn),
    }
    attr_text = " ".join(f'{k}="{_e(v)}"' for k, v in attrs.items())
    return (
        f'<article class="tile" role="button" tabindex="0" {attr_text}>{thumb}<div class="meta">'
        f'<div class="id">{_e(rec["id"])}</div><div class="line">'
        f'<span class="tag role">{_e(rec["role"])}</span><span class="tag arch">{_e(rec["archetype"])}</span>'
        f'<span class="tag">{_e(rec["genre"])}</span>'
        f'<span class="tag {_conf_class(rv["confidence"])}">{rv["confidence"]:.2f}</span>'
        f'<span class="tag status-{_e(rv["status"])}">{_e(rv["status"])}</span></div>'
        f'<div class="flags">{_e(flags) if flags else "&nbsp;"}</div></div></article>'
    )


def _excluded_tile(row: dict, idx: int) -> str:
    attrs = {
        "id": f"t{idx}", "data-id": row["id"], "data-pack": row["id"].split("/", 1)[0], "data-excluded": "1",
        "data-reason": row["reason"], "data-matched": row["matched"], "data-source": row["source"],
        "data-glob": "", "data-globn": "0",
    }
    attr_text = " ".join(f'{k}="{_e(v)}"' for k, v in attrs.items())
    return (
        f'<article class="tile excluded" role="button" tabindex="0" {attr_text}>'
        f'<div class="thumb none">excluded</div><div class="meta"><div class="id">{_e(row["id"])}</div>'
        f'<div class="line"><span class="tag reason">{_e(row["reason"])}</span>'
        f'<span class="tag">{_e(row["source"])}</span></div>'
        f'<div class="flags">{_e(row["matched"])}</div></div></article>'
    )


def _grid(items: list[tuple[tuple[str, str], str, str]]) -> str:
    """``items`` = [(group key, group label, tile html)] already sorted; collapse runs over the limit."""
    out: list[str] = []
    i = 0
    while i < len(items):
        j = i
        while j < len(items) and items[j][0] == items[i][0]:
            j += 1
        run = items[i:j]
        if len(run) > FAMILY_COLLAPSE_OVER:
            out.append(
                f'<details class="family" data-family="{_e(run[0][0][1])}"><summary class="family-tile">'
                f'<span class="id">{_e(run[0][1])}</span><span class="count">&times;{len(run)}</span>'
                f'<span class="sub">tap to expand</span></summary><div class="grid">'
                + "".join(t for _, _, t in run) + "</div></details>")
        else:
            out.extend(t for _, _, t in run)
        i = j
    return '<div class="grid">' + "".join(out) + "</div>"


def _section(sec_id: str, title: str, note: str, count: int, body: str) -> str:
    inner = body if count else '<p class="empty">Nothing here.</p>'
    return (f'<section class="sec" id="{_e(sec_id)}" data-section="{_e(sec_id)}"><h2>{_e(title)} '
            f'<span class="n">{_e(note)} - {count}</span></h2>{inner}</section>')


def write_review_page(
    directory: dict, out_dir: Path, *, only_unreviewed: bool = False, max_confidence: float | None = None,
    excluded: dict | None = None, packs: set[str] | None = None, base_dir: Path | None = None,
    rules: dict | None = None,
) -> Path:
    """Write ``<out_dir>/index.html`` and return its path.

    ``excluded`` is the ``excluded.json`` document (the Excluded section), ``packs`` restricts both sections to
    those packs, ``base_dir`` is the folder ``visuals.thumb`` is relative to (the directory file's folder; default
    ``out_dir.parent``), ``rules`` feeds the family grouping of excluded rows (default: the packaged rules).
    ``only_unreviewed`` keeps status ``auto`` records and ``max_confidence`` keeps records at or below it; both
    filter records only, never the excluded rows.
    """
    out_dir = Path(out_dir)
    base_dir = Path(base_dir) if base_dir is not None else out_dir.parent
    if rules is None:
        from .rules import load_rules

        rules = load_rules()
    globs = _family_globs(directory, excluded)

    records = [
        w for w in directory["weapons"]
        if (not packs or w["pack"] in packs)
        and (not only_unreviewed or w["review"]["status"] == "auto")
        and (max_confidence is None or w["review"]["confidence"] <= max_confidence)
    ]
    records.sort(key=lambda w: (w["genre"], w["family"], w["id"]))
    role_titles = dict(ROLE_SECTIONS)
    buckets: dict[str, list[dict]] = {"low": [], "unknown": []}
    by_role: dict[str, list[dict]] = {role: [] for role in role_titles}
    for w in records:
        if w["review"]["confidence"] < LOW_CONFIDENCE:
            buckets["low"].append(w)
        elif w["role"] in by_role:
            by_role[w["role"]].append(w)
        elif w["archetype"] == "unknown":
            buckets["unknown"].append(w)
        else:
            buckets.setdefault(w["archetype"], []).append(w)

    counter = iter(range(1, 10**9))

    def record_section(sec_id: str, title: str, note: str, recs: list[dict]) -> str:
        items = [((w["genre"], w["family"]), f'{w["family"]} ({w["genre"]})',
                  _record_tile(w, next(counter), globs, base_dir, out_dir)) for w in recs]
        return _section(sec_id, title, note, len(recs), _grid(items))

    sections = [
        ("sec-low", "Low confidence", "confidence below 0.6", record_section(
            "sec-low", "Low confidence", "confidence below 0.6", buckets["low"]), len(buckets["low"])),
        ("sec-unknown", "Unknown", "whole weapons, archetype unknown", record_section(
            "sec-unknown", "Unknown", "whole weapons, archetype unknown", buckets["unknown"]), len(buckets["unknown"])),
    ]
    for arch in sorted(a for a in buckets if a not in ("low", "unknown")):
        sid = f"sec-archetype-{arch}"
        sections.append((sid, arch, "archetype", record_section(sid, arch, "archetype", buckets[arch]),
                         len(buckets[arch])))

    for role, title in ROLE_SECTIONS:
        sid = f"sec-role-{role}"
        sections.append((sid, title, f"role {role}", record_section(sid, title, f"role {role}", by_role[role]),
                         len(by_role[role])))

    rows = [r for r in (excluded or {}).get("excluded", []) if not packs or r["id"].split("/", 1)[0] in packs]
    keyed = sorted(((r["reason"], family_of(r["id"].split("/", 1)[1], rules), r["id"], r) for r in rows),
                   key=lambda k: k[:3])
    items = [((reason, fam), f"{fam} ({reason})", _excluded_tile(r, next(counter))) for reason, fam, _, r in keyed]
    sections.append(("sec-excluded", "Excluded", "rejected candidates, restore false rejections",
                     _section("sec-excluded", "Excluded", "rejected candidates, restore false rejections",
                              len(rows), _grid(items)), len(rows)))

    nav = "".join(
        '<a href="#{}"{}>{} ({})</a>'.format(_e(sid), "" if n else ' class="zero"', _e(title), n)
        for sid, title, _, _, n in sections
    )
    low = len(buckets["low"])
    summary = f"{len(records)} records, {low} below 0.6, {len(rows)} excluded"
    if only_unreviewed or max_confidence is not None or packs:
        bits = []
        if only_unreviewed:
            bits.append("unreviewed only")
        if max_confidence is not None:
            bits.append(f"confidence <= {max_confidence:g}")
        if packs:
            bits.append(f"{len(packs)} pack(s)")
        summary += " (" + ", ".join(bits) + ")"
    enums = {
        "role": list(ROLES), "kind": list(KINDS), "archetype": list(ARCHETYPES), "hold_class": list(HOLD_CLASSES),
        "genre": list(GENRES), "carrier": list(CARRIER_KINDS), "ammo": list(AMMO_PROJECTILES),
    }
    page = TEMPLATE.read_text(encoding="utf-8")
    # </ would end the script element early; the escaped form is the same JSON string
    enums_json = json.dumps(enums, sort_keys=True).replace("</", "<\\/")
    for token, value in (("@@STATE_KEY@@", _e(directory["overrides_digest"])), ("@@SUMMARY@@", _e(summary)),
                         ("@@NAV@@", nav), ("@@SECTIONS@@", "\n".join(s[3] for s in sections)),
                         ("@@ENUMS@@", enums_json)):
        page = page.replace(token, value)
    dest = out_dir / "index.html"
    write_text_lf(dest, page)
    return dest


@_guarded
def cmd(args, cfg) -> int:
    from .directory import EXCLUDED_NAME, load_directory, read_json, weapons_dir

    catalogs_dir = _catalogs(args, cfg)
    wdir = weapons_dir(catalogs_dir)
    directory = load_directory(catalogs_dir)
    excluded = read_json(wdir / EXCLUDED_NAME) if (wdir / EXCLUDED_NAME).is_file() else None
    packs = set(_csv(args.pack) or [])
    unknown = sorted(packs - {p["pack"] for p in directory["packs"]})
    if unknown:
        raise InputError(f"unknown pack(s) in the directory: {', '.join(unknown)}")
    out_dir = Path(args.review_out) if args.review_out else wdir / "review"
    dest = write_review_page(directory, out_dir, only_unreviewed=args.only_unreviewed,
                             max_confidence=args.max_confidence, excluded=excluded, packs=packs or None,
                             base_dir=wdir)
    _emit({"ok": True, "page": dest.as_posix(), "records": len(directory["weapons"]),
           "excluded": len((excluded or {}).get("excluded", []))})
    return EXIT_OK
