"""Interpret the raw RenderSettings / Light / global-Volume docs a
``unity_yaml.parse_scene`` call collected into the scene-grammar ``look``
block (spec §4/§7; decisions D2/D6/D7/D8 bind the sun-angle and skybox
conventions -- see ``tasks/todo.md`` "## S9-SG").
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from .guid_index import GuidIndex
from .unity_yaml import SceneDoc, WorldXform, euler_zxy_deg, iter_docs, rotate_vector, round_deg_0_360

# D6: Unity's built-in Default-Skybox material GUID (every project ships it;
# it does not have its own .meta file to resolve).
_BUILTIN_SKYBOX_GUID = "0000000000000000f000000000000000"

_FOG_MODES = {0: "none", 1: "linear", 2: "exp", 3: "exp2"}
_AMBIENT_MODES = {0: "skybox", 1: "trilight", 3: "flat", 4: "custom"}
_SHADOW_TYPES = {0: "none", 1: "hard", 2: "soft"}
_TONEMAPPING_MODES = {0: "none", 1: "neutral", 2: "aces"}

_UNPARSEABLE = object()


def _rgb(c: Mapping[str, Any] | None) -> list[float]:
    c = c or {}
    return [round(float(c.get("r", 0.0)), 4), round(float(c.get("g", 0.0)), 4), round(float(c.get("b", 0.0)), 4)]


def _extract_fog(rs: Mapping[str, Any]) -> dict:
    """``!u!104 RenderSettings`` fog: mode 0 none / 1 linear / 2 exp / 3 exp2
    (``m_Fog: 0`` always forces ``none`` regardless of ``m_FogMode``)."""
    mode = _FOG_MODES.get(int(rs.get("m_FogMode", 0)), "none") if rs.get("m_Fog") else "none"
    return {
        "mode": mode,
        "color_rgb": _rgb(rs.get("m_FogColor")),
        "density": round(float(rs.get("m_FogDensity", 0.0)), 4),
        "start_m": round(float(rs.get("m_LinearFogStart", 0.0)), 4),
        "end_m": round(float(rs.get("m_LinearFogEnd", 0.0)), 4),
    }


def _extract_ambient(rs: Mapping[str, Any]) -> dict:
    """Ambient mode 0 skybox / 1 trilight / 3 flat / 4 custom, the three
    ambient colours and intensity straight off ``RenderSettings``."""
    return {
        "mode": _AMBIENT_MODES.get(int(rs.get("m_AmbientMode", 0)), "skybox"),
        "sky_rgb": _rgb(rs.get("m_AmbientSkyColor")),
        "equator_rgb": _rgb(rs.get("m_AmbientEquatorColor")),
        "ground_rgb": _rgb(rs.get("m_AmbientGroundColor")),
        "intensity": round(float(rs.get("m_AmbientIntensity", 1.0)), 4),
    }


def _extract_sky(rs: Mapping[str, Any], index: GuidIndex) -> dict:
    ref = rs.get("m_SkyboxMaterial") or {}
    guid = ref.get("guid")
    file_id = ref.get("fileID", 0)
    if not guid or file_id == 0:
        return {"kind": "none", "material_path": None, "zenith_rgb": None, "horizon_rgb": None}
    if guid == _BUILTIN_SKYBOX_GUID:
        return {"kind": "material", "material_path": "builtin:Default-Skybox", "zenith_rgb": None, "horizon_rgb": None}
    return {"kind": "material", "material_path": index.by_guid.get(guid), "zenith_rgb": None, "horizon_rgb": None}


def _extract_sun(lights: tuple[tuple[Mapping[str, Any], WorldXform], ...], warnings: list[str]) -> dict | None:
    """Exactly one ``!u!108 Light`` with ``m_Type: 1`` (directional) is
    required; zero or several -> ``sun: null`` plus a warning (spec §7 --
    the consumer (``Look.from_scene_grammar``) fails loud on ``sun is None``,
    not the miner).

    D8: ``forward = q . (0,0,1)``, ``dir = -forward``,
    ``elevation = asin(dir.y)``, ``azimuth = atan2(dir.x, dir.z) mod 360`` --
    the exact inverse of ``LookBuilder.SunDirection``.
    """
    directional = [(body, xf) for body, xf in lights if int(body.get("m_Type", -1)) == 1]
    if len(directional) != 1:
        if not directional:
            warnings.append("no directional Light in the scene -- look.sun is null")
        else:
            warnings.append(f"{len(directional)} directional Lights in the scene -- look.sun is null (spec §7)")
        return None
    body, xf = directional[0]
    forward = rotate_vector(xf.rot, (0.0, 0.0, 1.0))
    direction = (-forward[0], -forward[1], -forward[2])
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, direction[1]))))
    azimuth = math.degrees(math.atan2(direction[0], direction[2])) % 360.0
    shadow_type = int((body.get("m_Shadows") or {}).get("m_Type", 0))
    return {
        "azimuth_deg": round_deg_0_360(azimuth),
        "elevation_deg": round(elevation, 4),
        "intensity": round(float(body.get("m_Intensity", 1.0)), 4),
        "color_rgb": _rgb(body.get("m_Color")),
        "shadows": _SHADOW_TYPES.get(shadow_type, "none"),
    }


def _post_value(value: Any):
    """A profile override's ``m_Value``: colours -> ``[r,g,b,a]``, vectors ->
    ``[x,y,...]``, scalars stay scalars, ``{fileID}`` refs are unparseable
    (spec: never fabricate a value for those -- the caller lists them in
    ``unparsed`` instead)."""
    if isinstance(value, Mapping):
        if "fileID" in value:
            return _UNPARSEABLE
        if "r" in value and "g" in value and "b" in value:
            return [round(float(value.get(k, 0.0)), 4) for k in ("r", "g", "b", "a")]
        if "x" in value and "y" in value:
            keys = [k for k in ("x", "y", "z", "w") if k in value]
            return [round(float(value[k]), 4) for k in keys]
        return _UNPARSEABLE
    if isinstance(value, float):
        return round(value, 4)
    return value


def _extract_post(
    volume_body: Mapping[str, Any] | None, index: GuidIndex, extracted_root: Path, warnings: list[str]
) -> dict | None:
    if volume_body is None:
        return None
    ref = volume_body.get("sharedProfile") or {}
    guid = ref.get("guid")
    profile_path = index.by_guid.get(guid) if guid else None
    if not profile_path:
        warnings.append("global Volume sharedProfile GUID not found in the GUID index -- post.overrides is empty")
        return {"profile_path": None, "overrides": {}, "unparsed": []}
    profile_abs = extracted_root / profile_path
    if not profile_abs.is_file():
        warnings.append(f"Volume profile asset not found on disk: {profile_path}")
        return {"profile_path": profile_path, "overrides": {}, "unparsed": []}

    overrides: dict[str, dict[str, Any]] = {}
    unparsed: list[str] = []
    for doc in iter_docs(profile_abs, wanted=frozenset({114})):
        name = doc.body.get("m_Name")
        if not name or "components" in doc.body:
            continue  # the profile's own root doc (m_Name == the asset name) is not a component
        params: dict[str, Any] = {}
        for key, val in doc.body.items():
            if not isinstance(val, Mapping) or "m_OverrideState" not in val:
                continue
            if int(val.get("m_OverrideState", 0)) != 1:
                continue
            parsed = _post_value(val.get("m_Value"))
            if parsed is _UNPARSEABLE:
                unparsed.append(f"{name}.{key}")
                continue
            params[key] = parsed
        if name == "Tonemapping" and "mode" in params:
            params["mode"] = _TONEMAPPING_MODES.get(int(params["mode"]), "none")
        if params:
            overrides[name] = params
    return {"profile_path": profile_path, "overrides": overrides, "unparsed": sorted(unparsed)}


def extract_look(scene_doc: SceneDoc, index: GuidIndex, extracted_root: Path) -> tuple[dict, list[str]]:
    """Build the scene-grammar ``look`` block from one scene's raw docs.
    Returns ``(look_dict, warnings)`` -- the caller (``mine.py``) merges the
    warnings into the pack-level list and keeps only the first non-duplicate
    scene's look (spec §5)."""
    warnings: list[str] = []
    rs = scene_doc.render_settings or {}
    look = {
        "sun": _extract_sun(scene_doc.lights, warnings),
        "sky": _extract_sky(rs, index),
        "ambient": _extract_ambient(rs),
        "fog": _extract_fog(rs),
        "post": _extract_post(scene_doc.global_volume, index, extracted_root, warnings),
        "lighting_settings_path": (
            index.by_guid.get(scene_doc.lighting_settings_guid) if scene_doc.lighting_settings_guid else None
        ),
    }
    return look, warnings


def extract_cameras(scene_doc: SceneDoc) -> list[dict]:
    """One row per ``!u!20 Camera`` in the scene: ``id`` = its GameObject's
    name, world position/yaw, ``pitch_deg`` = ``-(Unity euler x)`` so a
    positive value looks up, ``fov_deg``/``enabled`` straight off the
    component."""
    out = []
    for name, body, xf in scene_doc.cameras:
        pitch, yaw, _roll = euler_zxy_deg(xf.rot)
        out.append(
            {
                "id": name,
                "position_m": [round(c, 4) for c in xf.pos],
                "yaw_deg": round_deg_0_360(yaw),
                "pitch_deg": round(-pitch, 4),
                "fov_deg": round(float(body.get("field of view", 60.0)), 4),
                "enabled": bool(body.get("m_Enabled", 1)),
            }
        )
    return out
