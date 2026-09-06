"""AC16 (miner half): `iter_docs`, `field`, `GuidIndex.build`, `parse_scene`
world-transform composition + unresolved accounting, and the Overview
heuristic on the fixture pack built by ``tests/fixtures/scene_mine/build_fixture.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "scene_mine"))

import build_fixture  # noqa: E402

from synty_inventory.scene_mine import stats  # noqa: E402
from synty_inventory.scene_mine.guid_index import GuidIndex, GuidIndexError  # noqa: E402
from synty_inventory.scene_mine.unity_yaml import (  # noqa: E402
    SceneParseError,
    UnityDoc,
    field,
    iter_docs,
    parse_scene,
)


@pytest.fixture
def fixture_pack(tmp_path: Path) -> dict:
    return build_fixture.build(tmp_path / "extracted")


# --- iter_docs ----------------------------------------------------------------


def test_iter_docs_class_ids_fileids_stripped(fixture_pack):
    docs = list(iter_docs(fixture_pack["demo_scene"]))
    by_fid = {d.file_id: d for d in docs}

    # 8 PrefabInstances (class 1001) + their 8 stripped Transforms (class 4).
    instance_fids = fixture_pack["instance_fileids"]
    for name, fid in instance_fids.items():
        assert by_fid[fid].class_id == 1001
        assert by_fid[fid].stripped is False
        assert by_fid[fid + 1].class_id == 4
        assert by_fid[fid + 1].stripped is True

    # Root/Child GameObject+Transform pairs are class 1 / class 4, not stripped.
    assert by_fid[build_fixture.ROOT_GO].class_id == 1
    assert by_fid[build_fixture.ROOT_TF].class_id == 4
    assert by_fid[build_fixture.ROOT_TF].stripped is False

    # RenderSettings (104) is parsed by default; LightmapSettings (157) is not
    # in the default wanted set (D3) -- only `parse_scene` asks for it too.
    assert any(d.class_id == 104 for d in docs)
    assert not any(d.class_id == 157 for d in docs)


def test_iter_docs_wanted_can_include_157(fixture_pack):
    docs = list(iter_docs(fixture_pack["demo_scene"], wanted=frozenset({157})))
    assert len(docs) == 1
    assert docs[0].body["m_LightingSettings"]["guid"] == build_fixture.LIGHTING_SETTINGS_GUID


# --- field ----------------------------------------------------------------------


def test_field_raises_scene_parse_error_naming_scene_fileid_field():
    doc = UnityDoc(class_id=4, file_id=4242, stripped=False, body={"m_Father": {"fileID": 0}})
    with pytest.raises(SceneParseError) as exc_info:
        field(doc, "m_GameObject", "fileID", scene="my_scene.unity")
    err = exc_info.value
    assert err.scene == "my_scene.unity"
    assert err.file_id == 4242
    assert err.field_path == "m_GameObject"
    assert "my_scene.unity" in str(err)
    assert "4242" in str(err)


# --- GuidIndex --------------------------------------------------------------------


def test_guid_index_duplicate_guid_names_both_paths(tmp_path: Path):
    guid = build_fixture.guid(999)
    a = tmp_path / "A.prefab"
    b = tmp_path / "sub" / "B.prefab"
    b.parent.mkdir(parents=True)
    a.with_suffix(".prefab.meta").write_text(f"guid: {guid}\n", encoding="utf-8")
    b.with_suffix(".prefab.meta").write_text(f"guid: {guid}\n", encoding="utf-8")
    with pytest.raises(GuidIndexError) as exc_info:
        GuidIndex.build(tmp_path)
    msg = str(exc_info.value)
    assert "A.prefab" in msg
    assert "B.prefab" in msg
    assert guid in msg


# --- parse_scene: world-transform composition -----------------------------------


def test_parse_scene_world_positions_match_hand_derivation(fixture_pack):
    """The fixture's Root sits at (100, 0, 50) with a 90 deg yaw about Y; the
    Child is a further local (10, 0, 0) under Root. Under a +90 deg Y
    rotation (Unity/D8 convention), a local offset (x, y, z) becomes a world
    offset (z, y, -x) -- see `build_fixture._rotate90`. Every placement's
    expected position in `EXPECTED_POSITIONS` was computed by that one rule
    applied to each instance's own local offset and its resolved parent
    (Root, Child, or P3's own composed world transform for P6, which is
    parented to P3's *stripped* Transform)."""
    index = GuidIndex.build(fixture_pack["root"])
    scene_doc = parse_scene(fixture_pack["demo_scene"], index, fixture_pack["catalog"])
    assert not scene_doc.unresolved
    assert len(scene_doc.placements) == 8

    by_name = {p.instance_name: p for p in scene_doc.placements}
    for name, expected in fixture_pack["expected_positions"].items():
        got = by_name[name].pos_m
        assert got == pytest.approx(expected, abs=1e-3), name
        assert by_name[name].yaw_deg == pytest.approx(fixture_pack["expected_yaw_deg"], abs=1e-3)

    assert by_name["P2"].static is True
    assert by_name["P5"].scale == pytest.approx((1.0, 1.0, 1.93), abs=1e-6)
    # P6 is parented through P3's own stripped Transform -> P3's instance name
    # appears in the ancestor chain, after Root/Child.
    assert by_name["P6"].parent_path == "Root/Child/P3"
    assert by_name["P3"].parent_path == "Root/Child"
    assert by_name["P1"].parent_path == "Root"


def test_parse_scene_duplicate_layout_scene_has_same_placements(fixture_pack):
    index = GuidIndex.build(fixture_pack["root"])
    demo = parse_scene(fixture_pack["demo_scene"], index, fixture_pack["catalog"])
    copy = parse_scene(fixture_pack["demo_copy_scene"], index, fixture_pack["catalog"])
    key = lambda sd: sorted((p.asset_id, p.pos_m, p.yaw_deg) for p in sd.placements)  # noqa: E731
    assert key(demo) == key(copy)


# --- unresolved accounting -------------------------------------------------------


def _unresolved_scene_text() -> tuple[str, GuidIndex, dict]:
    good_guid = build_fixture.guid(501)
    missing_meta_guid = build_fixture.guid(502)  # never in the GUID index -> no_meta
    not_in_catalog_guid = build_fixture.guid(503)  # in the index, absent from the catalog
    not_placeable_guid = build_fixture.guid(504)  # in the index + catalog, placeable: false

    parts = [build_fixture.HEADER]
    fid = 8000
    for name, g in (
        ("Good", good_guid),
        ("NoMeta", missing_meta_guid),
        ("NotInCatalog", not_in_catalog_guid),
        ("NotPlaceable", not_placeable_guid),
    ):
        parts.append(build_fixture._prefab_instance_block(fid, name, g, 0, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), False))
        fid += 10
    scene_text = "".join(parts)

    index = GuidIndex(
        by_guid={
            good_guid: "Assets/Fake/Good.prefab",
            not_in_catalog_guid: "Assets/Fake/NotInCatalog.prefab",
            not_placeable_guid: "Assets/Fake/NotPlaceable.prefab",
        }
    )
    catalog = {
        "assets": [
            {"id": "GOOD", "placeable": True, "guid": good_guid, "files": {"unity_prefab": "Assets/Fake/Good.prefab"}},
            {
                "id": "NOT_PLACEABLE",
                "placeable": False,
                "guid": not_placeable_guid,
                "files": {"unity_prefab": "Assets/Fake/NotPlaceable.prefab"},
            },
        ]
    }
    return scene_text, index, catalog


