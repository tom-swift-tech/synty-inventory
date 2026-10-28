"""G1 S9 tools beside ``attach-calibrate`` and ``attach-spotcheck`` (docs/weapon_attach_geometry.md 3.10, 3.11, 4.3; AC142, AC144, AC78-style cache proof).

* ``attach-eval`` (AC142): the agreement table per geometry slot, and no exit code that depends on it. The directory is a literal one (``directory()``),
  the counts below are worked out by hand from the table:

    slot        pair            in the part's lists        label    state    reads as
    optic       L1 L2           listed (same_pack_fit)     fits     listed   agree
                L3              listed (cross_pack_fit)    no       listed   disagree
                P1              pending (same_pack_fit)    fits     pending  undecided
                A1              neither                    fits     absent   disagree
                A2 A3           neither                    no       absent   agree
                                                       -> agree 4, disagree 2, undecided 1, agreement 4 / 6 = 0.6667
    muzzle      L1 L2           listed                     no       listed   disagree
                A1 A2           neither                    fits     absent   disagree      -> agreement 0 / 4 = 0.0
    underbarrel L1              listed                     fits     listed   agree         -> agreement 1.0
    magazine    (no labelled pair)                                                           -> pairs 0, agreement null
    laser_light L1 (twin)       listed                     fits     TP   |  L2 listed, no: FP  |  A1 absent, fits: FN
                                                       -> label-era precision 1/2, recall 1/2: the only pairs the gates read
* ``attach-preview --pairs / --icons / --directory`` (spec 3.10): drawn with a stub renderer; the icon sheet cell is the render (64 px) and, to its right,
  a 32 px strip with the host icon above the part icon (each a 32 x 32 cell).
* The fit cache (spec 3.11): ``weapons build`` persists ``<catalogs>/weapons/_fit_cache.json``; a warm build reads no host mesh for features and gives the
  same directory bytes; a changed ``attach_rules_digest`` misses it; the file is ignored by git.

Deliberate breaks, on a scratch copy: the cache key without ``attach_rules_digest``; ``_fit_cache.json`` not saved; the gates reading the geometry slots.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T = _load("g1_tools_world")
H = _load("review_helpers")
W = T.W

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons import directory as directory_mod  # noqa: E402
from synty_inventory.weapons import eval as eval_mod  # noqa: E402
from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import fit_geometry as FG  # noqa: E402
from synty_inventory.weapons import geometry as geometry_mod  # noqa: E402
from synty_inventory.weapons import guards, preview  # noqa: E402
from synty_inventory.weapons.icons import RenderError, decode_png, encode_png  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402

BACKGROUND = (58, 64, 76, 255)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    monkeypatch.setattr(export_mod, "_repo_root", lambda: None)  # pytest's tmp dirs sit inside this checkout
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# -- attach-eval (AC142) ---------------------------------------------------------------------------------------------


def host_rec(name):
    return {"id": f"Q/{name}", "role": "whole", "kind": "ranged", "hold_class": "long_gun"}


def eval_directory():
    def part(slot, listed, pending=()):
        return {"id": f"Q/Part_{slot}", "role": "part", "kind": None, "hold_class": "none",
                "attachment": {"slot": slot, "compatible_hosts": [{"host": f"Q/{h}", "tier": t} for h, t in listed],
                               "pending_hosts": [{"host": f"Q/{h}", "tier": t} for h, t in pending]}}

    names = ["L1", "L2", "L3", "P1", "A1", "A2", "A3"]
    return {"weapons": [
        part("optic", [("L1", "same_pack_fit"), ("L2", "same_pack_fit"), ("L3", "cross_pack_fit")], [("P1", "same_pack_fit")]),
        part("muzzle", [("L1", "same_pack_fit"), ("L2", "same_pack_fit")]),
        part("underbarrel", [("L1", "same_pack_fit")]),
        part("magazine", [("L1", "same_pack_fit")]),
        part("laser_light", [("L1", "twin"), ("L2", "same_pack_fit")]),
        *(host_rec(n) for n in names)]}


def label(slot, host, fits):
    return {"part": f"Q/Part_{slot}", "host": f"Q/{host}", "fits": fits}


GEOMETRY_LABELS = [
    label("optic", "L1", True), label("optic", "L2", True), label("optic", "L3", False), label("optic", "P1", True),
    label("optic", "A1", True), label("optic", "A2", False), label("optic", "A3", False),
    label("muzzle", "L1", False), label("muzzle", "L2", False), label("muzzle", "A1", True), label("muzzle", "A2", True),
    label("underbarrel", "L1", True),
]
LASER_LABELS = [label("laser_light", "L1", True), label("laser_light", "L2", False), label("laser_light", "A1", True)]


@pytest.fixture
def run_eval(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(directory_mod, "load_directory", lambda cat: eval_directory())
    monkeypatch.setattr(eval_mod, "_catalogs", lambda args, cfg: Path("."))

    def go(pairs, *, min_precision=None, min_recall=None):
        path = tmp_path / "labels.json"
        path.write_text(json.dumps({"schema": "weapon-attach-labels/1", "pairs": pairs}), encoding="utf-8")
        args = SimpleNamespace(labels=str(path), min_precision=min_precision, min_recall=min_recall, pack=None)
        code = eval_mod.cmd(args, None)
        return code, json.loads(capsys.readouterr().out)
    return go


def test_ac142_the_agreement_table_per_geometry_slot_counts_the_hand_worked_cells(run_eval):
    code, out = run_eval(GEOMETRY_LABELS)
    assert code == 0 and out["ok"] is True
    assert list(out["slots"]) == ["optic", "muzzle", "underbarrel", "magazine"]
    optic = out["slots"]["optic"]
    assert optic["pairs"] == 7
    assert optic["listed"] == {"labelled_fit": 2, "labelled_no_fit": 1}
    assert optic["pending"] == {"labelled_fit": 1, "labelled_no_fit": 0}
    assert optic["absent"] == {"labelled_fit": 1, "labelled_no_fit": 2}
    assert (optic["agree"], optic["disagree"], optic["undecided"], optic["agreement"]) == (4, 2, 1, 0.6667)
    muzzle = out["slots"]["muzzle"]
    assert (muzzle["pairs"], muzzle["agree"], muzzle["disagree"], muzzle["agreement"]) == (4, 0, 4, 0.0)
    assert (out["slots"]["underbarrel"]["pairs"], out["slots"]["underbarrel"]["agreement"]) == (1, 1.0)
    assert (out["slots"]["magazine"]["pairs"], out["slots"]["magazine"]["agreement"]) == (0, None)
    assert out["pairs"] == 12 and out["label_era"]["pairs"] == 0 and out["gated"] == "label_era"


def test_ac142_the_exit_is_0_at_any_agreement_for_the_four_slots(run_eval):
    # the muzzle slot disagrees on every pair (agreement 0.0): still exit 0
    assert run_eval([p for p in GEOMETRY_LABELS if p["part"] == "Q/Part_muzzle"])[0] == 0
    # gates cannot be met by geometry pairs and cannot move the exit through them: with only geometry pairs a gate proves nothing (null) and fails
    # as "nothing was proved", never on the agreement
    code, out = run_eval(GEOMETRY_LABELS, min_precision=0.01, min_recall=0.01)
    assert code == 4 and [(f["gate"], f["got"]) for f in out["failed"]] == [("min_precision", None), ("min_recall", None)]
    assert out["slots"]["optic"]["agreement"] == 0.6667  # the table is printed on a failure too


def test_ac79_the_gates_read_the_label_era_slots_only_laser_light_here(run_eval):
    pairs = GEOMETRY_LABELS + LASER_LABELS
    code, out = run_eval(pairs)
    assert code == 0 and out["label_era"]["pairs"] == 3 and out["label_era"]["positives"] == 2
    era = out["label_era"]["default"]
    assert (era["tp"], era["fp"], era["fn"], era["tn"], era["precision"], era["recall"]) == (1, 1, 1, 0, 0.5, 0.5)
    assert run_eval(pairs, min_precision=0.5, min_recall=0.5)[0] == 0  # at the gate
    code, out = run_eval(pairs, min_precision=0.51)
    assert code == 4 and [(f["gate"], f["got"]) for f in out["failed"]] == [("min_precision", 0.5)]
    code, out = run_eval(pairs, min_recall=0.51)
    assert code == 4 and [f["gate"] for f in out["failed"]] == ["min_recall"]
    # the geometry slots disagree wildly (0.0 on the muzzle) and move neither verdict
    assert out["slots"]["muzzle"]["agreement"] == 0.0


def test_the_views_over_all_pairs_are_printed_unchanged(run_eval):
    _code, out = run_eval(GEOMETRY_LABELS + LASER_LABELS)
    # default view over all 15 pairs: listed pairs predict. TP: optic L1 L2, underbarrel L1, laser L1 (4); FP: optic L3 (cross listed, default reads
    # it), muzzle L1 L2, laser L2 (4); FN: optic P1? pending same_pack_fit is read by the default view -> TP (5th); optic A1, muzzle A1 A2, laser A1 (4)
    d = out["default"]
    assert (d["tp"], d["fp"], d["fn"], d["tn"]) == (5, 4, 4, 2)
    assert set(out["views"]) == {"default", "with_cross_pack", "same_pack_only"}


# -- attach-preview --pairs, --icons, --directory (spec 3.10) --------------------------------------------------------


SCOPE, NOTCHED, SCOPED_RAIL, LOWRAIL = (T.pid(n) for n in (T.GW.SCOPE, T.GW.CARBINE, T.SCOPED_RAIL, T.GW.LOWRAIL))
SILENCER, SIL_RING, UZI = T.pid(T.GW.SILENCER), T.pid(T.GW.RING_DEVICE), T.pid(T.GW.UZI)
NOWHERE = f"{T.PACK}/SM_Wep_Nowhere_01"
PAIRS = [  # a listed fit, a pending pair, a pair the directory does not list, another listed fit, a host that does not exist
    {"part": SCOPE, "host": SCOPED_RAIL}, {"part": SCOPE, "host": LOWRAIL}, {"part": SIL_RING, "host": NOTCHED},
    {"part": SILENCER, "host": UZI}, {"part": SCOPE, "host": NOWHERE},
]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("g1_tools")
    cat, root, directory, _excluded = T.build(tmp)
    stub = tmp / "glb_root_stub"
    stub.mkdir()
    cfg = H.write_config(tmp, cat, extra=[f'threejs_v2: "{root.as_posix()}"', f'synty_glb_root: "{stub.as_posix()}"'])
    return SimpleNamespace(tmp=tmp, cat=cat, root=root, directory=directory, cfg=cfg)


def stub_pixels(size):
    px = np.zeros((size, size, 4), dtype=np.uint8)
    px[size // 4:size // 2, size // 4:size // 2] = (200, 120, 40, 255)
    return px


class StubRenderer:
    def __init__(self, fail=()):
        self.jobs, self.fail = [], set(fail)

    def render_pair(self, job, size):
        self.jobs.append(job)
        if job["part"] in self.fail:
            raise RenderError("boom")
        return stub_pixels(size)


def with_stub(monkeypatch, renderer):
    class Ctx:
        def __init__(self, root, gpu=False):
            pass

        def __enter__(self):
            return renderer

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(preview, "check_renderer", lambda root: Path(root or "."))
    monkeypatch.setattr(preview, "PreviewRenderer", Ctx)


def pairs_file(tmp_path, pairs=PAIRS, name="pairs.json", **extra):
    path = tmp_path / name
    path.write_text(json.dumps({"schema": "weapon-attach-spotcheck/1", "pairs": [dict(p, slot="x", tier="y", fits=None, placed_wrong=None) for p in pairs], **extra}),
                    encoding="utf-8")
    return path


def verb(world, capsys, *flags):
    return H.run(world.cfg, capsys, ["weapons", "attach-preview", *flags])


def test_pairs_renders_exactly_the_listed_pairs_in_the_files_order_with_the_directorys_tier(world, capsys, monkeypatch, tmp_path):
    stub = StubRenderer()
    with_stub(monkeypatch, stub)
    out_dir = tmp_path / "pv"
    code, res = verb(world, capsys, "--out", str(out_dir), "--pairs", str(pairs_file(tmp_path)), "--size", "64")
    assert code == 0 and res["ok"] is True and (res["rendered"], res["failed"], res["pairs"]) == (4, [], 4)
    assert [(j["part"], j["host"]) for j in stub.jobs] == [(p["part"], p["host"]) for p in PAIRS[:4]]  # the file's order; the missing host is left out
    assert [j["tier"] for j in stub.jobs] == ["same_pack_fit", "same_pack_fit", "unlisted", "same_pack_fit"]
    assert [j["slot"] for j in stub.jobs] == ["optic", "optic", "muzzle", "muzzle"]
    assert [j["twin"] for j in stub.jobs] == [False] * 4
    assert res["unusable"] == [{"part": SCOPE, "host": NOWHERE, "reason": "host_missing"}] and res["skipped"] == {"host_missing": 1}
    index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    assert index["schema"] == "weapon-attach-preview/1" and len(index["pairs"]) == 4
    assert sorted(p.name for p in out_dir.iterdir() if p.suffix == ".png") == sorted(e["file"] for e in index["pairs"])  # the renders; no sheet without a flag


def test_pairs_takes_a_bare_pairs_object_and_ignores_extra_keys(world, capsys, monkeypatch, tmp_path):
    stub = StubRenderer()
    with_stub(monkeypatch, stub)
    path = tmp_path / "bare.json"
    path.write_text(json.dumps({"pairs": [{"part": SCOPE, "host": SCOPED_RAIL, "note": "x"}]}), encoding="utf-8")
    code, res = verb(world, capsys, "--out", str(tmp_path / "pv"), "--pairs", str(path), "--size", "64")
    assert code == 0 and res["rendered"] == 1 and [(j["part"], j["host"]) for j in stub.jobs] == [(SCOPE, SCOPED_RAIL)]


@pytest.mark.parametrize(("name", "doc"), [
    ("not an object", []),
    ("no pairs list", {"pairs": "x"}),
    ("another schema", {"schema": "weapon-attach-labels/1", "pairs": []}),
    ("an id without a slash", {"pairs": [{"part": "nope", "host": SCOPED_RAIL}]}),
    ("a missing host", {"pairs": [{"part": SCOPE}]}),
    ("a pair twice", {"pairs": [{"part": SCOPE, "host": SCOPED_RAIL}, {"part": SCOPE, "host": SCOPED_RAIL}]}),
])
def test_a_broken_pairs_file_is_exit_2_and_nothing_is_written(world, capsys, monkeypatch, tmp_path, name, doc):
    stub = StubRenderer()
    with_stub(monkeypatch, stub)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    code, res = verb(world, capsys, "--out", str(tmp_path / "pv"), "--pairs", str(path))
    assert code == 2 and res["ok"] is False and stub.jobs == [] and not (tmp_path / "pv").exists(), name


def test_pairs_with_ids_and_a_missing_pairs_file_are_exit_2(world, capsys, monkeypatch, tmp_path):
    with_stub(monkeypatch, StubRenderer())
    code, res = verb(world, capsys, "--pairs", str(pairs_file(tmp_path)), "--ids", SCOPE)
    assert code == 2 and "--pairs and --ids" in res["error"]
    assert verb(world, capsys, "--pairs", str(tmp_path / "nope.json"))[0] == 2


def test_pairs_plan_lists_the_pairs_without_a_renderer_and_writes_nothing(world, capsys, tmp_path):
    code, res = verb(world, capsys, "--plan", "--out", str(tmp_path / "pv"), "--pairs", str(pairs_file(tmp_path)))
    assert code == 0 and res["pairs"] == 4 and [p["tier"] for p in res["plan"]] == ["same_pack_fit", "same_pack_fit", "unlisted", "same_pack_fit"]
    assert not (tmp_path / "pv").exists()


def test_pairs_limit_and_pack_narrow_the_list(world, capsys, tmp_path):
    path = pairs_file(tmp_path)
    code, res = verb(world, capsys, "--plan", "--pairs", str(path), "--limit", "2")
    assert [(p["part"], p["host"]) for p in res["plan"]] == [(p["part"], p["host"]) for p in PAIRS[:2]]
    code, res = verb(world, capsys, "--plan", "--pairs", str(path), "--pack", "FAKE_G1_OTHER")
    assert code == 0 and res["pairs"] == 0


def test_directory_renders_the_same_pairs_against_another_directory(world, capsys, tmp_path):
    other = copy.deepcopy(world.directory)  # an "older build": the scope is no longer listed on the toothed host
    scope = next(w for w in other["weapons"] if w["id"] == SCOPE)
    scope["attachment"]["compatible_hosts"] = [e for e in scope["attachment"]["compatible_hosts"] if e["host"] != SCOPED_RAIL]
    alt = tmp_path / "older" / "directory.json"
    alt.parent.mkdir()
    alt.write_text(json.dumps(other), encoding="utf-8")
    path = pairs_file(tmp_path, PAIRS[:1])
    code, res = verb(world, capsys, "--plan", "--pairs", str(path))
    assert [p["tier"] for p in res["plan"]] == ["same_pack_fit"]
    code, res = verb(world, capsys, "--plan", "--pairs", str(path), "--directory", str(alt))
    assert code == 0 and [p["tier"] for p in res["plan"]] == ["unlisted"]
    code, res = verb(world, capsys, "--plan", "--pairs", str(path), "--directory", str(tmp_path / "nope.json"))
    assert code == 2 and "no weapon directory at" in res["error"]


# -- the icons ----------------------------------------------------------------------------------------------------------


HOST_RGB, PART_RGB = (10, 200, 30), (200, 30, 10)


def write_icon(path, rgb, h=16, w=16):
    path.parent.mkdir(parents=True, exist_ok=True)
    px = np.zeros((h, w, 4), dtype=np.uint8)
    px[..., :3], px[..., 3] = rgb, 255
    path.write_bytes(encode_png(px))


def test_the_name_rule_gives_the_asset_then_the_pack_suffixed_names_with_side_and_clean():
    assert preview.icon_names("P/SM_Wep_X_01") == [
        "ICON_SM_Wep_X_01.png", "ICON_SM_Wep_X_01_Side.png", "ICON_SM_Wep_X_01_Clean.png",
        "ICON_SM_Wep_X_01_P.png", "ICON_SM_Wep_X_01_P_Side.png", "ICON_SM_Wep_X_01_P_Clean.png"]


def test_icons_are_found_by_path_below_the_roots_case_insensitively_the_first_root_winning(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_icon(a / "Sub" / "icon_sm_wep_x_01_side.png", (1, 2, 3))  # the file name's case is the pack's; the rule matches without it
    write_icon(b / "ICON_SM_Wep_X_01_Side.png", (4, 5, 6))
    write_icon(b / "ICON_SM_Wep_Y_01.png", (7, 8, 9))
    index = preview.index_icons([a, b])
    assert preview.find_icon(index, "P/SM_Wep_X_01") == a / "Sub" / "icon_sm_wep_x_01_side.png"  # the first root wins the name
    assert preview.find_icon(index, "P/SM_Wep_Y_01") == b / "ICON_SM_Wep_Y_01.png"
    assert preview.find_icon(index, "P/SM_Wep_Z_01") is None
    write_icon(b / "ICON_SM_Wep_X_01.png", (9, 9, 9))  # the plain name outranks _Side
    assert preview.find_icon(preview.index_icons([a, b]), "P/SM_Wep_X_01") == b / "ICON_SM_Wep_X_01.png"


def test_an_icon_folder_that_is_not_there_is_exit_2(world, capsys, monkeypatch, tmp_path):
    with_stub(monkeypatch, StubRenderer())
    code, res = verb(world, capsys, "--out", str(tmp_path / "pv"), "--pairs", str(pairs_file(tmp_path)), "--icons", str(tmp_path / "nope"))
    assert code == 2 and "icon folder not found" in res["error"]


def test_the_contact_sheet_takes_any_equal_cells_and_squares_are_unchanged():
    squares = [np.full((4, 4, 4), 10 * (i + 1), dtype=np.uint8) for i in range(3)]
    sheet = preview.contact_sheet(squares)
    assert sheet.shape == (8, 8, 4) and (sheet[4:8, 0:4] == 30).all() and tuple(sheet[4, 4]) == BACKGROUND  # 2 columns, 2 rows, 4th cell empty
    wide = [np.full((4, 6, 4), 10 * (i + 1), dtype=np.uint8) for i in range(3)]
    sheet = preview.contact_sheet(wide)
    assert sheet.shape == (8, 12, 4) and (sheet[0:4, 6:12] == 20).all() and (sheet[4:8, 0:6] == 30).all() and tuple(sheet[6, 9]) == BACKGROUND


def test_a_wide_icon_keeps_its_aspect_in_its_cell():
    px = np.zeros((8, 16, 4), dtype=np.uint8)
    px[..., :3], px[..., 3] = (100, 150, 200), 255
    cell = preview._fit_icon(px, 32, 32)  # 16 x 8 -> 32 x 16, centred: rows 8..24 are the icon
    assert cell.shape == (32, 32, 4) and tuple(cell[16, 16]) == (100, 150, 200, 255) and tuple(cell[4, 16]) == BACKGROUND and tuple(cell[28, 16]) == BACKGROUND


def test_a_transparent_icon_shows_the_sheet_background_through():
    px = np.zeros((16, 16, 4), dtype=np.uint8)
    px[..., :3], px[..., 3] = (255, 255, 255), 0
    assert tuple(preview._fit_icon(px, 32, 32)[10, 10]) == BACKGROUND


def test_icons_go_beside_the_render_on_the_sheet_by_path_and_are_never_copied(world, capsys, monkeypatch, tmp_path):
    stub = StubRenderer()
    with_stub(monkeypatch, stub)
    icons_a, icons_b = tmp_path / "hud_a", tmp_path / "hud_b"
    write_icon(icons_a / "Icons_Weapons" / "ICON_SM_Wep_Rifle_Notched_Scoped_01_Side.png", HOST_RGB)  # the host: _Side, below a sub folder
    write_icon(icons_b / "ICON_SM_Wep_Zulu_Scope_01_FAKE_G1.png", PART_RGB)  # the part: the pack-suffixed name, in the second root
    (icons_b / "ICON_SM_Wep_Rifle_Notched_01.png").write_bytes(b"not a png")  # an icon the decoder cannot read counts as missing
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    pairs = [{"part": SCOPE, "host": SCOPED_RAIL}, {"part": SIL_RING, "host": NOTCHED}]
    out_dir = tmp_path / "pv"
    code, res = verb(world, capsys, "--out", str(out_dir), "--pairs", str(pairs_file(tmp_path, pairs)), "--size", "64",
                     "--icons", str(icons_a), str(icons_b))
    assert code == 0 and res["rendered"] == 2
    assert res["icons"] == {"host": 1, "part": 1, "missing": sorted([NOTCHED, SIL_RING])}
    sheet = decode_png((out_dir / "sheet.png").read_bytes())  # --icons implies --sheet
    assert sheet.shape == (64, 192, 4)  # two cells in one row, each the 64 px render and a 32 px strip
    assert tuple(sheet[24, 24]) == (200, 120, 40, 255)  # the stub's block in the first render
    assert tuple(sheet[16, 80]) == (*HOST_RGB, 255)  # strip, upper half: the host icon, a 16 px icon doubled into its 32 x 32 cell
    assert tuple(sheet[48, 80]) == (*PART_RGB, 255)  # strip, lower half: the part icon
    assert tuple(sheet[16, 160]) == BACKGROUND and tuple(sheet[48, 160]) == BACKGROUND  # the second pair has none
    assert all(decode_png(p.read_bytes()).shape == (64, 64, 4) for p in out_dir.glob("*.png") if p.name != "sheet.png")  # the pair PNGs are the renders alone
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert [f for f in after if f not in before and not f.startswith("pv/")] == ["pairs.json"]  # nothing but the pairs file beside the output
    assert not any(p.name.startswith("ICON_") for p in out_dir.iterdir())  # read by path, never copied


def test_without_icons_the_sheet_is_the_renders_and_only_with_the_flag(world, capsys, monkeypatch, tmp_path):
    with_stub(monkeypatch, StubRenderer())
    out_dir = tmp_path / "pv"
    verb(world, capsys, "--out", str(out_dir), "--pairs", str(pairs_file(tmp_path, PAIRS[:2])), "--size", "64")
    assert not (out_dir / "sheet.png").exists()
    code, res = verb(world, capsys, "--out", str(out_dir), "--pairs", str(pairs_file(tmp_path, PAIRS[:2])), "--size", "64", "--sheet")
    assert code == 0 and "icons" not in res and decode_png((out_dir / "sheet.png").read_bytes()).shape == (64, 128, 4)


# -- the fit cache: persisted by the build, keyed on the attach rules (spec 3.11, 4.3) ----------------------------------


@pytest.fixture
def computes(monkeypatch):
    seen: list = []
    real = FG._compute

    def counting(*args, **kwargs):
        seen.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(FG, "_compute", counting)
    return seen


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A fresh world (so a test may delete its caches) and the ``weapons build`` verb over it."""
    world_ = T.tools_world()
    cat, root = W.write_world(tmp_path, world_)
    cfg = H.write_config(tmp_path, cat, extra=[f'threejs_v2: "{root.as_posix()}"'])
    import synty_inventory.packs.profile as profile

    monkeypatch.setattr(profile, "load_settings_table", lambda *a, **k: W.pack_settings(world_))
    return SimpleNamespace(cat=cat, root=root, cfg=cfg, wdir=cat / "weapons", world=world_, tmp=tmp_path)


