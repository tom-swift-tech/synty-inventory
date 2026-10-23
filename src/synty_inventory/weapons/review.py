"""``weapons review``: the static review page (spec 3.9).

``write_review_page`` renders ``review_template.html`` around server-side rendered tiles, so the page is readable
without JavaScript and every tile is a plain element a test can count. The inline script only adds the correction
panel; it holds its state in a guarded ``localStorage``, makes no request of any kind and writes nothing (the
reviewer downloads or copies a ``weapon-corrections/1`` file and runs ``weapons apply-corrections`` on it).

Section placement (a record is on exactly one tile, so the placement is a precedence, not a filter):
a part with an ``attachment`` block -> **Attachments** (W8d; whatever its confidence, because that section is where its
forward flip, host checklist and reasons live: spec 6.2 "an attachment appears there and not in Parts"); else
confidence < 0.6 -> **Low confidence**; else role ``part`` / ``ammo`` / ``carrier`` -> **Parts** / **Ammo** /
**Carriers** (an arrow or a holster is not an unclassified weapon, whatever its archetype); else archetype
``unknown`` (whole or emplaced weapons only) -> **Unknown**; else its archetype's section. The section order is Low
confidence, Unknown, the archetype sections (alphabetical), Attachments, Parts, Ammo, Carriers, Excluded.
Rejected candidates from ``excluded.json`` form the last section so a false rejection can be restored.

W8d adds the attachment workspace (docs/weapon_attachments.md 6.2). The Attachments section is grouped by slot, then
family. An attachment tile shows its slot and kind, its host count by tier and its review reasons; its panel has the
slot / kind dropdowns, a forward flip, the host checklist (inferred / added / removed per host, tier and score, a "no
mount" dimmed row for ``pending_hosts``), the family glob and a note. A host tile with mounts opens a Mounts table (one
row per slot). The data those panels need is embedded once as ``<script type="application/json" id="attach-data">``;
the script turns checklist, flip and mount choices into ``weapon-corrections/1`` entries (``set.attachment_slot`` /
``attachment_kind``, ``compatible {add, remove}``, ``mounts``, ``forward``). "Label mode" records fits / does-not-fit per
pair as ``weapon-attach-labels/1`` (consumed by ``weapons attach-eval``). The placement previews that
``weapons attach-preview`` wrote (``<previews dir>/index.json`` plus PNGs) are embedded when the files exist.
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
    ATTACH_KINDS,
    ATTACH_SLOTS,
    CARRIER_KINDS,
    COMPAT_TIERS,
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
from .preview import DEFAULT_DIRNAME as PREVIEW_DIRNAME
from .preview import INDEX_NAME as PREVIEW_INDEX  # `weapons attach-preview` writes this beside its PNGs
from .preview import PREVIEW_SCHEMA

ROLE_SECTIONS = (("part", "Parts"), ("ammo", "Ammo"), ("carrier", "Carriers"))  # role -> section title
LOW_CONFIDENCE = 0.6  # review.confidence below this lands in the Low confidence section (spec 3.9)
FAMILY_COLLAPSE_OVER = 12  # a (pack, family) with more members than this in one section collapses to one tile
TEMPLATE = Path(__file__).with_name("review_template.html")
ATTACH_DATA_SCHEMA = "weapon-attach-review/1"  # the embedded data block
PREVIEWS_PER_TILE = 3  # server-rendered preview thumbnails on one attachment tile (twins first)


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


def _fam_label(n: int) -> str:
    """The text of the "Apply to family" checkbox: N is what the written glob really matches (AC36)."""
    return f"Apply to family ({n} {'id' if n == 1 else 'ids'})"


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


def _axis_of(vec) -> str | None:
    """The signed axis (``+x`` .. ``-z``) a unit vector lies along, or None when it is not axis aligned."""
    for i, name in enumerate("xyz"):
        if abs(abs(vec[i]) - 1.0) <= 1e-3 and all(abs(vec[j]) <= 1e-3 for j in range(3) if j != i):
            return ("+" if vec[i] > 0 else "-") + name
    return None


def _flip_of(att: dict) -> tuple[str, str] | None:
    """``(measured, flipped)`` signed axes of the direction the ``forward`` override decides, or None (unmeasured anchor).

    ``attach.measure_anchor`` applies an override only when it names the measured axis (docs 3.4.3): that axis is the
    anchor's ``forward`` for foot slots and the bore axis (the anchor's ``up``) for a muzzle device, so the flip is the
    same axis with the opposite sign.
    """
    anchor = att.get("anchor")
    if not anchor:
        return None
    now = _axis_of(anchor["up"] if att["slot"] == "muzzle" else anchor["forward"])
    if now is None:
        return None
    return now, ("-" if now[0] == "+" else "+") + now[1]


def load_previews(previews_dir, out_dir: Path) -> dict[tuple[str, str], dict]:
    """``{(part id, host id): {src, twin}}`` of the placement previews whose PNG exists, ``src`` relative to ``out_dir``.

    ``previews_dir/index.json`` is the ``weapon-attach-preview/1`` file ``weapons attach-preview`` writes. A missing or
    unreadable index, a pair whose file is gone and a name that climbs out of the folder are skipped: the page then simply
    has no preview for that pair (never an error, and never a path outside the folder).
    """
    if previews_dir is None:
        return {}
    previews_dir = Path(previews_dir)
    index = previews_dir / PREVIEW_INDEX
    if not index.is_file():
        return {}
    try:
        doc = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict) or doc.get("schema") != PREVIEW_SCHEMA or not isinstance(doc.get("pairs"), list):
        return {}
    out: dict[tuple[str, str], dict] = {}
    for pair in doc["pairs"]:
        if not isinstance(pair, dict):
            continue
        part, host, name = pair.get("part"), pair.get("host"), pair.get("file")
        if not all(isinstance(x, str) and x for x in (part, host, name)) or Path(name).name != name:
            continue
        path = previews_dir / name
        if not path.is_file():
            continue
        try:
            rel = os.path.relpath(path, out_dir)
        except ValueError:  # another drive: no relative path exists
            continue
        out[(part, host)] = {"src": quote(Path(rel).as_posix(), safe="/@"), "twin": pair.get("tier") == "twin"}
    return out


def _tier_chips(att: dict) -> list[str]:
    counts: dict[str, int] = {}
    for e in att["compatible_hosts"]:
        counts[e["tier"]] = counts.get(e["tier"], 0) + 1
    chips = [f"{t} {counts[t]}" for t in COMPAT_TIERS if t in counts]
    if att["pending_hosts"]:
        chips.append(f"no mount {len(att['pending_hosts'])}")
    return chips or ["no hosts"]


def _attach_entry(rec: dict, previews: dict) -> dict:
    """The embedded data of one attachment: slot, kind, the flip and every candidate host (compatible first, then pending)."""
    att = rec["attachment"]
    hosts = []
    for e in att["compatible_hosts"]:
        hosts.append({"host": e["host"], "tier": e["tier"], "score": e["score"], "pending": False})
    for e in att["pending_hosts"]:
        hosts.append({"host": e["host"], "tier": e["tier"], "score": None, "pending": True})
    for h in hosts:
        pv = previews.get((rec["id"], h["host"]))
        h["preview"] = pv["src"] if pv else None
    flip = _flip_of(att)
    return {"slot": att["slot"], "kind": att["kind"], "flip": {"from": flip[0], "to": flip[1]} if flip else None,
            "hosts": hosts}


def _host_entry(rec: dict, nodes: list[str] | None) -> dict:
    """The embedded Mounts table of a host: one row per slot, plus the child nodes a reviewer may pick."""
    mounts = rec["geometry"]["mounts"]
    rows = {}
    seen = set(nodes or [])
    for slot in ATTACH_SLOTS:
        m = mounts.get(slot)
        if m is None:
            continue
        rows[slot] = {"source": m["source"], "child": m.get("child_node"), "occupied_by": list(m.get("occupied_by") or []),
                      "confidence": m.get("confidence"), "reason": m.get("reason")}
        seen.update(m.get("occupied_by") or [])
        if m.get("child_node"):
            seen.add(m["child_node"])
    return {"mounts": rows, "nodes": sorted(seen)}


def _conf_class(conf: float) -> str:
    return "conf-low" if conf < LOW_CONFIDENCE else ("conf-mid" if conf < 0.8 else "conf-ok")


def _record_tile(rec: dict, idx: int, globs: dict, base_dir: Path, out_dir: Path, previews: dict | None = None) -> str:
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
        "data-globn": str(globn), "data-famlabel": _fam_label(globn),
    }
    chips = extra = ""
    mounts = (rec.get("geometry") or {}).get("mounts")
    if isinstance(mounts, dict):  # a host the Mounts table can open for; mount_missing feeds the "No mount" chip
        attrs["data-mounts"] = "1"
        if "mount_missing" in rv["reasons"]:
            attrs["data-nomount"] = "1"
    att = rec.get("attachment")
    if att:
        flip = _flip_of(att) or ("", "")
        attrs.update({"data-attach": "1", "data-slot": att["slot"], "data-akind": att["kind"],
                      "data-flipfrom": flip[0], "data-flipto": flip[1]})
        chips = (f'<span class="tag slot">{_e(att["slot"])}</span><span class="tag akind">{_e(att["kind"])}</span>'
                 + "".join(f'<span class="tag tier">{_e(c)}</span>' for c in _tier_chips(att)))
        shown = sorted(((h["host"], previews[(rec["id"], h["host"])]) for h in att["compatible_hosts"] + att["pending_hosts"]
                        if (rec["id"], h["host"]) in (previews or {})),
                       key=lambda hp: (not hp[1]["twin"], hp[0]))[:PREVIEWS_PER_TILE]
        pvs = "".join(f'<img class="pv" src="{_e(pv["src"])}" width="96" height="96" alt="" loading="lazy" '
                      f'title="{_e(host)}">' for host, pv in shown)
        extra = (f'<div class="reasons">{_e(", ".join(rv["reasons"])) if rv["reasons"] else "&nbsp;"}</div>'
                 + (f'<div class="pvs">{pvs}</div>' if pvs else ""))
    attr_text = " ".join(f'{k}="{_e(v)}"' for k, v in attrs.items())
    return (
        f'<article class="tile" role="button" tabindex="0" {attr_text}>{thumb}<div class="meta">'
        f'<div class="id">{_e(rec["id"])}</div><div class="line">'
        f'<span class="tag role">{_e(rec["role"])}</span><span class="tag arch">{_e(rec["archetype"])}</span>'
        f'<span class="tag">{_e(rec["genre"])}</span>'
        f'<span class="tag {_conf_class(rv["confidence"])}">{rv["confidence"]:.2f}</span>'
        f'<span class="tag status-{_e(rv["status"])}">{_e(rv["status"])}</span>{chips}</div>'
        f'<div class="flags">{_e(flags) if flags else "&nbsp;"}</div>{extra}</div></article>'
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


def _grid(items: list[tuple[tuple, str, str, tuple[str, int]]]) -> str:
    """``items`` = [(group key, group label, tile html, (family glob, ids it matches))] already sorted.

    A run of equal keys over the limit collapses to one tile. Its count is the records the tile holds (``k``); when
    the family glob matches more ids than that (members in another section, excluded rows) the tile reads
    "k of N", so the number on the tile and the "Apply to family (N ids)" scope never disagree (AC36).
    """
    out: list[str] = []
    i = 0
    while i < len(items):
        j = i
        while j < len(items) and items[j][0] == items[i][0]:
            j += 1
        run = items[i:j]
        if len(run) > FAMILY_COLLAPSE_OVER:
            glob, n = run[0][3]
            of = f'<span class="of">of {n}</span>' if n > len(run) else ""
            out.append(
                f'<details class="family" data-family="{_e(run[0][0][1])}" '
                f'data-count="{len(run)}" data-glob="{_e(glob)}" data-globn="{n}">'
                f'<summary class="family-tile"><span class="id">{_e(run[0][1])}</span>'
                f'<span class="count">&times;{len(run)}</span>{of}'
                f'<span class="sub">tap to expand</span></summary><div class="grid">'
                + "".join(t for _, _, t, _ in run) + "</div></details>")
        else:
            out.extend(t for _, _, t, _ in run)
        i = j
    return '<div class="grid">' + "".join(out) + "</div>"


def _section(sec_id: str, title: str, note: str, count: int, body: str) -> str:
    inner = body if count else '<p class="empty">Nothing here.</p>'
    return (f'<section class="sec" id="{_e(sec_id)}" data-section="{_e(sec_id)}"><h2>{_e(title)} '
            f'<span class="n">{_e(note)} - {count}</span></h2>{inner}</section>')


def write_review_page(
    directory: dict, out_dir: Path, *, only_unreviewed: bool = False, max_confidence: float | None = None,
    excluded: dict | None = None, packs: set[str] | None = None, base_dir: Path | None = None,
    rules: dict | None = None, previews_dir: Path | None = None, host_nodes: dict[str, list[str]] | None = None,
) -> Path:
    """Write ``<out_dir>/index.html`` and return its path.

    ``excluded`` is the ``excluded.json`` document (the Excluded section), ``packs`` restricts both sections to
    those packs, ``base_dir`` is the folder ``visuals.thumb`` is relative to (the directory file's folder; default
    ``out_dir.parent``), ``rules`` feeds the family grouping of excluded rows (default: the packaged rules).
    ``only_unreviewed`` keeps status ``auto`` records and ``max_confidence`` keeps records at or below it; both
    filter records only, never the excluded rows.

    ``previews_dir`` (W8d) is the folder ``weapons attach-preview`` wrote (its ``index.json`` and PNGs); the previews whose
    file exists are embedded. ``host_nodes`` maps a host id to the mesh node names of its GLB, for the Mounts table's
    dropdown (without it the table offers the nodes the directory already names, ``none`` and "unchanged").
    """
    out_dir = Path(out_dir)
    base_dir = Path(base_dir) if base_dir is not None else out_dir.parent
    if rules is None:
        from .rules import load_rules

        rules = load_rules()
    globs = _family_globs(directory, excluded)
    previews = load_previews(previews_dir, out_dir)

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
    attachments: list[dict] = []
    for w in records:
        if w["role"] == "part" and w.get("attachment"):
            attachments.append(w)
        elif w["review"]["confidence"] < LOW_CONFIDENCE:
            buckets["low"].append(w)
        elif w["role"] in by_role:
            by_role[w["role"]].append(w)
        elif w["archetype"] == "unknown":
            buckets["unknown"].append(w)
        else:
            buckets.setdefault(w["archetype"], []).append(w)

    counter = iter(range(1, 10**9))

    def record_section(sec_id: str, title: str, note: str, recs: list[dict]) -> str:
        # one tile per (pack, family): the family glob is per pack, so a collapse across packs would hide which ids
        # "Apply to family" touches. Sorting by (genre, family, id) keeps each pack's members adjacent (id = pack/...).
        items = [((w["pack"], w["family"], w["genre"]), f'{w["pack"]}/{w["family"]} ({w["genre"]})',
                  _record_tile(w, next(counter), globs, base_dir, out_dir, previews),
                  globs.get((w["pack"], w["family"]), ("", 0)))
                 for w in recs]
        return _section(sec_id, title, note, len(recs), _grid(items))

    def attachment_section() -> str:
        # grouped by slot (the spec's slot order, an unknown slot of a newer directory last), then by (pack, family)
        by_slot: dict[str, list[dict]] = {}
        for w in attachments:
            by_slot.setdefault(w["attachment"]["slot"], []).append(w)
        order = [s for s in ATTACH_SLOTS if s in by_slot] + sorted(s for s in by_slot if s not in ATTACH_SLOTS)
        body = []
        for slot in order:
            recs = sorted(by_slot[slot], key=lambda w: (w["pack"], w["family"], w["id"]))
            items = [((w["pack"], w["family"]), f'{w["pack"]}/{w["family"]} ({slot})',
                      _record_tile(w, next(counter), globs, base_dir, out_dir, previews),
                      globs.get((w["pack"], w["family"]), ("", 0))) for w in recs]
            body.append(f'<h3 class="slot" data-slot="{_e(slot)}">{_e(slot)} <span class="n">{len(recs)}</span></h3>'
                        + _grid(items))
        return _section("sec-attachments", "Attachments", "parts that mount on a weapon, by slot and family",
                        len(attachments), "".join(body))

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

    sections.append(("sec-attachments", "Attachments", "parts that mount on a weapon, by slot and family",
                     attachment_section(), len(attachments)))

    for role, title in ROLE_SECTIONS:
        sid = f"sec-role-{role}"
        sections.append((sid, title, f"role {role}", record_section(sid, title, f"role {role}", by_role[role]),
                         len(by_role[role])))

    rows = [r for r in (excluded or {}).get("excluded", []) if not packs or r["id"].split("/", 1)[0] in packs]
    keyed = sorted(((r["reason"], family_of(r["id"].split("/", 1)[1], rules), r["id"], r) for r in rows),
                   key=lambda k: k[:3])
    items = [((reason, fam), f"{fam} ({reason})", _excluded_tile(r, next(counter)), ("", 0))
             for reason, fam, _, r in keyed]
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
    attach_data = {
        "schema": ATTACH_DATA_SCHEMA, "slots": list(ATTACH_SLOTS), "kinds": {k: list(v) for k, v in ATTACH_KINDS.items()},
        "tiers": list(COMPAT_TIERS),
        "attachments": {w["id"]: _attach_entry(w, previews) for w in attachments},
        "hosts": {w["id"]: _host_entry(w, (host_nodes or {}).get(w["id"])) for w in records
                  if isinstance((w.get("geometry") or {}).get("mounts"), dict)},
    }
    nomount = sum(1 for w in records if isinstance((w.get("geometry") or {}).get("mounts"), dict)
                  and "mount_missing" in w["review"]["reasons"])
    page = TEMPLATE.read_text(encoding="utf-8")
    # </ would end the script element early; the escaped form is the same JSON string
    enums_json = json.dumps(enums, sort_keys=True).replace("</", "<\\/")
    attach_json = json.dumps(attach_data, sort_keys=True).replace("</", "<\\/")
    for token, value in (("@@STATE_KEY@@", _e(directory["overrides_digest"])), ("@@SUMMARY@@", _e(summary)),
                         ("@@NAV@@", nav), ("@@SECTIONS@@", "\n".join(s[3] for s in sections)),
                         ("@@ENUMS@@", enums_json), ("@@ATTACH@@", attach_json), ("@@NOMOUNT@@", str(nomount))):
        page = page.replace(token, value)
    dest = out_dir / "index.html"
    write_text_lf(dest, page)
    return dest


def _host_nodes(directory: dict, cfg) -> dict[str, list[str]]:
    """``{host id: sorted mesh node names}`` read from each mount-bearing host's GLB; ``{}`` when threejs_v2 is not
    configured. A GLB that is missing or unreadable just has no entry (the Mounts table then offers what the directory
    names). Read-only."""
    from ..cli import _threejs_v2
    from ..sources.glb_measure import read_glb_json
    from .mounts import mesh_nodes

    try:
        root = _threejs_v2(cfg)
    except Exception:  # noqa: BLE001 - an unconfigured or odd root only means "no node list"
        return {}
    if root is None:
        return {}
    out: dict[str, list[str]] = {}
    for w in directory["weapons"]:
        glb = (w.get("files") or {}).get("glb")
        if not glb or not isinstance((w.get("geometry") or {}).get("mounts"), dict):
            continue
        try:
            names = mesh_nodes(read_glb_json(Path(root) / glb), (w["files"].get("glb_node") or None))
        except Exception:  # noqa: BLE001
            continue
        if names:
            out[w["id"]] = sorted(names)
    return out


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
    previews_dir = getattr(args, "previews", None)
    if previews_dir is None:  # the folder `weapons attach-preview` writes by default: embedded when it is there
        previews_dir = wdir / PREVIEW_DIRNAME
    dest = write_review_page(directory, out_dir, only_unreviewed=args.only_unreviewed,
                             max_confidence=args.max_confidence, excluded=excluded, packs=packs or None,
                             base_dir=wdir, previews_dir=Path(previews_dir), host_nodes=_host_nodes(directory, cfg))
    _emit({"ok": True, "page": dest.as_posix(), "records": len(directory["weapons"]),
           "excluded": len((excluded or {}).get("excluded", []))})
    return EXIT_OK
