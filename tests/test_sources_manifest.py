"""Phase 3 generator contract: GEN_* pack ingestion from sidecar manifests.

Synthetic GEN pack (docs/gen_manifest_v1.md) built per-test in tmp_path:
one correct asset, one unit-cube-scaled, one wrong pivot, one Z-up, one
missing sidecar — the failure classes Phase 4's QA gates will reject; here
Phase 3 must ingest them all, record measured truth beside declared intent,
and surface sidecar errors without failing the scan.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "glb"))
from build_glb import make_single_node_doc, plain_position_accessor, write_glb  # noqa: E402

from synty_inventory.catalog import build_catalog, load_catalog, catalog_path, scan_and_write
from synty_inventory.schema import validate_catalog
from synty_inventory.sources.manifest import (
    GenEntry,
    apply_gen_overlay,
    discover_gen_packs,
    gen_pack_ref,
    load_gen_entries,
    scan_gen,
    validate_manifest,
)

PACK = "GEN_TestTheme"


def _sidecar(stem: str, **over) -> dict:
    doc = {
        "schema": "gen-manifest/1",
        "id": stem,
        "pack": PACK,
        "type": "prop",
        "semantic_role": "exterior_prop",
        "tags": ["generated"],
        "intended_size_m": [1.0, 1.0, 1.0],
        "pivot": "base",
        "up_axis": "Y",
        "generation": {
            "model": "local-tripo-v2",
            "pipeline_version": "0.1.0",
            "prompt": f"A low poly {stem} in Synty style",
            "negative_prompt": "",
            "seed": 7,
            "created": "2026-08-22T00:00:00Z",
            "supersedes": None,
            "source_images": [],
        },
        "license": "own",
    }
    doc.update(over)
    return doc


def _write_glb_box(path: Path, mn: list[float], mx: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_glb(path, make_single_node_doc({}, plain_position_accessor(mn, mx)))


def make_gen_pack(threejs: Path) -> Path:
    """The synthetic pack: 4 manifested GLBs + 1 orphan, plus the pack-level
    manifest.json GLB listing (threejs-v2 convention)."""
    models = threejs / PACK / "models" / "Models"
    # 1. correct: 2 x 3 x 2 box, base pivot, intended size agrees
    _write_glb_box(models / "GuardTower01.glb", [-1.0, 0.0, -1.0], [1.0, 3.0, 1.0])
    (models / "GuardTower01.gen.json").write_text(
        json.dumps(
            _sidecar(
                "GuardTower01",
                type="building/shell",
                semantic_role="building_shell",
                tags=["tower", "guard"],
                intended_size_m=[2.0, 3.0, 2.0],
            )
        ),
        encoding="utf-8",
    )
    # 2. unit-cube normalized: asked for 4x6x4, mesh is 1x1x1
    _write_glb_box(models / "Crate01.glb", [-0.5, 0.0, -0.5], [0.5, 1.0, 0.5])
    (models / "Crate01.gen.json").write_text(
        json.dumps(_sidecar("Crate01", intended_size_m=[4.0, 6.0, 4.0])), encoding="utf-8"
    )
    # 3. wrong pivot: declared base, mesh centered on origin
    _write_glb_box(models / "Barrel01.glb", [-0.5, -0.75, -0.5], [0.5, 0.75, 0.5])
    (models / "Barrel01.gen.json").write_text(
        json.dumps(_sidecar("Barrel01", intended_size_m=[1.0, 1.5, 1.0])), encoding="utf-8"
    )
    # 4. Z-up export: tallest along z, flat in y
    _write_glb_box(models / "Wall01.glb", [-2.0, 0.0, -0.1], [2.0, 0.2, 3.9])
    (models / "Wall01.gen.json").write_text(
        json.dumps(_sidecar("Wall01", intended_size_m=[4.0, 4.0, 0.2])), encoding="utf-8"
    )
    # 5. orphan: GLB with no sidecar
    _write_glb_box(models / "Orphan01.glb", [-0.5, 0.0, -0.5], [0.5, 1.0, 0.5])
    listing = {
        "models": [
            f"models/Models/{stem}.glb"
            for stem in ("GuardTower01", "Crate01", "Barrel01", "Wall01", "Orphan01")
        ]
    }
    (threejs / PACK / "manifest.json").write_text(json.dumps(listing), encoding="utf-8")
    return threejs / PACK


def _build(threejs: Path, catalogs: Path) -> dict:
    ref = gen_pack_ref(threejs / PACK)
    assert ref is not None and ref.engine == "GLB"
    doc, errors = scan_and_write(ref, catalogs, threejs_v2=threejs)
    assert errors == []
    return doc


def by_id(doc: dict) -> dict:
    return {a["id"]: a for a in doc["assets"]}


# --- validate_manifest units --------------------------------------------------


def test_validate_manifest_good():
    assert validate_manifest(_sidecar("X"), "X", PACK) == []


def test_validate_manifest_catches_each_violation():
    checks = [
        (_sidecar("X", schema="nope/9"), "schema"),
        (_sidecar("Y"), "id"),  # stem mismatch: validated as stem "X"
        (_sidecar("X", pack="GEN_Other"), "pack"),
        (_sidecar("X", type="nonsense"), "type"),
        (_sidecar("X", semantic_role="nonsense"), "semantic_role"),
        (_sidecar("X", intended_size_m=[0, 1, 1]), "intended_size_m"),
        (_sidecar("X", intended_size_m=None), "intended_size_m"),
        (_sidecar("X", pivot="top"), "pivot"),
        (_sidecar("X", up_axis="Z"), "up_axis"),
        (_sidecar("X", generation=None), "generation"),
        (_sidecar("X", license=""), "license"),
        (_sidecar("X", tags=["OK_UPPER"]), "tags"),
    ]
    for doc, needle in checks:
        errs = validate_manifest(doc, "X", PACK)
        assert errs, f"expected error for {needle}"
        assert any(needle in e for e in errs), (needle, errs)


def test_validate_manifest_missing_generation_keys():
    doc = _sidecar("X")
    doc["generation"].pop("prompt")
    doc["generation"]["model"] = ""
    errs = validate_manifest(doc, "X", PACK)
    assert any("generation.prompt" in e for e in errs)
    assert any("generation.model" in e for e in errs)


# --- discovery / scan ---------------------------------------------------------


def test_discover_gen_packs(tmp_path: Path):
    make_gen_pack(tmp_path)
    (tmp_path / "POLYGON_City").mkdir()  # non-GEN sibling ignored
    (tmp_path / "GEN_Empty").mkdir()  # GEN dir without GLBs or listing ignored
    refs = discover_gen_packs(tmp_path)
    assert [r.pack_id for r in refs] == [PACK]
    assert refs[0].extras["gen_dir"] == tmp_path / PACK


def test_scan_gen_lists_every_glb_stem(tmp_path: Path):
    make_gen_pack(tmp_path)
    raws = scan_gen(tmp_path, PACK)
    assert [r.id for r in raws] == sorted(
        ["GuardTower01", "Crate01", "Barrel01", "Wall01", "Orphan01"]
    )
    assert all(r.engine == "GLB" for r in raws)


def test_gen_catalog_end_to_end(tmp_path: Path):
    threejs = tmp_path / "threejs"
    catalogs = tmp_path / "catalogs"
    make_gen_pack(threejs)
    doc = _build(threejs, catalogs)

    assert doc["engine"] == "GLB"
    assert doc["origin"] == "Generated"
    assert validate_catalog(doc) == []
    assets = by_id(doc)
    assert len(assets) == 5

    # 1. correct asset: declared structure + measured geometry
    tower = assets["GuardTower01"]
    assert tower["source"] == "generated"
    assert tower["license"] == "own"
    assert tower["type"] == "building/shell"
    assert tower["semantic_role"] == "building_shell"
    assert set(["tower", "guard"]) <= set(tower["tags"])
    assert tower["description"].startswith("A low poly GuardTower01")
    prov = tower["provenance"]
    assert prov["type"] == "declared"
    assert prov["semantic_role"] == "declared"
    assert prov["description"] == "declared"
    assert tower["files"]["glb"] == f"{PACK}/models/Models/GuardTower01.glb"
    assert tower["bounds"]["source"] == "measured"
    assert tower["bounds"]["size"] == [2.0, 3.0, 2.0]
    assert tower["bounds"]["pivot"] == "center_bottom"
    gen = tower["generation"]
    assert gen["intended_size_m"] == [2.0, 3.0, 2.0]
    assert gen["pivot"] == "base"
    assert gen["prompt"]
    assert gen["supersedes"] is None

    # 2. unit-cube: measured truth (1,1,1) recorded, declared intent (4,6,4)
    # preserved for the Phase 4 scale_agreement gate — never merged
    crate = assets["Crate01"]
    assert crate["bounds"]["size"] == [1.0, 1.0, 1.0]
    assert crate["generation"]["intended_size_m"] == [4.0, 6.0, 4.0]

    # 3. wrong pivot: measured classification wins the bounds record
    barrel = assets["Barrel01"]
    assert barrel["bounds"]["pivot"] == "center"
    assert barrel["generation"]["pivot"] == "base"

    # 4. Z-up: measured as exported, no silent reorientation
    wall = assets["Wall01"]
    assert wall["bounds"]["size"] == [4.0, 0.2, 4.0]

    # 5. orphan: ingested rules-only, error surfaced, still measured
    orphan = assets["Orphan01"]
    assert "source" not in orphan
    assert "generation" not in orphan
    assert orphan["provenance"].get("description") != "declared"
    assert orphan["bounds"]["source"] == "measured"
    assert any("Orphan01" in e for e in doc["_gen_errors"])


def test_invalid_sidecar_ingests_rules_only(tmp_path: Path):
    threejs = tmp_path / "threejs"
    catalogs = tmp_path / "catalogs"
    make_gen_pack(threejs)
    bad = _sidecar("Crate01", type="nonsense")
    (threejs / PACK / "models" / "Models" / "Crate01.gen.json").write_text(
        json.dumps(bad), encoding="utf-8"
    )
    doc = _build(threejs, catalogs)
    crate = by_id(doc)["Crate01"]
    assert "generation" not in crate
    assert any("Crate01" in e and "type invalid" in e for e in doc["_gen_errors"])
    assert validate_catalog(doc) == []


# --- provenance ranks ---------------------------------------------------------


def _entry(stem: str = "X", **over) -> GenEntry:
    return GenEntry(stem=stem, glb_rel=f"{PACK}/models/Models/{stem}.glb", manifest=_sidecar(stem, **over))


def test_declared_beats_rules_but_not_review_or_human():
    asset = {
        "id": "X",
        "tags": [],
        "description": "rules text",
        "type": "prop",
        "provenance": {"description": "vlm_reviewed"},
    }
    apply_gen_overlay(asset, _entry("X", description="declared text"))
    assert asset["description"] == "rules text"  # vlm_reviewed (4) > declared (2)
    assert asset["provenance"]["description"] == "vlm_reviewed"
    assert asset["provenance"]["type"] == "declared"  # rules (implicit) < declared

    # human provenance blocks the overlay directly; locked_fields without a
    # provenance stamp are enforced at merge time (merge.is_human_field),
    # same as every other overlay source.
    human = {"id": "Y", "description": "human text", "provenance": {"description": "human"}}
    apply_gen_overlay(human, _entry("Y", description="declared text"))
    assert human["description"] == "human text"

    from synty_inventory.merge import merge_asset

    old = {"id": "Z", "description": "hand-typed", "locked_fields": ["description"]}
    new = {"id": "Z", "description": "declared text", "provenance": {"description": "declared"}}
    assert merge_asset(old, new)["description"] == "hand-typed"


def test_rescan_keeps_declared_and_refreshes_generation(tmp_path: Path):
    threejs = tmp_path / "threejs"
    catalogs = tmp_path / "catalogs"
    make_gen_pack(threejs)
    first = by_id(_build(threejs, catalogs))["GuardTower01"]
    assert first["generation"]["seed"] == 7

    # regenerate: same stem => same asset id, new seed, supersedes chain
    side = _sidecar(
        "GuardTower01",
        type="building/shell",
        semantic_role="building_shell",
        intended_size_m=[2.0, 3.0, 2.0],
    )
    side["generation"]["seed"] = 8
    side["generation"]["supersedes"] = "2026-08-22T00:00:00Z/7"
    (threejs / PACK / "models" / "Models" / "GuardTower01.gen.json").write_text(
        json.dumps(side), encoding="utf-8"
    )
    doc = _build(threejs, catalogs)
    assert sum(1 for a in doc["assets"] if a["id"] == "GuardTower01") == 1
    tower = by_id(doc)["GuardTower01"]
    assert tower["generation"]["seed"] == 8
    assert tower["generation"]["supersedes"] == "2026-08-22T00:00:00Z/7"
    assert tower["provenance"]["type"] == "declared"
    assert tower["bounds"]["source"] == "measured"

    on_disk = load_catalog(catalog_path(catalogs, PACK))
    assert by_id(on_disk)["GuardTower01"]["generation"]["seed"] == 8


def test_build_catalog_without_pack_listing(tmp_path: Path):
    """A GEN pack that ships only GLBs + sidecars (no manifest.json listing)
    still ingests: the glob fallback lists models, the gen overlay wires glb."""
    threejs = tmp_path / "threejs"
    make_gen_pack(threejs)
    (threejs / PACK / "manifest.json").unlink()
    ref = gen_pack_ref(threejs / PACK)
    doc = build_catalog(ref, threejs_v2=threejs, catalogs_dir=tmp_path / "catalogs")
    tower = by_id(doc)["GuardTower01"]
    assert tower["files"]["glb"] == f"{PACK}/models/Models/GuardTower01.glb"
    assert tower["bounds"]["source"] == "measured"


def test_load_gen_entries_noops_for_synty_packs(tmp_path: Path):
    make_gen_pack(tmp_path)
    assert load_gen_entries(tmp_path, "POLYGON_City") == {}
    assert load_gen_entries(None, PACK) == {}
