"""Local VLM review pipeline for threejs-v2 packs.

For a given ``pack_id`` under ``threejs_v2_root``: iterate the pack's
``manifest.json`` GLBs (deterministic order, first-wins on a duplicate stem —
same rule ``sources.threejs_v2.glb_index`` uses so a rescan attaches text to
the same asset the overlay would resolve `files.glb` to), render 1-2 stills
per asset via the synty-glb QA renderer, ask a local Ollama VLM to describe
each one, and write/merge the pack's ``catalog.json`` in the exact shape
``sources.threejs_v2.apply_threejs_overlay`` already ingests as
``vlm_reviewed`` provenance (POLYGON_City's ``catalog.json`` is the reference
shape).

Stills are cached under ``<threejs_v2_root>/<pack_id>/_review_stills/<stem>/``
-- next to the GLBs they come from, outside this repo and outside
``catalogs`` -- so a rerun only re-renders a view whose PNG is missing, and
the images never end up in git.

Resumable: an asset already carrying ``reviewed: true`` in the on-disk
``catalog.json`` is skipped before it counts against ``--limit``. A per-asset
render or VLM failure is logged and skipped; it never aborts the batch.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from .sources.glb_measure import measure_glb
from .sources.threejs_v2 import BUNDLE_STEMS
from .vlm import LOCAL_DEFAULT_MODEL, LOCAL_DEFAULT_URL, query_local_vlm

STILLS_DIRNAME = "_review_stills"
MANIFEST_NAME = "manifest.json"
CATALOG_NAME = "catalog.json"

# Chosen empirically against real renders (see the review.py brief): the
# renderer always expands the camera frame to include a fixed 1.8m human
# gizmo it plants at the model's +X/+Z corner (qa/harness.js addHumanGizmo).
# "quarter"/"front" put that gizmo in the near field, right beside or in
# front of the asset. "left" looks from the opposite corner, so the gizmo
# ends up far from (often occluded by) the asset for anything bigger than
# it; "top" is the fallback -- it never overlaps the asset's footprint,
# trading identifying silhouette for a clean, unambiguous split between the
# two shapes. Verified visually on one small prop and one large building
# before picking this pair; re-verify if the harness's gizmo placement ever
# changes.
DEFAULT_VIEWS: tuple[str, ...] = ("left", "top")

CATEGORY_TYPE = {
    "prop": "prop",
    "building": "building/module",
    "vehicle": "vehicle",
    "character": "character",
    "environment": "environment",
    "fx": "fx",
}

# Same allow-list the overlay applies on read (sources/threejs_v2.py
# _TOKEN_RE) -- filter here so a tag we can't ever apply doesn't sit in the
# catalog looking reviewed.
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-+.]*$")

PROMPT_TEMPLATE = (
    "You are cataloging a single low-poly Synty POLYGON-style 3D game asset "
    "from one or more renders of one GLB model.\n"
    "A small teal humanoid capsule-and-sphere figure next to a thin yellow "
    "pole may appear in a corner of the image -- that is a fixed 1.8-meter "
    "human scale reference planted by the renderer, never the asset. Ignore "
    "it completely and describe only the other 3D model.\n"
    "{context}"
    "Reply with ONLY a JSON object: "
    '{{"name": "<short human name>", '
    '"description": "<1-2 sentences: what it is, colors, notable features>", '
    '"tags": ["<5-10 lowercase snake_case tags>"], '
    '"category": "<prop|building|vehicle|character|environment|fx>", '
    '"semantic_role": "<short snake_case role, e.g. exterior_prop, '
    'building_module, spacecraft, character_part>"}}'
)


class RenderError(RuntimeError):
    """A synty-glb render subprocess failed to produce the requested stills."""


def _default_log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _stem_index(models: Sequence[str]) -> dict[str, str]:
    """stem -> manifest-relative path, first occurrence wins (manifest order).

    Mirrors ``sources.threejs_v2.glb_index``'s dedup rule so a duplicate stem
    resolves to the same GLB the overlay would wire ``files.glb`` to.
    """
    idx: dict[str, str] = {}
    for rel in models:
        stem = Path(rel).stem
        idx.setdefault(stem, rel)
    return idx


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_catalog(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _scaffold_catalog(pack_id: str) -> dict:
    return {
        "pack_id": pack_id,
        "origin": "Synty / converted",
        "style": pack_id.lower(),
        "units": "meters",
        "version": 1,
        "assets": [],
    }


def _views_for(glb: Path, default: Sequence[str]) -> Sequence[str]:
    """Vertical planar assets (wall signs, decals, draped ivy) are thin along Z,
    so BOTH default views (left = along X, top = along Y) see them edge-on and
    the VLM reviews a sliver. Render those face-on instead. Horizontal flats
    (floors, thin-Y) stay face-on from `top`, thin-X planes from `left` --
    only thin-Z needs the swap."""
    try:
        measured = measure_glb(glb)
    except Exception:  # noqa: BLE001 -- view choice must never kill a review
        return default
    if not measured:
        return default
    mn, mx = measured
    size = [abs(b - a) for a, b in zip(mn, mx)]
    largest = max(size)
    if largest <= 0:
        return default
    thin_z = size[2] / largest < 0.08 and size[2] == min(size)
    planar = min(size[0], size[1]) / largest > 0.25
    if thin_z and planar:
        return ("front", "top")
    return default


def _render_stills(
    glb: Path,
    stills_dir: Path,
    views: Sequence[str],
    synty_glb_root: Path,
    *,
    timeout: int = 600,
) -> list[Path]:
    """Render `views` for `glb` into `stills_dir`, skipping views already on disk."""
    stills_dir.mkdir(parents=True, exist_ok=True)
    wanted = [stills_dir / f"{v}.png" for v in views]
    missing_views = [v for v, p in zip(views, wanted) if not p.is_file()]
    if not missing_views:
        return wanted
    # --no-gizmo: the harness's 1.8 m human-scale figure dominates the frame on
    # small assets and the VLM describes IT instead of the asset. Scale comes
    # from measured bounds, so review stills never need the gizmo. Requires a
    # synty-glb checkout whose qa render accepts the flag (2026-08-20+).
    cmd = [sys.executable, "-m", "synty_glb.qa", "render", str(glb), str(stills_dir), *missing_views, "--no-gizmo"]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(synty_glb_root / "src")
    proc = subprocess.run(
        cmd,
        cwd=str(synty_glb_root),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    still_missing = [p for p in wanted if not p.is_file()]
    if still_missing:
        raise RenderError(
            f"render incomplete for {glb.name} (rc={proc.returncode}): "
            f"missing {[p.name for p in still_missing]}; stderr={proc.stderr[-500:]}"
        )
    return wanted


def _stem_block(stem: str) -> str:
    """The source filename stem is free, near-always-truthful context: a wall
    anchor rendered small reads as an angular rock, but SM_Gen_Prop_Chain_Anchor_01
    settles it. Without this, shared-kit (SM_Gen_*) stems -- absent from the
    catalog of record -- were reviewed completely blind."""
    return (
        f"The asset's source filename stem is {stem!r}. Synty filenames are "
        "almost always truthful about what the asset IS -- use them to "
        "identify it, use the image for colors, shape, materials and notable "
        "details, and only contradict the filename when the image clearly "
        "shows something else.\n"
    )


def _context_block(context: dict | None) -> str:
    if not context:
        return ""
    bits = []
    if context.get("name"):
        bits.append(f"name={context['name']!r}")
    if context.get("type"):
        bits.append(f"type={context['type']!r}")
    if context.get("tags"):
        bits.append(f"tags={context['tags']!r}")
    if not bits:
        return ""
    return (
        "Existing (unverified, possibly generic/wrong) catalog data for this "
        f"asset -- confirm or correct it from the image, don't just repeat it: {', '.join(bits)}.\n"
    )


def _context_for(catalogs_dir: Path | None, pack_id: str, stem: str) -> dict | None:
    """Best-effort read-only lookup in the catalog of record (synty_catalogs).

    Never writes there. Missing/unreadable is a silent None -- context is a
    prompting aid, not a requirement.
    """
    if catalogs_dir is None:
        return None
    doc = _load_json(Path(catalogs_dir) / f"{pack_id}.json")
    if not doc:
        return None
    for asset in doc.get("assets") or []:
        if isinstance(asset, dict) and asset.get("id") == stem:
            return {
                "name": asset.get("name"),
                "type": asset.get("type"),
                "tags": (asset.get("tags") or [])[:8],
            }
    return None


def _build_entry(stem: str, rel_path: str, draft: dict) -> dict:
    name = str(draft.get("name") or "").strip() or stem
    description = str(draft.get("description") or "").strip()
    tags = [
        t.strip().lower().replace(" ", "_")
        for t in (draft.get("tags") or [])
        if isinstance(t, str) and t.strip()
    ]
    tags = [t for t in tags if _TAG_RE.match(t)]
    category = str(draft.get("category") or "").strip().lower()
    role = str(draft.get("semantic_role") or "").strip()

    entry: dict = {"id": stem, "name": name, "reviewed": True, "file": rel_path}
    dtype = CATEGORY_TYPE.get(category, category)
    if dtype:
        entry["type"] = dtype
    if category:
        entry["category"] = [category]
    if description:
        entry["description"] = description
    if tags:
        entry["tags"] = tags
    if role:
        entry["semantic_role"] = role
    return entry


def review_pack(
    pack_id: str,
    *,
    threejs_v2_root: Path,
    synty_glb_root: Path,
    catalogs_dir: Path | None = None,
    limit: int | None = None,
    match: str | None = None,
    model: str = LOCAL_DEFAULT_MODEL,
    url: str = LOCAL_DEFAULT_URL,
    views: Sequence[str] = DEFAULT_VIEWS,
    render_fn: Callable[[Path, Path, Sequence[str], Path], list[Path]] | None = None,
    query_fn: Callable[[list[Path], str], dict | None] | None = None,
    render_timeout: int = 600,
    vlm_timeout: int = 600,
    log: Callable[[str], None] | None = None,
) -> dict:
    """Review up to `limit` unreviewed GLBs in `pack_id` and merge results
    into `<threejs_v2_root>/<pack_id>/catalog.json`.

    `render_fn`/`query_fn` are injection points for tests (default to the
    real subprocess renderer / real Ollama call). `vlm_timeout` is a
    separate knob from `render_timeout` -- a slower/larger model tag needs
    more than the default 600s per call, independent of render time.
    """
    log = log or _default_log
    render = render_fn or (
        lambda glb, stills_dir, vs, root: _render_stills(glb, stills_dir, vs, root, timeout=render_timeout)
    )
    query = query_fn or (
        lambda images, prompt: query_local_vlm(images, prompt, url=url, model=model, timeout=vlm_timeout)
    )

    pack_dir = Path(threejs_v2_root) / pack_id
    manifest = _load_json(pack_dir / MANIFEST_NAME)
    if not manifest:
        return {"ok": False, "pack_id": pack_id, "error": f"missing/unreadable {pack_dir / MANIFEST_NAME}"}

    stems = _stem_index(manifest.get("models") or [])
    catalog_file = pack_dir / CATALOG_NAME
    doc = _load_json(catalog_file) or _scaffold_catalog(pack_id)
    doc.setdefault("assets", [])
    by_id = {a["id"]: a for a in doc["assets"] if isinstance(a, dict) and a.get("id")}

    candidates = sorted(stems)
    if match:
        needle = match.lower()
        candidates = [s for s in candidates if needle in s.lower()]

    reviewed_ids: list[str] = []
    skipped_bundle: list[str] = []
    skipped_reviewed: list[str] = []
    failed: list[dict] = []

    for stem in candidates:
        if stem.lower() in BUNDLE_STEMS:
            skipped_bundle.append(stem)
            continue
        existing = by_id.get(stem)
        if existing and existing.get("reviewed"):
            skipped_reviewed.append(stem)
            continue
        if limit is not None and len(reviewed_ids) >= limit:
            break

        rel_path = stems[stem]
        glb = pack_dir / rel_path
        if not glb.is_file():
            failed.append({"id": stem, "error": f"GLB not found on disk: {glb}"})
            continue

        stills_dir = pack_dir / STILLS_DIRNAME / stem
        try:
            images = render(glb, stills_dir, _views_for(glb, views), synty_glb_root)
        except (RenderError, subprocess.SubprocessError, OSError, TimeoutError) as exc:
            log(f"review: render failed for {stem}: {exc}")
            failed.append({"id": stem, "error": f"render: {exc}"})
            continue

        context = _context_for(catalogs_dir, pack_id, stem)
        prompt = PROMPT_TEMPLATE.format(context=_stem_block(stem) + _context_block(context))
        draft = query(images, prompt)
        if not draft:
            log(f"review: VLM produced no usable JSON for {stem}")
            failed.append({"id": stem, "error": "vlm: no usable JSON reply"})
            continue

        entry = _build_entry(stem, rel_path, draft)
        by_id[stem] = entry
        reviewed_ids.append(stem)

        # Write after every asset, not just at the end, so an interrupted
        # batch keeps its progress and the next run resumes past it.
        doc["assets"] = list(by_id.values())
        _write_catalog(catalog_file, doc)
        log(f"review: {stem} -> {entry.get('name')!r}")

    return {
        "ok": not failed,
        "pack_id": pack_id,
        "catalog": str(catalog_file),
        "reviewed": reviewed_ids,
        "skipped_already_reviewed": len(skipped_reviewed),
        "skipped_bundle": skipped_bundle,
        "failed": failed,
        "candidates": len(candidates),
    }
