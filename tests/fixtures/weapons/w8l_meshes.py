"""FAKE_* vertex clouds for the W8l anchor tests (docs/weapon_attachments.md 3.4 steps 1a and 3b; AC105, AC107).

``measure_anchor`` reads vertices only (extents, a foot slab, end sections), so these are boxes given by their eight corners; nothing is
from a real pack. Every expected number in the tests is a LITERAL worked out by hand from the dimensions below, never read from the code
under test. Y-up, metres, a part hangs from a foot at y 0 (slots ``magazine``, ``underbarrel``); ``flip_y`` makes the foot stand at the
bottom (slots ``optic``, ``laser_light``, ``sight_front``).

``banana(lean)``  a magazine 0.20 m tall (y -0.20..0) whose lower quarter leans ``lean`` metres toward +z (negative: toward -z):

    foot slab    x +-0.010, y -0.004..0,      z -0.010..0.010        (centre z 0.000)
    upper body   x +-0.010, y -0.140..-0.004, z -0.010..0.010
    back plate   x +-0.030, y -0.140..-0.010, z -0.050..-0.040       (the larger end section sits at -z)
    lower box    x +-0.010, y -0.200..-0.140, z lean-0.010..lean+0.010

  The 4 mm foot slab is y >= -0.004 (the foot box only: the plate tops out at y -0.010). The free end is the lowest quarter, y <= -0.15: only
  the lower box reaches it, so the displacement of the free end against the foot is exactly ``lean`` along z. The end sections along z
  (the longer horizontal axis, 0.07 or more against x 0.06) are, for a lean of 0.009 / 0.011 / 0.030: the -z end holds the plate
  (x 0.06 x y 0.136 = 8.16e-3) and the +z end holds the foot and body face and the lower box (x 0.02 x y 0.20 = 4.0e-3) or the lower box
  alone (x 0.02 x y 0.06 = 1.2e-3): ratio above 1.15 in every case, the larger end at -z, so the section rule says -z for all three.

``lipped_ridge()``  a part 0.24 m tall hanging from a ridge: ridge x +-0.0105, y -0.005..0, z -0.002..0.002 (4 mm along z, 21 mm across); body
  x +-0.0105, y -0.240..-0.005, z -0.015..0.035 (50 mm, centre z 0.010). The 4 mm slab (y >= -0.004) is the ridge top only: 4 mm x 21 mm. The
  8 mm slab (y >= -0.008) reaches the body top at y -0.005: z -0.015..0.035 (50 mm) x 21 mm, centre z 0.010.
"""

from __future__ import annotations

import numpy as np


def box(lo, hi) -> np.ndarray:
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], dtype=np.float64)


def cloud(*boxes) -> np.ndarray:
    return np.concatenate(boxes)


def flip_y(v: np.ndarray) -> np.ndarray:
    return v * np.array([1.0, -1.0, 1.0])


def flip_z(v: np.ndarray) -> np.ndarray:
    return v * np.array([1.0, 1.0, -1.0])


def banana(lean: float) -> np.ndarray:
    return cloud(
        box((-0.010, -0.004, -0.010), (0.010, 0.0, 0.010)),
        box((-0.010, -0.140, -0.010), (0.010, -0.004, 0.010)),
        box((-0.030, -0.140, -0.050), (0.030, -0.010, -0.040)),
        box((-0.010, -0.200, lean - 0.010), (0.010, -0.140, lean + 0.010)),
    )


def lipped_ridge() -> np.ndarray:
    return cloud(
        box((-0.0105, -0.005, -0.002), (0.0105, 0.0, 0.002)),
        box((-0.0105, -0.240, -0.015), (0.0105, -0.005, 0.035)),
    )


def post_on_base() -> np.ndarray:
    """An iron-sight post standing on a base, foot at y 0 (use with ``flip_y`` NOT applied; slot ``sight_front`` wants the foot at the bottom).

    post x +-0.006, y 0..0.030, z +-0.00215 (12 mm x 4.3 mm: 4.3 mm deep at the 4, 8 and 16 mm rungs alike up to y 0.012); a base plate
    x +-0.006, y 0.012..0.020, z +-0.020 sits above the 8 mm rung (y <= 0.008) but inside the 16 mm one (y <= 0.016): a ladder that
    stepped here would read the 40 mm base instead of the 4.3 mm post.
    """
    return cloud(
        box((-0.006, 0.0, -0.00215), (0.006, 0.030, 0.00215)),
        box((-0.006, 0.012, -0.020), (0.006, 0.020, 0.020)),
    )


def stub_over_body() -> np.ndarray:
    """A 2.5 mm stub on a body: stub x +-0.010, y -0.005..0, z +-0.00125; body x +-0.010, y -0.100..-0.005, z +-0.020 (40 mm)."""
    return cloud(
        box((-0.010, -0.005, -0.00125), (0.010, 0.0, 0.00125)),
        box((-0.010, -0.100, -0.020), (0.010, -0.005, 0.020)),
    )


def line_contact() -> np.ndarray:
    """A wedge standing on an edge, foot at y 0: the edge x -0.02, 0, 0.02 at z 0 (three points, extent 0 along z), a body above x +-0.02, z +-0.03."""
    edge = np.array([[-0.02, 0.0, 0.0], [0.0, 0.0, 0.0], [0.02, 0.0, 0.0]])
    return cloud(edge, box((-0.02, 0.020, -0.03), (0.02, 0.040, 0.03)))


def ridge_over_ridge() -> np.ndarray:
    """A hanging part with a thin ridge (4 mm along z, 2 mm across) over a plate (10 mm x 4 mm) over a base (50 mm x 21 mm):

    ridge  x +-0.001,  y -0.003..0,       z +-0.002   -> the whole 4 mm slab: 4 mm x 2 mm
    plate  x +-0.002,  y -0.007..-0.005,  z +-0.005   -> joins at the 8 mm rung: 10 mm x 4 mm
    base   x +-0.0105, y -0.013..-0.011,  z +-0.025   -> joins at the 16 mm rung: 50 mm x 21 mm
    body   x +-0.0105, y -0.240..-0.020,  z +-0.030   -> below every rung (the total height is 0.24)

    Rung 0 is a lip along z (4 mm, the next rung 10 mm >= 8); rung 1 is not a lip along z (10 mm) but IS one along x (4 mm, the next rung
    21 mm >= 8), so the ladder takes both steps and ends at the 16 mm rung: foot 0.050 x 0.021.
    """
    return cloud(
        box((-0.001, -0.003, -0.002), (0.001, 0.0, 0.002)),
        box((-0.002, -0.007, -0.005), (0.002, -0.005, 0.005)),
        box((-0.0105, -0.013, -0.025), (0.0105, -0.011, 0.025)),
        box((-0.0105, -0.240, -0.030), (0.0105, -0.020, 0.030)),
    )
