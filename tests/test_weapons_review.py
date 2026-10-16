"""Weapon directory W4: the static review page (docs/weapon_directory.md section 3.9; AC20).

The page is parsed with the stdlib ``html.parser``; what the inline script does in a browser is checked by the
lead's capture checkpoint (and by the throwaway capture script), not here. Counts below are literals about the
committed fixture packs: 7 records have confidence below 0.6, 6 sit exactly on 0.6 (not low), the review pack holds a
14-member shield set (collapses), a 12-member knife set (does not) and one id with HTML metacharacters.
"""

from __future__ import annotations

import importlib.util
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_helpers", Path(__file__).parent / "fixtures" / "weapons" / "review_helpers.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
wfx = H.wfx

from synty_inventory.weapons.review import write_review_page  # noqa: E402

VOID = {"meta", "link", "br", "hr", "img", "input", "area", "base", "col", "embed", "source", "track", "wbr"}
LOW_IDS = {
    "FAKE_Generic/SM_Wep_Mystery_01", "FAKE_SciFi/SM_Prop_Device_01", "FAKE_SciFi/SM_Prop_Device_02",
    "FAKE_SciFi/SM_Prop_Device_03", "FAKE_SciFi/SM_Wep_Blaster_01", "FAKE_SciFi/SM_Wep_Mystery_01",
    "FAKE_SciFi/SM_Wep_Plasma_Gun_02",
}
TOKEN_AXE = "FAKE_Review/SM_Prop_Axe_Token_01"  # confidence exactly 0.60: not low


