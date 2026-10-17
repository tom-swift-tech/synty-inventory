"""Weapon directory W2e: the id-only ``forward`` and ``confidence_cap`` overrides (docs/weapon_directory.md 4.5; AC38, AC39).

Everything is synthetic. Expectations are literals worked out from the fixture meshes in make_glbs.py:

* ``shoulder_launcher``: a z-long tube x/y +-0.05, z -0.63..0.37 with the origin 63 % from the -z end, so the pivot
  rule says forward ``-z`` (butt at z -0.63, the 4-vertex end face at z 0.37 is the far end). ``shoulder_launcher_pz``
  is the same tube slid to z -0.37..0.63 (origin 37 % from -z): natively ``+z``.
* the fixture record ``FAKE_Modern/SM_Wep_Grenade_Launcher_02`` scores 0.83 from the rules alone (unmeasured); measured
  with the -z tube it loses 0.15 for the forward axis against the modern pack convention (+z), giving 0.68.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wfx = _load("wfx")
M = _load("make_glbs")
H = _load("review_helpers")

from synty_inventory.weapons import SchemaError  # noqa: E402
from synty_inventory.weapons import overrides as ovr  # noqa: E402
from synty_inventory.weapons.classify import classify  # noqa: E402
from synty_inventory.weapons.directory import build_directory_report  # noqa: E402
from synty_inventory.weapons.geometry import measure_cached, measure_weapon, measure_weapon_detail  # noqa: E402
from synty_inventory.weapons.review import write_review_page  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

LAUNCHER = "FAKE_Modern/SM_Wep_Grenade_Launcher_02"
LAUNCHER_GLB = "glb/FAKE_Modern/SM_Wep_Grenade_Launcher_02.glb"
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
MIRRORED = [[-1, 0, 0], [0, 1, 0], [0, 0, -1]]  # up +y, forward -z


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def glbs(tmp_path_factory):
    out = M.generate_all(tmp_path_factory.mktemp("glbs"))
    root = out["gun"].parent
    # a weak-belly bow (belly 0.13 < 0.15): the sign comes from the origin and is flagged forward_by_fallback
    out["bow_weak_belly"] = M.write_glb(root / "bow_weak_belly.glb", [{"name": "b", "mesh": M.bow_with_belly(0.003)}])
    return out


def launcher(glbs, rules, name="shoulder_launcher", **kw):
    return measure_weapon_detail(glbs[name], None, 1.0, "launcher", "ranged", "whole", rules, hold_class="long_gun",
                                 genre="modern", **kw)


# --- geometry: the sign ---------------------------------------------------------------------------------------------


def test_ac38_a_minus_z_launcher_with_a_plus_z_override_flips_forward_and_follows_it(glbs, rules):
    natural = launcher(glbs, rules)
    assert natural["geometry"]["axes"]["forward"] == "-z" and natural["geometry"]["axes"]["forward_source"] == "pivot"
    assert natural["geometry"]["muzzle"] == [0.0, 0.0, -0.63]  # the -z end is the muzzle while the sign says -z
    assert "axes_unexpected" in natural["reasons"]

    d = launcher(glbs, rules, forward_override="+z")
    geo = d["geometry"]
    assert geo["axes"]["forward"] == "+z" and geo["axes"]["forward_source"] == "override"
    assert geo["axes"]["up"] == "+y"
    assert geo["muzzle"] == [0.0, 0.0, 0.37]  # the end face at the +z end
    assert geo["butt"] == [0.0, 0.0, -0.63]
    assert geo["tip"] is None  # ranged
    assert geo["item_basis"] == IDENTITY
    assert d["warning"] is None
    # the pack convention is met now, so the natural measurement's reason is gone
    assert "axes_unexpected" not in d["reasons"]
    # nothing else moved: the bounds, the length and the pivot are the mesh's, not the sign's
    assert geo["bounds"] == natural["geometry"]["bounds"] and geo["length_m"] == 1.0
    assert geo["pivot_frac"] == natural["geometry"]["pivot_frac"] == 0.63


def test_ac38_the_overridden_item_basis_equals_that_of_the_same_mesh_measured_plus_z_natively(glbs, rules):
    native = launcher(glbs, rules, "shoulder_launcher_pz")["geometry"]
    assert native["axes"]["forward"] == "+z" and native["axes"]["forward_source"] == "pivot"
    flipped = launcher(glbs, rules, forward_override="+z")["geometry"]
    assert flipped["item_basis"] == native["item_basis"] == IDENTITY
    assert flipped["axes"]["forward"] == native["axes"]["forward"] and flipped["axes"]["up"] == native["axes"]["up"]


def test_an_override_equal_to_the_natural_sign_still_reports_the_source_override(glbs, rules):
    d = launcher(glbs, rules, forward_override="-z")
    assert d["geometry"]["axes"]["forward"] == "-z" and d["geometry"]["axes"]["forward_source"] == "override"
    assert d["geometry"]["item_basis"] == MIRRORED
    # judged from the final sign: an override that disagrees with the pack convention still earns the reason
    assert "axes_unexpected" in d["reasons"]


def test_an_override_can_flip_a_native_plus_z_mesh_to_minus_z_and_axes_unexpected_follows_the_final_sign(glbs, rules):
    d = launcher(glbs, rules, "shoulder_launcher_pz", forward_override="-z")
    assert d["geometry"]["axes"]["forward"] == "-z" and d["geometry"]["axes"]["forward_source"] == "override"
    assert d["geometry"]["muzzle"] == [0.0, 0.0, -0.37]
    assert "axes_unexpected" in d["reasons"]


def test_removing_the_override_restores_the_measured_sign(glbs, rules):
    with_override = launcher(glbs, rules, forward_override="+z")
    without = launcher(glbs, rules)
    explicit_none = launcher(glbs, rules, forward_override=None)
    assert with_override["geometry"]["axes"]["forward"] == "+z"
    assert without["geometry"]["axes"]["forward"] == "-z" and without["geometry"]["axes"]["forward_source"] == "pivot"
    assert json.dumps(without, sort_keys=True) == json.dumps(explicit_none, sort_keys=True)  # default = old behaviour
    assert without["warning"] is None


def test_the_override_flips_a_melee_weapons_tip_butt_and_item_basis(glbs, rules):
    d = measure_weapon_detail(glbs["sword"], None, 1.0, "sword", "melee", "whole", rules, genre="fantasy",
                              forward_override="-y")
    geo = d["geometry"]
    assert geo["axes"]["forward"] == "-y" and geo["axes"]["forward_source"] == "override"
    assert geo["tip"][1] == -0.15 and geo["butt"][1] == 0.85  # the pommel is now the tip, the apex the butt
    assert geo["item_basis"] == [[0, 0, -1], [1, 0, 0], [0, -1, 0]]
    natural = measure_weapon(glbs["sword"], None, 1.0, "sword", "melee", "whole", rules, genre="fantasy")
    assert natural["tip"][1] == 0.85 and natural["item_basis"] == [[0, 0, 1], [1, 0, 0], [0, 1, 0]]


def test_the_override_replaces_a_fallback_sign_and_drops_the_fallback_flag(glbs, rules):
    # the axe's sign comes from the end sections (forward_by_fallback)
    natural = measure_weapon_detail(glbs["axe"], None, 1.0, "axe", "melee", "whole", rules, genre="fantasy")
    assert natural["geometry"]["axes"]["forward_source"] == "section" and "forward_by_fallback" in natural["flags"]
    d = measure_weapon_detail(glbs["axe"], None, 1.0, "axe", "melee", "whole", rules, genre="fantasy",
                              forward_override="-y")
    assert d["geometry"]["axes"]["forward"] == "-y" and d["geometry"]["axes"]["forward_source"] == "override"
    assert "forward_by_fallback" not in d["flags"]


def test_a_bow_takes_the_override_when_the_axis_matches(glbs, rules):
    args = (glbs["bow_weak_belly"], None, 1.0, "bow", "ranged", "whole", rules)
    natural = measure_weapon_detail(*args, genre="fantasy")
    assert natural["geometry"]["axes"]["forward"] == "+z" and natural["geometry"]["axes"]["forward_source"] == "bow_rule"
    assert "forward_by_fallback" in natural["flags"]
    d = measure_weapon_detail(*args, genre="fantasy", forward_override="-z")
    assert d["geometry"]["axes"]["forward"] == "-z" and d["geometry"]["axes"]["forward_source"] == "override"
    assert d["geometry"]["axes"]["up"] == "+y" and d["geometry"]["item_basis"] == MIRRORED
    assert "forward_by_fallback" not in d["flags"] and d["warning"] is None
    # the bow's forward axis is its depth axis (z), not its long axis (y): a +y override is the wrong axis
    wrong = measure_weapon_detail(*args, genre="fantasy", forward_override="+y")
    assert wrong["geometry"]["axes"]["forward"] == "+z" and wrong["warning"] is not None
    # a clear belly (a decided bow) is overridable too
    clear = measure_weapon_detail(glbs["bow"], None, 1.0, "bow", "ranged", "whole", rules, genre="fantasy",
                                  forward_override="-z")
    assert clear["geometry"]["axes"]["forward"] == "-z" and clear["geometry"]["axes"]["forward_source"] == "override"


def test_a_shield_takes_the_override_when_the_axis_matches(glbs, rules):
    args = (glbs["shield"], None, 1.0, "shield", "shield", "whole", rules)
    assert measure_weapon_detail(*args, genre="fantasy")["geometry"]["axes"]["forward"] == "+z"
    d = measure_weapon_detail(*args, genre="fantasy", forward_override="-z")
    assert d["geometry"]["axes"]["forward"] == "-z" and d["geometry"]["axes"]["forward_source"] == "override"
    assert d["geometry"]["axes"]["up"] == "+y" and d["geometry"]["item_basis"] == MIRRORED
    wrong = measure_weapon_detail(*args, genre="fantasy", forward_override="+y")  # y is the shield's up axis
    assert wrong["geometry"]["axes"]["forward"] == "+z" and wrong["geometry"]["axes"]["forward_source"] == "shield_rule"
    assert wrong["warning"] is not None


def test_ac38_an_override_on_the_wrong_axis_is_not_applied_and_warns(glbs, rules):
    natural = launcher(glbs, rules)
    d = launcher(glbs, rules, forward_override="+x")  # the tube is z-long
    assert d["warning"] is not None and "'+x'" in d["warning"] and "ignored" in d["warning"]
    assert d["geometry"] == natural["geometry"] and d["flags"] == natural["flags"] and d["reasons"] == natural["reasons"]
    assert d["geometry"]["axes"]["forward_source"] == "pivot"


def test_an_unmeasurable_mesh_ignores_the_override(glbs, rules):
    d = measure_weapon_detail(glbs["garbage"], None, 1.0, "sword", "melee", "whole", rules, forward_override="+y")
    assert d["geometry"] is None and "no_geometry" in d["reasons"]


# --- geometry: the cache --------------------------------------------------------------------------------------------


def _cached(glbs, rules, cache, override):
    return measure_cached(glbs["shoulder_launcher"].parent, "shoulder_launcher.glb", None, 1.0, "launcher", "ranged",
                          "whole", rules, cache, hold_class="long_gun", genre="modern", forward_override=override)


@pytest.mark.parametrize("order", [(None, "+z"), ("+z", None), ("+z", "-z"), ("-z", "+z")])
def test_ac38_the_cache_never_serves_a_result_measured_for_another_override(glbs, rules, order):
    first_override, second_override = order
    cache: dict = {}
    first, was = _cached(glbs, rules, cache, first_override)
    assert was is False
    second, was = _cached(glbs, rules, cache, second_override)
    assert was is False  # a different override value is a different cache entry
    want = {None: "-z", "+z": "+z", "-z": "-z"}
    assert first["geometry"]["axes"]["forward"] == want[first_override]
    assert second["geometry"]["axes"]["forward"] == want[second_override]
    assert first["geometry"]["axes"]["forward_source"] == ("pivot" if first_override is None else "override")
    assert second["geometry"]["axes"]["forward_source"] == ("pivot" if second_override is None else "override")
    # both are kept in one entry, and each is served from the cache to its own override only
    assert len(cache["shoulder_launcher.glb"]["by_inputs"]) == 2
    again_first, was1 = _cached(glbs, rules, cache, first_override)
    again_second, was2 = _cached(glbs, rules, cache, second_override)
    assert was1 is True and was2 is True
    assert again_first == first and again_second == second


def test_a_cache_hit_returns_the_wrong_axis_warning_too(glbs, rules):
    cache: dict = {}
    first, _ = _cached(glbs, rules, cache, "+x")
    hit, was = _cached(glbs, rules, cache, "+x")
    assert was is True and hit["warning"] == first["warning"] and "'+x'" in hit["warning"]


def test_a_natural_cache_entry_is_keyed_as_before_the_override_existed(glbs, rules):
    cache: dict = {}
    _cached(glbs, rules, cache, None)
    natural_keys = set(cache["shoulder_launcher.glb"]["by_inputs"])
    _cached(glbs, rules, cache, "+z")
    both = set(cache["shoulder_launcher.glb"]["by_inputs"])
    assert len(natural_keys) == 1 and len(both) == 2 and natural_keys < both
    # a fresh cache built natural-only has exactly the natural key (an on-disk cache stays valid)
    fresh: dict = {}
    _cached(glbs, rules, fresh, None)
    assert set(fresh["shoulder_launcher.glb"]["by_inputs"]) == natural_keys


def test_the_override_did_not_bump_the_geometry_version_past_the_w2f_bump():
    import synty_inventory.weapons as pkg

    # 2 -> 3 is W2d's melee grip, 3 -> 4 is W2f's butt inset and head-forward sign; the override added no bump of its own
    assert pkg.WEAPON_GEOMETRY_VERSION == 4


# --- the build ------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w2e")
    cat = wfx.make_catalogs_dir(tmp)
    root = tmp / "threejs"
    # only the launcher has a file: the -z tube. Every other record stays unmeasured (no file on disk)
    M.write_glb(root / LAUNCHER_GLB, [{"name": "launcher", "mesh": M.shoulder_launcher()},
                                      {"name": "SM_Fixture_Collision", "mesh": M.box((-1, -1, -1), (1, 1, 1))}])
    return {"cat": cat, "root": root}


def build(world, ids=None, **kw):
    kw.setdefault("threejs_v2_dir", world["root"])
    kw.setdefault("geometry_cache", {})
    return build_directory_report(world["cat"], overrides=wfx.overrides_doc(ids=ids), pack_settings=wfx.pack_settings(),
                                  **kw)


def launcher_record(directory):
    return wfx.records_by_id(directory)[LAUNCHER]


def test_the_build_without_an_override_measures_the_minus_z_tube_naturally(world):
    directory, _, report = build(world)
    rec = launcher_record(directory)
    assert rec["geometry"]["axes"]["forward"] == "-z" and rec["geometry"]["axes"]["forward_source"] == "pivot"
    assert "axes_unexpected" in rec["review"]["reasons"]
    assert rec["review"]["confidence"] == 0.68  # 0.83 - 0.15
    assert report["warnings"] == [] or all("override" not in w for w in report["warnings"])


def test_ac38_the_build_applies_the_override_end_to_end(world):
    directory, _, report = build(world, {LAUNCHER: {"forward": "+z"}})
    rec = launcher_record(directory)
    geo = rec["geometry"]
    assert geo["axes"]["forward"] == "+z" and geo["axes"]["forward_source"] == "override"
    assert geo["muzzle"] == [0.0, 0.0, 0.37] and geo["item_basis"] == IDENTITY
    assert "axes_unexpected" not in rec["review"]["reasons"]
    assert rec["review"]["confidence"] == 0.83  # the forward penalty went with the reason
    assert rec["review"]["status"] == "auto" and rec["provenance"]["archetype"] == "rules"
    assert not any("override" in w for w in report["warnings"])
    assert rec["flags"] == launcher_record(build(world)[0])["flags"]  # the override adds and removes no flag here


def test_ac38_a_wrong_axis_override_lands_in_the_report_warnings_and_is_not_applied(world):
    directory, _, report = build(world, {LAUNCHER: {"forward": "+x"}})
    rec = launcher_record(directory)
    assert rec["geometry"]["axes"]["forward"] == "-z" and rec["geometry"]["axes"]["forward_source"] == "pivot"
    mine = [w for w in report["warnings"] if w.startswith(f"{LAUNCHER}: ")]
    assert len(mine) == 1 and "'+x'" in mine[0] and "ignored" in mine[0]


def test_ac38_a_warm_shared_cache_is_never_cross_served_between_builds(world):
    cache: dict = {}
    natural, _, _ = build(world, geometry_cache=cache)
    over, _, rep = build(world, {LAUNCHER: {"forward": "+z"}}, geometry_cache=cache)
    assert launcher_record(natural)["geometry"]["axes"]["forward"] == "-z"
    assert launcher_record(over)["geometry"]["axes"]["forward"] == "+z"
    assert rep["geometry_stats"]["cached"] == 0  # the override is a new entry: nothing was served from the natural one
    back, _, rep2 = build(world, geometry_cache=cache)
    assert launcher_record(back)["geometry"]["axes"]["forward"] == "-z"  # removing the override restores the sign
    assert launcher_record(back)["geometry"]["axes"]["forward_source"] == "pivot"
    assert rep2["geometry_stats"]["cached"] == 1  # the launcher: its natural entry is still there
    assert json.dumps(back, sort_keys=True) == json.dumps(natural, sort_keys=True)


def test_changing_only_the_forward_value_changes_the_overrides_digest_and_a_rebuild_picks_it_up(world):
    cache: dict = {}
    plus, _, _ = build(world, {LAUNCHER: {"forward": "+z"}}, geometry_cache=cache)
    minus, _, _ = build(world, {LAUNCHER: {"forward": "-z"}}, geometry_cache=cache)
    none, _, _ = build(world, {LAUNCHER: {"note": "n"}}, geometry_cache=cache)
    assert len({plus["overrides_digest"], minus["overrides_digest"], none["overrides_digest"]}) == 3
    assert launcher_record(plus)["geometry"]["axes"]["forward"] == "+z"
    assert launcher_record(minus)["geometry"]["axes"]["forward"] == "-z"
    assert launcher_record(minus)["geometry"]["axes"]["forward_source"] == "override"
    assert launcher_record(none)["geometry"]["axes"]["forward_source"] == "pivot"
    # and the confidence cap alone changes the digest too
    capped, _, _ = build(world, {LAUNCHER: {"confidence_cap": 0.5}}, geometry_cache=cache)
    assert capped["overrides_digest"] not in {plus["overrides_digest"], minus["overrides_digest"], none["overrides_digest"]}


def test_every_measurement_of_a_record_gets_the_override(world, monkeypatch):
    # the pass-2 re-measure loop calls measure_cached again; it must carry the override each time
    import synty_inventory.weapons.directory as D

    seen: list[tuple[str, str | None]] = []
    real = D.measure_cached

    def spy(root, glb, *a, **kw):
        seen.append((glb, kw.get("forward_override")))
        return real(root, glb, *a, **kw)

    monkeypatch.setattr(D, "measure_cached", spy)
    build(world, {LAUNCHER: {"forward": "+z"}})
    assert (LAUNCHER_GLB, "+z") in seen
    assert {ov for glb, ov in seen if glb == LAUNCHER_GLB} == {"+z"}
    assert {ov for glb, ov in seen if glb != LAUNCHER_GLB} == {None}  # other records are not touched
    seen.clear()
    build(world)
    assert {ov for _, ov in seen} == {None}


def test_a_forward_only_entry_is_not_a_set_or_a_confirm(world):
    directory, excluded, _ = build(world, {LAUNCHER: {"forward": "+z"}})
    rec = launcher_record(directory)
    assert rec["review"]["status"] == "auto" and rec["review"]["confidence"] == 0.83
    # it also declares no weapon the patterns missed: a rejected id with a forward entry stays excluded
    gone = next(e for e in build(world)[1]["excluded"] if e["reason"] != "override")
    directory2, excluded2, _ = build(world, {gone["id"]: {"forward": "+z", "confidence_cap": 0.5}})
    assert gone["id"] in {e["id"] for e in excluded2["excluded"]}
    assert gone["id"] not in {w["id"] for w in directory2["weapons"]}


# --- confidence_cap -------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cat(tmp_path_factory):
    return wfx.make_catalogs_dir(tmp_path_factory.mktemp("caps"))


def _rec(cat, ids, rec_id=LAUNCHER):
    directory, _ = wfx.build(cat, measure=False, overrides=wfx.overrides_doc(ids=ids))
    return wfx.records_by_id(directory)[rec_id]


def test_ac39_a_cap_of_0_55_on_a_record_that_scores_0_83_gives_0_55_and_low_confidence(cat):
    plain = _rec(cat, {})
    assert plain["review"]["confidence"] == 0.83 and "low_confidence" not in plain["review"]["reasons"]
    capped = _rec(cat, {LAUNCHER: {"confidence_cap": 0.55}})
    assert capped["review"]["confidence"] == 0.55
    assert "low_confidence" in capped["review"]["reasons"]
    assert capped["review"]["status"] == "auto"  # a cap is not a set or a confirm
    assert capped["archetype"] == plain["archetype"] and capped["role"] == plain["role"]


def test_ac39_the_capped_record_lands_in_the_review_pages_low_confidence_section(tmp_path):
    cat = H.make_catalogs(tmp_path)
    ids = {LAUNCHER: {"confidence_cap": 0.55}}
    directory, excluded = H.build_and_write(cat, overrides=wfx.overrides_doc(ids=ids))
    wdir = cat / "weapons"
    text = write_review_page(directory, wdir / "review", excluded=excluded, base_dir=wdir).read_text(encoding="utf-8")
    start = text.index('id="sec-low"')
    low = text[start:text.index("<section", start + 1)]
    assert f'data-id="{LAUNCHER}"' in low
    # and without the cap it is a normal-confidence tile outside the section
    plain, plain_excl = H.build_and_write(cat, overrides=wfx.overrides_doc())
    text2 = write_review_page(plain, wdir / "review2", excluded=plain_excl, base_dir=wdir).read_text(encoding="utf-8")
    start2 = text2.index('id="sec-low"')
    assert f'data-id="{LAUNCHER}"' not in text2[start2:text2.index("<section", start2 + 1)]


def test_a_cap_never_raises_a_confidence_that_is_already_lower(cat):
    low_id = "FAKE_SciFi/SM_Wep_Mystery_01"
    got = _rec(cat, {low_id: {"confidence_cap": 0.59}}, low_id)
    assert got["review"]["confidence"] == 0.2  # the rules' unknown-weapon floor, below the cap
    assert _rec(cat, {LAUNCHER: {"confidence_cap": 0.59}})["review"]["confidence"] == 0.59


def test_the_cap_also_lowers_a_set_or_confirm_overrides_one_point_zero_without_changing_the_status(cat):
    both = _rec(cat, {LAUNCHER: {"set": {"genre": "scifi"}, "confidence_cap": 0.4}})
    assert both["review"]["status"] == "overridden" and both["review"]["confidence"] == 0.4
    assert "low_confidence" in both["review"]["reasons"]
    confirmed = _rec(cat, {LAUNCHER: {"confirm": True, "confidence_cap": 0.4}})
    assert confirmed["review"]["status"] == "reviewed" and confirmed["review"]["confidence"] == 0.4
    no_cap = _rec(cat, {LAUNCHER: {"confirm": True}})
    assert no_cap["review"]["status"] == "reviewed" and no_cap["review"]["confidence"] == 1.0


def test_classify_applies_the_cap_after_the_measured_penalties(rules):
    asset = wfx.catalog_assets()[LAUNCHER][1]
    measured = {"length_m": 1.0, "forward_by_fallback": False, "axes_unexpected": True}
    doc = wfx.overrides_doc(ids={LAUNCHER: {"confidence_cap": 0.65}})  # above the 0.68 but irrelevant: 0.65 wins
    cls = classify(asset, "FAKE_Modern", rules, doc, wfx.pack_settings()["FAKE_Modern"], measured=measured)
    assert cls["confidence"] == 0.65 and "low_confidence" not in cls["reasons"]
    assert classify(asset, "FAKE_Modern", rules, wfx.overrides_doc(), wfx.pack_settings()["FAKE_Modern"],
                    measured=measured)["confidence"] == 0.68


# --- schema (exit 6) ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("entry", [
    {"confidence_cap": 0.6}, {"confidence_cap": 0.7}, {"confidence_cap": 1}, {"confidence_cap": True},
    {"confidence_cap": 0.049}, {"forward": "z"}, {"forward": "+w"},
])
def test_ac39_an_out_of_range_or_malformed_value_on_an_id_is_a_schema_error_exit_6(entry):
    doc = wfx.overrides_doc(ids={LAUNCHER: entry})
    with pytest.raises(SchemaError) as exc:
        ovr.checked_overrides(doc)
    assert exc.value.code == 6
    assert next(iter(entry)) in str(exc.value)


@pytest.mark.parametrize("entry", [{"forward": "+z"}, {"confidence_cap": 0.55}, {"forward": "+z", "confidence_cap": 0.5}])
def test_ac39_a_glob_entry_carrying_either_field_is_a_schema_error_exit_6(entry):
    doc = wfx.overrides_doc(globs={"FAKE_Modern/SM_Wep_Grenade_*": entry})
    with pytest.raises(SchemaError) as exc:
        ovr.checked_overrides(doc)
    assert exc.value.code == 6
    assert "exact ids only" in str(exc.value) and "FAKE_Modern/SM_Wep_Grenade_*" in str(exc.value)


def test_the_edges_of_the_cap_range_are_accepted():
    for cap in (0.05, 0.59, 0.3):
        ovr.checked_overrides(wfx.overrides_doc(ids={LAUNCHER: {"confidence_cap": cap, "forward": "-x"}}))
