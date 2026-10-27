"""G1 S2: the ``attachment_rules.fit_geometry`` block and its validator (docs/weapon_attach_geometry.md 4.1, 4.6; plan S2 "section 4.1").

The shipped block is compared with a literal copy of spec 4.1 (no ``frame:`` key). The validator rejects a missing key, a negative length and an
inverted interval, one test each (plus a sweep that every single key is required). Deliberate breaks, in a scratch copy:

* a missing key: the required-key loop dropped (``test_the_validator_rejects_a_missing_key``, ``..._every_key_is_required``);
* a negative length: the non-negative check dropped (``test_the_validator_rejects_a_negative_length``, ``..._every_length``);
* an inverted interval: the lo-above-hi check dropped (``test_the_validator_rejects_an_inverted_interval``);
* the block placed outside ``attachment_rules``: ``rules_digest`` moves (``test_the_block_moves_attach_rules_digest_and_never_rules_digest``).
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from synty_inventory.weapons.rules import attach_rules_digest, load_rules, validate_rules, weapon_rules_digest

# spec 4.1, written out
BLOCK = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {
        "window_m": 0.010, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005, "pitch_max_m": 0.040,
        "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85], "default_seat_len_m": 0.20, "sight_clear_m": 0.010,
    },
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.060},
    "clamp": {"overhang_max_m": 0.010, "ratio_min": 1.0},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {
        "end_slab_m": 0.010, "round_min": 0.8, "barrel_od_max_m": 0.060, "od_ratio": [0.85, 2.00], "inner_ratio": [0.47, 1.21],
        "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2,
    },
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}


def rules_with(edit):
    rules = deepcopy(load_rules())
    edit(rules["attachment_rules"]["fit_geometry"])
    return rules


def errors_of(edit):
    return validate_rules(rules_with(edit))


def leaf_paths(block=BLOCK):
    """Every key path of the block: the sections and every key inside them."""
    paths = []
    for key, val in block.items():
        paths.append((key,))
        if isinstance(val, dict):
            paths.extend((key, k) for k in val)
    return paths


def pop_path(table, path):
    for key in path[:-1]:
        table = table[key]
    del table[path[-1]]


def set_path(table, path, value):
    for key in path[:-1]:
        table = table[key]
    table[path[-1]] = value


def test_the_shipped_block_is_spec_4_1_with_no_frame_key_and_validates():
    rules = load_rules()
    assert rules["attachment_rules"]["fit_geometry"] == BLOCK
    assert "frame" not in rules["attachment_rules"]["fit_geometry"]
    assert validate_rules(rules) == []


def test_the_block_sits_inside_attachment_rules_and_not_beside_it():
    rules = load_rules()
    assert "fit_geometry" not in rules


def test_a_rules_table_without_the_block_still_validates():
    rules = deepcopy(load_rules())
    del rules["attachment_rules"]["fit_geometry"]
    assert validate_rules(rules) == []


def test_the_block_moves_attach_rules_digest_and_never_rules_digest():
    base = load_rules()
    assert weapon_rules_digest(base) == "7b9829af37328fe7"
    edited = rules_with(lambda b: b["well"].update(tol=0.16))
    assert validate_rules(edited) == []
    assert weapon_rules_digest(edited) == "7b9829af37328fe7"
    assert attach_rules_digest(edited) != attach_rules_digest(base)
    removed = deepcopy(base)
    del removed["attachment_rules"]["fit_geometry"]
    assert attach_rules_digest(removed) != attach_rules_digest(base) and weapon_rules_digest(removed) == "7b9829af37328fe7"


def test_the_validator_rejects_a_missing_key():
    errors = errors_of(lambda b: b["clamp"].pop("overhang_max_m"))
    assert errors and any("clamp.overhang_max_m" in e and "missing" in e for e in errors), errors


@pytest.mark.parametrize("path", leaf_paths(), ids=lambda p: ".".join(p))
def test_the_validator_requires_every_key(path):
    errors = errors_of(lambda b: pop_path(b, path))
    assert any(".".join(path) in e and "missing" in e for e in errors), errors


def test_the_validator_rejects_a_negative_length():
    errors = errors_of(lambda b: b["rail"].update(window_m=-0.001))
    assert errors and any("rail.window_m" in e and "negative" in e for e in errors), errors


@pytest.mark.parametrize("path", [
    (s, k) for s, keys in [
        ("locator", ["grid_m", "merge_m"]),
        ("rail", ["window_m", "bin_m", "tooth_amp_min_m", "tooth_merge_m", "pitch_min_m", "pitch_max_m", "tooth_h_tol_m", "default_seat_len_m",
                  "sight_clear_m"]),
        ("flat", ["band_m", "close_m", "min_m"]),
        ("clamp", ["overhang_max_m"]),
        ("bore", ["end_slab_m", "barrel_od_max_m", "axis_offset_max_m"]),
        ("well", ["entry_depth_m"]),
    ] for k in keys
], ids=lambda p: ".".join(p))
def test_the_validator_rejects_a_negative_value_for_every_length(path):
    errors = errors_of(lambda b: set_path(b, path, -0.001))
    assert any(".".join(path) in e and "negative" in e for e in errors), errors


def test_a_negative_end_of_an_interval_is_a_negative_length_too():
    errors = errors_of(lambda b: b["bore"].update(od_ratio=[-0.1, 2.0]))
    assert errors and any("bore.od_ratio" in e and "negative" in e for e in errors), errors


def test_the_depth_interval_is_signed_so_a_negative_depth_is_valid():
    assert errors_of(lambda b: b["depth"].update(lo_m=-0.040, hi_m=-0.010)) == []


def test_the_validator_rejects_an_inverted_interval():
    errors = errors_of(lambda b: b["bore"].update(od_ratio=[2.0, 0.85]))
    assert errors and any("bore.od_ratio" in e and "inverted" in e for e in errors), errors


@pytest.mark.parametrize("edit, key", [
    (lambda b: b["rail"].update(zone=[0.85, 0.15]), "rail.zone"),
    (lambda b: b["bore"].update(inner_ratio=[1.21, 0.47]), "bore.inner_ratio"),
    (lambda b: b["rail"].update(pitch_min_m=0.050, pitch_max_m=0.040), "rail"),
    (lambda b: b["depth"].update(lo_m=0.010, hi_m=0.003), "depth"),
], ids=["zone", "inner_ratio", "pitch", "depth"])
def test_every_interval_of_the_block_is_checked_for_inversion(edit, key):
    errors = errors_of(edit)
    assert any(key in e and "inverted" in e for e in errors), errors


def test_a_frame_key_is_an_unknown_key():
    errors = errors_of(lambda b: b.update(frame={"end_slab_m": 0.010}))
    assert errors and any("fit_geometry.frame" in e and "unknown key" in e for e in errors), errors


def test_an_unknown_key_inside_a_section_is_rejected():
    errors = errors_of(lambda b: b["well"].update(extra=1))
    assert any("well.extra" in e and "unknown key" in e for e in errors), errors


@pytest.mark.parametrize("edit, key", [
    (lambda b: b.update(slots=[]), "slots"),
    (lambda b: b.update(slots=["optic", "laser_light"]), "slots"),
    (lambda b: b.update(slots=["optic", "optic"]), "slots"),
    (lambda b: b.update(exceptions=["a", 3]), "exceptions"),
    (lambda b: b["locator"].update(sample_n=0), "locator.sample_n"),
    (lambda b: b["locator"].update(sample_n=24.5), "locator.sample_n"),
    (lambda b: b["locator"].update(hit_min=0.0), "locator.hit_min"),
    (lambda b: b["locator"].update(hit_min=1.5), "locator.hit_min"),
    (lambda b: b["bore"].update(round_min=1.2), "bore.round_min"),
    (lambda b: b["bore"].update(axis_tilt_max_deg=120), "bore.axis_tilt_max_deg"),
    (lambda b: b["well"].update(tol=True), "well.tol"),
    (lambda b: b["rail"].update(zone=[0.15]), "rail.zone"),
    (lambda b: b.update(clamp=[1, 2]), "clamp"),
], ids=lambda x: x if isinstance(x, str) else "")
def test_the_validator_rejects_a_value_of_the_wrong_kind_or_range(edit, key):
    errors = errors_of(edit)
    assert any(key in e for e in errors), errors
