"""W8n: the versions, the digests and the tables as a whole (docs/weapon_attachments.md 13.7 A6).

``WEAPON_ATTACH_VERSION`` 9 -> 10; ``WEAPON_GEOMETRY_VERSION`` stays 5 (no new decoded geometry field: the silencer seat and the settle cap are
post-passes cached beside the measurements); ``rules_digest`` stays 7b9829af37328fe7 (every A6 table sits inside ``attachment_rules``) and
``attach_rules_digest`` moves. The default export is byte-identical to W7 (AC77): the default-export tests of the other waves, which compare against
``w7_default_export.json``, keep passing (they are not repeated here).
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
W = N.W

import synty_inventory.weapons as pkg  # noqa: E402
from synty_inventory.weapons.rules import attach_rules_digest, load_rules, validate_rules, weapon_rules_digest  # noqa: E402

BASE_ATTACH_DIGEST = "769ab6e4a3106c40"  # attach_rules_digest(load_rules()) at base 8d4f343 (attach version 9)


def test_the_version_constants():
    assert pkg.WEAPON_ATTACH_VERSION == 11 and pkg.WEAPON_GEOMETRY_VERSION == 5


def test_the_rules_digest_stays_and_the_attach_digest_moves():
    rules = load_rules()
    assert weapon_rules_digest(rules) == "7b9829af37328fe7"
    assert len(attach_rules_digest(rules)) == 16 and attach_rules_digest(rules) != BASE_ATTACH_DIGEST


@pytest.mark.parametrize("edit", [
    lambda t: t["attach_host_class"].update(launcher=["launcher"]),
    lambda t: t["attach_class_never"].update(launcher=["muzzle"]),
    lambda t: t["attach_compat"].update(fit_span_min=0.7),
    lambda t: t["attach_compat"].update(drum_min_m=0.12),
    lambda t: t["contact"].update(cap_m=0.02),
    lambda t: t["muzzle_seat"].update(cover=0.5),
    lambda t: t["sight_probe"].update(receiver_tol_by_host={"P/Q": 0.01}),
])
def test_every_new_table_moves_the_attach_digest_and_never_the_rules_digest(edit):
    base = load_rules()
    rules = deepcopy(base)
    edit(rules["attachment_rules"])
    assert validate_rules(rules) == []
    assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)


def test_the_header_of_a_built_directory_records_attach_version_10(tmp_path):
    directory, _, _, _ = W.build(tmp_path, N.mag_world())
    assert directory["attach_version"] == 11 and directory["geometry_version"] == 5 and directory["rules_digest"] == "7b9829af37328fe7"
    assert directory["attach_rules_digest"] == attach_rules_digest(W.sight_rules())


def test_a_class_table_with_an_unknown_class_slot_or_duplicate_is_rejected():
    for edit, needle in (
        (lambda t: t["attach_class_never"].update(ghost=["muzzle"]), "ghost"),
        (lambda t: t["attach_class_never"].update(launcher=["barrel"]), "barrel"),
        (lambda t: t["attach_class_never"].update(launcher=["muzzle", "muzzle"]), "distinct"),
        (lambda t: t["attach_host_class"].update(launcher="launcher"), "launcher"),
        (lambda t: t.update(attach_host_class=[1]), "attach_host_class"),
    ):
        rules = deepcopy(load_rules())
        edit(rules["attachment_rules"])
        errors = validate_rules(rules)
        assert errors and any(needle in e for e in errors), (needle, errors)


def test_a_rules_file_without_any_of_the_new_tables_is_valid():
    rules = deepcopy(load_rules())
    t = rules["attachment_rules"]
    for key in ("attach_host_class", "attach_class_never", "muzzle_seat"):
        del t[key]
    for key in ("drum_min_m", "fit_span_min"):
        del t["attach_compat"][key]
    del t["sight_probe"]["receiver_tol_by_host"]
    assert validate_rules(rules) == []