def build_cli(built, capsys, *flags):
    geometry_mod._DECODE_MEMO.clear()
    code, out = H.run(built.cfg, capsys, ["weapons", "build", *flags])
    assert code == 0, out
    return out["report"]


def test_the_build_persists_the_fit_cache_and_a_warm_build_hits_it_with_the_same_bytes(built, capsys, computes):
    cold = build_cli(built, capsys)
    assert len(computes) > 0 and cold["geometry_stats"]["decoded"] > 0 and cold["fit_stats"]["computed"] > 0
    cache_file = built.wdir / "_fit_cache.json"
    assert sorted(p.name for p in built.wdir.iterdir()) == ["_fit_cache.json", "_geometry_cache.json", "directory.json", "excluded.json"]
    first, cache_bytes = (built.wdir / "directory.json").read_bytes(), cache_file.read_bytes()
    assert isinstance(json.loads(cache_bytes), dict) and json.loads(cache_bytes)  # entries: one per host with features
    hosts = len(computes)

    del computes[:]
    warm = build_cli(built, capsys)
    assert computes == [] and warm["geometry_stats"]["decoded"] == 0 and warm["fit_stats"]["computed"] == 0 and warm["fit_stats"]["cached"] > 0
    assert (built.wdir / "directory.json").read_bytes() == first  # a hit equals a recompute
    assert cache_file.read_bytes() == cache_bytes  # nothing new to save: the file is not rewritten with other content

    # the geometry cache gone, the fit cache kept: the hosts are decoded again, their features are not computed again, and the directory is the same
    (built.wdir / "_geometry_cache.json").unlink()
    again = build_cli(built, capsys)
    assert computes == [] and again["geometry_stats"]["decoded"] > 0
    assert (built.wdir / "directory.json").read_bytes() == first

    # --rebuild ignores both caches and computes every host's features again, to the same bytes
    rebuilt = build_cli(built, capsys, "--rebuild")
    assert len(computes) == hosts and rebuilt["geometry_stats"]["cached"] == 0
    assert (built.wdir / "directory.json").read_bytes() == first


