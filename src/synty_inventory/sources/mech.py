"""Mech/robot assembly data from POLYGON_Mech vehicle prefabs.

Unlike the ship kit (``sources/sockets.py``), a Synty mech is not a set of
separate part meshes that mate on flat caps -- all 196 named sub-meshes of
one body ("geo_<l|r|c>_<region>[_<detail>]_<NN>") live inside a single
master FBX (``SM_Veh_Mech_01.fbx``), and a "variant" (fighter/heavy/scout/...)
is just which of those 196 nodes are toggled visible. That toggle set is
only recoverable from the Unity ``.prefab`` text (``m_IsActive`` per
renderer, ``m_RootBone`` for the bone it skins to) -- it cannot be measured
from mesh geometry the way a ship part's mating face can. This module:

1. parses the 6 factory ``Prefabs/Vehicles/SM_Veh_Mech_0N.prefab`` files
   into ``{skeleton, slots, variants}`` for the body asset -- one ``slots``
   entry per (region, side, bone) triple with every geo-node name that
   shares it, and one ``variants`` entry per factory prefab listing its
   active node set (60-69 of 196, observed 2026-08-19);
2. resolves each standalone ``MechAttachments/SM_Mech_<Slot>_01_<Kind>_<NN>``
   FBX (bolt-on armor/weapon/frame pieces with no prefab of their own) to
   the ``(region, side, bone)`` it attaches at, from its filename alone.

Region/bone provenance (derived 2026-08-19 by parsing the 6 factory
prefabs -- see ``.parse_mech_prefabs.py`` / ``.mech_prefab_map.json``,
lead-provided ground truth, and cross-checked against every
``MechAttachments`` FBX stem in the extracted tree, 104/104 resolved):

    ankle -> Ankle_<L|R> (heel armor -> AnkleReverse_<L|R>)
    ball -> Ball_<L|R> (also "toes" armor)
    chest / collar / attach / jetpack -> Spine_01 (also "radio"/"battery"
        back-mounted gear, which carries no more specific geo-node analogue
        and defaults to the generic torso attach point)
    clavicle -> Spine_03 (left) / Clavicle_R (right) -- an authored kit
        asymmetry, not a bug; only seen on body geo, no standalone
        attachment uses it
    cockpit -> CockpitDoor (also "monitor"/"shell"/"door" cockpit trim)
    elbow -> Elbow_<L|R> (also "forearm" armor/weapons -- the kit has no
        separate forearm bone, the elbow joint drives that segment)
    exhaust -> Exhaust_<l|r|c>_01
    hand -> Hand_<L|R> (also "wrist" armor)
    head -> Head (also "helmet" armor); one head geo node roots on Neck
        instead but Head is the dominant bone (7/8) and the documented
        default
    hips / cargo -> Hips (also "belt" armor)
    lowerleg -> LowerLeg_<L|R> (also "shin"/"shinpad"/"knee"/"kneepad"
        armor -- confirmed by the body's own
        geo_<l|r>_lowerleg_knee_armor_* / *_shin_armor_* nodes)
    uppershin -> LowerLeg_<L|R> (a body geo region distinct from
        "lowerleg" by name, same bone)
    upperleg -> UpperLeg_<L|R> (also "thigh" armor)
    neck -> Neck
    shoulder -> Shoulder_<L|R>
    index / mid / thumb -> per-segment finger bones (body geo only, no
        standalone attachment uses them)

Standalone attachments carry no ``_l``/``_r`` marker (a single mesh is
placed on either side, sometimes both) -- resolved slots default to
``side="l"`` with a real, concrete bone name (``<Base>_L``); an assembler
mirrors position and ``scale.x = -1`` for the right instance, the same
convention ``sources/sockets.py`` uses for wing root mirroring. Regions
whose bone has no side (Spine_01, CockpitDoor, Hips, Head, Neck,
Exhaust_c_01) resolve to ``side="c"`` instead.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..merge import stamp_auto

MECH_VERSION = 1  # bump to invalidate the cached body parse when the algorithm changes

_BLOCK_RE = re.compile(r"^--- !u!(\d+) &(\d+)", re.M)
_GUID_RE = re.compile(r"^guid: ([0-9a-f]{32})", re.M)
_NAME_RE = re.compile(r"^  m_Name: (.*)$", re.M)
_ACTIVE_RE = re.compile(r"^  m_IsActive: (\d)", re.M)
_MESH_RE = re.compile(r"^  m_Mesh: \{fileID: -?\d+, guid: ([0-9a-f]{32})", re.M)
_ROOTBONE_RE = re.compile(r"^  m_RootBone: \{fileID: (\d+)\}", re.M)
_GAMEOBJECT_RE = re.compile(r"^  m_GameObject: \{fileID: (\d+)\}", re.M)
_FATHER_RE = re.compile(r"^  m_Father: \{fileID: (\d+)\}", re.M)

_GEO_NODE_RE = re.compile(r"^geo_([lrcLRC])_(.+)$")

_FILLER_TOKENS = {"armor", "weapon", "frame", "empty"}

# token (from either a MechAttachments slot folder name or an in-mesh geo
# node detail suffix) -> (canonical region, unsided bone stem, bilateral).
# bilateral=True means the concrete bone is "<stem>_L"/"<stem>_R"; False
# means ``stem`` is already the exact, unsided bone name. See the module
# docstring for the evidence behind each row.
REGION_BONE: dict[str, tuple[str, str, bool]] = {
    "ankle": ("ankle", "Ankle", True),
    "heel": ("ankle", "AnkleReverse", True),
    "ball": ("ball", "Ball", True),
    "toes": ("ball", "Ball", True),
    "shoulder": ("shoulder", "Shoulder", True),
    "elbow": ("elbow", "Elbow", True),
    "forearm": ("elbow", "Elbow", True),
    "hand": ("hand", "Hand", True),
    "wrist": ("hand", "Hand", True),
    "lowerleg": ("lowerleg", "LowerLeg", True),
    "shin": ("lowerleg", "LowerLeg", True),
    "shinpad": ("lowerleg", "LowerLeg", True),
    "knee": ("lowerleg", "LowerLeg", True),
    "kneepad": ("lowerleg", "LowerLeg", True),
    "uppershin": ("uppershin", "LowerLeg", True),
    "upperleg": ("upperleg", "UpperLeg", True),
    "thigh": ("upperleg", "UpperLeg", True),
    "chest": ("chest", "Spine_01", False),
    "collar": ("collar", "Spine_01", False),
    "attach": ("attach", "Spine_01", False),
    "jetpack": ("jetpack", "Spine_01", False),
    "radio": ("attach", "Spine_01", False),
    "battery": ("attach", "Spine_01", False),
    "cockpit": ("cockpit", "CockpitDoor", False),
    "monitor": ("cockpit", "CockpitDoor", False),
    "shell": ("cockpit", "CockpitDoor", False),
    "door": ("cockpit", "CockpitDoor", False),
    "hips": ("hips", "Hips", False),
    "belt": ("hips", "Hips", False),
    "cargo": ("cargo", "Hips", False),
    "head": ("head", "Head", False),
    "helmet": ("head", "Head", False),
    "neck": ("neck", "Neck", False),
    "exhaust": ("exhaust", "Exhaust_c_01", False),
}


# --- Unity .prefab text parsing (adapted from .parse_mech_prefabs.py) --------------


def read_guid_fbx_map(extracted_root: Path) -> dict[str, str]:
    """guid -> fbx filename, from every ``*.fbx.meta`` under the pack."""
    out: dict[str, str] = {}
    for meta in extracted_root.rglob("*.fbx.meta"):
        try:
            head = meta.read_text(encoding="utf-8", errors="replace")[:400]
        except OSError:
            continue
        m = _GUID_RE.search(head)
        if m:
            out[m.group(1)] = meta.with_suffix("").name
    return out


def parse_prefab(path: Path) -> list[dict[str, Any]]:
    """One row per SkinnedMeshRenderer/MeshRenderer node in the prefab:
    ``{"node", "active", "root_bone", "mesh_guid"}``. ``root_bone`` is the
    GameObject name the renderer's ``m_RootBone`` transform belongs to
    (``None`` if the renderer has none, e.g. a static MeshRenderer)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    marks = list(_BLOCK_RE.finditer(text))
    blocks = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        blocks.append((int(m.group(1)), int(m.group(2)), text[m.end():end]))

    go_name: dict[int, str] = {}
    go_active: dict[int, bool] = {}
    tf_go: dict[int, int] = {}
    tf_father: dict[int, int] = {}
    go_tf: dict[int, int] = {}
    renderers: list[tuple[int, str, int | None]] = []
    for cls, fid, body in blocks:
        if cls == 1:  # GameObject
            nm = _NAME_RE.search(body)
            ac = _ACTIVE_RE.search(body)
            go_name[fid] = nm.group(1).strip() if nm else "?"
            go_active[fid] = ac.group(1) == "1" if ac else True
        elif cls == 4:  # Transform
            g = _GAMEOBJECT_RE.search(body)
            f = _FATHER_RE.search(body)
            if g:
                gid = int(g.group(1))
                tf_go[fid] = gid
                go_tf[gid] = fid
            if f:
                tf_father[fid] = int(f.group(1))
        elif cls in (137, 33):  # SkinnedMeshRenderer / MeshFilter+Renderer pair
            g = _GAMEOBJECT_RE.search(body)
            mm = _MESH_RE.search(body)
            rb = _ROOTBONE_RE.search(body)
            if g and mm:
                renderers.append((int(g.group(1)), mm.group(1), int(rb.group(1)) if rb else None))

    def bone_name(tf_fid: int) -> str | None:
        go = tf_go.get(tf_fid)
        return go_name.get(go) if go else None

    rows = []
    for go_fid, guid, rootbone_tf in renderers:
        rows.append(
            {
                "node": go_name.get(go_fid, "?"),
                "active": go_active.get(go_fid, True),
                "root_bone": bone_name(rootbone_tf) if rootbone_tf else None,
                "mesh_guid": guid,
            }
        )
    return rows


