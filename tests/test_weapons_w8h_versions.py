"""W8h: versions and digests (AC93; docs/weapon_attachments.md 11 and 13.1). The constants are literals, not the code's.

The byte-identity of the default export against the stored W7 reference is pinned by ``test_weapons_w8d_regression`` /
``test_weapons_w8d_export`` (the ``w8d_w7_*`` files are never re-blessed); this file pins the numbers and the digest split.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("w8h_world", Path(__file__).parent / "fixtures" / "weapons" / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons.export import export_snapshot  # noqa: E402
from synty_inventory.weapons.rules import attach_rules_digest, load_rules, weapon_rules_digest  # noqa: E402

PACK = "FAKE_SightVer"
WORLD = {PACK: {"hosts": {"SM_Wep_Rifle_Ver_01": W.host_node("SM_Wep_Rifle_Ver_01", W.box_rifle())},
                "parts": {"SM_Wep_IronSight_Front_01": W.sight_part, "SM_Wep_IronSight_Rear_01": W.sight_part}}}


def snapshot(directory, *, attachments):
    return export_snapshot(
        directory, game="g", pack_ids=None, ids=None, roles={"whole", "part"} if attachments else {"whole"}, engines={"godot"},
        frame="godot", profile="private", pack_meta={}, rules_digest=weapon_rules_digest(load_rules()),
        overrides_digest="0" * 16, attachments=attachments)


def test_ac93_the_version_constants():
    assert pkg.WEAPON_ATTACH_VERSION == 8
    assert pkg.WEAPON_GEOMETRY_VERSION == 5


def test_ac93_the_directory_header_and_the_attachments_export_record_attach_version_8(tmp_path):
    directory = W.build(tmp_path, WORLD)[0]
    assert directory["attach_version"] == 8 and directory["geometry_version"] == 5
    assert len(directory["attach_rules_digest"]) == 16
    gf = snapshot(directory, attachments=True)["generated_from"]
    assert gf["attach_version"] == 8 and gf["attach_rules_digest"] == directory["attach_rules_digest"]


def test_ac93_the_default_export_header_has_neither_attach_key(tmp_path):
    gf = snapshot(W.build(tmp_path, WORLD)[0], attachments=False)["generated_from"]
    assert "attach_version" not in gf and "attach_rules_digest" not in gf
    assert gf["rules_digest"] == "7b9829af37328fe7" and gf["geometry_version"] == 5


def test_ac93_the_rules_digest_is_the_w7_one_and_the_genre_table_is_outside_it():
    rules = load_rules()
    assert weapon_rules_digest(rules) == "7b9829af37328fe7"
    assert rules["attachment_rules"]["attach_genre_by_pack"]  # the shipped table is non-empty, yet the digest above is the W7 one
    empty = W.sight_rules({})
    assert weapon_rules_digest(empty) == "7b9829af37328fe7"
    assert attach_rules_digest(empty) != attach_rules_digest(rules)
