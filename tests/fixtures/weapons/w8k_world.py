"""FAKE_* hosts for the W8k tests (docs/weapon_attachments.md 4.6 item 9; AC104): hosts whose sight probe REFUSES to seat.

Built on the W8h / W8i / W8j helpers (``w8j_world``). Meshes are boxes; nothing is from a real pack. Every expected number in the tests is
a LITERAL worked out by hand from the dimensions below.

prism      the W8h tent (z +-0.1, apex y 0.2, x +-0.02): its top run is under 3 bins, so both sight slots start ``none`` / ``probe_unavailable``.
           Its axial extent is z -0.1..0.1 (the middle z 0) and its height 0.2, so a child centred above y 0.11 is a high one (55 %).

spike slab  the W8j slab (a forward line of top y 0.06 over z -0.25..0.65, 0.9 long; a position p of its extent is z = -0.25 + 0.9 p) with
           the receiver replaced by a SPIKE: a box x +-0.02, y 0.06..0.10, z -0.2495..-0.2405. Its two 5 mm bins (0 and 1) are the highest
           (y 0.10) and the bin after them is 40 mm lower, so the receiver run is 2 bins, under the 3 the probe needs, and the probe refuses the
           host. The profile has 180 populated bins, so the fused front post detector still runs. The spike itself is a 10 mm wide run
           standing 40 mm over its baseline, but at position 0.006: far from the 0.6 a front post needs. A post is a box on the forward
           line, placed 0.5 mm inside its bins like the W8j posts (the literals of ``w8j_world``: 20 mm wide at 0.8 is z 0.4655..0.4845).

short slab  the same shape over z -0.025..0.025 (50 mm, 10 bins): fewer than the 12 populated bins the detector needs, so it has no profile
           to judge, whatever stands on it.
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


J = _load("w8j_world")
X, W, A, G = J.X, J.W, J.A, J.G

SPIKE_TOP = 0.10  # the spike's top; the forward line is J.SLAB_TOP, 0.06


def spike_slab(rises=(), *, z0: float = J.SLAB_Z0, z1: float = J.SLAB_Z1):
    """A forward line of top y 0.06 over z0..z1 and a 2-bin spike at its rear end (see the module docstring), and

    ``rises``: [(z0, z1, height)] boxes of that height ABOVE the forward line (a post).
    """
    parts = [G.box((-0.02, 0.0, z0), (0.02, J.SLAB_TOP, z1)),
             G.box((-0.02, J.SLAB_TOP, z0 + 0.0005), (0.02, SPIKE_TOP, z0 + 0.0095))]
    for a, b, h in rises:
        parts.append(G.box((-0.02, J.SLAB_TOP, a), (0.02, J.SLAB_TOP + h, b)))
    return G.merge(*parts)


def spike_host(name: str, rises=(), *, kids=(), z0: float = J.SLAB_Z0, z1: float = J.SLAB_Z1):
    return W.host_node(name, spike_slab(rises, z0=z0, z1=z1), [W.kid(name, s, m, at) for s, m, at in kids])
