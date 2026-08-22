from pathlib import Path

from synty_inventory.sources.unreal import (
    apply_unreal_overlay,
    asset_index,
    discover_pack_dirs,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_discover_pack_dirs_none_root_returns_empty():
    assert discover_pack_dirs(None) == {}


def test_discover_pack_dirs_missing_root_returns_empty():
    assert discover_pack_dirs(Path("Z:/does/not/exist")) == {}


def test_discover_pack_dirs_uses_folder_name_as_pack_id(tmp_path: Path):
    (tmp_path / "POLYGON_City").mkdir()
    (tmp_path / "polygon-city-01").mkdir()
    mapped = discover_pack_dirs(tmp_path)
    assert mapped["POLYGON_City"] == tmp_path / "POLYGON_City"
    assert mapped["polygon-city-01"] == tmp_path / "polygon-city-01"
    assert "Polygon_City" not in mapped


def test_asset_index_exact_and_case_insensitive_match(tmp_path: Path):
    pack_root = tmp_path / "POLYGON_City"
    _touch(pack_root / "Content/Buildings/SM_Bld_Apartment_01.uasset")
    exact, ci = asset_index(tmp_path, "POLYGON_City")
    assert exact["SM_Bld_Apartment_01"] == "POLYGON_City/Content/Buildings/SM_Bld_Apartment_01.uasset"
    assert ci["sm_bld_apartment_01"] == exact["SM_Bld_Apartment_01"]


def test_asset_index_no_tree_on_disk_returns_empty():
    """The real-machine case: no unreal_root configured at all."""
    exact, ci = asset_index(None, "POLYGON_City")
    assert exact == {} and ci == {}


def test_stray_folder_does_not_overlay_unrelated_pack(tmp_path: Path):
    pack_root = tmp_path / "polygon-city-01"
    _touch(pack_root / "Content/Buildings/SM_Bld_Apartment_01.uasset")
    exact, ci = asset_index(tmp_path, "POLYGON_City")
    assert exact == {} and ci == {}


def test_apply_unreal_overlay_sets_files_field_with_no_provenance():
    asset = {"id": "SM_Bld_Apartment_01", "files": {"unreal_uasset": None}}
    apply_unreal_overlay(asset, "polygon-city-01/Content/Buildings/SM_Bld_Apartment_01.uasset")
    assert asset["files"]["unreal_uasset"] == "polygon-city-01/Content/Buildings/SM_Bld_Apartment_01.uasset"
    assert "provenance" not in asset


def test_apply_unreal_overlay_does_not_clobber_native_unreal_scan_path():
    """scan.scan_unreal() already wired files.unreal_uasset for a genuinely
    Unreal-sourced pack; a reference unreal_root overlay must not replace it."""
    asset = {"id": "SM_Bld_Apartment_01", "files": {"unreal_uasset": "OriginalPack/Content/SM_Bld_Apartment_01.uasset"}}
    apply_unreal_overlay(asset, "reference-tree/Content/SM_Bld_Apartment_01.uasset")
    assert asset["files"]["unreal_uasset"] == "OriginalPack/Content/SM_Bld_Apartment_01.uasset"


def test_apply_unreal_overlay_noop_when_no_match():
    asset = {"id": "SM_Bld_Apartment_01", "files": {"unreal_uasset": None}}
    apply_unreal_overlay(asset, None)
    assert asset["files"]["unreal_uasset"] is None
