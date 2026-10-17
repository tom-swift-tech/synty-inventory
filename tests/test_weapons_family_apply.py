"""Weapon directory W5: the review page's family tile and its "Apply to family" scope agree (AC36).

The world: FAKE_Review's 14-member shield set has one member moved to the Unknown section (an override), one more
shield-set id that the build rejects (a non-placeable row, so it sits in ``excluded.json``), and a second pack
(FAKE_Review2) that repeats the same family name. For every tile and family tile the page shows an N; N must equal
the number of ids the written glob resolves to, measured with the real corrections matcher (``apply_corrections``
then ``overrides.matching_keys``), not with a re-implementation of fnmatch.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_helpers", Path(__file__).parent / "fixtures" / "weapons" / "review_helpers.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
wfx = H.wfx

from synty_inventory.weapons import icons  # noqa: E402
from synty_inventory.weapons.corrections import apply_corrections  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides, matching_keys  # noqa: E402
from synty_inventory.weapons.review import write_review_page  # noqa: E402

from test_weapons_review import Page  # noqa: E402  (the stdlib-parser page model of the W4 tests)

SECOND = "FAKE_Review2"
MOVED = f"{H.REVIEW_PACK}/SM_Wep_Shield_Set_14"  # leaves the shield section for Unknown
EXTRA_ID = f"{H.REVIEW_PACK}/SM_Wep_Shield_Set_99"  # rejected (non-placeable): an excluded row inside the glob


def _glob_ids(glob: str, all_ids: set[str]) -> set[str]:
    """The ids a family correction written with this glob applies to, by the real corrections matcher."""
    doc, _ = apply_corrections(
        {"schema": "weapon-corrections/1", "corrections": [{"target": {"glob": glob}, "confirm": True}]},
        empty_overrides())
    return {i for i in all_ids if matching_keys(i, doc)}


def _make_catalogs(tmp_path: Path) -> Path:
    cat = H.make_catalogs(tmp_path)
    mk = H._load("make_catalogs")
    src = cat / f"{H.REVIEW_PACK}.json"
    doc = json.loads(src.read_text(encoding="utf-8"))
    doc["assets"].append(mk._asset(H.REVIEW_PACK, "SM_Wep_Shield_Set_99", placeable=False))
    doc["asset_count"] = len(doc["assets"])
    src.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    twin = json.loads(json.dumps(doc))  # the same family names under another pack (shields only)
    twin["pack_id"] = SECOND
    twin["assets"] = [mk._asset(SECOND, a["id"]) for a in doc["assets"] if a["id"].startswith("SM_Wep_Shield_Set_")
                      and a["id"] != "SM_Wep_Shield_Set_99"]
    twin["asset_count"] = len(twin["assets"])
    (cat / f"{SECOND}.json").write_text(json.dumps(twin, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return cat


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("famapply")
    cat = _make_catalogs(tmp)
    settings = {**H.pack_settings(), SECOND: {"setting": "fantasy", "era": "medieval"}}
    directory, excluded = H.build_and_write(
        cat, pack_settings=settings,
        overrides=wfx.overrides_doc(ids={MOVED: {"set": {"archetype": "unknown"}}}))
    wdir = cat / "weapons"
    path = write_review_page(directory, wdir / "review", excluded=excluded, base_dir=wdir)
    text = path.read_text(encoding="utf-8")
    all_ids = {w["id"] for w in directory["weapons"]} | {e["id"] for e in excluded["excluded"]}
    return SimpleNamespace(cat=cat, wdir=wdir, directory=directory, excluded=excluded, path=path, text=text,
                           page=Page(text), all_ids=all_ids)


def test_the_world_has_the_shape_the_checks_need(world):
    ids = {w["id"] for w in world.directory["weapons"]}
    assert MOVED in ids and EXTRA_ID in {e["id"] for e in world.excluded["excluded"]}
    by_sec = {t["data-id"]: t["_section"] for t in world.page.tiles}
    assert by_sec[MOVED] == "sec-unknown" and by_sec[f"{H.REVIEW_PACK}/SM_Wep_Shield_Set_01"] == "sec-archetype-shield"
    assert by_sec[f"{SECOND}/SM_Wep_Shield_Set_01"] == "sec-archetype-shield"


def test_a_family_tile_never_spans_two_packs(world):
    fams = world.page.families
    assert len(fams) == 2  # one per pack: 13 + 14 shields (a cross-pack collapse would give one tile)
    per_family: dict[int, set[str]] = {}
    for t in world.page.tiles:
        if t["_family"] is not None:
            per_family.setdefault(t["_family"], set()).add(t["data-pack"])
    assert all(len(packs) == 1 for packs in per_family.values()) and len(per_family) == 2
    assert {next(iter(p)) for p in per_family.values()} == {H.REVIEW_PACK, SECOND}


def test_the_tile_count_is_what_it_holds_and_reads_k_of_n_when_the_glob_is_wider(world):
    tiles = {f["attrs"]["data-glob"]: f["attrs"] for f in world.page.families}
    review = tiles[f"{H.REVIEW_PACK}/SM_Wep_Shield_Set_*"]
    # 14 members - 1 moved to Unknown = 13 held; the glob matches 14 records + 1 excluded row
    assert (review["data-count"], review["data-globn"]) == ("13", "15")
    assert '<span class="count">&times;13</span><span class="of">of 15</span>' in world.text
    second = tiles[f"{SECOND}/SM_Wep_Shield_Set_*"]
    assert (second["data-count"], second["data-globn"]) == ("14", "14")
    assert '<span class="count">&times;14</span><span class="sub">' in world.text  # k == N: no "of"


def test_for_every_family_tile_the_displayed_n_is_what_the_written_glob_resolves_to(world):
    checked = 0
    for fam in world.page.families:
        glob = fam["attrs"]["data-glob"]
        assert glob
        assert int(fam["attrs"]["data-globn"]) == len(_glob_ids(glob, world.all_ids)), glob
        checked += 1
    assert checked == 2


def test_for_every_record_tile_the_label_n_is_what_the_written_glob_resolves_to(world):
    n_checked = 0
    for t in world.page.tiles:
        glob = t.get("data-glob")
        if not glob:
            continue
        resolved = _glob_ids(glob, world.all_ids)
        assert int(t["data-globn"]) == len(resolved), (t["data-id"], glob)
        word = "id" if len(resolved) == 1 else "ids"
        assert t["data-famlabel"] == f"Apply to family ({len(resolved)} {word})", t["data-id"]
        assert t["data-id"] in resolved  # the glob always covers the tile it was written from
        n_checked += 1
    assert n_checked > 40
    # the two packs resolve separately: the same family name in another pack is never in the id set
    review = _glob_ids(f"{H.REVIEW_PACK}/SM_Wep_Shield_Set_*", world.all_ids)
    assert EXTRA_ID in review and MOVED in review and not any(i.startswith(SECOND) for i in review)


def test_the_panel_script_takes_its_label_from_the_page(world):
    js = next(s for s in world.page.scripts if "type" not in s["attrs"])["text"]
    assert "data-famlabel" in js and "Apply to family" in world.text
    assert 'id="c-fam"' in world.text and 'id="p-fam"' in world.text


# --- in a real browser: the label the reviewer reads and the glob that gets written -------------------------------

_BROWSER: dict = {}


def _chromium():
    if "reason" not in _BROWSER:
        reason = None
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                icons._launch_browser(pw, False).close()
        except Exception as exc:  # noqa: BLE001
            reason = f"no Chromium here: {str(exc).splitlines()[0] if str(exc) else exc!r}"
        _BROWSER["reason"] = reason
    if _BROWSER["reason"]:
        pytest.skip(_BROWSER["reason"])


def test_in_chromium_the_checkbox_label_and_the_written_glob_agree(world):
    _chromium()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = icons._launch_browser(pw, False)
        try:
            page = browser.new_page()
            page.goto(world.path.as_uri())
            for rid in (f"{H.REVIEW_PACK}/SM_Wep_Shield_Set_01", f"{SECOND}/SM_Wep_Shield_Set_01",
                        "FAKE_Fantasy/SM_Wep_Sword_01"):
                page.locator(f'.tile[data-id="{rid}"]').first.evaluate("e => e.click()")
                label = page.locator("#l-fam").inner_text().strip()
                page.locator("#c-fam").check()
                page.locator("#b-ok").click()
                corr = page.evaluate("() => window.__buildCorrections()")
                assert len(corr["corrections"]) == 1
                target = corr["corrections"][0]["target"]
                assert "glob" in target, rid
                n = len(_glob_ids(target["glob"], world.all_ids))
                assert label == f"Apply to family ({n} {'id' if n == 1 else 'ids'})", (rid, label, target)
                page.locator("#b-clear").click()
        finally:
            browser.close()
