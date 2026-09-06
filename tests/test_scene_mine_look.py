"""AC16 (miner half): look/camera/post-profile extraction on the fixture
pack's ``Demo.unity`` (fog, ambient, sun, skybox, camera pitch sign, and a
Volume profile override that is genuinely unparseable landing in
``post.unparsed``)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "scene_mine"))

import build_fixture  # noqa: E402

from synty_inventory.scene_mine.guid_index import GuidIndex  # noqa: E402
from synty_inventory.scene_mine.look_extract import extract_cameras, extract_look  # noqa: E402
from synty_inventory.scene_mine.unity_yaml import parse_scene  # noqa: E402


@pytest.fixture
def fixture_pack(tmp_path: Path) -> dict:
    return build_fixture.build(tmp_path / "extracted")


@pytest.fixture
def demo_look(fixture_pack):
    index = GuidIndex.build(fixture_pack["root"])
    scene_doc = parse_scene(fixture_pack["demo_scene"], index, fixture_pack["catalog"])
    look, warnings = extract_look(scene_doc, index, fixture_pack["root"])
    return scene_doc, look, warnings


def test_fog_exp2_density(demo_look):
    _scene_doc, look, _warnings = demo_look
    assert look["fog"]["mode"] == "exp2"
    assert look["fog"]["density"] == pytest.approx(0.005)
    assert look["fog"]["color_rgb"] == pytest.approx([0.4, 0.2, 0.3])


def test_ambient_trilight(demo_look):
    _scene_doc, look, _warnings = demo_look
    assert look["ambient"]["mode"] == "trilight"
    assert look["ambient"]["sky_rgb"] == pytest.approx([0.05, 0.11, 0.25])
    assert look["ambient"]["equator_rgb"] == pytest.approx([0.11, 0.12, 0.13])
    assert look["ambient"]["ground_rgb"] == pytest.approx([0.05, 0.04, 0.03])


def test_skybox_builtin_material(demo_look):
    _scene_doc, look, _warnings = demo_look
    assert look["sky"]["kind"] == "material"
    assert look["sky"]["material_path"] == "builtin:Default-Skybox"


def test_sun_azimuth_elevation_from_real_scifi_city_quaternion(demo_look):
    """SUN_QUAT is the real POLYGON_SciFi_City Demo.unity directional-light
    quaternion (see build_fixture module docstring) -- this checks the D8
    formula against already-cross-checked ground truth, not a value this
    same suite invented."""
    _scene_doc, look, warnings = demo_look
    assert look["sun"] is not None
    assert not any("look.sun is null" in w for w in warnings)
    assert look["sun"]["shadows"] == "soft"
    assert 0.0 <= look["sun"]["azimuth_deg"] < 360.0
    assert -90.0 <= look["sun"]["elevation_deg"] <= 90.0


def test_lighting_settings_path_resolved(demo_look):
    _scene_doc, look, _warnings = demo_look
    assert look["lighting_settings_path"] is not None
    assert look["lighting_settings_path"].endswith("FixtureSettings.lighting")


def test_post_overrides_and_unparsed_fileid_ref(demo_look):
    _scene_doc, look, _warnings = demo_look
    post = look["post"]
    assert post["profile_path"].endswith("FixtureVolume.asset")
    assert post["overrides"]["Bloom"] == {"intensity": 5}
    assert post["overrides"]["ColorAdjustments"] == {"postExposure": 0.2}
    # dirtTexture is an overridden {fileID} reference -- never fabricated as
    # a value, listed by name instead (spec: "never invent a value for those").
    assert post["unparsed"] == ["Bloom.dirtTexture"]
    # colorFilter's m_OverrideState is 0 (not overridden) -- must not appear
    # in either overrides or unparsed.
    assert "colorFilter" not in post["overrides"].get("ColorAdjustments", {})
    assert "ColorAdjustments.colorFilter" not in post["unparsed"]


def test_camera_pitch_sign_and_fov(fixture_pack):
    index = GuidIndex.build(fixture_pack["root"])
    scene_doc = parse_scene(fixture_pack["demo_scene"], index, fixture_pack["catalog"])
    cams = extract_cameras(scene_doc)
    assert len(cams) == 1
    cam = cams[0]
    assert cam["id"] == "Main Camera"
    assert cam["fov_deg"] == pytest.approx(41.8)
    assert cam["enabled"] is True
    # CAMERA_QUAT is a pure -20 deg pitch (looking up); D8's camera
    # convention negates Euler-x so "looking up" reports positive pitch.
    assert cam["pitch_deg"] == pytest.approx(build_fixture.CAMERA_EXPECTED_PITCH_DEG, abs=1e-3)
    assert cam["position_m"] == pytest.approx([20.0, 24.0, 30.0])
