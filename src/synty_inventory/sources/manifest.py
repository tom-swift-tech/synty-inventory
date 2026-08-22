"""Generator-fed (`GEN_*`) packs: sidecar manifest ingestion.

Contract: docs/gen_manifest_v1.md. One ``<Stem>.gen.json`` sidecar per GLB
under ``<threejs_v2>/GEN_<Theme>/``. The manifest *declares* structure
(type, role, tags, prose, sockets) at provenance ``declared`` (rank 2 —
above ``rules``, below ``measured``/review/human); geometry is never
declared — bounds and pivot always come from GLB measurement. The
``intended_size_m`` / ``pivot`` / ``up_axis`` expectations are stored inside
the asset's ``generation`` block for the Phase 4 QA gates.

Sibling of ``sources/mech.py``: ``load_gen_entries`` no-ops (returns empty)
for every pack that is not ``GEN_``-prefixed, so the enrich pipeline can call
it unconditionally.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..discover import PackRef
from ..merge import may_overlay
from ..scan import RawAsset
from ..schema import (
    GEN_PIVOTS,
    GENERATION_REQUIRED,
    SEMANTIC_ROLES,
    TYPE_MIGRATION,
    TYPES,
    default_placeable,
    kind_for_type,
    normalize_attachment,
    normalize_mount,
    normalize_semantic_role,
)

GEN_PREFIX = "GEN_"
SIDECAR_SUFFIX = ".gen.json"
SCHEMA_ID = "gen-manifest/1"

_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_\-+.]*$")


@dataclass
class GenEntry:
    """One GLB in a GEN pack: its rel path (threejs_v2-relative, same format
    as ``sources.threejs_v2.glb_index``), its parsed sidecar (None when the
    sidecar is missing or invalid), and any validation errors."""

    stem: str
    glb_rel: str
    manifest: dict | None = None
    errors: list[str] = field(default_factory=list)


def is_gen_pack(pack_id: str) -> bool:
    return pack_id.startswith(GEN_PREFIX)


def _is_vec3(v) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)


def validate_manifest(doc: dict, stem: str, pack_id: str) -> list[str]:
    """Spec-v1 checks (docs/gen_manifest_v1.md). Returns a flat error list;
    an empty list means the sidecar may be ingested."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["manifest is not an object"]
    if doc.get("schema") != SCHEMA_ID:
        errors.append(f"schema must be {SCHEMA_ID!r}: {doc.get('schema')!r}")
    if doc.get("id") != stem:
        errors.append(f"id must equal GLB stem {stem!r}: {doc.get('id')!r}")
    if doc.get("pack") != pack_id:
        errors.append(f"pack must equal pack dir {pack_id!r}: {doc.get('pack')!r}")
    atype = TYPE_MIGRATION.get(doc.get("type") or "", doc.get("type") or "")
    if atype not in TYPES:
        errors.append(f"type invalid: {doc.get('type')!r}")
    if doc.get("semantic_role") not in SEMANTIC_ROLES:
        errors.append(f"semantic_role invalid: {doc.get('semantic_role')!r}")
    size = doc.get("intended_size_m")
    if not (_is_vec3(size) and all(x > 0 for x in size)):
        errors.append("intended_size_m must be a positive [x,y,z]")
    if doc.get("pivot") not in GEN_PIVOTS:
        errors.append(f"pivot invalid: {doc.get('pivot')!r}")
    if doc.get("up_axis") != "Y":
        errors.append(f"up_axis must be 'Y': {doc.get('up_axis')!r}")
    gen = doc.get("generation")
    if not isinstance(gen, dict):
        errors.append("generation block missing")
    else:
        for key in GENERATION_REQUIRED:
            if not gen.get(key):
                errors.append(f"generation.{key} missing or empty")
    if not (isinstance(doc.get("license"), str) and doc["license"].strip()):
        errors.append("license missing or empty")
    tags = doc.get("tags")
    if tags is not None:
        if not isinstance(tags, list):
            errors.append("tags must be a list")
        else:
            for t in tags:
                if not (isinstance(t, str) and _TOKEN_RE.match(t)):
                    errors.append(f"tags entry not a lowercase token: {t!r}")
    return errors


