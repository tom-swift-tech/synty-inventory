"""G1 S8: the export and the directory header of the geometry fit gate (docs/weapon_attach_geometry.md 4.3, 4.4, 4.6; AC145, AC146, AC148).

* AC145: ``fit_digest`` is an optional key of the directory header and, with ``--attachments`` only, of ``generated_from``; ``signals`` is an optional key of a
  directory-form pending entry; ``feature`` of a mount passes through to the export; every mount ``source`` of an export is one of the four values; a
  plain (no ``--attachments``) header that holds ``fit_digest`` fails the key check. The checks run on the FAKE_G1 world (API, ``cross_world``) and, through the
  CLI, on the w8d world.
* AC146: ``WEAPON_ATTACH_VERSION`` 14, ``WEAPON_GEOMETRY_VERSION`` 6, ``rules_digest`` and ``overrides_digest`` unchanged, ``attach_rules_digest`` changed; the
  default exports equal the W7 references once ``geometry_version`` 5 is read as 6.
* AC148 (the closed interim state of 937ea4d): on the w8d world no optic or underbarrel pair reaches ``compatible_hosts`` (so the default export) through
  ``rail_flat`` alone, and the 288 unverified ``rail_flat`` optic pairs of that merge are pending entries with the signal.

Every digest and count is a LITERAL measured at S8; a change of a rule, a measure or a detector moves them on purpose (INV-25).
"""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GW = _load("g1_world")
X = _load("w8d_world")
g1_refs = _load("g1_refs")
W, H = GW.W, X.H

import synty_inventory.weapons as pkg  # noqa: E402
from synty_inventory.weapons import directory as dirmod  # noqa: E402
from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons.directory import write_directory  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import attach_rules_digest, load_rules  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

SOURCES = {"override", "child_node", "probe", "none"}
PACKS = ",".join(sorted(X.ATTACH_PACKS))
OLD_ATTACH_DIGEST = "1dacc105674aff85"  # attach_rules_digest at 0934b2f (attach version 13)


def private_snapshot(directory, *, attachments, **kw):
    return export_mod.export_snapshot(
        directory, game="ref", pack_ids=None, ids=None, roles={"whole"} | ({"part"} if attachments else set()), engines={"godot"}, frame="item",
        profile="private", pack_meta={p["pack"]: p for p in directory["packs"]}, rules_digest=directory["rules_digest"],
        overrides_digest=directory["overrides_digest"], attachments=attachments, **kw)


@pytest.fixture(scope="module")
def g1(tmp_path_factory):
    world = GW.cross_world()
    cat, root = W.write_world(tmp_path_factory.mktemp("g1_export"), world)
    d, _ex, report = dirmod.build_directory_report(cat, overrides=empty_overrides(), pack_settings=W.pack_settings(world), rules=GW.cross_rules(),
                                                   threejs_v2_dir=root, geometry_cache={})
    return d, report


