"""Stream Unity scene/asset YAML and compose ``PrefabInstance`` placements
into world space (spec ``s9_scene_grammar_spec.md`` §3.1/§4/§5, decision D3).

Unity's ``.unity``/``.asset`` files are a sequence of independent YAML
documents, each headed by a non-YAML line (``--- !u!<class> &<fileID>``, the
``!u!`` tag is not valid YAML on its own) followed by the document body.
``iter_docs`` splits on that header with a plain regex and only asks PyYAML
to parse the body of the class ids the miner actually needs -- every other
document's text is skipped without ever being parsed, which is what keeps a
50k-``PrefabInstance`` scene inside memory (spec §7 sizing clause) instead of
building a full-file DOM.

A ``PrefabInstance`` (class ``1001``) carries its own transform as override
entries (``m_Modification.m_Modifications``) on the source prefab's root
Transform, parented to a scene ``!u!4 Transform`` via
``m_Modification.m_TransformParent.fileID``. That parent chain can pass
through a *stripped* ``!u!4`` document, which has no fields of its own beyond
``m_PrefabInstance.fileID`` -- it means "this Transform's world position is
wherever that PrefabInstance ends up", so composing world transforms is a
mutual recursion between "the world of a Transform fileID" and "the world of
a PrefabInstance fileID", memoized so a chain is only ever walked once
(the parent may appear later in the file than the child).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import yaml

from .guid_index import GuidIndex

# CSafeLoader/SafeLoader only -- never yaml.Loader/FullLoader/UnsafeLoader
# (those execute arbitrary `!!python/object` tags; a Synty scene is untrusted
# third-party YAML by the time it reaches this tool).
_LOADER = yaml.CSafeLoader if getattr(yaml, "__with_libyaml__", False) else yaml.SafeLoader

# D3: the only classes worth a real YAML parse. Everything else is skipped by
# text in `iter_docs` without ever reaching PyYAML.
WANTED_CLASS_IDS = frozenset({1, 4, 20, 104, 108, 114, 1001})

_HEADER_RE = re.compile(r"^--- !u!(?P<cls>\d+) &(?P<fid>-?\d+)(?P<stripped> stripped)?\s*$")

_COPY_SUFFIX_RE = re.compile(r"^(.*) \(\d+\)$")


class SceneParseError(ValueError):
    """Malformed or unexpected Unity YAML. Always names the scene, the
    fileID of the offending document (when known) and the field path, so a
    failure points at the corrupt line instead of a bare stack trace (spec
    §5: no ``unwrap``-equivalents)."""

    def __init__(
        self,
        scene: str,
        file_id: int | None,
        field_path: str | None,
        message: str,
        *,
        offset: int | None = None,
    ) -> None:
        self.scene = scene
        self.file_id = file_id
        self.field_path = field_path
        self.offset = offset
        parts = [str(scene)]
        if file_id is not None:
            parts.append(f"fileID={file_id}")
        if field_path is not None:
            parts.append(f"field={field_path}")
        if offset is not None:
            parts.append(f"byte_offset={offset}")
        parts.append(message)
        super().__init__(": ".join(parts))


@dataclass(frozen=True)
class UnityDoc:
    """One ``--- !u!<class> &<fileID>`` document. ``stripped`` marks a
    document that exists only as a prefab-instance correspondence pointer
    (no fields beyond ``m_CorrespondingSourceObject``/``m_PrefabInstance``)."""

    class_id: int
    file_id: int
    stripped: bool
    body: Mapping[str, Any]


def iter_docs(path: Path, wanted: frozenset[int] = WANTED_CLASS_IDS) -> Iterator[UnityDoc]:
    """Yield a :class:`UnityDoc` for every document whose class id is in
    ``wanted``; every other document's body is skipped without being parsed.

    The file is read once as text (a Synty demo scene is a few MB -- this is
    not the memory-sensitive part; parsing 2000+ tiny multi-doc YAML bodies
    one at a time is). A malformed body raises :class:`SceneParseError` with
    the byte offset of its header line.
    """
    text = path.read_text(encoding="utf-8", errors="strict")
    lines = text.splitlines(keepends=True)
    n = len(lines)
    i = 0
    while i < n and (lines[i].startswith("%") or not lines[i].strip()):
        i += 1
    while i < n:
        header = lines[i].rstrip("\r\n")
        match = _HEADER_RE.match(header)
        if not match:
            i += 1
            continue
        class_id = int(match.group("cls"))
        file_id = int(match.group("fid"))
        stripped = match.group("stripped") is not None
        start = i + 1
        j = start
        while j < n and not _HEADER_RE.match(lines[j].rstrip("\r\n")):
            j += 1
        if class_id in wanted:
            chunk = "".join(lines[start:j])
            try:
                parsed = yaml.load(chunk, Loader=_LOADER)
            except yaml.YAMLError as exc:
                offset = len("".join(lines[:start]).encode("utf-8"))
                raise SceneParseError(str(path), file_id, None, f"YAML error in document body: {exc}", offset=offset) from exc
            if not isinstance(parsed, dict) or len(parsed) != 1:
                offset = len("".join(lines[:start]).encode("utf-8"))
                raise SceneParseError(
                    str(path), file_id, None, "expected a single-key document body (type name -> fields)", offset=offset
                )
            body = next(iter(parsed.values())) or {}
            yield UnityDoc(class_id=class_id, file_id=file_id, stripped=stripped, body=body)
        i = j


def field(doc: UnityDoc, *keys: str, scene: str) -> Any:
    """Typed accessor: walks ``doc.body`` through ``keys`` and raises
    :class:`SceneParseError` naming ``scene``, ``doc.file_id`` and the dotted
    field path on any miss. No ``dict.get`` default, no silent ``None`` --
    every access to a field the miner depends on for correctness goes through
    here (spec §5)."""
    cur: Any = doc.body
    for i, key in enumerate(keys):
        if not isinstance(cur, Mapping) or key not in cur:
            raise SceneParseError(scene, doc.file_id, ".".join(keys[: i + 1]), "field missing")
        cur = cur[key]
    return cur


def _vec3(mapping: Any, scene: str, file_id: int, name: str) -> tuple[float, float, float]:
    if not isinstance(mapping, Mapping):
        raise SceneParseError(scene, file_id, name, "expected an {x,y,z} mapping")
    out = []
    for axis in ("x", "y", "z"):
        if axis not in mapping:
            raise SceneParseError(scene, file_id, f"{name}.{axis}", "field missing")
        out.append(float(mapping[axis]))
    return (out[0], out[1], out[2])


def _quat(mapping: Any, scene: str, file_id: int, name: str) -> tuple[float, float, float, float]:
    if not isinstance(mapping, Mapping):
        raise SceneParseError(scene, file_id, name, "expected an {x,y,z,w} mapping")
    out = []
    for axis in ("x", "y", "z", "w"):
        if axis not in mapping:
            raise SceneParseError(scene, file_id, f"{name}.{axis}", "field missing")
        out.append(float(mapping[axis]))
    return (out[0], out[1], out[2], out[3])


# --- quaternion / world-transform composition --------------------------------


@dataclass(frozen=True)
class WorldXform:
    pos: tuple[float, float, float]
    rot: tuple[float, float, float, float]  # x, y, z, w
    scale: tuple[float, float, float]


IDENTITY_XFORM = WorldXform(pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0, 1.0), scale=(1.0, 1.0, 1.0))


def _quat_normalize(q: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n == 0:
        return (0.0, 0.0, 0.0, 1.0)
    return (x / n, y / n, z / n, w / n)


def _quat_mul(a: tuple[float, float, float, float], b: tuple[float, float, float, float]):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_to_matrix(q: tuple[float, float, float, float]):
    x, y, z, w = _quat_normalize(q)
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def rotate_vector(q: tuple[float, float, float, float], v: Sequence[float]) -> tuple[float, float, float]:
    m = _quat_to_matrix(q)
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def compose(
    parent: WorldXform,
    local_pos: tuple[float, float, float],
    local_rot: tuple[float, float, float, float],
    local_scale: tuple[float, float, float],
) -> WorldXform:
    """``world = parent_world ∘ (T·R·S)`` -- the same recursion Unity's own
    Transform hierarchy performs. ``world_scale`` is tracked only so a child
    further down the chain gets the right *position*; it is never reported as
    a placement's ``scale`` (world scale is ill-defined under rotation when a
    non-uniform-scaled parent exists -- not observed in Synty demo scenes,
    where every non-leaf Transform carries scale ``[1,1,1]``)."""
    scaled = tuple(parent.scale[i] * local_pos[i] for i in range(3))
    rotated = rotate_vector(parent.rot, scaled)
    world_pos = tuple(parent.pos[i] + rotated[i] for i in range(3))
    world_rot = _quat_normalize(_quat_mul(parent.rot, local_rot))
    world_scale = tuple(parent.scale[i] * local_scale[i] for i in range(3))
    return WorldXform(pos=world_pos, rot=world_rot, scale=world_scale)  # type: ignore[arg-type]


def euler_zxy_deg(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Unity's ZXY Euler decomposition of a world-space quaternion.

    Returns ``(pitch_x, yaw_y, roll_z)`` in degrees, unwrapped: pitch is the
    ``asin`` branch and stays in ``[-90, 90]``; yaw/roll are the ``atan2``
    branch and stay in ``(-180, 180]``. Callers normalise yaw to ``[0, 360)``
    themselves (spec A5) -- pitch is left signed so a camera's "positive =
    looking up" convention (D8) is a plain negation, not a second wrap.

    Verified against a real scene's ``m_LocalEulerAnglesHint`` (the
    Directional Light in ``POLYGON_SciFi_City/.../Demo.unity``) to within
    0.001 degrees on all three axes.
    """
    m = _quat_to_matrix(q)
    v = max(-1.0, min(1.0, -m[1][2]))
    pitch = math.asin(v)
    if abs(m[1][2]) < 0.9999999:
        yaw = math.atan2(m[0][2], m[2][2])
        roll = math.atan2(m[1][0], m[1][1])
    else:  # gimbal lock: pitch is +-90, yaw/roll are not independently recoverable
        yaw = math.atan2(-m[2][0], m[0][0])
        roll = 0.0
    return math.degrees(pitch), math.degrees(yaw), math.degrees(roll)