class Page(HTMLParser):
    """Collects what the checks need and verifies that tags nest and close."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.stack: list[str] = []
        self.sections: list[str] = []  # section ids in document order
        self.tiles: list[dict] = []  # attrs of every .tile, in order, plus its section / family
        self.urls: list[tuple[str, str, str]] = []  # (tag, attr, value)
        self.families: list[dict] = []
        self.scripts: list[dict] = []
        self.tags: list[str] = []
        self.doctype = None
        self._in_script = None
        self._script_text: list[str] = []
        self._family_depth: list[int] = []
        self.feed(text)
        self.close()
        if self.stack:
            self.problems.append(f"unclosed: {self.stack}")

    def handle_decl(self, decl):
        self.doctype = decl

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        for name in ("src", "href", "action", "data", "poster", "srcset"):
            if name in a:
                self.urls.append((tag, name, a[name] or ""))
        if tag == "section":
            self.sections.append(a.get("id", ""))
        if tag == "details" and "family" in (a.get("class") or "").split():
            self.families.append({"tiles": 0, "attrs": a})
            self._family_depth.append(len(self.stack))
        if "tile" in (a.get("class") or "").split() and "data-id" in a:
            self.tiles.append({**a, "_section": self.sections[-1] if self.sections else None,
                               "_family": len(self.families) - 1 if self._family_depth else None,
                               "_img": False})
            if self._family_depth:
                self.families[-1]["tiles"] += 1
        if tag == "img" and self.tiles and a.get("class") == "thumb":
            self.tiles[-1]["_img"] = a.get("src")
        if tag == "script":
            self._in_script, self._script_text = a, []
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"</{tag}> closes {self.stack[-1:] }")
            return
        self.stack.pop()
        if self._family_depth and len(self.stack) == self._family_depth[-1] and tag == "details":
            self._family_depth.pop()
        if tag == "script":
            self.scripts.append({"attrs": self._in_script, "text": "".join(self._script_text)})
            self._in_script = None

    def handle_data(self, data):
        if self._in_script is not None:
            self._script_text.append(data)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("review")
    cat = H.make_catalogs(tmp)
    directory, excluded = H.build_and_write(cat, overrides=wfx.overrides_doc(
        ids={"FAKE_Modern/SM_Wep_Pistol_01": {"confirm": True}, H.SWORD_02: {"set": {"genre": "scifi"}}}))
    wdir = cat / "weapons"
    with_icons = [H.SWORD_01, H.SWORD_02, "FAKE_Modern/SM_Wep_Pistol_01", H.SHIELD_SET[0], H.KNIFE_SET[0]]
    H.attach_icons(directory, wdir, with_icons)
    out_dir = wdir / "review"
    path = write_review_page(directory, out_dir, excluded=excluded, base_dir=wdir)
    text = path.read_text(encoding="utf-8")
    return SimpleNamespace(tmp=tmp, cat=cat, wdir=wdir, directory=directory, excluded=excluded, out_dir=out_dir,
                           path=path, text=text, page=Page(text), icons=with_icons)


def tile_ids(page: Page, section: str | None = None) -> list[str]:
    return [t["data-id"] for t in page.tiles if section is None or t["_section"] == section]


# --- AC20 ---------------------------------------------------------------------------------------------------

def test_ac20_the_page_is_valid_html5_that_the_stdlib_parser_accepts(world):
    page, text = world.page, world.text
    assert page.problems == []
    assert text.startswith("<!DOCTYPE html>") and (page.doctype or "").lower() == "doctype html"
    assert '<html lang="en">' in text and '<meta charset="utf-8">' in text
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in text  # usable on a phone
    assert re.search(r"<title>[^<]+</title>", text)
    ids = re.findall(r'\sid="([^"]*)"', text)
    assert len(ids) == len(set(ids))  # element ids are unique
    assert text.count("<script") == text.count("</script>") == 2
    assert "\r" not in text and text.endswith("\n")


def test_ac20_one_tile_per_record_and_per_excluded_row(world):
    want = sorted([w["id"] for w in world.directory["weapons"]] + [e["id"] for e in world.excluded["excluded"]])
    got = sorted(tile_ids(world.page))
    assert got == want
    assert len(got) == len(set(got))
    assert len(world.directory["weapons"]) >= 170 and len(world.excluded["excluded"]) == 22
    excluded_ids = {e["id"] for e in world.excluded["excluded"]}
    for t in world.page.tiles:
        assert ("data-excluded" in t) == (t["data-id"] in excluded_ids)
        assert (t["_section"] == "sec-excluded") == (t["data-id"] in excluded_ids)


def test_ac20_sections_come_in_the_spec_order(world):
    archetypes = sorted({w["archetype"] for w in world.directory["weapons"]
                         if w["review"]["confidence"] >= 0.6 and w["archetype"] != "unknown"})
    assert world.page.sections == ["sec-low", "sec-unknown", *[f"sec-archetype-{a}" for a in archetypes], "sec-excluded"]
    assert len(archetypes) >= 30
    assert [m for m in re.findall(r"<h2>([^<]+?) <span", world.text)][:2] == ["Low confidence", "Unknown"]
    assert re.findall(r"<h2>([^<]+?) <span", world.text)[-1] == "Excluded"


def test_ac20_the_low_confidence_section_holds_exactly_the_records_below_0_6(world):
    low = set(tile_ids(world.page, "sec-low"))
    below = {w["id"] for w in world.directory["weapons"] if w["review"]["confidence"] < 0.6}
    assert low == below == LOW_IDS and len(low) == 7
    # records sitting exactly on 0.6 are not low, and no tile appears twice across sections
    assert TOKEN_AXE not in low
    assert world.page.tiles[[t["data-id"] for t in world.page.tiles].index(TOKEN_AXE)]["_section"] == "sec-archetype-axe"
    at_edge = [w for w in world.directory["weapons"] if w["review"]["confidence"] == 0.6]
    assert len(at_edge) == 7 and not any(w["id"] in low for w in at_edge)


def test_ac20_unknown_holds_the_unknown_archetypes_that_are_not_low(world):
    unknown = set(tile_ids(world.page, "sec-unknown"))
    want = {w["id"] for w in world.directory["weapons"]
            if w["archetype"] == "unknown" and w["review"]["confidence"] >= 0.6}
    assert unknown == want and len(unknown) == 25
    assert unknown.isdisjoint(LOW_IDS)


def test_ac20_each_archetype_section_holds_only_its_archetype(world):
    arch = {w["id"]: w["archetype"] for w in world.directory["weapons"]}
    for t in world.page.tiles:
        if t["_section"].startswith("sec-archetype-"):
            assert arch[t["data-id"]] == t["_section"].removeprefix("sec-archetype-")
            assert float(t["data-conf"]) >= 0.6
    assert len(tile_ids(world.page, "sec-archetype-shield")) == 8 + 14


def test_ac20_tiles_are_sorted_by_genre_family_id_within_a_section(world):
    key = {w["id"]: (w["genre"], w["family"], w["id"]) for w in world.directory["weapons"]}
    for sec in world.page.sections:
        if sec == "sec-excluded":
            continue
        ids = tile_ids(world.page, sec)
        assert ids == sorted(ids, key=lambda i: key[i]), sec


def test_ac20_references_only_relative_paths_and_contains_no_http_url(world):
    assert "http://" not in world.text and "https://" not in world.text
    low = world.text.lower()
    assert "http:" not in low and "https:" not in low and "ftp:" not in low and "file:" not in low
    markup = re.sub(r"<script.*?</script>", "", low, flags=re.S)  # CSS and HTML only; the script has createObjectURL(
    assert "@import" not in markup and "url(" not in markup
    for tag, attr, value in world.page.urls:
        assert value.startswith("#") or not re.match(r"^([a-z][a-z0-9+.-]*:|/|\\|[A-Za-z]:)", value), (tag, attr, value)
        assert "\\" not in value
    assert not [u for u in world.page.urls if u[0] in ("link", "form", "iframe", "a") and not u[2].startswith("#")]
    assert not [s for s in world.page.scripts if "src" in s["attrs"]]
    assert "<link" not in low and "<iframe" not in low and "<form" not in low and "<object" not in low


def test_the_page_makes_no_requests_and_writes_nothing(world):
    js = next(s for s in world.page.scripts if "type" not in s["attrs"])["text"]
    for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "importScripts", "import(",
                      "document.cookie", "indexedDB", ".submit(", "window.open", "location.href", "eval(",
                      "new Function", "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert forbidden not in js, forbidden
    assert "localStorage" in js and "try {" in js  # state only in a guarded localStorage
    assert "window.localStorage" in js and "store = null" in js
    assert "weapon-corrections/1" in js and "download" in js and "navigator.clipboard" in js


def test_thumbnails_are_relative_paths_to_files_that_exist_and_other_tiles_are_text_only(world):
    with_img = {t["data-id"]: t["_img"] for t in world.page.tiles if t["_img"]}
    assert sorted(with_img) == sorted(world.icons)
    for rid, src in with_img.items():
        assert src.startswith("../icons/") and src.endswith("@64.png") and "%" not in src.replace("%20", "")
        assert (world.out_dir / src).is_file(), src
    assert with_img[H.SWORD_02] == "../icons/FAKE_Fantasy/SM_Wep_Sword_02@64.png"
    plain = [t for t in world.page.tiles if not t["_img"]]
    assert len(plain) == len(world.page.tiles) - 5
    assert world.text.count('class="thumb none"') == len(plain)


def test_a_thumbnail_that_is_missing_on_disk_gives_a_text_only_tile(world, tmp_path):
    directory = json.loads(json.dumps(world.directory))
    directory["weapons"][0]["visuals"]["thumb"] = "icons/gone@64.png"
    page = Page(write_review_page(directory, tmp_path / "r", excluded=world.excluded, base_dir=world.wdir)
                .read_text(encoding="utf-8"))
    assert not any(t["_img"] for t in page.tiles if t["data-id"] == directory["weapons"][0]["id"])


def test_a_family_of_more_than_12_collapses_to_one_counted_tile_that_expands(world):
    shield = [t for t in world.page.tiles if t["data-id"] in set(H.SHIELD_SET)]
    assert len(shield) == 14
    fams = {t["_family"] for t in shield}
    assert len(fams) == 1 and None not in fams  # all 14 live inside one <details>
    assert re.search(r'<summary class="family-tile"><span class="id">sm_wep_shield_set \(fantasy\)</span>'
                     r'<span class="count">&times;17</span>', world.text)  # 14 here + 3 shields of FAKE_Fantasy: same genre+family
    # a family of exactly 12 is not collapsed, a 13th member would be
    knife = [t for t in world.page.tiles if t["data-id"] in set(H.KNIFE_SET)]
    assert len(knife) == 12 and {t["_family"] for t in knife} == {None}
    # the collapsed members are still reachable as tiles: one per record, in the section of their archetype
    assert {t["_section"] for t in shield} == {"sec-archetype-shield"}
    assert world.page.families and all(f["tiles"] > 12 for f in world.page.families)
    assert not any('class="family"' in t.get("class", "") for t in world.page.tiles)


def test_collapse_threshold_is_per_section_genre_and_family(world, tmp_path):
    directory = json.loads(json.dumps(world.directory))
    extra = [w for w in directory["weapons"] if w["id"] == H.KNIFE_SET[0]][0]
    new = json.loads(json.dumps(extra))
    new["id"], new["asset_id"] = f"{extra['pack']}/SM_Wep_Knife_Set_13", "SM_Wep_Knife_Set_13"
    directory["weapons"].append(new)
    directory["weapons"].sort(key=lambda w: w["id"])
    page = Page(write_review_page(directory, tmp_path / "r", excluded=world.excluded, base_dir=world.wdir)
                .read_text(encoding="utf-8"))
    knife = [t for t in page.tiles if t["data-id"].startswith("FAKE_Review/SM_Wep_Knife_Set_")]
    assert len(knife) == 13 and len({t["_family"] for t in knife}) == 1 and knife[0]["_family"] is not None


def test_html_metacharacters_in_an_id_are_escaped_everywhere(world):
    assert H.ODD_ID in tile_ids(world.page)  # the parser unescapes the attribute back to the original id
    assert "<b>" not in world.text and '&"q"' not in world.text
    assert "&lt;b&gt;&amp;&quot;q&quot;" in world.text
    assert len(world.page.problems) == 0


def test_tiles_carry_the_values_the_panel_edits_and_the_family_glob(world):
    by_id = {t["data-id"]: t for t in world.page.tiles}
    sword = by_id[H.SWORD_02]
    assert (sword["data-role"], sword["data-kind"], sword["data-archetype"], sword["data-hold_class"]) == (
        "whole", "melee", "sword", "melee_one")
    assert sword["data-genre"] == "scifi" and sword["data-status"] == "overridden"  # from the override in this world
    assert by_id["FAKE_Modern/SM_Wep_Pistol_01"]["data-status"] == "reviewed"
    shield = by_id[H.SHIELD_SET[3]]
    assert shield["data-glob"] == "FAKE_Review/SM_Wep_Shield_Set_*" and shield["data-globn"] == "14"
    assert by_id[H.KNIFE_SET[0]]["data-glob"] == "FAKE_Review/SM_Wep_Knife_Set_*"
    assert by_id[H.SWORD_REVIEW]["data-glob"] == "FAKE_Review/SM_Wep_Sword_Review_*" and by_id[H.SWORD_REVIEW]["data-globn"] == "1"
    # the glob of a family always matches every member of that family
    import fnmatch

    for t in world.page.tiles:
        if t.get("data-glob"):
            assert fnmatch.fnmatchcase(t["data-id"], t["data-glob"]), t["data-id"]
    excluded = next(t for t in world.page.tiles if "data-excluded" in t)
    assert excluded["data-reason"] and excluded["data-glob"] == ""


def test_the_status_confidence_and_flags_are_shown_on_the_tile(world):
    assert 'class="tag status-reviewed">reviewed</span>' in world.text
    assert 'class="tag status-overridden">overridden</span>' in world.text
    assert 'class="tag conf-low">0.20</span>' in world.text and 'class="tag conf-ok">0.93</span>' in world.text
    assert "unmeasured" in world.text  # flags column (the unmeasured build)


def test_enums_for_the_dropdowns_come_from_the_spec_lists(world):
    block = next(s for s in world.page.scripts if s["attrs"].get("id") == "enums")
    enums = json.loads(block["text"])
    assert enums["role"] == ["whole", "part", "ammo", "carrier", "emplaced"]
    assert enums["kind"] == ["ranged", "melee", "thrown", "shield"]
    assert enums["hold_class"] == ["one_hand", "long_gun", "melee_one", "melee_two", "melee_bat", "bow", "crossbow",
                                   "thrown", "shield", "none"]
    assert enums["genre"] == ["modern", "scifi", "fantasy", "western", "other"]
    assert len(enums["archetype"]) == 36 and enums["archetype"][-1] == "unknown" and "wand" in enums["archetype"]
    assert enums["carrier"] == ["quiver", "sheath", "scabbard", "holster"]
    assert enums["ammo"] == ["bullet", "shell", "arrow", "bolt", "rocket", "other"]


def test_the_panel_has_the_controls_the_spec_names(world):
    for needle in ('id="f-role"', 'id="f-kind"', 'id="f-archetype"', 'id="f-hold_class"', 'id="f-genre"',
                   ">Mark correct<", ">Not a weapon<", ">Restore<", "Apply to family", 'id="note"',
                   ">Download corrections.json<", ">Copy to clipboard<"):
        assert needle in world.text, needle


def test_the_page_is_byte_identical_on_a_second_render(world, tmp_path):
    first = world.path.read_bytes()
    again = write_review_page(world.directory, world.out_dir, excluded=world.excluded, base_dir=world.wdir)
    assert again == world.path and again.read_bytes() == first


# --- filters ------------------------------------------------------------------------------------------------

def test_only_unreviewed_drops_reviewed_and_overridden_records(world, tmp_path):
    page = Page(write_review_page(world.directory, tmp_path / "r", only_unreviewed=True, excluded=world.excluded,
                                  base_dir=world.wdir).read_text(encoding="utf-8"))
    ids = set(tile_ids(page))
    assert "FAKE_Modern/SM_Wep_Pistol_01" not in ids and H.SWORD_02 not in ids  # reviewed / overridden
    assert H.SWORD_01 in ids
    assert len(ids) == len(world.directory["weapons"]) - 2 + 22  # excluded rows are not filtered


def test_max_confidence_and_pack_filters(world, tmp_path):
    page = Page(write_review_page(world.directory, tmp_path / "r", max_confidence=0.6, excluded=world.excluded,
                                  base_dir=world.wdir).read_text(encoding="utf-8"))
    recs = [t for t in page.tiles if "data-excluded" not in t]
    assert len(recs) == 7 + 7 and all(float(t["data-conf"]) <= 0.6 for t in recs)
    page = Page(write_review_page(world.directory, tmp_path / "p", packs={"FAKE_Review"}, excluded=world.excluded,
                                  base_dir=world.wdir).read_text(encoding="utf-8"))
    assert {t["data-pack"] for t in page.tiles} == {"FAKE_Review"}
    assert len(page.tiles) == 14 + 12 + 3 and page.sections[-1] == "sec-excluded"


# --- CLI ----------------------------------------------------------------------------------------------------

def test_cli_review_writes_the_page_under_weapons_review(tmp_path, monkeypatch, capsys):
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    cat = H.make_catalogs(tmp_path)
    directory, excluded = H.build_and_write(cat)
    H.attach_icons(directory, cat / "weapons", [H.SWORD_01])
    from synty_inventory.weapons.directory import write_directory

    write_directory(cat, directory, excluded)
    cfg = H.write_config(tmp_path, cat)
    before = {p.name for p in (cat / "weapons").iterdir()}
    code, out = H.run(cfg, capsys, ["weapons", "review"])
    assert code == 0 and out["ok"] is True
    page = cat / "weapons" / "review" / "index.html"
    assert page.is_file()
    assert {p.name for p in (cat / "weapons").iterdir()} == before | {"review"}
    parsed = Page(page.read_text(encoding="utf-8"))
    assert parsed.problems == [] and len(parsed.tiles) == len(directory["weapons"]) + len(excluded["excluded"])
    assert next(t for t in parsed.tiles if t["data-id"] == H.SWORD_01)["_img"] == "../icons/FAKE_Fantasy/SM_Wep_Sword_01@64.png"
    # --out DIR, the filters, and a rerun
    custom = tmp_path / "elsewhere"
    code, out = H.run(cfg, capsys, ["weapons", "review", "--out", str(custom), "--pack", "FAKE_Review",
                                    "--only-unreviewed", "--max-confidence", "1"])
    assert code == 0
    parsed = Page((custom / "index.html").read_text(encoding="utf-8"))
    assert {t["data-pack"] for t in parsed.tiles} == {"FAKE_Review"}
    assert next(t for t in parsed.tiles if t["data-id"] == H.SHIELD_SET[0])["_img"] is False  # no icon for it here
    code, out = H.run(cfg, capsys, ["weapons", "review", "--pack", "NO_SUCH_PACK"])
    assert code == 2 and out["ok"] is False


def test_cli_review_without_a_built_directory_exits_2(tmp_path, monkeypatch, capsys):
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    cat = H.make_catalogs(tmp_path)
    code, out = H.run(H.write_config(tmp_path, cat), capsys, ["weapons", "review"])
    assert code == 2 and "weapons build" in out["error"]
    assert not (cat / "weapons").exists()
