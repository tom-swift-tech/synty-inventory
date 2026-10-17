"""Weapon directory W3: icon harness and ``weapons icons`` (AC17, AC18; docs/weapon_directory.md section 3.8).

Three layers:
- pure parts (input sha, framing, link paths, skip logic, PNG encode, link write-back, carry-forward): no browser;
- AC18: runs everywhere, because the renderer is simulated as unavailable;
- AC17 and the batch behaviour (failed asset, poisoned cache, link-back): need Playwright, Chromium and the synty-glb
  checkout (``SYNTI_SYNTY_GLB_ROOT`` or a default location below). They skip with an explicit reason when one is missing
  and must PASS on the development machine.

Every bound below is a literal worked out from the spec (88 % fill, 6 % padding), not an import of a constant under test.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import struct
import sys
import zlib
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("wfx", _FIX / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)
_spec = importlib.util.spec_from_file_location("make_glbs", _FIX / "make_glbs.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

from synty_inventory.cli import main  # noqa: E402
from synty_inventory.weapons import guards, icons, to_text  # noqa: E402
from synty_inventory.weapons.directory import (  # noqa: E402
    DIRECTORY_NAME,
    build_directory_report,
    read_json,
    write_directory,
)
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

# Where the synty-glb checkout lives when SYNTI_SYNTY_GLB_ROOT is unset: beside this repo (a sibling checkout or
# worktree under the same tools folder), then Tom's usual spot. The folder name is assembled so the public source
# carries no machine path (tests/test_paths.py).
DEFAULT_SYNTY_GLB_ROOTS = (
    Path(__file__).resolve().parents[2] / "synty-glb",
    Path("D:/") / "_".join(("game", "assets", "library")) / "tools" / "synty-glb",
)
ENV_KEYS = ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
            "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT")

# fixture record -> (named fixture GLB, expected archetype, expected kind). The record's classification decides
# the geometry axes; the GLB is the synthetic stand-in generated at test time.
SIX = {
    "FAKE_Modern/SM_Wep_Rifle_Assault_01": ("gun", "rifle", "ranged"),
    "FAKE_Fantasy/SM_Wep_Claymore_06": ("sword", "sword", "melee"),
    "FAKE_Fantasy/SM_Wep_Spear_01": ("spear", "spear", "melee"),
    "FAKE_Fantasy/SM_Wep_Axe_01": ("axe", "axe", "melee"),
    "FAKE_Fantasy/SM_Wep_Bow_03": ("bow", "bow", "ranged"),
    "FAKE_Fantasy/SM_Wep_Shield_01": ("shield", "shield", "shield"),
}


# --- helpers -------------------------------------------------------------------------------------------------------


def read_png(data: bytes) -> np.ndarray:
    """Decode an 8-bit RGBA, non-interlaced PNG (all five filter types) to an (h, w, 4) uint8 array."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos:pos + 4])
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert (depth, ctype, interlace) == (8, 6, 0), "expected 8-bit RGBA, not interlaced"
        elif tag == b"IDAT":
            idat += body
    raw = zlib.decompress(idat)
    stride = w * 4
    out = np.zeros((h, stride), dtype=np.int32)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = np.frombuffer(raw, np.uint8, stride, y * (stride + 1) + 1).astype(np.int32)
        up = out[y - 1] if y else np.zeros(stride, dtype=np.int32)
        if ft == 0:
            cur = line
        elif ft == 2:
            cur = (line + up) & 255
        else:  # Sub, Average and Paeth need the left neighbour: a byte loop
            cur = np.zeros(stride, dtype=np.int32)
            for i in range(stride):
                a = int(cur[i - 4]) if i >= 4 else 0
                b = int(up[i])
                c = int(up[i - 4]) if i >= 4 else 0
                if ft == 1:
                    pred = a
                elif ft == 3:
                    pred = (a + b) // 2
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[i] = (int(line[i]) + pred) & 255
        out[y] = cur
    return out.astype(np.uint8).reshape(h, w, 4)


def synty_glb_root() -> Path | None:
    env = os.environ.get("SYNTI_SYNTY_GLB_ROOT")
    for cand in ([Path(env)] if env else []) + list(DEFAULT_SYNTY_GLB_ROOTS):
        if (cand / "node_modules" / "three" / "build" / "three.module.js").is_file():
            return cand
    return None


_RENDERER: dict = {}


def renderer_root() -> Path:
    """The synty-glb root, or skip with the reason (no Playwright / Chromium / three.js here). Probed once."""
    if "root" not in _RENDERER:
        reason = None
        root = synty_glb_root()
        if root is None:
            reason = "synty-glb root with node_modules/three not found (set SYNTI_SYNTY_GLB_ROOT)"
        else:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                reason = "the playwright package is not installed"
            else:
                try:
                    with sync_playwright() as pw:
                        icons._launch_browser(pw, False).close()
                except Exception as exc:  # noqa: BLE001
                    reason = f"Chromium cannot be launched: {str(exc).splitlines()[0] if str(exc) else exc!r}"
        _RENDERER.update(root=root, reason=reason)
    if _RENDERER["reason"]:
        pytest.skip(_RENDERER["reason"])
    return _RENDERER["root"]


def write_config(tmp: Path, cat: Path, *, threejs: Path | None = None, glb_root: Path | None = None) -> Path:
    lines = [f'unity_root: "{tmp.as_posix()}/unity"', f'extracted_root: "{tmp.as_posix()}/extracted"',
             f'catalogs: "{cat.as_posix()}"']
    if threejs is not None:
        lines.append(f'threejs_v2: "{threejs.as_posix()}"')
    if glb_root is not None:
        lines.append(f'synty_glb_root: "{glb_root.as_posix()}"')
    cfg = tmp / "config.yaml"
    cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cfg


def run_cli(cfg: Path, *argv: str) -> tuple[int, dict]:
    """``synty-inventory --config CFG weapons icons ...`` with a clean SYNTI_* environment; (exit code, JSON)."""
    out = io.StringIO()
    with mock.patch.dict(os.environ), mock.patch.object(guards, "other_inventory_processes", return_value=[]):
        # (the sole-runner guard would otherwise list the machine's processes, about a second per call)
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        with contextlib.redirect_stdout(out):
            code = main(["--config", str(cfg), "weapons", "icons", *argv])
    return code, json.loads(out.getvalue())


