"""``build_directory``: the weapon directory from the per-pack catalogs (spec 3.1, 3.3, 4.2, 4.3).

Pure given its inputs: no clock, no network, no randomness (INV-4). Catalogs are only read (INV-5); the single
write path is ``write_directory``, which touches nothing but ``<catalogs>/weapons/``. A record is measured when
``measure`` is on, ``threejs_v2_dir`` is given and its ``files.glb`` decodes; otherwise it keeps the unmeasured stub
(``geometry: null``, flag ``unmeasured``, reason ``no_geometry``). Hints are derived for every record regardless.
The geometry cache is a plain dict the caller owns and persists (``geometry.load_cache`` / ``save_cache``), so
this module stays free of file writes outside ``write_directory``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path

from .. import weapons as _pkg  # read versions at call time (a test may bump WEAPON_VERSION)
from ..paths import is_pack_catalog_file
from ..schema import migrate_catalog
from . import InputError, SchemaError, digest, to_text, write_text_lf
from .candidates import evaluate_candidate
from .classify import classify, classify_attachment, tokenize_id
from .geometry import measure_cached, pass2_inputs
from .hints import build_group_stats, derive_hints
from .overrides import effective_override, load_overrides
from .rules import attach_rules_digest, head_lead_tokens, load_rules, weapon_rules_digest
from .schema import validate_directory
from .variants import discover_variants, has_colourway_info, variant_link_paths

DIRECTORY_NAME = "directory.json"
EXCLUDED_NAME = "excluded.json"
ICONS_DIRNAME = "icons"  # the folder weapons/icons.py fills; the carried-over variant links are checked against it


def weapons_dir(catalogs_dir: Path) -> Path:
    return catalogs_dir / "weapons"


def load_pack_catalogs(catalogs_dir: Path) -> dict[str, dict]:
    """pack_id -> catalog doc for every top-level pack catalog (``weapons/`` and sidecars are invisible)."""
    if not catalogs_dir.is_dir():
        raise InputError(f"catalogs directory not found: {catalogs_dir}")
    docs: dict[str, dict] = {}
    for path in sorted(catalogs_dir.glob("*.json")):
        if not is_pack_catalog_file(path):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"catalog unreadable: {path.name}: {exc}") from exc
        if not isinstance(raw, dict) or not raw.get("pack_id") or not isinstance(raw.get("assets"), list):
            continue  # a sidecar that is not a pack catalog
        doc = migrate_catalog(raw)
        if doc["pack_id"] in docs:
            raise InputError(f"two catalog files declare pack_id {doc['pack_id']}")
        docs[doc["pack_id"]] = doc
    return docs


def _pack_tree(doc: dict, pack_id: str, extracted_root: Path | None) -> Path | None:
    """The extracted Unity tree of one pack (the folder holding ``Assets/Synty/...``), or None.

    With ``extracted_root`` (the configured folder with one sub-folder per pack) the tree is
    ``<extracted_root>/<pack_id>`` or nothing. Without it the catalog's own ``source.extracted`` (where the scan
    read the pack from) is tried, so a plain ``weapons build`` finds the tree without extra wiring. Neither is ever
    written into the directory; a missing tree just means no variants are listed.
    """
    if extracted_root is not None:
        tree = Path(extracted_root) / pack_id
    else:
        src = (doc.get("source") or {}).get("extracted")
        tree = Path(src) if isinstance(src, str) and src else None
    return tree if tree is not None and tree.is_dir() else None


def _pack_settings(pack_settings: dict | None) -> dict:
    if pack_settings is not None:
        return pack_settings
    from ..packs.profile import load_settings_table

    return load_settings_table()


def _record(asset: dict, pack_id: str, cls: dict, source: str, renamed_from: list[str]) -> dict:
    files = deepcopy(asset.get("files") or {})
    files.setdefault("glb_node", None)
    flags = sorted(set(cls["flags"]) | {"unmeasured"})
    reasons = sorted(set(cls["reasons"]) | {"no_geometry"})
    return {
        "schema_version": 1,
        "id": f"{pack_id}/{asset['id']}",
        "pack": pack_id,
        "asset_id": asset["id"],
        "files": files,
        "renamed_from": sorted(set(renamed_from)),
        "family": cls["family"],
        "role": cls["role"],
        "kind": cls["kind"],
        "genre": cls["genre"],
        "genre_source": cls["genre_source"],
        "archetype": cls["archetype"],
        "hold_class": cls["hold_class"],
        "component": cls["component"],
        "carrier": cls["carrier"],
        "ammo": cls["ammo"],
        "flags": flags,
        "duplicate_of": None,
        "geometry": None,
        "hints": {"size_class": None, "size_basis": None, "inventory_cells": None, "weight_class": None,
                  "quality_tier": None, "ammo_family": None},
        "visuals": {"icon": None, "thumb": None, "icon_input_sha": None, "variants": []},
        "review": {
            "status": cls["status"],
            "confidence": cls["confidence"],
            "reasons": reasons,
            "matched_rule": cls["matched_rule"],
            "candidate_source": source,
        },
        "provenance": dict(cls["provenance"]),
    }


def _attach_class(asset: dict, pack_id: str, cls: dict, rules: dict) -> dict | None:
    """The attachment {slot, kind, rule} of the final classification of a part, or None (docs/weapon_attachments.md 3.3)."""
    return classify_attachment(asset["id"], pack_id, cls["role"], cls["component"], rules)


def _attachment_block(attach_class: dict | None, detail: dict | None) -> dict | None:
    """The record's ``attachment`` block. ``anchor`` and ``footprint`` are null together: with no measurement at all
    (no geometry) and when the foot cannot be measured (the latter adds the review reason ``anchor_unmeasured``)."""
    if attach_class is None:
        return None
    got = (detail or {}).get("attach") or {}
    return {
        "slot": attach_class["slot"], "kind": attach_class["kind"],
        "anchor": got.get("anchor"), "footprint": got.get("footprint"),
        "compatible_hosts": [], "pending_hosts": [],
    }


def _apply_attachment(rec: dict, block: dict | None, detail: dict | None) -> None:
    """Attach the block to a part record and fold the anchor's consequences into its review (spec 3.4 step 6).

    Only a record whose mesh decoded is judged: a null anchor multiplies the confidence by 0.9, a symmetric (coin-flip)
    forward caps it at 0.59, so both land on the review page. A record without geometry already carries ``no_geometry``.
    """
    if rec["role"] != "part":
        return
    rec["attachment"] = block
    got = (detail or {}).get("attach")
    if block is None or got is None:
        return
    review = rec["review"]
    review["reasons"] = sorted(set(review["reasons"]) | set(got["reasons"]))
    conf = review["confidence"]
    if block["anchor"] is None:
        conf *= 0.9
    elif block["anchor"]["symmetric"]:
        conf = min(conf, 0.59)
    review["confidence"] = round(conf, 2)
    if review["confidence"] < 0.6:
        review["reasons"] = sorted(set(review["reasons"]) | {"low_confidence"})


def _context(cls: dict) -> tuple:
    """The classification fields a measurement depends on (spec 3.5: archetype, kind, role, hold)."""
    return cls["archetype"], cls["kind"], cls["role"], cls["hold_class"]


def _measure_record(asset, pack_id, cls, source, rules, overrides, setting, threejs_v2_dir, cache, stats,
                    forward_override=None):
    """Measure one record's GLB, then re-classify with the measured length (pass 2).

    Pass 2 can change archetype/hold (a length rule filling an unknown archetype, the long-blade exception); the
    measurement depends on both, so a changed context is measured once more (the decode is memoised, so this
    costs no second read). ``forward_override`` is the id override's ``forward`` (spec 4.5), passed to every
    measurement, and so is ``head_lead`` (W7 R-H2: one of the id's tokens is in ``rules.head_lead_tokens``; the id decides
    it, so it does not change between the pass-1 and pass-2 classifications). Returns ``(final classification, last measurement detail)``.

    W7b: a whole/emplaced record whose rules leave ``kind`` null starts as ``melee`` (``kind_guessed``, unmeasured
    fallback), is measured as such, and pass 2 then takes ``ranged`` when the measured long axis is ``z``. ``kind`` is part
    of ``_context``, so that change is measured once more with the final kind (a ranged record gets a muzzle and no tip).
    The loop cannot oscillate: the long axis depends on the kind only through the tie-break default of
    ``geometry._pick_long_axis`` (``y`` for melee/thrown, ``z`` otherwise), which applies among axes within the tie
    tolerance of the longest. A first axis ``z`` was either the default or the strict longest, so the ranged re-measure
    picks ``z`` again; a first axis that is not ``z`` means ``z`` was outside the tolerance, so the melee kind keeps it
    outside. Either way the second classification repeats the first kind.
    """
    files = asset.get("files") or {}
    node = files.get("glb_node") or None
    scale = float(files.get("glb_scale") or 1.0)
    detail = None
    head_lead = bool(head_lead_tokens(rules) & set(tokenize_id(asset["id"], rules)))
    for _ in range(3):
        attach = _attach_class(asset, pack_id, cls, rules)
        detail, cached = measure_cached(
            threejs_v2_dir, files["glb"], node, scale, cls["archetype"], cls["kind"], cls["role"], rules, cache,
            hold_class=cls["hold_class"], genre=cls["genre"], forward_override=forward_override,
            head_lead=head_lead, attach_slot=attach["slot"] if attach else None,
        )
        stats["cached" if cached else "decoded"] += 1
        measured = pass2_inputs(detail)
        if measured is None:
            break
        refined = classify(asset, pack_id, rules, overrides, setting, candidate_source=source, measured=measured)
        stable = _context(refined) == _context(cls)
        cls = refined
        if stable:
            break
    return cls, detail


def _apply_measurement(rec: dict, detail: dict) -> None:
    """Merge a measurement into the unmeasured stub record: geometry, flags, reasons, provenance."""
    if detail["geometry"] is None:
        rec["review"]["reasons"] = sorted(set(rec["review"]["reasons"]) | set(detail["reasons"]))
        return
    rec["geometry"] = detail["geometry"]
    rec["flags"] = sorted((set(rec["flags"]) - {"unmeasured"}) | set(detail["flags"]))
    rec["review"]["reasons"] = sorted((set(rec["review"]["reasons"]) - {"no_geometry"}) | set(detail["reasons"]))
    rec["provenance"]["geometry"] = "measured"


def _mark_duplicates(records: list[dict]) -> None:
    """duplicate_of = id of the first record (by id) sharing the same GLB file and node selection."""
    for rec in records:  # reset, so carried-over records from a partial build are recomputed on the union
        rec["duplicate_of"] = None
        rec["flags"] = [f for f in rec["flags"] if f != "duplicate_mesh"]
    owner: dict[str, str] = {}
    for rec in sorted(records, key=lambda r: r["id"]):
        glb = rec["files"].get("glb")
        if not glb:
            continue
        key = json.dumps([glb, rec["files"].get("glb_node")], sort_keys=True)
        if key in owner:
            rec["duplicate_of"] = owner[key]
            rec["flags"] = sorted(set(rec["flags"]) | {"duplicate_mesh"})
        else:
            owner[key] = rec["id"]


def _check_renames(records: list[dict]) -> None:
    """INV-13: a renamed id is never a live record id and is claimed by at most one record (exit 6)."""
    live = {r["id"] for r in records}
    claimed: dict[str, str] = {}
    for rec in sorted(records, key=lambda r: r["id"]):
        for old in rec["renamed_from"]:
            if old in live:
                raise SchemaError(f"renamed_from {old!r} (claimed by {rec['id']}) equals a live record id")
            if old in claimed:
                raise SchemaError(f"renamed_from {old!r} is claimed by both {claimed[old]} and {rec['id']}")
            claimed[old] = rec["id"]


def _counts(records: list[dict]) -> dict:
    def tally(values):
        out: dict[str, int] = {}
        for v in values:
            if v is not None:
                out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))

    return {
        "by_role": tally(r["role"] for r in records),
        "by_kind": tally(r["kind"] for r in records),
        "by_genre": tally(r["genre"] for r in records),
        "by_archetype": tally(r["archetype"] for r in records),
        "by_status": tally(r["review"]["status"] for r in records),
    }


def _stale_overrides(overrides: dict, all_ids: set[str], pack_ids: set[str], *, partial: bool) -> list[dict]:
    rows = []

    def relevant(key: str) -> bool:
        if not partial:
            return True
        pack_part = key.split("/", 1)[0]
        return any(fnmatchcase(p, pack_part) for p in pack_ids)

    for key in sorted(overrides.get("ids", {})):
        if relevant(key) and key not in all_ids:
            rows.append({"key": key, "kind": "id"})
    for key in sorted(overrides.get("globs", {})):
        if relevant(key) and not any(fnmatchcase(i, key) for i in all_ids):
            rows.append({"key": key, "kind": "glob"})
    return rows


def build_directory_report(
    catalogs_dir: Path,
    *,
    packs: list[str] | None = None,
    rules: dict | None = None,
    overrides: dict | None = None,
    measure: bool = True,
    threejs_v2_dir: Path | None = None,
    pack_settings: dict | None = None,
    base: tuple[dict, dict] | None = None,
    geometry_cache: dict | None = None,
    extracted_root: Path | None = None,
) -> tuple[dict, dict, dict]:
    """``(directory doc, excluded doc, report)``.

    ``pack_settings`` (pack_id -> {setting, era}) defaults to the curated table; ``base`` is the previous
    ``(directory, excluded)`` pair that a ``packs=`` partial build merges into (other packs stay untouched).
    ``threejs_v2_dir`` is the root ``files.glb`` is relative to; ``geometry_cache`` (default: a throwaway dict) is
    read and filled in place. ``extracted_root`` (the configured folder with one extracted tree per pack) lets
    variant discovery list the colourways on disk (spec 3.7); when None the catalogs' ``source.extracted`` is used,
    and without any tree no variants are listed. The report carries stale overrides, warnings and live-run statistics;
    it is never part of the directory.
    """
    rules = rules if rules is not None else load_rules()
    overrides = overrides if overrides is not None else load_overrides()
    settings = _pack_settings(pack_settings)
    docs = load_pack_catalogs(catalogs_dir)
    if not docs:
        raise InputError(f"no pack catalogs found in {catalogs_dir}")

    if packs:
        missing = sorted(set(packs) - set(docs))
        if missing:
            raise InputError(f"unknown pack(s), no catalog in {catalogs_dir}: {', '.join(missing)}")
        selected = sorted(set(packs))
    else:
        selected = sorted(docs)
    partial = bool(packs) and set(selected) != set(docs)

    rules_digest, overrides_digest = weapon_rules_digest(rules), digest(overrides)
    attach_digest = attach_rules_digest(rules)
    records: list[dict] = []
    excluded: list[dict] = []
    pack_rows: list[dict] = []
    all_ids: set[str] = set()
    warnings: list[str] = []
    cache = geometry_cache if geometry_cache is not None else {}
    geo_stats = {"decoded": 0, "cached": 0}
    can_measure = measure and threejs_v2_dir is not None
    skipped_for_root = False
    listing_cache: dict = {}  # Alts directory listings, shared by every record of the build (fast over ~2,700)
    trees_missing = 0

    if partial:
        if base is None:
            raise InputError("a --pack build needs the existing directory to merge into; run a full build first")
        base_dir, base_excl = base
        if (base_dir.get("weapon_version") != _pkg.WEAPON_VERSION
                or base_dir.get("rules_digest") != rules_digest
                or base_dir.get("attach_rules_digest") != attach_digest
                or base_dir.get("attach_version") != _pkg.WEAPON_ATTACH_VERSION
                or base_dir.get("overrides_digest") != overrides_digest):
            raise InputError("the existing directory was built with other rules/overrides/version; run a full build")
        keep = set(selected)
        records += [deepcopy(w) for w in base_dir["weapons"] if w["pack"] not in keep]
        excluded += [deepcopy(e) for e in base_excl["excluded"] if e["id"].split("/", 1)[0] not in keep]
        pack_rows += [deepcopy(p) for p in base_dir["packs"] if p["pack"] not in keep]

    for pack_id in selected:
        doc = docs[pack_id]
        if pack_id not in settings:
            warnings.append(f"pack {pack_id} is missing from pack_settings: genre falls back to the archetype table")
        seen_asset_ids: set[str] = set()
        n_records = n_excluded = 0
        tree = _pack_tree(doc, pack_id, extracted_root)
        for asset in doc["assets"]:
            aid = asset.get("id")
            if not isinstance(aid, str) or not aid:
                raise SchemaError(f"{pack_id}: an asset has no string id")
            if aid in seen_asset_ids:
                raise SchemaError(f"{pack_id}: duplicate asset id {aid}")
            seen_asset_ids.add(aid)
            full_id = f"{pack_id}/{aid}"
            all_ids.add(full_id)

            ev = evaluate_candidate(asset, pack_id, rules)
            id_entry = overrides.get("ids", {}).get(full_id) or {}
            eff = effective_override(full_id, overrides) if (ev["candidate"] or id_entry) else None
            wants_in = bool(id_entry.get("set") or id_entry.get("confirm"))
            placeable = asset.get("placeable") is not False

            accepted, source, reason, matched = ev["accepted"], ev["source"], ev["reason"], ev["matched"]
            if not ev["candidate"]:
                # an exact-id set/confirm override declares the asset a weapon the patterns missed
                if wants_in and placeable and not id_entry.get("exclude"):
                    accepted, source = True, "name_token"
                else:
                    continue
            elif not accepted and reason != "nonplaceable" and placeable and wants_in and not id_entry.get("exclude"):
                accepted = True  # "Restore": an explicit override beats a name-pattern rejection
            if accepted and eff and eff["exclude"]:
                accepted, reason = False, "override"
                matched = "override:" + eff["exclude_by"]
            if not accepted:
                excluded.append({"id": full_id, "reason": reason, "matched": matched, "source": source})
                n_excluded += 1
                continue
            cls = classify(asset, pack_id, rules, overrides, settings.get(pack_id), candidate_source=source)
            detail = None
            if can_measure and (asset.get("files") or {}).get("glb"):
                cls, detail = _measure_record(
                    asset, pack_id, cls, source, rules, overrides, settings.get(pack_id), threejs_v2_dir, cache,
                    geo_stats, forward_override=(eff or {}).get("forward"),
                )
            elif measure and (asset.get("files") or {}).get("glb"):
                skipped_for_root = True
            rec = _record(asset, pack_id, cls, source, (eff or {}).get("renamed_from") or [])
            if not has_colourway_info(asset):
                rec["review"]["reasons"] = sorted(set(rec["review"]["reasons"]) | {"colourway_unknown"})
            elif tree is not None:
                try:
                    rec["visuals"]["variants"] = discover_variants(asset, tree, listing_cache)
                except (OSError, ValueError) as exc:  # never fail the build over colourways
                    warnings.append(f"{full_id}: variants not listed ({exc})")
            else:
                trees_missing += 1
            if detail is not None:
                _apply_measurement(rec, detail)
                if detail.get("warning"):
                    warnings.append(f"{full_id}: {detail['warning']}")
            _apply_attachment(rec, _attachment_block(_attach_class(asset, pack_id, cls, rules), detail), detail)
            records.append(rec)
            n_records += 1
        pack_rows.append({
            "pack": pack_id,
            "scanned_at": doc.get("scanned_at"),
            "asset_count": len(doc["assets"]),
            "candidates": n_records + n_excluded,
            "records": n_records,
            "excluded": n_excluded,
        })

    _mark_duplicates(records)
    _check_renames(records)
    records.sort(key=lambda r: r["id"])
    excluded.sort(key=lambda e: e["id"])
    pack_rows.sort(key=lambda p: p["pack"])

    # hints last: the quality-tier triangle term needs the (archetype, genre) statistics over ALL records,
    # including ones carried over from the base of a partial build (their geometry is already measured)
    group_stats = build_group_stats(records, rules)
    for rec in records:
        rec["hints"] = derive_hints(rec, group_stats, rules)
        rec["provenance"]["hints"] = "rules"
    if skipped_for_root:
        warnings.append("geometry skipped: threejs_v2 root is not configured, records stay unmeasured")
    if trees_missing:
        warnings.append(f"variants skipped for {trees_missing} record(s): no extracted tree for their pack")

    directory = {
        "schema": "weapon-directory/1",
        "weapon_version": _pkg.WEAPON_VERSION,
        "geometry_version": _pkg.WEAPON_GEOMETRY_VERSION,
        "rules_digest": rules_digest,
        "overrides_digest": overrides_digest,
        "attach_version": _pkg.WEAPON_ATTACH_VERSION,
        "attach_rules_digest": attach_digest,
        "packs": pack_rows,
        "counts": _counts(records),
        "weapons": records,
    }
    excluded_doc = {"schema": "weapon-excluded/1", "excluded": excluded}

    mine = [r for r in records if r["pack"] in set(selected)]
    with_glb = [r for r in mine if r["files"].get("glb")]
    n = len(mine) or 1
    report = {
        "packs_built": selected,
        "records": len(mine),
        "excluded": sum(1 for e in excluded if e["id"].split("/", 1)[0] in set(selected)),
        "counts": _counts(mine),
        "low_confidence_share": round(sum(1 for r in mine if r["review"]["confidence"] < 0.6) / n, 4),
        "unknown_share": round(sum(1 for r in mine if r["archetype"] == "unknown" and r["role"] in ("whole", "emplaced")) / n, 4),
        # W7b: the guessed kinds (measured long axis, or melee when unmeasured) for the lead's hand check from icons
        "kind_guessed": [{"id": r["id"], "kind": r["kind"]} for r in mine if "kind_guessed" in r["review"]["reasons"]],
        "geometry_coverage": (round(sum(1 for r in with_glb if r["geometry"] is not None) / len(with_glb), 4)
                              if with_glb else 1.0),
        "geometry_stats": dict(geo_stats),
        "stale_overrides": _stale_overrides(overrides, all_ids, set(selected), partial=partial),
        "warnings": sorted(warnings),
    }
    return directory, excluded_doc, report


def build_directory(catalogs_dir: Path, **kwargs) -> tuple[dict, dict]:
    """``(directory doc, excluded doc)``; same keyword arguments as ``build_directory_report``."""
    directory, excluded, _ = build_directory_report(catalogs_dir, **kwargs)
    return directory, excluded


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"unreadable JSON {path}: {exc}") from exc


def load_directory(catalogs_dir: Path, path: Path | None = None) -> dict:
    path = path or weapons_dir(catalogs_dir) / DIRECTORY_NAME
    if not path.is_file():
        raise InputError(f"no weapon directory at {path}; run `weapons build` first")
    return read_json(path)


def carry_icon_links(catalogs_dir: Path, directory: dict) -> None:
    """Keep the ``visuals`` icon links ``weapons icons`` wrote into the existing directory.json (in place).

    ``build`` derives ``visuals`` as all-null, which would wipe the links on every rebuild. A record whose previous
    ``icon`` and ``thumb`` files still exist next to directory.json takes its ``icon``, ``thumb`` and
    ``icon_input_sha`` back; the previous directory and the icon files are inputs, so two builds on the same inputs
    stay byte-identical (INV-4). The next ``icons`` run re-checks the input sha and re-renders a stale picture.
    """
    wdir = weapons_dir(catalogs_dir)
    prev_path = wdir / DIRECTORY_NAME
    if not prev_path.is_file():
        return
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        old = {w["id"]: w["visuals"] for w in prev["weapons"]}
    except (OSError, ValueError, KeyError, TypeError):
        return  # an unreadable previous file carries nothing; the new one is written regardless
    for rec in directory["weapons"]:
        vis = old.get(rec["id"])
        if not isinstance(vis, dict):
            continue
        if (rec["visuals"]["icon"] is None
                and all(isinstance(vis.get(k), str) and vis[k] for k in ("icon", "thumb", "icon_input_sha"))
                and (wdir / vis["icon"]).is_file() and (wdir / vis["thumb"]).is_file()):
            for key in ("icon", "thumb", "icon_input_sha"):
                rec["visuals"][key] = vis[key]
            if vis.get("icon_mode") == "blend_retry":  # optional key; only with the link it describes
                rec["visuals"]["icon_mode"] = "blend_retry"
        _carry_variant_links(wdir, rec, vis)


def _carry_variant_links(wdir: Path, rec: dict, old_vis: dict) -> None:
    """The same carry-forward for ``visuals.variants[]``, matched by ``variant_id``.

    A variant takes its previous ``icon`` and ``icon_input_sha`` back only when the previous link is exactly the
    path ``icons --variants`` writes for that colourway and both PNGs (icon and ``@64`` thumbnail) still exist.
    A colourway that vanished from the tree is not carried (it is no longer in ``variants``), and one whose sibling
    material changed keeps its link: the next ``icons --variants`` run re-checks the input sha.
    """
    old = {v.get("variant_id"): v for v in old_vis.get("variants") or [] if isinstance(v, dict)}
    for var in rec["visuals"]["variants"]:
        prev = old.get(var["variant_id"])
        if var.get("icon") is not None or not isinstance(prev, dict):
            continue
        icon, thumb = variant_link_paths(ICONS_DIRNAME, rec["pack"], rec["asset_id"], var["variant_id"])
        if (prev.get("icon") == icon and isinstance(prev.get("icon_input_sha"), str) and prev["icon_input_sha"]
                and (wdir / icon).is_file() and (wdir / thumb).is_file()):
            var["icon"], var["icon_input_sha"] = icon, prev["icon_input_sha"]
            if prev.get("icon_mode") == "blend_retry":  # optional keys; only with the link they describe
                var["icon_mode"] = "blend_retry"
            if isinstance(prev.get("visually_identical"), bool):
                var["visually_identical"] = prev["visually_identical"]


def write_directory(catalogs_dir: Path, directory: dict, excluded: dict) -> tuple[Path, Path]:
    """Validate then write ``weapons/directory.json`` and ``weapons/excluded.json`` (LF, sorted keys).

    A schema violation raises ``SchemaError`` before anything is written (spec section 7). Icon links already in
    the existing directory.json survive (``carry_icon_links``).
    """
    carry_icon_links(catalogs_dir, directory)
    errors = validate_directory(directory, excluded)
    if errors:
        raise SchemaError("the built directory violates weapon-directory/1:\n  " + "\n  ".join(errors[:25]),
                          details={"errors": errors})
    out = weapons_dir(catalogs_dir)
    dpath, epath = out / DIRECTORY_NAME, out / EXCLUDED_NAME
    write_text_lf(dpath, to_text(directory))
    write_text_lf(epath, to_text(excluded))
    return dpath, epath
