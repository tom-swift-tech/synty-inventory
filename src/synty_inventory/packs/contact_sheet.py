"""``packs contact-sheet``: one grid PNG, one labelled row-block per pack
(spec §3.3 / G1 gate artifact, §3.1).

Reuses the existing headless render path rather than inventing a new one:
``review.py``'s ``_render_stills`` (a ``synty_glb.qa render`` subprocess,
same cache location ``<threejs_v2>/<pack_id>/_review_stills/<stem>/``, so a
still already rendered for a prior ``review``/``vision`` pass over the same
asset is free here too). When an asset has no GLB at all (UI/interface
packs are textures, not meshes -- see ``INTERFACE_*`` catalogs), this falls
back to a Synty-extracted preview PNG under ``<catalogs>/previews/<pack_id>/``
if one exists, else the cell is a labelled placeholder. Every requested pack
gets its own labelled row-block even when none of its assets render --
that is the one hard requirement (AC8's "≥ 1 row per pack"), not that every
cell has a real picture.

New dependency: Pillow (PIL), for image composition -- not declared in
``pyproject.toml`` ``[project.dependencies]`` yet (out of this agent's
owned scope; follow-on for whoever owns that file). ``numpy`` is already a
hard dependency and is not enough on its own to decode/paste PNGs.
"""

from __future__ import annotations

import math
from pathlib import Path

CELL = 128
PAD = 6
LABEL_H = 22
COLS = 8

# One render view is enough for a thumbnail contact sheet (footprint_sheet.py
# and review.py both use "front"/"left" as their primary framing view).
_VIEW = "front"

_BG = (16, 20, 26)
_HEADER_BG = (30, 38, 50)
_HEADER_FG = (230, 230, 230)
_CELL_BORDER = (58, 69, 84)
_MISSING_BORDER = (120, 60, 60)
_MISSING_FG = (210, 140, 140)
_LABEL_FG = (200, 200, 200)


def select_representative(doc: dict, per_pack: int) -> list[dict]:
    """Deterministic pick of up to ``per_pack`` placeable assets: grouped by
    ``semantic_role`` (falling back to ``type``), each group id-sorted, then
    round-robin across groups so one busy role can't crowd out the rest."""
    assets = [a for a in doc.get("assets") or [] if a.get("placeable") is not False]
    groups: dict[str, list[dict]] = {}
    for a in assets:
        key = a.get("semantic_role") or a.get("type") or "unknown"
        groups.setdefault(key, []).append(a)
    for g in groups.values():
        g.sort(key=lambda a: a.get("id") or "")
    order = sorted(groups)

    out: list[dict] = []
    idx = 0
    while len(out) < per_pack:
        progressed = False
        for key in order:
            g = groups[key]
            if idx < len(g):
                out.append(g[idx])
                progressed = True
                if len(out) >= per_pack:
                    break
        if not progressed:
            break
        idx += 1
    return out


def resolve_cell_image(
    asset: dict,
    pack_id: str,
    *,
    catalogs_dir: Path | None,
    threejs_v2: Path | None,
    synty_glb_root: Path | None,
    render_timeout: int = 600,
) -> tuple[Path | None, str]:
    """``(image_path_or_None, source)`` -- ``source`` is one of ``"rendered"``,
    ``"preview"``, ``"render_failed"``, ``"no_glb"``."""
    glb_rel = (asset.get("files") or {}).get("glb")
    if glb_rel and threejs_v2 is not None and synty_glb_root is not None:
        glb = Path(threejs_v2) / glb_rel
        if glb.is_file():
            from ..review import RenderError, _render_stills

            stills_dir = Path(threejs_v2) / pack_id / "_review_stills" / asset["id"]
            try:
                images = _render_stills(glb, stills_dir, (_VIEW,), Path(synty_glb_root), timeout=render_timeout)
                if images and images[0].is_file():
                    return images[0], "rendered"
            except (RenderError, OSError, TimeoutError):
                pass
            return None, "render_failed"

    if catalogs_dir is not None:
        preview = Path(catalogs_dir) / "previews" / pack_id / f"{asset['id']}.png"
        if preview.is_file():
            return preview, "preview"

    return None, "no_glb"


