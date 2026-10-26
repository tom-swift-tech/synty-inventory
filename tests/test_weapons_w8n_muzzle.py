"""W8n item 4: the silencer seat, ``seat_setback_m`` (docs/weapon_attachments.md 13.7 A6-2).

A suppressor's pair on a host with a probe muzzle seat and nothing baked on it gets ``seat_setback_m`` = how far the part sits back over the host's
exposed muzzle end (along the bore, toward the host), from the host's silhouette near the tip:

    d = min(stub, max(cover * L, dev_rear_near + device_cover_m), max_frac * L)      L = the part's footprint height_m; d <= dead_m: no key

``stub`` is the bare shroud behind the tip, ``dev_rear_near`` the rear face of a device (a brake) within ``device_reach_m`` of the tip.
Fixtures: ``w8n_world.muzzle_world`` (see its header for the hand-worked distances). The silhouette is read in 2 mm bins, so a number worked out
by hand carries a tolerance of one bin (0.002); the exact values the build writes are asserted separately where they are stable.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8n_world", FIX / "w8n_world.py")
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)
W = N.W

from synty_inventory.weapons import attach, directory as dirmod, geometry as geo, preview, review  # noqa: E402
from synty_inventory.weapons.attach import place  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import attach_rules_digest, attachment_rules, load_rules, validate_rules, weapon_rules_digest  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

BIN = 0.002
SPEC_TABLE = {
    "cover": 0.4, "device_cover_m": 0.005, "device_reach_m": 0.080, "max_frac": 0.75, "dead_m": 0.003, "window_m": 0.15, "bin_m": 0.002,
    "ref_ratio": 1.4, "run_min_bins": 3, "device_max_m": 0.045, "sample_pitch_m": 0.0015, "range_m": 0.30, "radius_cap_m": 0.035,
}


def test_the_shipped_table_is_the_specified_one():
    assert attachment_rules(load_rules())["muzzle_seat"] == SPEC_TABLE
    assert validate_rules(load_rules()) == []


# -- the build --------------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, excluded, cat, root = W.build(tmp_path_factory.mktemp("w8n_muzzle"), N.muzzle_world(), overrides=N.muzzle_overrides())
    return SimpleNamespace(directory=directory, excluded=excluded, by_id=W.by_id(directory), root=root, cat=cat)


def entry(built, part, host, pack=N.PACK):
    att = built.by_id[N.pid(part, pack)]["attachment"]
    return next(e for e in att["compatible_hosts"] if e["host"] == N.pid(host))


def setback(built, part, host, pack=N.PACK):
    return entry(built, part, host, pack).get("seat_setback_m")


def test_the_fixture_is_what_the_comments_say(built):
    for host in (N.SH_BARE, N.SH_SHROUD, N.SH_BRAKE, N.SH_FAR):
        m = built.by_id[N.pid(host)]["geometry"]["mounts"]["muzzle"]
        assert m["source"] == "probe" and m["point"] == [0.0, 0.046, 0.65] and m["up"] == [0.0, 0.0, 1.0] and m["occupied_by"] == []
    for host in (N.SH_BAKED, N.SH_TWIN):
        assert built.by_id[N.pid(host)]["geometry"]["mounts"]["muzzle"]["occupied_by"] != []
    assert built.by_id[N.pid(N.SILENCER)]["attachment"]["footprint"]["height_m"] == 0.2
    assert built.by_id[N.pid(N.SILENCER_SHORT)]["attachment"]["footprint"]["height_m"] == 0.12


def test_a_bare_barrel_has_no_key(built):
    assert "seat_setback_m" not in entry(built, N.SILENCER, N.SH_BARE) and "seat_setback_m" not in entry(built, N.SILENCER_SHORT, N.SH_BARE)


def test_a_shroud_stub_caps_the_long_silencer_and_cover_decides_the_short_one(built):
    # the shroud's front face is 61 mm behind the tip: stub 0.061 (the 2 mm bins read 0.062)
    # L 0.2: min(0.061, max(0.4 * 0.2 = 0.08, 0.005), 0.75 * 0.2 = 0.15) = 0.061: the stub is the smallest
    assert setback(built, N.SILENCER, N.SH_SHROUD) == pytest.approx(0.061, abs=BIN)
    # L 0.12: min(0.061, max(0.048, 0.005), 0.09) = 0.048: the cover is the smallest
    assert setback(built, N.SILENCER_SHORT, N.SH_SHROUD) == pytest.approx(0.048, abs=1e-9)


def test_a_brake_near_the_tip_lifts_the_seat_over_the_device(built):
    # brake rear face 55 mm behind the tip (inside the 80 mm reach), the shroud 101 mm: stub 0.101, dev_rear_near 0.055
    # L 0.2: min(0.101, max(0.08, 0.055 + 0.005 = 0.060), 0.15) = 0.080
    assert setback(built, N.SILENCER, N.SH_BRAKE) == pytest.approx(0.080, abs=1e-9)
    # L 0.12: min(0.101, max(0.048, 0.060), 0.09) = 0.060: the device decides, and the part's rear end clears the brake's rear face by the 5 mm cover
    assert setback(built, N.SILENCER_SHORT, N.SH_BRAKE) == pytest.approx(0.060, abs=BIN)
    assert setback(built, N.SILENCER_SHORT, N.SH_BRAKE) >= 0.055 + 0.005 - 1e-9


def test_a_device_beyond_the_reach_is_not_a_brake_of_the_tip(built):
    # the only device's front face is 121 mm behind the tip (rear face 145 mm), past the 80 mm reach: dev_rear_near 0, so the cover decides
    assert setback(built, N.SILENCER, N.SH_FAR) == pytest.approx(0.080, abs=1e-9)
    assert setback(built, N.SILENCER_SHORT, N.SH_FAR) == pytest.approx(0.048, abs=1e-9)


def test_the_values_are_rounded_to_a_tenth_of_a_millimetre(built):
    got = [e["seat_setback_m"] for r in built.directory["weapons"] if r.get("attachment") for e in r["attachment"]["compatible_hosts"]
           if "seat_setback_m" in e]
    assert len(got) == 6 and all(v == round(v, 4) and 0.003 < v <= 0.2 for v in got)


def test_the_exact_values_of_the_fixture_are_stable(built):
    assert [setback(built, N.SILENCER, h) for h in (N.SH_SHROUD, N.SH_BRAKE, N.SH_FAR)] == [0.062, 0.08, 0.08]
    assert [setback(built, N.SILENCER_SHORT, h) for h in (N.SH_SHROUD, N.SH_BRAKE, N.SH_FAR)] == [0.048, 0.061, 0.048]


# -- which entries get the key ----------------------------------------------------------------------------------------------


def test_a_host_with_a_baked_silencer_gets_no_key_for_a_part_that_replaces_it(built):
    e = entry(built, N.SILENCER, N.SH_BAKED)
    assert e["tier"] == "same_pack_fit" and e["replaces"] == [f"{N.SH_BAKED}_Silencer"] and "seat_setback_m" not in e


def test_a_twin_entry_has_no_key(built):
    assert entry(built, N.SILENCER, N.SH_TWIN)["tier"] == "twin" and "seat_setback_m" not in entry(built, N.SILENCER, N.SH_TWIN)
    assert entry(built, N.SILENCER_SHORT, N.SH_BAKED)["tier"] == "twin" and "seat_setback_m" not in entry(built, N.SILENCER_SHORT, N.SH_BAKED)


def test_an_override_entry_has_no_key_though_the_shroud_would_give_one(built):
    e = entry(built, N.SILENCER_X, N.SH_SHROUD, N.OTHER)
    assert e["tier"] == "override" and "seat_setback_m" not in e
    assert setback(built, N.SILENCER, N.SH_SHROUD) is not None  # the same host does key a natural pair


def test_only_the_suppressors_of_the_muzzle_slot_are_keyed(built):
    for rec in built.directory["weapons"]:
        att = rec.get("attachment") or {}
        if att.get("slot") != "muzzle" or att.get("kind") != "suppressor":
            assert not [e for e in att.get("compatible_hosts") or [] if "seat_setback_m" in e], rec["id"]


@pytest.mark.parametrize(("slot", "kind", "tier", "mount", "want"), [
    ("muzzle", "suppressor", "same_pack_fit", {"source": "probe", "occupied_by": [], "child_node": None, "point": [0, 0, 1], "up": [0, 0, 1]}, True),
    ("muzzle", "suppressor", "cross_pack_fit", {"source": "probe", "occupied_by": [], "child_node": None, "point": [0, 0, 1], "up": [0, 0, 1]}, True),
    ("muzzle", "brake", "same_pack_fit", {"source": "probe", "occupied_by": [], "child_node": None, "point": [0, 0, 1], "up": [0, 0, 1]}, False),
    ("optic", "suppressor", "same_pack_fit", {"source": "probe", "occupied_by": [], "child_node": None, "point": [0, 0, 1], "up": [0, 0, 1]}, False),
    ("muzzle", "suppressor", "twin", {"source": "probe", "occupied_by": [], "child_node": None, "point": [0, 0, 1], "up": [0, 0, 1]}, False),
    ("muzzle", "suppressor", "override", {"source": "probe", "occupied_by": [], "child_node": None, "point": [0, 0, 1], "up": [0, 0, 1]}, False),
    ("muzzle", "suppressor", "same_pack_fit", {"source": "probe", "occupied_by": ["X"], "child_node": None, "point": [0, 0, 1], "up": [0, 0, 1]}, False),
    ("muzzle", "suppressor", "same_pack_fit", {"source": "child_node", "occupied_by": [], "child_node": "X", "point": [0, 0, 1], "up": [0, 0, 1]}, False),
    ("muzzle", "suppressor", "same_pack_fit", {"source": "none", "occupied_by": [], "child_node": None, "point": None, "up": None}, False),
    ("muzzle", "suppressor", "same_pack_fit", None, False),
])
def test_which_pairs_are_keyed(slot, kind, tier, mount, want):
    assert attach.setback_applies(slot, kind, tier, mount) is want


# -- the rule on hand-built numbers -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("stub", "dev", "length", "want"), [
    (0.061, 0.0, 0.2, 0.061),      # the stub is the smallest
    (0.30, 0.0, 0.2, 0.08),        # cover: 0.4 * 0.2
    (0.30, 0.0, 0.12, 0.048),
    (0.30, 0.055, 0.12, 0.06),     # device: 0.055 + 0.005
    (0.30, 0.10, 0.12, 0.09),      # capped at 0.75 * 0.12
    (0.003, 0.0, 0.2, None),       # at the dead zone: no key
    (0.0031, 0.0, 0.2, 0.0031),
    (0.0, 0.0, 0.2, None),
])
def test_the_rule_on_numbers(stub, dev, length, want):
    assert attach.setback_of(stub, dev, length, SPEC_TABLE) == want


def test_the_rule_is_parametrised_by_the_table():
    assert attach.setback_of(0.30, 0.0, 0.2, dict(SPEC_TABLE, cover=0.5)) == 0.1
    assert attach.setback_of(0.30, 0.0, 0.2, dict(SPEC_TABLE, max_frac=0.3)) == 0.06
    assert attach.setback_of(0.30, 0.0, 0.2, dict(SPEC_TABLE, dead_m=0.1)) is None


# -- placement, export, review -----------------------------------------------------------------------------------------------


def job(built, part, host, entry_override=None):
    p, h = built.by_id[N.pid(part)], built.by_id[N.pid(host)]
    e = entry(built, part, host)
    pair = {"part": p["id"], "host": h["id"], "slot": p["attachment"]["slot"], "tier": e["tier"], "score": e["score"], "twin": e["tier"] == "twin"}
    return preview.build_job(pair, p, h, built.root)


def test_the_preview_moves_the_part_back_along_the_bore_by_the_key(built):
    p, h = built.by_id[N.pid(N.SILENCER)], built.by_id[N.pid(N.SH_BRAKE)]
    mount = h["geometry"]["mounts"]["muzzle"]
    want = np.eye(4)
    want[:3, 3] = -0.08 * np.asarray(mount["up"])
    want = want @ place(p["attachment"]["anchor"], mount)
    got = np.asarray(job(built, N.SILENCER, N.SH_BRAKE)["matrix"])
    assert np.allclose(got, want, atol=1e-9)
    assert np.allclose(got[:3, 3], [0.0, 0.046, 0.57], atol=1e-9)  # the anchor (the mating end) at the tip z 0.65 minus 0.08


def test_an_entry_without_the_key_is_placed_exactly_as_place_does(built):
    p, h = built.by_id[N.pid(N.SILENCER)], built.by_id[N.pid(N.SH_BARE)]
    got = job(built, N.SILENCER, N.SH_BARE)["matrix"]
    assert np.array_equal(np.asarray(got), np.asarray(place(p["attachment"]["anchor"], h["geometry"]["mounts"]["muzzle"])))
    assert np.allclose(np.asarray(got)[:3, 3], [0.0, 0.046, 0.65], atol=1e-9)


def test_the_review_page_shows_the_key_on_the_host_row_only_when_there_is_one(built):
    data = review._attach_entry(built.by_id[N.pid(N.SILENCER)], {})
    rows = {h["host"].split("/", 1)[1]: h for h in data["hosts"]}
    assert rows[N.SH_BRAKE]["seat_setback_m"] == 0.08 and rows[N.SH_SHROUD]["seat_setback_m"] == 0.062
    assert "seat_setback_m" not in rows[N.SH_BARE] and "seat_setback_m" not in rows[N.SH_TWIN]


def test_the_directory_with_the_keys_validates(built):
    assert validate_directory(built.directory, built.excluded) == []


def bad_directory(built, edit):
    doc = deepcopy(built.directory)
    edit({w["id"]: w for w in doc["weapons"]})
    return validate_directory(doc, built.excluded)


def set_key(part, host, value, pack=N.PACK):
    def edit(recs):
        for e in recs[N.pid(part, pack)]["attachment"]["compatible_hosts"]:
            if e["host"] == N.pid(host):
                e["seat_setback_m"] = value
    return edit


@pytest.mark.parametrize("value", [0.0, -0.01, 0.2001, 0.5, "0.05", None, True])
def test_the_schema_refuses_a_key_that_is_not_a_positive_number_up_to_20_cm(built, value):
    errors = bad_directory(built, set_key(N.SILENCER, N.SH_SHROUD, value))
    assert errors and any("attachment" in e for e in errors), (value, errors)  # the directory validates without the edit (above): the edit is the cause


@pytest.mark.parametrize("value", [0.0001, 0.05, 0.2])
def test_the_schema_accepts_a_key_from_a_tenth_of_a_millimetre_to_20_cm(built, value):
    assert bad_directory(built, set_key(N.SILENCER, N.SH_SHROUD, value)) == []


def test_the_schema_refuses_the_key_on_a_twin_or_override_entry(built):
    for part, host, pack in ((N.SILENCER, N.SH_TWIN, N.PACK), (N.SILENCER_X, N.SH_SHROUD, N.OTHER)):
        errors = bad_directory(built, set_key(part, host, 0.05, pack))
        assert any("seat_setback_m is never on a twin or override entry" in e for e in errors), (part, errors)
        assert bad_directory(built, set_key(part, host, 0.2, pack)) != [] and bad_directory(built, set_key(part, host, 0.0, pack)) != []


def test_the_schema_refuses_the_key_on_a_part_that_is_not_a_muzzle_suppressor(built):
    def edit(recs):
        recs[N.pid(N.SILENCER)]["attachment"]["kind"] = "brake"
    errors = bad_directory(built, edit)
    assert any("seat_setback_m is for suppressor entries of the muzzle slot only" in e for e in errors), errors


# -- the cache ----------------------------------------------------------------------------------------------------------------


@pytest.fixture()
def tree(tmp_path):
    return W.write_world(tmp_path, N.muzzle_world())


def run(tree, cache, rules=None, with_root=True, base=None):
    cat, root = tree
    return dirmod.build_directory_report(
        cat, overrides=N.muzzle_overrides(), pack_settings=W.pack_settings(N.muzzle_world()), rules=rules or W.sight_rules(),
        threejs_v2_dir=root if with_root else None, geometry_cache=cache, base=base)


def keys(directory) -> dict:
    return {(w["id"], e["host"]): e.get("seat_setback_m") for w in directory["weapons"] for e in (w.get("attachment") or {}).get("compatible_hosts") or []}


def test_a_second_build_reads_no_mesh_for_the_silencer_seat_and_equals_the_first(tree, monkeypatch):
    cache: dict = {}
    d1, _, r1 = run(tree, cache)
    assert r1["setback_stats"] == {"computed": 4, "cached": 0, "kept": 0}  # Bare, Shroud, Brake, FarBrake: one host read each, not one per pair
    assert sorted(k for k in cache if k.startswith("muz|")) == sorted(f"muz|glb/{N.PACK}/{h}.glb" for h in (N.SH_BARE, N.SH_SHROUD, N.SH_BRAKE, N.SH_FAR))

    def refuse(*a, **k):
        raise AssertionError("a mesh was decoded on a build whose inputs did not change")

    monkeypatch.setattr(geo, "load_triangles", refuse)
    d2, _, r2 = run(tree, cache)
    assert r2["setback_stats"] == {"computed": 0, "cached": 4, "kept": 0} and r2["geometry_stats"]["decoded"] == 0
    assert d2 == d1 and keys(d2) == keys(d1)
    monkeypatch.undo()
    d3, _, r3 = run(tree, {})
    assert d3 == d1 and r3["setback_stats"]["computed"] == 4


def test_the_table_the_attach_version_and_the_code_digests_are_in_the_fingerprint(tree, monkeypatch):
    cache: dict = {}
    d1, _, _ = run(tree, cache)
    rules = W.sight_rules()
    rules["attachment_rules"]["muzzle_seat"]["device_reach_m"] = 0.20
    d2, _, r2 = run(tree, cache, rules)
    assert r2["setback_stats"] == {"computed": 4, "cached": 0, "kept": 0}  # another question
    far = (N.pid(N.SILENCER), N.pid(N.SH_FAR))
    assert keys(d1)[far] == 0.08 and keys(d2)[far] == 0.15  # the far brake (rear face 0.145 behind the tip) now counts: min(stub, max(0.08, 0.145 + 0.005), 0.15)
    _, _, r3 = run(tree, cache, rules)
    assert r3["setback_stats"]["cached"] == 4
    for name in ("_ATTACH_CODE_DIGEST", "_PROBE_CODE_DIGEST"):
        monkeypatch.setattr(geo, name, "0" * 16)
        _, _, r = run(tree, cache, rules)
        assert r["setback_stats"]["computed"] == 4 and r["setback_stats"]["cached"] == 0, name
        monkeypatch.undo()
    import synty_inventory.weapons as pkg
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", 14)  # the shipped value is 13 (A8, W8p): any other value is a new fingerprint
    _, _, r = run(tree, cache, rules)
    assert r["setback_stats"]["computed"] == 4, "WEAPON_ATTACH_VERSION is in the fingerprint"


def test_a_changed_host_file_misses_and_remeasures(tree):
    cat, root = tree
    cache: dict = {}
    run(tree, cache)
    shroud = root / "glb" / N.PACK / f"{N.SH_SHROUD}.glb"
    shroud.write_bytes(shroud.read_bytes() + b"\0" * 4)
    _, _, r = run(tree, cache)
    assert r["setback_stats"]["computed"] == 1 and r["setback_stats"]["cached"] == 3


def test_a_host_whose_mesh_cannot_be_read_keeps_the_stored_key(tree):
    d1, _, _ = run(tree, {})
    records = deepcopy(d1["weapons"])
    stored = dirmod._stored_setbacks(records)
    assert stored[(N.pid(N.SILENCER), N.pid(N.SH_BRAKE))] == 0.08 and len(stored) == 6
    for r in records:
        for e in (r.get("attachment") or {}).get("compatible_hosts") or []:
            e.pop("seat_setback_m", None)
    stats = {"computed": 0, "cached": 0, "kept": 0}
    dirmod._apply_muzzle_seat(records, W.sight_rules(), None, {}, stats, stored)  # no threejs root: nothing can be measured
    assert stats["computed"] == 0 and stats["cached"] == 0 and stats["kept"] == 8   # 4 hosts x 2 natural parts
    assert dirmod._stored_setbacks(records) == stored


def test_an_undecodable_host_is_unavailable_and_stores_no_answer(tree):
    cat, root = tree
    d, _, _ = run(tree, {})
    by = W.by_id(d)
    host = by[N.pid(N.SH_SHROUD)]
    mount = host["geometry"]["mounts"]["muzzle"]
    params = attachment_rules(load_rules())["muzzle_seat"]
    cache: dict = {}
    garbage = root / "glb" / N.PACK / "garbage.glb"
    garbage.write_bytes(b"this is not a glb")
    files = dict(host["files"], glb=f"glb/{N.PACK}/garbage.glb")
    assert geo.muzzle_stub_cached(root, files, mount, [], params, cache) == (None, "unavailable")
    assert all(not e["by_inputs"] for e in cache.values())
    missing = dict(host["files"], glb="glb/nowhere/missing.glb")
    assert geo.muzzle_stub_cached(root, missing, mount, [], params, cache) == (None, "unavailable")


def test_a_rules_file_without_the_table_writes_no_key(tree):
    rules = W.sight_rules()
    del rules["attachment_rules"]["muzzle_seat"]
    d, _, r = run(tree, {}, rules)
    assert all(v is None for v in keys(d).values()) and r["setback_stats"] == {"computed": 0, "cached": 0, "kept": 0}


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    import json
    from synty_inventory.weapons import export as export_mod
    from synty_inventory.weapons.directory import write_directory
    rh = importlib.util.spec_from_file_location("review_helpers", FIX / "review_helpers.py")
    H = importlib.util.module_from_spec(rh)
    rh.loader.exec_module(H)
    tmp = tmp_path_factory.mktemp("w8n_muzzle_export")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(export_mod, "_repo_root", lambda: None)  # the pytest tmp dir sits inside this checkout
    directory, excluded, cat, root = W.build(tmp, N.muzzle_world(), overrides=N.muzzle_overrides())
    write_directory(cat, directory, excluded)
    out = tmp / "game_repo"
    out.mkdir()
    yield SimpleNamespace(cfg=H.write_config(tmp, cat, []), out=out, H=H, json=json)
    mp.undo()


def export(ex, capsys, *flags, name):
    path = ex.out / name
    code, _ = ex.H.run(ex.cfg, capsys, ["weapons", "export", "--game", "ref", "--packs", N.PACK, "--roles", "all", *flags, "--out", str(path)])
    assert code == 0
    return ex.json.loads(path.read_text(encoding="utf-8")), path


def test_the_attachments_export_carries_the_key_and_the_default_export_none(exported, capsys):
    doc, path = export(exported, capsys, "--attachments", name="att.json")
    rec = next(w for w in doc["weapons"] if w["id"] == N.pid(N.SILENCER))
    got = {e["host"]: e.get("seat_setback_m") for e in rec["attachment"]["compatible_hosts"]}
    assert got[N.pid(N.SH_BRAKE)] == 0.08 and got[N.pid(N.SH_SHROUD)] == 0.062 and got[N.pid(N.SH_BARE)] is None
    code, res = exported.H.run(exported.cfg, capsys, ["weapons", "validate", "--snapshot", str(path)])
    assert code == 0 and res["errors"] == []
    default, dpath = export(exported, capsys, name="default.json")
    assert "seat_setback_m" not in dpath.read_text(encoding="utf-8") and all("attachment" not in w for w in default["weapons"])


# -- the table validates ------------------------------------------------------------------------------------------------------


def broken(mutate):
    rules = deepcopy(load_rules())
    mutate(rules["attachment_rules"]["muzzle_seat"])
    return validate_rules(rules)


@pytest.mark.parametrize(("mutate", "needle"), [
    (lambda t: t.pop("cover"), "cover"),
    (lambda t: t.update(cover=0.0), "cover"),
    (lambda t: t.update(cover=1.5), "cover"),
    (lambda t: t.update(max_frac=0.0), "max_frac"),
    (lambda t: t.update(max_frac=1.1), "max_frac"),
    (lambda t: t.update(dead_m=-0.001), "dead_m"),
    (lambda t: t.update(bin_m="fine"), "bin_m"),
    (lambda t: t.update(run_min_bins=0), "run_min_bins"),
    (lambda t: t.update(run_min_bins=2.5), "run_min_bins"),
    (lambda t: t.update(device_reach_m=True), "device_reach_m"),
    (lambda t: t.update(window_m=0.35), "window_m"),               # over range_m
    (lambda t: t.update(range_m=0.1), "window_m"),
    (lambda t: t.update(window_m=0.20), "window_m"),               # window + 10 mm over the schema bound 0.2
    (lambda t: t.update(device_reach_m=0.2), "device_reach_m"),    # over the window
    (lambda t: t.update(surprise=1), "surprise"),
])
def test_the_table_rejects_a_malformed_value(mutate, needle):
    errors = broken(mutate)
    assert errors and any(needle in e for e in errors), errors


def test_the_table_moves_the_attach_digest_only():
    base = load_rules()
    for mutate in (lambda t: t["muzzle_seat"].update(cover=0.5), lambda t: t.pop("muzzle_seat")):
        rules = deepcopy(base)
        mutate(rules["attachment_rules"])
        assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)


def test_a_table_without_muzzle_seat_is_valid():
    rules = deepcopy(load_rules())
    del rules["attachment_rules"]["muzzle_seat"]
    assert validate_rules(rules) == []
