"""Unit tests for ``packs.contact_sheet`` (spec §3.3 ``packs contact-sheet``,
G1 gate artifact) -- fixture catalogs and a monkeypatched renderer, no real
GLBs or ``synty-glb`` subprocess."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from synty_inventory.packs.contact_sheet import (
    CELL,
    COLS,
    LABEL_H,
    PAD,
    build_contact_sheet,
    compose_grid,
    resolve_cell_image,
    select_representative,
)


def _asset(id_, *, role="exterior_prop", placeable=True, glb=None):
    return {"id": id_, "semantic_role": role, "placeable": placeable, "files": {"glb": glb}}


def _doc(pack_id, assets):
    return {"pack_id": pack_id, "assets": assets}


# --- select_representative --------------------------------------------------------


def test_select_representative_is_deterministic_across_calls():
    doc = _doc("PACK", [_asset(f"z{i}", role="prop") for i in range(5)] + [_asset(f"a{i}", role="wall") for i in range(5)])
    first = [a["id"] for a in select_representative(doc, 6)]
    second = [a["id"] for a in select_representative(doc, 6)]
    assert first == second


def test_select_representative_round_robins_across_roles():
    doc = _doc(
        "PACK",
        [_asset("prop_a", role="prop"), _asset("prop_b", role="prop"), _asset("wall_a", role="wall")],
    )
    picked = [a["id"] for a in select_representative(doc, 3)]
    # groups sorted alphabetically ("prop" < "wall"); round-robin picks index
    # 0 from each group first, then index 1 from whichever group still has one
    assert picked == ["prop_a", "wall_a", "prop_b"]


def test_select_representative_caps_at_per_pack():
    doc = _doc("PACK", [_asset(f"a{i}") for i in range(100)])
    assert len(select_representative(doc, 10)) == 10


def test_select_representative_excludes_nonplaceable():
    doc = _doc("PACK", [_asset("a", placeable=True), _asset("b", placeable=False)])
    picked = [a["id"] for a in select_representative(doc, 10)]
    assert picked == ["a"]


# --- resolve_cell_image ------------------------------------------------------------


def test_resolve_cell_image_falls_back_to_preview_without_glb(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    preview_dir = catalogs_dir / "previews" / "PACK"
    preview_dir.mkdir(parents=True)
    im = Image.new("RGB", (4, 4))
    im.save(preview_dir / "asset_01.png")

    asset = _asset("asset_01", glb=None)
    img, source = resolve_cell_image(
        asset, "PACK", catalogs_dir=catalogs_dir, threejs_v2=None, synty_glb_root=None
    )
    assert source == "preview"
    assert img == preview_dir / "asset_01.png"


def test_resolve_cell_image_no_source_anywhere(tmp_path: Path):
    asset = _asset("asset_01", glb=None)
    img, source = resolve_cell_image(
        asset, "PACK", catalogs_dir=tmp_path, threejs_v2=None, synty_glb_root=None
    )
    assert img is None
    assert source == "no_glb"


def test_resolve_cell_image_renders_via_synty_glb(tmp_path: Path, monkeypatch):
    threejs_v2 = tmp_path / "threejs_v2"
    glb_path = threejs_v2 / "PACK" / "models" / "asset_01.glb"
    glb_path.parent.mkdir(parents=True)
    glb_path.write_bytes(b"fake-glb")
    synty_glb_root = tmp_path / "synty-glb"
    synty_glb_root.mkdir()

    def fake_render(glb, stills_dir, views, root, *, timeout=600):
        stills_dir.mkdir(parents=True, exist_ok=True)
        out = stills_dir / f"{views[0]}.png"
        Image.new("RGB", (4, 4)).save(out)
        return [out]

    monkeypatch.setattr("synty_inventory.review._render_stills", fake_render)

    asset = _asset("asset_01", glb="PACK/models/asset_01.glb")
    img, source = resolve_cell_image(
        asset,
        "PACK",
        catalogs_dir=None,
        threejs_v2=threejs_v2,
        synty_glb_root=synty_glb_root,
    )
    assert source == "rendered"
    assert img is not None and img.is_file()


def test_resolve_cell_image_render_failure_reports_render_failed(tmp_path: Path, monkeypatch):
    threejs_v2 = tmp_path / "threejs_v2"
    glb_path = threejs_v2 / "PACK" / "models" / "asset_01.glb"
    glb_path.parent.mkdir(parents=True)
    glb_path.write_bytes(b"fake-glb")
    synty_glb_root = tmp_path / "synty-glb"
    synty_glb_root.mkdir()

    from synty_inventory.review import RenderError

    def fake_render(glb, stills_dir, views, root, *, timeout=600):
        raise RenderError("boom")

    monkeypatch.setattr("synty_inventory.review._render_stills", fake_render)

    asset = _asset("asset_01", glb="PACK/models/asset_01.glb")
    img, source = resolve_cell_image(
        asset, "PACK", catalogs_dir=None, threejs_v2=threejs_v2, synty_glb_root=synty_glb_root
    )
    assert img is None
    assert source == "render_failed"


# --- compose_grid --------------------------------------------------------------------


def test_compose_grid_writes_valid_png(tmp_path: Path):
    cell_img = tmp_path / "cell.png"
    Image.new("RGB", (16, 16)).save(cell_img)
    blocks = [
        {"pack_id": "PACK_A", "cells": [("a", cell_img, "rendered"), ("b", None, "no_glb")]},
        {"pack_id": "PACK_B", "cells": []},
    ]
    out = tmp_path / "sheet.png"
    compose_grid(blocks, out)
    assert out.is_file()
    with Image.open(out) as im:
        assert im.width == COLS * (CELL + PAD) + PAD
        # PACK_A: 1 row of cells; PACK_B: 0 cells -> treated as 1 placeholder row
        expected_h = 2 * (LABEL_H + 1 * (CELL + PAD) + PAD)
        assert im.height == expected_h


# --- build_contact_sheet (integration, one labelled row-block per pack) ------------


def test_build_contact_sheet_gives_every_requested_pack_a_row_even_if_catalog_missing(tmp_path: Path):
    docs = {"PACK_A": _doc("PACK_A", [_asset("a1"), _asset("a2")])}

    def load_doc(pack_id):
        return docs.get(pack_id)

    out = tmp_path / "sheet.png"
    report = build_contact_sheet(
        ["PACK_A", "PACK_MISSING"],
        load_doc=load_doc,
        catalogs_dir=None,
        threejs_v2=None,
        synty_glb_root=None,
        out_path=out,
        per_pack=10,
    )
    assert out.is_file()
    assert [p["pack_id"] for p in report["packs"]] == ["PACK_A", "PACK_MISSING"]
    missing_row = next(p for p in report["packs"] if p["pack_id"] == "PACK_MISSING")
    assert missing_row["error"] == "catalog not found"