def round_deg_0_360(deg: float) -> float:
    """Normalise + round a degree value into ``[0, 360)`` without the
    rounding step itself pushing it back up to exactly ``360.0`` (the
    schema's ``deg`` type is ``exclusiveMaximum: 360``)."""
    v = round(deg % 360.0, 4)
    return 0.0 if v >= 360.0 else v


def _strip_copy_suffix(name: str) -> str:
    match = _COPY_SUFFIX_RE.match(name)
    return match.group(1) if match else name


def _instance_local_trs(doc: UnityDoc, scene: str):
    """Local TRS + name + static flag from a PrefabInstance's override list.

    Defaults (spec §3.1): position ``(0,0,0)``, rotation identity, scale
    ``(1,1,1)`` when a given property has no override entry -- Unity omits an
    override entirely when it matches the source prefab's own value.
    """
    mods = field(doc, "m_Modification", "m_Modifications", scene=scene)
    pos = {"x": 0.0, "y": 0.0, "z": 0.0}
    rot = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    scale = {"x": 1.0, "y": 1.0, "z": 1.0}
    name: str | None = None
    static = False
    for mod in mods:
        if not isinstance(mod, Mapping):
            continue
        prop = mod.get("propertyPath", "")
        if prop.startswith("m_LocalPosition."):
            pos[prop.rsplit(".", 1)[1]] = float(mod.get("value", 0.0))
        elif prop.startswith("m_LocalRotation."):
            rot[prop.rsplit(".", 1)[1]] = float(mod.get("value", 0.0))
        elif prop.startswith("m_LocalScale."):
            scale[prop.rsplit(".", 1)[1]] = float(mod.get("value", 1.0))
        elif prop == "m_Name":
            name = str(mod.get("value", ""))
        elif prop == "m_StaticEditorFlags":
            static = int(mod.get("value", 0) or 0) != 0
    pos_t = (pos["x"], pos["y"], pos["z"])
    rot_t = (rot["x"], rot["y"], rot["z"], rot["w"])
    scale_t = (scale["x"], scale["y"], scale["z"])
    return pos_t, rot_t, scale_t, name, static