@pytest.fixture(scope="module")
def w8d(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("g1_export_w8d")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(export_mod, "_repo_root", lambda: None)
    rules = X.world_rules()
    rules["attachment_rules"]["attach_genre_by_pack"]["FAKE_CompB"] = "other"  # the world of the W8o/W8p export tests
    directory, excluded, cat, _root = X.build(tmp, rules=rules)
    write_directory(cat, directory, excluded)
    out = tmp / "game_repo"
    out.mkdir()
    yield {"tmp": tmp, "cfg": X.write_config(tmp, cat), "directory": directory, "out": out}
    mp.undo()


def cli_export(world, capsys, *flags, name="snap.json"):
    out = world["out"] / name
    code, _res = H.run(world["cfg"], capsys, ["weapons", "export", "--game", "ref", "--packs", PACKS, *flags, "--out", str(out)])
    return code, out


def reference(name: str) -> str:
    return (FIX / name).read_bytes().decode("utf-8").replace("\r\n", "\n")


# -- AC145: the consumer schema ----------------------------------------------------------------------------------------------------------


def test_ac145_the_directory_carries_fit_digest_and_validates_with_signals_on_pending_entries(g1):
    d, _report = g1
    # literal: the cross_world digest after E2 (the FAKE_G1 world alone: 9e88713e0a47d5d0, test_weapons_g1_compat). E2 re-pin (E2-Q2, E2-Q3), from 87fc33df830cfc68 at S8
    assert d["fit_digest"] == "e4245a0e01a13252"
    assert validate_directory(d) == []
    signalled = [e for w in d["weapons"] if w.get("attachment") for e in w["attachment"]["pending_hosts"] if "signals" in e]
    assert signalled and all(e["signals"] for e in signalled)  # the evidence of an unverified pair or a parked fit: optional, never empty
    text = json.dumps(d)
    assert "fit_parked" not in text and '"listed"' not in text  # the transient markers of compat.candidate never reach a record


def test_ac145_a_pending_entry_may_not_carry_other_keys_or_an_empty_signal_list(g1):
    d, _report = g1
    for edit in (lambda e: e.__setitem__("score", 0.5), lambda e: e.__setitem__("signals", []), lambda e: e.__setitem__("fit_parked", True),
                 lambda e: e.__setitem__("signals", [1])):
        broken = deepcopy(d)
        entry = next(e for w in broken["weapons"] if w.get("attachment") for e in w["attachment"]["pending_hosts"] if "signals" in e)
        edit(entry)
        assert validate_directory(broken) != []
    broken = deepcopy(d)
    broken["fit_digest"] = "xyz"
    assert validate_directory(broken) != []
    del broken["fit_digest"]
    assert validate_directory(broken) == []  # optional: a pre-G1 directory has none


def test_ac145_every_mount_source_of_the_attachments_export_is_one_of_the_four_and_feature_passes_through(g1):
    d, _report = g1
    snap = private_snapshot(d, attachments=True)
    assert export_mod.check_snapshot(snap) == []
    by = {w["id"]: w for w in snap["weapons"]}
    seen_features = set()
    for rec in snap["weapons"]:
        for slot, m in ((rec.get("geometry") or {}).get("mounts") or {}).items():
            assert m["source"] in SOURCES, (rec["id"], slot, m["source"])
            if "feature" in m:
                seen_features.add((slot, m["feature"]))
    # a rail seat is written as source `probe` with a `feature` (never `source: rail`, ARM_E70): the toothed top, the flat top, the barrel ring
    assert {("optic", "rail_teeth"), ("optic", "rail_flat"), ("muzzle", "barrel_ring")} <= seen_features
    carbine = by[GW.pid(GW.CARBINE)]["geometry"]["mounts"]
    assert carbine["optic"]["source"] == "probe" and carbine["optic"]["feature"] == "rail_teeth"
    assert by[GW.pid(GW.FLAT)]["geometry"]["mounts"]["optic"]["feature"] == "rail_flat"


def test_ac145_fit_digest_is_in_generated_from_with_attachments_only(g1):
    d, _report = g1
    with_att = private_snapshot(d, attachments=True)["generated_from"]
    plain = private_snapshot(d, attachments=False)["generated_from"]
    assert with_att["fit_digest"] == d["fit_digest"] and with_att["attach_version"] == 16
    assert "fit_digest" not in plain and "attach_version" not in plain and "attach_rules_digest" not in plain


def test_ac145_a_plain_header_that_holds_fit_digest_fails_and_a_pre_g1_attachments_header_passes(g1):
    d, _report = g1
    plain = private_snapshot(d, attachments=False)
    assert export_mod.check_snapshot(plain) == []
    plain["generated_from"]["fit_digest"] = d["fit_digest"]
    assert any("generated_from: keys must be" in e for e in export_mod.check_snapshot(plain))
    older = deepcopy(d)
    del older["fit_digest"]  # a directory built before G1: attach_version, but no fit_digest
    snap = private_snapshot(older, attachments=True)
    assert "fit_digest" not in snap["generated_from"] and export_mod.check_snapshot(snap) == []
    bad = private_snapshot(d, attachments=True)
    bad["generated_from"]["fit_digest"] = "NOT-HEX"
    assert any("fit_digest" in e and "16 lower-case hex" in e for e in export_mod.check_snapshot(bad))


def test_ac145_the_pending_hosts_of_the_export_are_ids_and_the_default_cut_drops_cross_pack_pending(g1):
    d, _report = g1
    snap = private_snapshot(d, attachments=True)
    by = {w["id"]: w for w in snap["weapons"]}
    mag = by[GW.pid(GW.MAG_RIFLE, GW.OTHER)]["attachment"]
    assert all(isinstance(h, str) for h in mag["pending_hosts"])
    assert mag["pending_hosts"] == []  # A8-1 and D-13: a cross-pack pending entry, parked fits included, is not exported by default
    same = by[GW.pid(GW.MAG_DRUM)]["attachment"]["pending_hosts"]
    assert same and all(isinstance(h, str) for h in same)  # the same-pack not_judged entries are


# -- AC146: the migration ------------------------------------------------------------------------------------------------------------------


def test_ac146_the_versions_and_the_digests():
    assert pkg.WEAPON_ATTACH_VERSION == 16 and pkg.WEAPON_GEOMETRY_VERSION == 6
    rules = load_rules()
    got = attach_rules_digest(rules)
    assert got == "d221b5faa57f12c9" and got != OLD_ATTACH_DIGEST  # E3.8 (clamp.ratio_min 1.0 to 0.69, Tom 2026-10-28) re-pinned this digest; S11 finding 12
    from synty_inventory.weapons.rules import weapon_rules_digest

    assert weapon_rules_digest(rules) == "7b9829af37328fe7"  # unchanged since a8c: the geometry block lives under attachment_rules


def test_ac146_the_directory_header_of_the_w8d_world(w8d):
    d = w8d["directory"]
    assert (d["attach_version"], d["geometry_version"], d["rules_digest"]) == (16, 6, "7b9829af37328fe7")
    assert d["overrides_digest"] == "7d8dd8ce21b0f42b"  # the overrides code is untouched
    # the world's rules carry its own attach_genre_by_pack (FAKE_CompB in a setting of its own), so its attach_rules_digest is not the shipped table's
    assert d["attach_rules_digest"] == "e2c15e21764814cf" and d["fit_digest"] == "84938175e9d16450"  # E3.8 (clamp.ratio_min 1.0 to 0.69, Tom 2026-10-28) re-pinned both digests of this world; S11 finding 12
    print(f"AC146: rules_digest {d['rules_digest']}, overrides_digest {d['overrides_digest']}, attach_rules_digest {d['attach_rules_digest']} "
          f"(was {OLD_ATTACH_DIGEST}), fit_digest {d['fit_digest']}")


def test_ac146_the_default_export_equals_the_w7_reference_read_as_version_6(w8d, capsys):
    code, out = cli_export(w8d, capsys)
    assert code == 0
    text = out.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert text == g1_refs.as_geometry_v6(reference("w8d_w7_attach_default_export.json"))
    assert "fit_digest" not in text and "attach_version" not in text
    code, out = cli_export(w8d, capsys, "--roles", "all", name="roles_all.json")
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["generated_from"] == json.loads(g1_refs.as_geometry_v6(reference("w8d_w7_attach_roles_all_export.json")))["generated_from"]


def test_ac145_the_cli_export_with_attachments_carries_fit_digest_and_validates(w8d, capsys):
    code, out = cli_export(w8d, capsys, "--attachments", name="attach.json")
    assert code == 0
    gf = json.loads(out.read_text(encoding="utf-8"))["generated_from"]
    assert gf["fit_digest"] == w8d["directory"]["fit_digest"] == "84938175e9d16450"
    assert (gf["attach_version"], gf["attach_rules_digest"]) == (16, w8d["directory"]["attach_rules_digest"])
    code, _res = H.run(w8d["cfg"], capsys, ["weapons", "validate", "--snapshot", str(out)])
    assert code == 0


# -- AC148: the interim state of 937ea4d is closed -----------------------------------------------------------------------------------------


def _pairs(directory):
    for w in directory["weapons"]:
        a = w.get("attachment")
        if a:
            yield w, a


def test_ac148_the_unverified_rail_flat_optic_pairs_of_the_w8d_world_are_pending_with_the_signal(w8d):
    pend = [(w["id"], e) for w, a in _pairs(w8d["directory"]) if a["slot"] == "optic" for e in a["pending_hosts"] if "rail_flat" in e.get("signals", ())]
    # 511 pending optic pairs sit on the 35 flat-seat hosts of the world. 288 of them are the pairs 937ea4d LISTED through the label-era path (a scratch run of
    # that tree and of this one over the same world shows every one of the 288 here, none still listed); 223 more were no candidate then (family, affinity)
    assert len(pend) == 511
    assert all(e["tier"] in ("same_pack_fit", "cross_pack_fit") and e["signals"] == ["rail_flat"] for _i, e in pend)
    flat_hosts = {w["id"] for w in w8d["directory"]["weapons"] if ((w.get("geometry") or {}).get("mounts") or {}).get("optic", {}).get("feature") == "rail_flat"}
    assert len(flat_hosts) == 35
    for _w, a in _pairs(w8d["directory"]):
        if a["slot"] == "optic":
            assert not [e for e in a["compatible_hosts"] if e["host"] in flat_hosts and e["tier"] in ("same_pack_fit", "cross_pack_fit")]


def test_ac148_no_optic_or_underbarrel_pair_is_listed_through_rail_flat_alone(w8d, g1):
    for directory in (w8d["directory"], g1[0]):
        for _w, a in _pairs(directory):
            if a["slot"] in ("optic", "underbarrel"):
                assert not [e for e in a["compatible_hosts"] if set(e.get("signals", ())) <= {"rail_flat", "frame_body"} and "rail_flat" in e.get("signals", ())]
                assert not [e for e in a["compatible_hosts"] if e["tier"] in ("same_pack_fit", "cross_pack_fit") and not e["signals"]]


def test_ac148_the_default_export_lists_no_optic_through_rail_flat(w8d, capsys):
    code, out = cli_export(w8d, capsys, "--roles", "all", "--attachments", name="all_attach.json")
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    cross = {}
    for w in doc["weapons"]:
        a = w.get("attachment")
        if a:
            for e in a["compatible_hosts"]:
                assert e["tier"] in ("override", "twin", "same_pack_fit", "cross_pack_fit")
                if e["tier"] == "cross_pack_fit":
                    cross[a["slot"]] = cross.get(a["slot"], 0) + 1
    print(f"AC148: listed cross_pack_fit entries of the w8d attachments export by slot: {cross}")
    assert cross.get("optic", 0) == 17  # was 84 under the provisional S7 merge: the 67 flat-seat pairs it listed are pending now (g1 3.5, Q-G3)
    assert cross.get("muzzle", 0) == 27 and cross.get("laser_light", 0) == 2 and "magazine" not in cross
