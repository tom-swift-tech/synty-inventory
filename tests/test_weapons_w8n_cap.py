"""W8n item 3: the settle cap (docs/weapon_attachments.md 13.7 A6-4 c).

``attachment_rules.contact.cap_m`` (0.030 m, required, 0 < cap_m <= clamp_m): an optic or underbarrel entry whose settled ``|seat_shift_m|`` is
over the cap is REMOVED from ``compatible_hosts`` (the host's seat is wrong by more than a foot excuses; it is not pending either). The cap reads
the value however it was found (computed, cached or kept); entries that never get a key (twin, override, other slots) are never removed.

Fixtures: ``w8n_world.cap_world`` (the W8m boxes: pack FAKE_W8M, a scope child at a hand-chosen height over a body whose top is y 0.10; the shift is
the body top minus the child's foot, so a foot at 0.125 is a 25 mm gap). Every expected number is a LITERAL.
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
W, M = N.W, N.M

from synty_inventory.weapons import directory as dirmod, geometry as geo  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules, validate_rules  # noqa: E402


def case_of(host: str) -> str:
    return host.split("/", 1)[1].split("_")[3]  # SM_Wep_Rifle_<case>_01


def entries(by, part) -> dict:
    return {case_of(e["host"]): e for e in by[M.pid(part)]["attachment"]["compatible_hosts"]}


def shifts(by, part) -> dict:
    return {case: e.get("seat_shift_m") for case, e in entries(by, part).items()}


def named_anywhere(by, part, case) -> bool:
    att = by[M.pid(part)]["attachment"]
    return any(case_of(e["host"]) == case for e in att["compatible_hosts"] + att["pending_hosts"])


def run(root_cat, rules=None, cache=None, with_root=True, base=None):
    cat, root = root_cat
    return dirmod.build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=W.pack_settings(N.cap_world()), rules=rules or W.sight_rules(),
        threejs_v2_dir=root if with_root else None, geometry_cache={} if cache is None else cache, base=base)


@pytest.fixture()
def tree(tmp_path):
    return W.write_world(tmp_path, N.cap_world())


def test_the_shipped_cap_is_30_mm_and_the_clamp_stays_60():
    contact = attachment_rules(load_rules())["contact"]
    assert contact["cap_m"] == 0.03 and contact["clamp_m"] == 0.06


# -- the cap on a built directory --------------------------------------------------------------------------------------------


def test_a_gap_up_to_30_mm_keeps_its_entry_and_one_over_it_is_removed(tree):
    d, _, report = run(tree)
    by = W.by_id(d)
    # S7 (spec 3.4 step 3): the three Ub hosts have no scope child but a smooth top, so the scope part meets them on a flat optic seat. G1 3.5/AC148 (S8):
    # a flat seat is `unverified`, so they are pending (rail_flat) and the listed entries are the three seat_ref hosts; a pending pair has no contact key
    assert shifts(by, M.SCOPE_PART) == {"Gap25": -0.025, "Gap30": -0.03, "Sunk25": 0.025}
    flat = {case_of(e["host"]): e.get("signals") for e in by[M.pid(M.SCOPE_PART)]["attachment"]["pending_hosts"]}
    assert flat == {"UbGap25": ["rail_flat"], "UbGap40": ["rail_flat"], "UbSunk40": ["rail_flat"]}
    assert shifts(by, M.GRIP_PART) == {"UbGap25": -0.025}
    for case in ("Gap31", "Gap40", "Sunk40", "TwinGap40"):  # 31 mm, 40 mm, sunk 40 mm: not compatible, and not pending either
        assert not named_anywhere(by, M.SCOPE_PART, case), case
    for case in ("UbGap40", "UbSunk40"):
        assert not named_anywhere(by, M.GRIP_PART, case), case
    assert report["contact_capped"] == 6  # Gap31, Gap40, Sunk40, TwinGap40 (scope part) + UbGap40, UbSunk40 (grip part)


def test_the_cap_off_keeps_every_pair_with_its_shift(tree):
    rules = W.sight_rules()
    rules["attachment_rules"]["contact"]["cap_m"] = 0.06
    d, _, report = run(tree, rules)
    by = W.by_id(d)
    assert shifts(by, M.SCOPE_PART) == {"Gap25": -0.025, "Gap30": -0.03, "Gap31": -0.031, "Gap40": -0.04, "Sunk25": 0.025, "Sunk40": 0.04,
                                        "TwinGap40": -0.04}  # G1 (S8): the flat optic seats are pending, not listed
    assert shifts(by, M.GRIP_PART) == {"UbGap25": -0.025, "UbGap40": -0.04, "UbSunk40": 0.04}
    assert report["contact_capped"] == 0


def test_a_twin_on_a_40_mm_gap_host_is_never_removed(tree):
    d, _, _ = run(tree)
    entered = entries(W.by_id(d), M.TWIN_PART)
    # S7 (spec 3.4 step 3): the Ub hosts meet the part on their flat optic seats (G1 3.5, S8: pending, not listed); the twins are the seven hosts with a child
    twins = {case: e for case, e in entered.items() if e["tier"] == "twin"}
    assert sorted(twins) == ["Gap25", "Gap30", "Gap31", "Gap40", "Sunk25", "Sunk40", "TwinGap40"]
    assert all("seat_shift_m" not in e for e in twins.values())
    assert sorted(set(entered) - set(twins)) == []
    pending = {case_of(e["host"]) for e in W.by_id(d)[M.pid(M.TWIN_PART)]["attachment"]["pending_hosts"]}
    assert pending == {"UbGap25", "UbGap40", "UbSunk40"}


def test_an_override_on_a_40_mm_gap_host_is_never_removed(tmp_path):
    ovr = W.overrides_doc(ids={M.pid(M.ZETA_PART): {"compatible": {"add": [M.hid("Gap40")]}}})
    world = N.cap_world()
    world[M.PACK]["parts"][M.ZETA_PART] = M.zeta_part
    d, _, _, _ = W.build(tmp_path, world, overrides=ovr)
    got = entries(W.by_id(d), M.ZETA_PART)
    # G1 3.1/3.8 (S8): the family test is retired, so the zeta scope (no shared token) is a same-pack seat_ref fit on the hosts within the cap too; the
    # override still lists the 40 mm gap host the cap would have removed, unkeyed
    assert got["Gap40"]["tier"] == "override" and "seat_shift_m" not in got["Gap40"]
    assert sorted(got) == ["Gap25", "Gap30", "Gap40", "Sunk25"] and {got[c]["tier"] for c in ("Gap25", "Gap30", "Sunk25")} == {"same_pack_fit"}


def test_the_cap_acts_on_a_cached_shift_too_and_a_cache_hit_equals_a_recompute(tree, monkeypatch):
    cache: dict = {}
    d1, _, r1 = run(tree, cache=cache)
    n = r1["contact_stats"]["computed"]
    assert n > 0 and r1["contact_capped"] == 6

    def refuse(*a, **k):
        raise AssertionError("a mesh was decoded on a build whose inputs did not change")

    monkeypatch.setattr(geo, "load_triangles", refuse)
    d2, _, r2 = run(tree, cache=cache)
    assert r2["contact_stats"] == {"computed": 0, "cached": n, "kept": 0} and r2["contact_capped"] == 6 and d2 == d1


def test_a_stored_shift_over_the_cap_is_removed_when_the_meshes_cannot_be_read(tree):
    rules = W.sight_rules()
    rules["attachment_rules"]["contact"]["cap_m"] = 0.06
    d, _, _ = run(tree, rules)
    records = deepcopy(d["weapons"])
    stored = dirmod._stored_shifts(records)
    assert stored[(M.pid(M.SCOPE_PART), M.hid("Gap40"))] == -0.04 and stored[(M.pid(M.SCOPE_PART), M.hid("Gap25"))] == -0.025
    for r in records:
        for e in (r.get("attachment") or {}).get("compatible_hosts") or []:
            e.pop("seat_shift_m", None)
    stats = {"computed": 0, "cached": 0, "kept": 0}
    capped = dirmod._apply_contact(records, W.sight_rules(), None, {}, stats, stored)  # no threejs root: every value is the carried one
    assert stats["computed"] == 0 and stats["cached"] == 0 and capped == 6
    by = {r["id"]: r for r in records}
    assert shifts(by, M.SCOPE_PART) == {"Gap25": -0.025, "Gap30": -0.03, "Sunk25": 0.025}  # G1 (S8): the flat optic seats are pending


def alt_world():
    """FAKE_W8M's Gap40 host only, and another pack's scope (x +-0.01, z +-0.03, 50 mm tall: a 0.06 foot on the 0.06 well, not a twin of the 40 mm child)."""
    world = N.cap_world()
    keep = {M.host_id(c) for c in ("Gap40",)}
    world[M.PACK] = {"hosts": {k: v for k, v in world[M.PACK]["hosts"].items() if k in keep}, "parts": {}}
    world[N.PACK] = {"parts": {"SM_Wep_Alt_Scope_01": lambda: N.G.box((-0.01, 0.0, -0.03), (0.01, 0.05, 0.03))}}
    return world


def test_a_part_that_loses_its_last_cross_pack_entry_loses_the_compat_cross_pack_reason(tmp_path):
    rules = W.sight_rules(genre_by_pack={M.PACK: "fixture", N.PACK: "fixture"})
    alt = N.pid("SM_Wep_Alt_Scope_01")

    kept = deepcopy(rules)
    kept["attachment_rules"]["contact"]["cap_m"] = 0.06   # the cap off: the pair is listed, with the reason
    by = W.by_id(W.build(tmp_path / "off", alt_world(), rules=kept)[0])
    assert [(e["tier"], e["seat_shift_m"]) for e in by[alt]["attachment"]["compatible_hosts"]] == [("cross_pack_fit", -0.04)]
    assert "compat_cross_pack" in by[alt]["review"]["reasons"]

    by = W.by_id(W.build(tmp_path / "on", alt_world(), rules=rules)[0])
    assert by[alt]["attachment"]["compatible_hosts"] == [] and by[alt]["attachment"]["pending_hosts"] == []
    assert "compat_cross_pack" not in by[alt]["review"]["reasons"]


# -- the table validates -----------------------------------------------------------------------------------------------------


def broken(mutate):
    rules = deepcopy(load_rules())
    mutate(rules["attachment_rules"]["contact"])
    return validate_rules(rules)


@pytest.mark.parametrize(("mutate", "needle"), [
    (lambda c: c.pop("cap_m"), "cap_m"),                    # required
    (lambda c: c.update(cap_m=0.0), "cap_m"),
    (lambda c: c.update(cap_m=-0.01), "cap_m"),
    (lambda c: c.update(cap_m=0.061), "cap_m"),             # over the clamp (and over the schema bound of seat_shift_m)
    (lambda c: c.update(cap_m=0.04, clamp_m=0.03), "cap_m must not exceed clamp_m"),
    (lambda c: c.update(cap_m="thirty"), "cap_m"),
    (lambda c: c.update(cap_m=True), "cap_m"),
])
def test_the_cap_rejects_a_malformed_value(mutate, needle):
    errors = broken(mutate)
    assert errors and any(needle in e for e in errors), errors


@pytest.mark.parametrize("cap", [0.03, 0.06, 0.001])
def test_the_cap_accepts_a_value_up_to_the_clamp(cap):
    assert broken(lambda c: c.update(cap_m=cap)) == []
    assert broken(lambda c: c.update(cap_m=0.02, clamp_m=0.02)) == []