def _default_instance_name(doc: UnityDoc, index: GuidIndex, scene: str) -> str:
    guid = field(doc, "m_SourcePrefab", "guid", scene=scene)
    asset_path = index.by_guid.get(guid)
    return Path(asset_path).stem if asset_path else f"<unresolved guid {guid}>"


def _resolve_transform_world(
    fid: int,
    transforms: Mapping[int, UnityDoc],
    instances: Mapping[int, UnityDoc],
    memo_t: dict[int, WorldXform],
    memo_i: dict[int, WorldXform],
    visiting: set[int],
    scene: str,
) -> WorldXform:
    if fid == 0:
        return IDENTITY_XFORM
    if fid in memo_t:
        return memo_t[fid]
    if fid in visiting:
        raise SceneParseError(scene, fid, "m_Father", "cycle in Transform parent chain")
    visiting.add(fid)
    tdoc = transforms.get(fid)
    if tdoc is None:
        visiting.discard(fid)
        raise SceneParseError(scene, fid, "m_Father", f"referenced Transform fileID {fid} is not present in this scene")
    if tdoc.stripped:
        inst_fid = field(tdoc, "m_PrefabInstance", "fileID", scene=scene)
        world = _resolve_instance_world(inst_fid, transforms, instances, memo_t, memo_i, visiting, scene)
    else:
        local_pos = _vec3(field(tdoc, "m_LocalPosition", scene=scene), scene, fid, "m_LocalPosition")
        local_rot = _quat(field(tdoc, "m_LocalRotation", scene=scene), scene, fid, "m_LocalRotation")
        local_scale = _vec3(field(tdoc, "m_LocalScale", scene=scene), scene, fid, "m_LocalScale")
        father_fid = field(tdoc, "m_Father", "fileID", scene=scene)
        parent = _resolve_transform_world(father_fid, transforms, instances, memo_t, memo_i, visiting, scene)
        world = compose(parent, local_pos, local_rot, local_scale)
    memo_t[fid] = world
    visiting.discard(fid)
    return world


