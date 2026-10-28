"""E3.12: the well section is cut with the anchor as the twin forward correction leaves it (errata E3.12; AC133, AC136).

``directory._apply_fit_parts`` cuts a magazine part's entry section by placing the part at the host's seat with its stored anchor. ``compat.twin_forward``
(first act of ``apply_compat``) rewrites that anchor when the part twins a baked child: the forward becomes the host's, and the footprint's length and width
swap. Until E3.12 the cut ran BEFORE the correction, so a part whose prior forward was the wrong axis was cut with its length and width exchanged (and its
cache key carried the old anchor), while ``attach-calibrate`` places the part from the finished directory and read it right. The fix is the order: the
directory runs ``twin_forward`` first (``apply_compat`` repeats it and finds nothing to do).

The worlds are inline and synthetic (box meshes, FAKE packs, neutral names). Y-up, metres, +z forward, +x side; a host is the receiver block of
``fixtures/weapons/e3_well_meshes.py`` with ONE baked magazine child, a box 0.10 across (x) by 0.08 along (z) hanging from a flat top, so the host's well
reference reads (f, s) = (0.08, 0.10). The part is the same box. Its prior forward is the longer horizontal extent, +x, which is the wrong axis: the
corrected forward is +z. Every expected number is a LITERAL worked out by hand from those boxes, never read from the code under test.

Red on the old order (run on the unmodified base source before the fix): ``test_twin_section_is_cut_with_the_corrected_forward`` (the section reads
[0.10, 0.08], the verdict ``no_fit``), ``test_cache_keys_are_the_corrected_anchors`` (the carried part's key is a miss: it holds the stored, corrected anchor, a
full build keyed the prior) and the two partial-build tests (fit_digest differs). Green on both orders: the guards.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "weapons"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load("e3_well_meshes")
W, A = E.W, E.A

from synty_inventory.weapons import compat  # noqa: E402
from synty_inventory.weapons import directory as dirmod  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402

ABS = 1e-4  # stored measures are rounded to 1e-4 m

PACK_1, PACK_2 = "FAKE_E312A", "FAKE_E312B"
SEAT_AT = (0.0, 0.02, -0.03)  # the child's origin: its flat top lands 2 cm inside the receiver


def box_wide():
    """0.10 across (x) by 0.08 along (z), 0.12 tall: the child and its twin part."""
    return A.mag_box(0.05, 0.12, 0.04)


def box_taller():
    """The same footprint, 0.15 tall: a twin of nothing, so no forward evidence."""
    return A.mag_box(0.05, 0.15, 0.04)


def box_long():
    """0.08 across by 0.10 along: the prior forward (+z) is already the host's; the guard that cannot change."""
    return A.mag_box(0.04, 0.12, 0.05)


def names(n: int) -> dict:
    return {"host": f"SM_Wep_Rifle_Ord_{n:02d}", "twin": f"SM_Wep_Zulu_Mag_Ord_{n:02d}", "odd": f"SM_Wep_Zulu_Mag_OrdOdd_{n:02d}"}


def world(packs=(PACK_1, PACK_2)) -> dict:
    out = {}
    for i, pack in enumerate(packs, start=1):
        n = names(i)
        out[pack] = {
            "hosts": {n["host"]: W.host_node(n["host"], E.receiver(), [W.kid(n["host"], "Mag_Wide", box_wide(), SEAT_AT)])},
            "parts": {n["twin"]: box_wide, n["odd"]: box_taller},
        }
    return out


def pid(pack: str, name: str) -> str:
    return f"{pack}/{name}"


def build(cat, root, w, *, cache=None, **kwargs):
    """``(directory, report)``; ``kwargs`` are those of ``build_directory_report`` (``packs``, ``base``)."""
    directory, excluded, report = dirmod.build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=W.pack_settings(w), rules=W.sight_rules(), threejs_v2_dir=root,
        geometry_cache={} if cache is None else cache, **kwargs)
    return directory, excluded, report


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    """The two-pack world built once with a spy on the part pass: the directory, the sections it stored, the verdicts, and the geometry cache."""
    w = world()
    cat, root = W.write_world(tmp_path_factory.mktemp("e3_order"), w)
    sections: dict = {}
    verdicts: dict = {}
    mp = pytest.MonkeyPatch()
    real_fit, real_verdict = dirmod._apply_fit_parts, compat.pair_verdict

    def spy_fit(*a, **k):
        got = real_fit(*a, **k)
        sections.update(got)
        return got

    def spy_verdict(part, host, fit_rules, seat=None):
        got = real_verdict(part, host, fit_rules, seat)
        if part["slot"] == "magazine":
            verdicts[(part["id"], host["id"])] = got.value
        return got

    mp.setattr(dirmod, "_apply_fit_parts", spy_fit)
    mp.setattr(compat, "pair_verdict", spy_verdict)
    cache: dict = {}
    try:
        directory, excluded, report = build(cat, root, w, cache=cache)
    finally:
        mp.undo()
    return {"w": w, "cat": cat, "root": root, "directory": directory, "excluded": excluded, "report": report, "sections": sections,
            "verdicts": verdicts, "cache": cache}


def record(directory, rid):
    return next(r for r in directory["weapons"] if r["id"] == rid)


# -- the order: the section is cut with the corrected forward ---------------------------------------------------------------


