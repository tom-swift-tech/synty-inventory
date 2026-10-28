"""W8o: the default view of ``weapons export --attachments`` (docs/weapon_attachments.md 13.8 A7-1; AC117).

World: ``w8d_world`` with ONE change to its rules: FAKE_CompB is moved out of the shared setting into a setting of its own. That gives the three packs
of the acceptance row: P1 = FAKE_CompA and P2 = FAKE_Mount in one setting, P3 = FAKE_CompB in another. Every expected id and count is a literal worked
out from the fixture (see the comments), the exports go through the real CLI path.

* ``FAKE_CompA/SM_Wep_Rifle_Mag_01`` (P1): twin of the Mag child of Alpha and of a child of ``FAKE_Mount/..Mount_01``; pending ``same_pack_fit`` on Gamma,
  Beta and Epsilon (G1 3.1/3.7, S8: no affinity or family cut any more, and these hosts have no well, so ``not_judged``); pending ``cross_pack_fit`` on the
  seatless hosts of the exported packs: Attach/Pistol_01 and Assault_01 and the seven FAKE_Mount hosts Pistol_Mount, Fall, Hull, Muzz, Plain, Shared, Tilt.
  ``FAKE_Mount/..Double_01`` is on neither list now: its default well (the large child, 0.06 x 0.024) is not the part's entry section (0.04 x 0.02),
  so the pair is ``no_fit`` (3.7); under A8-1 (W8p) it had been parked in ``pending_hosts``, under A7 listed.
* Nothing may name a FAKE_CompB host (Delta) from a part of another pack, nor a part of FAKE_CompB a host of another pack.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec_g1 = importlib.util.spec_from_file_location("g1_refs", FIX / "g1_refs.py")
g1_refs = importlib.util.module_from_spec(_spec_g1)
_spec_g1.loader.exec_module(g1_refs)
_spec = importlib.util.spec_from_file_location("w8d_world", FIX / "w8d_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)
H = X.H

from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons.directory import write_directory  # noqa: E402

PACKS = ",".join(sorted(X.ATTACH_PACKS))  # FAKE_Attach,FAKE_CompA,FAKE_CompB,FAKE_Mount
MAG = "FAKE_CompA/SM_Wep_Rifle_Mag_01"
P3_PART = "FAKE_CompB/SM_Wep_Alt_Scope_01"
DOUBLE = "FAKE_Mount/SM_Wep_Rifle_Double_01"
FALL = "FAKE_Mount/SM_Wep_Rifle_Fall_01"
SAME_PENDING = ["FAKE_CompA/SM_Wep_Pistol_Gamma_01", "FAKE_CompA/SM_Wep_Rifle_Beta_01", "FAKE_CompA/SM_Wep_Rifle_Epsilon_01"]
CROSS_PENDING = (["FAKE_Attach/SM_Wep_Pistol_01", "FAKE_Attach/SM_Wep_Rifle_Assault_01", "FAKE_Mount/SM_Wep_Pistol_Mount_01"]
                 + [f"FAKE_Mount/SM_Wep_Rifle_{n}_01" for n in ("Fall", "Hull", "Muzz", "Plain", "Shared", "Tilt")])


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w8o_export")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(export_mod, "_repo_root", lambda: None)
    rules = X.world_rules()
    rules["attachment_rules"]["attach_genre_by_pack"]["FAKE_CompB"] = "other"  # P3: its own setting
    directory, excluded, cat, root = X.build(tmp, rules=rules)
    write_directory(cat, directory, excluded)
    out = tmp / "game_repo"
    out.mkdir()
    yield {"tmp": tmp, "cfg": X.write_config(tmp, cat), "directory": directory, "out": out,
           "by_id": {w["id"]: w for w in directory["weapons"]}}
    mp.undo()


def export(world, capsys, *flags, name="snap.json"):
    out = world["out"] / name
    code, res = H.run(world["cfg"], capsys, ["weapons", "export", "--game", "ref", "--packs", PACKS, *flags, "--out", str(out)])
    return code, res, out


def by_id(path: Path) -> dict:
    return {w["id"]: w for w in json.loads(path.read_text(encoding="utf-8"))["weapons"]}


def named(rec) -> list[str]:
    att = rec["attachment"]
    return [e["host"] for e in att["compatible_hosts"]] + list(att["pending_hosts"])


def test_ac117_the_setting_wall_in_the_directory_p1_to_p2_yes_p3_never(world):
    mag = world["by_id"][MAG]["attachment"]
    assert {"host": FALL, "tier": "cross_pack_fit"} in mag["pending_hosts"]  # P1 -> P2 (a seatless host: pending; Double is a no_fit now, see the docstring)
    assert DOUBLE not in [e["host"] for e in mag["compatible_hosts"] + mag["pending_hosts"]]
    for rec in world["by_id"].values():
        att = rec.get("attachment")
        if att is None:
            continue
        for host in (e["host"] for e in att["compatible_hosts"] + att["pending_hosts"]):
            assert (rec["pack"] == "FAKE_CompB") == host.startswith("FAKE_CompB/"), (rec["id"], host)  # P3 only ever with itself


def test_ac117_the_default_attachments_export_lists_no_cross_magazine_and_no_pending_cross(world, capsys):
    code, _, out = export(world, capsys, "--roles", "all", "--attachments", name="default.json")
    assert code == 0
    docs = by_id(out)
    mag = docs[MAG]["attachment"]
    assert [(e["host"], e["tier"]) for e in mag["compatible_hosts"]] == [  # A8-1: the seated cross-pack magazine pair is no longer listed
        ("FAKE_CompA/SM_Wep_Rifle_Alpha_01", "twin"), ("FAKE_Mount/SM_Wep_Rifle_Mount_01", "twin")]
    assert mag["pending_hosts"] == SAME_PENDING  # the cross-pack pairs, seated or not, stay out (D-13, A8-1)
    for rec in docs.values():  # P3 never, in either list, either direction
        if rec.get("attachment") is None:
            continue
        if rec["pack"] != "FAKE_CompB":
            assert not [h for h in named(rec) if h.startswith("FAKE_CompB/")], rec["id"]
        else:
            assert all(h.startswith("FAKE_CompB/") for h in named(rec)), rec["id"]


def test_ac117_pending_cross_pack_is_present_with_pending_min_tier_cross_pack_fit(world, capsys):
    code, _, out = export(world, capsys, "--roles", "all", "--attachments", "--pending-min-tier", "cross_pack_fit", name="pending_cross.json")
    assert code == 0
    mag = by_id(out)[MAG]["attachment"]
    assert mag["pending_hosts"] == SAME_PENDING + sorted(CROSS_PENDING)  # (tier rank, host) order; Double is a no_fit now (G1 3.7, S8)
    assert len(mag["compatible_hosts"]) == 2  # the compatible cut is its own flag (3 under A7: Double was listed)
    assert not [h for h in mag["pending_hosts"] if h.startswith("FAKE_CompB/")]


def test_ac117_the_two_cuts_are_independent(world, capsys):
    # compatible cut at twin, pending cut at cross_pack_fit; and the reverse
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", "--min-compat-tier", "twin", "--pending-min-tier", "cross_pack_fit", name="c1.json")
    mag = by_id(out)[MAG]["attachment"]
    assert [e["tier"] for e in mag["compatible_hosts"]] == ["twin", "twin"] and len(mag["pending_hosts"]) == 12  # G1 (S8): 3 same-pack + 9 cross-pack
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", "--min-compat-tier", "same_pack_fit", "--pending-min-tier", "twin", name="c2.json")
    mag = by_id(out)[MAG]["attachment"]
    assert [e["tier"] for e in mag["compatible_hosts"]] == ["twin", "twin"] and mag["pending_hosts"] == []


def test_ac117_without_attachments_the_export_is_the_w7_one_and_the_pending_flag_is_refused(world, capsys):
    code, _, out = export(world, capsys, name="plain.json")
    assert code == 0
    assert json.loads(out.read_bytes().decode("utf-8"))["generated_from"]["geometry_version"] == 6  # G1, on its own
    assert out.read_bytes().decode("utf-8").replace("\r\n", "\n") == g1_refs.as_geometry_v6(
        (FIX / "w8d_w7_attach_default_export.json").read_bytes().decode("utf-8").replace("\r\n", "\n"))  # G1: the one number that moved
    for flags in (("--pending-min-tier", "cross_pack_fit"), ("--pending-min-tier", "same_pack_fit")):
        code, res, _ = export(world, capsys, *flags, name="refused_pending.json")
        assert code == 2 and "--pending-min-tier" in res["error"] and "--attachments" in res["error"], flags
        assert not (world["out"] / "refused_pending.json").exists()
    # the old refusals, unchanged: a tier other than the old default, the foreign-host flag
    code, res, _ = export(world, capsys, "--min-compat-tier", "twin", name="refused_min.json")
    assert code == 2 and res["error"] == "--min-compat-tier and --keep-foreign-hosts only act with --attachments"
    code, res, _ = export(world, capsys, "--min-compat-tier", "cross_pack_fit", name="refused_min2.json")
    assert code == 2
    code, res, _ = export(world, capsys, "--keep-foreign-hosts", name="refused_keep.json")
    assert code == 2 and res["error"] == "--min-compat-tier and --keep-foreign-hosts only act with --attachments"
    code, _, out = export(world, capsys, "--min-compat-tier", "same_pack_fit", name="ok_same.json")  # the old default value given explicitly
    assert code == 0


def test_ac117_the_header_records_no_tier_and_carries_the_new_version(world, capsys):
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", "--pending-min-tier", "cross_pack_fit", name="header.json")
    gf = json.loads(out.read_text(encoding="utf-8"))["generated_from"]
    assert gf["attach_version"] == 14 and gf["filter"]["attachments"] is True  # G1 4.6/AC146 (S8): attach version 13 -> 14
    assert "min_compat_tier" not in gf["filter"] and "pending_min_tier" not in gf["filter"]  # no place records a tier cut (judgment call: none added)


def test_ac117_mount_missing_reasons_follow_the_old_default_tiers(world):
    # a host is `mount_missing` iff a part has a PENDING override / twin / same_pack_fit entry on it; a host whose only pending entries are cross_pack_fit
    # (which the wider DEFAULT_TIERS would have flagged) carries no `mount_missing`
    old_tiers = {"override", "twin", "same_pack_fit"}
    flagged = {i for i, w in world["by_id"].items() if "mount_missing" in w["review"]["reasons"]}
    pending_old, pending_any = set(), set()
    for rec in world["by_id"].values():
        att = rec.get("attachment")
        for e in (att or {}).get("pending_hosts", ()):
            pending_any.add(e["host"])
            if e["tier"] in old_tiers:
                pending_old.add(e["host"])
    cross_only = pending_any - pending_old
    assert flagged <= pending_old
    assert cross_only and not (cross_only & flagged)
    assert "FAKE_CompA/SM_Wep_Rifle_Beta_01" in flagged and "FAKE_Mount/SM_Wep_Rifle_Fall_01" in cross_only
