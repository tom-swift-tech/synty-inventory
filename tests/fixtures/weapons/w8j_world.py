"""FAKE_* packs: synthetic hosts for the W8j tests (docs/weapon_attachments.md 4.6 item 8, 7; AC99-AC103).

Written through ``w8h_world.write_world`` like the W8i fixtures (see w8i_world.py for the helpers reused here). Meshes are boxes; nothing is
from a real pack. Every expected number in the tests is a LITERAL worked out by hand from the dimensions below.

Hosts are +z forward, +y up, x +-0.02, and either the W8h box rifle (receiver top y 0.10, axial extent z -0.2525..0.65) or a SLAB (below).

A slab is a plain host built from boxes: a receiver (top y 0.10, z -0.25..0.05, so the sight probe has a top run to seat the rear sight
on and a post on the forward line is never the highest thing) and a forward line (top y 0.06, z 0.05..0.65). Its length is 0.9
(z -0.25..0.65), so a position p of the host's forward extent is z = -0.25 + 0.9 p, and the detector's 5 mm bins start at z -0.25 (bin k
is z -0.25 + 0.005 k ..). A post is a box on the forward line. Posts are placed 0.5 mm inside their bins on purpose, so that float noise
cannot move a face into the next bin:

  20 mm wide post at 0.8:  z 0.4655..0.4845  -> bins 143..146 (4 bins, 20 mm), centre z 0.475, position 0.8056
  20 mm wide post at 0.4:  z 0.1055..0.1245  -> bins 71..74 (4 bins, 20 mm), centre z 0.115, position 0.4056
   4 mm wide post at 0.8:  z 0.4705..0.4745  -> bin 144 only (1 bin, 5 mm)
  40 mm wide post at 0.8:  z 0.4555..0.4945  -> bins 141..148 (8 bins, 40 mm)

The forward line starts at position 0.333, so a post at 0.4 is on it, in the REAR half of the host.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


X = _load("w8i_world")
W, A, G = X.W, X.A, X.G

SLAB_Z0, SLAB_Z1 = -0.25, 0.65
SLAB_RECEIVER_TOP, SLAB_RECEIVER_END = 0.10, 0.05  # the receiver: y 0.10 over z -0.25..0.05
SLAB_TOP = 0.06  # the forward line, z 0.05..0.65

# (z0, z1) of the post cases, see the module docstring
POST_WIDE_08 = (0.4655, 0.4845)
POST_WIDE_04 = (0.1055, 0.1245)
POST_NARROW_08 = (0.4705, 0.4745)
POST_BROAD_08 = (0.4555, 0.4945)


def slab(rises=(), *, steps=()):
    """A slab host mesh: the receiver box plus the forward line (see the module docstring), and

    ``rises``: [(z0, z1, height)] boxes of that height ABOVE the forward line (a post), and
    ``steps``: [(z, height)] the forward line stepping up by ``height`` at z and staying there to the end of the host.
    """
    parts = [G.box((-0.02, 0.0, SLAB_Z0), (0.02, SLAB_RECEIVER_TOP, SLAB_RECEIVER_END))]
    edges = [SLAB_RECEIVER_END, *[z for z, _ in sorted(steps)], SLAB_Z1]
    tops = [SLAB_TOP]
    for _, h in sorted(steps):
        tops.append(tops[-1] + h)
    for z0, z1, top in zip(edges, edges[1:], tops):
        parts.append(G.box((-0.02, 0.0, z0), (0.02, top, z1)))
    for z0, z1, h in rises:
        parts.append(G.box((-0.02, SLAB_TOP, z0), (0.02, SLAB_TOP + h, z1)))
    return G.merge(*parts)


def slab_host(name: str, rises=(), *, steps=(), kids=()):
    return W.host_node(name, slab(rises, steps=steps), [W.kid(name, s, m, at) for s, m, at in kids])


def sheet():
    """A glass sheet: 3 mm thick (y), 20 x 40 mm, to be moved over the receiver top (y 0.10)."""
    return X.block(0.010, 0.0015, 0.020)


def optic_part():
    """An optic part stand-in (the W8a optic, a scope tube with a foot)."""
    return A.optic()