def snapshot(root: Path) -> dict[str, tuple]:
    """Every file and directory under ``root``: path -> (kind, sha256, mtime_ns). Any write changes it."""
    snap: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            snap[rel] = ("dir", None, None)
        else:
            snap[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    return snap


def make_world(tmp: Path) -> dict:
    """Fixture catalogs + a threejs_v2 root holding the six named fixture GLBs + a measured, written directory."""
    cat = wfx.make_catalogs_dir(tmp)
    root = tmp / "threejs"
    named = M.generate_all(tmp / "named")
    base, _ = wfx.build(cat, measure=False)
    by_id = wfx.records_by_id(base)
    for rid, (glb_name, _arch, _kind) in SIX.items():
        dest = root / by_id[rid]["files"]["glb"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(named[glb_name].read_bytes())
    directory, excluded, _ = build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=wfx.pack_settings(), threejs_v2_dir=root, geometry_cache={})
    write_directory(cat, directory, excluded)
    by_id = wfx.records_by_id(directory)
    for rid, (_g, arch, kind) in SIX.items():
        rec = by_id[rid]
        assert (rec["archetype"], rec["kind"]) == (arch, kind) and rec["geometry"] is not None, rid
    return {"cat": cat, "root": root, "named": named, "dir": directory, "excl": excluded,
            "dpath": cat / "weapons" / DIRECTORY_NAME}


def fake_glb_root(tmp: Path) -> Path:
    """A synty-glb look-alike that passes the static availability check (the launch is what tests then break)."""
    entry = tmp / "fake_glb" / "node_modules" / "three" / "build" / "three.module.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("// stand-in\n", encoding="utf-8")
    return tmp / "fake_glb"


# --- pure parts ----------------------------------------------------------------------------------------------------


def test_input_sha_is_16_hex_deterministic_and_covers_every_input():
    basis = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    base = icons.icon_input_sha("a" * 64, None, 1.0, basis)
    assert len(base) == 16 and int(base, 16) >= 0
    assert icons.icon_input_sha("a" * 64, None, 1.0, basis) == base
    variants = [
        icons.icon_input_sha("b" * 64, None, 1.0, basis),  # other GLB bytes
        icons.icon_input_sha("a" * 64, "Bow_A", 1.0, basis),  # a node selection
        icons.icon_input_sha("a" * 64, ["Bow_A", "Bow_B"], 1.0, basis),
        icons.icon_input_sha("a" * 64, None, 0.01, basis),  # the glb_scale correction
        icons.icon_input_sha("a" * 64, None, 1.0, [[0, 0, 1], [1, 0, 0], [0, 1, 0]]),  # a corrected axis
    ]
    assert len({base, *variants}) == 6
    assert icons.node_tag(["Bow_A", "Bow_B"]) == "Bow_A+Bow_B" and icons.node_tag("Bow_A") == "Bow_A"


def test_camera_forward_is_screen_right_and_shields_are_face_on():
    def screen_right(d):
        look = [-c for c in d]  # from the camera towards the model
        up = [0.0, 1.0, 0.0]
        right = [look[1] * up[2] - look[2] * up[1], look[2] * up[0] - look[0] * up[2], look[0] * up[1] - look[1] * up[0]]
        n = math.sqrt(sum(c * c for c in right))
        return [c / n for c in right]

    w = icons.camera_direction(False)
    assert math.isclose(sum(c * c for c in w), 1.0, abs_tol=1e-9)
    # azimuth 25, elevation 15: cos25 cos15 = 0.8754, sin15 = 0.2588, sin25 cos15 = 0.4082
    assert w == pytest.approx((-0.8754, 0.2588, 0.4082), abs=5e-4)
    r = screen_right(w)  # in the item frame, forward is +Z
    assert r[2] > 0.9 and abs(r[1]) < 1e-9  # forward points to screen right, and the horizon stays level
    s = icons.camera_direction(True)
    assert s[2] > 0.85 and s[1] > 0  # on the face (+forward) side, raised by the elevation
    assert screen_right(s)[0] > 0.9  # the shield's item +X (its width axis) is screen right


def test_fit_frustum_fills_88_percent_of_the_long_edge_and_centres():
    f = icons.fit_frustum([2.0, -1.0, -5.0], [4.0, -0.5, -3.0])  # 2.0 wide, 0.5 tall: width is the long side
    width, height = f["right"] - f["left"], f["top"] - f["bottom"]
    assert width == pytest.approx(height) and width == pytest.approx(2.0 / 0.88)
    assert (f["left"] + f["right"]) / 2 == pytest.approx(3.0) and (f["bottom"] + f["top"]) / 2 == pytest.approx(-0.75)
    assert (3.0 - f["left"]) / width == pytest.approx(0.5)
    assert (2.0 - f["left"]) / width == pytest.approx(0.06, abs=1e-12)  # 6 % padding on the long edge
    assert f["near"] < 3.0 and f["far"] > 5.0  # the camera looks down -z: depth 3..5 lies between near and far
    tall = icons.fit_frustum([0, 0, 0], [0.2, 1.0, 0.1])
    assert (tall["top"] - tall["bottom"]) == pytest.approx(1.0 / 0.88)


@pytest.mark.parametrize("lo,hi", [([0, 0, 0], [0, 0, 1]), ([0, 0, 0], [float("inf"), 1, 1]),
                                   ([0, 0, 0], [float("nan"), 1, 1])])
def test_fit_frustum_rejects_degenerate_bounds(lo, hi):
    with pytest.raises(icons.RenderError):
        icons.fit_frustum(lo, hi)


def test_link_paths_are_relative_with_forward_slashes():
    out = Path("C:/cat/weapons/icons")
    assert icons.link_paths(out, "POLYGON_X", "SM_Wep_A") == ("icons/POLYGON_X/SM_Wep_A.png",
                                                              "icons/POLYGON_X/SM_Wep_A@64.png")
    assert icons.link_paths(out, "P", "SM Wep B")[1] == "icons/P/SM Wep B@64.png"


def test_png_encode_decode_roundtrip_is_exact_and_deterministic(tmp_path):
    rng = np.random.default_rng(7)
    px = rng.integers(0, 256, size=(8, 8, 4), dtype=np.uint8)
    a, b = icons.encode_png(px), icons.encode_png(px)
    assert a == b and a[:8] == b"\x89PNG\r\n\x1a\n"
    assert np.array_equal(read_png(a), px)
    p = tmp_path / "x.png"
    p.write_bytes(icons.encode_png(np.zeros((64, 64, 4), np.uint8)))
    assert icons.png_ok(p, 64) and not icons.png_ok(p, 256)


def test_unpremultiply_and_premultiplied_downsample_leave_no_dark_fringe():
    px = np.array([[[128, 0, 0, 128]]], dtype=np.uint8)  # half-covered pure red, premultiplied
    assert icons.unpremultiply(px)[0, 0].tolist() == [255, 0, 0, 128]
    assert icons.unpremultiply(np.zeros((1, 1, 4), np.uint8))[0, 0].tolist() == [0, 0, 0, 0]
    block = np.zeros((2, 2, 4), dtype=np.uint8)
    block[0, :] = [255, 0, 0, 255]  # two opaque red pixels over two empty ones
    small = icons.downsample(block, 1)
    assert small.shape == (1, 1, 4) and small[0, 0].tolist() == [128, 0, 0, 128]  # (510 + 2) // 4
    assert icons.unpremultiply(small)[0, 0].tolist() == [255, 0, 0, 128]  # still pure red at half alpha
    with pytest.raises(ValueError):
        icons.downsample(np.zeros((6, 6, 4), np.uint8), 4)


def _vis(sha, icon="icons/P/A.png", thumb="icons/P/A@64.png"):
    return {"icon": icon, "thumb": thumb, "icon_input_sha": sha, "variants": []}


def test_skip_logic(tmp_path):
    base = tmp_path / "weapons"
    icon, thumb = "icons/P/A.png", "icons/P/A@64.png"
    for rel, size in ((icon, 256), (thumb, 64)):
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_bytes(icons.encode_png(np.zeros((size, size, 4), np.uint8)))

    def need(vis, sha="s1", size=256, rebuild=False):
        return icons.needs_render(vis, sha, icon, thumb, base, size, rebuild)

    assert need(_vis("s1")) is False  # unchanged sha, both PNGs intact: skipped
    assert need(_vis("s1"), rebuild=True) is True
    assert need(_vis("s0")) is True  # sha mismatch
    assert need({"icon": None, "thumb": None, "icon_input_sha": None, "variants": []}) is True
    assert need(_vis("s1", icon="icons/P/other.png")) is True  # a link pointing somewhere else
    assert need(_vis("s1"), size=128) is True  # a --size change must not reuse the old PNG
    (base / thumb).write_bytes(b"\x89PNG\r\n\x1a\ntruncated")
    assert need(_vis("s1")) is True  # poisoned thumbnail
    (base / thumb).unlink()
    assert need(_vis("s1")) is True  # missing file


def test_apply_links_sets_nulls_and_leaves_the_rest(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, excluded = wfx.build(cat, measure=False)
    ids = [w["id"] for w in directory["weapons"][:3]]
    before = copy.deepcopy(directory)
    results = {ids[0]: {"icon": "icons/a.png", "thumb": "icons/a@64.png", "sha256": "0123456789abcdef"}}
    assert icons.apply_links(directory, results, {ids[1]}) is True
    first = directory["weapons"][0]["visuals"]
    assert (first["icon"], first["thumb"], first["icon_input_sha"]) == ("icons/a.png", "icons/a@64.png", "0123456789abcdef")
    assert directory["weapons"][1]["visuals"] == before["weapons"][1]["visuals"]  # failed but already null: no change
    assert icons.apply_links(directory, results, set()) is False  # second application changes nothing
    assert icons.apply_links(directory, {}, {ids[0]}) is True  # a failure after success resets the links
    assert directory["weapons"][0]["visuals"] == before["weapons"][0]["visuals"]
    assert directory == before and validate_directory(directory, excluded) == []


def test_icon_links_survive_a_rebuild_when_the_files_exist(tmp_path):
    """Carry-forward (directory.write_directory): a rebuild must not wipe what ``icons`` linked, and stays INV-4."""
    cat = wfx.make_catalogs_dir(tmp_path)

    def rebuild():
        d, e, _ = build_directory_report(cat, overrides=empty_overrides(), pack_settings=wfx.pack_settings())
        write_directory(cat, d, e)
        return d

    d = rebuild()
    dpath = cat / "weapons" / DIRECTORY_NAME
    first_bytes = dpath.read_bytes()
    assert rebuild() and dpath.read_bytes() == first_bytes  # INV-4 with an existing directory in place
    rid = d["weapons"][0]["id"]
    pack, aid = rid.split("/", 1)
    icon, thumb = f"icons/{pack}/{aid}.png", f"icons/{pack}/{aid}@64.png"
    stored = read_json(dpath)
    stored["weapons"][0]["visuals"].update(icon=icon, thumb=thumb, icon_input_sha="0123456789abcdef")
    dpath.write_bytes(wfx_text(stored))
    for rel in (icon, thumb):
        (cat / "weapons" / rel).parent.mkdir(parents=True, exist_ok=True)
        (cat / "weapons" / rel).write_bytes(b"png")
    linked = dpath.read_bytes()

    again = rebuild()
    vis = wfx.records_by_id(again)[rid]["visuals"]
    assert (vis["icon"], vis["thumb"], vis["icon_input_sha"]) == (icon, thumb, "0123456789abcdef")
    assert dpath.read_bytes() == linked  # and the rebuild reproduces the linked file byte for byte
    assert all(w["visuals"]["icon"] is None for w in again["weapons"] if w["id"] != rid)

    (cat / "weapons" / thumb).unlink()  # the picture is gone: the link must go too (INV-8)
    assert wfx.records_by_id(rebuild())[rid]["visuals"] == {"icon": None, "thumb": None, "icon_input_sha": None,
                                                           "variants": []}


def wfx_text(doc: dict) -> bytes:
    return to_text(doc).encode("utf-8")


def test_bad_size_is_bad_input_even_before_the_renderer_check(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    code, out = run_cli(write_config(tmp_path, cat), "--size", "100")
    assert code == 2 and out["ok"] is False and "multiple of 64" in out["error"]


# --- AC18: runs everywhere -----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ac18_world(tmp_path_factory):
    return make_world(tmp_path_factory.mktemp("ac18"))


def _assert_nothing_written(world, before_tree, before_bytes, code, out):
    assert code == 5 and out["ok"] is False
    assert snapshot(world["cat"]) == before_tree  # no file or directory created, none touched
    assert world["dpath"].read_bytes() == before_bytes
    assert all(w["visuals"]["icon"] is None for w in read_json(world["dpath"])["weapons"])


@pytest.mark.parametrize("flags", [(), ("--variants",)], ids=["default", "variants"])
@pytest.mark.parametrize("how", ["no_root", "root_missing_on_disk", "no_playwright", "launch_fails"])
def test_ac18_unavailable_renderer_exits_5_and_writes_nothing(ac18_world, tmp_path, monkeypatch, how, flags):
    cat = tmp_path / "catalogs"  # a private copy per case: one case's leftovers must not hide another's write
    shutil.copytree(ac18_world["cat"], cat)
    w = {**ac18_world, "cat": cat, "dpath": cat / "weapons" / DIRECTORY_NAME}
    glb_root = {"no_root": None, "root_missing_on_disk": tmp_path / "nowhere"}.get(how, "fake")
    if glb_root == "fake":
        glb_root = fake_glb_root(tmp_path)
    cfg = write_config(tmp_path, w["cat"], threejs=w["root"], glb_root=glb_root)
    if how == "no_playwright":
        monkeypatch.setitem(sys.modules, "playwright", None)
        monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    elif how == "launch_fails":
        pytest.importorskip("playwright.sync_api")

        def boom(*a, **k):
            raise RuntimeError("no chromium here")

        monkeypatch.setattr(icons, "_launch_browser", boom)
    before_tree, before_bytes = snapshot(w["cat"]), w["dpath"].read_bytes()
    code, out = run_cli(cfg, *flags)
    _assert_nothing_written(w, before_tree, before_bytes, code, out)
    assert out["renderer"] == "unavailable"


def test_ac18_the_directory_has_records_that_would_have_been_rendered(ac18_world):
    measured = [r for r in ac18_world["dir"]["weapons"] if r["geometry"] is not None]
    assert {r["id"] for r in measured} == set(SIX)  # so exit 5 above is a real refusal, not an empty run


# --- AC17: needs the renderer --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ac17(tmp_path_factory):
    glb_root = renderer_root()
    tmp = tmp_path_factory.mktemp("ac17")
    w = make_world(tmp)
    cfg = write_config(tmp, w["cat"], threejs=w["root"], glb_root=glb_root)
    icons_dir = w["cat"] / "weapons" / "icons"
    base_bytes = w["dpath"].read_bytes()

    def pngs():
        return {p.relative_to(icons_dir).as_posix(): p.read_bytes() for p in sorted(icons_dir.rglob("*.png"))}

    run1 = run_cli(cfg)
    linked = w["dpath"].read_bytes()
    png1, tree1 = pngs(), snapshot(w["cat"])
    run2 = run_cli(cfg, "--rebuild")  # forces a second render of every icon
    png2 = pngs()
    tree2 = snapshot(w["cat"])
    run3 = run_cli(cfg)  # nothing changed since run2: must write nothing
    tree3 = snapshot(w["cat"])
    return {**w, "cfg": cfg, "base_bytes": base_bytes, "linked": linked, "run1": run1, "run2": run2, "run3": run3,
            "png1": png1, "png2": png2, "tree1": tree1, "tree2": tree2, "tree3": tree3, "icons_dir": icons_dir}


def _png_name(rid: str, suffix: str = "") -> str:
    pack, aid = rid.split("/", 1)
    return f"{pack}/{aid}{suffix}.png"


def test_ac17_first_run_renders_the_six_fixtures_and_nothing_else(ac17):
    code, out = ac17["run1"]
    assert code == 0 and out["ok"] is True, out
    assert out["rendered"] == sorted(SIX) and out["skipped"] == [] and out["failed"] == []
    assert out["no_geometry"] == len(ac17["dir"]["weapons"]) - 6  # records without a measured mesh get no icon
    assert sorted(ac17["png1"]) == sorted(_png_name(r, s) for r in SIX for s in ("", "@64"))


@pytest.mark.parametrize("rid", sorted(SIX))
@pytest.mark.parametrize("suffix,size,tol", [("", 256, 0.02), ("@64", 64, 0.03)])
def test_ac17_png_has_alpha_clear_corners_and_fills_88_percent(ac17, rid, suffix, size, tol):
    img = read_png(ac17["png1"][_png_name(rid, suffix)])
    assert img.shape == (size, size, 4)
    alpha = img[..., 3]
    assert [int(alpha[0, 0]), int(alpha[0, -1]), int(alpha[-1, 0]), int(alpha[-1, -1])] == [0, 0, 0, 0]
    # a real silhouette on a clear background (a 1 cm bow limb is under one pixel wide at 64 px: never fully opaque)
    assert alpha.max() >= (255 if size == 256 else 128) and (alpha == 0).sum() > size * size // 2
    ys, xs = np.nonzero(alpha > 0)
    fill = max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1) / size
    # +-0.02 at 256 px; at 64 px one antialiased pixel is 0.016, so the tolerance there is two pixels
    assert abs(fill - 0.88) <= tol, fill
    cx, cy = (xs.min() + xs.max() + 1) / 2 / size, (ys.min() + ys.max() + 1) / 2 / size
    assert abs(cx - 0.5) <= 0.02 and abs(cy - 0.5) <= 0.02, (cx, cy)


def _tip_vs_butt(alpha):
    """(left half, right half) of the silhouette split at the middle of its bounding box: (area, tallest column)."""
    ys, xs = np.nonzero(alpha > 0)
    mid = (xs.min() + xs.max() + 1) // 2
    left, right = alpha[:, xs.min():mid] > 0, alpha[:, mid:xs.max() + 1] > 0

    def col_height(m):
        return int(m.sum(axis=0).max())

    return (int(left.sum()), col_height(left)), (int(right.sum()), col_height(right))


def _span(alpha, side):
    """Vertical extent of the silhouette in the outer quarter on ``side`` of its bounding box."""
    ys, xs = np.nonzero(alpha > 0)
    q = (xs.max() - xs.min() + 1) // 4
    cols = alpha[:, xs.min():xs.min() + q] if side == "left" else alpha[:, xs.max() + 1 - q:xs.max() + 1]
    rows = np.nonzero((cols > 0).any(axis=1))[0]
    return int(rows.max() - rows.min() + 1)


def test_ac17_forward_points_right_for_each_shape(ac17):
    """Tip and butt are told apart by shape, with per-fixture literals, so a mirrored image cannot pass:
    the gun's thin barrel, the sword's and spear's wide guard / ferrule at the butt, the axe's head at the tip and the
    bow's belly (forward = the riser bulge, the limb tips are behind it) all have a known side. The shield is face-on and has none."""
    def alpha(rid):
        return read_png(ac17["png1"][_png_name(rid)])[..., 3]

    (la, _), (ra, _) = _tip_vs_butt(alpha("FAKE_Modern/SM_Wep_Rifle_Assault_01"))
    assert la > 1.5 * ra  # gun: the heavy receiver and stock are on the left, the thin barrel to the right
    (_, lh), (_, rh) = _tip_vs_butt(alpha("FAKE_Fantasy/SM_Wep_Claymore_06"))
    assert lh > 2 * rh  # sword: the 20 cm guard sits near the butt (left); the blade is 5 cm wide
    (_, lh), (_, rh) = _tip_vs_butt(alpha("FAKE_Fantasy/SM_Wep_Spear_01"))
    assert lh > rh  # spear: the 5 cm ferrule at the butt is wider than the 3 cm shaft and head
    (_, lh), (_, rh) = _tip_vs_butt(alpha("FAKE_Fantasy/SM_Wep_Axe_01"))
    assert rh > 2 * lh  # axe: the 24 cm head is on the tip side (right)
    b = alpha("FAKE_Fantasy/SM_Wep_Bow_03")
    assert _span(b, "left") > 2 * _span(b, "right")  # bow: the limb ends sit behind (left), the riser / belly bulges forward (right)


def test_ac17_links_are_written_relative_and_the_rest_of_directory_json_is_untouched(ac17):
    after = read_json(ac17["dpath"])
    assert validate_directory(after, ac17["excl"]) == []
    for rec in after["weapons"]:
        vis = rec["visuals"]
        if rec["id"] in SIX:
            pack, aid = rec["id"].split("/", 1)
            assert vis["icon"] == f"icons/{pack}/{aid}.png" and vis["thumb"] == f"icons/{pack}/{aid}@64.png"
            assert "\\" not in vis["icon"] and len(vis["icon_input_sha"]) == 16
            assert (ac17["cat"] / "weapons" / vis["icon"]).is_file()
        else:
            assert vis["icon"] is None and vis["thumb"] is None and vis["icon_input_sha"] is None
    restored = copy.deepcopy(after)
    for rec in restored["weapons"]:
        rec["visuals"].update(icon=None, thumb=None, icon_input_sha=None)
    assert wfx_text(restored) == ac17["base_bytes"]  # nothing but the three link fields changed
    assert ac17["linked"] == wfx_text(after)  # and the file is the canonical writer's output


def test_ac17_two_consecutive_runs_give_identical_png_bytes(ac17):
    code, out = ac17["run2"]
    assert code == 0 and out["rendered"] == sorted(SIX), out  # --rebuild really rendered again
    assert ac17["png1"] == ac17["png2"]


def test_ac17_a_second_run_with_unchanged_inputs_writes_zero_files(ac17):
    code, out = ac17["run3"]
    assert code == 0 and out["rendered"] == [] and out["skipped"] == sorted(SIX) and out["failed"] == []
    assert out["directory_written"] is False
    assert ac17["tree3"] == ac17["tree2"]  # every path, byte and mtime identical: nothing created, nothing rewritten


def test_ac17_variants_on_records_without_colourways_renders_nothing_extra(ac17):
    code, out = run_cli(ac17["cfg"], "--variants")  # the six fixtures have no Alts materials: no variants to draw
    assert code == 0 and out["rendered"] == [] and out["variants"] == {"rendered": [], "skipped": [], "failed": [], "visually_identical": 0}
    assert "not built yet" not in json.dumps(out)
    assert snapshot(ac17["cat"]) == ac17["tree3"]


def test_ac17_a_rebuild_after_icons_keeps_the_links(ac17):
    before = ac17["dpath"].read_bytes()
    d, e, _ = build_directory_report(ac17["cat"], overrides=empty_overrides(), pack_settings=wfx.pack_settings(),
                                     threejs_v2_dir=ac17["root"], geometry_cache={})
    write_directory(ac17["cat"], d, e)
    assert ac17["dpath"].read_bytes() == before
    assert all(wfx.records_by_id(d)[r]["visuals"]["icon"] for r in SIX)


# --- batch behaviour: failure, poisoned cache, stale sha, filters -----------------------------------------------------


def test_a_failed_asset_stays_null_is_listed_and_leaves_no_stale_picture(tmp_path):
    glb_root = renderer_root()
    w = make_world(tmp_path)
    cfg = write_config(tmp_path, w["cat"], threejs=w["root"], glb_root=glb_root)
    sword, gun = "FAKE_Fantasy/SM_Wep_Claymore_06", "FAKE_Modern/SM_Wep_Rifle_Assault_01"
    code, out = run_cli(cfg, "--ids", f"{sword},{gun}")
    assert code == 0 and out["rendered"] == sorted([sword, gun]), out
    sword_icon = w["cat"] / "weapons" / "icons" / _png_name(sword).split("/", 1)[0] / (sword.split("/", 1)[1] + ".png")
    assert sword_icon.is_file()
    gun_before = (w["cat"] / "weapons" / "icons" / _png_name(gun)).read_bytes()

    # the sword's GLB turns into garbage after the directory was built: the icon cannot be rendered any more
    glb = w["root"] / wfx.records_by_id(w["dir"])[sword]["files"]["glb"]
    glb.write_bytes(b"this is not a glb")
    code, out = run_cli(cfg, "--ids", f"{sword},{gun}")
    assert code == 0 and [f["id"] for f in out["failed"]] == [sword] and out["skipped"] == [gun], out
    by_id = wfx.records_by_id(read_json(w["dpath"]))
    assert by_id[sword]["visuals"] == {"icon": None, "thumb": None, "icon_input_sha": None, "variants": []}
    assert not sword_icon.exists()  # INV-8: the stale picture is not left lying around
    assert by_id[gun]["visuals"]["icon"] and (w["cat"] / "weapons" / "icons" / _png_name(gun)).read_bytes() == gun_before


def test_poisoned_and_stale_icons_are_rendered_again_and_filters_pick_records(tmp_path):
    glb_root = renderer_root()
    w = make_world(tmp_path)
    cfg = write_config(tmp_path, w["cat"], threejs=w["root"], glb_root=glb_root)
    axe, shield = "FAKE_Fantasy/SM_Wep_Axe_01", "FAKE_Fantasy/SM_Wep_Shield_01"
    code, out = run_cli(cfg, "--ids", f"{axe},{shield}")
    assert out["rendered"] == sorted([axe, shield])
    icon_dir = w["cat"] / "weapons" / "icons"
    good = (icon_dir / _png_name(axe)).read_bytes()

    (icon_dir / _png_name(axe)).write_bytes(good[:40])  # poisoned: truncated PNG
    (icon_dir / _png_name(shield, "@64")).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
    code, out = run_cli(cfg, "--ids", f"{axe},{shield}")
    assert out["rendered"] == sorted([axe, shield]) and (icon_dir / _png_name(axe)).read_bytes() == good

    d = read_json(w["dpath"])
    for rec in d["weapons"]:
        if rec["id"] == axe:
            rec["visuals"]["icon_input_sha"] = "0" * 16  # a sha that no longer matches the inputs
    w["dpath"].write_bytes(wfx_text(d))
    code, out = run_cli(cfg, "--ids", f"{axe},{shield}")
    assert out["rendered"] == [axe] and out["skipped"] == [shield]

    code, out = run_cli(cfg, "--pack", "FAKE_Modern")  # --pack filters; only the rifle of that pack has a mesh
    assert out["rendered"] == ["FAKE_Modern/SM_Wep_Rifle_Assault_01"] and out["skipped"] == []
    code, out = run_cli(cfg, "--ids", "FAKE_Modern/Nope_01")
    assert code == 2 and "unknown id" in out["error"]
    code, out = run_cli(cfg, "--pack", "NOPE")
    assert code == 2 and "unknown pack" in out["error"]


# --- W5: icons --variants (spec 3.7; AC19 icon links) -----------------------------------------------------------------
# The atlas_alt fixture: three sibling textures (A red, B green, C blue), one atlas whose B texture is a .tga, a lone
# letter, and a pack with a dedicated material. The GLBs carry a red base-colour texture, so a variant's colour proves
# that the texture was really swapped. Colours are checked by dominant channel, never by an exact pixel.

_spec = importlib.util.spec_from_file_location("atlas_alt_helpers", _FIX / "atlas_alt" / "helpers.py")
AA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AA)

SWORD_A = "FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01"
AXE_A = "FAKE_AtlasAlt/SM_Wep_Axe_Atlas_01"
MACE_A = "FAKE_AtlasAlt/SM_Wep_Mace_Atlas_01"
RED, GREEN, BLUE = 0, 1, 2


def make_atlas_world(tmp: Path, *, extracted: Path | None = None) -> dict:
    """Atlas catalogs + a threejs_v2 root with a textured GLB per asset + a built, written directory with variants."""
    cat = AA.make_catalogs(tmp)
    root = tmp / "threejs"
    for doc_path in sorted(cat.glob("*.json")):
        for asset in json.loads(doc_path.read_text(encoding="utf-8"))["assets"]:
            AA.write_textured_glb(root / asset["files"]["glb"], AA.COLOURS["A"])
    tree = extracted or AA.EXTRACTED
    directory, excluded, _ = build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, threejs_v2_dir=root, geometry_cache={},
        extracted_root=tree)
    write_directory(cat, directory, excluded)
    return {"cat": cat, "root": root, "dir": directory, "excl": excluded, "extracted": tree,
            "dpath": cat / "weapons" / DIRECTORY_NAME}


