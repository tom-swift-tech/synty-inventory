"""skeleton_asset: a prefab-less FBX in an ``Animations/`` folder is a clip even
when its stem (POLYGON_Dogs ``_POLYGON_Dog_*``) carries no clip prefix."""

from pathlib import Path

from synty_inventory.enrich import skeleton_asset
from synty_inventory.scan import RawAsset, RawFile


def _raw(stem: str, rel: str, prefab: bool = False) -> RawAsset:
    mesh = RawFile(stem=stem, rel=rel, abs_path=Path(rel), kind="mesh")
    pf = RawFile(stem=stem, rel=rel.replace(".fbx", ".prefab"), abs_path=Path(rel), kind="prefab") if prefab else None
    return RawAsset(id=stem, kit="PolygonDog", shared=False, mesh=mesh, prefab=pf)


def test_animations_folder_fbx_is_clip() -> None:
    stem = "_POLYGON_Dog_Action_Sitting_Bark"
    a = skeleton_asset(_raw(stem, f"Assets/Synty/PolygonDog/Animations/Actions_Sitting/{stem}.fbx"), "POLYGON_Dogs", None)
    assert a["type"] == "animation"
    assert a["kind"] == "animation"
    assert a["placeable"] is False
    assert a["semantic_role"] == "animation_clip"


def test_same_stem_outside_animations_stays_prop() -> None:
    stem = "_POLYGON_Dog_Action_Sitting_Bark"
    a = skeleton_asset(_raw(stem, f"Assets/Synty/PolygonDog/Models/{stem}.fbx"), "POLYGON_Dogs", None)
    assert a["type"] == "prop"
    assert a["placeable"] is True


def test_real_mesh_or_prefab_in_animations_folder_is_kept() -> None:
    sm = skeleton_asset(_raw("SM_Prop_Bone_01", "Assets/Synty/PolygonDog/Animations/SM_Prop_Bone_01.fbx"), "POLYGON_Dogs", None)
    assert sm["placeable"] is True
    pf = skeleton_asset(
        _raw("Dog_Bowl_01", "Assets/Synty/PolygonDog/Animations/Dog_Bowl_01.fbx", prefab=True), "POLYGON_Dogs", None
    )
    assert pf["type"] != "animation"
