"""Prefab -> base-mesh GLB resolution (sources.prefab_glb) and its enrich
wiring: a prefab whose name matches no GLB takes the GLB of the FBX its
active renderers show, restricted to those renderers' nodes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "glb"))

from build_glb import plain_position_accessor, write_glb  # noqa: E402

from synty_inventory.enrich import enrich_catalog  # noqa: E402
from synty_inventory.merge import stamp_auto  # noqa: E402
from synty_inventory.schema import empty_files, empty_placement  # noqa: E402
from synty_inventory.sources.glb_measure import apply_measured_bounds, measure_glb  # noqa: E402
from synty_inventory.sources.prefab_glb import PrefabGlbResolver  # noqa: E402

PACK = "POLYGON_Test_Characters"
FBX_GUID = "4a5a8c8ff5d6d2e48ab8d2b27100cf57"
PROP_GUID = "11111111111111111111111111111111"
FOREIGN_GUID = "99999999999999999999999999999999"

# Three side-by-side 1 m cubes in one bundle GLB: A at x 0..1, B at 2..3, C at 4..5.
NODES = {"Character_A": 0.0, "Character_B": 2.0, "Character_C": 4.0}


def _bundle_doc() -> dict:
    names = list(NODES)
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(names)))}],
        "nodes": [{"name": n, "mesh": i} for i, n in enumerate(names)],
        "meshes": [{"primitives": [{"attributes": {"POSITION": i}}]} for i in range(len(names))],
        "accessors": [plain_position_accessor([x, 0.0, 0.0], [x + 1.0, 1.0, 1.0]) for x in NODES.values()],
    }


def _single_doc() -> dict:
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "SM_Prop_Base", "mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [plain_position_accessor([0.0, 0.0, 0.0], [2.0, 3.0, 4.0])],
    }


def _prefab(renderers: list[tuple[str, bool, str]]) -> str:
    """Unity prefab text: one GameObject + SkinnedMeshRenderer per row
    ``(node name, active, mesh guid)``."""
    out = ["%YAML 1.1", "%TAG !u! tag:unity3d.com,2011:"]
    for i, (name, active, guid) in enumerate(renderers):
        go, smr = 1000 + i, 2000 + i
        out += [
            f"--- !u!1 &{go}",
            "GameObject:",
            f"  m_Name: {name}",
            f"  m_IsActive: {int(active)}",
            f"--- !u!137 &{smr}",
            "SkinnedMeshRenderer:",
            f"  m_GameObject: {{fileID: {go}}}",
            "  m_Enabled: 1",
            f"  m_Mesh: {{fileID: 4300000, guid: {guid}, type: 3}}",
        ]
    return "\n".join(out) + "\n"


def _world(tmp_path: Path, prefabs: dict[str, list[tuple[str, bool, str]]]) -> tuple[Path, Path]:
    extracted = tmp_path / "extracted" / PACK
    models = extracted / "Assets" / "Models"
    models.mkdir(parents=True)
    (models / "Character.fbx.meta").write_text(f"fileFormatVersion: 2\nguid: {FBX_GUID}\n", encoding="utf-8")
    (models / "SM_Prop_Base.fbx.meta").write_text(f"fileFormatVersion: 2\nguid: {PROP_GUID}\n", encoding="utf-8")
    pf_dir = extracted / "Assets" / "Prefabs"
    pf_dir.mkdir(parents=True)
    for stem, rows in prefabs.items():
        (pf_dir / f"{stem}.prefab").write_text(_prefab(rows), encoding="utf-8")

    tj = tmp_path / "threejs-v2"
    glb_dir = tj / PACK / "models" / "Models"
    glb_dir.mkdir(parents=True)
    write_glb(glb_dir / "Character.glb", _bundle_doc())
    write_glb(glb_dir / "SM_Prop_Base.glb", _single_doc())
    manifest = {"models": ["models/Models/Character.glb", "models/Models/SM_Prop_Base.glb"]}
    (tj / PACK / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return extracted, tj


def _asset(stem: str) -> dict:
    return stamp_auto(
        {
            "id": stem,
            "name": stem,
            "type": "character",
            "category": [],
            "tags": [],
            "description": "",
            "semantic_role": "unknown",
            "semantic_detail": "",
            "placement": empty_placement(),
            "ai_notes": "",
            "files": empty_files(),
            "paths": {"prefab": f"Assets/Prefabs/{stem}.prefab", "mesh": None, "materials": []},
        }
    )


def _resolver(extracted: Path, tj: Path) -> PrefabGlbResolver:
    from synty_inventory.sources.threejs_v2 import glb_index

    exact, ci = glb_index(tj, PACK)
    return PrefabGlbResolver(extracted, tj, exact, ci)


GLB = f"{PACK}/models/Models/Character.glb"

PREFABS = {
    # Synty character prefab: every mesh of the shared FBX, one switched on.
    "SM_Chr_B_01": [("Character_A", False, FBX_GUID), ("Character_B", True, FBX_GUID), ("Character_C", False, FBX_GUID)],
    # Modular preset: several meshes of one FBX at once.
    "Preset_AC": [("Character_A", True, FBX_GUID), ("Character_B", False, FBX_GUID), ("Character_C", True, FBX_GUID)],
    "All_On": [(n, True, FBX_GUID) for n in NODES],
    "Prop_Wrapper": [("Anything", True, PROP_GUID)],
    "Two_Fbx": [("Character_A", True, FBX_GUID), ("SM_Prop_Base", True, PROP_GUID)],
    "Foreign": [("Character_A", True, FOREIGN_GUID)],
    "Renamed_Node": [("Character_Z", True, FBX_GUID)],
    "All_Off": [("Character_A", False, FBX_GUID)],
}


def test_resolve_cases(tmp_path: Path):
    extracted, tj = _world(tmp_path, PREFABS)
    r = _resolver(extracted, tj)
    assert r.resolve(_asset("SM_Chr_B_01")) == (GLB, "Character_B")
    assert r.resolve(_asset("Preset_AC")) == (GLB, ["Character_A", "Character_C"])
    assert r.resolve(_asset("All_On")) == (GLB, None)
    assert r.resolve(_asset("Prop_Wrapper")) == (f"{PACK}/models/Models/SM_Prop_Base.glb", None)
    for unresolvable in ("Two_Fbx", "Foreign", "Renamed_Node", "All_Off", "No_Such_Prefab"):
        assert r.resolve(_asset(unresolvable)) is None, unresolvable


def test_measure_union_of_nodes(tmp_path: Path):
    _, tj = _world(tmp_path, {})
    mn, mx = measure_glb(tj / GLB, ["Character_A", "Character_C"])
    assert mn == [0.0, 0.0, 0.0] and mx == [5.0, 1.0, 1.0]
    mn, mx = measure_glb(tj / GLB, "Character_B")
    assert mn == [2.0, 0.0, 0.0] and mx == [3.0, 1.0, 1.0]


def test_enrich_wires_and_measures_prefab_glb(tmp_path: Path):
    extracted, tj = _world(tmp_path, PREFABS)
    doc = {
        "pack_id": PACK,
        "source": {"extracted": str(extracted)},
        "assets": [_asset("SM_Chr_B_01"), _asset("Preset_AC"), _asset("Two_Fbx")],
    }
    enrich_catalog(doc, viewer_data=None, threejs_v2=tj)
    by_id = {a["id"]: a for a in doc["assets"]}

    b = by_id["SM_Chr_B_01"]
    assert b["files"]["glb"] == GLB and b["files"]["glb_node"] == "Character_B"
    assert b["bounds"]["source"] == "measured" and b["bounds"]["min"] == [2.0, 0.0, 0.0]

    ac = by_id["Preset_AC"]
    assert ac["files"]["glb_node"] == ["Character_A", "Character_C"]
    assert ac["bounds"]["max"] == [5.0, 1.0, 1.0]

    assert not by_id["Two_Fbx"]["files"].get("glb")
    assert doc["_measure_stats"]["prefab_glb"] == 2

    # Re-enrich is stable (the stored node selection is honoured, not the whole GLB).
    enrich_catalog(doc, viewer_data=None, threejs_v2=tj)
    assert by_id["SM_Chr_B_01"]["bounds"]["min"] == [2.0, 0.0, 0.0]


def test_measured_bounds_honour_stored_glb_node(tmp_path: Path):
    _, tj = _world(tmp_path, {})
    asset = _asset("SM_Chr_B_01")
    asset["files"].update(glb=GLB, glb_node="Character_C")
    stats: dict[str, int] = {}
    apply_measured_bounds(asset, tj, {}, stats)
    assert asset["bounds"]["min"] == [4.0, 0.0, 0.0] and asset["bounds"]["max"] == [5.0, 1.0, 1.0]
