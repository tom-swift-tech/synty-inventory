"""``synty-inventory weapons ...`` verb group (spec 3.2).

Every verb of the spec is registered here, so later slices add modules, not registrations: a verb whose module
does not exist yet answers ``{"ok": false, "error": "not built in this checkout"}`` with exit 2. A later slice
provides ``synty_inventory.weapons.<module>.cmd(args, cfg) -> int`` for its verb and the stub steps aside.

All verbs print JSON on stdout. Exit codes: 0 ok, 2 bad input, 3 refusal, 4 below --min-coverage, 5 renderer
unavailable, 6 schema violation.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from . import (
    ARCHETYPES,
    EXIT_BAD_INPUT,
    EXIT_COVERAGE,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_SCHEMA,
    COMPAT_TIERS,
    GENRES,
    KINDS,
    ROLES,
    STATUSES,
    WeaponsError,
)
from .guards import ensure_sole_runner

# verb -> module that implements it (None = implemented in this file)
_LATER_MODULES = {
    "icons": "icons",
    "review": "review",
    "apply-corrections": "corrections",
    "export": "export",
    "attach-eval": "eval",  # W8c
    "attach-preview": "preview",  # W8d
    "attach-spotcheck": "spotcheck",  # G1 S9
}
# the slice that provides each later verb that has no module yet, named in the "not built" answer
_BUILT_BY = {"attach-eval": "W8c", "attach-preview": "W8d", "attach-spotcheck": "G1 S9"}


def _emit(obj) -> None:
    from ..cli import emit_json  # lazy: the root cli imports this module at import time

    emit_json(obj)


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()]


def _error(message: str, code: int, **extra) -> int:
    _emit({"ok": False, "error": message, **extra})
    return code


def _catalogs(args, cfg) -> Path:
    from ..cli import _catalogs as root_catalogs

    return root_catalogs(args, cfg)


def _not_built(args, cfg, verb: str) -> int:
    module = _LATER_MODULES[verb]
    full = f"synty_inventory.weapons.{module}"
    try:
        mod = importlib.import_module(full)
    except ModuleNotFoundError as exc:
        if exc.name != full:
            raise  # a real import failure inside an existing module
        extra = {"hint": f"not implemented until slice {_BUILT_BY[verb]}"} if verb in _BUILT_BY else {}
        return _error("not built in this checkout", EXIT_BAD_INPUT, verb=verb, **extra)
    return mod.cmd(args, cfg)


def _guarded(fn):
    """Run a verb, turning ``WeaponsError`` into JSON + its exit code."""

    def wrapper(args, cfg) -> int:
        try:
            return fn(args, cfg)
        except WeaponsError as exc:
            return _error(str(exc), exc.code, **exc.details)

    wrapper.__name__ = fn.__name__
    return wrapper


@_guarded
def cmd_build(args, cfg) -> int:
    from .directory import (
        EXCLUDED_NAME,
        DIRECTORY_NAME,
        build_directory_report,
        read_json,
        weapons_dir,
        write_directory,
    )
    from ..cli import _threejs_v2
    from .fit_geometry import FIT_CACHE_NAME, load_fit_cache, save_fit_cache
    from .geometry import CACHE_NAME, load_cache, save_cache
    from .overrides import load_overrides
    from .rules import load_rules

    ensure_sole_runner()  # exit 2 naming the pid when another inventory process runs: both write cache files
    catalogs_dir = _catalogs(args, cfg)
    packs = _csv(args.pack)
    rules = load_rules()
    overrides = load_overrides()
    base = None
    wdir = weapons_dir(catalogs_dir)
    if packs and (wdir / DIRECTORY_NAME).is_file() and (wdir / EXCLUDED_NAME).is_file():
        base = (read_json(wdir / DIRECTORY_NAME), read_json(wdir / EXCLUDED_NAME))
    threejs_v2 = _threejs_v2(cfg)
    cache_path = wdir / CACHE_NAME
    cache = {} if args.rebuild else load_cache(cache_path)
    # G1 (spec 3.11, plan S9): the host features of the fit gate are cached beside the geometry cache, in <catalogs>/weapons/_fit_cache.json. Its
    # entries carry their own key (GLB sha256, node, scale, versions, attach_rules_digest, the fit code digests), so a stale file only misses
    fit_path = wdir / FIT_CACHE_NAME
    fit_cache = {} if args.rebuild else load_fit_cache(fit_path)
    fit_before = json.dumps(fit_cache, sort_keys=True)
    directory, excluded, report = build_directory_report(
        catalogs_dir, packs=packs, rules=rules, overrides=overrides, measure=not args.no_geometry, base=base,
        threejs_v2_dir=threejs_v2, geometry_cache=cache, fit_cache=fit_cache,
        # the configured per-pack extracted trees: variant discovery (spec 3.7) lists the colourways found there
        extracted_root=Path(cfg["extracted_root"]) if cfg.get("extracted_root") else None,
    )
    dpath, epath = write_directory(catalogs_dir, directory, excluded)
    report["directory"] = dpath.name
    if args.no_geometry:
        report["geometry"] = "skipped (--no-geometry)"
    elif threejs_v2 is None:
        report["geometry"] = "skipped (threejs_v2 not configured)"
    else:
        report["geometry"] = "measured"
        if cache and report["geometry_stats"]["decoded"]:
            save_cache(cache_path, cache)  # only when something was decoded: a cache-hit run rewrites nothing
        if fit_cache and json.dumps(fit_cache, sort_keys=True) != fit_before:
            save_fit_cache(fit_path, fit_cache)  # likewise: only a changed cache is written
    if args.report:
        rpath = Path(args.report)
        rpath.parent.mkdir(parents=True, exist_ok=True)
        rpath.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    ok = True
    notes: list[str] = []
    if args.strict and report["stale_overrides"]:
        ok = False
        notes.append("stale overrides with --strict")
        code = EXIT_REFUSED
    elif args.min_coverage is not None and report["geometry_coverage"] < args.min_coverage:
        ok = False
        notes.append(f"geometry coverage {report['geometry_coverage']} below --min-coverage {args.min_coverage}")
        code = EXIT_COVERAGE
    else:
        code = EXIT_OK
    _emit({"ok": ok, "notes": notes, "report": report})
    return code


def _resolve_id(directory: dict, wanted: str) -> dict:
    weapons = directory["weapons"]
    if "/" in wanted:
        for w in weapons:
            if w["id"] == wanted:
                return w
        raise WeaponsError(f"no weapon with id {wanted!r}", EXIT_BAD_INPUT)
    hits = [w["id"] for w in weapons if w["asset_id"] == wanted]
    if not hits:
        raise WeaponsError(f"no weapon with asset id {wanted!r}", EXIT_BAD_INPUT)
    if len(hits) > 1:
        raise WeaponsError(
            f"asset id {wanted!r} is ambiguous; use one of the qualified ids", EXIT_BAD_INPUT,
            {"candidates": sorted(hits)},
        )
    return next(w for w in weapons if w["id"] == hits[0])


@_guarded
def cmd_show(args, cfg) -> int:
    from .directory import load_directory

    directory = load_directory(_catalogs(args, cfg))
    _emit({"ok": True, "weapon": _resolve_id(directory, args.id)})
    return EXIT_OK


def _row(w: dict) -> dict:
    return {
        "id": w["id"], "role": w["role"], "kind": w["kind"], "archetype": w["archetype"], "genre": w["genre"],
        "hold_class": w["hold_class"], "confidence": w["review"]["confidence"], "status": w["review"]["status"],
        "flags": w["flags"],
    }


@_guarded
def cmd_list(args, cfg) -> int:
    from .directory import load_directory

    directory = load_directory(_catalogs(args, cfg))
    packs = set(_csv(args.pack) or [])
    rows = []
    for w in directory["weapons"]:
        if packs and w["pack"] not in packs:
            continue
        if args.kind and w["kind"] != args.kind:
            continue
        if args.role and w["role"] != args.role:
            continue
        if args.archetype and w["archetype"] != args.archetype:
            continue
        if args.genre and w["genre"] != args.genre:
            continue
        if args.status and w["review"]["status"] != args.status:
            continue
        if args.max_confidence is not None and w["review"]["confidence"] > args.max_confidence:
            continue
        rows.append(_row(w))
    total = len(rows)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    _emit({"ok": True, "total": total, "count": len(rows), "weapons": rows})
    return EXIT_OK


@_guarded
def cmd_validate(args, cfg) -> int:
    from .directory import DIRECTORY_NAME, EXCLUDED_NAME, read_json, weapons_dir
    from .overrides import load_overrides
    from .rules import load_rules, shadowed_rules
    from .schema import validate_directory

    if args.snapshot:
        from .export import validate_snapshot

        if not Path(args.snapshot).is_file():
            raise WeaponsError(f"snapshot file not found: {args.snapshot}", EXIT_BAD_INPUT)
        errors = validate_snapshot(args.snapshot)
        _emit({"ok": not errors, "snapshot": "invalid" if errors else "ok", "errors": errors})
        return EXIT_SCHEMA if errors else EXIT_OK
    problems: dict[str, list] = {}
    rules = load_rules()  # SchemaError -> exit 6
    shadowed = shadowed_rules(rules)
    if shadowed:
        problems["shadowed_rules"] = shadowed
    load_overrides()  # SchemaError -> exit 6

    result: dict = {"rules": "ok" if not shadowed else "shadowed", "overrides": "ok", "directory": "absent"}
    if args.directory:
        dpath = Path(args.directory)
        if not dpath.is_file():
            raise WeaponsError(f"directory file not found: {dpath}", EXIT_BAD_INPUT)
    else:
        dpath = weapons_dir(_catalogs(args, cfg)) / DIRECTORY_NAME
    if dpath.is_file():
        epath = dpath.with_name(EXCLUDED_NAME)
        excluded = read_json(epath) if epath.is_file() else None
        errors = validate_directory(read_json(dpath), excluded)
        result["directory"] = "ok" if not errors else "invalid"
        if errors:
            problems["directory_errors"] = errors
    result["ok"] = not problems
    result.update(problems)
    _emit(result)
    return EXIT_OK if not problems else EXIT_SCHEMA


# -- attach-calibrate: the oracle (docs/weapon_attach_geometry.md 3.2, 3.11; plan S9) -------------------------------------------------------
#
# ``calibrate`` is pure (AC144), so this is where files are read. A built directory has lost part of the authored assemblies (a preset's
# ``refuse_filled`` empties the ``occupied_by`` of its filled slots, a policy refusal turns a slot ``none``), so the oracle is re-derived from the
# directory records and the GLBs by the SAME steps ``mounts.build_mounts`` and ``fit_geometry._compute`` take: the child vocabulary and the body
# filter give the baked children, ``locate_by_translation`` the fused parts of a preset, the A1 twin entries the twins. Every positive is handed to
# ``calibrate.observe_positive`` as the plain dict that module documents. A positive's ``tags`` are its class key, ``<slot>:<class>``, which is
# what ``fit_geometry.exceptions`` lists (4.2: reasons by class, never asset ids).
#
# Populations (S10a). The positives are the spec's, and each row prints the spec's count beside its own: the locator searches every part of the pack, an
# attachment block or not (AC131: 163 placements), and runs on every preset, a host or not (the Heavy and Complex presets are authored assemblies too); a
# baked glass sheet is no optic (the rules' ``baked_sights.glass_tokens``); a baked magazine against its own well is no judgment, so the well row holds the
# twin magazines (4.2). What is left out is counted under ``not_positives``, never dropped silently.


def _fused_node(point_fsu) -> str:
    """The seat node of a preset's fused part: WHERE it stands (its seat point in the host's (f, s, u) frame, to the millimetre), not which part it is.
    The locator finds the variants of one fitting (two scope models cut from the same mesh) at the same spot, and one spot is one seat (C1)."""
    return "fused@" + ",".join(f"{c:.3f}" for c in point_fsu)


def _gather_oracle(directory: dict, threejs: Path, rules: dict, packs: set[str] | None) -> dict:
    """``{observations, toothed, frame, positives, hosts, skipped}``: the observations of every positive of the directory's eligible hosts.

    ``toothed`` / ``frame`` are the host ids whose reduced mesh carries a toothed run, and the hosts whose forward axis the frame vote moved
    (the two sheets of ``attach-preview``). ``positives`` counts the positives per ``<slot>:<class>``, ``skipped`` the hosts left out by reason.
    ``placements`` counts the locator's placements as AC131 does (by the part's block slot, ``other`` without one), ``preset_only_hosts`` the presets that
    are no host (only their located parts are positives) and ``not_positives`` what was seen and left out (glass sheets, baked magazines)."""
    import dataclasses

    import numpy as np

    from ..naming import SKIP_STEM_RE
    from ..sources.glb_geometry import load_triangles
    from ..sources.glb_measure import read_glb_json
    from . import calibrate as fc
    from . import fit_geometry as fit
    from . import geometry, mounts
    from .attach import measure_anchor, place
    from .mount_probe import end_ring_d
    from .rules import attachment_rules

    tables = attachment_rules(rules)
    fit_rules = tables.get("fit_geometry")
    if not fit_rules:
        raise WeaponsError("the rules carry no attachment_rules.fit_geometry block: there is nothing to calibrate", EXIT_SCHEMA)
    # the locator searches every part of the host's pack that has a GLB (AC131), an attachment block or not: a body part has none, and so does the Military
    # muzzle brake (spec Q-G9). The twins are the parts whose block lists a twin entry.
    parts = [w for w in directory["weapons"] if w.get("role") == "part" and (w.get("files") or {}).get("glb")]

    def fit_slot(rec: dict) -> str | None:
        """The slot a located part fills: its attachment block's, else the geometry slot the child vocabulary (``mounts.matching_slots``) reads from its
        name (``brake`` is a muzzle device), else None (a body part: it fills nothing)."""
        if rec.get("attachment"):
            return rec["attachment"]["slot"]
        named = [s for s in mounts.matching_slots(rec["asset_id"], tables) if s in fit.FIT_SLOTS]
        return named[0] if named else None

    slot_of = {rec["id"]: fit_slot(rec) for rec in parts}
    twins: dict[tuple[str, str], list[tuple[dict, dict]]] = {}  # (host, slot) -> [(part record, its twin entry)]
    for part in parts:
        if not part.get("attachment"):
            continue
        for e in part["attachment"]["compatible_hosts"]:
            if e["tier"] == "twin":
                twins.setdefault((e["host"], part["attachment"]["slot"]), []).append((part, e))
    mesh_memo: dict[str, tuple | None] = {}

    def part_mesh(rec: dict):
        """``(verts, tris)`` of a part record, collision hulls dropped (as the preset's fused-part set loads it), or None."""
        if rec["id"] not in mesh_memo:
            files = rec["files"]
            got = load_triangles(threejs / files["glb"], files.get("glb_node") or None,
                                 exclude=lambda n: bool(SKIP_STEM_RE.search(n or "")), scale=float(files.get("glb_scale") or 1.0))
            ok = got is not None and len(got[0]) and len(got[1])
            mesh_memo[rec["id"]] = (np.asarray(got[0], dtype=np.float64), np.asarray(got[1], dtype=np.int64)) if ok else None
        return mesh_memo[rec["id"]]

    anchor_memo: dict[str, tuple] = {}

    def part_anchor(rec: dict) -> tuple:
        """``(anchor, footprint)`` of a located part: its block's, else measured from its mesh for the slot its name reads (as a baked child is), else
        ``(None, None)``."""
        if rec.get("attachment"):
            return rec["attachment"]["anchor"], rec["attachment"]["footprint"]
        if rec["id"] not in anchor_memo:
            got = part_mesh(rec) if slot_of[rec["id"]] else None
            m = measure_anchor(got[0], slot_of[rec["id"]]) if got is not None else None
            anchor_memo[rec["id"]] = (m["anchor"], m["footprint"]) if m and m["anchor"] is not None else (None, None)
        return anchor_memo[rec["id"]]

    observations: list[dict] = []
    positives: dict[str, int] = {}
    skipped: dict[str, int] = {}
    placed: dict[str, int] = {}
    not_positives: dict[str, int] = {}
    preset_only_hosts = 0
    toothed_hosts: set[str] = set()
    frame_hosts: set[str] = set()
    used = 0
    empty = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))

    for host in sorted((w for w in directory["weapons"] if not packs or w["pack"] in packs), key=lambda w: w["id"]):
        geo, files = host.get("geometry"), host.get("files") or {}
        if not geo or not geo.get("axes") or not files.get("glb"):
            continue
        is_host = bool(geo.get("mounts")) and mounts.eligible(host["role"], host["kind"], host["hold_class"])
        # a preset that is no host (Military's Heavy and Complex presets: hold class none, no mounts) is still an authored assembly, and AC131 locates on all
        # 14 presets. Only its located parts are positives: it has no mounts, no baked children, no twins and no frame vote of its own (spec 3.2)
        if not is_host and not (host["role"] == "whole" and mounts.is_filled_host(host["asset_id"], tables)):
            continue
        path = threejs / files["glb"]
        glb_node, scale = files.get("glb_node") or None, float(files.get("glb_scale") or 1.0)
        whole = mounts._load_mesh(path, glb_node, scale, frozenset()) if path.is_file() else None
        if whole is None:
            skipped["glb_unreadable"] = skipped.get("glb_unreadable", 0) + 1
            continue
        axes = {"forward": geo["axes"]["forward"], "up": geo["axes"]["up"]}
        basis = fit.frame_basis(axes)
        verts_all = np.asarray(whole[0], dtype=np.float64)
        f_idx = "xyz".index(axes["forward"][1])
        f_sign = 1 if axes["forward"][0] == "+" else -1

        # -- the frame (spec 3.3). The vote is not stored in a record, so it is read back: the voted axis differs from the bounding-box axis
        # (``geometry.long_axis``), or, when it does not, a body axis that differs from the record's is the conflict the vote kept the build's frame on
        if is_host:
            body = geometry._body_vertices(path, glb_node, scale, rules, verts_all)
            changed = axes["forward"][1] != geo["long_axis"]
            if not changed and geometry._pick_long_axis(np.ptp(body, axis=0), 2) != f_idx:
                skipped["frame_conflict"] = skipped.get("frame_conflict", 0) + 1  # INV-27: no detector runs on it, so it is no positive
                continue
            if changed:
                frame_hosts.add(host["id"])
                ring = end_ring_d(body, f_idx, f_sign, geometry._FRAME_END_SLAB_M)
                if ring is not None:
                    observations.append(fc.frame_observation(host["id"], ring))
            used += 1
        else:
            preset_only_hosts += 1

        # -- the baked children of the four slots, as build_mounts finds them (the body filter included, the policy refusals not) --------------
        candidates = mounts.mesh_nodes(read_glb_json(path), glb_node)
        vert_memo: dict[str, np.ndarray | None] = {}

        def vertices(name: str, path=path, glb_node=glb_node, scale=scale, vert_memo=vert_memo):
            if name not in vert_memo:
                vert_memo[name] = mounts._load(path, name, glb_node, scale)
            return vert_memo[name]

        volume = mounts._volume(verts_all)
        by_slot: dict[str, list[str]] = {slot: [] for slot in fit.FIT_SLOTS}
        for name in sorted(candidates) if is_host else ():
            slots = mounts.matching_slots(name, tables)
            if not slots:
                continue
            v = vertices(name)
            if v is not None and volume > 1e-9 and mounts._volume(v) >= mounts._BODY_FRAC * volume:
                continue  # the body of the gun, not a baked child
            for slot in slots:
                if slot in by_slot:
                    by_slot[slot].append(name)
        # a glass sheet (a ``baked_sights.glass_tokens`` word in the child's name) is dropped from the host mesh like any child, but it is no optic: a 3 mm
        # foot that is no clamp. The rules' own classification, as ``build_mounts`` reads it
        glass = set(mounts.baked_children(candidates, host["asset_id"], tables, vertices, verts_all, axes, volume)["glass"]) if is_host else set()
        measured = {slot: mounts._measure_children(vertices, slot, by_slot[slot], tables.get("anchor"))
                    for slot in ("optic", "underbarrel", "magazine")}
        listed = {slot: sorted(n for n in by_slot[slot] if n in measured[slot]) for slot in measured}

        # -- a preset's fused parts (spec 3.2): the parts of the host's pack the locator finds in its mesh --------------------------------------
        placements: list = []
        located_mesh: dict[str, np.ndarray] = {}
        located_rec: dict[str, dict] = {}
        if mounts.is_filled_host(host["asset_id"], tables):
            for rec in (p for p in parts if p["pack"] == host["pack"]):
                got = part_mesh(rec)
                if got is None:
                    continue
                found = fit.locate_by_translation(verts_all, got[0], fit_rules)
                placements += [dataclasses.replace(pl, part=rec["id"]) for pl in found]
                if found:
                    located_mesh[rec["id"]], located_rec[rec["id"]] = got[0], rec
        for pl in placements:  # AC131 counts a placement by its part's block slot, "other" for a part without one
            key = (located_rec[pl.part].get("attachment") or {}).get("slot") or "other"
            placed[key] = placed.get(key, 0) + 1
        filling = [pl for pl in placements if slot_of[pl.part]]
        reduced_memo: dict[frozenset, tuple | None] = {}

        def reduced(drop: frozenset, path=path, glb_node=glb_node, scale=scale, basis=basis, filling=filling,
                    located_mesh=located_mesh, reduced_memo=reduced_memo):
            """The host minus ``drop`` and minus the located slot parts, in the (f, s, u) frame (as ``fit_geometry._compute`` reduces it)."""
            if drop not in reduced_memo:
                got = mounts._load_mesh(path, glb_node, scale, drop)
                if got is None:
                    reduced_memo[drop] = None
                else:
                    v, t = np.asarray(got[0], dtype=np.float64), np.asarray(got[1], dtype=np.int64)
                    if filling:
                        v, t = fit.strip(v, t, filling, located_mesh, fit_rules)
                    reduced_memo[drop] = (fit.to_fsu(basis, v), t)
            return reduced_memo[drop]

        def fsu(point, basis=basis):
            return tuple(float(c) for c in fit.to_fsu(basis, [point])[0])

        # -- the centreline and the muzzle seat of the real pipeline: the A0 probe on the host minus its muzzle children ----------------------
        muzzle_children = frozenset(by_slot["muzzle"])
        muzzle_v = verts_all if not muzzle_children else mounts._load(path, None, glb_node, scale, muzzle_children)
        point_s = bore_source = None
        # a preset that is no host has no muzzle mount, so spec 3.4 step 1 takes its second branch: the middle of the side extent, and no mount bore source
        if muzzle_v is not None and is_host:
            point, _src, face = geometry.muzzle_probe(muzzle_v, axes["forward"], axes["up"])
            point_s = float(np.dot([round(float(c), 4) for c in point], basis[1]))
            bore_source = mounts.bore_diameter(face, f_idx)[1]  # the mount's: it only says that the muzzle mount found a face (E3.2); it is not evidence (i)
        muzzle_mesh = reduced(muzzle_children)
        # E3.1 / E3.2: evidence (i) and the barrel face's OD are read on the stripped mesh by the helper the build uses, so the two cannot drift. Not for a
        # preset that is no host (no mount, bore_source None): it has no evidence (i)
        stripped_face = mounts.stripped_muzzle_face(muzzle_mesh[0], muzzle_mesh[1]) if muzzle_mesh is not None and bore_source is not None else None
        s0 = fc.centreline(muzzle_mesh, reduced(frozenset()), point_s, bore_source, fit_rules, stripped_face=stripped_face)
        sight = (geo.get("mounts") or {}).get("sight_front")
        sight_f = float(np.dot(sight["point"], basis[0])) if sight and sight.get("source") == "probe" and sight.get("point") else None

        # C1: every positive names its ``seat_node`` (plan 9.6 ruling 5; a seat is (host, slot, node)): a baked child is its own node, a twin takes the node of
        # the baked child it is seated on (so it shares that child's seat), a preset's fused part takes the node of the spot it stands at (``_fused_node``).
        # ``calibrate`` only counts them
        def add(pos: dict, host=host) -> None:
            pos.update(host=host["id"], tags=[f"{pos['slot']}:{pos['cls']}"])
            positives[pos["tags"][0]] = positives.get(pos["tags"][0], 0) + 1
            observations.extend(fc.observe_positive(pos, fit_rules))

        # -- optic (top) and underbarrel (bottom): baked children, A1 twins, located parts ----------------------------------------------------
        for slot, side in (("optic", "top"), ("underbarrel", "bottom")):
            names = listed[slot]
            mesh = reduced(frozenset(names)) or empty
            if is_host and fc.toothed(mesh, side, s0, fit_rules):
                toothed_hosts.add(host["id"])

            def rail(cls, label, node, point, footprint, slot=slot, mesh=mesh, s0=s0, sight_f=sight_f):
                add({"cls": cls, "slot": slot, "part": label, "seat_node": node, "mesh": mesh, "s0": s0, "seat": fsu(point),
                     "foot_length_m": footprint.get("foot_length_m"), "foot_width_m": footprint.get("foot_width_m"),
                     "sight_f": sight_f if slot == "optic" else None})

            for name in names:
                if slot == "optic" and name in glass:
                    not_positives["optic:glass"] = not_positives.get("optic:glass", 0) + 1
                    continue
                anchor, footprint, _vol = measured[slot][name]
                rail("baked", name, name, anchor["point"], footprint)
            for rec, entry in twins.get((host["id"], slot), ()):
                child = (entry.get("replaces") or [None])[0]
                child = child if child in measured[slot] else (mounts._seat(measured[slot]) if measured[slot] else None)
                if child is not None and rec["attachment"]["anchor"] is not None:
                    rail("twin", rec["id"], child, measured[slot][child][0]["point"], rec["attachment"]["footprint"])
            for pl in placements:
                rec = located_rec[pl.part]
                anchor, footprint = part_anchor(rec)
                if slot_of[rec["id"]] == slot and anchor is not None:
                    at = np.asarray(anchor["point"]) + np.asarray(pl.t)
                    rail("preset", rec["id"], _fused_node(fsu(at)), at, footprint)

        # -- muzzle: the barrel end of the host minus its muzzle devices, against each device's mating face -----------------------------------
        def device(cls, label, node, verts, anchor, footprint, point, axis, muzzle_mesh=muzzle_mesh, bore_source=bore_source, stripped_face=stripped_face,
                   basis=basis):
            add({"cls": cls, "slot": "muzzle", "part": label, "seat_node": node, "mesh": muzzle_mesh or empty, "bore_source": bore_source, "stripped_face": stripped_face,
                 "seat": fsu(point),
                 "axis_fsu": tuple(float(c) for c in fit.to_fsu(basis, [axis])[0]), "mate_d_m": (footprint or {}).get("mate_d_m"),
                 "device": {"verts": verts, "anchor": anchor}})

        baked_anchor: dict[str, tuple] = {}
        for name in by_slot["muzzle"]:
            v = vertices(name)
            got = measure_anchor(v, "muzzle") if v is not None else None
            if got is not None and got["anchor"] is not None:
                baked_anchor[name] = (v, got["anchor"], got["footprint"])
                device("baked", name, name, v, got["anchor"], got["footprint"], got["anchor"]["point"], got["anchor"]["up"])
        for rec, entry in twins.get((host["id"], "muzzle"), ()):
            child = (entry.get("replaces") or [None])[0]
            child = child if child in baked_anchor else (sorted(baked_anchor)[0] if baked_anchor else None)
            got = part_mesh(rec)
            if child is not None and got is not None and rec["attachment"]["anchor"] is not None:  # seated where the device it twins stands
                seat = baked_anchor[child][1]
                device("twin", rec["id"], child, got[0], rec["attachment"]["anchor"], rec["attachment"]["footprint"], seat["point"], seat["up"])
        for pl in placements:
            rec = located_rec[pl.part]
            anchor, footprint = part_anchor(rec)
            if slot_of[rec["id"]] == "muzzle" and anchor is not None:
                at = np.asarray(anchor["point"]) + np.asarray(pl.t)
                device("preset", rec["id"], _fused_node(fsu(at)), located_mesh[rec["id"]], anchor, footprint, at, anchor["up"])

        # -- magazine: the well of a baked magazine against the entry section of the magazine on its seat ----------------------------------
        def well_pos(cls, label, child, part_verts, part_tris, path=path, scale=scale, basis=basis):
            child_got = load_triangles(path, child, exclude=mounts._collision, scale=scale)
            # E3.6 (F1): the reference host drops every magazine node of the mount, as ``fit_geometry.host_features`` does, so that the oracle and the
            # directory read the same plane on a host with several magazine seats
            ref_host = reduced(frozenset({child, *by_slot["magazine"]}))
            if child_got is None or ref_host is None or not len(child_got[0]) or not len(child_got[1]):
                return
            add({"cls": cls, "slot": "magazine", "part": label, "seat_node": child, "ref_host": ref_host,
                 "ref_mag": (fit.to_fsu(basis, np.asarray(child_got[0], dtype=np.float64)), np.asarray(child_got[1], dtype=np.int64)),
                 "part_mesh": (fit.to_fsu(basis, part_verts), part_tris)})

        # a baked magazine against its own well reads 0 by construction (the reference is the child itself): no judgment, so no positive. Spec 4.2 names
        # the judged twin magazines for ``well.tol``
        not_positives["magazine:baked"] = not_positives.get("magazine:baked", 0) + len(listed["magazine"])
        for rec, entry in twins.get((host["id"], "magazine"), ()):
            child = (entry.get("replaces") or [None])[0]
            child = child if child in measured["magazine"] else (mounts._seat(measured["magazine"]) if measured["magazine"] else None)
            got = part_mesh(rec)
            if child is None or got is None or rec["attachment"]["anchor"] is None:
                continue
            # the magazine is placed on the seat of the child it twins, as the pair pass of the directory places it
            m = place(rec["attachment"]["anchor"], mounts._child_frame("magazine", child, measured["magazine"], axes))
            well_pos("twin", rec["id"], child, got[0] @ m[:3, :3].T + m[:3, 3], got[1])
        # a magazine fused into a preset with no baked magazine has no well reference to compare with (errata E2-Q3): it is no positive
        for pl in placements:
            if slot_of[pl.part] == "magazine" and not listed["magazine"]:
                skipped["located_magazine_without_reference"] = skipped.get("located_magazine_without_reference", 0) + 1

    return {"observations": observations, "toothed": toothed_hosts, "frame": frame_hosts, "positives": dict(sorted(positives.items())),
            "hosts": used, "preset_only_hosts": preset_only_hosts, "skipped": dict(sorted(skipped.items())),
            "placements": {"total": sum(placed.values()), "by_slot": dict(sorted(placed.items()))}, "not_positives": dict(sorted(not_positives.items()))}


