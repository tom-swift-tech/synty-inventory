"""E3.5: guard tests for the frame-changed sight-slot clause (docs/weapon_attach_geometry.md 3.8; AC139, AC149; errata E3.5).

Q-G4 puts the record, and with it the sight probe and the fused front post detector (4.6 item 8 (D)), in the voted frame. On a host whose frame
the vote changed, the detector can find a post that the build frame missed, so its two sight slots read ``slot_disabled`` where the label-era
(build frame) directory had ``probe_unavailable``. AC139 and AC149 allow exactly that and nothing wider.

The fixtures are in ``fixtures/weapons/e3_sight_world.py``: POST (the Uzi of AC147 with a 25 mm wide, 24 mm tall post at the muzzle end), a plain
rifle and the both-rings host, which are not frame-changed, and two sight parts. The old frame is the ``frame_axis: y`` override on POST; the
voted frame is the same world without it. Every expected number is a LITERAL worked out by hand from those dimensions, never read from the code
under test: the 25 mm and 24 mm of the post are written out here, not taken from ``baked_sights.fused_post``.

The clause is the function ``unlisted`` below: the additions (host, slot) that the text does NOT list. Against the AC139 text as it stood before E3
(``amended=False``: the preset fill list only) the POST refusals are unlisted additions; against the amended text they are listed. Deliberate
breaks, and the tests that fail on each:

* a clause that permits any new refusal on a frame-changed host (not only the sight slots):
  ``test_a_muzzle_or_optic_refusal_on_a_frame_changed_host_is_not_permitted``;
* a detector run in the build frame (POST stays ``probe_unavailable``): ``test_fused_post_found_only_in_the_voted_frame``;
* the text left at the pre-E3 wording: ``test_ac139_additions_are_the_preset_fill_list_plus_frame_changed_sight_refusals`` (its negative control);
* a sight slot of a host that is not frame-changed, or ``laser_light`` anywhere, moving between the frames:
  ``test_ac149_laser_light_identical_everywhere``,
  ``test_ac149_the_sight_slots_move_only_on_the_frame_changed_host_and_take_its_pending_pairs_with_them``;
* a frame-changed host that has no fused post but GAINS sight seats in the voted frame (``probe_unavailable`` in the build frame): the clause does
  not cover it, so it is counted. The synthetic PLAIN host shows the mechanism (``test_a_frame_changed_host_without_a_post_gains_sight_seats``);
  the live pin ``test_live_no_frame_changed_host_gains_a_sight_seat`` holds the count of real hosts at 0.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from synty_inventory.paths import load_config

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("e3_sight_world", _FIX / "e3_sight_world.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

W = S.W

SIGHTS = ("sight_front", "sight_rear")
OTHER_SLOTS = ("optic", "muzzle", "underbarrel", "magazine", "laser_light")
# the preset fill list (Q-G11) is a14 against a8c policy, not a frame effect: no preset host is in this world, so its additions are none here
PRESET_HOSTS: frozenset = frozenset()


def _build(tmp_path_factory, name, overrides, rules=None, world=None):
    d, _excluded, _cat, _root = W.build(tmp_path_factory.mktemp(name), world or S.sight_world(), overrides=overrides, rules=rules)
    return SimpleNamespace(directory=d, by_id=W.by_id(d))


@pytest.fixture(scope="module")
def voted(tmp_path_factory):
    return _build(tmp_path_factory, "e3_sight_voted", S.voted_overrides())


@pytest.fixture(scope="module")
def old(tmp_path_factory):
    return _build(tmp_path_factory, "e3_sight_old", S.build_frame_overrides())


@pytest.fixture(scope="module")
def voted_without_the_detector(tmp_path_factory):
    rules = W.sight_rules()
    del rules["attachment_rules"]["baked_sights"]["fused_post"]  # no table, no detector: the one thing that differs from `voted`
    return _build(tmp_path_factory, "e3_sight_nodet", S.voted_overrides(), rules)


@pytest.fixture(scope="module")
def plain_voted(tmp_path_factory):
    return _build(tmp_path_factory, "e3_plain_voted", S.voted_overrides(), world=S.sight_world(with_plain=True))


@pytest.fixture(scope="module")
def plain_old(tmp_path_factory):
    return _build(tmp_path_factory, "e3_plain_old", S.build_frame_overrides(with_plain=True), world=S.sight_world(with_plain=True))


def short(pid: str) -> str:
    return pid.split("/", 1)[1]


def hosts(b):
    return [r for r in b.directory["weapons"] if (r.get("geometry") or {}).get("mounts")]


def mount(b, host, slot):
    return b.by_id[S.pid(host)]["geometry"]["mounts"][slot]


def state(b, host, slot):
    m = mount(b, host, slot)
    return (m["source"], m["reason"])


def refused(b) -> set:
    """The refused (host, slot) set of a directory: a slot that is none / slot_disabled (the set AC139 compares)."""
    return {(short(r["id"]), slot) for r in hosts(b) for slot, m in r["geometry"]["mounts"].items()
            if m["source"] == "none" and m["reason"] == "slot_disabled"}


def frame_changed(b) -> set:
    """The hosts whose frame the vote changed: a body forward (AC147)."""
    return {short(r["id"]) for r in hosts(b) if r["geometry"]["axes"]["forward_source"] == "body"}


def unlisted(additions, *, frame_changed_hosts, amended: bool, preset_hosts=PRESET_HOSTS) -> set:
    """The additions the AC139 text does not list. Before E3 only the preset fill list; amended, also the sight slots of a frame-changed host."""
    out = set()
    for host, slot in additions:
        if host in preset_hosts:
            continue
        if amended and host in frame_changed_hosts and slot in SIGHTS:
            continue
        out.add((host, slot))
    return out


def pair_hosts(b, part):
    """``(listed hosts, pending hosts)`` of a sight part, by short name."""
    a = b.by_id[S.pid(part)]["attachment"]
    return ({short(e["host"]) for e in a["compatible_hosts"]}, {short(e["host"]) for e in a["pending_hosts"]})


def pair_entries(b, part, host):
    a = b.by_id[S.pid(part)]["attachment"]
    return [e for e in a["compatible_hosts"] + a["pending_hosts"] if short(e["host"]) == host]


# --- the fixture: its post is what the tests say it is ---------------------------------------------------------------------


def test_the_fixture_post_is_25_mm_wide_and_24_mm_tall():
    verts = S.post_body()[0]
    post = verts[(verts[:, 1] > 0.06) & (verts[:, 2] > 0.1)]  # only the post reaches over y 0.06 at z > 0.1 (the barrel tops at 0.052)
    assert len(post) == 4  # the top face of the box
    assert post[:, 2].max() - post[:, 2].min() == pytest.approx(0.025, abs=1e-9)
    assert post[:, 1].max() - 0.052 == pytest.approx(0.024, abs=1e-9)
    assert verts[(verts[:, 2] > 0.1) & (verts[:, 1] <= 0.06)][:, 1].max() == pytest.approx(0.052, abs=1e-9)  # the barrel top the rise is measured from


# --- the post is found only in the voted frame -------------------------------------------------------------------------------


def test_fused_post_found_only_in_the_voted_frame(voted, old):
    assert voted.by_id[S.pid(S.POST)]["geometry"]["axes"]["forward"] == "+z"  # the vote changed the frame ...
    assert old.by_id[S.pid(S.POST)]["geometry"]["axes"]["forward"] == "-y"  # ... and frame_axis y kept the build frame
    for slot in SIGHTS:
        assert state(old, S.POST, slot) == ("none", "probe_unavailable"), slot  # the build frame: no post found, no seat
        assert mount(old, S.POST, slot)["point"] is None, slot
        assert state(voted, S.POST, slot) == ("none", "slot_disabled"), slot  # the feature frame: the post refuses both sight slots
    assert frame_changed(voted) == {"SM_Wep_SMG_Post_01"} and frame_changed(old) == set()


def test_the_refusal_of_the_post_is_the_detectors_and_nothing_else(voted, voted_without_the_detector):
    # without the fused_post table the voted frame seats both sight slots: the post alone turns the seats into slot_disabled
    for slot in SIGHTS:
        assert state(voted_without_the_detector, S.POST, slot) == ("probe", None), slot
    assert refused(voted_without_the_detector) == set()
    assert refused(voted) == {("SM_Wep_SMG_Post_01", "sight_front"), ("SM_Wep_SMG_Post_01", "sight_rear")}


def test_the_other_slots_of_the_post_host_keep_their_state_in_both_frames(voted, old):
    for slot in OTHER_SLOTS:
        assert state(voted, S.POST, slot) == state(old, S.POST, slot), slot
    assert state(voted, S.POST, "muzzle") == ("probe", None)  # seated in both frames, and no refusal
    assert state(voted, S.POST, "optic") == ("probe", None)


# --- AC139 ------------------------------------------------------------------------------------------------------------------


def test_ac139_additions_are_the_preset_fill_list_plus_frame_changed_sight_refusals(voted, old):
    assert refused(old) <= refused(voted)  # the superset
    additions = refused(voted) - refused(old)
    assert additions == {("SM_Wep_SMG_Post_01", "sight_front"), ("SM_Wep_SMG_Post_01", "sight_rear")}
    changed = frame_changed(voted)
    assert unlisted(additions, frame_changed_hosts=changed, amended=True) == set()
    # the AC139 text as it stood before E3 lists the preset fill additions only: here it leaves both refusals unlisted (the red of the old text)
    assert unlisted(additions, frame_changed_hosts=changed, amended=False) == additions
    post = voted.by_id[S.pid(S.POST)]  # each addition is reported with its host class
    assert (post["kind"], post["hold_class"], post["archetype"]) == ("ranged", "long_gun", "smg")


def test_a_muzzle_or_optic_refusal_on_a_frame_changed_host_is_not_permitted(voted, old):
    changed = frame_changed(voted)
    assert changed == {"SM_Wep_SMG_Post_01"}
    for slot in OTHER_SLOTS:  # the clause names the two sight slots only
        case = {("SM_Wep_SMG_Post_01", slot)}
        assert unlisted(case, frame_changed_hosts=changed, amended=True) == case, slot
    for host in ("SM_Wep_Rifle_Plain_01", "SM_Wep_SMG_Both_01"):  # and only a host whose frame the vote changed
        case = {(host, "sight_front")}
        assert unlisted(case, frame_changed_hosts=changed, amended=True) == case, host
    # and in the built worlds: no muzzle, optic, underbarrel, magazine or laser_light refusal appears on any host in either frame
    for b in (voted, old):
        assert {slot for _host, slot in refused(b)} <= set(SIGHTS)


# --- AC149 ------------------------------------------------------------------------------------------------------------------


def test_ac149_laser_light_identical_everywhere(voted, old):
    ids = sorted(r["id"] for r in hosts(voted))
    assert ids == sorted(r["id"] for r in hosts(old)) and len(ids) == 3
    for pid in ids:
        a, b = voted.by_id[pid]["geometry"]["mounts"]["laser_light"], old.by_id[pid]["geometry"]["mounts"]["laser_light"]
        assert a == b, pid
        assert (a["source"], a["reason"]) == ("none", "no_child_no_probe"), pid  # nothing in either frame reads this slot


def test_ac149_the_sight_slots_move_only_on_the_frame_changed_host_and_take_its_pending_pairs_with_them(voted, old):
    for host in (S.RIFLE, S.BOTH):  # not frame-changed: every sight entry is identical
        for slot in SIGHTS:
            assert mount(voted, host, slot) == mount(old, host, slot), (host, slot)
    for slot in SIGHTS:  # the one allowed move: probe_unavailable to slot_disabled
        assert state(old, S.POST, slot) == ("none", "probe_unavailable") and state(voted, S.POST, slot) == ("none", "slot_disabled"), slot
    for part in (S.SIGHT_FRONT, S.SIGHT_REAR):
        assert pair_hosts(old, part) == ({"SM_Wep_Rifle_Plain_01"}, {"SM_Wep_SMG_Both_01", "SM_Wep_SMG_Post_01"}), part  # the old frame promises POST (pending)
        assert pair_hosts(voted, part) == ({"SM_Wep_Rifle_Plain_01"}, {"SM_Wep_SMG_Both_01"}), part  # the fused post removes it; nothing else moves
        for host in ("SM_Wep_Rifle_Plain_01", "SM_Wep_SMG_Both_01"):
            assert pair_entries(voted, part, host) == pair_entries(old, part, host), (part, host)


# --- a frame-changed host without a post that gains sight seats --------------------------------------------------------------


def seat_gaining_hosts(voted_by_id: dict, old_by_id: dict) -> list:
    """The frame-changed hosts (a body forward in the voted directory) whose sight slot is ``probe_unavailable`` in the build frame and seated by
    the probe in the voted frame: the voted frame found seats the build frame did not, and no fused post refused them (that would read
    ``slot_disabled``, the clause of AC139 and AC149). Short host names, sorted. Both arguments map record id to record."""
    out = []
    for pid, rec in sorted(voted_by_id.items()):
        g = rec.get("geometry") or {}
        if (g.get("axes") or {}).get("forward_source") != "body":
            continue
        old = ((old_by_id[pid].get("geometry") or {}).get("mounts") or {}) if pid in old_by_id else {}
        for slot in SIGHTS:
            was = old.get(slot) or {}
            if (was.get("source"), was.get("reason")) == ("none", "probe_unavailable") and g["mounts"][slot]["source"] == "probe":
                out.append(short(pid))
                break
    return out


def assert_no_seat_gaining_hosts(voted_by_id: dict, old_by_id: dict) -> None:
    got = seat_gaining_hosts(voted_by_id, old_by_id)
    assert len(got) == 0, f"{len(got)} frame-changed host(s) gain sight seats in the voted frame: {got}"  # the pin: 0, written out here


def test_a_frame_changed_host_without_a_post_gains_sight_seats(plain_voted, plain_old):
    """The mechanism the live pin guards against: the plain Uzi has no post, no seat in the build frame and both seats in the voted frame."""
    for slot in SIGHTS:
        assert state(plain_old, S.PLAIN, slot) == ("none", "probe_unavailable"), slot
        assert state(plain_voted, S.PLAIN, slot) == ("probe", None), slot
    assert seat_gaining_hosts(plain_voted.by_id, plain_old.by_id) == ["SM_Wep_SMG_Uzi_01"]  # POST is refused by its post, so it is not counted
    assert refused(plain_voted) == {("SM_Wep_SMG_Post_01", "sight_front"), ("SM_Wep_SMG_Post_01", "sight_rear")}  # and the plain host adds no refusal


def test_the_pin_is_red_on_a_world_with_a_post_less_frame_changed_host(plain_voted, plain_old):
    with pytest.raises(AssertionError, match="1 frame-changed host"):
        assert_no_seat_gaining_hosts(plain_voted.by_id, plain_old.by_id)


def test_the_pin_is_green_on_the_world_without_it(voted, old):
    assert_no_seat_gaining_hosts(voted.by_id, old.by_id)  # POST has its post; RIFLE and BOTH are not frame-changed


@pytest.mark.live
def test_live_no_frame_changed_host_gains_a_sight_seat():
    """The live pin: in the real directory no host whose frame the vote changed gets sight seats it did not have in the build frame (count 0).

    The voted directory is built in memory from the configured catalogs (nothing is written: ``build_directory_report`` writes nothing and the
    caches are throwaway dicts). The build-frame directory is the same build with a ``frame_axis`` override per frame-changed host, naming the
    host's own build axis (its bounding-box ``long_axis``, which is what the build frame follows), on top of the committed overrides."""
    from synty_inventory.paths import ConfigError
    from synty_inventory.weapons import overrides as overrides_mod
    from synty_inventory.weapons.directory import build_directory_report
    from synty_inventory.weapons.overrides import load_overrides
    from synty_inventory.weapons.rules import load_rules

    try:
        cfg = load_config(require=False)
    except ConfigError:
        pytest.skip("the library is not on this machine")
    if not all(cfg.get(k) is not None and Path(cfg[k]).is_dir() for k in ("catalogs", "threejs_v2", "extracted_root")):
        pytest.skip("the library is not on this machine")
    rules = load_rules()
    committed = Path(overrides_mod.__file__).resolve().parent.parent / "data" / "weapon_overrides.json"  # by path: the suite points the default at an empty file

    def build(overrides):
        d, _excluded, _report = build_directory_report(
            Path(cfg["catalogs"]), packs=None, rules=rules, overrides=overrides, measure=True, base=None, threejs_v2_dir=Path(cfg["threejs_v2"]),
            geometry_cache={}, extracted_root=Path(cfg["extracted_root"]), fit_cache={})
        return {r["id"]: r for r in d["weapons"]}

    voted_by_id = build(load_overrides(committed))
    changed = sorted(pid for pid, r in voted_by_id.items() if ((r.get("geometry") or {}).get("axes") or {}).get("forward_source") == "body")
    assert len(changed) == 3  # AC147: three frame-changed hosts today, one of them a tool
    old_doc = deepcopy(load_overrides(committed))
    for pid in changed:
        old_doc["ids"].setdefault(pid, {})["frame_axis"] = voted_by_id[pid]["geometry"]["long_axis"]
    old_by_id = build(old_doc)
    for pid in changed:  # the override really gave the build frame back
        assert old_by_id[pid]["geometry"]["axes"]["forward_source"] != "body", pid
    assert_no_seat_gaining_hosts(voted_by_id, old_by_id)