def test_twin_section_is_cut_with_the_corrected_forward(made):
    # the part is 0.10 across by 0.08 along: its prior forward is +x (the longer extent), the host's is +z. The section at the seat is the host's well
    # reference, 0.08 along f by 0.10 across s (deviation 0). Cut before the correction it read [0.10, 0.08], 25 % off on both axes against well.tol 0.15
    host, twin = pid(PACK_1, names(1)["host"]), pid(PACK_1, names(1)["twin"])
    assert made["sections"][twin]["sections"][host][""] == pytest.approx([0.08, 0.10], abs=ABS)
    assert made["verdicts"][(twin, host)] == "fit"


def test_the_stored_anchor_is_the_corrected_one(made):
    # the record carries what the cut used: forward +z, length 0.08, width 0.10 (the swap of twin_forward), source `twin`
    twin = pid(PACK_1, names(1)["twin"])
    att = record(made["directory"], twin)["attachment"]
    assert att["anchor"]["forward"] == [0.0, 0.0, 1.0] and att["anchor"]["forward_source"] == "twin"
    assert (att["footprint"]["length_m"], att["footprint"]["width_m"]) == pytest.approx((0.08, 0.10), abs=ABS)


def test_a_part_with_no_twin_evidence_keeps_its_prior_forward(made):
    # guard: the correction needs a twinned child. The taller box twins nothing, keeps forward +x, and its section is 0.10 along f(=x) by 0.08 across
    host, odd = pid(PACK_1, names(1)["host"]), pid(PACK_1, names(1)["odd"])
    assert record(made["directory"], odd)["attachment"]["anchor"]["forward"] == [1.0, 0.0, 0.0]
    assert made["sections"][odd]["sections"][host][""] == pytest.approx([0.10, 0.08], abs=ABS)


def test_a_part_already_along_the_host_forward_is_unchanged(tmp_path):
    # guard: the prior forward (+z, the longer extent) is the host's: no swap, the section is the part's own 0.10 along f by 0.08 across
    host, part = "SM_Wep_Rifle_OrdLong_01", "SM_Wep_Zulu_Mag_OrdLong_01"
    w = {PACK_1: {"hosts": {host: W.host_node(host, E.receiver(), [W.kid(host, "Mag_Long", box_long(), SEAT_AT)])}, "parts": {part: box_long}}}
    cat, root = W.write_world(tmp_path, w)
    got: dict = {}
    mp = pytest.MonkeyPatch()
    real = dirmod._apply_fit_parts
    mp.setattr(dirmod, "_apply_fit_parts", lambda *a, **k: got.update(real(*a, **k)) or got)
    try:
        directory, _ex, _rep = build(cat, root, w)
    finally:
        mp.undo()
    assert got[pid(PACK_1, part)]["sections"][pid(PACK_1, host)][""] == pytest.approx([0.10, 0.08], abs=ABS)
    assert record(directory, pid(PACK_1, part))["attachment"]["anchor"]["forward"] == [0.0, 0.0, 1.0]


# -- the cache key and the partial build ------------------------------------------------------------------------------------


def well_keys(cache):
    """``{cache id: set of input fingerprints}`` of the well entries."""
    return {cid: set(entry["by_inputs"]) for cid, entry in sorted(cache.items()) if cid.startswith("well|")}


def test_cache_keys_are_the_corrected_anchors(made):
    # A carried part of a partial build holds the anchor twin_forward stored when it was built. Its well key must be the one a full build stored: a full
    # build now reads the corrected anchor too. The first pack is rebuilt (anchors re-measured, then corrected), the second carried (stored, corrected),
    # on the cache the full build filled: a miss on either computes a section, which fit_stats counts.
    cache = json.loads(json.dumps(made["cache"]))  # a copy: the module fixture's stays as built
    before = well_keys(cache)
    assert len(before) == 8  # 4 parts x 2 hosts: a section is cut on every host that has a seat, the other pack's too
    d_full = made["directory"]
    _d, _ex, report = build(made["cat"], made["root"], made["w"], cache=cache, packs=[PACK_1], base=(d_full, made["excluded"]))
    assert report["fit_stats"]["computed"] == 0, report["fit_stats"]
    assert well_keys(cache) == before  # and no new fingerprint was stored beside the old ones


@pytest.mark.parametrize("warm", [True, False])
def test_a_partial_build_reproduces_the_full_build(made, warm):
    # the directory (fit_digest, every record) of a build of one pack over the carried other is the full build's, with the full build's cache warm or
    # a cold one: the section a part is cut with does not depend on how its anchor got to the cut
    cache = json.loads(json.dumps(made["cache"])) if warm else {}
    full = made["directory"]
    got, _ex, _rep = build(made["cat"], made["root"], made["w"], cache=cache, packs=[PACK_1], base=(full, made["excluded"]))
    assert got["fit_digest"] == full["fit_digest"]
    assert got["weapons"] == full["weapons"]
    # the carried second pack, rebuilt instead, gives the same
    got2, _ex2, _rep2 = build(made["cat"], made["root"], made["w"], cache=cache, packs=[PACK_2], base=(full, made["excluded"]))
    assert got2["fit_digest"] == full["fit_digest"]
    assert got2["weapons"] == full["weapons"]
