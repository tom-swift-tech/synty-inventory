"""W6b: ``carry_icon_links`` carries the optional W6 keys (``icon_mode``, ``visually_identical``) with the link.

Direct unit test of the rebuild carry-forward: a temp catalogs dir holds a previous directory.json plus the icon files
it names. All expected values are literals.
"""

from __future__ import annotations

import json
from pathlib import Path

from synty_inventory.weapons.directory import carry_icon_links


def _fresh(wid: str) -> dict:
    """A record as ``build`` derives it: visuals all-null, one variant per letter."""
    return {
        "id": wid, "pack": "PackX", "asset_id": wid,
        "visuals": {"icon": None, "thumb": None, "icon_input_sha": None,
                    "variants": [{"variant_id": "B", "icon": None, "icon_input_sha": None}]},
    }


def _old(wid: str) -> dict:
    return {
        "id": wid, "pack": "PackX", "asset_id": wid,
        "visuals": {"icon": f"icons/PackX/{wid}.png", "thumb": f"icons/PackX/{wid}@64.png",
                    "icon_input_sha": "sha-rec", "icon_mode": "blend_retry",
                    "variants": [{"variant_id": "B", "icon": f"icons/PackX/{wid}@B.png", "icon_input_sha": "sha-var",
                                  "icon_mode": "blend_retry", "visually_identical": True}]},
    }


def _setup(tmp_path: Path, present: set[str]) -> Path:
    wdir = tmp_path / "weapons"
    (wdir / "icons" / "PackX").mkdir(parents=True)
    (wdir / "directory.json").write_text(
        json.dumps({"weapons": [_old("kept"), _old("lost")]}), encoding="utf-8")
    for name in present:
        (wdir / "icons" / "PackX" / name).write_bytes(b"png")
    return tmp_path


def test_icon_mode_and_visually_identical_are_carried_with_the_link(tmp_path):
    cat = _setup(tmp_path, {"kept.png", "kept@64.png", "kept@B.png", "kept@B@64.png"})
    directory = {"weapons": [_fresh("kept")]}
    carry_icon_links(cat, directory)
    vis = directory["weapons"][0]["visuals"]
    assert vis["icon"] == "icons/PackX/kept.png" and vis["icon_input_sha"] == "sha-rec"
    assert vis["icon_mode"] == "blend_retry"
    var = vis["variants"][0]
    assert var["icon"] == "icons/PackX/kept@B.png" and var["icon_input_sha"] == "sha-var"
    assert var["icon_mode"] == "blend_retry" and var["visually_identical"] is True


def test_nothing_is_carried_when_the_icon_file_is_missing(tmp_path):
    # "lost": the record's thumb and the variant's @64 thumbnail are missing, so neither link is carried.
    cat = _setup(tmp_path, {"lost.png", "lost@B.png"})
    directory = {"weapons": [_fresh("lost")]}
    carry_icon_links(cat, directory)
    vis = directory["weapons"][0]["visuals"]
    assert vis["icon"] is None and vis["thumb"] is None and "icon_mode" not in vis
    var = vis["variants"][0]
    assert var["icon"] is None and var["icon_input_sha"] is None
    assert "icon_mode" not in var and "visually_identical" not in var


def test_variant_keys_follow_only_their_own_link_and_junk_values_are_dropped(tmp_path):
    cat = _setup(tmp_path, {"kept.png", "kept@64.png"})  # record link exists, variant pictures do not
    prev_path = cat / "weapons" / "directory.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8"))
    prev["weapons"][0]["visuals"]["icon_mode"] = "other"
    prev_path.write_text(json.dumps(prev), encoding="utf-8")
    directory = {"weapons": [_fresh("kept")]}
    carry_icon_links(cat, directory)
    vis = directory["weapons"][0]["visuals"]
    assert vis["icon"] == "icons/PackX/kept.png" and "icon_mode" not in vis  # only "blend_retry" is carried
    assert vis["variants"][0]["icon"] is None
    assert "icon_mode" not in vis["variants"][0] and "visually_identical" not in vis["variants"][0]