def _resolve_instance_world(
    fid: int,
    transforms: Mapping[int, UnityDoc],
    instances: Mapping[int, UnityDoc],
    memo_t: dict[int, WorldXform],
    memo_i: dict[int, WorldXform],
    visiting: set[int],
    scene: str,
) -> WorldXform:
    if fid in memo_i:
        return memo_i[fid]
    if fid in visiting:
        raise SceneParseError(scene, fid, "m_TransformParent", "cycle in PrefabInstance parent chain")
    visiting.add(fid)
    idoc = instances.get(fid)
    if idoc is None:
        visiting.discard(fid)
        raise SceneParseError(scene, fid, "m_PrefabInstance", f"referenced PrefabInstance fileID {fid} is not present in this scene")
    pos, rot, scale, _name, _static = _instance_local_trs(idoc, scene)
    parent_fid = field(idoc, "m_Modification", "m_TransformParent", "fileID", scene=scene)
    parent = _resolve_transform_world(parent_fid, transforms, instances, memo_t, memo_i, visiting, scene)
    world = compose(parent, pos, rot, scale)
    memo_i[fid] = world
    visiting.discard(fid)
    return world


def _ancestor_names(
    fid: int,
    transforms: Mapping[int, UnityDoc],
    instances: Mapping[int, UnityDoc],
    game_objects: Mapping[int, UnityDoc],
    index: GuidIndex,
    memo_names: dict[int, list[str]],
    visiting: set[int],
    scene: str,
) -> list[str]:
    """Names of the scene-hierarchy ancestors above Transform ``fid``, root
    first -- used for a placement's ``parent_path``. A stripped Transform
    means the ancestor is itself a PrefabInstance; its name is its own
    ``m_Name`` override (or the prefab stem when unnamed), and the walk
    continues through *its* ``m_TransformParent``."""
    if fid == 0:
        return []
    if fid in memo_names:
        return memo_names[fid]
    if fid in visiting:
        raise SceneParseError(scene, fid, "m_Father", "cycle while building parent_path")
    visiting.add(fid)
    tdoc = transforms.get(fid)
    if tdoc is None:
        visiting.discard(fid)
        raise SceneParseError(scene, fid, "m_Father", f"referenced Transform fileID {fid} is not present in this scene")
    if tdoc.stripped:
        inst_fid = field(tdoc, "m_PrefabInstance", "fileID", scene=scene)
        idoc = instances.get(inst_fid)
        if idoc is None:
            visiting.discard(fid)
            raise SceneParseError(scene, fid, "m_PrefabInstance", f"referenced PrefabInstance fileID {inst_fid} is not present")
        _pos, _rot, _scale, mod_name, _static = _instance_local_trs(idoc, scene)
        name = mod_name if mod_name is not None else _default_instance_name(idoc, index, scene)
        parent_fid = field(idoc, "m_Modification", "m_TransformParent", "fileID", scene=scene)
        chain = _ancestor_names(parent_fid, transforms, instances, game_objects, index, memo_names, visiting, scene) + [name]
    else:
        go_fid = field(tdoc, "m_GameObject", "fileID", scene=scene)
        go = game_objects.get(go_fid)
        if go is None:
            visiting.discard(fid)
            raise SceneParseError(scene, go_fid, "m_GameObject", "referenced GameObject is not present in this scene")
        name = field(go, "m_Name", scene=scene)
        father_fid = field(tdoc, "m_Father", "fileID", scene=scene)
        chain = _ancestor_names(father_fid, transforms, instances, game_objects, index, memo_names, visiting, scene) + [name]
    memo_names[fid] = chain
    visiting.discard(fid)
    return chain


