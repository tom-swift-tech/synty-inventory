"""Optic weapon-attachment gear heuristics."""

from synty_inventory.knowledge import infer
def _gear(stem: str) -> dict:
    rec = infer(stem)
    assert rec is not None, stem
    return rec.get("gear") or {}


def test_mod_scope_is_optic_attachment():
    g = _gear("SM_Wep_Mod_Scope_01")
    assert g["kind"] == "attachment"
    assert g["role"] == "optic"
    assert g["slot"] == "none"
    assert g["attach"] is True


def test_attachment_sniper_scope_is_optic():
    g = _gear("SM_Wep_Attachment_SniperScope_01")
    assert g["kind"] == "attachment"
    assert g["role"] == "optic"
    assert g["slot"] == "none"


def test_wep_scope_sniper_is_optic():
    g = _gear("SM_Wep_Scope_Sniper_01")
    assert g["kind"] == "attachment"
    assert g["role"] == "optic"
    assert g["slot"] == "none"


def test_american_scope_long_is_optic():
    g = _gear("SM_Wep_American_Scope_Long_01")
    assert g["kind"] == "attachment"
    assert g["role"] == "optic"
    assert g["slot"] == "none"


def test_sniper_weapon_stays_hand_r():
    g = _gear("SM_Wep_Sniper_01")
    assert g["kind"] == "weapon"
    assert g["slot"] == "hand_r"
    assert g.get("role") in (None, )


def test_non_optic_mod_is_attachment_without_role():
    g = _gear("SM_Wep_Mod_Mag_01")
    assert g["kind"] == "attachment"
    assert g["role"] is None
    assert g["slot"] == "none"
    assert g["attach"] is True