def _glb_rels(pack_dir: Path, pack_id: str) -> list[str]:
    """threejs_v2-relative GLB paths, from the pack-level manifest.json
    listing when present (the threejs-v2 convention), else a deterministic
    glob of the pack dir."""
    listing = pack_dir / "manifest.json"
    if listing.is_file():
        try:
            doc = json.loads(listing.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = None
        if isinstance(doc, dict) and isinstance(doc.get("models"), list):
            return [f"{pack_id}/{rel}" for rel in doc["models"] if isinstance(rel, str)]
    return sorted(
        f"{pack_id}/{p.relative_to(pack_dir).as_posix()}" for p in pack_dir.rglob("*.glb")
    )


def load_gen_entries(threejs_v2: Path | None, pack_id: str) -> dict[str, GenEntry]:
    """Stem -> GenEntry for a GEN pack; empty for non-GEN packs or when the
    pack dir does not exist. No caching: a regeneration mid-session must be
    picked up by the next scan."""
    if threejs_v2 is None or not is_gen_pack(pack_id):
        return {}
    pack_dir = threejs_v2 / pack_id
    if not pack_dir.is_dir():
        return {}
    entries: dict[str, GenEntry] = {}
    for rel in _glb_rels(pack_dir, pack_id):
        glb_path = threejs_v2 / rel
        stem = glb_path.stem
        if stem in entries:
            continue
        entry = GenEntry(stem=stem, glb_rel=rel)
        sidecar = glb_path.with_name(stem + SIDECAR_SUFFIX)
        if not sidecar.is_file():
            entry.errors.append(f"{stem}: sidecar {sidecar.name} missing")
        else:
            try:
                doc = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                doc = None
                entry.errors.append(f"{stem}: sidecar unreadable: {exc}")
            if doc is not None:
                errs = validate_manifest(doc, stem, pack_id)
                if errs:
                    entry.errors.extend(f"{stem}: {e}" for e in errs)
                else:
                    entry.manifest = doc
        entries[stem] = entry
    return entries


def scan_gen(threejs_v2: Path, pack_id: str) -> list[RawAsset]:
    """Skeleton inputs for a GEN pack: one RawAsset per GLB stem. No Unity
    prefab/mesh — ``files.glb`` is wired by ``apply_gen_overlay`` (and by the
    threejs-v2 overlay when the pack ships a manifest.json listing)."""
    return [
        RawAsset(id=stem, kit=None, shared=False, engine="GLB")
        for stem in sorted(load_gen_entries(threejs_v2, pack_id))
    ]


def gen_pack_ref(pack_dir: Path) -> PackRef | None:
    """PackRef for one ``GEN_*`` directory, or None when it is not one."""
    if not (pack_dir.is_dir() and is_gen_pack(pack_dir.name)):
        return None
    if not any(pack_dir.rglob("*.glb")) and not (pack_dir / "manifest.json").is_file():
        return None
    return PackRef(pack_id=pack_dir.name, engine="GLB", extras={"gen_dir": pack_dir})


def discover_gen_packs(threejs_v2: Path | None) -> list[PackRef]:
    """Every GEN pack under the threejs_v2 root, sorted by pack id."""
    if threejs_v2 is None or not threejs_v2.is_dir():
        return []
    refs = []
    for child in sorted(threejs_v2.iterdir()):
        ref = gen_pack_ref(child)
        if ref is not None:
            refs.append(ref)
    return refs


def _allowed(asset: dict, field_name: str) -> bool:
    return may_overlay(asset, field_name, "declared")


def apply_gen_overlay(asset: dict, entry: GenEntry | None) -> dict:
    """Wire ``files.glb`` and overlay the declared structure from the sidecar
    onto ``asset`` in place, at provenance ``declared``. Geometry (bounds /
    dimensions / measured pivot) is deliberately untouched — that stays with
    ``apply_measured_bounds`` at rank ``measured``."""
    if entry is None:
        return asset
    files = asset.setdefault("files", {})
    if not files.get("glb"):  # empty_files() pre-seeds glb: None — don't clobber a wired path
        files["glb"] = entry.glb_rel
    m = entry.manifest
    if m is None:  # missing/invalid sidecar: rules-only skeleton, Phase 3
        return asset

    prov = asset.setdefault("provenance", {})

    # Scanner-owned generator metadata: the whole provenance story of the
    # asset, refreshed on every scan (merge.py treats these like kit/guid).
    gen = dict(m.get("generation") or {})
    gen["intended_size_m"] = m.get("intended_size_m")
    gen["pivot"] = m.get("pivot")
    gen["up_axis"] = m.get("up_axis")
    asset["generation"] = gen
    asset["source"] = "generated"
    asset["license"] = m.get("license") or "own"

    name = (m.get("name") or "").strip()
    if name and _allowed(asset, "name"):
        asset["name"] = name
        prov["name"] = "declared"

    atype = TYPE_MIGRATION.get(m.get("type") or "", m.get("type") or "")
    if atype in TYPES and _allowed(asset, "type"):
        asset["type"] = atype
        prov["type"] = "declared"
        # Classification follows the declared type (GEN assets have no
        # prefab; kind/placeable are scanner-owned flags, not provenance'd).
        asset["kind"] = kind_for_type(atype, False)
        asset["placeable"] = default_placeable(atype, asset["kind"])

    raw_role = m.get("semantic_role")
    if raw_role and _allowed(asset, "semantic_role"):
        role, detail = normalize_semantic_role(raw_role, m.get("semantic_detail") or raw_role)
        asset["semantic_role"] = role
        asset["semantic_detail"] = detail
        prov["semantic_role"] = "declared"

    new_tags = [t for t in (m.get("tags") or []) if isinstance(t, str) and _TOKEN_RE.match(t)]
    if new_tags and _allowed(asset, "tags"):
        merged = list(asset.get("tags") or [])
        for t in new_tags:
            if t not in merged:
                merged.append(t)
        asset["tags"] = merged
        prov["tags"] = "declared"

    desc = (m.get("description") or "").strip() or (gen.get("prompt") or "").strip()
    if desc and _allowed(asset, "description"):
        asset["description"] = desc
        prov["description"] = "declared"

    place_in = m.get("placement") or {}
    if place_in and _allowed(asset, "placement"):
        place = asset.setdefault("placement", {})
        if place_in.get("mount") is not None:
            place["mount"] = normalize_mount(place_in.get("mount"))
        if place_in.get("attachment") is not None:
            place["attachment"] = normalize_attachment(place_in.get("attachment"))
        for key in ("height", "orientation", "preferred_floors", "constraints", "preferred_contexts"):
            val = place_in.get(key)
            if val:
                place[key] = val
        prov["placement"] = "declared"

    kit = (m.get("kit") or "").strip() if isinstance(m.get("kit"), str) else None
    if kit and _allowed(asset, "module"):
        module = asset.setdefault("module", {})
        module["family"] = kit
        prov["module"] = "declared"

    sockets = m.get("sockets")
    if isinstance(sockets, list) and sockets and _allowed(asset, "part"):
        part = asset.setdefault("part", {})
        part["sockets"] = [dict(s, source=s.get("source") or "declared") for s in sockets if isinstance(s, dict)]
        prov["part"] = "declared"

    return asset