@_guarded
def cmd_calibrate(args, cfg) -> int:
    """``attach-calibrate [--directory PATH] [--json OUT] [--pack A,B]``: does each literal of the fit gate cover its oracle positives?

    Prints, per literal of spec 4.2, the positives by class, the extreme observed value, the margin and the literal (``calibrate.calibrate``).
    Exit 0 when every literal covers its positives, 6 (as ``validate``) when one has no positives or a positive lies beyond it; the JSON names the
    literals in ``failed``. ``--json`` writes the full report, with the pair lists of ``attach-preview --pairs`` (``sheets``), to OUT, which must be
    outside this repository (the report is pack-derived)."""
    from .. import weapons as _pkg
    from ..cli import _threejs_v2
    from . import export as _export
    from . import calibrate
    from .directory import DIRECTORY_NAME, read_json, weapons_dir
    from .geometry import _FRAME_BORE_MAX_M
    from .guards import refuse_export_target
    from .rules import attachment_rules, load_rules

    out_path = None
    if args.json_out:
        out_path = Path(args.json_out)
        refuse_export_target(out_path, repo=_export._repo_root())  # exit 3 before anything is read
    dpath = Path(args.directory) if args.directory else weapons_dir(_catalogs(args, cfg)) / DIRECTORY_NAME
    if not dpath.is_file():
        raise WeaponsError(f"directory file not found: {dpath}", EXIT_BAD_INPUT)
    threejs = _threejs_v2(cfg)
    if threejs is None:
        raise WeaponsError("threejs_v2 is not configured: the oracle GLBs cannot be found", EXIT_BAD_INPUT)
    directory = read_json(dpath)
    rules = load_rules()
    fit_rules = attachment_rules(rules).get("fit_geometry")
    packs = set(_csv(args.pack) or [])
    oracle = _gather_oracle(directory, threejs, rules, packs or None)
    result = calibrate.calibrate(oracle["observations"], fit_rules, frame_bore_max_m=_FRAME_BORE_MAX_M)
    report = {
        "ok": result["ok"], "hosts": oracle["hosts"], "preset_only_hosts": oracle["preset_only_hosts"], "skipped": oracle["skipped"],
        "positives": oracle["positives"], "not_positives": oracle["not_positives"],
        "placements": {"measured": oracle["placements"], "spec": calibrate.PLACEMENTS_SPEC},
        "rows": result["rows"], "failed": result["failed"], "unmeasured": result["unmeasured"],
        "parameters": calibrate.parameters(fit_rules),
    }
    if out_path is not None:
        sheets = calibrate.sheet_pairs(directory, oracle["toothed"], oracle["frame"], tuple(COMPAT_TIERS))
        full = {**report, "sheets": sheets, "attach_rules_digest": directory.get("attach_rules_digest"),
                "weapon_attach_version": _pkg.WEAPON_ATTACH_VERSION}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes((json.dumps(full, indent=1, sort_keys=True) + "\n").encode("utf-8"))
        report["json"] = out_path.name
        report["sheets"] = {name: len(pairs) for name, pairs in sheets.items()}
    _emit(report)
    return EXIT_OK if result["ok"] else EXIT_SCHEMA


