"""Weapon directory W6: blank-render BLEND retry, ``visually_identical`` colourways, the ``--gpu`` flag.

Pure logic first, with a fake renderer standing in for ``icons.Renderer`` (no browser needed); one real-renderer test
proves the harness half of the retry on a synthetic glTF MASK material, and skips with its reason when Chromium or the
synty-glb checkout is not available. Every bound is a literal worked out from the fixtures, not a constant under test.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("wfx", _FIX / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)
_spec = importlib.util.spec_from_file_location("atlas_alt_helpers", _FIX / "atlas_alt" / "helpers.py")
AA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AA)

from synty_inventory.cli import build_parser, main  # noqa: E402
from synty_inventory.weapons import guards, icons  # noqa: E402
from synty_inventory.weapons.directory import (  # noqa: E402
    DIRECTORY_NAME,
    build_directory_report,
    read_json,
    write_directory,
)
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

SWORD = "FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01"  # colourways A, B, C
AXE = "FAKE_AtlasAlt/SM_Wep_Axe_Atlas_01"
RED, GREEN, NEAR_RED = (200, 40, 40), (40, 200, 40), (205, 45, 35)  # NEAR_RED is 10 off RED on its largest channel
ENV_KEYS = ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
            "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT")


# --- a fake renderer and a world of colourway records ---------------------------------------------------------------


def block(size: int, rgb) -> np.ndarray:
    """An opaque ``rgb`` square in the middle of a transparent image (premultiplied == straight at alpha 255)."""
    px = np.zeros((size, size, 4), dtype=np.uint8)
    q = size // 4
    px[q:size - q, q:size - q] = (*rgb, 255)
    return px


class FakeRenderer:
    """Stands in for ``icons.Renderer``. ``draw(glb_name, texture_name, force_blend)`` returns an ``(r, g, b)`` colour
    for a visible picture or None for a blank one; every call is logged as ``(glb, texture, force_blend)``."""

    def __init__(self, draw=None):
        self.draw = draw or (lambda glb, tex, blend: RED)
        self.calls: list[tuple] = []

    def __call__(self, root, *, gpu=False, **_kw):  # the constructor the batch calls
        self.gpu = gpu
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def render(self, glb, nodes, scale, item_basis, shield, size, texture=None, force_blend=False):
        glb_name, tex_name = Path(glb).name, (Path(texture).name if texture is not None else None)
        self.calls.append((glb_name, tex_name, bool(force_blend)))
        rgb = self.draw(glb_name, tex_name, bool(force_blend))
        return np.zeros((size, size, 4), np.uint8) if rgb is None else block(size, rgb)


def by_colourway(glb, tex, blend):
    """Texture A repeats the default colour, B is green, C differs from the default by 10 of 255."""
    if tex is None or tex.endswith("_A.png"):
        return RED
    return GREEN if tex.endswith("_B.png") else NEAR_RED


@pytest.fixture
def world(tmp_path, monkeypatch):
    """The atlas-alt fixture catalogs: textured GLBs, a built directory with variants, the renderer check faked away."""
    cat = AA.make_catalogs(tmp_path)
    root = tmp_path / "threejs"
    for doc_path in sorted(cat.glob("*.json")):
        for asset in json.loads(doc_path.read_text(encoding="utf-8"))["assets"]:
            AA.write_textured_glb(root / asset["files"]["glb"], AA.COLOURS["A"])
    directory, excluded, _ = build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, threejs_v2_dir=root, geometry_cache={},
        extracted_root=AA.EXTRACTED)
    write_directory(cat, directory, excluded)
    monkeypatch.setattr(icons, "check_renderer", lambda glb_root: Path("."))
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    return SimpleNamespace(tmp=tmp_path, cat=cat, root=root, dir=directory, excl=excluded,
                           dpath=cat / "weapons" / DIRECTORY_NAME, icons=cat / "weapons" / "icons")


def render(world, monkeypatch, fake, *, ids=(SWORD, AXE), variants=True, rebuild=False, directory=None):
    """``render_icons`` over the chosen records with ``fake`` as the renderer; returns ``(results, report)``."""
    monkeypatch.setattr(icons, "Renderer", fake)
    recs = [w for w in (directory or world.dir)["weapons"] if w["id"] in ids]
    report: dict = {}
    results = icons.render_icons(recs, world.icons, variants=variants, threejs_v2_dir=world.root,
                                 synty_glb_root=Path("."), rebuild=rebuild, report=report, extracted_root=AA.EXTRACTED)
    return results, report


def icon_path(world, rid: str, letter: str | None = None, suffix: str = "") -> Path:
    pack, aid = rid.split("/", 1)
    tag = f"@{letter}" if letter else ""
    return world.icons / pack / f"{aid}{tag}{suffix}.png"


def blank_for(*glb_stems, always=()):
    """A draw function: pictures of the named GLBs are blank unless ``force_blend`` (or never visible for ``always``)."""
    def draw(glb, tex, blend):
        if any(stem in glb for stem in always):
            return None
        if any(stem in glb for stem in glb_stems) and not blend:
            return None
        return by_colourway(glb, tex, blend)
    return draw


# --- item 1: blank_render and the BLEND retry -------------------------------------------------------------------------


def test_a_blank_default_render_is_retried_once_with_blend_and_recorded(world, monkeypatch):
    fake = FakeRenderer(blank_for("Sword"))
    results, report = render(world, monkeypatch, fake, variants=False)
    sword_calls = [c for c in fake.calls if "Sword" in c[0]]
    assert [c[2] for c in sword_calls] == [False, True]  # drawn normally first, then once as BLEND
    assert [c[2] for c in fake.calls if "Axe" in c[0]] == [False]  # a picture that shows something is never retried
    assert results[SWORD]["icon_mode"] == "blend_retry" and "icon_mode" not in results[AXE]
    assert report["blend_retry"] == [SWORD] and report["failed"] == [] and report["rendered"] == sorted([SWORD, AXE])
    img = icons.decode_png(icon_path(world, SWORD).read_bytes())
    assert img.shape == (256, 256, 4) and (img[..., 3] > 0).any()  # the retry's picture is what was written
    assert icon_path(world, SWORD, suffix="@64").is_file()


def test_a_blank_render_after_the_retry_fails_the_asset_and_removes_stale_files(world, monkeypatch):
    for suffix in ("", "@64"):
        stale = icon_path(world, SWORD, suffix=suffix)
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"old picture")
    fake = FakeRenderer(blank_for(always=("Sword",)))
    results, report = render(world, monkeypatch, fake, variants=False)
    assert report["failed"] == [{"id": SWORD, "error": "blank_render"}]
    assert SWORD not in results and report["blend_retry"] == [] and report["rendered"] == [AXE]
    assert not icon_path(world, SWORD).exists() and not icon_path(world, SWORD, suffix="@64").exists()  # INV-8
    assert [c[2] for c in fake.calls if "Sword" in c[0]] == [False, True]  # retried once, not more
    # and the directory goes back to null for it, mode included
    d = copy.deepcopy(world.dir)
    vis = wfx.records_by_id(d)[SWORD]["visuals"]
    vis.update(icon="icons/x.png", thumb="icons/x@64.png", icon_input_sha="0" * 16, icon_mode="blend_retry")
    assert icons.apply_links(d, results, {SWORD}) is True
    assert wfx.records_by_id(d)[SWORD]["visuals"] == {"icon": None, "thumb": None, "icon_input_sha": None, "variants": vis["variants"]}


def test_a_normal_render_draws_once_without_the_blend_option(world, monkeypatch):
    fake = FakeRenderer()
    results, report = render(world, monkeypatch, fake, variants=False)
    assert len(fake.calls) == 2 and all(c[2] is False for c in fake.calls)
    assert all("icon_mode" not in r for r in results.values()) and report["blend_retry"] == []


def test_the_blend_mode_is_stored_kept_when_skipped_and_cleared_by_a_clean_rerender(world, monkeypatch):
    d = copy.deepcopy(world.dir)
    results, report = render(world, monkeypatch, FakeRenderer(blank_for("Sword")), variants=False, directory=d)
    assert icons.apply_links(d, results, set()) is True
    vis = wfx.records_by_id(d)[SWORD]["visuals"]
    assert vis["icon_mode"] == "blend_retry" and "icon_mode" not in wfx.records_by_id(d)[AXE]["visuals"]
    assert validate_directory(d, world.excl) == []
    # unchanged inputs: nothing is drawn, and the stored mode stays (the link write-back must not drop it)
    fake = FakeRenderer()
    results, report = render(world, monkeypatch, fake, variants=False, directory=d)
    assert fake.calls == [] and report["skipped"] == sorted([SWORD, AXE]) and report["blend_retry"] == []
    assert results[SWORD]["icon_mode"] == "blend_retry"
    assert icons.apply_links(d, results, set()) is False
    assert wfx.records_by_id(d)[SWORD]["visuals"]["icon_mode"] == "blend_retry"
    # a re-render that no longer needs the retry clears the mode
    results, report = render(world, monkeypatch, FakeRenderer(), variants=False, directory=d, rebuild=True)
    assert "icon_mode" not in results[SWORD]
    assert icons.apply_links(d, results, set()) is True
    assert "icon_mode" not in wfx.records_by_id(d)[SWORD]["visuals"]


def test_colourway_icons_get_the_same_retry_and_blank_variants_fail(world, monkeypatch):
    def draw(glb, tex, blend):
        if tex is not None and tex.endswith("_B.png") and not blend:
            return None  # B only shows after the retry
        if tex is not None and "_C_" in tex:
            return None  # C never shows
        return by_colourway(glb, tex, blend)

    fake = FakeRenderer(draw)
    results, report = render(world, monkeypatch, fake, ids=(SWORD,))
    v = report["variants"]
    assert v["rendered"] == [f"{SWORD}@A", f"{SWORD}@B"]
    assert v["failed"] == [{"id": SWORD, "variant": "C", "error": "blank_render"}]
    assert report["blend_retry"] == [f"{SWORD}@B"]
    assert v["links"][SWORD]["B"]["icon_mode"] == "blend_retry" and "icon_mode" not in v["links"][SWORD]["A"]
    assert not icon_path(world, SWORD, "C").exists() and icon_path(world, SWORD, "B").is_file()
    d = copy.deepcopy(world.dir)
    assert icons.apply_variant_links(d, v["links"], {SWORD: {"C"}}) is True
    by_letter = {x["variant_id"]: x for x in wfx.records_by_id(d)[SWORD]["visuals"]["variants"]}
    assert by_letter["B"]["icon_mode"] == "blend_retry" and "icon_mode" not in by_letter["A"]
    assert by_letter["C"]["icon"] is None and "icon_mode" not in by_letter["C"]
    assert validate_directory(d, world.excl) == []
    assert icons.apply_variant_links(d, v["links"], {SWORD: {"C"}}) is False  # applying twice changes nothing
    # a skipped variant keeps its stored mode; one that is rendered again without the retry loses it
    results2, report2 = render(world, monkeypatch, FakeRenderer(), ids=(SWORD,), directory=d)
    assert report2["variants"]["links"][SWORD]["B"].get("icon_mode") == "blend_retry"
    assert f"{SWORD}@B" in report2["variants"]["skipped"]
    results3, report3 = render(world, monkeypatch, FakeRenderer(), ids=(SWORD,), directory=d, rebuild=True)
    assert "icon_mode" not in report3["variants"]["links"][SWORD]["B"]


def test_the_schema_accepts_icon_mode_only_as_blend_retry_and_visually_identical_only_as_a_boolean(world):
    d = copy.deepcopy(world.dir)
    rec = wfx.records_by_id(d)[SWORD]
    rec["visuals"]["icon_mode"] = "blend_retry"
    rec["visuals"]["variants"][0]["icon_mode"] = "blend_retry"
    rec["visuals"]["variants"][0]["visually_identical"] = True
    assert validate_directory(d, world.excl) == []
    rec["visuals"]["icon_mode"] = "sharp"
    assert validate_directory(d, world.excl) != []
    rec["visuals"]["icon_mode"] = "blend_retry"
    rec["visuals"]["variants"][0]["visually_identical"] = "yes"
    assert validate_directory(d, world.excl) != []
    rec["visuals"]["variants"][0]["visually_identical"] = True
    rec["visuals"]["unknown_key"] = 1  # visuals stays closed
    assert validate_directory(d, world.excl) != []


def test_icon_input_sha_and_harness_version_are_unchanged_by_the_retry_machinery():
    """Existing icons stay valid: default renders are byte-identical, so the cache key must not move."""
    assert icons.ICON_HARNESS_VERSION == 1
    basis, turned = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [[0, 0, 1], [1, 0, 0], [0, 1, 0]]
    assert icons.icon_input_sha("a" * 64, None, 1.0, basis) == "5c92357186eb2891"  # computed with the pre-W6 code
    assert icons.icon_input_sha("a" * 64, ["Bow_A", "Bow_B"], 0.01, turned) == "9d21700c6c44bb8f"
    assert icons.icon_input_sha("a" * 64, None, 1.0, basis) != icons.icon_input_sha("a" * 64, None, 1.0, turned)


class FakePage:
    """Records the payload of every page call; answers the two harness calls with a fixed box and a blank picture."""

    def __init__(self):
        self.prepare: list[dict] = []

    def evaluate(self, script, payload):
        if "iconPrepare" in script:
            self.prepare.append(payload)
            return {"min": [-1.0, -1.0, -2.0], "max": [1.0, 1.0, -1.0]}
        return {"pixels": __import__("base64").b64encode(bytes(payload["size"] * payload["size"] * 4)).decode()}


def test_the_prepare_payload_asks_for_blend_only_when_told_to():
    page = FakePage()
    renderer = icons.Renderer(Path("."))
    renderer._server, renderer._page = SimpleNamespace(glbs={}, textures={}), page
    basis = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    renderer.render(Path("a.glb"), None, 1.0, basis, False, 64)
    renderer.render(Path("a.glb"), None, 1.0, basis, False, 64, force_blend=True)
    assert [p["forceBlend"] for p in page.prepare] == [False, True]
    assert {k: v for k, v in page.prepare[0].items() if k != "forceBlend"} == {
        k: v for k, v in page.prepare[1].items() if k != "forceBlend"}  # nothing else about the render changes


# --- item 2: visually_identical ---------------------------------------------------------------------------------------


def png_of(rgba: np.ndarray, path: Path) -> Path:
    path.write_bytes(icons.encode_png(rgba))
    return path


def filtered_png(rgba: np.ndarray, filters: list[int]) -> bytes:
    """Encode ``rgba`` with the given PNG filter type per row (0 None, 1 Sub, 2 Up, 3 Average, 4 Paeth)."""
    h, w, _ = rgba.shape
    stride = w * 4
    rows = rgba.reshape(h, stride).astype(int)
    out = bytearray()
    for y in range(h):
        ft, prev = filters[y % len(filters)], (rows[y - 1] if y else np.zeros(stride, int))
        out.append(ft)
        for i in range(stride):
            a = int(rows[y][i - 4]) if i >= 4 else 0
            b = int(prev[i])
            c = int(prev[i - 4]) if i >= 4 else 0
            if ft == 0:
                pred = 0
            elif ft == 1:
                pred = a
            elif ft == 2:
                pred = b
            elif ft == 3:
                pred = (a + b) // 2
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            out.append((int(rows[y][i]) - pred) & 255)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b""))


def test_decode_png_inverts_encode_png_exactly():
    px = np.random.default_rng(3).integers(0, 256, size=(16, 24, 4), dtype=np.uint8)
    assert np.array_equal(icons.decode_png(icons.encode_png(px)), px)
    assert icons.decode_png(icons.encode_png(px)).dtype == np.uint8


@pytest.mark.parametrize("filters", [[0], [1], [2], [3], [4], [0, 1, 2, 3, 4], [4, 3, 2, 1, 0, 4]])
def test_decode_png_handles_all_five_filter_types(filters):
    px = np.random.default_rng(11).integers(0, 256, size=(13, 9, 4), dtype=np.uint8)
    assert np.array_equal(icons.decode_png(filtered_png(px, filters)), px)


def test_decode_png_rejects_what_it_cannot_read():
    good = icons.encode_png(np.zeros((4, 4, 4), np.uint8))
    with pytest.raises(ValueError):
        icons.decode_png(b"not a png at all")
    with pytest.raises(ValueError):
        icons.decode_png(good[:40])  # truncated before the data
    rgb = bytearray(good)
    rgb[25] = 2  # IHDR colour type: truecolour without alpha
    with pytest.raises(ValueError):
        icons.decode_png(bytes(rgb))
    interlaced = bytearray(good)
    interlaced[28] = 1
    with pytest.raises(ValueError):
        icons.decode_png(bytes(interlaced))


def covered_pair(tmp_path, mutate):
    """Two 16x16 icons: a 10x10 opaque red block (100 covered pixels); ``mutate`` edits the second one."""
    a = np.zeros((16, 16, 4), np.uint8)
    a[3:13, 3:13] = (200, 40, 40, 255)
    b = a.copy()
    mutate(b)
    return png_of(a, tmp_path / "a.png"), png_of(b, tmp_path / "b.png")


def test_icon_difference_counts_the_covered_pixels_that_differ_by_more_than_12(tmp_path):
    same = covered_pair(tmp_path, lambda b: None)
    assert icons.icon_difference(*same) == 0.0
    one = covered_pair(tmp_path, lambda b: b.__setitem__((5, 5, 1), 40 + 13))  # 13 > 12 on one channel of one pixel
    assert icons.icon_difference(*one) == pytest.approx(0.01)  # 1 of 100 covered
    edge = covered_pair(tmp_path, lambda b: b.__setitem__((5, 5, 1), 40 + 12))  # exactly 12 is not "more than 12"
    assert icons.icon_difference(*edge) == 0.0
    down = covered_pair(tmp_path, lambda b: b.__setitem__((5, 5, 0), 200 - 13))
    assert icons.icon_difference(*down) == pytest.approx(0.01)  # the sign of the difference does not matter
    tenth = covered_pair(tmp_path, lambda b: b[3:5, 3:8].__setitem__(slice(None), (0, 0, 255, 255)))
    assert icons.icon_difference(*tenth) == pytest.approx(0.10)  # 10 of 100


def test_icon_difference_covered_means_alpha_in_either_image_and_alpha_counts_as_a_channel(tmp_path):
    def add_pixel(b):  # a pixel only the second image covers: 101 covered, 1 differs
        b[0, 0] = (200, 40, 40, 255)

    assert icons.icon_difference(*covered_pair(tmp_path, add_pixel)) == pytest.approx(1 / 101)

    def fade(b):  # same colour, alpha 255 -> 200: only the alpha channel differs, by 55
        b[4, 4, 3] = 200

    assert icons.icon_difference(*covered_pair(tmp_path, fade)) == pytest.approx(0.01)
    empty = png_of(np.zeros((16, 16, 4), np.uint8), tmp_path / "empty.png")
    assert icons.icon_difference(empty, empty) == 0.0  # nothing covered: nothing differs
    with pytest.raises(ValueError):
        icons.icon_difference(empty, png_of(np.zeros((32, 32, 4), np.uint8), tmp_path / "big.png"))
    with pytest.raises(OSError):
        icons.icon_difference(empty, tmp_path / "missing.png")


def big_pair(tmp_path, n_changed: int, delta: int):
    """Two 64x64 icons with a 40x40 opaque block (1600 covered pixels); the second has its first ``n_changed`` pixels
    brightened by ``delta`` on every colour channel."""
    a = np.zeros((64, 64, 4), np.uint8)
    a[12:52, 12:52] = (100, 90, 80, 255)
    b = a.copy()
    for i in range(n_changed):
        b[12, 12 + i, :3] += delta
    return png_of(a, tmp_path / "a.png"), png_of(b, tmp_path / "b.png")


@pytest.mark.parametrize("n_changed,delta,identical", [
    (7, 100, True),    # 0.44 % of the pixels: under the plain 0.5 % bound, even though the pixels are strong
    (8, 30, True),     # 0.50 %, all faint (30 of 255): the faint tail counts as the same picture (live: Shield_01 B/C)
    (15, 30, True),    # 0.94 %, faint
    (17, 30, False),   # 1.06 %: more than 1 % of the picture is tinted
    (8, 100, False),   # 0.50 % with strong pixels: a small decal in a clear colour (live: the Staff_01 gem)
    (0, 0, True),
])
def test_looks_identical_accepts_a_faint_tail_but_not_a_strong_decal(tmp_path, n_changed, delta, identical):
    pair = big_pair(tmp_path, n_changed, delta)
    assert icons.looks_identical(*pair) is identical


def test_a_colourway_that_looks_like_the_default_is_flagged_and_the_others_are_not(world, monkeypatch):
    results, report = render(world, monkeypatch, FakeRenderer(by_colourway), ids=(SWORD,))
    links = report["variants"]["links"][SWORD]
    assert {k: v["visually_identical"] for k, v in links.items()} == {"A": True, "B": False, "C": True}
    assert report["variants"]["visually_identical"] == [f"{SWORD}@A", f"{SWORD}@C"]
    d = copy.deepcopy(world.dir)
    assert icons.apply_links(d, results, set()) is True
    assert icons.apply_variant_links(d, report["variants"]["links"], {}) is True
    flags = {v["variant_id"]: v.get("visually_identical") for v in wfx.records_by_id(d)[SWORD]["visuals"]["variants"]}
    assert flags == {"A": True, "B": False, "C": True}
    assert validate_directory(d, world.excl) == []


def test_the_flag_is_computed_from_the_files_so_skipped_variants_are_covered_and_runs_agree(world, monkeypatch):
    d = copy.deepcopy(world.dir)
    results, report = render(world, monkeypatch, FakeRenderer(by_colourway), ids=(SWORD,), directory=d)
    icons.apply_links(d, results, set())
    icons.apply_variant_links(d, report["variants"]["links"], {})
    fake = FakeRenderer(by_colourway)
    results2, report2 = render(world, monkeypatch, fake, ids=(SWORD,), directory=d)
    assert fake.calls == [] and len(report2["variants"]["skipped"]) == 3  # nothing drawn: all from the cache
    assert report2["variants"]["links"] == report["variants"]["links"]  # the same flags, from the PNGs on disk
    assert icons.apply_variant_links(d, report2["variants"]["links"], {}) is False
    # a repainted default picture flips the flags of the skipped colourways on the next run
    png_of(block(256, GREEN), icon_path(world, SWORD))
    _r, report3 = render(world, monkeypatch, FakeRenderer(by_colourway), ids=(SWORD,), directory=d)
    assert {k: v["visually_identical"] for k, v in report3["variants"]["links"][SWORD].items()} == {
        "A": False, "B": True, "C": False}


def test_no_flag_without_a_default_icon_or_a_comparable_pair(world, monkeypatch):
    fake = FakeRenderer(lambda glb, tex, blend: None if tex is None else by_colourway(glb, tex, blend))
    results, report = render(world, monkeypatch, fake, ids=(SWORD,))
    assert report["failed"] == [{"id": SWORD, "error": "blank_render"}]  # the default icon failed
    links = report["variants"]["links"][SWORD]
    assert sorted(links) == ["A", "B", "C"] and all("visually_identical" not in v for v in links.values())
    assert report["variants"]["visually_identical"] == []
    d = copy.deepcopy(world.dir)
    for var in wfx.records_by_id(d)[SWORD]["visuals"]["variants"]:
        var["visually_identical"] = True  # a stale flag from an earlier run
    icons.apply_variant_links(d, report["variants"]["links"], {})
    assert all("visually_identical" not in v for v in wfx.records_by_id(d)[SWORD]["visuals"]["variants"])
    # a differently sized default picture cannot be compared either: no key, and no crash
    results, report = render(world, monkeypatch, FakeRenderer(by_colourway), ids=(SWORD,))
    png_of(np.zeros((64, 64, 4), np.uint8), icon_path(world, SWORD))
    got = icons._flag_identical(world.icons.parent, results, {SWORD: {"A": {"icon": "icons/FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01@A.png"}}})
    assert got == []


# --- the CLI summary --------------------------------------------------------------------------------------------------


def run_cli(world, *argv):
    cfg = world.tmp / "config.yaml"
    cfg.write_text("\n".join([f'unity_root: "{world.tmp.as_posix()}/unity"', f'extracted_root: "{AA.EXTRACTED.as_posix()}"',
f'catalogs: "{world.cat.as_posix()}"',
                              f'threejs_v2: "{world.root.as_posix()}"', 'synty_glb_root: "."']) + "\n", encoding="utf-8")
    out = io.StringIO()
    with mock.patch.dict(os.environ):
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        with contextlib.redirect_stdout(out):
            code = main(["--config", str(cfg), "weapons", "icons", *argv])
    return code, json.loads(out.getvalue())


def test_the_cli_summary_counts_blend_retries_and_identical_colourways(world, monkeypatch):
    monkeypatch.setattr(icons, "Renderer", FakeRenderer(by_colourway_blank_sword))
    code, out = run_cli(world, "--variants")
    assert code == 0 and out["ok"] is True, out
    assert out["blend_retry"] == 1  # the sword's default icon
    # A and C of the sword, axe and knife, and the lone A of the mace
    assert out["variants"]["visually_identical"] == 7 and isinstance(out["variants"]["visually_identical"], int)
    d = read_json(world.dpath)
    assert validate_directory(d, world.excl) == []
    sword = wfx.records_by_id(d)[SWORD]["visuals"]
    assert sword["icon_mode"] == "blend_retry"
    assert [v["visually_identical"] for v in sword["variants"]] == [True, False, True]
    code, out = run_cli(world, "--variants")  # a second run draws nothing and keeps everything
    assert out["rendered"] == [] and out["blend_retry"] == 0 and out["directory_written"] is False
    assert read_json(world.dpath) == d


def test_a_default_icon_drawn_again_without_variants_refreshes_the_colourway_flags(world, monkeypatch):
    """Live finding (Mech Shotgun_01): the default icon was blank before W6, so colourway A was flagged different; the
    default was then redrawn through the BLEND retry with a plain ``icons --rebuild`` and A, now the same picture, kept
    the stale ``False``. The flag compares with the default icon, so every run refreshes it from the PNGs on disk; a
    blend_retry picture is compared like any other (there is no rule that excludes it)."""
    monkeypatch.setattr(icons, "Renderer", FakeRenderer(by_colourway_blank_sword))
    code, _out = run_cli(world, "--variants", "--ids", SWORD)
    assert code == 0
    sword = wfx.records_by_id(read_json(world.dpath))[SWORD]["visuals"]
    assert sword["icon_mode"] == "blend_retry"  # the default needed the retry, as the shotgun did
    assert [v["visually_identical"] for v in sword["variants"]] == [True, False, True]
    # the default is redrawn on its own as green: the colourways are not drawn again, so only the refresh can fix flags
    green_default = FakeRenderer(lambda glb, tex, blend: GREEN if tex is None else by_colourway(glb, tex, blend))
    monkeypatch.setattr(icons, "Renderer", green_default)
    code, out = run_cli(world, "--rebuild", "--ids", SWORD)
    assert code == 0 and out["rendered"] == [SWORD] and "variants" not in out
    sword = wfx.records_by_id(read_json(world.dpath))[SWORD]["visuals"]
    assert [v["visually_identical"] for v in sword["variants"]] == [False, True, False]
    assert validate_directory(read_json(world.dpath), world.excl) == []


def by_colourway_blank_sword(glb, tex, blend):
    """The sword's default picture needs the retry; every colourway icon shows at once."""
    if tex is None and "Sword" in glb and not blend:
        return None
    return by_colourway(glb, tex, blend)