def atlas_config(tmp: Path, w: dict, glb_root: Path) -> Path:
    cfg = write_config(tmp, w["cat"], threejs=w["root"], glb_root=glb_root)
    text = cfg.read_text(encoding="utf-8").replace(f'{tmp.as_posix()}/extracted', w["extracted"].as_posix())
    cfg.write_text(text, encoding="utf-8")
    return cfg


def variant_png(w: dict, rid: str, letter: str, suffix: str = "") -> Path:
    pack, aid = rid.split("/", 1)
    return w["cat"] / "weapons" / "icons" / pack / f"{aid}@{letter}{suffix}.png"


def dominant(png: Path) -> int:
    """Index (0 R, 1 G, 2 B) of the channel with the largest mean over the opaque pixels."""
    img = read_png(png.read_bytes())
    opaque = img[img[..., 3] > 200][:, :3].astype(float)
    assert len(opaque) > 50, "no opaque body in the picture"
    return int(opaque.mean(axis=0).argmax())


def plan(w: dict, rid: str, *, extracted: Path | None = None, rebuild: bool = False, size: int = 256):
    """The browser-free half of icons --variants for one record: (todo, links, skipped, failed)."""
    rec = wfx.records_by_id(read_json(w["dpath"]))[rid]
    glb = w["root"] / rec["files"]["glb"]
    todo, links, skipped, failed = [], {}, [], []
    icons._plan_variants(rec, glb, "d" * 16, w["cat"] / "weapons" / "icons", extracted or w["extracted"], size,
                         rebuild, {}, {}, todo, links, skipped, failed)
    return todo, links, skipped, failed