def test_a_corrupt_fit_cache_is_ignored_not_fatal(built, capsys, computes):
    build_cli(built, capsys)
    first = (built.wdir / "directory.json").read_bytes()
    (built.wdir / "_fit_cache.json").write_text("{not json", encoding="utf-8")
    (built.wdir / "_geometry_cache.json").unlink()
    del computes[:]
    build_cli(built, capsys)
    assert len(computes) > 0 and (built.wdir / "directory.json").read_bytes() == first


def build_api(built, rules, fit, geometry):
    return directory_mod.build_directory_report(
        built.cat, overrides=empty_overrides(), pack_settings=W.pack_settings(built.world), rules=rules, threejs_v2_dir=built.root,
        geometry_cache=geometry, fit_cache=fit)


EDITS = {  # spec 3.11: any value of attachment_rules moves attach_rules_digest, which is in the key of a host's features
    "a fit_geometry literal": lambda r: r["attachment_rules"]["fit_geometry"]["clamp"].update(overhang_max_m=0.011),
    "a sight_probe value": lambda r: r["attachment_rules"]["sight_probe"].update(side_frac=0.11),
    "the genre of a pack": lambda r: r["attachment_rules"]["attach_genre_by_pack"].update({"ZZ_Pack": "modern"}),
}


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_a_changed_attach_rules_digest_misses_the_fit_cache_and_recomputes(built, computes, edit):
    rules = T.tools_rules()
    fit: dict = {}
    build_api(built, rules, fit, {})
    hosts = len(computes)
    assert hosts > 0
    del computes[:]
    build_api(built, rules, fit, {})  # the same rules with a cold geometry cache: every host's features come from the fit cache
    assert computes == []
    edited = copy.deepcopy(rules)
    EDITS[edit](edited)
    before = directory_mod.attach_rules_digest(rules)
    assert directory_mod.attach_rules_digest(edited) != before and directory_mod.weapon_rules_digest(edited) == directory_mod.weapon_rules_digest(rules)
    build_api(built, edited, fit, {})
    assert len(computes) == hosts  # every host missed: the key carries the digest


