"""E3.8 ``clamp.ratio_min`` 0.69 (docs/weapon_attach_geometry.md 4.1, 4.2, AC134, AC137; errata E3).

``attach-calibrate`` is driven over a SYNTHETIC oracle: ``_gather_oracle`` is replaced by a fixed observation list, so no world, GLB or pack is read. The
toothed positives are the ratios 0.80, 1.5 and 3.0 (foot width over run width); every bound below is this test's own literal (0.80 the smallest
positive, 0.85 the overridden literal), never read from the constants under test. The shipped-rules case reads the ``clamp.ratio_min`` ROW, not the exit
code of the whole run: the other literals of the shipped block are not this test's business.

Deliberate break: the shipped ``ratio_min`` back at 1.0 turns the first test red (1.0 lies above the 0.80 positive: ``exceeded``).
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("review_helpers")

from synty_inventory.weapons import cli as wcli  # noqa: E402
from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import guards, rules as rules_mod  # noqa: E402

# this test's own literal block (the G1 spec 4.1 shape, ratio_min at its E3.8 value 0.69); the override cases change only ratio_min on it
FIT = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {"window_m": 0.01, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005, "pitch_max_m": 0.04,
             "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85], "default_seat_len_m": 0.2,
             "sight_clear_m": 0.01},
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.06},
    "clamp": {"overhang_max_m": 0.01, "ratio_min": 0.69},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {"end_slab_m": 0.01, "round_min": 0.8, "circ_min": 0.75, "barrel_od_max_m": 0.06, "od_ratio": [0.85, 2.0], "inner_ratio": [0.47, 1.21],
             "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2},
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}
POSITIVE_RATIOS = [0.80, 1.5, 3.0]  # the three toothed optic positives; the smallest, 0.80, is the bound under test


def obs(key, value, cls="baked", slot="optic"):
    return {"key": key, "value": value, "cls": cls, "slot": slot, "host": "P/Host", "part": "P/Part", "tags": [f"{slot}:{cls}"]}


def observations(ratios):
    """One positive per other literal of 4.2, inside ``FIT``, so a run fails only where a case makes it; plus one ratio observation per entry of ``ratios``."""
    rest = [
        obs("overhang", 0.008), obs("zone", 0.4), obs("depth", 0.0),
        obs("od_ratio", 1.5, slot="muzzle"), obs("inner_ratio", 0.71, slot="muzzle"), obs("axis_offset", 0.0, slot="muzzle"),
        obs("axis_tilt", 0.0, slot="muzzle"), obs("circ", 0.827, cls="preset", slot="muzzle"), obs("well_off", 0.0, slot="magazine"),
        {"key": "frame_ring", "value": 0.015, "cls": "frame", "slot": None, "host": "P/Host", "part": "P/Part", "tags": []},
    ]
    return [obs("ratio", r) for r in ratios] + rest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    monkeypatch.setattr(export_mod, "_repo_root", lambda: None)  # pytest's tmp dirs sit inside this checkout
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def verb(tmp_path, capsys, monkeypatch):
    """``run(ratios, rules=None) -> (exit code, parsed report)``: the real verb over a synthetic oracle (``rules`` None keeps the SHIPPED rules)."""
    cat = tmp_path / "catalogs"
    cat.mkdir()
    directory = tmp_path / "directory.json"
    directory.write_text("{}\n", encoding="utf-8")
    cfg = H.write_config(tmp_path, cat, extra=[f'threejs_v2: "{tmp_path.as_posix()}"'])

    def run(ratios, rules=None):
        if rules is not None:  # the shipped rules with the fit_geometry block replaced by this test's literal block
            shipped = rules_mod.load_rules()
            shipped["attachment_rules"]["fit_geometry"] = rules
            monkeypatch.setattr(rules_mod, "load_rules", lambda path=None: shipped)
        oracle = {"observations": observations(ratios), "toothed": [], "frame": [], "positives": {}, "hosts": 1, "preset_only_hosts": 0, "skipped": {},
                  "not_positives": {}, "placements": {}}
        monkeypatch.setattr(wcli, "_gather_oracle", lambda directory_, threejs, rules_, packs: oracle)
        return H.run(cfg, capsys, ["weapons", "attach-calibrate", "--directory", str(directory)])

    return run


def row(out, literal):
    return next(r for r in out["rows"] if r["literal"] == literal)


def test_ac137_shipped_ratio_min_clears_a_080_positive(verb):
    # AC134: a toothed optic's ratio >= the literal. The shipped literal must lie at or under the smallest positive (1.0 sat above 0.80: `exceeded`)
    code, out = verb(POSITIVE_RATIOS)
    ratio = row(out, "clamp.ratio_min")
    assert (ratio["n"], ratio["observed"]) == (3, 0.8)
    assert ratio["ok"] is True
    assert all(f["literal"] != "clamp.ratio_min" for f in out["failed"])


def test_ac137_rules_overridden_to_0_85_exit_6_names_the_literal(verb):
    rules = copy.deepcopy(FIT)
    rules["clamp"]["ratio_min"] = 0.85  # above the 0.80 positive
    code, out = verb(POSITIVE_RATIOS, rules)
    assert code == 6 and out["ok"] is False
    assert out["failed"] == [{"literal": "clamp.ratio_min", "reason": "exceeded"}]
    assert row(out, "clamp.ratio_min")["observed"] == 0.8 and row(out, "clamp.ratio_min")["violations_n"] == 1


def test_ac137_no_positives_exit_6(verb):
    code, out = verb([], copy.deepcopy(FIT))  # the same rules, no toothed positive at all
    assert code == 6 and out["ok"] is False
    assert out["failed"] == [{"literal": "clamp.ratio_min", "reason": "no_positives"}]
    assert row(out, "clamp.ratio_min")["covered"] is False
