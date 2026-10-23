"""``weapons export``: a per-game snapshot of the directory (spec 3.10) and its validator.

A snapshot is pack-derived data meant for a *game's* private repo, never for this one (INV-1), so the verb refuses an
output path inside the catalogs dir (except under its own ``weapons/snapshots/`` folder, W7b), a configured pack root or
this checkout. The file is deterministic (INV-4
style): sorted keys, 1-space indent, ``\\n``, no clock, no machine path, no hostname; ``scanned_at`` is copied from
the pack catalogs through the directory.

The default ``--frame item`` bakes every point of the geometry block through ``item_basis`` (a signed axis
permutation, so a rotation about the scene origin: no translation, no rounding drift). Fields that are *not*
coordinates, or that describe the mesh rather than the weapon, stay as measured: ``axes``, ``item_basis``,
``long_axis``, ``pivot_frac``, ``length_m``, the radii, the ``*_source`` labels, ``triangles`` and ``node_offset``
(the node's scene-space translation, which a consumer applies as ``item_basis * node_offset`` itself; AC34).

``--attachments`` (docs/weapon_attachments.md 7, slice W8d) is the only way the attachment data leaves the directory:
host ``geometry.mounts`` and the attachment part records (``attachment``) are added to the snapshot, filtered by
``--min-compat-tier`` / ``--keep-foreign-hosts`` and, in the item frame, baked through each record's OWN ``item_basis``
(a host's mounts through the host's, a part's anchor through the part's: the consumer rotates each mesh by its own
basis). Without the flag nothing changes: the output is the W7 one byte for byte (D-10, INV-19). Judgment calls, all
inline where they act and repeated in the W8d report: the pseudo role ``attachment`` of ``--roles``; the extra
``filter.keep_foreign_hosts`` key (only with ``--keep-foreign-hosts``); the attachment records an ``--ids-file`` export adds.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
from copy import deepcopy
from pathlib import Path

import yaml

from .. import __version__
from ..paths import find_config_file
from ..schema import pivot_from_aabb
from . import (
    COMPAT_TIERS,
    EXIT_OK,
    ROLES,
    InputError,
    RefusalError,
    SchemaError,
    digest,  # noqa: F401  (re-exported: the spec lists it in this module's surface)
    to_text,
    write_text_lf,
)
from .cli import _catalogs, _csv, _emit, _guarded
from .compat import export_compatible, export_pending
from .guards import refuse_export_target, repo_root
from .schema import check_export_attachment, validate_directory, validate_record

ENGINES = ("godot", "unity", "threejs", "all")
FRAMES = ("item", "asset")
PROFILES = ("private", "public")
# --engine -> the files.* keys it keeps. `all` keeps every key. threejs keeps glb_scale (AC26/AC37): the exported
# bounds are post-scale but the GLB file is not, so a consumer loading the mesh needs the factor to size it.
ENGINE_FILE_KEYS = {
    "godot": ("godot_scene",),
    "unity": ("unity_prefab", "unity_mesh", "unity_materials"),
    "threejs": ("glb", "glb_node", "glb_scale"),
}
# the engine names written into generated_from.filter.engines ("threejs" is the glb files)
ENGINE_LABEL = {"godot": "godot", "unity": "unity", "threejs": "glb", "all": "all"}
PUBLIC_KEYS = ("archetype", "family", "genre", "geometry", "hints", "id", "kind", "role", "visuals")
_POINTS = ("tip", "butt", "muzzle", "grip", "support")
# W8b/W8c: the host mounts and the review reasons they (and the compatibility pass) add exist only in the directory. The default export is byte-identical to
# W7's (D-10, INV-19), so the projection drops them; `--attachments` (W8d) brings the data back (mounts, attachment), not the reasons.
_MOUNT_REASONS = ("compat_cross_pack", "mount_ambiguous", "mount_estimated", "mount_missing", "twin_multi")
# `--attachments` keeps those reasons OUT too: the same snapshot must differ from the plain one only by the added keys (AC77),
# and what they say is in the data (`mounts` that are none, `pending_hosts`, the tiers). The anchor reasons
# (anchor_unmeasured, anchor_forward_unsure, attach_kind_unknown) are part of the record's confidence story (3.4.6) and stay.
ATTACHMENT_ROLE = "attachment"  # pseudo role of `--roles`: restricts the export to the attachment parts (with --attachments)
_BASE_GF_KEYS = ["tool", "weapon_version", "geometry_version", "rules_digest", "overrides_digest", "packs", "filter"]
_ATTACH_GF_KEYS = ["attach_version", "attach_rules_digest"]
_BASE_FILTER_KEYS = ["engines", "frame", "game", "roles"]
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_DRIVE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_PUBLIC_APPROVAL_KEY = "weapons_public_icons_approved"
SNAPSHOTS_DIRNAME = "snapshots"  # <catalogs>/weapons/snapshots/: the default output folder (spec 3.1)
_UNSAFE_STEM = re.compile(r'[\\/:*?"<>|\x00-\x1f]')  # path separators, drive/stream colon, wildcards, control chars


# -- item-frame bake --------------------------------------------------------------------------------------


def _rows(basis) -> list[tuple[int, int]]:
    """``[(source axis, sign)]`` per row of a signed-permutation ``item_basis``; ValueError otherwise."""
    out = []
    for row in basis:
        nz = [(i, int(v)) for i, v in enumerate(row) if v]
        if len(nz) != 1 or abs(nz[0][1]) != 1:
            raise ValueError(f"item_basis row {row!r} is not a signed axis")
        out.append(nz[0])
    if sorted(i for i, _ in out) != [0, 1, 2]:
        raise ValueError(f"item_basis {basis!r} does not permute the axes")
    return out


def _det(basis) -> int:
    m = [[int(v) for v in row] for row in basis]
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def _apply(rows: list[tuple[int, int]], p: list[float]) -> list[float]:
    """``item_basis * p``; ``+ 0.0`` turns a negated zero back into 0.0 so the bytes cannot flip."""
    return [sign * p[axis] + 0.0 for axis, sign in rows]


def bake_item_frame(geometry: dict) -> dict:
    """The geometry block in the item frame (forward +Z, up +Y); a new dict, the input is not modified."""
    rows = _rows(geometry["item_basis"])
    out = deepcopy(geometry)
    out["frame"] = "item"
    for key in _POINTS:
        if geometry.get(key) is not None:
            out[key] = _apply(rows, geometry[key])
    b = geometry["bounds"]
    lo, hi = _apply(rows, b["min"]), _apply(rows, b["max"])
    new_min = [min(a, c) for a, c in zip(lo, hi)]
    new_max = [max(a, c) for a, c in zip(lo, hi)]
    out["bounds"] = {
        "min": new_min, "max": new_max,
        "size": [b["size"][axis] for axis, _ in rows],  # a permutation of the measured size: no re-subtraction
        # the pivot label is relative to a y-up box, so it is re-derived in the item frame
        "pivot": pivot_from_aabb(new_min, new_max),
    }
    return out


# -- snapshot ---------------------------------------------------------------------------------------------


def _filter_files(files: dict, engines: set[str]) -> dict:
    if "all" in engines:
        return deepcopy(files)
    keep = {k for e in engines for k in ENGINE_FILE_KEYS[e]}
    return {k: deepcopy(v) for k, v in files.items() if k in keep}


def _public_record(rec: dict) -> dict:
    geom = rec["geometry"]
    return {
        "id": rec["id"], "kind": rec["kind"], "role": rec["role"], "archetype": rec["archetype"],
        "genre": rec["genre"], "family": rec["family"], "hints": deepcopy(rec["hints"]),
        "geometry": {"length_m": geom["length_m"] if geom else None},
        "visuals": {"icon": rec["visuals"]["icon"], "thumb": rec["visuals"]["thumb"]},
    }


def _bake_frame(rows: list[tuple[int, int]], frame: dict) -> dict:
    """A copy of an anchor / mount frame with ``point``, ``forward`` and ``up`` rotated by the basis (the other keys stay)."""
    out = dict(frame)
    for key in ("point", "forward", "up"):
        out[key] = _apply(rows, frame[key])
    return out


def _bake_mounts(rows: list[tuple[int, int]], mounts: dict) -> dict:
    """``geometry.mounts`` with every non-null frame baked; ``span_m``, ``bore_d_m`` and the labels are scalars and stay."""
    return {slot: (m if m["point"] is None else _bake_frame(rows, m)) for slot, m in mounts.items()}


def _export_attachment(att: dict, rows, *, min_tier: str, host_ids: set[str], keep_foreign: bool) -> dict:
    """The export form of an ``attachment`` block (C-19, C-23).

    ``compatible_hosts`` and ``pending_hosts`` are cut at ``min_tier`` by the same rule (``compat.export_compatible`` /
    ``export_pending``); a host outside the exported set is dropped unless ``keep_foreign``; ``pending_hosts`` become ids
    sorted by (tier rank, host). The anchor is baked through ``rows`` (the part's OWN ``item_basis``) when given;
    ``footprint`` is scalars and never baked.
    """
    out = deepcopy(att)
    listed = [e for e in att["compatible_hosts"] if keep_foreign or e["host"] in host_ids]
    pending = [e for e in att["pending_hosts"] if keep_foreign or e["host"] in host_ids]
    out["compatible_hosts"] = export_compatible(listed, min_tier)
    out["pending_hosts"] = export_pending(pending, min_tier)
    if rows is not None and out["anchor"] is not None:
        out["anchor"] = _bake_frame(rows, out["anchor"])
    return out


def _private_record(rec: dict, engines: set[str], frame: str, attach: dict | None = None) -> dict:
    """One full-profile snapshot record. ``attach`` (``--attachments``) is ``{min_tier, host_ids, keep_foreign}``; None
    keeps the W7 projection: no ``attachment`` key, no ``geometry.mounts``."""
    out = deepcopy(rec)
    out.pop("attachment", None)  # W8d adds it back behind --attachments; the default output stays the W7 one (D-10)
    out["files"] = _filter_files(rec["files"], engines)
    if frame == "item" and rec["geometry"] is not None:
        out["geometry"] = bake_item_frame(rec["geometry"])
    if out["geometry"] is not None:
        out["geometry"].pop("mounts", None)  # after the bake: bake_item_frame deep-copies the whole block
    out["review"]["reasons"] = [r for r in out["review"]["reasons"] if r not in _MOUNT_REASONS]
    if attach is not None:
        # each record is baked through its OWN item_basis: a host's mounts through the host's, a part's anchor through the
        # part's (C-20). Baking the part through its host's would put the part's frame in the wrong axes (AC77 mutation).
        geom = rec["geometry"]
        rows = _rows(geom["item_basis"]) if frame == "item" and geom is not None else None
        if geom is not None and "mounts" in geom:
            mounts = geom["mounts"]
            out["geometry"]["mounts"] = None if mounts is None else (
                _bake_mounts(rows, mounts) if rows is not None else deepcopy(mounts))
        if "attachment" in rec:
            out["attachment"] = None if rec["attachment"] is None else _export_attachment(rec["attachment"], rows, **attach)
    return out


def _attachment_scope(directory: dict, have: set[str], pack_ids, ids, min_tier: str) -> list[dict]:
    """The attachment part records ``--attachments`` adds to the exported set (spec 7: "added to the exported set").

    ``--packs``: every attachment part of those packs. ``--ids-file`` (judgment call: the file lists the weapons a game
    wants, not their accessories): the listed attachments plus the attachment parts of ANY pack that fit at least one
    exported host at ``min_tier`` or above (compatible or pending), so a BONDED-style id list still gets its scopes.
    ``have`` is the id set already chosen by role.
    """
    out = []
    for w in directory["weapons"]:
        att = w.get("attachment")
        if att is None or w["id"] in have:
            continue
        if pack_ids is not None:
            keep = w["pack"] in pack_ids
        else:
            hosts = {e["host"] for e in export_compatible(att["compatible_hosts"], min_tier)}
            hosts |= {e["host"] for e in att["pending_hosts"] if export_pending([e], min_tier)}
            keep = w["id"] in ids or bool(hosts & have)
        if keep:
            out.append(w)
    return out


def export_snapshot(
    directory: dict, *, game: str, pack_ids: set[str] | None, ids: set[str] | None, roles: set[str],
    engines: set[str], frame: str, profile: str, pack_meta: dict[str, dict], rules_digest: str,
    overrides_digest: str, attachments: bool = False, min_compat_tier: str = "same_pack_fit",
    keep_foreign_hosts: bool = False,
) -> dict:
    """The snapshot document (spec 3.10). ``engines`` holds CLI engine names (godot, unity, threejs, all).

    ``attachments`` is ``--attachments`` (docs/weapon_attachments.md 7): host mounts and the attachment part records are
    emitted and the header gains ``attach_version``, ``attach_rules_digest`` and ``filter.attachments``; off, the document is
    the W7 one. ``roles`` holds the real roles only: ``--roles attachment`` (a pseudo role, handled by the caller) just
    leaves it without ``whole``, so ``filter.roles`` never carries it and a consumer that validates the list against
    ``ROLES`` keeps working.
    """
    chosen = [
        w for w in directory["weapons"]
        if (pack_ids is None or w["pack"] in pack_ids) and (ids is None or w["id"] in ids) and w["role"] in roles
    ]
    attach = None
    if attachments:
        # (an ids file lists weapons: a part named in it is chosen by its role above, or here when its role was not asked)
        have = {w["id"] for w in chosen}
        chosen += _attachment_scope(directory, have, pack_ids, ids, min_compat_tier)
        attach = {"min_tier": min_compat_tier, "keep_foreign": keep_foreign_hosts,
                  "host_ids": {w["id"] for w in chosen}}
    chosen.sort(key=lambda w: w["id"])
    if profile == "public":
        weapons = [_public_record(w) for w in chosen]
    else:
        weapons = [_private_record(w, engines, frame, attach) for w in chosen]
    packs = sorted(pack_ids) if pack_ids is not None else sorted({w["pack"] for w in chosen})
    generated_from = {
        "tool": f"synty-inventory {__version__}",
        "weapon_version": directory["weapon_version"],
        "geometry_version": directory["geometry_version"],
        "rules_digest": rules_digest,
        "overrides_digest": overrides_digest,
        "packs": [
            {"pack": p, "scanned_at": (pack_meta.get(p) or {}).get("scanned_at"),
             "asset_count": (pack_meta.get(p) or {}).get("asset_count")}
            for p in packs
        ],
        "filter": {"game": game, "roles": sorted(roles), "engines": sorted({ENGINE_LABEL[e] for e in engines}),
                   "frame": frame},
    }
    if attachments:  # these keys exist ONLY with --attachments: the default header is the W7 one (C-24)
        generated_from["attach_version"] = directory["attach_version"]
        generated_from["attach_rules_digest"] = directory["attach_rules_digest"]
        generated_from["filter"]["attachments"] = True
        if keep_foreign_hosts:  # judgment call: lets `validate --snapshot` accept hosts outside the set (INV-14)
            generated_from["filter"]["keep_foreign_hosts"] = True
    return {"schema_version": 1, "generated_from": generated_from, "weapons": weapons}


# -- validation -------------------------------------------------------------------------------------------


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _leaks(doc) -> list[str]:
    """Drive letters, backslashes, absolute paths and the machine's hostname anywhere in the document."""
    host = socket.gethostname().strip()
    host_re = re.compile(rf"(?<![A-Za-z0-9]){re.escape(host)}(?![A-Za-z0-9])", re.IGNORECASE) if len(host) >= 4 else None
    out: list[str] = []
    for s in _strings(doc):
        if _DRIVE.search(s):
            out.append(f"drive-letter path: {s[:80]!r}")
        elif "\\" in s:
            out.append(f"backslash path: {s[:80]!r}")
        elif s.startswith(("/", "~", "file:")):
            out.append(f"absolute path: {s[:80]!r}")
        elif host_re and host_re.search(s):
            out.append(f"hostname: {s[:80]!r}")
    return out


def _check_geometry(geom: dict, frame: str, where: str) -> list[str]:
    errs: list[str] = []
    if geom["frame"] != frame:
        errs.append(f"{where}.geometry.frame: {geom['frame']!r} != filter.frame {frame!r}")
    try:
        _rows(geom["item_basis"])
        if _det(geom["item_basis"]) != 1:
            errs.append(f"{where}.geometry.item_basis: not a rotation (determinant != 1)")
    except ValueError as exc:
        errs.append(f"{where}.geometry.item_basis: {exc}")
    b = geom["bounds"]
    if any(lo > hi + 1e-9 for lo, hi in zip(b["min"], b["max"])):
        errs.append(f"{where}.geometry.bounds: min exceeds max")
    if frame == "item" and geom["tip"] is not None and geom["tip"][2] < geom["butt"][2] - 1e-4:
        errs.append(f"{where}.geometry: item frame must point forward along +Z (tip.z < butt.z)")
    return errs


def _record_errors(rec: dict, where: str, *, host_ids: set[str] | None = None, attachments: bool = False) -> list[str]:
    """``validate_record`` violations of one snapshot record, with ``files.glb_scale`` checked here.

    The weapon/1 JSON schema (weapons/schema.py) types every ``files.*`` value as null, string or string list, so it
    rejects the numeric ``glb_scale`` that AC26/AC37 let a threejs snapshot carry. Until the schema learns the key,
    the factor is validated here (a finite number > 0) and hidden from the schema check; every other violation is
    reported as before.

    A snapshot made with ``--attachments`` also carries ``geometry.mounts`` (validated by ``validate_record``: INV-15,
    INV-16, INV-18, with the item-frame expectation of a probe muzzle) and ``attachment`` in its EXPORT form
    (``pending_hosts`` are ids), which the directory schema does not describe: it is hidden from ``validate_record`` and
    checked by ``check_export_attachment`` (INV-14, INV-18). Without ``--attachments`` neither may appear at all.
    ``host_ids`` is the snapshot's id set (None: foreign hosts are allowed, ``filter.keep_foreign_hosts``).
    """
    errs: list[str] = []
    view = rec
    geom = rec.get("geometry")
    if not attachments:
        if "attachment" in rec:
            errs.append(f"{where}.attachment: present in a snapshot made without --attachments (D-10)")
        if isinstance(geom, dict) and "mounts" in geom:
            errs.append(f"{where}.geometry.mounts: present in a snapshot made without --attachments (D-10)")
    elif "attachment" in rec:
        att = rec["attachment"]
        if isinstance(att, dict):
            errs += check_export_attachment(att, rec.get("role"), where, host_ids)
        elif att is not None:
            errs.append(f"{where}.attachment: must be an object or null")
        view = {**view, "attachment": None}
    files = view.get("files")
    if not (isinstance(files, dict) and "glb_scale" in files):
        return errs + [f"{where}: {e}" for e in validate_record(view)]
    scale = files["glb_scale"]
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not (0 < scale < float("inf")):
        errs.append(f"{where}.files.glb_scale: must be a finite number greater than 0, got {scale!r}")
    view = {**view, "files": {k: v for k, v in files.items() if k != "glb_scale"}}
    return errs + [f"{where}: {e}" for e in validate_record(view)]


def check_snapshot(doc) -> list[str]:
    """Shape, frame, sortedness, engine filter and path-leakage violations of a snapshot document."""
    if not isinstance(doc, dict):
        return ["snapshot: top level must be an object"]
    if sorted(doc) != ["generated_from", "schema_version", "weapons"]:
        return [f"snapshot: top-level keys must be exactly schema_version, generated_from, weapons (got {sorted(doc)})"]
    errs: list[str] = []
    if doc["schema_version"] != 1:
        errs.append(f"schema_version: expected 1, got {doc['schema_version']!r}")
    gf = doc["generated_from"]
    # --attachments adds attach_version / attach_rules_digest / filter.attachments, and ONLY then (C-24)
    flt_in = gf.get("filter") if isinstance(gf, dict) else None
    attachments = isinstance(flt_in, dict) and "attachments" in flt_in
    want_gf = _BASE_GF_KEYS + (_ATTACH_GF_KEYS if attachments else [])
    if not isinstance(gf, dict) or sorted(gf) != sorted(want_gf):
        return errs + [f"generated_from: keys must be {', '.join(want_gf)}"]
    if not (isinstance(gf["tool"], str) and gf["tool"].startswith("synty-inventory ")):
        errs.append("generated_from.tool: must read 'synty-inventory <version>'")
    for key in ("weapon_version", "geometry_version"):
        if not (isinstance(gf[key], int) and gf[key] >= 1):
            errs.append(f"generated_from.{key}: must be a positive integer")
    if attachments:
        if not (isinstance(gf["attach_version"], int) and not isinstance(gf["attach_version"], bool)
                and gf["attach_version"] >= 1):
            errs.append("generated_from.attach_version: must be a positive integer")
    for key in ("rules_digest", "overrides_digest") + (("attach_rules_digest",) if attachments else ()):
        if not (isinstance(gf[key], str) and _HEX16.match(gf[key])):
            errs.append(f"generated_from.{key}: must be 16 lower-case hex characters")
    packs = gf["packs"]
    if not (isinstance(packs, list) and all(
            isinstance(p, dict) and sorted(p) == ["asset_count", "pack", "scanned_at"] for p in packs)):
        errs.append("generated_from.packs: must be a list of {pack, scanned_at, asset_count}")
    elif [p["pack"] for p in packs] != sorted(p["pack"] for p in packs):
        errs.append("generated_from.packs: must be sorted by pack")
    flt = gf["filter"]
    want_flt = _BASE_FILTER_KEYS + (["attachments"] if attachments else [])
    keep_foreign = attachments and "keep_foreign_hosts" in flt
    if keep_foreign:
        want_flt.append("keep_foreign_hosts")
    if not (isinstance(flt, dict) and sorted(flt) == sorted(want_flt)):
        return errs + [f"generated_from.filter: keys must be exactly {', '.join(want_flt)}"]
    for key in ("attachments", "keep_foreign_hosts"):
        if key in flt and flt[key] is not True:
            errs.append(f"generated_from.filter.{key}: present only as true")
    frame = flt["frame"]
    if frame not in FRAMES:
        errs.append(f"generated_from.filter.frame: {frame!r} not in {list(FRAMES)}")
    if not (isinstance(flt["game"], str) and flt["game"]):
        errs.append("generated_from.filter.game: must be a non-empty string")
    if not (isinstance(flt["roles"], list) and set(flt["roles"]) <= set(ROLES) and flt["roles"] == sorted(flt["roles"])):
        errs.append("generated_from.filter.roles: must be a sorted list of roles")
    labels = set(ENGINE_LABEL.values())
    if not (isinstance(flt["engines"], list) and set(flt["engines"]) <= labels and flt["engines"]):
        errs.append(f"generated_from.filter.engines: must be a non-empty list drawn from {sorted(labels)}")
    weapons = doc["weapons"]
    if not isinstance(weapons, list):
        return errs + ["weapons: must be a list"]
    ids = [w.get("id") if isinstance(w, dict) else None for w in weapons]
    if None in ids:
        return errs + ["weapons: every entry must be an object with an id"]
    if len(set(ids)) != len(ids):
        errs.append("weapons: duplicate ids")
    if ids != sorted(ids):
        errs.append("weapons: must be sorted by id")
    public = ["files" not in w for w in weapons]
    if any(public) and not all(public):
        errs.append("weapons: public-profile and full records are mixed")
    # INV-14: a host an attachment names must be in the exported set (the exporter drops the others), unless the snapshot
    # says it kept foreign hosts on purpose
    host_ids = None if keep_foreign else set(ids)
    for i, w in enumerate(weapons):
        where = f"weapons[{i}]"
        # with --attachments the attachment parts join the set whatever --roles asked for; a part without an attachment
        # block must still have its role listed
        attachment_part = attachments and w.get("role") == "part" and w.get("attachment") is not None
        if isinstance(flt.get("roles"), list) and w.get("role") not in flt["roles"] and not attachment_part:
            errs.append(f"{where}.role: {w.get('role')!r} not in filter.roles")
        if "files" not in w:  # public profile: exactly the public key list (INV-11)
            if sorted(w) != sorted(PUBLIC_KEYS):
                errs.append(f"{where}: public record keys must be exactly {list(PUBLIC_KEYS)}")
            elif sorted(w["geometry"] or {}) != ["length_m"] or sorted(w["visuals"] or {}) != ["icon", "thumb"]:
                errs.append(f"{where}: public geometry/visuals may carry only length_m / icon, thumb")
            continue
        errs += _record_errors(w, where, host_ids=host_ids, attachments=attachments)
        if w.get("geometry") and frame in FRAMES:
            errs += _check_geometry(w["geometry"], frame, where)
        engines = set(flt["engines"]) if isinstance(flt["engines"], list) else set()
        if engines and "all" not in engines:
            allowed = {k for lab, e in (("godot", "godot"), ("unity", "unity"), ("glb", "threejs"))
                       if lab in engines for k in ENGINE_FILE_KEYS[e]}
            extra = sorted(set(w["files"]) - allowed)
            if extra:
                errs.append(f"{where}.files: keys {extra} are outside the engine filter {sorted(engines)}")
    errs += [f"leak: {m}" for m in _leaks(doc)]
    return errs


def validate_snapshot(path) -> list[str]:
    """Violations of a snapshot file: unreadable JSON, non-canonical bytes, then ``check_snapshot``."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        return [f"snapshot unreadable: {exc}"]
    errs = check_snapshot(doc)
    if b"\r" in raw:
        errs.append("file: must use LF line endings")
    elif raw != to_text(doc).encode("utf-8"):
        errs.append("file: not in canonical form (sorted keys, 1-space indent, trailing newline)")
    return errs


# -- CLI --------------------------------------------------------------------------------------------------


def _public_approved(args) -> bool:
    """``weapons_public_icons_approved: true`` in config.yaml (not a path, so it is not in ``cfg``; spec B-1)."""
    path = find_config_file(getattr(args, "config", None))
    if path is None:
        return False
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and data.get(_PUBLIC_APPROVAL_KEY) is True


def _repo_root() -> Path | None:
    """This checkout (INV-1: a snapshot never lands in the public repo); a seam so tests can aim elsewhere."""
    return repo_root()


def _forbidden_roots(catalogs_dir: Path | None, cfg) -> list[Path]:
    """Folders a snapshot must not land in. ``catalogs_dir=None`` leaves the catalogs folder out (the default output
    ``<catalogs>/weapons/snapshots/`` is inside it by design, spec 3.1); the checkout and every pack root stay."""
    roots = [catalogs_dir, _repo_root()]
    roots += [v for k, v in cfg.items() if k != "catalogs" and isinstance(v, Path)]
    return [r.resolve() for r in roots if r is not None]


def kind_violations(directory: dict) -> list[str]:
    """Ids of the whole/emplaced records with ``kind: null`` (spec 3.4.2 PATCH W7b), in directory order."""
    return [w["id"] for w in directory["weapons"] if w.get("role") in ("whole", "emplaced") and w.get("kind") is None]


def default_snapshot_path(catalogs_dir: Path, game: str) -> Path:
    """``<catalogs>/weapons/snapshots/<game>.json``; ``game`` must be a safe file stem (no path parts)."""
    from .directory import weapons_dir

    if (not game or game != game.strip() or game in (".", "..") or game.endswith(".") or _UNSAFE_STEM.search(game)):
        raise InputError(f"--game {game!r} cannot be used as a file name for the default snapshot; "
                         "use a plain name (no path separators) or give --out")
    return weapons_dir(catalogs_dir) / SNAPSHOTS_DIRNAME / f"{game}.json"


def _read_ids(path: Path) -> set[str]:
    """One id per line (blank lines and ``#`` comments ignored), or a JSON list of ids."""
    if not path.is_file():
        raise InputError(f"ids file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError(f"ids file is not valid JSON: {exc}") from exc
        if not all(isinstance(i, str) for i in data):
            raise InputError("ids file: every entry must be a string")
        return set(data)
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")}


def _relocate_icons(snapshot: dict, src_base: Path, icons_dir: Path, out_file: Path) -> tuple[list, list[str]]:
    """Point every icon/thumb at ``icons_dir/<pack>/<name>`` relative to the snapshot file.

    Returns the ``(src, dst)`` copies to make and warnings. An icon whose file is missing becomes null (never a
    path to nothing). Nothing is copied here, so a later validation failure leaves the disk untouched.
    """
    import os

    copies: dict[Path, Path] = {}
    warnings: list[str] = []

    def move(rec_id: str, pack: str, holder: dict, key: str) -> None:
        rel = holder.get(key)
        if rel is None:
            return
        src = src_base / rel
        if not src.is_file():
            warnings.append(f"{rec_id}: {key} file missing, set to null")
            holder[key] = None
            return
        dst = icons_dir / pack / Path(rel).name
        try:
            holder[key] = Path(os.path.relpath(dst, out_file.parent)).as_posix()
        except ValueError as exc:  # another drive: no relative path exists
            raise InputError(f"--icons-dir cannot be made relative to the snapshot file: {exc}") from exc
        copies[src] = dst

    for w in snapshot["weapons"]:
        pack = w["id"].split("/", 1)[0]
        vis = w["visuals"]
        for key in ("icon", "thumb"):
            move(w["id"], pack, vis, key)
        for var in vis.get("variants") or []:
            move(w["id"], pack, var, "icon")
    return sorted(copies.items()), warnings


@_guarded
def cmd(args, cfg) -> int:
    from .directory import load_directory, weapons_dir

    attachments = bool(getattr(args, "attachments", False))
    min_tier = getattr(args, "min_compat_tier", None) or "same_pack_fit"
    keep_foreign = bool(getattr(args, "keep_foreign_hosts", False))
    engine = args.engine
    engines = {engine}
    frame, profile = args.frame, args.profile
    if engine not in ENGINES or frame not in FRAMES or profile not in PROFILES:
        raise InputError("bad --engine, --frame or --profile value")
    if min_tier not in COMPAT_TIERS:
        raise InputError(f"--min-compat-tier {min_tier!r} not in {list(COMPAT_TIERS)}")
    # the attachment flags act only with --attachments; refusing them otherwise beats a silent no-op that looks like data
    if not attachments and (keep_foreign or min_tier != "same_pack_fit"):
        raise InputError("--min-compat-tier and --keep-foreign-hosts only act with --attachments")
    if attachments and profile == "public":
        raise InputError("--attachments cannot be combined with --profile public (the public record has no geometry)")
    roles_arg = _csv(args.roles) or ["whole"]
    pseudo = ATTACHMENT_ROLE in roles_arg
    if pseudo and not attachments:
        raise InputError(f"--roles {ATTACHMENT_ROLE} needs --attachments")
    roles = set(ROLES) if "all" in roles_arg else set(roles_arg) - {ATTACHMENT_ROLE}
    if not roles <= set(ROLES):
        raise InputError(f"unknown role(s) {sorted(roles - set(ROLES))}; allowed: {list(ROLES)}, 'all'"
                         + (f" or '{ATTACHMENT_ROLE}'" if attachments else ""))

    # B-1: the public profile is refused before anything else is read or touched
    if profile == "public" and not _public_approved(args):
        raise RefusalError(
            f"--profile public is refused: set `{_PUBLIC_APPROVAL_KEY}: true` in config.yaml once Tom has confirmed "
            "that public icon renders are licence-safe (spec B-1)")

    catalogs_dir = _catalogs(args, cfg)
    explicit = bool(args.export_out)
    out_file = (Path(args.export_out) if explicit else default_snapshot_path(catalogs_dir, args.game)).resolve()
    # W7b: an explicit --out below the default folder is as safe as the default (the resolve() above has already folded
    # any `..`), so it skips the catalogs-dir refusal; pack roots, this checkout and the git check still apply
    snapshots_dir = (weapons_dir(catalogs_dir) / SNAPSHOTS_DIRNAME).resolve()
    skip_catalogs_root = not explicit or snapshots_dir in out_file.parents
    for root in _forbidden_roots(None if skip_catalogs_root else catalogs_dir, cfg):
        if out_file == root or root in out_file.parents:
            raise RefusalError(
                "refusing to write a snapshot inside the catalogs dir, a pack root or this repository "
                "(it is pack-derived data for a game's private repo, INV-1)", details={"root": root.name})
    refuse_export_target(out_file, repo=_repo_root())  # this checkout, or a git repo that tracks *.synty* files

    directory = load_directory(catalogs_dir)
    # W7b: a record with a null kind would make sit_armory reject the whole snapshot (ARM_E02). The validation below
    # refuses it too, but only with a positional message; name the ids first so the cure (rebuild) is obvious
    bad_kind = kind_violations(directory)
    if bad_kind:
        shown = ", ".join(bad_kind[:5]) + (f", ... ({len(bad_kind)} in all)" if len(bad_kind) > 5 else "")
        raise SchemaError(
            f"{len(bad_kind)} whole/emplaced record(s) have kind null, so the export would write a snapshot "
            f"that consumers reject: {shown}; rebuild the directory with `weapons build` (kind is inferred) or set a "
            "kind override", details={"kind_null_ids": bad_kind[:25]})
    problems = validate_directory(directory)
    if problems:
        raise SchemaError("the weapon directory violates weapon-directory/1:\n  " + "\n  ".join(problems[:25]),
                          details={"errors": problems})
    pack_meta = {p["pack"]: p for p in directory["packs"]}
    pack_ids = ids = None
    if args.packs:
        pack_ids = set(_csv(args.packs) or [])
        unknown = sorted(pack_ids - set(pack_meta))
        if unknown:
            raise InputError(f"unknown pack(s) in the directory: {', '.join(unknown)}", details={"unknown": unknown})
    else:
        ids = _read_ids(Path(args.ids_file))
        absent = sorted(ids - {w["id"] for w in directory["weapons"]})
        if absent:
            raise InputError(f"{len(absent)} id(s) are not in the directory; a snapshot must not silently shrink",
                             details={"missing": absent})

    if attachments and not (directory.get("attach_version") and directory.get("attach_rules_digest")):
        raise InputError("the weapon directory predates attachments (no attach_version in its header): "
                         "run `weapons build` first")
    snapshot = export_snapshot(
        directory, game=args.game, pack_ids=pack_ids, ids=ids, roles=roles, engines=engines, frame=frame,
        profile=profile, pack_meta=pack_meta, rules_digest=directory["rules_digest"],
        overrides_digest=directory["overrides_digest"], attachments=attachments, min_compat_tier=min_tier,
        keep_foreign_hosts=keep_foreign,
    )
    copies: list = []
    warnings: list[str] = []
    if args.icons_dir:
        copies, warnings = _relocate_icons(snapshot, weapons_dir(catalogs_dir), Path(args.icons_dir).resolve(),
                                           out_file)
    errors = check_snapshot(snapshot)
    if errors:
        raise SchemaError("the snapshot violates the export contract:\n  " + "\n  ".join(errors[:25]),
                          details={"errors": errors})
    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    write_text_lf(out_file, to_text(snapshot))
    summary = {"ok": True, "weapons": len(snapshot["weapons"]),
               "packs": [p["pack"] for p in snapshot["generated_from"]["packs"]],
               "frame": frame, "profile": profile, "icons_copied": len(copies), "warnings": warnings}
    if attachments:  # an extra key only for the new mode: the plain run prints what it always printed
        summary["attachments"] = sum(1 for w in snapshot["weapons"] if w.get("attachment"))
    _emit(summary)
    return EXIT_OK