@pytest.fixture
def pass_computes(monkeypatch):
    """The part and well results computed (not cached) by a build, counted per kind: ``fitpart|`` (a muzzle part's inner ring) and ``well|`` (a magazine's entry section)."""
    seen = {"part": 0, "well": 0}
    real = directory_mod._fit_cached

    def counting(cache, cache_id, key, fp, compute):
        value, how = real(cache, cache_id, key, fp, compute)
        if how == "computed":
            seen["well" if cache_id.startswith("well|") else "part"] += 1
        return value, how
    monkeypatch.setattr(directory_mod, "_fit_cached", counting)
    return seen


def fit_edit(rules, block, key, value):
    edited = copy.deepcopy(rules)
    edited["attachment_rules"]["fit_geometry"][block][key] = value
    return edited


def cold_then_warm(built, pass_computes):
    """Build cold (so the geometry cache holds every part and well result), then return (rules, the cache, the cold counts)."""
    rules, geometry = T.tools_rules(), {}
    build_api(built, rules, {}, geometry)
    cold = dict(pass_computes)
    for k in pass_computes:
        pass_computes[k] = 0
    return rules, geometry, cold


def rebuild(built, rules, geometry, pass_computes):
    for k in pass_computes:
        pass_computes[k] = 0
    build_api(built, rules, {}, copy.deepcopy(geometry))
    return dict(pass_computes)


