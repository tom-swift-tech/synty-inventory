"""FAKE_* vertex clouds for the E3.7 foot mid-line tests (docs/weapon_attachments.md 3.4 step 1b; AC107, AC134).

``measure_anchor`` reads vertices only, so each part is a few boxes given by their eight corners; nothing is from a real pack. Every expected
number in the tests is a LITERAL worked out by hand from the dimensions below, never read from the code under test. Metres, Y-up. The parts
stand on a foot at y 0 (slots ``optic``, ``laser_light``, ``sight_front``, ``sight_rear``); ``flip_y`` hangs one from a foot at y 0 instead
(slots ``underbarrel``, ``magazine``). ``forward`` is z in all of them (the longer horizontal axis), ``right`` is x. The foot slabs are the
corners with y <= 0.004 / 0.008 / 0.016 (the rungs of ``foot_depths_m``).

``side_hook_part()``  a 33.3 mm base on a 6.2 mm side hook (the shape E3.7 is about; the dimensions are the errata's worked example):

    hook    x 0.0130..0.0192, y 0.000..0.010, z -0.0581..0.0581   (6.2 mm across, 116.2 mm long; centre x 0.0161)
    base    x -0.0140..0.0193, y 0.010..0.040, z -0.0500..0.0500  (33.3 mm across)

  whole extent along x: -0.0140..0.0193 (33.3 mm); MID-LINE x = 0.00265. The hook sits inside that span, off the mid-line (13.45 mm).
  4 mm and 8 mm slabs: the hook's bottom corners only: x 0.0130..0.0192 (6.2 mm, over the 4.5 mm lip limit), z 116.2 mm; centre x 0.0161.
  They do not hold the mid-line. 16 mm slab (y <= 0.016: the hook's top corners at y 0.010 and the base's bottom corners at y 0.010):
  x -0.0140..0.0193 = 33.3 mm, z -0.0581..0.0581 = 116.2 mm, centre x 0.00265, z 0. It holds the mid-line. Without the rule the ladder stops
  at the 4 mm rung: width 0.0062, point x 0.0161. A host run 16.4 mm wide centred at x 0 (the test's own literal) reads ratio 0.0062 / 0.0164 =
  0.378 without the rule and 0.0333 / 0.0164 = 2.03 with it.

``narrow_pad_on_mid_line()``  a 9.5 mm pad under a wide body:

    pad     x -0.00475..0.00475, y 0.000..0.012, z -0.030..0.030
    body    x -0.0200..0.0200, y 0.012..0.040, z -0.045..0.045

  mid-line x 0. 4 mm slab: the pad's bottom corners, x 9.5 mm, z 60 mm, centre (0, 0, 0): it holds the mid-line and is not a lip (9.5 mm is
  over 4.5 mm). The ladder stops at rung 0 with or without the rule.

``lip_on_mid_line()``  a ridge (a true narrow lip) on the mid-line over a body 50 mm long:

    ridge   x -0.0105..0.0105, y 0.000..0.005, z -0.002..0.002    (4 mm along z, 21 mm across)
    body    x -0.0105..0.0105, y 0.005..0.240, z -0.015..0.035

  mid-line x 0. 4 mm slab: the ridge's bottom corners, 4 mm along z, a lip (the 8 mm slab is 50 mm: over 2.0 times); it holds the mid-line.
  8 mm slab (ridge bottom corners at y 0, ridge top and body bottom corners at y 0.005): x 21 mm, z -0.015..0.035 = 50 mm, centre (0, 0, 0.010).
  Not a lip (the 16 mm slab is the same set). Result with or without the rule: the 8 mm rung.

``no_rung_holds_the_mid_line()``  a foot entirely on one side, under a body on the other:

    toe     x 0.022..0.028, y 0.000..0.006, z -0.030..0.030        (6 mm across)
    step    x 0.016..0.030, y 0.006..0.016, z -0.030..0.030        (14 mm across)
    body    x -0.030..0.000, y 0.020..0.040, z -0.045..0.045

  whole extent along x: -0.030..0.030, MID-LINE x 0. 4 mm slab: the toe's bottom corners, x 0.022..0.028. 8 mm slab (adds the step's bottom
  corners at y 0.006): x 0.016..0.030. 16 mm slab (adds the step's top corners at y 0.016): the same. None holds x 0 (the body's lowest corners
  are at y 0.020). The ladder as before: rung 0 is 6 mm across, over the lip limit, so it stops there: width 0.006, length 0.060, centre
  x 0.025. (A rule that took the deepest rung when none holds the mid-line would read 0.014.)
"""

from __future__ import annotations

import numpy as np


def box(lo, hi) -> np.ndarray:
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], dtype=np.float64)


def cloud(*boxes) -> np.ndarray:
    return np.concatenate(boxes)


def flip_y(v: np.ndarray) -> np.ndarray:
    return v * np.array([1.0, -1.0, 1.0])


def side_hook_part() -> np.ndarray:
    return cloud(
        box((0.0130, 0.0, -0.0581), (0.0192, 0.010, 0.0581)),
        box((-0.0140, 0.010, -0.0500), (0.0193, 0.040, 0.0500)),
    )


def narrow_pad_on_mid_line() -> np.ndarray:
    return cloud(
        box((-0.00475, 0.0, -0.030), (0.00475, 0.012, 0.030)),
        box((-0.0200, 0.012, -0.045), (0.0200, 0.040, 0.045)),
    )


def lip_on_mid_line() -> np.ndarray:
    return cloud(
        box((-0.0105, 0.0, -0.002), (0.0105, 0.005, 0.002)),
        box((-0.0105, 0.005, -0.015), (0.0105, 0.240, 0.035)),
    )


def no_rung_holds_the_mid_line() -> np.ndarray:
    return cloud(
        box((0.022, 0.0, -0.030), (0.028, 0.006, 0.030)),
        box((0.016, 0.006, -0.030), (0.030, 0.016, 0.030)),
        box((-0.030, 0.020, -0.045), (0.000, 0.040, 0.045)),
    )
