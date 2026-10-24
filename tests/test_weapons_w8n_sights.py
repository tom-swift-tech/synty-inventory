"""W8n item 5: the per-host receiver tolerance of the sight probe (docs/weapon_attachments.md 13.7 A6-4 d2).

``sight_probe.receiver_tol_by_host`` maps ``"<pack>/<host id>"`` to a receiver tolerance (metres, 0 < tol <= 0.03) used for that host only; every other
host keeps ``receiver_tol_m`` (0.006). The receiver run is the bins within the tolerance of the host's highest point, and the rear seat is the run's rear
end plus ``rear_inset_m`` (10 mm).

Fixture: ``w8n_world.sight_world``, a deck (top y 0.10, z -0.30..0.10) with a row of crests on it (top y 0.111, z -0.2575..-0.2025): at 6 mm only the crests
are the receiver, so the rear seat sits at the crests' rear end plus 10 mm (z about -0.25, a 5 mm bin); at 12 mm or more the whole deck is, and the seat
is the deck's rear end plus 10 mm (z -0.29). At 10 mm it is still the crests (the crests are 11 mm over the deck).
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8n_world", FIX / "w8n_world.py")
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)
W, G = N.W, N.G

from synty_inventory.weapons.rules import attach_rules_digest, attachment_rules, load_rules, validate_rules, weapon_rules_digest  # noqa: E402

KEY = N.pid(N.TOOTH_HOST)
CREST_REAR, DECK_REAR = -0.25, -0.29


def test_the_shipped_table_names_the_apocalypse_submachine_gun_only():
    probe = attachment_rules(load_rules())["sight_probe"]
    assert probe["receiver_tol_m"] == 0.006
    assert probe["receiver_tol_by_host"] == {"POLYGON_Apocalypse/SM_Wep_SubMGun_01": 0.014}


def rear(by, host):
    m = by[N.pid(host)]["geometry"]["mounts"]["sight_rear"]
    assert m["source"] == "probe", host
    return m["point"]


def front(by, host):
    return by[N.pid(host)]["geometry"]["mounts"]["sight_front"]["point"]


def build(tmp_path, tol_by_host=None, world=None, cache=None):
    rules = W.sight_rules()
    if tol_by_host is not None:
        rules["attachment_rules"]["sight_probe"]["receiver_tol_by_host"] = tol_by_host
    assert validate_rules(rules) == []
    return W.by_id(W.build(tmp_path, world or N.sight_world(), rules=rules, cache=cache)[0])


def test_without_a_row_for_the_host_the_crests_are_the_receiver(tmp_path):
    by = build(tmp_path)  # the shipped row names another pack's host
    for host in (N.TOOTH_HOST, N.TOOTH_TWIN):
        assert rear(by, host)[2] == pytest.approx(CREST_REAR, abs=0.005) and rear(by, host)[1] == pytest.approx(0.111, abs=0.001)


def test_the_named_host_reaches_the_deck_and_the_other_host_is_unchanged(tmp_path):
    by = build(tmp_path, {KEY: 0.014})
    assert rear(by, N.TOOTH_HOST)[2] == pytest.approx(DECK_REAR, abs=0.005) and rear(by, N.TOOTH_HOST)[1] == pytest.approx(0.100, abs=0.001)
    assert rear(by, N.TOOTH_TWIN)[2] == pytest.approx(CREST_REAR, abs=0.005) and rear(by, N.TOOTH_TWIN)[1] == pytest.approx(0.111, abs=0.001)
    assert front(by, N.TOOTH_HOST) == front(by, N.TOOTH_TWIN)   # the front seat does not read the receiver tolerance


def test_12_mm_reproduces_the_deck_and_10_mm_does_not(tmp_path):
    assert rear(build(tmp_path / "a", {KEY: 0.012}), N.TOOTH_HOST)[2] == pytest.approx(DECK_REAR, abs=0.005)
    assert rear(build(tmp_path / "b", {KEY: 0.010}), N.TOOTH_HOST)[2] == pytest.approx(CREST_REAR, abs=0.005)   # the crests are 11 mm over the deck


def test_the_key_is_the_pack_and_the_host_id_together(tmp_path):
    world = N.sight_world()
    world[N.OTHER] = {"hosts": {N.TOOTH_HOST: W.host_node(N.TOOTH_HOST, N.tooth_host())}}   # the same id in another pack
    by = build(tmp_path, {KEY: 0.014}, world)
    assert rear(by, N.TOOTH_HOST)[2] == pytest.approx(DECK_REAR, abs=0.005)
    other = by[N.pid(N.TOOTH_HOST, N.OTHER)]["geometry"]["mounts"]["sight_rear"]["point"]
    assert other[2] == pytest.approx(CREST_REAR, abs=0.005)


def test_a_cached_measurement_does_not_survive_a_change_of_the_row(tmp_path):
    cache: dict = {}
    first = build(tmp_path / "a", None, cache=cache)
    assert rear(first, N.TOOTH_HOST)[2] == pytest.approx(CREST_REAR, abs=0.005)
    second = build(tmp_path / "a", {KEY: 0.014}, cache=cache)   # the same files, another row: a new question
    assert rear(second, N.TOOTH_HOST)[2] == pytest.approx(DECK_REAR, abs=0.005)
    third = build(tmp_path / "a", {KEY: 0.014}, cache=cache)
    assert rear(third, N.TOOTH_HOST) == rear(second, N.TOOTH_HOST)


# -- the table validates ------------------------------------------------------------------------------------------------------


def broken(value):
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["sight_probe"]["receiver_tol_by_host"] = value
    return validate_rules(rules)


@pytest.mark.parametrize("value", [
    {"P/H_01": 0.0}, {"P/H_01": -0.01}, {"P/H_01": 0.0301}, {"P/H_01": "0.01"}, {"P/H_01": True}, {"P/H_01": None},
    {"H_01": 0.01}, {"P/Q/H_01": 0.01}, {"/H_01": 0.01}, {"P/": 0.01}, [0.01], "P/H_01",
])
def test_the_row_rejects_a_malformed_entry(value):
    errors = broken(value)
    assert errors and any("receiver_tol_by_host" in e for e in errors), errors


@pytest.mark.parametrize("value", [{}, {"P/H_01": 0.001}, {"P/H_01": 0.03}, {"P/H_01": 0.014, "Q/H_02": 0.02}])
def test_the_row_accepts_a_pack_host_key_with_a_tolerance_up_to_30_mm(value):
    assert broken(value) == []


def test_the_row_moves_the_attach_digest_only():
    base = load_rules()
    rules = deepcopy(base)
    rules["attachment_rules"]["sight_probe"]["receiver_tol_by_host"]["POLYGON_Apocalypse/SM_Wep_SubMGun_01"] = 0.012
    assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)
    rules = deepcopy(base)
    del rules["attachment_rules"]["sight_probe"]["receiver_tol_by_host"]
    assert validate_rules(rules) == [] and attach_rules_digest(rules) != attach_rules_digest(base)