def test_the_tools_world_computes_4_muzzle_parts_and_25_wells_cold_and_none_warm(built, pass_computes):
    rules, geometry, cold = cold_then_warm(built, pass_computes)
    assert cold == {"part": 4, "well": 25}
    assert rebuild(built, rules, geometry, pass_computes) == {"part": 0, "well": 0}


@pytest.mark.parametrize("key", ["end_slab_m", "inner_ratio"])
def test_the_part_cache_keys_on_the_bore_block_so_a_bore_value_recomputes_the_muzzle_parts_only(built, pass_computes, key):
    # spec 3.11 / the ruling on item 8: the part pass keys on the rule inputs it reads, not on attach_rules_digest. ``device_inner_d`` reads
    # bore.end_slab_m; the key carries the whole bore block, so any bore value recomputes the 4 muzzle parts and nothing else
    rules, geometry, _cold = cold_then_warm(built, pass_computes)
    value = {"end_slab_m": 0.012, "inner_ratio": [0.5, 1.2]}[key]
    assert value != rules["attachment_rules"]["fit_geometry"]["bore"][key]
    assert rebuild(built, fit_edit(rules, "bore", key, value), geometry, pass_computes) == {"part": 4, "well": 0}


@pytest.mark.parametrize(("block", "key", "value"), [
    ("clamp", "overhang_max_m", 0.011), ("clamp", "ratio_min", 0.9), ("well", "tol", 0.2)])
