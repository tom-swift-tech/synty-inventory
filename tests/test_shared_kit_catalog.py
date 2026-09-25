"""Standalone shared-kit catalog (discover.SHARED_KIT_PACKS, e.g. POLYGON_Generic)."""

import json
import shutil
from pathlib import Path

import pytest

from synty_inventory import discover as discover_mod
from synty_inventory.catalog import build_catalog
from synty_inventory.discover import discover, shared_kit_refs
from synty_inventory.scan import scan_extracted
from synty_inventory.schema import validate_catalog

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HOST = FIXTURES / "FakePack"


@pytest.fixture
def fake_generic(monkeypatch):
    monkeypatch.setattr(
        discover_mod,
        "SHARED_KIT_PACKS",
        {"FAKE_Generic": {"kit": "PolygonGeneric", "host_pack": "FakePack"}},
    )


def test_only_kit_keeps_shared_twin_over_pack_copy():
    got = {a.id: a for a in scan_extracted(HOST, include_shared=True, only_kit="polygongeneric")}
    assert set(got) == {"SM_Prop_GenericOnly_01", "SM_Prop_SharedTwin_01"}
    twin = got["SM_Prop_SharedTwin_01"]
    assert twin.shared is True
    assert "PolygonGeneric" in twin.prefab.rel


def test_shared_kit_refs_need_host_with_kit(fake_generic, tmp_path):
    refs = shared_kit_refs(FIXTURES)
    assert [r.pack_id for r in refs] == ["FAKE_Generic"]
    assert refs[0].extracted_path == HOST
    assert refs[0].extras == {"shared_kit": "PolygonGeneric", "host_pack": "FakePack"}
    assert shared_kit_refs(tmp_path) == []
    assert shared_kit_refs(None) == []


def test_discover_root_adds_shared_kit_pack(fake_generic, tmp_path):
    # Live layout: a Unity root of .unitypackage files + a separate extracted root.
    unity, extracted = tmp_path / "Unity", tmp_path / "extracted"
    unity.mkdir()
    (unity / "FakePack_Unity_2022_3_v1_0.unitypackage").write_bytes(b"")
    shutil.copytree(HOST, extracted / "FakePack")
    refs = {r.pack_id: r for r in discover(unity, extracted_root=extracted)}
    assert set(refs) == {"FakePack", "FAKE_Generic"}
    assert refs["FAKE_Generic"].extracted_path == extracted / "FakePack"


def test_build_shared_kit_catalog_uses_host_glbs_without_host_assets(fake_generic, tmp_path):
    manifest = {
        "models": [
            "models/Models/SM_Prop_GenericOnly_01.glb",
            "models/Models/SM_Bld_Shop_01.glb",
            "models/Models/SM_Prop_HostGlbOnly_01.glb",
        ]
    }
    (tmp_path / "FakePack").mkdir()
    (tmp_path / "FakePack" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    doc = build_catalog(shared_kit_refs(FIXTURES)[0], threejs_v2=tmp_path)
    assert validate_catalog(doc) == []
    by_id = {a["id"]: a for a in doc["assets"]}
    # Kit assets only: no host prefabs, no host GLB-only injection.
    assert set(by_id) == {"SM_Prop_GenericOnly_01", "SM_Prop_SharedTwin_01"}
    assert by_id["SM_Prop_GenericOnly_01"]["files"]["glb"] == "FakePack/models/Models/SM_Prop_GenericOnly_01.glb"
    assert all(a["shared_kit"] and a["kit"] == "PolygonGeneric" for a in doc["assets"])
    assert doc["source"]["host_pack"] == "FakePack"
    assert doc["source"]["shared_kit"] == "PolygonGeneric"
