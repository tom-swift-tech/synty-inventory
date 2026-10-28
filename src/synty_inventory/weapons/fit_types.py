"""Types and vocabulary of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.1 step 5, 3.11).

This is the leaf of the ``fit_*`` modules: it imports only the standard library, so the detector modules (``fit_locate``, ``fit_rails``,
``fit_bore``, ``fit_well``) and the facade (``fit_geometry``) all import from here with no import cycle. ``FrameVote`` is NOT here: the
frame vote is record geometry and lives in ``geometry.py`` (spec 3.11).

Vocabulary
----------
``VERDICT_VALUES`` are the four values of ``V(P, H, X)`` (spec 3.1 step 4); ``SIGNALS`` are the geometry evidence names of 3.1 step 5.
``FIT_SLOTS`` are the four slots whose fit is a physical mating (spec 1).

The dicts ``fit_geometry.verdict`` reads (the spec does not fix their shape; this is the minimal explicit one)
------------------------------------------------------------------------------------------------------------
``host_feats``: the features of ONE host in ONE slot, as the later wiring (S7/S8) builds them from the detectors. A missing key is
the same as ``None`` / ``False``. Lengths are metres.

====================  ==========================  ============================================================================================
key                   type                        meaning
====================  ==========================  ============================================================================================
``frame_conflict``    bool                        the host has a frame conflict (spec 3.3 step 4): every slot is ``not_judged``
``frame_body``        bool                        the host's record frame is the voted body frame (3.3 step 3): signal ``frame_body`` is added
``toothed_run``       ``{length_m, width_m}``     optic/underbarrel: the toothed run the slot's seat sits on (``length_m`` is the run length
                                                  after the sight clip of 3.4 step 4; ``width_m`` is ``RailRun.width_m``)
``ref``               ``{flat_run_m,              optic/underbarrel: an authored reference seat (``child_node``/``override``). ``flat_run_m``
                      child_foot_length_m}``      is the length of the flat run containing the reference contact, or ``None`` when no flat run
                                                  covers it (a stepped seat); ``child_foot_length_m`` is the reference child's own
                                                  ``foot_length_m`` (used when ``flat_run_m`` is ``None``)
``flat_seat``         bool                        optic only: a flat seat (3.4 step 3) exists; it lists nothing (``unverified``)
``barrel_end``        ``{od_m, evidence}``        muzzle: the detected barrel end; ``evidence`` is a ``BarrelEnd.evidence`` value
``well_ref``          ``{length_m, width_m}``     magazine: the authored magazine's entry section ``(L_ref, W_ref)`` (3.7 step 1)
====================  ==========================  ============================================================================================

``part``: what the verdict reads of the candidate part.

====================  ==========================  ============================================================================================
key                   type                        meaning
====================  ==========================  ============================================================================================
``anchor_measured``   bool                        the part's anchor was measured (A3.4); False gives ``unverified`` where the host is judged
``foot_length_m``     float or None               optic/underbarrel ``Lp`` (``footprint.foot_length_m``)
``foot_width_m``      float or None               optic/underbarrel ``Wp`` (``footprint.foot_width_m``)
``mate_d_m``          float or None               muzzle: mating ring outer diameter (``footprint.mate_d_m``); None gives ``unverified``
``device_inner_d``    float or None               muzzle: inner bore ring diameter of the mating face; None means the device has no ring
``entry_section``     ``(L_p, W_p)`` or None      magazine: the candidate's entry section at the reference plane; None = empty section (drum)
====================  ==========================  ============================================================================================

``pair_seat``: ``None``, or a dict whose keys ``ref`` (optic/underbarrel) and ``well_ref`` (magazine) replace the host's value of the same
name. It carries the seat a pair actually uses when the slot's mount lists several (spec 3.5, A1) or the twin's own seat (3.7 step 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# spec 3.1 step 4
VERDICT_VALUES = ("fit", "unverified", "no_fit", "not_judged")
# spec 3.1 step 5: the geometry evidence a verdict may name
SIGNALS = ("rail_teeth", "seat_ref", "rail_flat", "barrel_ring", "barrel_round", "well_entry", "drum", "frame_body")
# spec 1: the four slots whose fit is a physical mating
FIT_SLOTS = ("optic", "muzzle", "underbarrel", "magazine")


@dataclass(frozen=True)
class RailRun:
    """A toothed run on a rail (or a flat seat, ``toothed`` False). Spec 3.4."""

    f0: float
    f1: float
    top_u: float
    pitch_m: float
    amp_m: float
    teeth: int
    width_m: float
    toothed: bool  # False only for a flat seat


@dataclass(frozen=True)
class BarrelEnd:
    """The barrel end of a host: its centre in (side, up), the face position along forward, and its OD. Spec 3.6."""

    centre_su: tuple[float, float]
    face_f: float
    od_m: float
    evidence: Literal["ring", "face_ring", "round_section"]


@dataclass(frozen=True)
class WellRef:
    """The authored magazine's reference: the receiver-bottom plane and the entry section. Spec 3.7."""

    u_rb: float
    length_m: float
    width_m: float
    source: Literal["child"]


@dataclass(frozen=True)
class Placement:
    """A part located inside a preset host by translation only. Spec 3.2."""

    part: str
    t: tuple[float, float, float]
    hit: float


@dataclass(frozen=True)
class Verdict:
    """``V(P, H, X)`` and the geometry evidence behind it. Spec 3.1 steps 4 and 5."""

    value: Literal["fit", "unverified", "no_fit", "not_judged"]
    signals: tuple[str, ...]  # SIGNALS vocabulary

    def __post_init__(self) -> None:
        if self.value not in VERDICT_VALUES:
            raise ValueError(f"verdict value {self.value!r} not in {list(VERDICT_VALUES)}")
        bad = [s for s in self.signals if s not in SIGNALS]
        if bad:
            raise ValueError(f"signals {bad} not in {list(SIGNALS)}")