# --- item 5: --gpu -------------------------------------------------------------------------------------------------------


def test_gpu_is_a_flag_of_the_icons_parser_and_defaults_to_false():
    parser = build_parser()
    assert parser.parse_args(["weapons", "icons"]).gpu is False
    assert parser.parse_args(["weapons", "icons", "--gpu"]).gpu is True


@pytest.mark.parametrize("flags,expected", [([], False), (["--gpu"], True)])
def test_the_gpu_flag_reaches_render_icons(tmp_path, monkeypatch, flags, expected):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, excluded = wfx.build(cat, measure=False)
    write_directory(cat, directory, excluded)
    seen: dict = {}

    def fake_render_icons(records, out_dir, **kw):
        seen.update(kw)
        kw["report"].update(rendered=[], skipped=[], failed=[], blend_retry=[])
        return {}

    monkeypatch.setattr(icons, "render_icons", fake_render_icons)
    monkeypatch.setattr(icons, "check_renderer", lambda root: Path("."))
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f'unity_root: "{tmp_path.as_posix()}/unity"\nextracted_root: "{tmp_path.as_posix()}/extracted"\n'
                   f'catalogs: "{cat.as_posix()}"\nsynty_glb_root: "."\n', encoding="utf-8")
    with mock.patch.dict(os.environ):
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        assert main(["--config", str(cfg), "weapons", "icons", *flags]) == 0
    assert seen["gpu"] is expected


