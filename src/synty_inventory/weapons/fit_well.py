"""Magazine well reference of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.7 steps 1 and 2; plan slice S6).

The receiver is solid where a magazine enters, so the host side of the magazine verdict is the authored magazine's own **entry section**:

* ``crossings`` casts a vertical line (along ``u``) through a mesh and lists where it meets triangles;
* ``well_reference`` finds the receiver-bottom plane ``u_rb`` (the lowest HOST crossing above the reference magazine's top-face centre) and
  cuts the reference magazine at ``u_rb - entry_depth_m`` to get ``(L_ref, W_ref)``;
* ``entry_section`` is that cut, for any magazine mesh: the verdict (``fit_geometry.verdict``, step 3) compares a candidate's cut at the same plane.

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring). All meshes are in the host's (f, s, u) frame (forward, side, up): column 0, 1, 2.
"""

from __future__ import annotations

import numpy as np

from .fit_types import WellRef

# Spec 3.7 step 1: the line probe is moved this far off an edge or vertex. The offset is (_OFFSET_M, _OFFSET_M * _OFFSET_RATIO) in (f, s): the
# irrational-looking ratio keeps the probe off a quad's diagonal (a box face is two triangles whose shared diagonal passes through the face
# centre, which is exactly where a magazine's top-face centre line goes), so a line is neither counted twice (once per triangle) nor missed.
_OFFSET_M = 1e-5
_OFFSET_RATIO = 1.6180339887
# Vertices within this of the highest vertex are the magazine's top face (the storage rounding of spec 4.3; a vertex-density-free definition).
_TOP_FACE_M = 1e-4
_AREA_EPS = 1e-18  # a projected triangle of smaller area (a vertical wall seen from above) cannot be crossed transversally


def _r(x) -> float:
    """Round to 1e-4 m (spec 4.3); ``+ 0.0`` turns -0.0 into 0.0."""
    return round(float(x), 4) + 0.0


def _mesh(verts, tris) -> tuple[np.ndarray, np.ndarray]:
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    return v, t


def crossings(verts_fsu, tris, f: float, s: float) -> list[float]:
    """The ``u`` coordinates, ascending, where the vertical line through ``(f, s)`` crosses the triangles (spec 3.7 step 1).

    The probe is first moved by ``(1e-5, 1e-5 x phi)`` m in (f, s) (see ``_OFFSET_M``) so a line through an edge or a vertex is not counted
    once per triangle that shares it, or missed. A triangle is crossed when the offset probe lies inside its (f, s) projection (closed test);
    ``u`` is the barycentric interpolation of the three vertices. A triangle with no projected area (a vertical wall) is skipped. A closed mesh
    gives an even count. Returns ``[]`` when the line misses the mesh.
    """
    v, t = _mesh(verts_fsu, tris)
    if len(t) == 0:
        return []
    px = float(f) + _OFFSET_M
    py = float(s) + _OFFSET_M * _OFFSET_RATIO
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    # twice the signed projected area, and the barycentric weights as edge functions of the probe
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    w_a = (b[:, 0] - px) * (c[:, 1] - py) - (b[:, 1] - py) * (c[:, 0] - px)
    w_b = (c[:, 0] - px) * (a[:, 1] - py) - (c[:, 1] - py) * (a[:, 0] - px)
    w_c = area - w_a - w_b
    sign = np.where(area >= 0.0, 1.0, -1.0)  # orientation-free: the weights share the sign of the area when the probe is inside
    ok = (np.abs(area) > _AREA_EPS) & (w_a * sign >= 0.0) & (w_b * sign >= 0.0) & (w_c * sign >= 0.0)
    if not ok.any():
        return []
    k = np.flatnonzero(ok)
    u = (w_a[k] * a[k, 2] + w_b[k] * b[k, 2] + w_c[k] * c[k, 2]) / area[k]
    return sorted(float(x) for x in u)


def entry_section(mag_verts_fsu, mag_tris, u_plane: float) -> tuple[float, float] | None:
    """Spec 3.7 steps 1 and 2: the ``(f extent, s extent)`` of the magazine surface cut by the plane ``u = u_plane``, rounded to 1e-4 m.

    Every triangle edge with one end on or above the plane (``u >= u_plane``) and the other strictly below it contributes its crossing point;
    those points are the intersection of the surface with the plane. A vertex exactly on the plane counts as above, one convention for the whole
    mesh, so such a vertex is neither lost nor counted twice. The result is the extent of those points, so it does not depend on the triangle
    order. Returns ``None`` when the plane meets no edge, i.e. the section is empty: a drum, or a part that does not reach the plane (the
    verdict turns it into ``unverified`` with signal ``drum``).
    """
    v, t = _mesh(mag_verts_fsu, mag_tris)
    if len(t) == 0:
        return None
    d = v[t, 2] - float(u_plane)  # (M, 3) height of each triangle corner over the plane
    above = d >= 0.0
    pts = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        cut = above[:, i] != above[:, j]
        if not cut.any():
            continue
        pi, pj = v[t[cut, i]], v[t[cut, j]]
        di, dj = d[cut, i], d[cut, j]
        k = (di / (di - dj))[:, None]  # di and dj differ in sign, so the denominator is never 0
        pts.append(pi[:, :2] + k * (pj[:, :2] - pi[:, :2]))
    if not pts:
        return None
    p = np.concatenate(pts)
    return _r(p[:, 0].max() - p[:, 0].min()), _r(p[:, 1].max() - p[:, 1].min())


def well_reference(host_verts_fsu, host_tris, mag_verts_fsu, mag_tris, rules: dict) -> WellRef | None:
    """Spec 3.7 step 1: the receiver-bottom plane and the entry section of the authored magazine, or None.

    ``host_tris`` is the host's triangle list ALREADY MINUS the reference magazine's own triangles (the caller reduces the mesh, P1 rule; this
    function does not know which triangles are the magazine's). The top-face centre is the midpoint of the f and s extents of the magazine
    vertices within 1e-4 m of its highest one (the extent midpoint, not the vertex mean, so vertex density cannot skew it). ``u_rb`` is the
    lowest host crossing on the vertical line through that centre. The entry section is cut at ``u_rb - rules["well"]["entry_depth_m"]``.

    None when the line meets no host triangle, or the magazine has no usable section there (it does not reach the plane, or the section has no
    length or width: such a reference would divide by zero in the verdict).

    ``source`` is always ``"child"`` (the function sees only meshes and cannot tell a child node from a located preset magazine). The S7 caller
    sets ``"located"`` for a located preset magazine with ``dataclasses.replace(ref, source="located")``.
    """
    mv, mt = _mesh(mag_verts_fsu, mag_tris)
    if len(mv) == 0 or len(mt) == 0:
        return None
    top = mv[mv[:, 2] >= mv[:, 2].max() - _TOP_FACE_M]
    f = (top[:, 0].max() + top[:, 0].min()) / 2.0
    s = (top[:, 1].max() + top[:, 1].min()) / 2.0
    hits = crossings(host_verts_fsu, host_tris, f, s)
    if not hits:
        return None
    u_rb = hits[0]
    section = entry_section(mv, mt, u_rb - float(rules["well"]["entry_depth_m"]))
    if section is None or not section[0] > 0 or not section[1] > 0:
        return None
    return WellRef(u_rb=_r(u_rb), length_m=section[0], width_m=section[1], source="child")
