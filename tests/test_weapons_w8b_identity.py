"""W8b: the default export is byte-identical to the W7 export (INV-19, D-10; AC77's default half as far as W8b reaches).

``fixtures/weapons/w7_default_export.json`` is a REAL W7 export: the default ``weapons export --game golden --packs
FAKE_Fantasy,FAKE_Modern,FAKE_Shared`` of the ``review_helpers`` synthetic world, produced by the W7 tree (synty-inventory
main at e6e82b6, before any W8 code) and committed unedited. This build must reproduce it byte for byte even though the
directory it exports from now carries ``geometry.mounts`` on every eligible host: the export drops the block, adds no key,
leaves ``rules_digest`` (7b9829af37328fe7) and ``geometry_version`` (5) alone and does not mention ``attach_version``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_here = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("review_helpers", _here / "fixtures" / "weapons" / "review_helpers.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
_spec2 = importlib.util.spec_from_file_location("w8a_attach", _here / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(A)

from synty_inventory.weapons import export as X  # noqa: E402

GOLDEN = _here / "fixtures" / "weapons" / "w7_default_export.json"
PACKS = "FAKE_Fantasy,FAKE_Modern,FAKE_Shared"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w8b_identity")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(X, "_repo_root", lambda: None)  # the pytest tmp dir sits inside this checkout
    cat = H.make_catalogs(tmp, shared=True)
    root = H.make_threejs(tmp, cat)
    directory, _ = H.build_and_write(cat, threejs_v2_dir=root)
    out_dir = tmp / "game_repo"
    out_dir.mkdir()
    yield {"tmp": tmp, "cat": cat, "directory": directory, "cfg": H.write_config(tmp, cat), "out": out_dir}
    mp.undo()


def export(world, capsys, *flags, name="snap.json", packs=PACKS):
    out = world["out"] / name
    code, res = H.run(world["cfg"], capsys, ["weapons", "export", "--game", "golden", "--packs", packs, *flags, "--out", str(out)])
    return code, res, out


def golden_text() -> str:
    return GOLDEN.read_bytes().decode("utf-8").replace("\r\n", "\n")  # a CRLF checkout is the same file


def test_the_golden_is_the_w7_header(world):
    doc = json.loads(golden_text())
    gf = doc["generated_from"]
    assert (gf["geometry_version"], gf["rules_digest"], gf["weapon_version"]) == (5, "7b9829af37328fe7", 1)
    assert "attach_version" not in gf and "attachments" not in gf["filter"]
    assert len(doc["weapons"]) == 89
    assert "mounts" not in golden_text()


def test_the_directory_this_build_exports_from_does_carry_mounts(world):
    # the golden proves nothing unless the export had a block to drop
    hosts = [w for w in world["directory"]["weapons"] if (w["geometry"] or {}).get("mounts")]
    assert len(hosts) >= 2
    assert all(sorted(w["geometry"]["mounts"]) == ["laser_light", "magazine", "muzzle", "optic", "underbarrel"] for w in hosts)


def test_the_default_export_equals_the_w7_golden_byte_for_byte(world, capsys):
    code, _, out = export(world, capsys)
    assert code == 0
    got = out.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert got == golden_text()
    assert '"mounts"' not in got and "attach_version" not in got and "mount_ambiguous" not in got


def test_the_header_keeps_the_w7_rules_digest_and_geometry_version(world, capsys):
    _, _, out = export(world, capsys, name="hdr.json")
    gf = json.loads(out.read_text(encoding="utf-8"))["generated_from"]
    assert gf["rules_digest"] == "7b9829af37328fe7" and gf["geometry_version"] == 5
    assert sorted(gf) == ["filter", "geometry_version", "overrides_digest", "packs", "rules_digest", "tool", "weapon_version"]


def test_a_mount_host_review_reason_never_reaches_the_default_export(tmp_path, monkeypatch, capsys):
    # mount_ambiguous is a directory-side reason of W8b; the W7-format export has to look as if W8 did not exist
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(X, "_repo_root", lambda: None)
    directory, excluded, cat, _root = A.build_mount_world(tmp_path)
    ambiguous = [w["id"] for w in directory["weapons"] if "mount_ambiguous" in w["review"]["reasons"]]
    assert ambiguous == [f"{A.MOUNT_PACK}/SM_Wep_Rifle_Double_01"]
    from synty_inventory.weapons.directory import write_directory

    write_directory(cat, directory, excluded)
    cfg = H.write_config(tmp_path, cat)
    out = tmp_path / "game_repo" / "snap.json"
    out.parent.mkdir()
    code, _res = H.run(cfg, capsys, ["weapons", "export", "--game", "golden", "--packs", A.MOUNT_PACK, "--out", str(out)])
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert '"mounts"' not in text and "mount_ambiguous" not in text and "attach_version" not in text