# --- the real harness: a glTF MASK material under its cutoff --------------------------------------------------------------


def mask_glb(path: Path, *, mode="MASK", alpha=0.4745, cutoff=0.5) -> Path:
    """The textured box fixture with its material turned into ``mode`` and a base-colour alpha of ``alpha``."""
    data = AA.textured_glb_bytes(AA.COLOURS["A"])
    (jlen, jtype) = struct.unpack("<II", data[12:20])
    assert jtype == 0x4E4F534A
    doc = json.loads(data[20:20 + jlen])
    mat = doc["materials"][0]
    mat["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, alpha]
    mat["alphaMode"] = mode
    if mode == "MASK":
        mat["alphaCutoff"] = cutoff
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    rest = data[20 + jlen:]
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + rest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    return path


def real_glb_root() -> Path:
    env = os.environ.get("SYNTI_SYNTY_GLB_ROOT")
    candidates = ([Path(env)] if env else []) + [
        Path(__file__).resolve().parents[2] / "synty-glb",
        Path("D:/") / "_".join(("game", "assets", "library")) / "tools" / "synty-glb",
    ]
    root = next((c for c in candidates if (c / "node_modules" / "three" / "build" / "three.module.js").is_file()), None)
    if root is None:
        pytest.skip("synty-glb root with node_modules/three not found (set SYNTI_SYNTY_GLB_ROOT)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("the playwright package is not installed")
    try:
        with sync_playwright() as pw:
            icons._launch_browser(pw, False).close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium cannot be launched: {str(exc).splitlines()[0] if str(exc) else exc!r}")
    return root


def one_record(rid: str, glb_rel: str) -> dict:
    pack, aid = rid.split("/", 1)
    return {"id": rid, "pack": pack, "asset_id": aid, "kind": "melee", "archetype": "sword",
            "geometry": {"item_basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}, "files": {"glb": glb_rel},
            "visuals": {"icon": None, "thumb": None, "icon_input_sha": None, "variants": []}}


def test_a_mask_material_under_its_cutoff_is_drawn_after_the_blend_retry(tmp_path):
    glb_root = real_glb_root()
    root = tmp_path / "threejs"
    mask_glb(root / "P" / "mask.glb")  # alphaMode MASK, base-colour alpha 0.4745 under the 0.5 cutoff
    mask_glb(root / "P" / "opaque.glb", mode="OPAQUE")
    mask_glb(root / "P" / "solid.glb", alpha=1.0)  # MASK but over the cutoff: shows at once
    recs = [one_record("P/mask", "P/mask.glb"), one_record("P/opaque", "P/opaque.glb"),
            one_record("P/solid", "P/solid.glb")]
    out_dir = tmp_path / "weapons" / "icons"
    report: dict = {}
    results = icons.render_icons(recs, out_dir, threejs_v2_dir=root, synty_glb_root=glb_root, report=report)
    assert report["failed"] == [], report
    assert report["blend_retry"] == ["P/mask"]
    assert results["P/mask"]["icon_mode"] == "blend_retry"
    assert "icon_mode" not in results["P/opaque"] and "icon_mode" not in results["P/solid"]
    img = icons.decode_png((out_dir / "P" / "mask.png").read_bytes())
    alpha = img[..., 3][img[..., 3] > 0]
    assert len(alpha) > 500  # a real picture, not a stray pixel
    assert 100 <= int(np.median(alpha)) <= 140  # 0.4745 * 255 = 121: the material was blended, not forced opaque
    solid = icons.decode_png((out_dir / "P" / "solid.png").read_bytes())
    assert int(np.median(solid[..., 3][solid[..., 3] > 0])) == 255
