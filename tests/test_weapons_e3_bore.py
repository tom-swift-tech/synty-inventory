"""E3.1 and E3.2: the barrel-face outer diameter (B) and the stripped-mesh ring evidence (W1), docs/weapon_attach_geometry_errata.md E3.1 / E3.2;
docs/weapon_attach_geometry.md 3.6 (i); AC133 (a), AC135.

Two layers.

* The pure detector and the calibrate maths are driven with a LITERAL ``fit_geometry`` block (``RULES``, this file's own copy) and a LITERAL
  ``stripped_face`` record (``{"ring", "centre_su", "od_m"}``: the shape ``mounts.stripped_muzzle_face`` returns and ``barrel_end`` reads from its ``mount``).
* The hosts of the errata fixture tables are built as one-mesh GLBs (``fixtures/weapons/e3_bore_meshes.py``) and go through ``mounts.build_mounts``, so the
  mount comes from the real probe path (``geometry.muzzle_probe`` then ``mounts.bore_diameter``), never from a hand-set ``bore_source``, and the injection
  of the stripped probe is the one the directory build runs. A fused device is a part found by translation and stripped, as on a preset.

Every expected number is a literal worked out from the dimensions in the fixture module docstring; nothing is read from the rules under test.

Deliberate breaks, on a scratch copy (reported with the slice):
* B left out (``od_m`` and ``centre_su`` from the slab for evidence (i)): ``test_slide_face_od_is_the_barrel_face`` and the block-behind fixture go red;
* B applied to (ii) and (iii) as well: ``test_evidence_ii_end_keeps_the_slab_od`` goes red;
* the unstripped probe instead of the stripped one (W1 left out): the fused-device-over-rod fixture goes red;
* W2 (a mount probe face within ``end_slab_m`` of the stripped extreme): the block-behind fixture goes red;
* no guard on a missing ring: ``test_the_stripped_face_has_no_ring_so_the_mounts_ring_does_not_hold`` goes red.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "weapons"
sys.path.insert(0, str(FIX))
import g1_bore_meshes as M  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load("e3_bore_meshes")
P = _load("g1_population_world")

from synty_inventory.weapons import calibrate as fc  # noqa: E402
from synty_inventory.weapons import fit_geometry as FG  # noqa: E402
from synty_inventory.weapons import geometry, mounts  # noqa: E402
from synty_inventory.weapons.fit_bore import barrel_end  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

# A literal copy of the spec 4.1 block (attachment_rules.fit_geometry), as test_weapons_g1_bore.py has it.
RULES = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {
        "window_m": 0.010, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005,
        "pitch_max_m": 0.040, "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85],
        "default_seat_len_m": 0.20, "sight_clear_m": 0.010,
    },
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.060},
    "clamp": {"overhang_max_m": 0.010, "ratio_min": 1.0},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {
        "end_slab_m": 0.010, "round_min": 0.8, "circ_min": 0.75, "barrel_od_max_m": 0.060, "od_ratio": [0.85, 2.00], "inner_ratio": [0.47, 1.21],
        "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2,
    },
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}
ALL_RULES = load_rules()  # build_mounts reads the shipped tables (the preset token, the child vocabulary); no bound below comes from it
NO_FACE = {"ring": False, "centre_su": None, "od_m": None}


def end_of(tmp_path, mesh, *, fused_parts=None, host_id="host_a", **kw):
    """The ``barrel_end`` record of ``mesh`` (asset axes, forward +z, up +y) as ``mounts.build_mounts`` stores it, or None."""
    path = E.write_host(tmp_path / "host.glb", mesh)
    out = mounts.build_mounts(path, None, 1.0, ALL_RULES, verts=mesh[0], axes=E.AXES, probe=geometry.muzzle_probe, host_id=host_id,
                              fused_parts=fused_parts, **kw)
    return out["host_feats"]["slots"]["muzzle"].get("barrel_end"), out


def preset_end(tmp_path, barrel):
    return end_of(tmp_path, E.fused(barrel), fused_parts=("device-parts", lambda: [E.device_part()]), host_id="preset_host_a")


def probe_source(mesh):
    """The bore source the A0 probe path gives on ``mesh`` (asset axes): what the muzzle mount of the unstripped host carries. (``build_mounts`` refuses
    the muzzle slot of a preset whose device fills it, after the features are read, so the block's own mount is not the probe's.)"""
    _point, _src, face = geometry.muzzle_probe(mesh[0], E.AXES["forward"], E.AXES["up"])
    return mounts.bore_diameter(face, 2)[1]


# -- B: the face, not the slab (E3.1) ------------------------------------------------------------------------------------


def test_slide_face_od_is_the_barrel_face(tmp_path):
    # a 60 x 30 mm block ends flush at f = 0.200; the tube (outer 22 mm, bore 15 mm) stands 3 mm proud of it, 5 mm side and -3 mm up of the block centre.
    # The slab is the block's corners (OD about 0.067, centre on the block); the barrel is the tube's end face
    end, out = end_of(tmp_path, E.plain(E.slide_face()))
    assert out["mounts"]["muzzle"]["bore_source"] == "ring"  # the mount comes from the probe path
    assert end["evidence"] == "ring"
    assert 0.021 <= end["od_m"] <= 0.023
    assert end["centre_su"] == pytest.approx([0.005, -0.003], abs=1e-3)
    assert end["face_f"] == pytest.approx(0.203, abs=1e-4)
    assert 0.024 / end["od_m"] == pytest.approx(1.09, abs=0.02)  # a 24 mm device mate over the barrel face
    assert sorted(end) == ["centre_su", "evidence", "face_f", "od_m"]  # the stored record keeps its four keys


def test_round_barrel_with_own_ring_keeps_slab_od(tmp_path):
    # guard: a 30 mm tube with its own ring and a flush end: the face is the slab
    end, out = end_of(tmp_path, E.plain(E.ringed_barrel()))
    assert out["mounts"]["muzzle"]["bore_source"] == "ring"
    assert end["evidence"] == "ring" and end["od_m"] == pytest.approx(0.030, abs=1e-4)
    assert end["centre_su"] == pytest.approx([0.0, 0.0], abs=1e-4)


def test_evidence_ii_end_keeps_the_slab_od(tmp_path):
    # guard: the A0 face holds one radius (face_extent), the 10 mm slab holds the bore ring (evidence (ii)): od_m is the slab's, no second radius is read
    end, out = end_of(tmp_path, E.plain(E.recessed_bore_barrel()))
    assert out["mounts"]["muzzle"]["bore_source"] == "face_extent"
    assert end["evidence"] == "face_ring" and end["od_m"] == pytest.approx(0.030, abs=2e-4)
    assert end["centre_su"] == pytest.approx([0.0, 0.0], abs=1e-4)


def test_barrel_end_reads_the_face_record_for_evidence_i_only():
    # the pure detector: the same slide-face mesh, the face record of the tube (OD 22 mm at (0.005, -0.003))
    mesh = E.slide_face()
    face = {"ring": True, "centre_su": [0.005, -0.003], "od_m": 0.022}
    end = barrel_end(mesh[0], mesh[1], {"bore_source": "ring", "stripped_face": face}, RULES)
    assert (end.evidence, end.od_m, end.centre_su, end.face_f) == ("ring", 0.022, (0.005, -0.003), 0.203)
    # no face record (a hand-set mount): today's slab, exactly
    slab = barrel_end(mesh[0], mesh[1], {"bore_source": "ring"}, RULES)
    assert slab.evidence == "ring" and slab.od_m == pytest.approx(0.067, abs=5e-4)
    # a mount with no ring evidence of its own: (ii) and (iii) never read the record
    rod = E.rod_barrel()
    end = barrel_end(rod[0], rod[1], {"bore_source": "face_extent", "stripped_face": {"ring": False, "centre_su": [0.1, 0.1], "od_m": 0.5}}, RULES)
    assert end.evidence == "round_section" and end.od_m == pytest.approx(0.024, abs=1e-4) and end.centre_su == pytest.approx((0.0, 0.0), abs=1e-4)


# -- W1: the stripped mesh decides evidence (i) (E3.2) -------------------------------------------------------------------


def test_fused_device_over_rod_barrel_is_round_section(tmp_path):
    # a solid 24 mm rod with a 40 mm / 12 mm device fused over its end: the mount's ring is the device's, the stripped host is the rod
    end, out = preset_end(tmp_path, E.rod_barrel())
    assert probe_source(E.fused(E.rod_barrel())) == "ring"  # the unstripped probe reads the device face
    assert [p["part"] for p in out["host_feats"]["located"]] == [E.DEVICE_PART]
    assert end["evidence"] == "round_section"
    assert 0.0235 <= end["od_m"] <= 0.0245
    assert end["face_f"] == pytest.approx(0.25, abs=1e-4)


def test_rod_barrel_without_device_is_round_section(tmp_path):
    # guard: the same rod, nothing fused
    end, out = end_of(tmp_path, E.plain(E.rod_barrel()))
    assert out["mounts"]["muzzle"]["bore_source"] == "face_extent"
    assert end["evidence"] == "round_section" and 0.0235 <= end["od_m"] <= 0.0245


def test_ringed_barrel_plus_fused_device_keeps_barrel_face_values(tmp_path):
    # guard: a barrel with its own 30 mm / 16 mm ring under the same device: (i) holds on the stripped face, the values are the barrel's
    end, _out = preset_end(tmp_path, E.ringed_barrel())
    assert probe_source(E.fused(E.ringed_barrel())) == "ring"
    assert end["evidence"] == "ring" and end["od_m"] == pytest.approx(0.030, abs=1e-4)
    assert end["centre_su"] == pytest.approx([0.0, 0.0], abs=1e-4) and end["face_f"] == pytest.approx(0.25, abs=1e-4)


def test_block_behind_barrel_plus_fused_device_ahead_reads_barrel_face_od(tmp_path):
    # a 60 x 30 mm block 5 mm behind the barrel's end (inside the slab) and the device ahead of it: the barrel face is the stripped probe's face
    end, _out = preset_end(tmp_path, E.block_behind_barrel())
    assert end["evidence"] == "ring"
    assert 0.021 <= end["od_m"] <= 0.023
    assert end["centre_su"] == pytest.approx([0.0, 0.0], abs=1e-3)


def test_the_stripped_face_has_no_ring_so_the_mounts_ring_does_not_hold():
    # the mount says ring, the stripped face has none: (i) does not hold, the end falls to (ii) and then (iii), with no error
    rod = E.rod_barrel()
    end = barrel_end(rod[0], rod[1], {"bore_source": "ring", "stripped_face": NO_FACE}, RULES)
    assert end.evidence == "round_section" and end.od_m == pytest.approx(0.024, abs=1e-4)
    recessed = E.recessed_bore_barrel()
    end = barrel_end(recessed[0], recessed[1], {"bore_source": "ring", "stripped_face": NO_FACE}, RULES)
    assert end.evidence == "face_ring" and end.od_m == pytest.approx(0.030, abs=2e-4)
    square = E.square_barrel()
    assert barrel_end(square[0], square[1], {"bore_source": "ring", "stripped_face": NO_FACE}, RULES) is None


def test_mount_ring_but_stripped_face_has_none_falls_through():
    # host_features with the injected probe: it is handed the stripped host and its answer decides (i)
    seen = []

    def probe(verts_fsu, tris):
        seen.append(len(verts_fsu))
        return NO_FACE

    rod = E.rod_barrel()
    muz = {**mounts.none_mount("x"), "source": "probe", "point": [0.0, 0.0, 0.25], "reason": None, "bore_source": "ring"}
    mnts = {"muzzle": muz, **{slot: mounts.none_mount("no_child_no_probe") for slot in ("optic", "underbarrel", "magazine")}}
    feats = FG.host_features(RULES, axes={"forward": "+x", "up": "+z"}, mounts=mnts, mesh=lambda drop: rod, child_mesh=lambda name: None,
                             stripped_probe=probe)
    end = feats["slots"]["muzzle"]["barrel_end"]
    assert seen == [len(rod[0])] and end["evidence"] == "round_section"
    # the default (no probe) is today's reading: the mount's ring
    plain = FG.host_features(RULES, axes={"forward": "+x", "up": "+z"}, mounts=mnts, mesh=lambda drop: rod, child_mesh=lambda name: None)
    assert plain["slots"]["muzzle"]["barrel_end"]["evidence"] == "ring"


def test_non_host_preset_has_no_ring_evidence():
    # guard: a preset that is no host has no muzzle mount (bore_source None): whatever a stripped face says, (i) does not hold
    tube = E.ringed_barrel()
    face = {"ring": True, "centre_su": [0.0, 0.0], "od_m": 0.030}
    end = barrel_end(tube[0], tube[1], {"bore_source": None, "stripped_face": face}, RULES)
    assert end.evidence == "face_ring"


def test_a_mount_that_found_only_a_face_extent_takes_the_stripped_ring():
    # W1: the mount has a face (a fused device's single radius), the stripped host has the barrel's ring: (i) holds, with the barrel face's values
    tube = E.ringed_barrel()
    face = {"ring": True, "centre_su": [0.001, 0.0], "od_m": 0.030}
    end = barrel_end(tube[0], tube[1], {"bore_source": "face_extent", "stripped_face": face}, RULES)
    assert (end.evidence, end.od_m, end.centre_su) == ("ring", 0.030, (0.001, 0.0))


def test_the_oracle_gives_a_preset_that_is_no_host_no_stripped_face(tmp_path_factory, monkeypatch):
    # guard: a preset with no muzzle mount (the population world's non-host preset) is calibrated with bore_source None and no stripped face
    tmp = tmp_path_factory.mktemp("e3_nonhost")
    _cat, root, directory, _excluded = P.build(tmp)
    seen = []
    real = fc.observe_positive

    def spy(pos, rules):
        seen.append(pos)
        return real(pos, rules)

    from synty_inventory.weapons import cli as wcli

    monkeypatch.setattr(fc, "observe_positive", spy)
    wcli._gather_oracle(directory, root, load_rules(), None)
    heavy = [p for p in seen if p["slot"] == "muzzle" and p["host"].endswith(P.HEAVY_PRESET)]
    assert heavy and all(p["bore_source"] is None and not p.get("stripped_face") for p in heavy)


# -- one helper for the build and the oracle ------------------------------------------------------------------------------


def test_the_helper_returns_the_ring_flag_the_face_centre_and_the_face_od():
    mesh = E.slide_face()
    got = mounts.stripped_muzzle_face(mesh[0], mesh[1])
    assert got["ring"] is True and got["od_m"] == pytest.approx(0.022, abs=5e-4)
    assert got["centre_su"] == pytest.approx([0.005, -0.003], abs=5e-4)
    rod = E.rod_barrel()
    assert mounts.stripped_muzzle_face(rod[0], rod[1])["ring"] is False
    assert mounts.stripped_muzzle_face(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)) is None


def test_oracle_and_build_share_the_stripped_probe(tmp_path_factory, monkeypatch):
    # the build and the oracle (attach-calibrate) call the one helper, on the same stripped (f, s, u) mesh, so they get the same record
    real = getattr(mounts, "stripped_muzzle_face", None)
    assert real is not None, "mounts has no stripped_muzzle_face helper"
    calls: dict[str, list] = {"build": [], "oracle": []}
    phase = ["build"]

    def spy(verts_fsu, tris=None, *args, **kw):
        got = real(verts_fsu, tris, *args, **kw)
        key = (np.asarray(verts_fsu, dtype=np.float64).tobytes(), np.asarray(tris if tris is not None else [], dtype=np.int64).tobytes())
        calls[phase[0]].append((key, json.dumps(got, sort_keys=True)))
        return got

    from synty_inventory.weapons import cli as wcli

    monkeypatch.setattr(mounts, "stripped_muzzle_face", spy)
    _cat, root, directory, _excluded = P.build(tmp_path_factory.mktemp("e3_share"))
    phase[0] = "oracle"
    wcli._gather_oracle(directory, root, load_rules(), None)
    built = dict(calls["build"])
    shared = [(key, result) for key, result in calls["oracle"] if key in built]
    assert len(shared) >= 15 and all(built[key] == result for key, result in shared)  # the same stripped mesh gives the same record
    assert any(json.loads(result)["ring"] for _key, result in shared)
    # one oracle mesh is the build's own only up to a part: the population world's preset has a muzzle brake that is a part with NO attachment block. The
    # oracle strips it (it reads the slot off the part's name, cli.fit_slot) and the directory build's fused set holds attachment parts only (directory.
    # _fused_parts_factory). That difference is in the part sets, not in the helper, and E3.1 does not touch it
    # The two part sets: the one cli._gather_oracle strips (every pack part whose name reads as a slot, an attachment-less muzzle brake included)
    # versus the one directory._fused_parts_factory fuses (only parts that carry an attachment block). The literal 1 is that known gap: it goes red the
    # day the two sets are aligned. That is intended; aligning them is a carried item, not part of this slice, so a red here is not a regression of E3.1
    assert len(calls["oracle"]) - len(shared) == 1


def test_calibrate_passes_the_face_data_into_barrel_end():
    # the pure layer: the pos carries the helper's record; observe_positive and centreline hand it to barrel_end with the mount's bore source
    mesh = E.slide_face()
    face = {"ring": True, "centre_su": [0.005, -0.003], "od_m": 0.022}
    pos = {"cls": "baked", "slot": "muzzle", "part": "part_a", "host": "host_a", "mesh": mesh, "bore_source": "ring", "seat": (0.203, 0.005, -0.003),
           "axis_fsu": (1.0, 0.0, 0.0), "mate_d_m": 0.024, "stripped_face": face}
    got = {o["key"]: o["value"] for o in fc.observe_positive(pos, RULES)}
    assert got["od_ratio"] == pytest.approx(1.09, abs=0.01) and got["axis_offset"] == pytest.approx(0.0, abs=1e-3)
    no_face = {o["key"]: o["value"] for o in fc.observe_positive({k: v for k, v in pos.items() if k != "stripped_face"}, RULES)}
    assert no_face["od_ratio"] == pytest.approx(0.36, abs=0.01)  # the slab: the old reading, for a hand-built pos
    # the mount's ring is refuted by the stripped face: no ring, a box that is not round: no barrel end, nothing to measure
    refuted = {**pos, "mesh": E.square_barrel(), "stripped_face": NO_FACE}
    assert [o["key"] for o in fc.observe_positive(refuted, RULES)] == ["unmeasured"]
    # centreline: with a barrel end the muzzle seat's side coordinate, without one the middle of the host's side extent
    box = E.square_barrel()
    whole = (box[0] + np.array([0.0, 0.1, 0.0]), box[1])  # the side extent is 0.08 .. 0.12, its middle 0.10
    assert fc.centreline(box, whole, 0.5, "ring", RULES) == pytest.approx(0.5)  # a hand-set ring: the mount's own
    assert fc.centreline(box, whole, 0.5, "ring", RULES, stripped_face=NO_FACE) == pytest.approx(0.10)
    assert fc.centreline(box, whole, 0.5, "ring", RULES, stripped_face={"ring": True, "centre_su": [0.0, 0.0], "od_m": 0.04}) == pytest.approx(0.5)


# -- the cache ------------------------------------------------------------------------------------------------------------


def test_host_features_cache_key_covers_the_probe_code(tmp_path, monkeypatch):
    # mirror of test_weapons_g1_seats.py (the fit-code cache tests): the helper's code is in neither FIT_CODE_DIGESTS nor the geometry key, so the
    # mounts code digest joins the host-features cache key; changing it recomputes the host
    computes: list[int] = []
    keys: list[dict] = []
    real = FG._compute
    real_features = FG.host_features

    def spy(rules, **kw):
        computes.append(1)
        return real(rules, **kw)

    def keyed(rules, **kw):
        keys.append(kw["cache_key"])
        return real_features(rules, **kw)

    monkeypatch.setattr(FG, "_compute", spy)
    monkeypatch.setattr(FG, "host_features", keyed)
    fit: dict = {}
    mesh = E.plain(E.slide_face())
    end_of(tmp_path, mesh, fit_cache=fit, fit_cache_id="host_a")
    assert len(computes) == 1
    # the pin; geometry_code joined in slice C / S11 finding 1 (the stripped face is geometry.muzzle_probe's, tests/test_weapons_e3_cache.py)
    assert sorted(keys[0]) == ["attach_rules_digest", "attach_version", "geometry_code", "geometry_version", "glb_node", "glb_scale", "mounts_code", "sha256"]
    digest = keys[0]["mounts_code"]
    assert len(digest) == 12 and set(digest) <= set("0123456789abcdef")
    end_of(tmp_path, mesh, fit_cache=fit, fit_cache_id="host_a")
    assert len(computes) == 1  # nothing changed: a hit
    monkeypatch.setattr(mounts, "_MOUNTS_CODE_DIGEST", "0" * 12)
    end_of(tmp_path, mesh, fit_cache=fit, fit_cache_id="host_a")
    assert len(computes) == 2
    assert keys[-1]["mounts_code"] == "0" * 12


def test_a_cache_entry_made_without_the_probe_is_not_served_to_a_call_with_it(tmp_path):
    # a hit equals a recompute: the same inputs with and without the injected probe are different results (a preset's ring), so they are kept apart
    fit: dict = {}
    mnts = {"muzzle": {**mounts.none_mount("x"), "source": "probe", "point": [0.0, 0.0, 0.25], "reason": None, "bore_source": "ring"},
            **{slot: mounts.none_mount("no_child_no_probe") for slot in ("optic", "underbarrel", "magazine")}}
    rod = E.rod_barrel()
    kw = dict(axes={"forward": "+x", "up": "+z"}, mounts=mnts, mesh=lambda drop: rod, child_mesh=lambda name: None, cache=fit, cache_id="h",
              cache_key={"sha256": "x"})
    first = FG.host_features(RULES, **kw)
    second = FG.host_features(RULES, stripped_probe=lambda v, t: NO_FACE, **kw)
    assert first["slots"]["muzzle"]["barrel_end"]["evidence"] == "ring"
    assert second["slots"]["muzzle"]["barrel_end"]["evidence"] == "round_section"