def test_variant_input_sha_covers_the_default_inputs_the_texture_bytes_and_the_letter():
    base = icons.variant_input_sha("a" * 16, "t" * 64, "B")
    assert len(base) == 16 and all(c in "0123456789abcdef" for c in base)
    assert icons.variant_input_sha("a" * 16, "t" * 64, "B") == base
    assert len({base, icons.variant_input_sha("b" * 16, "t" * 64, "B"),
                icons.variant_input_sha("a" * 16, "u" * 64, "B"),
                icons.variant_input_sha("a" * 16, "t" * 64, "C")}) == 4


def test_apply_variant_links_links_resets_and_leaves_the_rest(tmp_path):
    w = make_atlas_world(tmp_path)
    d = copy.deepcopy(w["dir"])
    by = wfx.records_by_id(d)
    before = copy.deepcopy(d)
    links = {SWORD_A: {"B": {"icon": "icons/x/B.png", "thumb": "icons/x/B@64.png", "sha256": "0123456789abcdef"}}}
    assert icons.apply_variant_links(d, links, {}) is True
    b = next(v for v in by[SWORD_A]["visuals"]["variants"] if v["variant_id"] == "B")
    assert (b["icon"], b["icon_input_sha"]) == ("icons/x/B.png", "0123456789abcdef")
    a = next(v for v in by[SWORD_A]["visuals"]["variants"] if v["variant_id"] == "A")
    assert a == next(v for v in wfx.records_by_id(before)[SWORD_A]["visuals"]["variants"] if v["variant_id"] == "A")
    assert icons.apply_variant_links(d, links, {}) is False  # applying twice changes nothing
    assert validate_directory(d, w["excl"]) == []
    assert icons.apply_variant_links(d, {}, {SWORD_A: {"B"}}) is True  # a failure after success goes back to null
    assert d == before


