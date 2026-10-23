"""W8d: ``weapons attach-preview`` (docs/weapon_attachments.md 6.2; AC83).

Everything here runs without a browser except the last test, which draws a real picture and skips cleanly when Playwright,
Chromium or three.js are missing. The geometry the picture shows is checked on the numbers instead: the job's 4x4 is applied to the
part's own fixture mesh and compared with the baked child it stands in for. Hand-derived literals (host frame, metres):

* optic() spans x -0.03..0.03, y 0..0.08, z -0.1..0.1; mag_box x +-0.01, y -0.12..0, z +-0.02; flip_y(optic()) y -0.08..0;
  upside_down_optic() x +-0.015, y 0..0.03, z +-0.06; the brake tube r 0.0125 about (x 0, y 0.055), z 0.65..0.73.
* Epsilon, Gamma are the upright hosts; their children sit at the authored offsets (the W8c SLOT_CASES literals).
* Alpha is the host whose body is turned a quarter turn about X, (x, y, z) -> (x, z, -y). Its baked children keep their authored
  meshes (they are not twins in orientation any more), so the placed part is checked against algebra instead
  (``TURNED_BOXES``): the optic anchor is (0.005, 0, 0.05) with forward +z, up +y (so right +x); Alpha's optic mount is
  (0.005, 0.1, -0.05) with forward +y, up +z (right -x). The part maps x -> 0.01 - x, z -> 0.1 + (z - 0.05) along y, y -> -0.05 + y
  along z: box x -0.02..0.04, y -0.05..0.15, z -0.05..0.03. The magazine anchor is the origin with forward +z, up -y (right -x);
  its mount (0, -0.05, 0) has forward +y, up -z (right +x): x -> -x, z -> -0.05 + z along y, y -> y along z: box
  x -0.01..0.01, y -0.07..-0.03, z -0.12..0.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8d_world", FIX / "w8d_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)
H, C = X.H, X.C

from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import icons, preview  # noqa: E402
from synty_inventory.weapons.attach import place  # noqa: E402
from synty_inventory.weapons.directory import write_directory  # noqa: E402
from synty_inventory.weapons.icons import RenderError  # noqa: E402

TOL_M, TOL_DEG = 0.0005, 0.1  # AC69's literals: 0.5 mm, 0.1 degrees
SLOTS = ["optic", "muzzle", "underbarrel", "magazine", "laser_light"]
# case -> (part mesh name, host, the baked child's AABB in the host's asset frame): upright hosts, where the baked twin is the
# ground truth
TWIN_CASES = {
    "optic_upright": ("SCOPE", "EPSILON", ((-0.03, 0.10, 0.0), (0.03, 0.18, 0.20))),
    "underbarrel": ("GRIP", "GAMMA", ((-0.03, -0.08, -0.07), (0.03, 0.0, 0.13))),
    "laser_light": ("LASER", "GAMMA", ((-0.015, -0.03, -0.06), (0.015, 0.0, 0.06))),
    "muzzle": ("SIL_BRAKE", "EPSILON", ((-0.0125, 0.0425, 0.65), (0.0125, 0.0675, 0.73))),
}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w8d_preview")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(export_mod, "_repo_root", lambda: None)  # the pytest tmp dir sits inside this checkout
    directory, excluded, cat, root = X.build(tmp)
    write_directory(cat, directory, excluded)
    glb_stub = tmp / "glb_root_stub"  # stands in for the synty-glb checkout when the renderer is stubbed
    glb_stub.mkdir()
    yield SimpleNamespace(tmp=tmp, directory=directory, cat=cat, root=root, by_id={w["id"]: w for w in directory["weapons"]},
                          cfg=X.write_config(tmp, cat, root=root), glb_stub=glb_stub)
    mp.undo()


def stub_pixels(size: int) -> np.ndarray:
    px = np.zeros((size, size, 4), dtype=np.uint8)
    px[size // 4:size // 2, size // 4:size // 2] = (200, 120, 40, 255)  # a premultiplied, fully opaque block
    return px


class StubRenderer:
    """Records the jobs it is asked to draw; ``blank`` ids return nothing drawn, ``fail`` ids raise."""

    def __init__(self, blank=(), fail=()):
        self.jobs: list[dict] = []
        self.blank, self.fail = set(blank), set(fail)

    def render_pair(self, job, size):
        self.jobs.append(job)
        if job["part"] in self.fail:
            raise RenderError("boom")
        return np.zeros((size, size, 4), dtype=np.uint8) if job["part"] in self.blank else stub_pixels(size)


# --- which pairs ----------------------------------------------------------------------------------------------------


def test_the_plan_covers_every_twin_pair_and_all_five_slots_with_a_non_twin_sample(world):
    pairs, skipped = preview.plan_pairs(world.directory)
    assert skipped == {}
    twins = [p for p in pairs if p["twin"]]
    others = [p for p in pairs if not p["twin"]]
    assert (len(pairs), len(twins), len(others)) == (67, 55, 12)  # A2: the 10 twin pairs of the two iron-sight parts (optic/iron) are gone with the kind
    assert [p["twin"] for p in pairs] == [True] * 55 + [False] * 12  # twins first
    assert {p["slot"] for p in pairs} == set(SLOTS) | {"sight_rear"}  # A3 (W8i): the rear iron sight part is a same_pack_fit of the pistol host (no family overlap needed)
    assert {p["slot"] for p in twins} == set(SLOTS)  # the twin pairs alone cover every slot
    assert len({(p["part"], p["host"]) for p in pairs}) == 67  # no pair twice
    # every compatible twin pair of the directory is in the plan
    want = {(w["id"], e["host"]) for w in world.directory["weapons"] if w.get("attachment")
            for e in w["attachment"]["compatible_hosts"] if e["tier"] == "twin"}
    assert {(p["part"], p["host"]) for p in twins} == want
    # the sample takes one pair per attachment, best tier first (W8e): the 9 same_pack_fit pairs (3 optic, 5 muzzle, 1 sight_rear,
    # round-robin over the slots) precede the 3 cross_pack_fit ones (2 magazine and 1 laser_light; underbarrel has no non-twin
    # candidate). A3 (W8i): the sight_rear pair is new (a same-pack sight needs no family overlap) and took a cross_pack laser_light place
    assert [p["slot"] for p in others] == ["optic", "muzzle", "sight_rear", "optic", "muzzle", "optic", "muzzle", "muzzle", "muzzle",
                                           "magazine", "laser_light", "magazine"]
    assert [p["tier"] for p in others] == ["same_pack_fit"] * 9 + ["cross_pack_fit"] * 3
    assert len({p["part"] for p in others}) == 12
    assert preview.plan_pairs(world.directory)[0] == pairs  # deterministic


def test_the_plan_narrows_by_ids_packs_and_limit_and_names_unusable_pairs(world):
    mag = "FAKE_CompA/SM_Wep_Rifle_Mag_01"
    pairs, _ = preview.plan_pairs(world.directory, ids={mag})
    assert [(p["host"].split("/")[1], p["tier"]) for p in pairs] == [
        ("SM_Wep_Rifle_Alpha_01", "twin"), ("SM_Wep_Rifle_Mount_01", "twin"), ("SM_Wep_Rifle_Double_01", "cross_pack_fit")]
    assert len(preview.plan_pairs(world.directory, limit=5)[0]) == 5
    assert all(p["twin"] for p in preview.plan_pairs(world.directory, limit=5)[0])
    only_a, _ = preview.plan_pairs(world.directory, packs={"FAKE_CompA"})
    assert len(only_a) == 19 and all(p["part"].startswith("FAKE_CompA/") for p in only_a)
    broken = json.loads(json.dumps(world.directory))
    recs = {w["id"]: w for w in broken["weapons"]}
    recs["FAKE_CompA/SM_Wep_Rifle_Alpha_01"]["geometry"]["mounts"]["magazine"].update(source="none", point=None, forward=None, up=None)
    recs["FAKE_Mount/SM_Wep_Rifle_Mount_01"]["files"]["glb"] = None
    del recs["FAKE_Mount/SM_Wep_Rifle_Double_01"]
    broken["weapons"] = list(recs.values())
    pairs, skipped = preview.plan_pairs(broken, ids={mag})
    assert pairs == [] and skipped == {"no_mount": 1, "host_unmeasured": 1, "host_missing": 1}
    recs[mag]["attachment"]["anchor"] = None
    assert preview.plan_pairs(broken, ids={mag})[1] == {"anchor_unmeasured": 1, "host_unmeasured": 1, "host_missing": 1}
    recs[mag]["files"]["glb"] = None
    assert preview.plan_pairs(broken, ids={mag})[1] == {"part_unmeasured": 2, "host_missing": 1}  # the part is judged before the host's GLB


# --- what the renderer is told -----------------------------------------------------------------------------------------


def job_of(world, part_id: str, host_id: str) -> dict:
    pair = next(p for p in preview.plan_pairs(world.directory, ids={part_id})[0] if p["host"] == host_id)
    return preview.build_job(pair, world.by_id[part_id], world.by_id[host_id], world.root)


def test_the_job_hides_the_baked_child_the_attachment_replaces_and_carries_the_hosts_basis(world):
    job = job_of(world, C.P[C.MAG], C.H[C.ALPHA])
    assert job["hide"] == ["SM_Wep_Rifle_Alpha_01_Mag"]
    assert job["item_basis"] == [[-1, 0, 0], [0, 0, 1], [0, 1, 0]]  # the host's, not the part's
    assert (job["host_scale"], job["part_scale"]) == (1.0, 1.0)
    assert job["host_glb"].is_file() and job["part_glb"].is_file()
    assert job["host_glb"].is_relative_to(world.root) and job["part_glb"].is_relative_to(world.root)
    m = np.asarray(job["matrix"])
    assert m.shape == (4, 4) and np.allclose(m[3], [0, 0, 0, 1])
    assert np.allclose(m[:3, :3] @ m[:3, :3].T, np.eye(3), atol=1e-9) and abs(np.linalg.det(m[:3, :3]) - 1.0) < 1e-9
    scope = job_of(world, C.P[C.SCOPE], C.H[C.EPSILON])
    assert scope["hide"] == ["SM_Wep_Rifle_Epsilon_01_Scope"]


def test_the_placed_part_is_tinted_and_the_host_is_not(world):
    """AC83 look: the attachment is drawn in its own flat colour so it reads against the host (white on white hid a muzzle brake)."""
    job = job_of(world, C.P[C.SIL_BRAKE], C.H[C.EPSILON])
    assert job["part_tint"] == "e8742a" and job["host_tint"] is None  # None: the host keeps its own materials
    r, g, b = (int(job["part_tint"][i:i + 2], 16) for i in (0, 2, 4))
    assert (r, g, b) == (232, 116, 42) and r - b > 150  # unmistakably orange, against a grey / white host
    seen = StubRenderer()
    preview.render_pairs(seen, [job], Path(world.tmp) / "tint_out", 64)
    assert seen.jobs[0]["part_tint"] == "e8742a"


def angle_deg(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1.0, 1.0))))


def test_every_planned_job_maps_the_anchor_onto_the_mount_within_the_tolerances(world):
    pairs, _ = preview.plan_pairs(world.directory)
    for pair in pairs:
        job = preview.build_job(pair, world.by_id[pair["part"]], world.by_id[pair["host"]], world.root)
        anchor = world.by_id[pair["part"]]["attachment"]["anchor"]
        mount = world.by_id[pair["host"]]["geometry"]["mounts"][pair["slot"]]
        m = np.asarray(job["matrix"])
        got = (m @ np.append(anchor["point"], 1.0))[:3]
        assert np.allclose(got, mount["point"], atol=TOL_M, rtol=0), pair
        for key in ("up", "forward"):
            assert angle_deg(m[:3, :3] @ anchor[key], mount[key]) <= TOL_DEG, (pair, key)


TURNED_BOXES = {  # worked out above, tolerance 1 mm
    "optic": ("SCOPE", ((-0.02, -0.05, -0.05), (0.04, 0.15, 0.03))),
    "magazine": ("MAG", ((-0.01, -0.07, -0.12), (0.01, -0.03, 0.0))),
}


@pytest.mark.parametrize("slot", sorted(TURNED_BOXES))
def test_a_part_on_the_turned_host_is_placed_by_the_algebra_of_the_frames(world, slot):
    name, (lo, hi) = TURNED_BOXES[slot]
    job = job_of(world, C.P[getattr(C, name)], C.H[C.ALPHA])
    verts, _ = C.PART_MESHES[getattr(C, name)]()
    box = C.aabb((np.c_[verts, np.ones(len(verts))] @ np.asarray(job["matrix"]).T)[:, :3])
    assert np.allclose(box[0], lo, atol=0.001, rtol=0) and np.allclose(box[1], hi, atol=0.001, rtol=0), box


@pytest.mark.parametrize("case", sorted(TWIN_CASES))
def test_the_placed_twin_lands_on_the_baked_child_it_replaces(world, case):
    part_name, host_name, child = TWIN_CASES[case]
    part_id, host_id = C.P[getattr(C, part_name)], C.H[getattr(C, host_name)]
    job = job_of(world, part_id, host_id)
    verts, _tris = C.PART_MESHES[getattr(C, part_name)]()
    placed = (np.c_[verts, np.ones(len(verts))] @ np.asarray(job["matrix"]).T)[:, :3]
    box = C.aabb(placed)
    want = (np.array(child[0]), np.array(child[1]))
    assert np.all(np.abs((box[0] + box[1]) / 2 - (want[0] + want[1]) / 2) <= 0.003), (box, want)
    assert C.iou(box, want) >= 0.90


def test_the_jobs_matrix_reproduces_the_shared_placement_oracle_including_the_three_cycle(world):
    """The oracle (mount_place.json, copied byte for byte in W8c) is what catches an inverse rotation: three_cycle is the one
    case whose rotation is not its own transpose, so a transposed matrix lands elsewhere. Run through ``build_job``."""
    oracle = json.loads((FIX / "mount_place.json").read_text(encoding="utf-8"))
    assert "three_cycle" in {c["name"] for c in oracle["cases"]}
    part_rec, host_rec = world.by_id[C.P[C.SCOPE]], world.by_id[C.H[C.EPSILON]]
    for case in oracle["cases"]:
        part = {"attachment": {"anchor": case["part"]}, "files": part_rec["files"]}
        host = {"geometry": {"mounts": {"optic": case["host"]}, "item_basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
                "files": host_rec["files"]}
        pair = {"part": "p", "host": "h", "slot": "optic", "tier": "twin", "score": 1.0, "twin": True}
        m = np.asarray(preview.build_job(pair, part, host, world.root)["matrix"])
        assert np.allclose(m[:3, 3], case["origin"], atol=TOL_M, rtol=0), case["name"]
        for k, column in enumerate(case["basis"]):
            assert angle_deg(m[:3, k], column) <= TOL_DEG, (case["name"], k)


# --- the files ---------------------------------------------------------------------------------------------------------


def test_render_pairs_writes_one_png_per_pair_an_index_and_an_optional_sheet(world, tmp_path):
    pairs, _ = preview.plan_pairs(world.directory, ids={C.P[C.MAG]})
    jobs = [preview.build_job(p, world.by_id[p["part"]], world.by_id[p["host"]], world.root) for p in pairs]
    stub = StubRenderer()
    out = tmp_path / "pv"
    report = preview.render_pairs(stub, jobs, out, 64, sheet=True)
    assert [j["host"] for j in stub.jobs] == [p["host"] for p in pairs] and report["rendered"] == 3 and report["failed"] == []
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted([e["file"] for e in report["pairs"]] + ["index.json", "sheet.png"]) and len(names) == 5
    assert all(n.startswith("FAKE_CompA_SM_Wep_Rifle_Mag_01--") or n in ("index.json", "sheet.png") for n in names)
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["schema"] == "weapon-attach-preview/1" and [p["tier"] for p in index["pairs"]] == ["twin", "cross_pack_fit", "twin"]
    assert {p["part"] for p in index["pairs"]} == {C.P[C.MAG]}
    png = (out / index["pairs"][0]["file"]).read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    from PIL import Image  # the pictures are real, flattened PNGs
    img = np.asarray(Image.open(out / index["pairs"][0]["file"]).convert("RGBA"))
    assert img.shape == (64, 64, 4) and img[..., 3].min() == 255
    assert tuple(img[0, 0, :3]) == preview.BACKGROUND and tuple(img[20, 20, :3]) == (200, 120, 40)
    assert np.asarray(Image.open(out / "sheet.png")).shape == (128, 128, 4)  # 3 pictures: a 2 x 2 grid
    assert b"\r\n" not in (out / "index.json").read_bytes()


def test_a_second_run_merges_into_the_index_and_a_failed_pair_is_listed_not_fatal(world, tmp_path):
    out = tmp_path / "pv"
    mag, scope = C.P[C.MAG], C.P[C.SCOPE]

    def jobs_of(pid):
        return [preview.build_job(p, world.by_id[p["part"]], world.by_id[p["host"]], world.root)
                for p in preview.plan_pairs(world.directory, ids={pid})[0]]

    preview.render_pairs(StubRenderer(), jobs_of(mag), out, 64)
    report = preview.render_pairs(StubRenderer(blank={scope}), jobs_of(mag)[:1] + jobs_of(scope)[:1], out, 64)
    assert report["rendered"] == 1 and report["failed"] == [{"part": scope, "host": jobs_of(scope)[0]["host"], "error": "blank_render"}]
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))["pairs"]
    assert len(index) == 3 and {p["part"] for p in index} == {mag}  # the earlier pairs are kept
    report = preview.render_pairs(StubRenderer(fail={scope}), jobs_of(scope)[:2], out, 64)
    assert report["rendered"] == 0 and [f["error"] for f in report["failed"]] == ["boom", "boom"]
    assert len(json.loads((out / "index.json").read_text(encoding="utf-8"))["pairs"]) == 3
    (out / index[0]["file"]).unlink()  # a PNG that went away drops out of the index at the next run
    preview.render_pairs(StubRenderer(), [], out, 64)
    assert len(json.loads((out / "index.json").read_text(encoding="utf-8"))["pairs"]) == 2


def test_the_contact_sheet_is_a_grid_in_index_order_on_the_background():
    imgs = [np.full((8, 8, 4), v, dtype=np.uint8) for v in (10, 20, 30, 40, 50)]
    sheet = preview.contact_sheet(imgs)
    assert sheet.shape == (16, 24, 4)  # 5 pictures: ceil(sqrt(5)) = 3 columns, 2 rows
    assert sheet[0, 0, 0] == 10 and sheet[0, 8, 0] == 20 and sheet[0, 16, 0] == 30 and sheet[8, 0, 0] == 40 and sheet[8, 8, 0] == 50
    assert tuple(sheet[8, 16, :3]) == preview.BACKGROUND and sheet[8, 16, 3] == 255  # the unused cell


def test_flatten_composites_a_premultiplied_picture_over_the_background():
    px = np.zeros((2, 2, 4), dtype=np.uint8)
    px[0, 0] = (255, 0, 0, 255)  # opaque red
    px[0, 1] = (50, 0, 0, 100)  # premultiplied: red 127 at alpha 100/255 over the background
    out = preview.flatten(px)
    assert tuple(out[0, 0]) == (255, 0, 0, 255)
    assert tuple(out[1, 1]) == (58, 64, 76, 255)
    assert tuple(out[0, 1, :3]) == (50 + round(58 * 155 / 255), round(64 * 155 / 255), round(76 * 155 / 255)) and out[0, 1, 3] == 255


def test_pair_file_names_are_stable_flat_and_distinct():
    a = preview.pair_file("FAKE_CompA/SM_Wep_Rifle_Mag_01", "FAKE_CompA/SM_Wep_Rifle_Alpha_01")
    assert a == preview.pair_file("FAKE_CompA/SM_Wep_Rifle_Mag_01", "FAKE_CompA/SM_Wep_Rifle_Alpha_01")
    assert a != preview.pair_file("FAKE_CompA/SM_Wep_Rifle_Mag_01", "FAKE_CompA/SM_Wep_Rifle_Alpha_02")
    assert "/" not in a and "\\" not in a and a.endswith(".png") and a.startswith("FAKE_CompA_SM_Wep_Rifle_Mag_01--")
    assert preview.pair_file("a/b c", "d/e") != preview.pair_file("a/b_c", "d/e")  # the hash tells sanitised twins apart


# --- the verb ----------------------------------------------------------------------------------------------------------


def verb(world, capsys, *argv, cfg=None):
    return H.run(cfg or world.cfg, capsys, ["weapons", "attach-preview", *argv])


def with_stub(monkeypatch, renderer):
    class Ctx:
        def __init__(self, root, gpu=False):
            self.gpu = gpu

        def __enter__(self):
            return renderer

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(preview, "check_renderer", lambda root: Path(root or "."))
    monkeypatch.setattr(preview, "PreviewRenderer", Ctx)


def test_plan_prints_the_pairs_writes_nothing_and_needs_no_renderer(world, capsys, tmp_path):
    out = tmp_path / "pv"
    code, res = verb(world, capsys, "--plan", "--out", str(out))
    assert code == 0 and (res["pairs"], res["twins"], len(res["plan"])) == (67, 55, 67)
    assert not out.exists()
    wdir_default = Path(world.cat) / "weapons" / preview.DEFAULT_DIRNAME
    assert not wdir_default.exists()
    code, res = verb(world, capsys, "--plan", "--ids", C.P[C.MAG])
    assert code == 0 and res["pairs"] == 3 and [p["tier"] for p in res["plan"]] == ["twin", "twin", "cross_pack_fit"]
    assert verb(world, capsys, "--plan", "--ids", "FAKE_Fantasy/SM_Wep_Sword_01")[0] == 2  # not an attachment
    assert verb(world, capsys, "--plan", "--pack", "NOPE")[0] == 2


def test_exit_5_and_nothing_written_when_the_renderer_is_unavailable(world, capsys, tmp_path):
    out = tmp_path / "pv"
    code, res = verb(world, capsys, "--out", str(out), "--ids", C.P[C.MAG])
    assert code == 5 and res["renderer"] == "unavailable" and not out.exists()  # no synty_glb_root in the config
    cfg = X.write_config(world.tmp, world.cat, root=world.root, extra=[f'synty_glb_root: "{(world.tmp / "no_such").as_posix()}"'])
    code, res = verb(world, capsys, "--out", str(out), "--ids", C.P[C.MAG], cfg=cfg)
    assert code == 5 and not out.exists()


def test_the_verb_with_a_stub_renderer_writes_only_into_its_folder(world, capsys, tmp_path, monkeypatch):
    stub = StubRenderer()
    with_stub(monkeypatch, stub)
    cfg = X.write_config(world.tmp, world.cat, root=world.root, extra=[f'synty_glb_root: "{world.glb_stub.as_posix()}"'])
    out = tmp_path / "pv"
    before = sorted(p.relative_to(world.tmp).as_posix() for p in world.tmp.rglob("*") if p.is_file())
    code, res = verb(world, capsys, "--out", str(out), "--ids", C.P[C.MAG], "--size", "64", "--sheet", cfg=cfg)
    assert code == 0 and (res["rendered"], res["failed"], res["pairs"]) == (3, [], 3)
    assert len([p for p in out.iterdir() if p.suffix == ".png"]) == 4 and (out / "index.json").is_file()  # 3 pairs + sheet.png
    assert [j["host"] for j in stub.jobs] == [C.H[C.ALPHA], world.by_id[C.P[C.MAG]]["attachment"]["compatible_hosts"][1]["host"],
                                              "FAKE_Mount/SM_Wep_Rifle_Double_01"]
    after = sorted(p.relative_to(world.tmp).as_posix() for p in world.tmp.rglob("*") if p.is_file())
    assert after == before  # nothing else under the world (catalogs, packs, the directory) changed


def test_the_default_output_is_the_weapons_folder_of_the_catalogs_and_nowhere_else(world, capsys, monkeypatch):
    stub = StubRenderer()
    with_stub(monkeypatch, stub)
    cfg = X.write_config(world.tmp, world.cat, root=world.root, extra=[f'synty_glb_root: "{world.glb_stub.as_posix()}"'])
    code, res = verb(world, capsys, "--ids", C.P[C.SCOPE], "--limit", "2", "--size", "64", cfg=cfg)
    default = (Path(world.cat) / "weapons" / preview.DEFAULT_DIRNAME)
    assert code == 0 and res["out"] == default.resolve().as_posix() and res["rendered"] == 2
    assert (default / "index.json").is_file()
    for p in default.iterdir():
        p.unlink()
    default.rmdir()


@pytest.mark.parametrize("where", ["catalogs", "pack_root", "repo"])
def test_the_verb_refuses_to_write_inside_the_catalogs_a_pack_root_or_the_checkout_exit_3(world, capsys, monkeypatch, where):
    stub = StubRenderer()
    with_stub(monkeypatch, stub)
    cfg = X.write_config(world.tmp, world.cat, root=world.root, extra=[f'synty_glb_root: "{world.glb_stub.as_posix()}"'])
    repo = Path(__file__).resolve().parent.parent
    target = {"catalogs": Path(world.cat) / "elsewhere", "pack_root": world.root / "previews", "repo": repo / "tests" / "pv_out"}[where]
    if where == "repo":
        monkeypatch.setattr(export_mod, "_repo_root", lambda: repo)
    code, res = verb(world, capsys, "--out", str(target), "--ids", C.P[C.MAG], cfg=cfg)
    assert code == 3 and not target.exists() and stub.jobs == [], res


def test_size_must_be_a_multiple_of_64(world, capsys):
    code, res = verb(world, capsys, "--plan", "--size", "100")
    assert code == 2


# --- a real picture (skipped cleanly without a renderer) ----------------------------------------------------------------


def test_the_real_renderer_draws_a_non_blank_picture_of_a_placed_twin(world, tmp_path):
    from tests.test_weapons_icons import renderer_root  # noqa: PLC0415 - skips with the reason when there is no renderer

    root = renderer_root()
    pairs, _ = preview.plan_pairs(world.directory, ids={C.P[C.SCOPE]})
    pair = next(p for p in pairs if p["host"] == C.H[C.EPSILON])
    job = preview.build_job(pair, world.by_id[pair["part"]], world.by_id[pair["host"]], world.root)
    with preview.PreviewRenderer(root, gpu=False) as renderer:
        report = preview.render_pairs(renderer, [job], tmp_path / "real", 192)
        px = renderer.render_pair(job, 192)
    assert report["rendered"] == 1 and report["failed"] == []
    assert (px[..., 3] > 0).sum() > 500
    flat = preview.flatten(px)
    orange = (flat[..., 0].astype(int) - flat[..., 2].astype(int)) > 100  # the tint, not the grey host nor the blue-grey background
    grey = (np.abs(flat[..., 0].astype(int) - flat[..., 2].astype(int)) < 20) & (flat[..., 0] > 150)
    assert orange.sum() > 100 and grey.sum() > 500  # a tinted part AND an untinted host are both in the picture
    assert len({tuple(c) for c in flat.reshape(-1, 4)[::97]}) > 3  # more than a flat fill
