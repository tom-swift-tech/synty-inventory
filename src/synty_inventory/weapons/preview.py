"""``weapons attach-preview``: look-first placement previews of attachments on their hosts (docs/weapon_attachments.md 6.2, AC83).

For a pair (attachment part, compatible host) the PNG shows the host with the attachment placed by the section 3.1
transform ``place(anchor, mount) = T(mount) * T(anchor)^-1`` and the baked children of the slot it mounts in
(``mounts.<slot>.occupied_by`` and ``child_node``, all of them, as the runtime hides them) left out. Tom looks at these before trusting a placement; the review page
embeds them (``review.load_previews``); they are never committed.

Which pairs. Every twin pair (an exact dimensional twin of the host's baked child is the ground truth, so these are the
placements to check first), plus a deterministic sample of the other compatible pairs: one pair per attachment (its
best-tier non-twin host, ties broken by the directory's order), then ``DEFAULT_OTHERS`` of those taken tier by tier, best tier
first (``same_pack_fit``, the default export tier, before ``cross_pack_fit``), round-robin over the slots inside a tier and by
part id inside a slot. A tier is only dipped into when the better ones are used up, so a slot whose only candidates are
cross-pack shows up after the same-pack ones (the twin pairs already cover every slot). ``--ids`` renders every
usable pair of the named attachments instead; ``--limit`` cuts the list (twins first). A pair is usable only when the
attachment has a measured anchor and the host has a measured mount for the slot (a ``none`` mount has nothing to place on)
and both have a GLB. ``--plan`` prints the pairs and needs no renderer.

Rendering. ``PreviewRenderer`` is the icon harness ``Renderer`` (same loopback server, browser and frame/decode path) opening
``icon_harness/preview.html``; ``render_pairs`` takes any object with ``render_pair(job, size)``, so the file handling and the
index are tested without a GPU. The placed attachment is drawn in one flat orange (``PART_TINT``, a field of every job) and the host with its own
materials made opaque (a translucent host would show the part through its body; glTF MASK cut-outs stay), so a white part on a white host cannot hide a muzzle brake. A preview is flattened onto a plain background: it is a picture to look at, not an icon, and a
dark model on a transparent PNG disappears in most viewers. Outputs: ``<name>.png`` per pair, ``index.json``
(``weapon-attach-preview/1``, merged with what an earlier run left), and with ``--sheet`` ``sheet.png``, a contact sheet in
index order. A failed pair is listed and the rest go on; a renderer that cannot start is exit 5 with nothing written.

Where it writes. Only into ``--out`` (default ``<catalogs>/weapons/attach-preview``): the same refusals as ``export`` apply
(not inside the catalogs dir except its own weapons folder, not inside a pack root or this checkout, not into a git work tree
that tracks ``*.synty*`` files). Read-only everywhere else: the directory and the GLBs are only read.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from . import ATTACH_SLOTS, EXIT_OK, EXIT_RENDERER, InputError, RefusalError, WeaponsError, write_text_lf
from .attach import hidden_nodes, place
from .compat import tier_rank
from .icons import (
    Renderer,
    RendererUnavailable,
    RenderError,
    _check_size,
    _selection,
    _write_atomic,
    camera_direction,
    check_renderer,
    encode_png,
    is_blank,
)

PREVIEW_SCHEMA = "weapon-attach-preview/1"
INDEX_NAME = "index.json"
SHEET_NAME = "sheet.png"
DEFAULT_DIRNAME = "attach-preview"
DEFAULT_SIZE = 384
DEFAULT_OTHERS = 12  # non-twin pairs in the default sample (every slot is covered when the directory has them)
BACKGROUND = (58, 64, 76)  # the flat colour a preview is drawn on
PART_TINT = "e8742a"  # the placed attachment is drawn in this flat colour (orange); the host keeps its own materials
BLANK_RENDER = "blank_render"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


# -- planning ---------------------------------------------------------------------------------------------------


def pair_file(part: str, host: str) -> str:
    """Stable PNG name of a pair: readable ids, plus a short hash so two ids that sanitise alike cannot collide."""
    tag = hashlib.sha1(f"{part}\n{host}".encode("utf-8")).hexdigest()[:6]
    return f"{_SAFE.sub('_', part)}--{_SAFE.sub('_', host)}--{tag}.png"


def _unusable(part: dict, host: dict | None, slot: str) -> str | None:
    """Why a pair cannot be drawn, or None."""
    if host is None:
        return "host_missing"
    if not (part.get("files") or {}).get("glb") or not part.get("geometry"):
        return "part_unmeasured"
    if not (host.get("files") or {}).get("glb") or not host.get("geometry"):
        return "host_unmeasured"
    if part["attachment"].get("anchor") is None:
        return "anchor_unmeasured"
    mount = ((host["geometry"].get("mounts") or {}).get(slot))
    if mount is None or mount.get("source") == "none" or mount.get("point") is None:
        return "no_mount"
    return None


def plan_pairs(directory: dict, *, packs=None, ids=None, limit: int = 0, others: int = DEFAULT_OTHERS) -> tuple[list[dict], dict]:
    """``(pairs, skipped)``: the pairs to draw and a count of unusable candidates by reason.

    A pair is ``{part, host, slot, tier, score, twin}``. Twins come first (sorted by part, host), then the others. With
    ``ids`` every usable compatible pair of those attachments is kept; without, the others are the tier-first, slot
    round-robin sample described in the module docstring. ``limit > 0`` keeps the first ``limit``.
    """
    by_id = {w["id"]: w for w in directory["weapons"]}
    parts = sorted((w for w in directory["weapons"]
                    if w.get("attachment") and (not packs or w["pack"] in packs) and (not ids or w["id"] in ids)),
                   key=lambda w: w["id"])
    skipped: dict[str, int] = {}
    twins: list[dict] = []
    best: list[dict] = []  # per attachment, its best-tier non-twin pair
    every_other: list[dict] = []
    for part in parts:
        slot = part["attachment"]["slot"]
        part_others: list[dict] = []
        for entry in part["attachment"]["compatible_hosts"]:
            why = _unusable(part, by_id.get(entry["host"]), slot)
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            pair = {"part": part["id"], "host": entry["host"], "slot": slot, "tier": entry["tier"],
                    "score": entry["score"], "twin": entry["tier"] == "twin"}
            if pair["twin"]:
                twins.append(pair)
            else:
                every_other.append(pair)
                part_others.append(pair)
        if part_others:  # min() keeps the first of equal ranks: the directory lists a part's hosts best tier first, but do not rely on it
            best.append(min(part_others, key=lambda p: tier_rank(p["tier"])))
    if ids:
        chosen_others = every_other
    else:
        slots = list(ATTACH_SLOTS) + sorted({p["slot"] for p in best} - set(ATTACH_SLOTS))  # a slot a newer directory adds
        chosen_others = []
        for rank in sorted({tier_rank(p["tier"]) for p in best}):  # best tier first: same_pack_fit before cross_pack_fit
            by_slot = {s: sorted((p for p in best if p["slot"] == s and tier_rank(p["tier"]) == rank), key=lambda p: p["part"])
                       for s in slots}
            while len(chosen_others) < others and any(by_slot.values()):
                for slot in slots:
                    if by_slot[slot] and len(chosen_others) < others:
                        chosen_others.append(by_slot[slot].pop(0))
    pairs = twins + chosen_others
    if limit and limit > 0:
        pairs = pairs[:limit]
    return pairs, skipped


def build_job(pair: dict, part: dict, host: dict, threejs_dir: Path) -> dict:
    """Everything the renderer needs for one pair, as plain data (paths, node names, scales, 4x4 as nested lists).

    ``matrix`` is ``attach.place(anchor, mount)``: attachment-scaled GLB space -> host-scaled GLB space. ``hide`` is every node of the
    slot's ``occupied_by`` plus its ``child_node`` for EVERY pair (E1: the runtime hides the whole slot whichever child the part
    is seated on); ``replaces`` never narrows it. A1: a twin pair whose entry's ``replaces`` names exactly one child that the mount
    has a seat for (``mounts.<slot>.seats``) is placed on that seat, so a twin of the smaller of two magazines lands on ITS child
    and not on the larger one that owns the mount's own seat (``replaces`` chooses the seat only); every other pair is placed on
    the mount as before. A2: an optic whose entry carries ``hides_slots`` (spec 4.3) also hides the nodes of those slots (the rear
    sight it covers), by the same whole-slot rule (``attach.hidden_nodes``, which settle to contact uses too). A5: an entry that carries
    ``seat_shift_m`` (spec 5.4) places the part ``translate(seat_shift_m * frame.up) @ place(anchor, frame)``, so every picture shows the
    settled pair; an entry without the key is placed as before. A6 (W8n, 13.7 A6-2): an entry that carries ``seat_setback_m`` also moves the part back
    along the bore, ``translate(-seat_setback_m * frame.up) @ place(anchor, frame)`` (the same frame logic as the shift; a muzzle entry has no shift).
    """
    slot = pair["slot"]
    anchor = part["attachment"]["anchor"]
    mounts = host["geometry"]["mounts"]
    mount = mounts[slot]
    entry = next((e for e in part["attachment"].get("compatible_hosts") or [] if e["host"] == pair["host"]), None)

    hide = hidden_nodes(mounts, slot, entry)
    frame = mount
    if pair.get("twin"):
        replaces = (entry or {}).get("replaces") or []
        if len(replaces) == 1 and replaces[0] in (mount.get("seats") or {}):
            frame = mount["seats"][replaces[0]]
    matrix = place(anchor, frame)
    shift = (entry or {}).get("seat_shift_m")
    if shift:  # translate(shift * up) on the left moves the placed part along the frame's up, in the host's space
        matrix[:3, 3] += float(shift) * np.asarray(frame["up"], dtype=np.float64)
    setback = (entry or {}).get("seat_setback_m")
    if setback:  # a silencer sits back over the host's exposed muzzle end: toward the host, against the mount's up
        matrix[:3, 3] -= float(setback) * np.asarray(frame["up"], dtype=np.float64)
    return {
        **pair,
        "host_glb": Path(threejs_dir) / host["files"]["glb"], "host_nodes": _selection(host["files"].get("glb_node")),
        "host_scale": float(host["files"].get("glb_scale") or 1.0), "hide": hide,
        "item_basis": [[int(c) for c in row] for row in host["geometry"]["item_basis"]],
        "part_glb": Path(threejs_dir) / part["files"]["glb"], "part_nodes": _selection(part["files"].get("glb_node")),
        "part_scale": float(part["files"].get("glb_scale") or 1.0),
        "part_tint": PART_TINT, "host_tint": None,  # None: the host is drawn with its own materials
        "matrix": [[float(c) for c in row] for row in matrix],
    }


# -- rendering --------------------------------------------------------------------------------------------------


class PreviewRenderer(Renderer):
    """The icon harness renderer, opened on ``preview.html`` (host plus a placed attachment)."""

    PAGE = "preview.html"
    READY = "__PREVIEW__"

    def render_pair(self, job: dict, size: int) -> np.ndarray:
        """Premultiplied RGBA (``size`` x ``size`` x 4, top row first) of one pair. Raises ``RenderError``."""
        return self._draw("window.previewPrepare", {
            "host": {"glb": self._glb_url(job["host_glb"]), "nodes": job["host_nodes"], "hide": job["hide"],
                     "scale": job["host_scale"]},
            "part": {"glb": self._glb_url(job["part_glb"]), "nodes": job["part_nodes"], "scale": job["part_scale"],
                     "matrix": job["matrix"], "tint": job["part_tint"]},
            "itemBasis": job["item_basis"], "camDir": list(camera_direction(False)),
        }, size)


def flatten(px: np.ndarray, background=BACKGROUND) -> np.ndarray:
    """Straight RGBA, fully opaque: the premultiplied render over a flat background."""
    rgb = px[..., :3].astype(np.float64)
    alpha = px[..., 3:4].astype(np.float64)
    out = np.empty(px.shape, dtype=np.uint8)
    out[..., :3] = np.clip(np.rint(rgb + np.asarray(background, dtype=np.float64) * (255.0 - alpha) / 255.0), 0, 255)
    out[..., 3] = 255
    return out


def contact_sheet(images: list[np.ndarray]) -> np.ndarray:
    """The images (equal squares) in a grid, row by row, ``ceil(sqrt(n))`` columns, unused cells in the background colour."""
    n = len(images)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    size = images[0].shape[0]
    sheet = np.empty((rows * size, cols * size, 4), dtype=np.uint8)
    sheet[..., :3], sheet[..., 3] = np.asarray(BACKGROUND, dtype=np.uint8), 255
    for i, img in enumerate(images):
        r, c = divmod(i, cols)
        sheet[r * size:(r + 1) * size, c * size:(c + 1) * size] = img
    return sheet


def _read_index(out_dir: Path) -> list[dict]:
    path = out_dir / INDEX_NAME
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(doc, dict) or doc.get("schema") != PREVIEW_SCHEMA or not isinstance(doc.get("pairs"), list):
        return []
    return [p for p in doc["pairs"] if isinstance(p, dict)]


def render_pairs(renderer, jobs: list[dict], out_dir: Path, size: int, *, sheet: bool = False) -> dict:
    """Draw every job and write the PNGs and ``index.json`` into ``out_dir``. ``renderer.render_pair(job, size)`` returns
    premultiplied RGBA; any object with that method works (the tests pass a stub). ``{rendered, failed, pairs}``."""
    out_dir = Path(out_dir)
    entries: list[dict] = []
    images: list[np.ndarray] = []
    failed: list[dict] = []
    for job in jobs:
        name = pair_file(job["part"], job["host"])
        try:
            px = renderer.render_pair(job, size)
            if is_blank(px):
                raise RenderError(BLANK_RENDER)
        except RenderError as exc:
            failed.append({"part": job["part"], "host": job["host"], "error": str(exc)})
            continue
        flat = flatten(px)
        _write_atomic(out_dir / name, encode_png(flat))
        images.append(flat)
        entries.append({"part": job["part"], "host": job["host"], "slot": job["slot"], "tier": job["tier"],
                        "score": job["score"], "file": name})
    # earlier runs: keep their pairs while the PNG is still there, so `--ids` adds to the index instead of replacing it
    fresh = {(e["part"], e["host"]) for e in entries}
    kept = [p for p in _read_index(out_dir)
            if (p.get("part"), p.get("host")) not in fresh and isinstance(p.get("file"), str)
            and Path(p["file"]).name == p["file"] and (out_dir / p["file"]).is_file()]
    pairs = sorted(kept + entries, key=lambda p: (p["part"], p["host"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_text_lf(out_dir / INDEX_NAME, json.dumps({"schema": PREVIEW_SCHEMA, "pairs": pairs}, indent=1, sort_keys=True) + "\n")
    if sheet and images:
        _write_atomic(out_dir / SHEET_NAME, encode_png(contact_sheet(images)))
    return {"rendered": len(entries), "failed": failed, "pairs": pairs}


# -- the verb ---------------------------------------------------------------------------------------------------


def _csv(value) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in str(value).split(",") if p.strip()]


def resolve_out(preview_out, catalogs_dir: Path, wdir: Path, cfg) -> Path:
    """The output folder, after the export refusals (exit 3). Nothing is created here."""
    from . import export as _export  # the seam the export tests steer (_repo_root); one set of rules for both verbs
    from .guards import refuse_export_target

    explicit = bool(preview_out)
    out = (Path(preview_out) if explicit else wdir / DEFAULT_DIRNAME).resolve()
    default_dir = (wdir / DEFAULT_DIRNAME).resolve()
    # like export: the default folder is inside the catalogs dir by design (spec 3.1); an explicit path elsewhere in it is not
    skip_catalogs_root = not explicit or out == default_dir or default_dir in out.parents
    for root in _export._forbidden_roots(None if skip_catalogs_root else catalogs_dir, cfg):
        if out == root or root in out.parents:
            raise RefusalError("refusing to write previews inside the catalogs dir, a pack root or this repository "
                               "(they are pack-derived pictures, never committed)", details={"root": root.name})
    refuse_export_target(out / INDEX_NAME, repo=_export._repo_root())
    return out


def _run(args, cfg) -> int:
    from ..cli import _catalogs, _threejs_v2, emit_json as _emit
    from .directory import DIRECTORY_NAME, read_json, weapons_dir

    size = getattr(args, "size", DEFAULT_SIZE)
    _check_size(size)
    catalogs_dir = _catalogs(args, cfg)
    wdir = weapons_dir(catalogs_dir)
    out_dir = resolve_out(getattr(args, "preview_out", None), catalogs_dir, wdir, cfg)
    dpath = wdir / DIRECTORY_NAME
    if not dpath.is_file():
        raise InputError(f"no weapon directory at {dpath}; run `weapons build` first")
    directory = read_json(dpath)

    packs, ids = _csv(getattr(args, "pack", None)), _csv(getattr(args, "ids", None))
    known_packs = {w["pack"] for w in directory["weapons"]}
    if packs and set(packs) - known_packs:
        raise InputError(f"unknown pack(s): {', '.join(sorted(set(packs) - known_packs))}")
    attachments = {w["id"] for w in directory["weapons"] if w.get("attachment")}
    if ids and set(ids) - attachments:
        raise InputError("not an attachment part in the directory: " + ", ".join(sorted(set(ids) - attachments)))
    pairs, skipped = plan_pairs(directory, packs=set(packs) if packs else None, ids=set(ids) if ids else None,
                                limit=getattr(args, "limit", 0) or 0)
    summary = {"ok": True, "size": size, "pairs": len(pairs), "twins": sum(1 for p in pairs if p["twin"]),
               "skipped": dict(sorted(skipped.items()))}
    if getattr(args, "plan", False):  # nothing is read from a GLB and nothing is written
        _emit({**summary, "plan": pairs})
        return EXIT_OK
    if not pairs:
        _emit({**summary, "rendered": 0, "failed": [], "out": out_dir.as_posix()})
        return EXIT_OK

    root = check_renderer(cfg.get("synty_glb_root"))  # exit 5 before anything is written
    threejs = _threejs_v2(cfg)
    if threejs is None:
        raise InputError("threejs_v2 is not configured: the GLBs cannot be found")
    by_id = {w["id"]: w for w in directory["weapons"]}
    jobs = [build_job(p, by_id[p["part"]], by_id[p["host"]], threejs) for p in pairs]
    with PreviewRenderer(root, gpu=bool(getattr(args, "gpu", False))) as renderer:
        report = render_pairs(renderer, jobs, out_dir, size, sheet=bool(getattr(args, "sheet", False)))
    _emit({**summary, "rendered": report["rendered"], "failed": report["failed"], "out": out_dir.as_posix(),
           "index": INDEX_NAME})
    return EXIT_OK


def cmd(args, cfg) -> int:
    """``synty-inventory weapons attach-preview``. Exit 5 when the renderer is unavailable (nothing written)."""
    from ..cli import emit_json as _emit

    try:
        return _run(args, cfg)
    except RendererUnavailable as exc:
        _emit({"ok": False, "error": str(exc), "renderer": "unavailable"})
        return EXIT_RENDERER
    except WeaponsError as exc:
        _emit({"ok": False, "error": str(exc), **exc.details})
        return exc.code
