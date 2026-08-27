"""T3: schema registration + write-time validation of the footprint block."""

from __future__ import annotations

import copy

from synty_inventory.enrich import ensure_schema_defaults
from synty_inventory.schema import (
    FOOTPRINT_CLASSES,
    SEMANTIC_FIELDS,
    validate_footprint,
)

BOUNDS = {"min": [0.0, 0.0, 0.0], "max": [5.0, 3.0, 5.0], "size": [5.0, 3.0, 5.0], "pivot": "corner", "source": "measured"}

GOOD = {
    "polygon_m": [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]],
    "components": 1,
    "area_m2": 25.0,
    "grade_area_m2": 25.0,
    "overhang_ratio": 0.0,
    "fill_ratio": 1.0,
    "class": "compact",
    "radius_m": None,
    "tile_cells": [1, 1],
    "snap_m": 0.25,
    "grade_band_m": [0.0, 0.5],
    "source": "measured",
    "version": 1,
}


def errs(footprint, bounds=BOUNDS):
    out: list[str] = []
    validate_footprint(footprint, bounds, "assets[0]", out)
    return out


def bad(**over):
    fp = copy.deepcopy(GOOD)
    fp.update(over)
    return fp


def test_footprint_is_lockable():
    """A human must be able to lock a footprint, same as any other enriched
    field -- which only works if merge.py knows the field exists."""
    assert "footprint" in SEMANTIC_FIELDS


def test_good_block_passes():
    assert errs(GOOD) == []


def test_null_is_legitimate():
    """Analysed-and-failed is a valid state, not a schema error."""
    assert errs(None) == []


def test_rejects_escaping_polygon():
    fp = bad(polygon_m=[[0.0, 0.0], [9.0, 0.0], [9.0, 9.0], [0.0, 9.0]], area_m2=81.0)
    assert any("escapes bounds" in e for e in errs(fp))


def test_rejects_area_over_bounds():
    assert any("exceeds the bounds footprint" in e for e in errs(bad(area_m2=100.0)))


def test_rejects_clockwise_ring():
    fp = bad(polygon_m=[[0.0, 0.0], [0.0, 5.0], [5.0, 5.0], [5.0, 0.0]])
    assert any("counter-clockwise" in e for e in errs(fp))


def test_rejects_duplicate_vertex():
    fp = bad(polygon_m=[[0.0, 0.0], [5.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]])
    assert any("duplicate vertex" in e for e in errs(fp))


def test_rejects_grade_over_area():
    assert any("grade_area_m2 exceeds" in e for e in errs(bad(grade_area_m2=30.0)))


def test_rejects_fill_ratio_over_one():
    assert any("fill_ratio out of range" in e for e in errs(bad(fill_ratio=1.5)))


def test_accepts_overhang_of_one():
    """A pole-mounted sign has nothing within the grade band, so an overhang
    of exactly 1.0 is legitimate rather than a violation."""
    assert not [e for e in errs(bad(overhang_ratio=1.0, grade_area_m2=0.0)) if "overhang" in e]


def test_rejects_overhang_above_one():
    assert any("overhang_ratio out of range" in e for e in errs(bad(overhang_ratio=1.2)))


def test_rejects_short_ring():
    assert any("ring of >= 4" in e for e in errs(bad(polygon_m=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])))


def test_rejects_unknown_class():
    assert any("class invalid" in e for e in errs(bad(**{"class": "blob"})))


def test_rejects_non_measured_source():
    assert any("source invalid" in e for e in errs(bad(source="vlm")))


def test_radius_required_for_radial():
    assert any("radius_m required" in e for e in errs(bad(**{"class": "radial", "radius_m": None})))


def test_radius_forbidden_when_not_radial():
    assert any("must be null unless class is radial" in e for e in errs(bad(radius_m=2.5)))


def test_rejects_bad_tile_cells():
    assert any("tile_cells" in e for e in errs(bad(tile_cells=[0, 1])))


def test_rejects_zero_components():
    assert any("components" in e for e in errs(bad(components=0)))


def test_every_class_value_is_accepted():
    for name in FOOTPRINT_CLASSES:
        fp = bad(**{"class": name})
        if name == "radial":
            fp["radius_m"] = 2.5
        assert not [e for e in errs(fp) if "class invalid" in e], name


def test_defaults_do_not_inject_footprint():
    """Absent and null are different states. A blanket default would touch
    every record in the store and blow the additive-only guarantee (AC7)."""
    a: dict = {}
    ensure_schema_defaults(a)
    assert "footprint" not in a


def test_defaults_leave_existing_footprint_alone():
    a = {"footprint": copy.deepcopy(GOOD)}
    before = copy.deepcopy(a)
    ensure_schema_defaults(a)
    assert a["footprint"] == before["footprint"]