def test_a_fresh_plan_lists_every_colourway_and_reports_a_tga_as_a_failure_with_its_reason(tmp_path):
    w = make_atlas_world(tmp_path)
    todo, links, skipped, failed = plan(w, SWORD_A)
    assert [t[2]["variant_id"] for t in todo] == ["A", "B", "C"] and links == {} and skipped == [] and failed == []
    assert [Path(t[3]).name for t in todo] == ["FakeAtlas_01_A.png", "FakeAtlas_01_B.png", "FakeAtlas_01_C_Diffuse.png"]
    assert len({t[4] for t in todo}) == 3  # one hash per colourway
    assert [(t[5], t[6]) for t in todo][1] == ("icons/FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01@B.png",
                                                 "icons/FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01@B@64.png")
    todo, _links, _skipped, failed = plan(w, MACE_A)
    assert [t[2]["variant_id"] for t in todo] == ["A"]
    assert len(failed) == 1 and (failed[0]["id"], failed[0]["variant"]) == (MACE_A, "B")
    assert "unsupported texture format .tga" in failed[0]["error"]


def test_a_missing_pack_tree_fails_each_variant_and_removes_the_stale_pictures(tmp_path):
    w = make_atlas_world(tmp_path)
    for suffix in ("", "@64"):
        stale = variant_png(w, SWORD_A, "B", suffix)
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"old picture")
    todo, _links, _skipped, failed = plan(w, SWORD_A, extracted=tmp_path / "nowhere")
    assert todo == [] and [f["variant"] for f in failed] == ["A", "B", "C"]
    assert all("no extracted tree" in f["error"] for f in failed)
    assert not variant_png(w, SWORD_A, "B").exists() and not variant_png(w, SWORD_A, "B", "@64").exists()


