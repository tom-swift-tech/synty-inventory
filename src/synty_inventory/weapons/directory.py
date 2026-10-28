"""``build_directory``: the weapon directory from the per-pack catalogs (spec 3.1, 3.3, 4.2, 4.3).

Pure given its inputs: no clock, no network, no randomness (INV-4). Catalogs are only read (INV-5); the single
write path is ``write_directory``, which touches nothing but ``<catalogs>/weapons/``. A record is measured when
``measure`` is on, ``threejs_v2_dir`` is given and its ``files.glb`` decodes; otherwise it keeps the unmeasured stub
(``geometry: null``, flag ``unmeasured``, reason ``no_geometry``). Hints are derived for every record regardless.
The geometry cache is a plain dict the caller owns and persists (``geometry.load_cache`` / ``save_cache``), so
this module stays free of file writes outside ``write_directory``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path

import numpy as np

from .. import weapons as _pkg  # read versions at call time (a test may bump WEAPON_VERSION)
from ..naming import SKIP_STEM_RE
from ..paths import is_pack_catalog_file
from ..schema import migrate_catalog
from ..sources.glb_geometry import load_triangles
from ..sources.glb_measure import _cache_key, node_cache_tag
from . import ATTACH_KINDS, InputError, SchemaError, digest, to_text, write_text_lf
from . import fit_geometry as _fit
from .candidates import evaluate_candidate
from .classify import attachment_reason, classify, classify_attachment, tokenize_id
from .attach import hidden_nodes, place, setback_applies, setback_of, settle_applies
from .compat import apply_compat, twin_forward
from .geometry import code_digest, measure_cached, muzzle_stub_cached, pass2_inputs, settle_cached
from .hints import build_group_stats, derive_hints
from .mounts import eligible, is_filled_host, mount_reasons
from .overrides import effective_override, load_overrides
from .pairs import apply_pairs
from .rules import attach_rules_digest, attachment_rules, head_lead_tokens, load_rules, weapon_rules_digest
from .schema import validate_directory
from .variants import discover_variants, has_colourway_info, variant_link_paths

DIRECTORY_NAME = "directory.json"
EXCLUDED_NAME = "excluded.json"
_ATTACH_SET_KEYS = {"attachment_slot", "attachment_kind"}
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


def _attach_class(asset: dict, pack_id: str, cls: dict, rules: dict, overrides: dict | None = None) -> dict | None:
    """The attachment {slot, kind, rule} of the final classification of a part, or None (docs/weapon_attachments.md 3.3).

    W8c: ``set.attachment_slot`` / ``set.attachment_kind`` of the overrides (exact id > longest glob) replace what the rules
    found, or make a part an attachment the rows missed. A slot without a kind takes the rule's kind when the rule found
    the same slot and ``other`` otherwise; a kind without a slot needs the rules' slot (SchemaError, exit 6, when the part
    has none or the kind does not belong to the slot). The override never changes ``component`` (3.3).
    """
    got = classify_attachment(asset["id"], pack_id, cls["role"], cls["component"], rules)
    if cls["role"] != "part" or not overrides:
        return got
    full_id = f"{pack_id}/{asset['id']}"
    chosen = ((effective_override(full_id, overrides) or {}).get("set")) or {}
    slot, kind = chosen.get("attachment_slot"), chosen.get("attachment_kind")
    if slot is None and kind is None:
        return got
    slot = slot or (got["slot"] if got else None)
    if slot is None:
        raise SchemaError(f"{full_id}: set.attachment_kind {kind!r} needs a slot, and the rules found none: "
                          "set attachment_slot as well")
    if kind is None:
        kind = got["kind"] if got and got["slot"] == slot else "other"
    elif kind not in ATTACH_KINDS[slot]:
        raise SchemaError(f"{full_id}: set.attachment_kind {kind!r} is not a kind of slot {slot} ({list(ATTACH_KINDS[slot])})")
    return {"slot": slot, "kind": kind, "rule": "override"}


def _attachment_block(attach_class: dict | None, detail: dict | None) -> dict | None:
    """The record's ``attachment`` block. ``anchor`` and ``footprint`` are null together: with no measurement at all
    (no geometry) and when the foot cannot be measured (the latter adds the review reason ``anchor_unmeasured``)."""
    if attach_class is None:
        return None
    got = (detail or {}).get("attach") or {}
    return {
        "slot": attach_class["slot"], "kind": attach_class["kind"],
        "pair": None,  # filled by pairs.apply_pairs once every record is known (A2, spec 3.5)
        "anchor": got.get("anchor"), "footprint": got.get("footprint"),
        "compatible_hosts": [], "pending_hosts": [],
    }


def _apply_side_unsure(rec: dict, reason: str | None) -> None:
    """Name-only review of an iron-sight part whose side the name does not decide (A2, spec 3.3).

    The part keeps ``attachment: null`` (no slot, no geometry is read to guess one); like a symmetric anchor, the reason caps the
    confidence at 0.59 and adds ``low_confidence``, so it lands on the review page under Parts. An override that sets the slot
    gives the part a block, and the caller passes no reason then.
    """
    if reason is None:
        return
    review = rec["review"]
    review["reasons"] = sorted(set(review["reasons"]) | {reason, "low_confidence"})
    review["confidence"] = round(min(review["confidence"], 0.59), 2)


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


def _fused_parts_factory(docs, rules, overrides, settings, threejs_v2_dir) -> Callable[[str, str], tuple | None]:
    """``fused_for(pack_id, host asset id)`` -> ``(key, load)`` or None: the parts a preset host may carry fused into its mesh (spec 3.2, Q-G11).

    None for a host that is not an ``attach_filled_hosts`` host (only a preset is searched). Otherwise every attachment part of the host's PACK: an
    accepted candidate whose pass-1 classification is role ``part`` and which has an attachment slot (``_attach_class``, id overrides included) and a
    GLB. Pass 1 is enough: it does not read the mesh, and a part's role never depends on a measurement. ``key`` hashes the set (id, slot, GLB sha256,
    node, scale), so it joins the geometry and fit cache fingerprints of the host; ``load()`` decodes the parts (``{id, slot, verts, tris}``, collision
    hulls dropped). Both are memoised per pack, so a pack with many presets reads its parts once.
    """
    tables = attachment_rules(rules)
    packs: dict[str, tuple[str, Callable] | None] = {}

    def for_pack(pack_id: str):
        if pack_id in packs:
            return packs[pack_id]
        rows = []
        for asset in docs[pack_id]["assets"]:
            files = asset.get("files") or {}
            if not isinstance(asset.get("id"), str) or not files.get("glb"):
                continue
            full_id = f"{pack_id}/{asset['id']}"
            ev = evaluate_candidate(asset, pack_id, rules)
            if not (ev["candidate"] and ev["accepted"]) or (effective_override(full_id, overrides) or {}).get("exclude"):
                continue
            cls = classify(asset, pack_id, rules, overrides, settings.get(pack_id), candidate_source=ev["source"])
            attach = _attach_class(asset, pack_id, cls, rules, overrides) if cls["role"] == "part" else None
            path = threejs_v2_dir / files["glb"]
            if attach is None or not path.is_file():
                continue
            rows.append({"id": asset["id"], "slot": attach["slot"], "path": path, "node": files.get("glb_node") or None,
                         "scale": float(files.get("glb_scale") or 1.0), "sha": hashlib.sha256(path.read_bytes()).hexdigest()})
        rows.sort(key=lambda r: r["id"])
        loaded: list[dict] = []

        def load() -> list[dict]:
            if not loaded:
                for r in rows:
                    got = load_triangles(r["path"], r["node"], exclude=lambda n: bool(SKIP_STEM_RE.search(n or "")), scale=r["scale"])
                    if got is not None and len(got[0]) and len(got[1]):
                        loaded.append({"id": r["id"], "slot": r["slot"], "verts": np.asarray(got[0], dtype=np.float64), "tris": np.asarray(got[1])})
            return loaded

        key = digest([[r["id"], r["slot"], r["sha"], node_cache_tag(r["node"]), r["scale"]] for r in rows])
        packs[pack_id] = (key, load) if rows else None
        return packs[pack_id]

    def fused_for(pack_id: str, asset_id: str):
        return for_pack(pack_id) if threejs_v2_dir is not None and is_filled_host(asset_id, tables) else None

    return fused_for


def _measure_record(asset, pack_id, cls, source, rules, overrides, setting, threejs_v2_dir, cache, stats,
                    forward_override=None, mount_overrides=None, frame_axis=None, fit_cache=None, fused_for=None):
    """Measure one record's GLB, then re-classify with the measured length (pass 2).

    Pass 2 can change archetype/hold (a length rule filling an unknown archetype, the long-blade exception); the
    measurement depends on both, so a changed context is measured once more (the decode is memoised, so this
    costs no second read). ``forward_override`` is the id override's ``forward`` (spec 4.5), passed to every
    measurement, and so is ``head_lead`` (W7 R-H2: one of the id's tokens is in ``rules.head_lead_tokens``; the id decides
    it, so it does not change between the pass-1 and pass-2 classifications). ``mount_overrides`` (W8c) is the id override's
    categorical ``mounts`` mapping; it joins the geometry cache fingerprint of an eligible host. ``frame_axis`` (G1) is the id override's forward
    axis (spec 4.5), passed to every measurement like ``forward_override``. G1 (S7): ``fit_cache`` is the dict of ``_fit_cache.json`` and ``fused_for`` the
    ``_fused_parts_factory`` closure (a preset host is searched for its fused parts). Returns ``(final classification, last measurement detail)``.

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
        attach = _attach_class(asset, pack_id, cls, rules, overrides)
        fused = fused_for(pack_id, asset["id"]) if fused_for is not None and eligible(cls["role"], cls["kind"], cls["hold_class"]) else None
        detail, cached = measure_cached(
            threejs_v2_dir, files["glb"], node, scale, cls["archetype"], cls["kind"], cls["role"], rules, cache,
            hold_class=cls["hold_class"], genre=cls["genre"], forward_override=forward_override,
            head_lead=head_lead, attach_slot=attach["slot"] if attach else None, mount_overrides=mount_overrides,
            host_id=asset["id"], attach_kind=attach["kind"] if attach else None, host_pack=pack_id, frame_axis=frame_axis,
            fit_cache=fit_cache, fused_parts=fused,
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


def _carried_child_extents(docs, selected, records, rules, overrides, settings, threejs_v2_dir, cache, fit_cache=None, fused_for=None,
                           host_feats: dict | None = None) -> dict[str, dict]:
    """``child_extents`` (the twin evidence) of the eligible hosts a partial build carries over from its base.

    The carried records hold no measurement, but a part rebuilt in this run must meet the same hosts it would meet in a
    full build, so the host GLBs are read again through the geometry cache (a hit when the cache is warm). The build's own
    decode / hit counters are not touched. A host that cannot be measured now keeps the relation its stored lists carry
    (``compat.apply_compat`` falls back to them). G1 (S7): the host's detector features are carried the same way, into ``host_feats`` when given.
    """
    wanted = {r["id"] for r in records if r["pack"] not in selected and (r.get("geometry") or {}).get("mounts")}
    out: dict[str, dict] = {}
    for pack_id in sorted(docs):
        for asset in docs[pack_id]["assets"]:
            full_id = f"{pack_id}/{asset.get('id')}"
            if full_id not in wanted or not (asset.get("files") or {}).get("glb"):
                continue
            ev = evaluate_candidate(asset, pack_id, rules)
            id_entry = overrides.get("ids", {}).get(full_id) or {}
            eff = effective_override(full_id, overrides) if (ev["candidate"] or id_entry) else None
            source = ev["source"] if ev["candidate"] else "name_token"
            cls = classify(asset, pack_id, rules, overrides, settings.get(pack_id), candidate_source=source)
            _, detail = _measure_record(
                asset, pack_id, cls, source, rules, overrides, settings.get(pack_id), threejs_v2_dir, cache,
                {"cached": 0, "decoded": 0}, forward_override=(eff or {}).get("forward"),
                mount_overrides=(eff or {}).get("mounts"), frame_axis=(eff or {}).get("frame_axis"), fit_cache=fit_cache, fused_for=fused_for)
            if detail is not None and "child_extents" in detail:
                out[full_id] = detail["child_extents"]
            if detail is not None and host_feats is not None and "host_feats" in detail:
                host_feats[full_id] = detail["host_feats"]
    return out


def _apply_measurement(rec: dict, detail: dict, compatible_slots=frozenset()) -> None:
    """Merge a measurement into the unmeasured stub record: geometry, flags, reasons, provenance.

    W8b: ``geometry.mounts`` is the host mount block for an eligible host and null for every other measured record
    (docs/weapon_attachments.md 4.1, D-9). ``compatible_slots`` are the slots with at least one inferred-compatible
    attachment, which turn a ``none`` mount into the review reason ``mount_missing``; the build passes the empty default
    here and ``compat.apply_compat`` adds that reason once every part's compatibility is known (W8c).
    """
    if detail["geometry"] is None:
        rec["review"]["reasons"] = sorted(set(rec["review"]["reasons"]) | set(detail["reasons"]))
        return
    rec["geometry"] = detail["geometry"]
    rec["geometry"]["mounts"] = detail.get("mounts")
    detail["reasons"] = sorted(set(detail["reasons"]) | mount_reasons(detail.get("mounts"), compatible_slots))
    rec["flags"] = sorted((set(rec["flags"]) - {"unmeasured"}) | set(detail["flags"]))
    rec["review"]["reasons"] = sorted((set(rec["review"]["reasons"]) - {"no_geometry"}) | set(detail["reasons"]))
    rec["provenance"]["geometry"] = "measured"


def _stored_shifts(records: list[dict]) -> dict[tuple[str, str], float]:
    """(part id, host id) -> seat_shift_m of the pairs the records carry now (those a partial build carries over from its base)."""
    return {(r["id"], e["host"]): e["seat_shift_m"] for r in records if r.get("attachment")
            for e in r["attachment"].get("compatible_hosts") or [] if "seat_shift_m" in e}


def _apply_contact(records: list[dict], rules: dict, threejs_v2_dir: Path | None, cache: dict, stats: dict, stored: dict) -> int:
    """A5 (W8m, spec 5.4): the post-pass after compatibility. Every entry of compatible_hosts of an optic or underbarrel part that
    attach.settle_applies selects gets seat_shift_m when settle_cached finds one; the key is absent otherwise (compat builds the
    entries without it, so an entry that finds none needs no removal). The pairs are walked host by host, so each host mesh is decoded once.

    A pair whose meshes cannot be read now (no threejs_v2 root, a missing or undecodable GLB) keeps the value its record carried before the
    build (stored: a partial build's carried-over parts), the way compat keeps a stored relation for a host it cannot measure. stats
    counts the pairs by how they were settled (computed, cached, kept), apart from geometry_stats.

    A6 (W8n, 13.7 A6-4): an entry whose settled ``|seat_shift_m|`` exceeds ``contact.cap_m`` is REMOVED from ``compatible_hosts`` (not pending
    either: the seat of that host is wrong by more than a foot can excuse). The cap reads the value whichever way it was found (computed, cached
    or kept); a tier that is never keyed (twin, override) is never removed. A part that loses its last cross-pack entry loses the review reason
    ``compat_cross_pack``, which compat set before the removal. Returns the number of entries removed.
    """
    params = attachment_rules(rules).get("contact")
    if not params:  # a custom rules file without the table: no rule, no key
        return 0
    cap = params.get("cap_m")
    capped: dict[str, set[str]] = {}  # part id -> the hosts whose entry the cap removes
    by_id = {r["id"]: r for r in records}
    work = []
    for part in records:
        att = part.get("attachment")
        if not att or not att.get("compatible_hosts") or att["slot"] not in params["slots"]:
            continue
        for entry in att["compatible_hosts"]:
            host = by_id.get(entry["host"])
            mount = (((host or {}).get("geometry") or {}).get("mounts") or {}).get(att["slot"])
            if settle_applies(att["slot"], mount, entry["tier"], att.get("anchor"), params):
                work.append((entry["host"], part["id"], part, host, entry, mount))
    memo: dict = {}
    for _, _, part, host, entry, mount in sorted(work, key=lambda w: w[:2]):
        att = part["attachment"]
        shift, how = None, "unavailable"
        if threejs_v2_dir is not None and (part.get("files") or {}).get("glb") and (host.get("files") or {}).get("glb"):
            shift, how = settle_cached(threejs_v2_dir, part["files"], host["files"], att["anchor"], mount,
                                       hidden_nodes(host["geometry"]["mounts"], att["slot"], entry), att["slot"], params, cache, memo)
        if how == "unavailable":
            shift = stored.get((part["id"], entry["host"]))
            how = "kept"
        stats[how] += 1
        if shift is not None:
            entry["seat_shift_m"] = shift
            if cap is not None and abs(shift) > cap + 1e-9:
                capped.setdefault(part["id"], set()).add(entry["host"])
    removed = 0
    for part in records:  # collected first, applied after the walk: the loop above reads the lists it would shrink
        gone = capped.get(part["id"])
        if not gone:
            continue
        att = part["attachment"]
        kept = [e for e in att["compatible_hosts"] if e["host"] not in gone]
        removed += len(att["compatible_hosts"]) - len(kept)
        att["compatible_hosts"] = kept
        if not any(e["tier"] == "cross_pack_fit" for e in kept + att["pending_hosts"]):
            part["review"]["reasons"] = [x for x in part["review"]["reasons"] if x != "compat_cross_pack"]
    return removed


# -- G1: the part side of the geometry verdict (spec 3.6 "Part side", 3.7 steps 1 and 2; plan S8) -----------------------------------------------
#
# ``compat`` stays a pure function over records and carried maps, so what needs a mesh is measured here, before it runs:
#   * a muzzle device's inner bore ring (``fit_geometry.device_inner_d``), one result per part (cache id ``fitpart|<part id>``);
#   * a magazine's entry section on every host that has a well reference: the part is placed at the reference seat with the existing placement (C-21,
#     ``attach.place``), taken into the host's (f, s, u) frame and cut at ``u_rb - entry_depth_m`` (``fit_geometry.entry_section``), one result per
#     (part, host) pair (cache id ``well|<part id>|<host id>``). The result holds a section for the mount's own seat (key "") and one for every child seat
#     of a mount that lists several (A1, key = the child node), because a twin pair is judged on its twin's own seat (3.7 step 2).
# Both are cached beside the measurements in the geometry cache, the way ``settle_cached`` caches a pair: valid while the part's file (mtime:size) and the
# version (``WEAPON_GEOMETRY_VERSION`` + the digests of this file and of the ``fit_*`` modules) match, one result per fingerprint of the inputs that are
# NOT the part's file (its anchor, the seat frames and the reference plane, the host axes, the rules, the attach version, ``attach.py``'s digest). The
# host's mesh is not an input: everything the pair reads of the host is in its features. A cache hit equals a recompute, and a build with nothing changed
# reads no mesh.

_FIT_PASS_CODE = code_digest(Path(__file__).read_bytes())  # the digest of this file, as geometry.py keeps one for itself
_ATTACH_CODE = code_digest((Path(__file__).parent / "attach.py").read_bytes())  # the placement the section is taken under
_FIT_KEEP = 8  # fingerprints kept per cache entry (the oldest go first)


def _fit_cached(cache: dict, cache_id: str, key: str, fp: str, compute: Callable[[], dict | None]) -> tuple[object, str]:
    """``(result, how)``, ``how`` being ``cached``, ``computed`` or ``unavailable`` (``compute`` returned None: the mesh cannot be read, nothing is stored).

    ``compute`` returns ``{"v": result}``; the result is any JSON value (a null result is cached too, as ``settle_cached`` does for "no key")."""
    version = f"{_pkg.WEAPON_GEOMETRY_VERSION}+{_FIT_PASS_CODE}+{digest(_fit.FIT_CODE_DIGESTS)}"
    entry = cache.get(cache_id)
    if not isinstance(entry, dict) or entry.get("key") != key or entry.get("version") != version:
        entry = {"key": key, "version": version, "by_inputs": {}}
        cache[cache_id] = entry
    hit = entry["by_inputs"].get(fp)
    if hit is not None:
        return hit["v"], "cached"
    got = compute()
    if got is None:
        return None, "unavailable"
    entry["by_inputs"][fp] = {"v": got["v"]}
    while len(entry["by_inputs"]) > _FIT_KEEP:
        del entry["by_inputs"][next(iter(entry["by_inputs"]))]
    return got["v"], "computed"


def _well_hosts(records: list[dict], feats_by_host: dict) -> list[tuple]:
    """``[(host id, frame basis, {seat key: (seat frame, well reference)})]`` of the hosts a magazine can be placed on, sorted by host id: an authored
    magazine seat (``child_node`` / ``override``) with a well reference. A host with no seat (none, or only a LOCATED magazine, errata E2.4) has none."""
    by_id = {r["id"]: r for r in records}
    out = []
    for host_id in sorted(feats_by_host):
        rec = by_id.get(host_id)
        feats = (feats_by_host[host_id].get("slots") or {}).get("magazine") or {}
        geo = (rec or {}).get("geometry") or {}
        mount = (geo.get("mounts") or {}).get("magazine")
        if not feats.get("well_ref") or not mount or mount["source"] == "none" or mount.get("point") is None or not geo.get("axes"):
            continue
        seats = {"": (mount, feats["well_ref"])}
        for node, ref in sorted((feats.get("well_refs") or {}).items()):
            if node in (mount.get("seats") or {}):
                seats[node] = (mount["seats"][node], ref)
        out.append((host_id, _fit.frame_basis(geo["axes"]), geo["axes"], seats))
    return out


def _apply_fit_parts(records: list[dict], rules: dict, threejs_v2_dir: Path | None, cache: dict, feats_by_host: dict, stats: dict) -> dict[str, dict]:
    """``{part id: {"device_inner_d": float | None}}`` for muzzle parts and ``{part id: {"sections": {host id: {seat key: [L, W] | None}}}}`` for
    magazine parts, the part side of the geometry verdict (see the section header). A part whose file cannot be read now has no entry, and a magazine
    pair without a section is ``unverified`` in ``compat``. ``stats`` counts the entries by how they were found (computed, cached)."""
    fit_rules = attachment_rules(rules).get("fit_geometry")
    out: dict[str, dict] = {}
    if not fit_rules or threejs_v2_dir is None:
        return out
    wells = _well_hosts(records, feats_by_host)
    for part in sorted(records, key=lambda r: r["id"]):
        att = part.get("attachment")
        files = part.get("files") or {}
        if not att or att["slot"] not in ("muzzle", "magazine") or att["anchor"] is None or not files.get("glb"):
            continue
        path = threejs_v2_dir / files["glb"]
        file_key = _cache_key(path)
        if file_key is None:
            continue
        node, scale = files.get("glb_node") or None, float(files.get("glb_scale") or 1.0)
        loaded: list = []

        def mesh(path=path, node=node, scale=scale, loaded=loaded):
            """The part's render mesh (collision hulls dropped), read once and only when a result is not cached."""
            if not loaded:
                got = load_triangles(path, node, exclude=lambda n: bool(SKIP_STEM_RE.search(n or "")), scale=scale)
                ok = got is not None and len(got[0]) and len(got[1]) and np.isfinite(got[0]).all()
                loaded.append((np.asarray(got[0], dtype=np.float64), np.asarray(got[1], dtype=np.int64)) if ok else None)
            return loaded[0]

        anchor = att["anchor"]
        common = {"av": _pkg.WEAPON_ATTACH_VERSION, "ad": _ATTACH_CODE}
        if att["slot"] == "muzzle":
            def inner(mesh=mesh, anchor=anchor):
                got = mesh()
                return None if got is None else {"v": _fit.device_inner_d(got[0], anchor, fit_rules)}

            value, how = _fit_cached(cache, f"fitpart|{part['id']}", file_key, digest({"an": anchor, "bore": fit_rules["bore"], **common}), inner)
            if how != "unavailable":
                stats[how] += 1
                out[part["id"]] = {"device_inner_d": value}
            continue
        sections: dict[str, dict] = {}
        for host_id, basis, axes, seats in wells:
            def cut(mesh=mesh, anchor=anchor, basis=basis, seats=seats):
                got = mesh()
                if got is None:
                    return None
                verts, tris = got
                found = {}
                for key, (seat, ref) in seats.items():
                    m = place(anchor, seat)
                    placed = _fit.to_fsu(basis, verts @ m[:3, :3].T + m[:3, 3])
                    section = _fit.entry_section(placed, tris, ref["u_rb"] - fit_rules["well"]["entry_depth_m"])
                    found[key] = None if section is None else [section[0], section[1]]
                return {"v": found}

            fp = digest({"an": anchor, "axes": axes, "depth": fit_rules["well"]["entry_depth_m"], **common,
                         "seats": {k: [{f: s[f] for f in ("point", "forward", "up")}, r["u_rb"]] for k, (s, r) in seats.items()}})
            value, how = _fit_cached(cache, f"well|{part['id']}|{host_id}", file_key, fp, cut)
            if how != "unavailable":
                stats[how] += 1
                sections[host_id] = value
        if sections:
            out[part["id"]] = {"sections": sections}
    return out


def _fit_records(feats_by_host: dict, part_fit: dict) -> list[dict]:
    """The measure records ``fit_geometry.fit_digest`` hashes (spec 4.3): one per (host, slot) that has features, the located placements of a preset as
    slot ``located``, and one per part with a measure. The digest sorts them, and every float is rounded there to 1e-4."""
    rows = []
    for host_id, feats in feats_by_host.items():
        for slot, got in (feats.get("slots") or {}).items():
            if got:
                rows.append({"host": host_id, "slot": slot, **got})
        if feats.get("located"):
            rows.append({"host": host_id, "slot": "located", "placements": feats["located"]})
    rows.extend({"part": part_id, **got} for part_id, got in part_fit.items())
    return rows


def _stored_setbacks(records: list[dict]) -> dict[tuple[str, str], float]:
    """(part id, host id) -> seat_setback_m of the pairs the records carry now (those a partial build carries over from its base)."""
    return {(r["id"], e["host"]): e["seat_setback_m"] for r in records if r.get("attachment")
            for e in r["attachment"].get("compatible_hosts") or [] if "seat_setback_m" in e}


def _apply_muzzle_seat(records: list[dict], rules: dict, threejs_v2_dir: Path | None, cache: dict, stats: dict, stored: dict) -> None:
    """A6 (W8n, 13.7 A6-2): the post-pass after compatibility and the contact pass. Every entry of a suppressor's ``compatible_hosts`` that
    ``attach.setback_applies`` selects (a probe muzzle mount with nothing baked on it, tier not twin or override) gets ``seat_setback_m`` when the
    host's muzzle end and the part's length ask for one (``attach.setback_of``); the key is absent otherwise (compat builds the entries without it).

    The host's muzzle end is measured once per host (``geometry.muzzle_stub_cached``: the silhouette is the host's, the part only brings its
    length ``footprint.height_m``). A host whose mesh cannot be read now (no threejs_v2 root, a missing or undecodable GLB) keeps the value each
    carried record had (``stored``, like the contact pass). ``stats`` counts the hosts read (computed, cached) and the pairs kept.
    """
    params = attachment_rules(rules).get("muzzle_seat")
    if not params:  # a custom rules file without the table: no rule, no key
        return
    by_id = {r["id"]: r for r in records}
    work = []
    for part in records:
        att = part.get("attachment")
        length = ((att or {}).get("footprint") or {}).get("height_m")
        if not att or att["slot"] != "muzzle" or att["kind"] != "suppressor" or not length:
            continue
        for entry in att["compatible_hosts"]:
            host = by_id.get(entry["host"])
            mount = (((host or {}).get("geometry") or {}).get("mounts") or {}).get("muzzle")
            if setback_applies(att["slot"], att["kind"], entry["tier"], mount):
                work.append((entry["host"], part["id"], host, entry, mount, float(length)))
    seen: dict[str, tuple] = {}
    memo: dict = {}
    for host_id, part_id, host, entry, mount, length in sorted(work, key=lambda w: w[:2]):
        if host_id not in seen:
            got, how = None, "unavailable"
            if threejs_v2_dir is not None and (host.get("files") or {}).get("glb"):
                got, how = muzzle_stub_cached(threejs_v2_dir, host["files"], mount, list(mount.get("occupied_by") or []), params, cache, memo)
            if how != "unavailable":
                stats[how] += 1
            seen[host_id] = (got, how)
        got, how = seen[host_id]
        if how == "unavailable":
            setback = stored.get((part_id, host_id))
            stats["kept"] += 1
        else:
            setback = setback_of(got["stub"], got["dev"], length, params) if got else None
        if setback is not None:
            entry["seat_setback_m"] = setback


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
    fit_cache: dict | None = None,
    host_feats: dict | None = None,
) -> tuple[dict, dict, dict]:
    """``(directory doc, excluded doc, report)``.

    ``pack_settings`` (pack_id -> {setting, era}) defaults to the curated table; ``base`` is the previous
    ``(directory, excluded)`` pair that a ``packs=`` partial build merges into (other packs stay untouched).
    ``threejs_v2_dir`` is the root ``files.glb`` is relative to; ``geometry_cache`` (default: a throwaway dict) is
    read and filled in place. ``extracted_root`` (the configured folder with one extracted tree per pack) lets
    variant discovery list the colourways on disk (spec 3.7); when None the catalogs' ``source.extracted`` is used,
    and without any tree no variants are listed. The report carries stale overrides, warnings and live-run statistics;
    it is never part of the directory.

    G1 (S7): ``fit_cache`` (default: none, nothing cached) is the dict of ``<catalogs>/weapons/_fit_cache.json``, read and filled in place like
    ``geometry_cache``; the caller persists it with ``fit_geometry.load_fit_cache`` / ``save_fit_cache`` (this module writes nothing but
    ``write_directory``). ``host_feats`` (default: none) is filled in place with ``{host id: {s0, slots, located}}`` for every eligible host,
    carried hosts of a partial build included, the way ``child_extents`` is carried: the detectors' features for the later verdict pass (S8). The
    report counts the hosts per mount ``feature`` value (``feature_counts``). E3 slice D3: it also carries ``frame_counts``, ``frame_changed_hosts``
    and ``fill_list`` (AC147, AC139), and (AC149, errata E3.5a) ``frame_sight_gain``, over the packs built like ``feature_counts``; none of them is
    part of the directory.
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
    contact_stats = {"computed": 0, "cached": 0, "kept": 0}  # A5: the pairs of the contact post-pass, apart from geo_stats (which tests pin)
    setback_stats = {"computed": 0, "cached": 0, "kept": 0}  # A6: the HOSTS the silencer seat read (computed, cached) and the pairs it kept
    fit_stats = {"computed": 0, "cached": 0}  # G1: the entries of the part pass (muzzle inner rings, magazine sections) by how they were found
    compat_stats: dict = {}  # G1: filled by apply_compat (parked_fit: the cross-pack pairs the geometry judged fit and A8-1 routed to pending)
    can_measure = measure and threejs_v2_dir is not None
    skipped_for_root = False
    listing_cache: dict = {}  # Alts directory listings, shared by every record of the build (fast over ~2,700)
    trees_missing = 0
    child_extents: dict[str, dict] = {}  # host id -> {slot: {child node: sorted AABB extents}} of the hosts measured now
    feats_by_host: dict[str, dict] = host_feats if host_feats is not None else {}  # host id -> detector features (S7)
    votes_by_host: dict[str, dict] = {}  # host id -> the frame vote's state of the hosts measured now (E3 D3: the report's frame keys)
    located_fills: dict[str, list[str]] = {}  # host id -> the slots a located part filled and refuse_filled refused (E3 D3: the report's fill_list)
    sight_gains: dict[str, bool] = {}  # host id -> a frame-changed host that gains a sight seat in the voted frame (AC149, E3.5a: the report's frame_sight_gain)
    fused_for = _fused_parts_factory(docs, rules, overrides, settings, threejs_v2_dir) if measure and threejs_v2_dir is not None else None

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
            # an override that only sets attachment_slot / attachment_kind classifies a part that is already a record; it
            # must not declare a weapon the candidate patterns missed or restore a rejected one
            wants_in = bool(set(id_entry.get("set") or {}) - _ATTACH_SET_KEYS or id_entry.get("confirm"))
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
                    geo_stats, forward_override=(eff or {}).get("forward"), mount_overrides=(eff or {}).get("mounts"),
                    frame_axis=(eff or {}).get("frame_axis"), fit_cache=fit_cache, fused_for=fused_for,
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
                if "child_extents" in detail:  # an eligible host: its baked children are the twin evidence (W8c)
                    child_extents[full_id] = detail["child_extents"]
                if "host_feats" in detail:
                    feats_by_host[full_id] = detail["host_feats"]
                if "frame_vote" in detail:
                    votes_by_host[full_id] = detail["frame_vote"]
                if "refused_by_located" in detail:
                    located_fills[full_id] = detail["refused_by_located"]
                if "frame_sight_gain" in detail:
                    sight_gains[full_id] = detail["frame_sight_gain"]
                _apply_measurement(rec, detail)
                if detail.get("warning"):
                    warnings.append(f"{full_id}: {detail['warning']}")
                warnings.extend(f"{full_id}: mount {problem}" for problem in detail.get("mount_problems") or [])
            attach_class = _attach_class(asset, pack_id, cls, rules, overrides)
            _apply_attachment(rec, _attachment_block(attach_class, detail), detail)
            if attach_class is None:  # an iron sight with no decided side is reviewed by name alone (A2)
                _apply_side_unsure(rec, attachment_reason(asset["id"], pack_id, cls["role"], cls["component"], rules))
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
    if partial and can_measure:  # a rebuilt part is judged against carried hosts exactly as in a full build
        child_extents.update(_carried_child_extents(docs, set(selected), records, rules, overrides, settings, threejs_v2_dir, cache,
                                                    fit_cache, fused_for, feats_by_host))
    # W8c: compatibility needs every host's mounts, so it is a post-pass over ALL records (carried-over ones included)
    stored_shifts = _stored_shifts(records)  # compat rebuilds every entry; a pair that cannot be settled now keeps its carried value
    stored_setbacks = _stored_setbacks(records)
    apply_pairs(records, overrides)  # A2: sight sets, before compatibility (a set candidate needs both members' lists)
    # E3.12: a twin part's forward is corrected BEFORE its well section is cut. The section places the part with its stored anchor, and the prior forward
    # (the longer horizontal extent) can be the wrong axis; calibrate places the part from the finished directory, so it reads the corrected one. The
    # carried hosts' child_extents are in by now (a partial build corrects against them too). apply_compat runs the same function first thing, as it
    # did before (compat.py stays self-correcting for its other callers); it finds the forward right and does nothing.
    twin_forward(records, child_extents)
    part_fit = _apply_fit_parts(records, rules, threejs_v2_dir if can_measure else None, cache, feats_by_host, fit_stats)  # G1: the mesh side, before compat
    warnings.extend(apply_compat(records, rules, overrides, child_extents=child_extents, host_feats=feats_by_host, part_fit=part_fit, stats=compat_stats))
    fit_digest = _fit.fit_digest(_fit_records(feats_by_host, part_fit))
    contact_capped = _apply_contact(records, rules, threejs_v2_dir if can_measure else None, cache, contact_stats, stored_shifts)  # A5: after compat, it needs the entries
    _apply_muzzle_seat(records, rules, threejs_v2_dir if can_measure else None, cache, setback_stats, stored_setbacks)  # A6: after the contact pass
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
        "fit_digest": fit_digest,
        "packs": pack_rows,
        "counts": _counts(records),
        "weapons": records,
    }
    excluded_doc = {"schema": "weapon-excluded/1", "excluded": excluded}

    mine = [r for r in records if r["pack"] in set(selected)]
    with_glb = [r for r in mine if r["files"].get("glb")]
    n = len(mine) or 1
    frame_counts, frame_changed_hosts, fill_list = _frame_and_fill_report(mine, votes_by_host, located_fills)
    frame_sight_gain = _frame_sight_gain_report(mine, sight_gains)
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
        "contact_stats": dict(contact_stats),
        "contact_capped": contact_capped,  # A6: the entries the contact cap removed
        "setback_stats": dict(setback_stats),
        "feature_counts": _feature_counts(mine),  # G1 (S7): hosts per mount feature value
        "frame_counts": frame_counts,  # E3 D3 (AC147): hosts whose frame vote changed / conflicted, over the packs built
        "frame_changed_hosts": frame_changed_hosts,  # E3 D3 (AC139, AC147): the changed hosts with their class (archetype)
        "fill_list": fill_list,  # E3 D3 (AC139, Q-G11): the preset slots a located fused part filled and refuse_filled refused
        "frame_sight_gain": frame_sight_gain,  # AC149 (E3.5a): the frame-changed hosts whose sight slot is probe_unavailable in the build frame and probe-seated in the voted one
        "fit_stats": dict(fit_stats),  # G1 (S8): the part pass (computed, cached)
        "cross_pack_magazine_fit": compat_stats.get("parked_fit", {}).get("magazine", 0),  # G1 AC140: cross-pack magazine pairs judged `fit`, parked by A8-1 (Q-G1)
        "stale_overrides": _stale_overrides(overrides, all_ids, set(selected), partial=partial),
        "warnings": sorted(warnings),
    }
    return directory, excluded_doc, report


def _frame_and_fill_report(records: list[dict], votes: dict[str, dict], fills: dict[str, list[str]]) -> tuple[dict, list[dict], list[dict]]:
    """``(frame_counts, frame_changed_hosts, fill_list)`` of the report (E3 slice D3: AC139, AC147), over ``records`` = the packs built, as ``_feature_counts``.

    ``votes`` / ``fills`` are the per-host ``frame_vote`` and ``refused_by_located`` of the hosts measured in this build (a carried host of a partial
    build is not in ``records``, so it is out of scope). ``class`` is the record's archetype. ``fill_list`` is exactly what ``mounts.refuse_filled``
    returned: the slots it refused where a located fused part fills them (alone or with the baked-glass disjunct; trace T-fill), not a guess from the
    final mounts. Both lists are sorted, so the report is deterministic.
    """
    changed = sorted((r for r in records if (votes.get(r["id"]) or {}).get("changed")), key=lambda r: r["id"])
    counts = {"changed": len(changed), "conflict": sum(1 for r in records if (votes.get(r["id"]) or {}).get("conflict"))}
    hosts = [{"host": r["id"], "class": r["archetype"]} for r in changed]
    fill_list = [{"host": r["id"], "class": r["archetype"], "slot": slot} for r in records for slot in fills.get(r["id"]) or ()]
    return counts, hosts, sorted(fill_list, key=lambda f: (f["host"], f["slot"]))


def _frame_sight_gain_report(records: list[dict], gains: dict[str, bool]) -> dict:
    """``{"count": n, "hosts": [{"host", "class"}]}`` of the report (AC149, errata E3.5a): the frame-changed hosts that gain a sight seat in the voted frame.

    ``gains`` is the per-host ``frame_sight_gain`` flag of the hosts measured in this build (``geometry.measure_weapon_detail`` probes the sight slots in
    the build frame for a frame-changed host: no single build holds that state). ``records`` = the packs built, as ``frame_changed_hosts``: a carried
    host of a partial build is out of scope. ``class`` is the record's archetype; the list is sorted by host id.
    """
    hosts = [{"host": r["id"], "class": r["archetype"]} for r in sorted(records, key=lambda r: r["id"]) if gains.get(r["id"])]
    return {"count": len(hosts), "hosts": hosts}


def _feature_counts(records: list[dict]) -> dict[str, int]:
    """``{feature: number of hosts with at least one mount of that feature}``, sorted by feature (G1, AC148)."""
    hosts: dict[str, set[str]] = {}
    for rec in records:
        for _, m in sorted(((rec.get("geometry") or {}).get("mounts") or {}).items()):
            if m.get("feature"):
                hosts.setdefault(m["feature"], set()).add(rec["id"])
    return {feature: len(ids) for feature, ids in sorted(hosts.items())}


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
