"""Builds a hand-specified Synty-shaped extracted tree + catalog for the
scene-mine tests (see ``tests/test_scene_mine_*.py``). Every geometric value
here is chosen so the expected world position of each placement can be
hand-derived with plain trigonometry (see ``EXPECTED`` below and the
per-instance comments) rather than trusted to the code under test.

Layout (spec: "a ~200-line Demo.unity with >= 6 PrefabInstances under a
nested parent chain"):

    Root (Transform, world pos (100, 0, 50), yaw 90 deg, m_Father: 0)
      Child (Transform, local pos (10, 0, 0), identity rotation, m_Father: Root)
      P1, P2, P5, P7  -- PrefabInstances parented directly to Root
        P2 is static (m_StaticEditorFlags override present)
        P5 has non-unit scale (scale.z = 1.93, mirrors the real Sci-Fi City
           dirt-mound finding)
      P3, P4, P8      -- PrefabInstances parented to Child
        P6 is parented to *P3's own stripped Transform* (spec: "one parented
           to another instance's stripped Transform")

A yaw-90 root keeps the world-position algebra exact: rotating a local
(x, y, z) offset by +90 deg about Y (Unity's convention, D8) sends
world_x = local_z, world_y = local_y, world_z = -local_x -- see
``_rotate90`` below, used only to *compute* the fixture's own expected
values (never imported by the code under test).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

PACK_DIR = "PolygonFixturePack"
PACK_ID = "POLYGON_FixturePack"

HEADER = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"

# Real POLYGON_SciFi_City Demo.unity directional-light quaternion + its
# hand-verified (elevation, azimuth) from tasks/s9_scene_grammar_spec.md's
# own facts block -- reusing real, already-cross-checked numbers here means
# the look-extraction test is checked against ground truth, not a value this
# same test suite invented.
SUN_QUAT = (0.5643327, -0.5691708, 0.22428448, 0.5543192)

# Pure X-axis rotation of -20 deg: forward = (0, sin(20deg), cos(20deg)) --
# a camera looking *up*. D8's camera convention is pitch_deg = -(Euler x),
# and euler_zxy_deg's asin-branch pitch on a pure-X quaternion is exactly the
# rotation angle, so the expected pitch_deg is -(-20) = +20.0.
_CAM_PHI = math.radians(-20.0)
CAMERA_QUAT = (math.sin(_CAM_PHI / 2), 0.0, 0.0, math.cos(_CAM_PHI / 2))
CAMERA_EXPECTED_PITCH_DEG = 20.0


def _rotate90(local: tuple[float, float, float]) -> tuple[float, float, float]:
    """World offset of a `local` vector under a +90 deg Y rotation, by hand:
    world_x = local_z, world_y = local_y, world_z = -local_x."""
    lx, ly, lz = local
    return (lz, ly, -lx)


ROOT_POS = (100.0, 0.0, 50.0)
CHILD_LOCAL = (10.0, 0.0, 0.0)
CHILD_POS = tuple(a + b for a, b in zip(ROOT_POS, _rotate90(CHILD_LOCAL)))  # (100, 0, 40)

def guid(n: int) -> str:
    """A 32-hex-char GUID that always contains a letter -- a real Synty GUID
    always does, and an all-digit "GUID" like ``00...01`` is YAML 1.1 octal
    (leading zeros), which PyYAML silently parses as the *integer* 1 instead
    of a string. Trailing ``f`` guarantees this never happens here."""
    return f"{n:x}".rjust(31, "0") + "f"


# guid -> (asset id, catalog type, local pos, local scale, parent, static)
_PREFABS = {
    guid(1): dict(id="FIX_Building_01", type="building/shell"),
    guid(2): dict(id="FIX_Road_01", type="environment/city_layout"),
    guid(3): dict(id="FIX_Prop_01", type="prop"),
    guid(4): dict(id="FIX_Vehicle_01", type="vehicle"),
    guid(5): dict(id="FIX_Character_01", type="character"),
    guid(6): dict(id="FIX_Fx_01", type="fx"),
    guid(7): dict(id="FIX_Weapon_01", type="weapon"),
    guid(8): dict(id="FIX_Env_01", type="environment"),
}
_GUIDS = list(_PREFABS)

# name -> (guid index 0-based, parent fileID key "root"/"child"/"p3", local pos, local scale, static)
_INSTANCES = {
    "P1": dict(guid=_GUIDS[0], parent="root", local=(5.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), static=False),
    "P2": dict(guid=_GUIDS[1], parent="root", local=(0.0, 2.0, 3.0), scale=(1.0, 1.0, 1.0), static=True),
    "P3": dict(guid=_GUIDS[2], parent="child", local=(1.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), static=False),
    "P4": dict(guid=_GUIDS[3], parent="child", local=(0.0, 0.0, 2.0), scale=(1.0, 1.0, 1.0), static=False),
    "P5": dict(guid=_GUIDS[4], parent="root", local=(0.0, 0.0, 5.0), scale=(1.0, 1.0, 1.93), static=False),
    "P6": dict(guid=_GUIDS[5], parent="p3", local=(0.0, 0.0, 1.0), scale=(1.0, 1.0, 1.0), static=False),
    "P7": dict(guid=_GUIDS[6], parent="root", local=(0.0, 0.0, -5.0), scale=(1.0, 1.0, 1.0), static=False),
    "P8": dict(guid=_GUIDS[7], parent="child", local=(-2.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), static=False),
}

ROOT_GO, ROOT_TF = 100, 101
CHILD_GO, CHILD_TF = 102, 103
_INST_BASE = {"P1": 1000, "P2": 1010, "P3": 1020, "P4": 1030, "P5": 1040, "P6": 1050, "P7": 1060, "P8": 1070}


def _instance_transform_fid(name: str) -> int:
    return _INST_BASE[name] + 1


def _expected_positions() -> dict[str, tuple[float, float, float]]:
    p3_world = tuple(a + b for a, b in zip(CHILD_POS, _rotate90(_INSTANCES["P3"]["local"])))
    out = {}
    for name, spec in _INSTANCES.items():
        if spec["parent"] == "root":
            base = ROOT_POS
        elif spec["parent"] == "child":
            base = CHILD_POS
        else:  # "p3": parented through P3's own stripped Transform
            base = p3_world
        out[name] = tuple(round(a + b, 4) for a, b in zip(base, _rotate90(spec["local"])))
    return out


EXPECTED_POSITIONS = _expected_positions()
# All instances share the Root's yaw (90 deg): nothing here adds its own
# local rotation, and Y-axis composition of identity rotations stays 90.
EXPECTED_YAW_DEG = 90.0


def _prefab_instance_block(inst_fid: int, name: str, guid: str, parent_fid: int, local, scale, static: bool) -> str:
    mods = [
        f"    - target: {{fileID: 400000000000001, guid: {guid}, type: 3}}\n"
        f"      propertyPath: m_Name\n      value: {name}\n      objectReference: {{fileID: 0}}\n",
    ]
    for axis, val in zip("xyz", local):
        mods.append(
            f"    - target: {{fileID: 400000000000002, guid: {guid}, type: 3}}\n"
            f"      propertyPath: m_LocalPosition.{axis}\n      value: {val}\n      objectReference: {{fileID: 0}}\n"
        )
    for axis, val in zip("xyz", scale):
        if val != 1.0:
            mods.append(
                f"    - target: {{fileID: 400000000000002, guid: {guid}, type: 3}}\n"
                f"      propertyPath: m_LocalScale.{axis}\n      value: {val}\n      objectReference: {{fileID: 0}}\n"
            )
    if static:
        mods.append(
            f"    - target: {{fileID: 400000000000003, guid: {guid}, type: 3}}\n"
            f"      propertyPath: m_StaticEditorFlags\n      value: 4294967295\n      objectReference: {{fileID: 0}}\n"
        )
    mods_text = "".join(mods)
    return (
        f"--- !u!1001 &{inst_fid}\n"
        "PrefabInstance:\n"
        "  m_ObjectHideFlags: 0\n"
        "  serializedVersion: 2\n"
        "  m_Modification:\n"
        "    serializedVersion: 3\n"
        f"    m_TransformParent: {{fileID: {parent_fid}}}\n"
        "    m_Modifications:\n"
        f"{mods_text}"
        "    m_RemovedComponents: []\n"
        "    m_RemovedGameObjects: []\n"
        "    m_AddedGameObjects: []\n"
        "    m_AddedComponents: []\n"
        f"  m_SourcePrefab: {{fileID: 100100000, guid: {guid}, type: 3}}\n"
        f"--- !u!4 &{inst_fid + 1} stripped\n"
        "Transform:\n"
        f"  m_CorrespondingSourceObject: {{fileID: 400000000000002, guid: {guid}, type: 3}}\n"
        f"  m_PrefabInstance: {{fileID: {inst_fid}}}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
    )


def _go_transform_block(go_fid: int, tf_fid: int, name: str, father_fid: int, pos, rot, children: list[int]) -> str:
    children_text = "".join(f"  - {{fileID: {c}}}\n" for c in children) or ""
    return (
        f"--- !u!1 &{go_fid}\n"
        "GameObject:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  serializedVersion: 6\n"
        "  m_Component:\n"
        f"  - component: {{fileID: {tf_fid}}}\n"
        "  m_Layer: 0\n"
        f"  m_Name: {name}\n"
        "  m_TagString: Untagged\n"
        "  m_Icon: {fileID: 0}\n"
        "  m_NavMeshLayer: 0\n"
        "  m_StaticEditorFlags: 0\n"
        "  m_IsActive: 1\n"
        f"--- !u!4 &{tf_fid}\n"
        "Transform:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {go_fid}}}\n"
        "  serializedVersion: 2\n"
        f"  m_LocalRotation: {{x: {rot[0]}, y: {rot[1]}, z: {rot[2]}, w: {rot[3]}}}\n"
        f"  m_LocalPosition: {{x: {pos[0]}, y: {pos[1]}, z: {pos[2]}}}\n"
        "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
        "  m_ConstrainProportionsScale: 0\n"
        "  m_Children:\n"
        f"{children_text}"
        f"  m_Father: {{fileID: {father_fid}}}\n"
        "  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}\n"
    )


_ROOT_QUAT = (0.0, math.sin(math.radians(45.0)), 0.0, math.cos(math.radians(45.0)))  # yaw 90 deg about Y


def _render_settings_block(lighting_guid: str) -> str:
    return (
        "--- !u!104 &2\n"
        "RenderSettings:\n"
        "  m_ObjectHideFlags: 0\n"
        "  serializedVersion: 9\n"
        "  m_Fog: 1\n"
        "  m_FogColor: {r: 0.4, g: 0.2, b: 0.3, a: 1}\n"
        "  m_FogMode: 3\n"
        "  m_FogDensity: 0.005\n"
        "  m_LinearFogStart: 0\n"
        "  m_LinearFogEnd: 300\n"
        "  m_AmbientSkyColor: {r: 0.05, g: 0.11, b: 0.25, a: 1}\n"
        "  m_AmbientEquatorColor: {r: 0.11, g: 0.12, b: 0.13, a: 1}\n"
        "  m_AmbientGroundColor: {r: 0.05, g: 0.04, b: 0.03, a: 1}\n"
        "  m_AmbientIntensity: 1\n"
        "  m_AmbientMode: 1\n"
        "  m_SubtractiveShadowColor: {r: 0.42, g: 0.478, b: 0.627, a: 1}\n"
        "  m_SkyboxMaterial: {fileID: 10304, guid: 0000000000000000f000000000000000, type: 0}\n"
        "  m_HaloStrength: 0.5\n"
        "  m_FlareStrength: 1\n"
        "  m_FlareFadeSpeed: 3\n"
        "  m_HaloTexture: {fileID: 0}\n"
        "  m_SpotCookie: {fileID: 10001, guid: 0000000000000000e000000000000000, type: 0}\n"
        "  m_DefaultReflectionMode: 0\n"
        "  m_DefaultReflectionResolution: 128\n"
        "  m_ReflectionBounces: 1\n"
        "  m_ReflectionIntensity: 1\n"
        "  m_CustomReflection: {fileID: 0}\n"
        "  m_Sun: {fileID: 0}\n"
        "  m_UseRadianceAmbientProbe: 0\n"
        "--- !u!157 &3\n"
        "LightmapSettings:\n"
        "  m_ObjectHideFlags: 0\n"
        "  serializedVersion: 12\n"
        f"  m_LightingSettings: {{fileID: 1, guid: {lighting_guid}, type: 2}}\n"
    )


def _light_block(light_go: int, light_comp: int, light_tf: int, quat) -> str:
    return (
        f"--- !u!1 &{light_go}\n"
        "GameObject:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  serializedVersion: 6\n"
        "  m_Component:\n"
        f"  - component: {{fileID: {light_tf}}}\n"
        f"  - component: {{fileID: {light_comp}}}\n"
        "  m_Layer: 0\n"
        "  m_Name: Directional light\n"
        "  m_TagString: Untagged\n"
        "  m_Icon: {fileID: 0}\n"
        "  m_NavMeshLayer: 0\n"
        "  m_StaticEditorFlags: 0\n"
        "  m_IsActive: 1\n"
        f"--- !u!108 &{light_comp}\n"
        "Light:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {light_go}}}\n"
        "  m_Enabled: 1\n"
        "  serializedVersion: 10\n"
        "  m_Type: 1\n"
        "  m_Shape: 0\n"
        "  m_Color: {r: 1, g: 0.9, b: 0.87, a: 1}\n"
        "  m_Intensity: 1.2\n"
        "  m_Shadows:\n"
        "    m_Type: 2\n"
        "    m_Resolution: -1\n"
        "    m_CustomResolution: -1\n"
        "    m_Strength: 1\n"
        "    m_Bias: 0.05\n"
        "    m_NormalBias: 0.4\n"
        "    m_NearPlane: 0.2\n"
        "  m_Cookie: {fileID: 0}\n"
        "  m_Lightmapping: 4\n"
        "  m_ColorTemperature: 6570\n"
        "  m_UseColorTemperature: 0\n"
        f"--- !u!4 &{light_tf}\n"
        "Transform:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {light_go}}}\n"
        "  serializedVersion: 2\n"
        f"  m_LocalRotation: {{x: {quat[0]}, y: {quat[1]}, z: {quat[2]}, w: {quat[3]}}}\n"
        "  m_LocalPosition: {x: -10.37, y: 1.3, z: 8.63}\n"
        "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
        "  m_ConstrainProportionsScale: 0\n"
        "  m_Children: []\n"
        "  m_Father: {fileID: 0}\n"
        "  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}\n"
    )


def _camera_block(cam_go: int, cam_comp: int, cam_tf: int, quat) -> str:
    return (
        f"--- !u!1 &{cam_go}\n"
        "GameObject:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  serializedVersion: 6\n"
        "  m_Component:\n"
        f"  - component: {{fileID: {cam_tf}}}\n"
        f"  - component: {{fileID: {cam_comp}}}\n"
        "  m_Layer: 0\n"
        "  m_Name: Main Camera\n"
        "  m_TagString: MainCamera\n"
        "  m_Icon: {fileID: 0}\n"
        "  m_NavMeshLayer: 0\n"
        "  m_StaticEditorFlags: 0\n"
        "  m_IsActive: 1\n"
        f"--- !u!20 &{cam_comp}\n"
        "Camera:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {cam_go}}}\n"
        "  m_Enabled: 1\n"
        "  serializedVersion: 2\n"
        "  m_ClearFlags: 1\n"
        "  near clip plane: 0.3\n"
        "  far clip plane: 1000\n"
        "  field of view: 41.8\n"
        "  orthographic: 0\n"
        "  orthographic size: 5\n"
        f"--- !u!4 &{cam_tf}\n"
        "Transform:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {cam_go}}}\n"
        "  serializedVersion: 2\n"
        f"  m_LocalRotation: {{x: {quat[0]}, y: {quat[1]}, z: {quat[2]}, w: {quat[3]}}}\n"
        "  m_LocalPosition: {x: 20, y: 24, z: 30}\n"
        "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
        "  m_ConstrainProportionsScale: 0\n"
        "  m_Children: []\n"
        "  m_Father: {fileID: 0}\n"
        "  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}\n"
    )


def _volume_block(vol_go: int, vol_comp: int, vol_tf: int, profile_guid: str) -> str:
    return (
        f"--- !u!1 &{vol_go}\n"
        "GameObject:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  serializedVersion: 6\n"
        "  m_Component:\n"
        f"  - component: {{fileID: {vol_tf}}}\n"
        f"  - component: {{fileID: {vol_comp}}}\n"
        "  m_Layer: 0\n"
        "  m_Name: Global Volume\n"
        "  m_TagString: Untagged\n"
        "  m_Icon: {fileID: 0}\n"
        "  m_NavMeshLayer: 0\n"
        "  m_StaticEditorFlags: 0\n"
        "  m_IsActive: 1\n"
        f"--- !u!114 &{vol_comp}\n"
        "MonoBehaviour:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {vol_go}}}\n"
        "  m_Enabled: 1\n"
        "  m_EditorHideFlags: 0\n"
        "  m_Script: {fileID: 11500000, guid: 172515602e62fb746b5d573b38a5fe58, type: 3}\n"
        "  m_Name: \n"
        "  m_EditorClassIdentifier: \n"
        "  m_IsGlobal: 1\n"
        "  priority: 0\n"
        "  blendDistance: 0\n"
        "  weight: 1\n"
        f"  sharedProfile: {{fileID: 11400000, guid: {profile_guid}, type: 2}}\n"
        f"--- !u!4 &{vol_tf}\n"
        "Transform:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {vol_go}}}\n"
        "  serializedVersion: 2\n"
        "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
        "  m_LocalPosition: {x: 0, y: 0, z: 0}\n"
        "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
        "  m_ConstrainProportionsScale: 0\n"
        "  m_Children: []\n"
        "  m_Father: {fileID: 0}\n"
        "  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}\n"
    )


def _demo_scene_text() -> str:
    parts = [HEADER, _render_settings_block(LIGHTING_SETTINGS_GUID)]
    parts.append(_light_block(5000, 5001, 5002, SUN_QUAT))
    parts.append(_camera_block(5010, 5011, 5012, CAMERA_QUAT))
    parts.append(_volume_block(5020, 5021, 5022, VOLUME_PROFILE_GUID))
    parts.append(_go_transform_block(ROOT_GO, ROOT_TF, "Root", 0, ROOT_POS, _ROOT_QUAT, [CHILD_TF]))
    parts.append(_go_transform_block(CHILD_GO, CHILD_TF, "Child", ROOT_TF, CHILD_LOCAL, (0, 0, 0, 1), []))
    for name, spec in _INSTANCES.items():
        parent_fid = {"root": ROOT_TF, "child": CHILD_TF, "p3": _instance_transform_fid("P3")}[spec["parent"]]
        parts.append(
            _prefab_instance_block(
                _INST_BASE[name], name, spec["guid"], parent_fid, spec["local"], spec["scale"], spec["static"]
            )
        )
    return "".join(parts)


def _overview_scene_text() -> tuple[str, list[dict]]:
    """10x10 grid of 100 distinct prefabs at a uniform 4 m pitch -- Synty's
    catalogue-scene shape (spec §7 Overview heuristic as re-set 2026-09-06:
    at least ``stats.MIN_LAYOUT_PLACEMENTS`` = 100 placements, every one a
    distinct asset). 100 exactly, so the test sits on the floor."""
    parts = [HEADER, _render_settings_block(LIGHTING_SETTINGS_GUID)]
    overview_prefabs = []
    fid = 9000
    for r in range(10):
        for c in range(10):
            n = r * 10 + c
            ov_guid = guid(200 + n)
            overview_prefabs.append({"guid": ov_guid, "id": f"OV_Prefab_{n:02d}", "type": "prop"})
            parts.append(
                _prefab_instance_block(fid, f"OV_Prefab_{n:02d}", ov_guid, 0, (c * 4.0, 0.0, r * 4.0), (1.0, 1.0, 1.0), False)
            )
            fid += 10
    return "".join(parts), overview_prefabs


LIGHTING_SETTINGS_GUID = "00000000000000000000000000000fed"
VOLUME_PROFILE_GUID = "00000000000000000000000000000fee"


def _profile_asset_text() -> str:
    return (
        "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
        "--- !u!114 &-1000000000001\n"
        "MonoBehaviour:\n"
        "  m_ObjectHideFlags: 3\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  m_GameObject: {fileID: 0}\n"
        "  m_Enabled: 1\n"
        "  m_EditorHideFlags: 0\n"
        "  m_Script: {fileID: 11500000, guid: 0b2db86121404754db890f4c8dfe81b2, type: 3}\n"
        "  m_Name: Bloom\n"
        "  m_EditorClassIdentifier: \n"
        "  active: 1\n"
        "  intensity:\n"
        "    m_OverrideState: 1\n"
        "    m_Value: 5\n"
        "  dirtTexture:\n"
        "    m_OverrideState: 1\n"
        "    m_Value: {fileID: 0}\n"
        "--- !u!114 &-1000000000002\n"
        "MonoBehaviour:\n"
        "  m_ObjectHideFlags: 3\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  m_GameObject: {fileID: 0}\n"
        "  m_Enabled: 1\n"
        "  m_EditorHideFlags: 0\n"
        "  m_Script: {fileID: 11500000, guid: 66f335fb1ffd8684294ad653bf1c7564, type: 3}\n"
        "  m_Name: ColorAdjustments\n"
        "  m_EditorClassIdentifier: \n"
        "  active: 1\n"
        "  postExposure:\n"
        "    m_OverrideState: 1\n"
        "    m_Value: 0.2\n"
        "  colorFilter:\n"
        "    m_OverrideState: 0\n"
        "    m_Value: {r: 1, g: 1, b: 1, a: 1}\n"
        "--- !u!114 &11400000\n"
        "MonoBehaviour:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  m_GameObject: {fileID: 0}\n"
        "  m_Enabled: 1\n"
        "  m_EditorHideFlags: 0\n"
        "  m_Script: {fileID: 11500000, guid: d7fd9488000d3734a9e00ee676215985, type: 3}\n"
        "  m_Name: FixtureProfile\n"
        "  m_EditorClassIdentifier: \n"
        "  components:\n"
        "  - {fileID: -1000000000001}\n"
        "  - {fileID: -1000000000002}\n"
    )


def _meta_text(guid: str) -> str:
    return f"fileFormatVersion: 2\nguid: {guid}\nNativeFormatImporter:\n  mainObjectFileID: 100100000\n"


def build(root: Path) -> dict[str, Any]:
    """Write the fixture tree under ``root`` and return everything a test
    needs: scene paths, expected per-instance world positions, and the
    catalog dict (with ``source.extracted`` pointing at ``root``)."""
    pack_root = root / "Assets" / "Synty" / PACK_DIR
    scenes_dir = pack_root / "Scenes"
    prefabs_dir = pack_root / "Prefabs"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    prefabs_dir.mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "Synty" / "PolygonGeneric").mkdir(parents=True, exist_ok=True)  # shared dir, must be ignored

    for guid, meta in _PREFABS.items():
        prefab_path = prefabs_dir / f"{meta['id']}.prefab"
        prefab_path.write_text("--- !u!1001 &1\n", encoding="utf-8")
        prefab_path.with_suffix(".prefab.meta").write_text(_meta_text(guid), encoding="utf-8")

    demo_text = _demo_scene_text()
    (scenes_dir / "Demo.unity").write_text(demo_text, encoding="utf-8")
    (scenes_dir / "Demo_Copy.unity").write_text(demo_text, encoding="utf-8")

    overview_text, overview_prefabs = _overview_scene_text()
    for meta in overview_prefabs:
        p = prefabs_dir / f"{meta['id']}.prefab"
        p.write_text("--- !u!1001 &1\n", encoding="utf-8")
        p.with_suffix(".prefab.meta").write_text(_meta_text(meta["guid"]), encoding="utf-8")
    (scenes_dir / "Overview.unity").write_text(overview_text, encoding="utf-8")

    demo_profile_dir = scenes_dir / "Demo"
    demo_profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = demo_profile_dir / "FixtureVolume.asset"
    profile_path.write_text(_profile_asset_text(), encoding="utf-8")
    profile_path.with_suffix(".asset.meta").write_text(_meta_text(VOLUME_PROFILE_GUID), encoding="utf-8")

    lighting_path = demo_profile_dir / "FixtureSettings.lighting"
    lighting_path.write_text("--- !u!850595691 &1\nLightingSettings:\n  m_Name: FixtureSettings\n", encoding="utf-8")
    lighting_path.with_suffix(".lighting.meta").write_text(_meta_text(LIGHTING_SETTINGS_GUID), encoding="utf-8")

    assets = []
    for guid, meta in _PREFABS.items():
        assets.append(
            {
                "id": meta["id"],
                "type": meta["type"],
                "placeable": True,
                "guid": guid,
                "files": {"unity_prefab": f"Assets/Synty/{PACK_DIR}/Prefabs/{meta['id']}.prefab"},
            }
        )
    for meta in overview_prefabs:
        assets.append(
            {
                "id": meta["id"],
                "type": meta["type"],
                "placeable": True,
                "guid": meta["guid"],
                "files": {"unity_prefab": f"Assets/Synty/{PACK_DIR}/Prefabs/{meta['id']}.prefab"},
            }
        )
    catalog = {
        "pack_id": PACK_ID,
        "version": 2,
        "source": {"extracted": str(root).replace("\\", "/")},
        "assets": assets,
    }

    return {
        "root": root,
        "scenes_dir": scenes_dir,
        "demo_scene": scenes_dir / "Demo.unity",
        "demo_copy_scene": scenes_dir / "Demo_Copy.unity",
        "overview_scene": scenes_dir / "Overview.unity",
        "catalog": catalog,
        "expected_positions": EXPECTED_POSITIONS,
        "expected_yaw_deg": EXPECTED_YAW_DEG,
        "instance_fileids": dict(_INST_BASE),
        "prefabs": _PREFABS,
    }