def _draw_placeholder(draw, x0: int, y0: int, text: str) -> None:
    draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], outline=_MISSING_BORDER)
    draw.text((x0 + 4, y0 + CELL // 2 - 6), text[:18], fill=_MISSING_FG)


def compose_grid(pack_blocks: list[dict], out_path: Path) -> None:
    """``pack_blocks``: ``[{"pack_id": str, "cells": [(label, path_or_None, source)]}]``."""
    from PIL import Image, ImageDraw

    width = COLS * (CELL + PAD) + PAD
    heights = []
    for block in pack_blocks:
        rows = max(1, math.ceil(len(block["cells"]) / COLS)) if block["cells"] else 1
        heights.append(LABEL_H + rows * (CELL + PAD) + PAD)
    height = sum(heights) or (LABEL_H + CELL + 2 * PAD)

    canvas = Image.new("RGB", (width, height), color=_BG)
    draw = ImageDraw.Draw(canvas)

    y = 0
    for block, block_h in zip(pack_blocks, heights):
        draw.rectangle([0, y, width, y + LABEL_H], fill=_HEADER_BG)
        draw.text((PAD, y + 4), f"{block['pack_id']}  ({len(block['cells'])} shown)", fill=_HEADER_FG)
        y += LABEL_H
        if not block["cells"]:
            _draw_placeholder(draw, PAD, y + PAD, "no assets selected")
        for i, (label, img_path, source) in enumerate(block["cells"]):
            cx = PAD + (i % COLS) * (CELL + PAD)
            cy = y + PAD + (i // COLS) * (CELL + PAD)
            if img_path is not None:
                try:
                    with Image.open(img_path) as im:
                        im = im.convert("RGB")
                        im.thumbnail((CELL, CELL))
                        ox = cx + (CELL - im.width) // 2
                        oy = cy + (CELL - im.height) // 2
                        canvas.paste(im, (ox, oy))
                    draw.rectangle([cx, cy, cx + CELL, cy + CELL], outline=_CELL_BORDER)
                except (OSError, ValueError):
                    _draw_placeholder(draw, cx, cy, source)
            else:
                _draw_placeholder(draw, cx, cy, source)
            draw.text((cx + 2, cy + CELL - 12), label[:20], fill=_LABEL_FG)
        y += block_h - LABEL_H

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def build_contact_sheet(
    pack_ids: list[str],
    *,
    load_doc,
    catalogs_dir: Path | None,
    threejs_v2: Path | None,
    synty_glb_root: Path | None,
    out_path: Path,
    per_pack: int = 48,
    render_timeout: int = 600,
) -> dict:
    """``load_doc(pack_id) -> dict | None`` is injected so tests can hand in
    fixture catalogs without a real ``<catalogs>`` tree. Returns a report
    dict describing exactly where each pack's cell images came from."""
    pack_blocks: list[dict] = []
    report_packs: list[dict] = []

    for pack_id in pack_ids:
        doc = load_doc(pack_id)
        if doc is None:
            pack_blocks.append({"pack_id": pack_id, "cells": []})
            report_packs.append({"pack_id": pack_id, "error": "catalog not found", "sources": {}})
            continue

        chosen = select_representative(doc, per_pack)
        cells: list[tuple[str, Path | None, str]] = []
        sources: dict[str, int] = {}
        for asset in chosen:
            img, source = resolve_cell_image(
                asset,
                pack_id,
                catalogs_dir=catalogs_dir,
                threejs_v2=threejs_v2,
                synty_glb_root=synty_glb_root,
                render_timeout=render_timeout,
            )
            cells.append((asset["id"], img, source))
            sources[source] = sources.get(source, 0) + 1

        pack_blocks.append({"pack_id": pack_id, "cells": cells})
        report_packs.append(
            {
                "pack_id": pack_id,
                "assets_considered": len(doc.get("assets") or []),
                "cells_shown": len(cells),
                "sources": sources,
            }
        )

    compose_grid(pack_blocks, Path(out_path))
    return {"out": str(out_path), "packs": report_packs}
