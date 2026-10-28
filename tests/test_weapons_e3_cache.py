"""Slice C (S11 finding 1): the host-features fit cache key carries geometry.py's code digest.

The stripped muzzle face (``mounts.stripped_muzzle_face``, E3.1 / E3.2) is computed by ``geometry.muzzle_probe``, the one A0 algorithm, and geometry.py is in
neither ``FIT_CODE_DIGESTS`` nor ``_MOUNTS_CODE_DIGEST``; the per-input fingerprint holds the mount view and a bool for the probe, not the face. An edit to
``muzzle_probe`` that moves the face but not the muzzle mount point would serve a stale ``_fit_cache.json`` record. The key therefore carries
``geometry._CODE_DIGEST`` (``geometry_code``), read when the host is built.

Every bound below is this file's own literal; the digest swap models the file edit (the code digest is a hash of the file's bytes, which a test cannot edit).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "weapons"
sys.path.insert(0, str(FIX))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load("e3_bore_meshes")

from synty_inventory.weapons import fit_geometry as FG  # noqa: E402
from synty_inventory.weapons import geometry, mounts  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

ALL_RULES = load_rules()  # build_mounts reads the shipped tables; no bound below comes from it
REAL_PROBE = geometry.muzzle_probe  # the mount's own probe stays the real one in every build: only the stripped face may differ
OTHER_DIGEST = "0" * 12


@pytest.fixture
def spies(monkeypatch):
    """``(computes, keys)``: one entry per ``fit_geometry._compute`` run and per host-features call (its ``cache_key``)."""
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
    return computes, keys


def build(tmp_path, fit):
    """The ``barrel_end`` record of the slide-face host (stripped face: the tube, OD 22 mm at (0.005, -0.003)), built with ``fit`` as the fit cache."""
    mesh = E.plain(E.slide_face())
    path = E.write_host(tmp_path / "host.glb", mesh)
    out = mounts.build_mounts(path, None, 1.0, ALL_RULES, verts=mesh[0], axes=E.AXES, probe=REAL_PROBE, host_id="host_a",
                              fit_cache=fit, fit_cache_id="host_a")
    return out["host_feats"]["slots"]["muzzle"]["barrel_end"]


def test_a_changed_geometry_code_digest_recomputes_the_host(tmp_path, monkeypatch, spies):
    computes, keys = spies
    fit: dict = {}
    build(tmp_path, fit)
    assert len(computes) == 1
    build(tmp_path, fit)
    assert len(computes) == 1  # nothing changed: a hit
    assert geometry._CODE_DIGEST != OTHER_DIGEST
    monkeypatch.setattr(geometry, "_CODE_DIGEST", OTHER_DIGEST)  # as if geometry.py had changed
    build(tmp_path, fit)
    assert len(computes) == 2
    assert keys[-1].get("geometry_code") == OTHER_DIGEST
    digest = keys[0]["geometry_code"]
    assert len(digest) == 12 and set(digest) <= set("0123456789abcdef")


def test_a_moved_stripped_face_is_not_served_from_the_cache(tmp_path, monkeypatch, spies):
    # the defect itself: muzzle_probe returns the same point and source but another face (the tube's centre moved 2 mm to the side), and geometry.py's
    # digest changes with the edit. The cached record holds the old centre; the recompute must read the new one
    computes, _keys = spies
    fit: dict = {}
    before = build(tmp_path, fit)
    assert before["centre_su"] == pytest.approx([0.005, -0.003], abs=1e-3)

    def shifted(verts, forward, up):
        point, source, face = REAL_PROBE(verts, forward, up)
        moved = face.copy()
        moved[:, 1] += 0.002  # column 1 is the side coordinate in the (f, s, u) frame the stripped probe runs in
        return point, source, moved

    monkeypatch.setattr(geometry, "muzzle_probe", shifted)
    monkeypatch.setattr(geometry, "_CODE_DIGEST", OTHER_DIGEST)
    after = build(tmp_path, fit)
    assert len(computes) == 2  # recomputed, not served
    assert after["centre_su"] == pytest.approx([0.007, -0.003], abs=1e-3)
    assert after["od_m"] == pytest.approx(before["od_m"], abs=1e-4)  # only the centre moved


def test_an_unchanged_second_build_is_a_hit(tmp_path, spies):
    # guard: the new key field does not make the cache miss when geometry.py is the same file
    computes, keys = spies
    fit: dict = {}
    first = build(tmp_path, fit)
    second = build(tmp_path, fit)
    assert len(computes) == 1
    assert keys[0] == keys[1]
    assert second == first