def register(sub) -> None:
    """Add the ``weapons`` group to the root parser's subparsers (spec 3.2)."""
    wp = sub.add_parser("weapons", help="Weapon directory: classified, measured per-weapon profiles")
    wsub = wp.add_subparsers(dest="weapons_cmd", required=True)

    def pack_opt(p):
        p.add_argument("--pack", default=None, help="comma list of pack ids; all packs when omitted")

    b = wsub.add_parser("build", help="Build <catalogs>/weapons/directory.json and excluded.json")
    pack_opt(b)
    b.add_argument("--rebuild", action="store_true", help="ignore the geometry cache")
    b.add_argument("--no-geometry", dest="no_geometry", action="store_true", help="skip geometry measurement")
    b.add_argument("--report", default=None, help="write the build report JSON here as well as stdout")
    b.add_argument("--min-coverage", dest="min_coverage", type=float, default=None,
                   help="exit 4 when geometry coverage of records with a GLB is below this fraction")
    b.add_argument("--strict", action="store_true", help="exit 3 when an override names a missing id/glob")
    b.set_defaults(func=cmd_build)

    s = wsub.add_parser("show", help="Print one record; ID is <pack>/<asset_id>, or a bare unique asset_id")
    s.add_argument("id", metavar="ID")
    s.set_defaults(func=cmd_show)

    ls = wsub.add_parser("list", help="List records with filters")
    pack_opt(ls)
    ls.add_argument("--kind", choices=KINDS)
    ls.add_argument("--role", choices=ROLES)
    ls.add_argument("--archetype", choices=ARCHETYPES)
    ls.add_argument("--genre", choices=GENRES)
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--max-confidence", dest="max_confidence", type=float, default=None)
    ls.add_argument("--limit", type=int, default=0, help="max rows (0 = all)")
    ls.set_defaults(func=cmd_list)

    ic = wsub.add_parser("icons", help="Render 256/64 px icons")
    pack_opt(ic)
    ic.add_argument("--ids", default=None, help="comma list of <pack>/<asset_id>")
    ic.add_argument("--size", type=int, default=256)
    ic.add_argument("--rebuild", action="store_true")
    ic.add_argument("--variants", action="store_true")
    ic.add_argument("--gpu", action="store_true",
                    help="use the GPU's ANGLE backend instead of software SwiftShader; output bytes then depend on the machine")
    ic.set_defaults(func=lambda a, c: _not_built(a, c, "icons"))

    rv = wsub.add_parser("review", help="Write the static review page (later slice)")
    rv.add_argument("--out", dest="review_out", default=None, help="output directory (distinct from the global --out)")
    pack_opt(rv)
    rv.add_argument("--only-unreviewed", dest="only_unreviewed", action="store_true")
    rv.add_argument("--max-confidence", dest="max_confidence", type=float, default=None)
    rv.add_argument("--previews", default=None,
                    help="folder `weapons attach-preview` wrote; its PNGs are embedded (default: <weapons dir>/attach-preview)")
    rv.set_defaults(func=lambda a, c: _not_built(a, c, "review"))

    ac = wsub.add_parser("apply-corrections", help="Merge a weapon-corrections/1 file into the overrides (later slice)")
    ac.add_argument("file", metavar="FILE")
    ac.add_argument("--dry-run", dest="dry_run", action="store_true")
    ac.set_defaults(func=lambda a, c: _not_built(a, c, "apply-corrections"))

    ex = wsub.add_parser("export", help="Write a per-game snapshot (later slice)")
    ex.add_argument("--game", required=True)
    grp = ex.add_mutually_exclusive_group(required=True)
    grp.add_argument("--packs", default=None, help="comma list of pack ids")
    grp.add_argument("--ids-file", dest="ids_file", default=None)
    ex.add_argument("--out", dest="export_out", default=None,
                    help="snapshot file (distinct from the global --out); default <catalogs>/weapons/snapshots/<game>.json")
    ex.add_argument("--roles", default="whole")
    ex.add_argument("--engine", choices=("godot", "unity", "threejs", "all"), default="all")
    ex.add_argument("--frame", choices=("item", "asset"), default="item")
    ex.add_argument("--icons-dir", dest="icons_dir", default=None)
    ex.add_argument("--profile", choices=("private", "public"), default="private")
    # W8a registered the attachment flags; the export honours them from W8d (`--min-compat-tier` and `--keep-foreign-hosts`
    # act only together with `--attachments`)
    ex.add_argument("--attachments", action="store_true",
                    help="also emit host mounts and the attachment part records (default off: the output is the W7 one)")
    ex.add_argument("--min-compat-tier", dest="min_compat_tier", choices=COMPAT_TIERS, default=None,
                    help="drop compatible_hosts below this tier (with --attachments; default cross_pack_fit)")
    ex.add_argument("--pending-min-tier", dest="pending_min_tier", choices=COMPAT_TIERS, default=None,
                    help="drop pending_hosts below this tier (with --attachments; default same_pack_fit: pending cross-pack pairs have no seat to measure)")
    ex.add_argument("--keep-foreign-hosts", dest="keep_foreign_hosts", action="store_true",
                    help="keep hosts that are not in the exported set (with --attachments)")
    ex.set_defaults(func=lambda a, c: _not_built(a, c, "export"))

    ae = wsub.add_parser("attach-eval", help="Agreement of the attachment compatibility with a labels file: a table per geometry slot, "
                                             "precision/recall for the label-era slots (W8c, G1 S9)")
    pack_opt(ae)
    ae.add_argument("--labels", default=None, help="weapon-attach-labels/1 file")
    ae.add_argument("--min-precision", dest="min_precision", type=float, default=None,
                    help="exit 4 when the precision of the label-era slots (laser_light, the sight slots) is below this; the four geometry "
                         "slots are never gated (spec 3.10)")
    ae.add_argument("--min-recall", dest="min_recall", type=float, default=None,
                    help="exit 4 when the recall of the label-era slots is below this")
    ae.set_defaults(func=lambda a, c: _not_built(a, c, "attach-eval"))

    ap = wsub.add_parser("attach-preview", help="Render attachment placement previews (W8d)")
    pack_opt(ap)
    ap.add_argument("--out", dest="preview_out", default=None,
                    help="output directory (distinct from the global --out; default <weapons dir>/attach-preview)")
    ap.add_argument("--ids", default=None, help="comma list of <pack>/<asset_id> attachments")
    ap.add_argument("--limit", type=int, default=0, help="max pairs rendered (0 = the default sample)")
    ap.add_argument("--size", type=int, default=384, help="PNG edge in px, a multiple of 64 (default 384)")
    ap.add_argument("--gpu", action="store_true", help="use the GPU instead of the software rasteriser")
    ap.add_argument("--sheet", action="store_true", help="also write sheet.png, a contact sheet of the rendered pairs")
    ap.add_argument("--plan", action="store_true",
                    help="print the pairs that would render and write nothing; needs no renderer")
    ap.add_argument("--pairs", default=None, metavar="FILE",
                    help="render exactly these pairs: a weapon-attach-spotcheck/1 file, or {\"pairs\": [{\"part\", \"host\"}]} (G1 S9)")
    ap.add_argument("--icons", nargs="+", default=None, metavar="ROOT",
                    help="HUD icon folders: each pair's host and part icon (ICON_SM_Wep_<name>[_<pack>][_Side|_Clean].png) goes beside its "
                         "render on the sheet, read by path and never copied; implies --sheet")
    ap.add_argument("--directory", default=None, metavar="PATH",
                    help="render against this directory.json instead of the catalogs one (the same pairs from an older build)")
    ap.set_defaults(func=lambda a, c: _not_built(a, c, "attach-preview"))

    cal = wsub.add_parser("attach-calibrate", help="Does each literal of the fit gate cover its oracle positives? (spec 3.11; exit 6 if not)")
    pack_opt(cal)
    cal.add_argument("--directory", default=None, help="directory.json to calibrate against (default: the catalogs one)")
    cal.add_argument("--json", dest="json_out", default=None, metavar="OUT",
                     help="write the full report, with the attach-preview pair lists (sheets), here; must be outside this repository")
    cal.set_defaults(func=cmd_calibrate)

    spc = wsub.add_parser("attach-spotcheck", help="The one-off spot check of the geometry fit gate: --draw 32 pairs once, --score the answers (spec 3.10)")
    mode = spc.add_mutually_exclusive_group(required=True)
    mode.add_argument("--draw", action="store_true", help="draw the 32 pairs and write the spot-check file; exit 6 if it exists")
    mode.add_argument("--score", action="store_true", help="print `fits k of 32 (placed wrong m)` from the answers in the file")
    spc.add_argument("--directory", default=None, help="directory.json to draw from (default: the catalogs one)")
    spc.add_argument("--file", default=None, help="the spot-check file (default: the committed weapon_attach_spotcheck.json in the package data)")
    spc.add_argument("--labels", default=None, help="weapon-attach-labels/1 file whose pairs the draw skips (default: the committed one, if any)")
    spc.add_argument("--baseline", default=None, help="with --score: the file as drawn; any change but fits/placed_wrong from null is exit 6")
    spc.set_defaults(func=lambda a, c: _not_built(a, c, "attach-spotcheck"))

    v = wsub.add_parser("validate", help="Validate rules, overrides and a directory (exit 6 on violations)")
    v.add_argument("--directory", default=None, help="directory.json to check (default: the catalogs one)")
    v.add_argument("--snapshot", default=None, help="a snapshot file (later slice)")
    v.set_defaults(func=cmd_validate)