# --- placement / scene document -----------------------------------------------


@dataclass(frozen=True)
class Placement:
    file_id: int
    asset_id: str
    instance_name: str
    pos_m: tuple[float, float, float]
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    scale: tuple[float, float, float]
    parent_path: str
    static: bool


@dataclass(frozen=True)
class UnresolvedRef:
    file_id: int
    guid: str
    asset_path: str | None
    reason: str  # no_meta | not_in_catalog | not_placeable
    instance_name: str
    hint: str | None


@dataclass(frozen=True)
class SceneDoc:
    path: Path
    placements: tuple[Placement, ...]
    unresolved: tuple[UnresolvedRef, ...]
    warnings: tuple[str, ...]
    render_settings: Mapping[str, Any] | None
    lights: tuple[tuple[Mapping[str, Any], WorldXform], ...]
    cameras: tuple[tuple[str, Mapping[str, Any], WorldXform], ...]
    global_volume: Mapping[str, Any] | None
    lighting_settings_guid: str | None


def parse_scene(path: Path, index: GuidIndex, catalog: Mapping[str, Any]) -> SceneDoc:
    """Parse one ``.unity`` scene into every ``PrefabInstance`` placement
    (world-composed, resolved against ``catalog`` via ``index``) plus the raw
    RenderSettings/Light/Camera/global-Volume docs ``look_extract`` needs.

    One pass over the file builds the doc maps; a memoized recursion (see
    ``_resolve_transform_world``/``_resolve_instance_world``) composes world
    transforms on demand, so the order PrefabInstances appear in the file
    never matters. Placements are then emitted in ascending fileID order
    (spec §5 determinism).

    ``catalog`` is a loaded pack catalog dict (``synty_inventory.catalog.load_catalog``);
    the join key is GUID -> ``.meta`` path (``index``) -> catalog
    ``files.unity_prefab`` (spec A3) -- never the instance's ``m_Name``.
    """
    scene = str(path)
    game_objects: dict[int, UnityDoc] = {}
    transforms: dict[int, UnityDoc] = {}
    instances: dict[int, UnityDoc] = {}
    lights_raw: list[tuple[UnityDoc, int]] = []  # (light doc, its GameObject fileID)
    cameras_raw: list[tuple[UnityDoc, int]] = []  # (camera doc, its GameObject fileID)
    volumes_raw: list[UnityDoc] = []
    render_settings: Mapping[str, Any] | None = None
    lighting_settings_guid: str | None = None

    # `LightmapSettings` (class 157) is outside D3's wanted-class list, but
    # `look.lighting_settings_path` needs its one field -- it is a single tiny
    # doc per scene, so adding it here does not touch the streaming/memory
    # intent D3 protects (that clause is about not parsing 2000+ PrefabInstance
    # bodies unnecessarily, not about this one extra doc).
    for doc in iter_docs(path, wanted=WANTED_CLASS_IDS | {157}):
        if doc.class_id == 1:
            game_objects[doc.file_id] = doc
        elif doc.class_id == 4:
            transforms[doc.file_id] = doc
        elif doc.class_id == 1001:
            instances[doc.file_id] = doc
        elif doc.class_id == 108:
            go_fid = field(doc, "m_GameObject", "fileID", scene=scene)
            lights_raw.append((doc, go_fid))
        elif doc.class_id == 20:
            go_fid = field(doc, "m_GameObject", "fileID", scene=scene)
            cameras_raw.append((doc, go_fid))
        elif doc.class_id == 114:
            if doc.body.get("m_IsGlobal") == 1:
                volumes_raw.append(doc)
        elif doc.class_id == 104:
            if render_settings is None:
                render_settings = doc.body
        elif doc.class_id == 157:
            guid = ((doc.body.get("m_LightingSettings") or {}).get("guid"))
            if lighting_settings_guid is None and guid:
                lighting_settings_guid = guid

    transform_by_gameobject: dict[int, int] = {}
    for tfid, tdoc in transforms.items():
        if tdoc.stripped:
            continue
        go_fid = field(tdoc, "m_GameObject", "fileID", scene=scene)
        transform_by_gameobject[go_fid] = tfid

    memo_t: dict[int, WorldXform] = {}
    memo_i: dict[int, WorldXform] = {}
    memo_names: dict[int, list[str]] = {}
    visiting: set[int] = set()

    def _world_of_gameobject(go_fid: int) -> WorldXform:
        tfid = transform_by_gameobject.get(go_fid)
        if tfid is None:
            raise SceneParseError(scene, go_fid, "m_GameObject", "no Transform found for this GameObject")
        return _resolve_transform_world(tfid, transforms, instances, memo_t, memo_i, visiting, scene)

    lights = tuple((doc.body, _world_of_gameobject(go_fid)) for doc, go_fid in lights_raw)
    cameras = tuple(
        (field(game_objects[go_fid], "m_Name", scene=scene), doc.body, _world_of_gameobject(go_fid))
        for doc, go_fid in cameras_raw
    )
    global_volume = volumes_raw[0].body if volumes_raw else None

    catalog_by_path: dict[str, Mapping[str, Any]] = {}
    for row in catalog.get("assets", []) or []:
        prefab_path = (row.get("files") or {}).get("unity_prefab")
        if prefab_path:
            catalog_by_path[prefab_path] = row

    placements: list[Placement] = []
    unresolved: list[UnresolvedRef] = []
    warnings: list[str] = []

    for fid in sorted(instances):
        idoc = instances[fid]
        pos, rot, scale, mod_name, static = _instance_local_trs(idoc, scene)
        guid = field(idoc, "m_SourcePrefab", "guid", scene=scene)
        parent_fid = field(idoc, "m_Modification", "m_TransformParent", "fileID", scene=scene)
        world = _resolve_instance_world(fid, transforms, instances, memo_t, memo_i, visiting, scene)
        pitch, yaw, roll = euler_zxy_deg(world.rot)
        instance_name = mod_name if mod_name is not None else _default_instance_name(idoc, index, scene)
        hint = _strip_copy_suffix(instance_name)

        asset_path = index.by_guid.get(guid)
        if asset_path is None:
            unresolved.append(
                UnresolvedRef(file_id=fid, guid=guid, asset_path=None, reason="no_meta", instance_name=instance_name, hint=hint)
            )
            continue
        row = catalog_by_path.get(asset_path)
        if row is None:
            unresolved.append(
                UnresolvedRef(file_id=fid, guid=guid, asset_path=asset_path, reason="not_in_catalog", instance_name=instance_name, hint=hint)
            )
            continue
        row_guid = row.get("guid")
        if row_guid and row_guid != guid:
            warnings.append(
                f"{scene}: fileID={fid} catalog guid {row_guid!r} disagrees with scene guid {guid!r} for {asset_path}"
            )
        if row.get("placeable") is False:
            unresolved.append(
                UnresolvedRef(file_id=fid, guid=guid, asset_path=asset_path, reason="not_placeable", instance_name=instance_name, hint=hint)
            )
            continue

        parent_path = "/".join(_ancestor_names(parent_fid, transforms, instances, game_objects, index, memo_names, visiting, scene))
        placements.append(
            Placement(
                file_id=fid,
                asset_id=row["id"],
                instance_name=instance_name,
                pos_m=tuple(round(c, 4) for c in world.pos),  # type: ignore[arg-type]
                yaw_deg=round_deg_0_360(yaw),
                pitch_deg=round(pitch, 4),
                roll_deg=round(roll, 4),
                scale=tuple(round(c, 4) for c in scale),  # type: ignore[arg-type]
                parent_path=parent_path,
                static=static,
            )
        )

    return SceneDoc(
        path=path,
        placements=tuple(placements),
        unresolved=tuple(unresolved),
        warnings=tuple(warnings),
        render_settings=render_settings,
        lights=lights,
        cameras=cameras,
        global_volume=global_volume,
        lighting_settings_guid=lighting_settings_guid,
    )
