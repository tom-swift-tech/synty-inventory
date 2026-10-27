"""W8p: the ``--attachments`` export of unverified entries (docs/weapon_attachments.md 13.9 A8-1; AC125).

World: ``w8d_world`` with the same one change as the W8o export test (FAKE_CompB in a setting of its own). The exports go through the real CLI path.

* ``FAKE_CompA/SM_Wep_Rifle_Mag_01``: twin on Alpha and on ``FAKE_Mount/..Mount_01``; its cross_pack_fit pair with ``FAKE_Mount/..Double_01`` has a seat, so
  before A8 it was a LISTED cross entry. It is now a pending ``{host, tier: cross_pack_fit}`` entry, with the same-pack pending Beta and Epsilon unchanged.
* The fixture holds no other listed cross magazine. Its listed cross entries of the other slots (counted from the fixture: laser_light 2, muzzle 6,
  optic 6) must stay where they are.
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

PACKS = ",".join(sorted(X.ATTACH_PACKS))
MAG = "FAKE_CompA/SM_Wep_Rifle_Mag_01"
DOUBLE = "FAKE_Mount/SM_Wep_Rifle_Double_01"
SAME_PENDING = ["FAKE_CompA/SM_Wep_Rifle_Beta_01", "FAKE_CompA/SM_Wep_Rifle_Epsilon_01"]
CROSS_PENDING = ["FAKE_Attach/SM_Wep_Rifle_Assault_01"] + [f"FAKE_Mount/SM_Wep_Rifle_{n}_01" for n in ("Fall", "Hull", "Muzz", "Plain", "Shared", "Tilt")]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w8p_export")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(export_mod, "_repo_root", lambda: None)
    rules = X.world_rules()
    rules["attachment_rules"]["attach_genre_by_pack"]["FAKE_CompB"] = "other"
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


def test_ac125_the_directory_holds_the_cross_magazine_as_a_pending_entry_and_no_listed_one(world):
    mag = world["by_id"][MAG]["attachment"]
    assert (DOUBLE, "cross_pack_fit") not in [(e["host"], e["tier"]) for e in mag["compatible_hosts"]]
    assert {"host": DOUBLE, "tier": "cross_pack_fit"} in mag["pending_hosts"]  # the pending form: host and tier, nothing else
    assert "compat_cross_pack" in world["by_id"][MAG]["review"]["reasons"]
    for rec in world["by_id"].values():
        att = rec.get("attachment")
        if att and att["slot"] == "magazine":
            assert not [e for e in att["compatible_hosts"] if e["tier"] == "cross_pack_fit"], rec["id"]


def test_ac125_the_default_attachments_export_has_no_cross_magazine_in_either_list(world, capsys):
    code, _, out = export(world, capsys, "--roles", "all", "--attachments", name="default.json")
    assert code == 0
    docs = by_id(out)
    mag = docs[MAG]["attachment"]
    assert [(e["host"], e["tier"]) for e in mag["compatible_hosts"]] == [
        ("FAKE_CompA/SM_Wep_Rifle_Alpha_01", "twin"), ("FAKE_Mount/SM_Wep_Rifle_Mount_01", "twin")]
    assert mag["pending_hosts"] == SAME_PENDING  # the pending default cut is same_pack_fit: the parked cross entries stay out
    for rec in docs.values():
        att = rec.get("attachment")
        if att and att["slot"] == "magazine":
            assert not [e for e in att["compatible_hosts"] if e["tier"] == "cross_pack_fit"], rec["id"]
            cross_only = {e["host"] for e in world["by_id"][rec["id"]]["attachment"]["pending_hosts"] if e["tier"] == "cross_pack_fit"}
            assert not cross_only & set(att["pending_hosts"]), rec["id"]
            # the pending list of the export is the directory's pending entries at same_pack_fit or better, nothing more
            want = sorted(e["host"] for e in world["by_id"][rec["id"]]["attachment"]["pending_hosts"] if e["tier"] != "cross_pack_fit")
            assert sorted(att["pending_hosts"]) == want, rec["id"]


def test_ac125_the_other_slots_keep_their_listed_cross_entries(world, capsys):
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", name="default_slots.json")
    cross = {}
    for rec in by_id(out).values():
        att = rec.get("attachment")
        for e in (att or {}).get("compatible_hosts", ()):
            if e["tier"] == "cross_pack_fit":
                cross[att["slot"]] = cross.get(att["slot"], 0) + 1
    assert cross == {"laser_light": 2, "muzzle": 6, "optic": 6}  # literals counted from the fixture world; magazine: none


def test_ac125_pending_min_tier_cross_pack_fit_puts_the_parked_hosts_back_in_pending_hosts(world, capsys):
    code, _, out = export(world, capsys, "--roles", "all", "--attachments", "--pending-min-tier", "cross_pack_fit", name="pending_cross.json")
    assert code == 0
    mag = by_id(out)[MAG]["attachment"]
    assert mag["pending_hosts"] == SAME_PENDING + sorted(CROSS_PENDING + [DOUBLE])  # (tier rank, host) order; the seated cross host is among them
    assert [e["tier"] for e in mag["compatible_hosts"]] == ["twin", "twin"]
    assert not [h for h in mag["pending_hosts"] if h.startswith("FAKE_CompB/")]


def test_ac125_min_compat_tier_is_unchanged(world, capsys):
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", "--min-compat-tier", "twin", name="twin_cut.json")
    mag = by_id(out)[MAG]["attachment"]
    assert [e["tier"] for e in mag["compatible_hosts"]] == ["twin", "twin"]
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", "--min-compat-tier", "same_pack_fit", name="same_cut.json")
    assert [e["tier"] for e in by_id(out)[MAG]["attachment"]["compatible_hosts"]] == ["twin", "twin"]
    # the optic of the fixture: its cross entries are cut by the compatible flag exactly as before
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", "--min-compat-tier", "same_pack_fit", name="same_cut2.json")
    assert not [e for r in by_id(out).values() if r.get("attachment") for e in r["attachment"]["compatible_hosts"] if e["tier"] == "cross_pack_fit"]


def test_ac125_the_header_carries_attach_version_13_and_the_w7_export_is_unchanged(world, capsys):
    _, _, out = export(world, capsys, "--roles", "all", "--attachments", name="header.json")
    gf = json.loads(out.read_text(encoding="utf-8"))["generated_from"]
    assert gf["attach_version"] == 13 and gf["filter"]["attachments"] is True
    code, _, plain = export(world, capsys, name="plain.json")
    assert code == 0
    assert plain.read_bytes().decode("utf-8").replace("\r\n", "\n") == g1_refs.as_geometry_v6(
        (FIX / "w8d_w7_attach_default_export.json").read_bytes().decode("utf-8").replace("\r\n", "\n"))  # G1: the one number that moved