def discover_vehicle_prefabs(extracted_root: Path) -> list[Path]:
    """The 6 factory ``Prefabs/Vehicles/SM_Veh_Mech_0N.prefab`` files
    (empty list for packs with no mech vehicle prefabs -- the caller's
    clean no-op signal)."""
    return sorted(
        p
        for p in extracted_root.rglob("*.prefab")
        if p.parent.name == "Vehicles" and re.match(r"^SM_Veh_Mech_\d+$", p.stem)
    )


def discover_attachment_fbx(extracted_root: Path) -> list[Path]:
    """Standalone bolt-on FBX under any ``MechAttachments`` folder."""
    return sorted(p for p in extracted_root.rglob("*.fbx") if p.parent.name == "MechAttachments")


def _parse_geo_node(node: str) -> tuple[str, str] | None:
    """``(region, side)`` from a ``geo_<l|r|c>_<region>[_<detail>]_<NN>``
    node name, or ``None`` for anything else in the prefab (helper
    GameObjects, empties)."""
    m = _GEO_NODE_RE.match(node)
    if not m:
        return None
    side, rest = m.groups()
    region = rest.split("_")[0].lower()
    return region, side.lower()


def build_body_mech(prefab_paths: list[Path], guid_fbx: dict[str, str] | None = None) -> dict[str, Any] | None:
    """Aggregate every prefab's renderer nodes into one body's
    ``{skeleton, slots, variants}`` (see module docstring). When
    ``guid_fbx`` (from ``read_guid_fbx_map``) is given, also returns
    ``_master_fbx``: the distinct mesh FBX names referenced -- expected to
    be exactly one (``SM_Veh_Mech_01.fbx``); more than one means a future
    kit revision split the master mesh and every region/bone assumption
    here needs re-deriving. Not part of the ``asset['mech']`` schema shape
    -- callers pop it before assigning."""
    if not prefab_paths:
        return None
    slots: dict[tuple[str, str, str], set[str]] = {}
    bones: set[str] = set()
    variants: dict[str, list[str]] = {}
    master_fbx: set[str] = set()
    for path in prefab_paths:
        rows = parse_prefab(path)
        active_nodes = []
        for row in rows:
            geo = _parse_geo_node(row["node"])
            bone = row["root_bone"] or "?"
            if geo is not None:
                region, side = geo
                slots.setdefault((region, side, bone), set()).add(row["node"])
            if row["root_bone"]:
                bones.add(row["root_bone"])
            if row["active"]:
                active_nodes.append(row["node"])
            if guid_fbx is not None and row.get("mesh_guid"):
                master_fbx.add(guid_fbx.get(row["mesh_guid"], f"guid:{row['mesh_guid'][:8]}"))
        variants[path.stem] = sorted(active_nodes)
    slot_list = [
        {"region": region, "side": side, "bone": bone, "geo_nodes": sorted(nodes)}
        for (region, side, bone), nodes in sorted(slots.items())
    ]
    return {
        "skeleton": sorted(bones),
        "slots": slot_list,
        "variants": variants,
        "_master_fbx": sorted(master_fbx),
    }


