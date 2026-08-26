"""Contact-sheet SVG of computed footprints, for eyeballing a pass before it
is written to any catalog.

One cell per asset: the measured AABB in grey, the computed polygon in cyan,
labelled with id / class / area / fill. Grouped by class so a systematic
error shows up as a block of wrong cells rather than one stray outlier.

This is deliberately a sidecar workflow -- it reads GLBs and writes an SVG,
and never touches a catalog. Look first, write second.

Not an independent check of the GLB decode path (the analyser and this share
``load_triangles``); it *is* independent of the raster -> components ->
trace -> clamp chain, which is where the bugs have actually been.

Usage::

    python -m synty_inventory.tools.footprint_sheet \\
        --pack POLYGON_City --out <dir> [--class l_plan,u_plan] [--limit 200]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from ..paths import load_config
from ..sources.footprint import analyze_footprint_detail

# Types whose footprint a layout pass will actually query. Everything else
# (foliage, debris, clouds, characters) gets a faithful polygon that nobody
# reads -- a tree's outline is "irregular" in the same sense a cathedral's
# would be, and the word carries no information in the tree's case.
BUILDABLE_TYPES = (
    "building/shell",
    "building/module",
    "building/interior_module",
    "environment/city_layout",
)

CELL = 190
PAD = 26
COLS = 6
ROWS_PER_PAGE = 8

CSS = """
  .bg   { fill: #10141a; }
  .box  { fill: none; stroke: #3a4554; stroke-width: 1.2; }
  .poly { fill: #22d3ee22; stroke: #22d3ee; stroke-width: 1.6; stroke-linejoin: round; }
  .seg  { stroke: #f59e0b; stroke-width: 3; stroke-linecap: round; }
  .ctr  { fill: #f472b6; }
  .id   { fill: #cbd5e1; font: 8px ui-monospace, monospace; }
  .meta { fill: #7c8ba1; font: 8px ui-monospace, monospace; }
  .warn { fill: #f87171; font: 9px ui-monospace, monospace; }
  .hdr  { fill: #e2e8f0; font: 14px ui-sans-serif, system-ui; }
"""


def _cell_svg(x0: int, y0: int, aid: str, block: dict | None, reason: str, box: tuple) -> list[str]:
    out = [f'<rect x="{x0}" y="{y0}" width="{CELL}" height="{CELL}" class="bg"/>']
    inner = CELL - 2 * PAD
    bx0, bz0, bx1, bz1 = box
    w = max(bx1 - bx0, 1e-6)
    h = max(bz1 - bz0, 1e-6)
    scale = inner / max(w, h)
    ox = x0 + PAD + (inner - w * scale) / 2
    oy = y0 + PAD + (inner - h * scale) / 2

    def to_px(x: float, z: float) -> tuple[float, float]:
        # +z runs up the page, matching how a plan is normally read
        return ox + (x - bx0) * scale, oy + (bz1 - z) * scale

    px0, py1 = to_px(bx0, bz0)
    px1, py0 = to_px(bx1, bz1)
    out.append(
        f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{max(px1 - px0, 0.5):.1f}" '
        f'height="{max(py1 - py0, 0.5):.1f}" class="box"/>'
    )

    label = html.escape(aid[:30])
    out.append(f'<text x="{x0 + 6}" y="{y0 + 13}" class="id">{label}</text>')

    if block is None:
        out.append(f'<text x="{x0 + 6}" y="{y0 + CELL - 8}" class="warn">{html.escape(reason)}</text>')
        return out

    ring = block.get("polygon_m") or []
    if ring:
        pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in (to_px(x, z) for x, z in ring))
        out.append(f'<polygon points="{pts}" class="poly"/>')
    seg = block.get("segment_m")
    if seg and len(seg) == 2:
        (sx0, sy0), (sx1, sy1) = to_px(*seg[0]), to_px(*seg[1])
        out.append(f'<line x1="{sx0:.1f}" y1="{sy0:.1f}" x2="{sx1:.1f}" y2="{sy1:.1f}" class="seg"/>')
    if block.get("class") == "radial" and ring:
        cx = sum(p[0] for p in ring) / len(ring)
        cz = sum(p[1] for p in ring) / len(ring)
        mx, my = to_px(cx, cz)
        out.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="2" class="ctr"/>')

    fill = block.get("fill_ratio")
    over = block.get("overhang_ratio") or 0.0
    meta = f"{block.get('class')}  {block.get('area_m2', 0):.1f}m2"
    if fill is not None:
        meta += f"  f{fill:.2f}"
    if over > 0.05:
        meta += f"  o{over:.2f}"
    if block.get("components", 1) > 1:
        meta += f"  x{block['components']}"
    meta += f"  n{len(ring)}"
    out.append(f'<text x="{x0 + 6}" y="{y0 + CELL - 8}" class="meta">{html.escape(meta)}</text>')
    return out


def build_pages(rows: list[tuple[str, dict | None, str, tuple]], title: str) -> list[str]:
    per_page = COLS * ROWS_PER_PAGE
    pages: list[str] = []
    for pno in range(0, len(rows), per_page):
        chunk = rows[pno : pno + per_page]
        width = COLS * CELL
        height = ROWS_PER_PAGE * CELL + 30
        body = [f'<rect width="{width}" height="{height}" class="bg"/>']
        head = f"{title} — {pno + 1}..{pno + len(chunk)} of {len(rows)}"
        body.append(f'<text x="8" y="20" class="hdr">{html.escape(head)}</text>')
        for i, (aid, block, reason, box) in enumerate(chunk):
            cx = (i % COLS) * CELL
            cy = (i // COLS) * CELL + 30
            body.extend(_cell_svg(cx, cy, aid, block, reason, box))
        pages.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><style>{CSS}</style>' + "".join(body) + "</svg>"
        )
    return pages


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Contact-sheet SVG of computed footprints.")
    p.add_argument("--pack", required=True)
    p.add_argument("--out", required=True, help="output directory for the SVG pages")
    p.add_argument("--class", dest="classes", default=None, help="comma list of footprint classes to include")
    p.add_argument(
        "--type",
        dest="types",
        default=None,
        help="comma list of schema types to include, or 'buildable' for the set a layout pass queries",
    )
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--config", default=None)
    args = p.parse_args(argv)

    cfg = load_config(Path(args.config) if args.config else None)
    catalogs = Path(cfg["catalogs"])
    threejs = Path(cfg["threejs_v2"])
    doc = json.loads((catalogs / f"{args.pack}.json").read_text(encoding="utf-8"))
    grid = doc.get("grid") or {}
    snap = float(grid.get("snap") or 0.25)
    tile = float(grid["tile"]) if grid.get("tile") else None
    want = {c.strip() for c in args.classes.split(",")} if args.classes else None
    if args.types == "buildable":
        want_types: set[str] | None = set(BUILDABLE_TYPES)
    elif args.types:
        want_types = {t.strip() for t in args.types.split(",")}
    else:
        want_types = None

    rows: list[tuple[str, dict | None, str, tuple]] = []
    for asset in doc["assets"]:
        if not asset.get("placeable"):
            continue
        if want_types and asset.get("type") not in want_types:
            continue
        glb = (asset.get("files") or {}).get("glb")
        if not glb:
            continue
        block, reason = analyze_footprint_detail(
            threejs / glb, (asset.get("files") or {}).get("glb_node"), snap=snap, tile_m=tile
        )
        if want and (block or {}).get("class") not in want:
            continue
        b = asset.get("bounds") or {}
        mn, mx = b.get("min"), b.get("max")
        box = (mn[0], mn[2], mx[0], mx[2]) if mn and mx else (0.0, 0.0, 1.0, 1.0)
        rows.append((asset["id"], block, reason, box))
        if args.limit and len(rows) >= args.limit:
            break

    rows.sort(key=lambda r: ((r[1] or {}).get("class") or "zz_null", r[0]))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pages = build_pages(rows, f"{args.pack} footprints")
    for i, svg in enumerate(pages, 1):
        (out / f"{args.pack}_footprints_{i:02d}.svg").write_text(svg, encoding="utf-8")

    summary = {"pack": args.pack, "assets": len(rows), "pages": len(pages), "dir": str(out)}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
