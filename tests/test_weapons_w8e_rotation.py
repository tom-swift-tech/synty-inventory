"""W8e (b): a second, independent guard for the placement rotation in ``preview.build_job``.

Until now only the shared ``mount_place.json`` three_cycle oracle case caught an inverse-rotation mutant of ``build_job``,
because every other fixture rotation is its own transpose. This pair (``fixtures/weapons/w8e_rot_pair.json``) has a rotation that
is not, and the literals below are derived on paper, not computed with ``attach.place``.

Convention (spec 3.1; ``frame_matrix``): a frame's columns are ``right = up x forward``, ``up``, ``forward``, and the part is
placed by ``M = F_mount * F_anchor^-1``, so the rotation maps each anchor axis onto the same-named mount axis, and the
translation is ``t = p_mount - R p_anchor``.

Anchor: forward (1,0,0), up (0,0,1)  ->  right = up x forward = (0,0,1) x (1,0,0) = (0*0-1*0, 1*1-0*0, 0*0-0*1) = (0,1,0).
Mount:  forward (0,1,0), up (-1,0,0) ->  right = (-1,0,0) x (0,1,0) = (0*0-0*1, 0*0-(-1)*0, (-1)*1-0*0) = (0,0,-1).

R sends anchor right (0,1,0) -> mount right (0,0,-1), anchor up (0,0,1) -> mount up (-1,0,0), anchor forward (1,0,0) -> mount forward
(0,1,0). So R's columns, for the inputs e_x, e_y, e_z, are (0,1,0), (0,0,-1), (-1,0,0):

        | 0  0 -1 |            | 0  1  0 |
    R = | 1  0  0 |    R^T =   | 0  0 -1 |    R != R^T (a signed 3-cycle of the axes; R^T is the inverse).
        | 0 -1  0 |            |-1  0  0 |

Anchor point p_a = (0.01, 0.02, 0.04): R p_a = (-0.04, 0.01, -0.02). Mount point p_m = (0.5, 0.6, 0.7), so
t = p_m - R p_a = (0.54, 0.59, 0.72).

The inverse-rotation mutant (R^T, translation recomputed so the anchor point still lands on the mount point) passes check 1 and
fails checks 2 and 3: R^T e_x = (0,0,-1), not the mount forward (0,1,0).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from synty_inventory.weapons import preview

_FIX = Path(__file__).parent / "fixtures" / "weapons"
PAIR = json.loads((_FIX / "w8e_rot_pair.json").read_text(encoding="utf-8"))

R_LITERAL = np.array([[0, 0, -1], [1, 0, 0], [0, -1, 0]], dtype=float)
T_LITERAL = np.array([0.54, 0.59, 0.72])
P_ANCHOR = np.array([0.01, 0.02, 0.04])
P_MOUNT = np.array([0.5, 0.6, 0.7])
# anchor axis -> the mount axis it must land on (hand-derived above)
AXES = {"forward": ((1, 0, 0), (0, 1, 0)), "up": ((0, 0, 1), (-1, 0, 0)), "right = up x forward": ((0, 1, 0), (0, 0, -1))}


def job_matrix() -> np.ndarray:
    pair = {"part": "p", "host": "h", "slot": PAIR["slot"], "tier": "twin", "score": 1.0, "twin": True}
    return np.asarray(preview.build_job(pair, PAIR["part"], PAIR["host"], Path("glbs"))["matrix"])


def test_the_fixture_rotation_is_not_its_own_transpose():
    assert not np.array_equal(R_LITERAL, R_LITERAL.T)
    assert np.allclose(R_LITERAL @ R_LITERAL.T, np.eye(3)) and np.isclose(np.linalg.det(R_LITERAL), 1.0)
    # the fixture really carries the frames derived in the module docstring
    assert PAIR["part"]["attachment"]["anchor"] == {"point": [0.01, 0.02, 0.04], "forward": [1, 0, 0], "up": [0, 0, 1]}
    assert PAIR["host"]["geometry"]["mounts"]["optic"]["forward"] == [0, 1, 0]
    assert PAIR["host"]["geometry"]["mounts"]["optic"]["up"] == [-1, 0, 0]


def test_the_jobs_matrix_maps_the_anchor_point_onto_the_mount_point():
    m = job_matrix()
    assert np.allclose(m[:3, :3] @ P_ANCHOR + m[:3, 3], P_MOUNT, atol=1e-9, rtol=0)
    assert np.allclose(m[3], [0, 0, 0, 1])


def test_the_jobs_matrix_maps_each_anchor_axis_onto_its_mount_axis():
    m = job_matrix()
    for name, (anchor_axis, mount_axis) in AXES.items():
        assert np.allclose(m[:3, :3] @ np.array(anchor_axis, dtype=float), mount_axis, atol=1e-9, rtol=0), name


def test_the_jobs_matrix_is_the_hand_derived_rotation_and_translation():
    m = job_matrix()
    assert np.allclose(m[:3, :3], R_LITERAL, atol=1e-9, rtol=0), m[:3, :3]
    assert np.allclose(m[:3, 3], T_LITERAL, atol=1e-9, rtol=0), m[:3, 3]


def test_the_transposed_rotation_with_a_corrected_translation_would_not_pass_the_axis_check():
    """Guards the guard: the inverse-rotation mutant lands the anchor point right and the axes wrong."""
    r_bad = R_LITERAL.T
    t_bad = P_MOUNT - r_bad @ P_ANCHOR
    assert np.allclose(r_bad @ P_ANCHOR + t_bad, P_MOUNT)  # check 1 alone cannot tell it apart
    assert not np.allclose(r_bad @ np.array([1.0, 0, 0]), [0, 1, 0])  # check 2 can