def resolve_attachment_slot(stem: str) -> tuple[str, str, str] | None:
    """``(region, side, attach_bone)`` for one MechAttachments FBX stem
    (e.g. ``SM_Mech_Leg_01_Armor_Kneepad_03`` -> ``("lowerleg", "l",
    "LowerLeg_L")``), or ``None`` when no token in the stem is recognised.
    Scans left to right so a more specific detail token beats a generic
    kind word, but a slot token that IS itself in ``REGION_BONE`` (e.g.
    ``Neck``, ``Cockpit``) wins before a same-bone-but-different-region
    detail token further right (e.g. "Collar") is reached."""
    if not stem.upper().startswith("SM_MECH_"):
        return None
    tokens = stem.split("_")[2:]  # drop "SM", "Mech"
    meaningful = [t.lower() for t in tokens if t.lower() not in _FILLER_TOKENS and not t.isdigit()]
    for tok in meaningful:
        hit = REGION_BONE.get(tok)
        if hit is None:
            continue
        region, bone, bilateral = hit
        if bilateral:
            return region, "l", f"{bone}_L"
        return region, "c", bone
    return None


def _dir_cache_key(paths: list[Path]) -> str | None:
    parts = []
    for p in sorted(paths):
        try:
            st = p.stat()
        except OSError:
            return None
        parts.append(f"{p.name}:{int(st.st_mtime)}:{st.st_size}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def apply_mech_catalog(catalog: dict, cache: dict[str, Any], stats: dict[str, int]) -> None:
    """Fill ``asset['mech']`` on the SM_Veh_Mech_* body assets and
    ``asset['part']['slot']``/``['attach_bone']`` on SM_Mech_* standalone
    attachment assets, for packs whose extracted tree has
    ``Prefabs/Vehicles/SM_Veh_Mech_*.prefab``. Cleanly no-ops (leaves every
    field untouched) when ``catalog['source']['extracted']`` is unset, the
    directory does not exist, or it has no mech vehicle prefabs -- covers
    every pack except POLYGON_Mech, and POLYGON_Mech before/without a
    Unity extraction on disk."""
    extracted = (catalog.get("source") or {}).get("extracted")
    if not extracted:
        return
    root = Path(extracted)
    if not root.is_dir():
        return
    prefab_paths = discover_vehicle_prefabs(root)
    if not prefab_paths:
        return

    pack_id = catalog.get("pack_id") or "?"
    cache_id = f"mech:{pack_id}:body"
    key = _dir_cache_key(prefab_paths)
    body = None
    if key is not None:
        full_key = f"{key}:v{MECH_VERSION}"
        entry = cache.get(cache_id)
        if entry and entry.get("key") == full_key:
            body = entry.get("result")
    if body is None:
        body = build_body_mech(prefab_paths, read_guid_fbx_map(root))
        if key is not None and body is not None:
            cache[cache_id] = {"key": f"{key}:v{MECH_VERSION}", "result": body}
    if body is None:
        return

    by_id = {a.get("id"): a for a in catalog.get("assets") or [] if isinstance(a, dict)}

    # every renderer node should skin to the one master FBX; more than one
    # name means a kit revision split the mesh and the region/bone table in
    # this module's docstring needs re-deriving against the new geometry.
    master_fbx = body.get("_master_fbx") or []
    stats["mech_master_fbx_mismatch"] = stats.get("mech_master_fbx_mismatch", 0) + max(0, len(master_fbx) - 1)

    body_hits = 0
    for stem in body["variants"]:
        asset = by_id.get(stem)
        if asset is None:
            continue
        asset["mech"] = {
            "skeleton": list(body["skeleton"]),
            "slots": [dict(s) for s in body["slots"]],
            "variants": {k: list(v) for k, v in body["variants"].items()},
        }
        asset.setdefault("provenance", {})["mech"] = "measured"
        # stamp_auto() seeds _auto["mech"] on first build (rank "measured"
        # already short-circuits the hash-mismatch path in is_human_field(),
        # but leaving _auto unset would leave the field's snapshot dangling
        # -- same convention as enrich.py's per-asset stamp_auto() pass,
        # done here because this field doesn't exist until this call).
        stamp_auto(asset)
        body_hits += 1
    stats["mech_body_assets"] = stats.get("mech_body_assets", 0) + body_hits

    resolved = 0
    unresolved = 0
    for attach_path in discover_attachment_fbx(root):
        asset = by_id.get(attach_path.stem)
        if asset is None:
            continue
        part = asset.setdefault("part", {})
        part.setdefault("mount", None)
        part.setdefault("sockets", None)
        slot = resolve_attachment_slot(attach_path.stem)
        if slot is None:
            part.setdefault("slot", None)
            part.setdefault("attach_bone", None)
            unresolved += 1
            continue
        region, side, bone = slot
        part["slot"] = {"region": region, "side": side}
        part["attach_bone"] = bone
        resolved += 1
    stats["mech_attach_resolved"] = stats.get("mech_attach_resolved", 0) + resolved
    stats["mech_attach_unresolved"] = stats.get("mech_attach_unresolved", 0) + unresolved