def _store_valid(w: dict, rid: str, letter: str, sha: str, size: int = 256):
    """Pretend ``letter`` was rendered with input hash ``sha``: both PNGs on disk and the link in directory.json."""
    for suffix, n in (("", size), ("@64", 64)):
        path = variant_png(w, rid, letter, suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(icons.encode_png(np.zeros((n, n, 4), np.uint8)))
    d = read_json(w["dpath"])
    for rec in d["weapons"]:
        for var in rec["visuals"]["variants"] if rec["id"] == rid else []:
            if var["variant_id"] == letter:
                var["icon"] = f"icons/{rid.split('/', 1)[0]}/{rid.split('/', 1)[1]}@{letter}.png"
                var["icon_input_sha"] = sha
    w["dpath"].write_bytes(wfx_text(d))


def test_a_stored_valid_variant_is_skipped_until_the_texture_bytes_or_the_flags_change(tmp_path):
    ext = tmp_path / "ext"
    shutil.copytree(AA.EXTRACTED, ext)
    w = make_atlas_world(tmp_path, extracted=ext)
    todo, *_ = plan(w, SWORD_A)
    sha_b = next(t[4] for t in todo if t[2]["variant_id"] == "B")
    _store_valid(w, SWORD_A, "B", sha_b)
    todo, links, skipped, failed = plan(w, SWORD_A)
    assert [t[2]["variant_id"] for t in todo] == ["A", "C"] and skipped == [f"{SWORD_A}@B"] and failed == []
    assert links == {SWORD_A: {"B": {"icon": "icons/FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01@B.png",
                                     "thumb": "icons/FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01@B@64.png", "sha256": sha_b}}}
    assert "B" in [t[2]["variant_id"] for t in plan(w, SWORD_A, rebuild=True)[0]]  # --rebuild renders it again
    assert "B" in [t[2]["variant_id"] for t in plan(w, SWORD_A, size=128)[0]]  # a --size change too
    tex = ext / "FAKE_AtlasAlt/Assets/Synty/FakeAtlas/Textures/Alts/FakeAtlas_01_B.png"
    tex.write_bytes(tex.read_bytes() + b"\0")  # the sibling texture is repainted
    assert "B" in [t[2]["variant_id"] for t in plan(w, SWORD_A)[0]]


def test_render_icons_variants_without_an_extracted_root_is_bad_input(tmp_path):
    pytest.importorskip("playwright.sync_api")
    w = make_atlas_world(tmp_path)
    fake = fake_glb_root(tmp_path)
    with pytest.raises(icons.InputError, match="extracted_root"):
        icons.render_icons([], w["cat"] / "weapons" / "icons", variants=True, threejs_v2_dir=w["root"],
                           synty_glb_root=fake)


def test_ac18_variants_flag_alone_does_not_hide_the_unavailable_renderer(tmp_path):
    w = make_atlas_world(tmp_path)
    cfg = write_config(tmp_path, w["cat"], threejs=w["root"], glb_root=tmp_path / "nowhere")
    before = snapshot(w["cat"])
    code, out = run_cli(cfg, "--variants")
    assert code == 5 and out["renderer"] == "unavailable" and snapshot(w["cat"]) == before


@pytest.fixture(scope="module")
def atlas_run(tmp_path_factory):
    glb_root = renderer_root()
    tmp = tmp_path_factory.mktemp("atlas")
    ext = tmp / "ext"
    shutil.copytree(AA.EXTRACTED, ext)
    w = make_atlas_world(tmp, extracted=ext)
    cfg = atlas_config(tmp, w, glb_root)
    run1 = run_cli(cfg, "--variants")
    after1 = w["dpath"].read_bytes()
    tree1 = snapshot(w["cat"])
    run2 = run_cli(cfg, "--variants")
    tree2 = snapshot(w["cat"])
    return {**w, "cfg": cfg, "tmp": tmp, "run1": run1, "run2": run2, "after1": after1, "tree1": tree1, "tree2": tree2}


def test_variants_first_run_renders_every_loadable_colourway_and_lists_the_tga(atlas_run):
    code, out = atlas_run["run1"]
    assert code == 0 and out["ok"] is True, out
    assert out["variants"]["rendered"] == sorted(
        [f"{AXE_A}@{x}" for x in "ABC"] + [f"{SWORD_A}@{x}" for x in "ABC"] + [f"{MACE_A}@A"]
        + [f"FAKE_AtlasAlt/SM_Wep_Knife_Atlas_01@{x}" for x in "ABC"]), out
    assert [(f["id"], f["variant"]) for f in out["variants"]["failed"]] == [(MACE_A, "B")]
    assert "unsupported texture format .tga" in out["variants"]["failed"][0]["error"]
    assert out["variants"]["skipped"] == []


def test_each_colourway_picture_shows_its_own_texture(atlas_run):
    for letter, channel in (("A", RED), ("B", GREEN), ("C", BLUE)):
        assert dominant(variant_png(atlas_run, SWORD_A, letter)) == channel, letter
    big = {x: variant_png(atlas_run, SWORD_A, x).read_bytes() for x in "ABC"}
    assert len(set(big.values())) == 3  # three different pictures
    for letter in "ABC":
        img = read_png(variant_png(atlas_run, SWORD_A, letter).read_bytes())
        thumb = read_png(variant_png(atlas_run, SWORD_A, letter, "@64").read_bytes())
        assert img.shape == (256, 256, 4) and thumb.shape == (64, 64, 4)
        assert [int(img[0, 0, 3]), int(img[-1, -1, 3])] == [0, 0]  # transparent background, like the default icon


def test_a_variant_is_the_same_framing_as_the_default_only_recoloured(atlas_run):
    default = read_png((atlas_run["cat"] / "weapons" / "icons" / "FAKE_AtlasAlt"
                        / "SM_Wep_Sword_Atlas_01.png").read_bytes())
    for letter in "BC":
        other = read_png(variant_png(atlas_run, SWORD_A, letter).read_bytes())
        assert (default[..., 3] > 0).tolist() == (other[..., 3] > 0).tolist(), letter  # same silhouette
    assert dominant(atlas_run["cat"] / "weapons" / "icons" / "FAKE_AtlasAlt" / "SM_Wep_Sword_Atlas_01.png") == RED


def test_the_links_are_written_into_the_directory_and_stay_valid(atlas_run):
    d = read_json(atlas_run["dpath"])
    assert validate_directory(d, atlas_run["excl"]) == []
    sword = wfx.records_by_id(d)[SWORD_A]["visuals"]["variants"]
    assert [v["icon"] for v in sword] == [f"icons/FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01@{x}.png" for x in "ABC"]
    assert all(len(v["icon_input_sha"]) == 16 for v in sword) and len({v["icon_input_sha"] for v in sword}) == 3
    mace = wfx.records_by_id(d)[MACE_A]["visuals"]["variants"]
    assert mace[0]["icon"] and mace[1]["icon"] is None and "icon_input_sha" not in mace[1]  # the .tga one stays null
    assert not variant_png(atlas_run, MACE_A, "B").exists()


def test_a_second_variants_run_changes_nothing(atlas_run):
    code, out = atlas_run["run2"]
    assert code == 0 and out["rendered"] == [] and out["directory_written"] is False
    assert out["variants"]["rendered"] == [] and len(out["variants"]["skipped"]) == 10  # 3 + 3 + 3 + 1
    assert [(f["id"], f["variant"]) for f in out["variants"]["failed"]] == [(MACE_A, "B")]
    assert atlas_run["tree2"] == atlas_run["tree1"]  # every path, byte and mtime identical


def _rebuild_atlas_directory(atlas_run) -> None:
    d, e, _ = build_directory_report(atlas_run["cat"], overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS,
                                     threejs_v2_dir=atlas_run["root"], geometry_cache={},
                                     extracted_root=atlas_run["extracted"])
    write_directory(atlas_run["cat"], d, e)


def _without_w6_keys(doc: dict) -> dict:
    """The directory minus the two optional keys W6 adds to ``visuals`` (``icon_mode``) and its variants
    (``icon_mode``, ``visually_identical``): the rebuild carry-forward lives in directory.py, which W6 does not own."""
    doc = copy.deepcopy(doc)
    for rec in doc["weapons"]:
        rec["visuals"].pop("icon_mode", None)
        for var in rec["visuals"]["variants"]:
            var.pop("icon_mode", None)
            var.pop("visually_identical", None)
    return doc


def test_a_rebuild_keeps_the_variant_links_while_the_pictures_exist(atlas_run):
    before = read_json(atlas_run["dpath"])
    _rebuild_atlas_directory(atlas_run)
    assert _without_w6_keys(read_json(atlas_run["dpath"])) == _without_w6_keys(before)
    atlas_run["dpath"].write_bytes(wfx_text(before))  # leave the module fixture as the icons run wrote it


def test_a_rebuild_keeps_icon_mode_and_visually_identical(atlas_run):
    before = atlas_run["dpath"].read_bytes()
    try:
        _rebuild_atlas_directory(atlas_run)
        assert atlas_run["dpath"].read_bytes() == before
    finally:
        atlas_run["dpath"].write_bytes(before)


def test_a_repainted_texture_renders_only_that_colourway_again(atlas_run):
    tex = atlas_run["extracted"] / "FAKE_AtlasAlt/Assets/Synty/FakeAtlas/Textures/Alts/FakeAtlas_01_C_Diffuse.png"
    original = tex.read_bytes()
    try:
        tex.write_bytes(AA._png((200, 200, 40)))  # C becomes yellow: red + green
        code, out = run_cli(atlas_run["cfg"], "--variants")
        assert code == 0 and out["variants"]["rendered"] == sorted(
            [f"{SWORD_A}@C", "FAKE_AtlasAlt/SM_Wep_Knife_Atlas_01@C", f"{AXE_A}@C"]), out
        assert dominant(variant_png(atlas_run, SWORD_A, "C")) != BLUE
    finally:
        tex.write_bytes(original)