def test_parse_scene_unresolved_accounting(tmp_path: Path):
    scene_text, index, catalog = _unresolved_scene_text()
    scene_path = tmp_path / "Unresolved.unity"
    scene_path.write_text(scene_text, encoding="utf-8")

    scene_doc = parse_scene(scene_path, index, catalog)

    assert [p.asset_id for p in scene_doc.placements] == ["GOOD"]
    reasons = {u.instance_name: u.reason for u in scene_doc.unresolved}
    assert reasons == {
        "NoMeta": "no_meta",
        "NotInCatalog": "not_in_catalog",
        "NotPlaceable": "not_placeable",
    }


# --- Overview heuristic ------------------------------------------------------------


def test_overview_heuristic_fires_on_the_catalogue_grid(fixture_pack):
    index = GuidIndex.build(fixture_pack["root"])
    overview_doc = parse_scene(fixture_pack["overview_scene"], index, fixture_pack["catalog"])
    placements = [
        {"asset_id": p.asset_id, "pos_m": p.pos_m, "yaw_deg": p.yaw_deg} for p in overview_doc.placements
    ]
    check = stats.is_overview_scene(placements)
    assert check.is_overview is True
    assert check.placements == 100 == stats.MIN_LAYOUT_PLACEMENTS  # the fixture grid sits exactly on the floor
    assert check.distinct_ratio == pytest.approx(1.0)


def test_overview_heuristic_does_not_fire_on_the_demo_layout(fixture_pack):
    index = GuidIndex.build(fixture_pack["root"])
    demo_doc = parse_scene(fixture_pack["demo_scene"], index, fixture_pack["catalog"])
    placements = [{"asset_id": p.asset_id, "pos_m": p.pos_m, "yaw_deg": p.yaw_deg} for p in demo_doc.placements]
    check = stats.is_overview_scene(placements)
    # 8 placements, all distinct -- a one-of-each ratio, but far below the 100-placement floor: a small
    # authored scene is not a catalogue grid (Sci-Fi City's 16-object Demo_TriplanarDirt is the real case).
    assert check.distinct_ratio == pytest.approx(1.0)
    assert check.is_overview is False


def _synthetic(n: int, distinct: int) -> list[dict]:
    # `distinct` unique ids, the rest repeats of the first; positions irrelevant (no spacing term any more)
    return [
        {"asset_id": f"A_{i if i < distinct else 0:03d}", "pos_m": (float(i), 0.0, 0.0), "yaw_deg": 0.0}
        for i in range(n)
    ]


@pytest.mark.parametrize(
    ("n", "distinct", "expected"),
    [
        (100, 90, True),  # both thresholds met exactly
        (100, 89, False),  # ratio just under 0.9
        (99, 99, False),  # one placement under the floor, even at ratio 1.0
        (602, 602, True),  # Sci-Fi City Overview.unity as measured 2026-09-06
        (333, 333, True),  # City Overview.unity as measured
        (5177, 246, False),  # City Demo.unity as measured (0.048)
        (2357, 366, False),  # Sci-Fi City Demo.unity as measured (0.155)
        (16, 8, False),  # Sci-Fi City Demo_TriplanarDirt as measured (0.5)
        (0, 0, False),
    ],
)
def test_overview_rule_thresholds(n, distinct, expected):
    check = stats.is_overview_scene(_synthetic(n, distinct))
    assert check.is_overview is expected
    assert check.placements == n and check.distinct == distinct