def test_a_value_the_part_and_well_measures_do_not_read_recomputes_none(built, pass_computes, block, key, value):
    rules, geometry, _cold = cold_then_warm(built, pass_computes)
    assert value != rules["attachment_rules"]["fit_geometry"][block][key]
    assert rebuild(built, fit_edit(rules, block, key, value), geometry, pass_computes) == {"part": 0, "well": 0}


def test_the_well_cache_keys_on_the_entry_depth_so_a_new_depth_recomputes_the_25_wells_only(built, pass_computes):
    # ``entry_section`` is cut at u_rb - well.entry_depth_m: the depth is in the well key, and the muzzle parts do not read it
    rules, geometry, _cold = cold_then_warm(built, pass_computes)
    assert rules["attachment_rules"]["fit_geometry"]["well"]["entry_depth_m"] != 0.003
    assert rebuild(built, fit_edit(rules, "well", "entry_depth_m", 0.003), geometry, pass_computes) == {"part": 0, "well": 25}


def test_the_fit_cache_file_is_never_committed_it_is_ignored_by_git():
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    for rel in ("catalogs/weapons/_fit_cache.json", "tests/fixtures/weapons/catalogs/weapons/_fit_cache.json", "anywhere/else/_fit_cache.json"):
        result = subprocess.run([git, "-C", str(ROOT), "check-ignore", "-q", rel], capture_output=True)
        assert result.returncode == 0, rel  # 0: ignored


def test_the_fit_cache_sits_beside_the_directory_in_the_catalogs_dir_never_in_the_repo(built, capsys):
    build_cli(built, capsys)
    assert FG.FIT_CACHE_NAME == "_fit_cache.json" and (built.wdir / FG.FIT_CACHE_NAME).is_file()
    assert ROOT not in (built.wdir / FG.FIT_CACHE_NAME).resolve().parents or ".pytest_tmp" in str(built.wdir)  # the pytest tmp dir is the one place inside


def test_the_digests_and_versions_this_slice_must_not_move_are_where_they_were():
    assert pkg.WEAPON_ATTACH_VERSION == 14 and pkg.WEAPON_GEOMETRY_VERSION == 6
