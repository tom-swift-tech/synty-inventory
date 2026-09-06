"""Regression test for the `stats.streets()` `module_m` bug: same-id road
placements stacked at the identical XZ position (a decal duplicated in place)
must not zero out the modal same-id nearest-neighbour distance -- module_m
is a *repeat spacing*, and 0 m also violates the schema's `module_m > 0`
constraint (AC-adjacent to spec §4's "document the exact definitions")."""

from __future__ import annotations

from synty_inventory.scene_mine import stats


def _p(asset_id: str, x: float, z: float, yaw: float = 0.0) -> dict:
    return {"asset_id": asset_id, "pos_m": [x, 0.0, z], "yaw_deg": yaw, "scale": [1.0, 1.0, 1.0]}


def test_module_m_ignores_coincident_same_id_pairs_and_cross_id_stacking():
    roles = {"tile": "road", "decal": "road"}
    scene = [
        # Two "tile" instances stacked at the exact same XZ (e.g. a duplicated
        # placement) -- their mutual nearest-neighbour distance is 0 m and
        # must not become the modal module_m.
        _p("tile", 0.0, 0.0),
        _p("tile", 0.0, 0.0),
        # Real 4 m repeat spacing -- this is the actual tile cadence.
        _p("tile", 4.0, 0.0),
        _p("tile", 8.0, 0.0),
        # A different road-role id ("decal") stacked at the same XZ as the
        # first tile -- a same-position, different-id neighbour that must
        # never leak into the same-id distance pool either.
        _p("decal", 0.0, 0.0),
    ]
    result = stats.streets([scene], roles)
    assert result is not None
    assert result["module_m"] == 4.0
    assert result["module_m"] > 0


def test_module_m_is_none_when_every_same_id_pair_is_coincident():
    roles = {"tile": "road"}
    scene = [_p("tile", 0.0, 0.0), _p("tile", 0.0, 0.0)]
    result = stats.streets([scene], roles)
    assert result is not None
    assert result["module_m"] is None
    assert result["run_lengths_p50"] is None
