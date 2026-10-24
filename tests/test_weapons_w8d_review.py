"""W8d: the Attachments section of the review page (docs/weapon_attachments.md 6.2; AC76).

World: ``w8d_world`` (review_helpers packs plus FAKE_Attach / FAKE_Mount / FAKE_CompA / FAKE_CompB), 39 attachment parts and 50
mount-bearing hosts. Literals below were worked out from the fixture meshes:

* ``FAKE_CompA/SM_Wep_Rifle_Mag_01`` is a magazine/standard part whose measured forward is +z (flip to -z). Its hosts: twins
  FAKE_CompA/Alpha and FAKE_Mount/Mount_01 (0.95), cross_pack_fit FAKE_Mount/Double_01 (0.5), then pending (no mount) hosts
  Beta and Epsilon (same_pack_fit) and more cross-pack ones:
  3 compatible + 37 pending = 40 rows in the full world (A5 item 0: the two hosts named `SM_Prop_*` take no
  attachment, so they are in no part's host list).
* ``FAKE_Attach/SM_Wep_Footless_Scope_01`` has no measurable anchor: nothing to flip.
* ``FAKE_CompA/SM_Wep_Rifle_Alpha_01`` is a host with all five mount slots; its optic seat is the child node
  ``SM_Wep_Rifle_Alpha_01_Scope`` (0.90), muzzle a probe seat (0.80), underbarrel and laser_light ``none`` (no_child_no_probe).
* 9 hosts carry the review reason ``mount_missing``: the "No mount" chip shows 9.

The browser tests drive the page in Chromium (skipped cleanly when none is installed), read ``window.__buildCorrections()`` and
feed the result to ``validate_corrections`` / ``apply_corrections``; one test rebuilds the directory with the resulting
overrides and checks the flip really turned the anchor.
"""

from __future__ import annotations

import importlib.util
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8d_world", FIX / "w8d_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)
H = X.H

from synty_inventory.weapons import ATTACH_SLOTS  # noqa: E402
from synty_inventory.weapons import corrections as C  # noqa: E402
from synty_inventory.weapons import icons  # noqa: E402
from synty_inventory.weapons import overrides as ovr  # noqa: E402
from synty_inventory.weapons.review import write_review_page  # noqa: E402

MAG = "FAKE_CompA/SM_Wep_Rifle_Mag_01"
ALPHA = "FAKE_CompA/SM_Wep_Rifle_Alpha_01"
MOUNT_01 = "FAKE_Mount/SM_Wep_Rifle_Mount_01"
FOOTLESS = "FAKE_Attach/SM_Wep_Footless_Scope_01"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
       b"\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82")


class Page(HTMLParser):
    """Sections, tiles (with the section they sit in), scripts and every URL-bearing attribute."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.sections: list[str] = []
        self.tiles: list[dict] = []
        self.urls: list[tuple[str, str, str]] = []
        self.pv_imgs: list[dict] = []  # <img class="pv"> inside tiles
        self.scripts: list[dict] = []
        self._tile_depth = 0
        self._stack: list[str] = []
        self._script = None
        self._buf: list[str] = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        for name in ("src", "href", "action", "data", "poster", "srcset"):
            if name in a:
                self.urls.append((tag, name, a[name]))
        if tag == "section":
            self.sections.append(a.get("id", ""))
        if tag == "article" and "tile" in a.get("class", "").split() and "data-id" in a:
            self.tiles.append({**a, "_section": self.sections[-1] if self.sections else None, "_pv": [], "_text": []})
            self._tile_depth = 1
        elif self.tiles and self._tile_depth and tag not in ("img", "input", "br", "meta", "link"):
            self._tile_depth += 1
        if tag == "img" and self.tiles and self._tile_depth and "pv" in a.get("class", "").split():
            self.tiles[-1]["_pv"].append(a)
            self.pv_imgs.append(a)
        if tag == "script":
            self._script = a
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append({**self._script, "text": "".join(self._buf)})
            self._script = None
        elif self.tiles and self._tile_depth and tag not in ("img", "input", "br", "meta", "link"):
            self._tile_depth -= 1

    def handle_data(self, data):
        if self._script is not None:
            self._buf.append(data)
        elif self.tiles and self._tile_depth:
            self.tiles[-1]["_text"].append(data)

    def tile(self, rid: str) -> dict:
        return next(t for t in self.tiles if t["data-id"] == rid)

    def ids(self, section: str) -> list[str]:
        return [t["data-id"] for t in self.tiles if t["_section"] == section]

    def data(self) -> dict:
        s = next(s for s in self.scripts if s.get("id") == "attach-data")
        return json.loads(s["text"])


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w8d_review")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    directory, excluded, cat, root = X.build(tmp)
    previews = tmp / "previews"
    previews.mkdir()
    pair = {"part": MAG, "host": ALPHA, "file": "mag--alpha.png", "tier": "twin"}
    (previews / pair["file"]).write_bytes(PNG)
    gone = {"part": MAG, "host": MOUNT_01, "file": "missing.png", "tier": "twin"}  # listed, file absent: no preview
    climb = {"part": MAG, "host": "FAKE_Mount/SM_Wep_Rifle_Double_01", "file": "../escape.png", "tier": "cross_pack_fit"}
    (tmp / "escape.png").write_bytes(PNG)
    (previews / "index.json").write_text(
        json.dumps({"schema": "weapon-attach-preview/1", "pairs": [pair, gone, climb]}), encoding="utf-8")
    out = tmp / "review"
    page_path = write_review_page(directory, out, excluded=excluded, base_dir=tmp, previews_dir=previews)
    text = page_path.read_text(encoding="utf-8")
    yield {"tmp": tmp, "directory": directory, "cat": cat, "root": root, "by_id": {w["id"]: w for w in directory["weapons"]},
           "path": page_path, "text": text, "page": Page(text), "previews": previews, "out": out}
    mp.undo()


# --- structure: section, tiles, panels' data -------------------------------------------------------------------------


def test_the_attachments_section_sits_between_the_archetype_sections_and_parts_and_holds_the_attachments(world):
    page = world["page"]
    secs = page.sections
    assert secs.index("sec-attachments") == secs.index("sec-role-part") - 1
    assert all(s.startswith("sec-archetype-") for s in secs[secs.index("sec-unknown") + 1:secs.index("sec-attachments")])
    ids = page.ids("sec-attachments")
    assert len(ids) == 39 == len({i for i in ids})  # A2: the sight_side_unsure part has no block
    attachments = {i for i, w in world["by_id"].items() if w["role"] == "part" and w.get("attachment")}
    assert set(ids) == attachments
    assert not set(page.ids("sec-role-part")) & attachments  # an attachment appears there and not in Parts
    # A2: a sight_side_unsure part has no block and caps at 0.59, so it is listed under Low confidence, not Parts
    unsure = "FAKE_Attach/SM_Wep_IronSight_01"
    assert unsure in page.ids("sec-low") and unsure not in page.ids("sec-role-part")
    assert set(page.ids("sec-role-part")) == {i for i, w in world["by_id"].items() if w["role"] == "part"} - attachments - {unsure}
    # even a low-confidence attachment is listed under Attachments only
    low = [i for i in ids if world["by_id"][i]["review"]["confidence"] < 0.6]
    assert low and not set(low) & set(page.ids("sec-low"))
    assert [p for p in secs if p == "sec-attachments"] == ["sec-attachments"]


def test_an_attachment_tile_shows_slot_kind_tier_counts_and_reasons(world):
    t = world["page"].tile(MAG)
    assert (t["data-attach"], t["data-slot"], t["data-akind"], t["data-flipfrom"], t["data-flipto"]) == ("1", "magazine", "standard", "+z", "-z")
    text = " ".join("".join(t["_text"]).split())
    assert "magazine" in text and "standard" in text
    assert "twin 2" in text and "cross_pack_fit 1" in text and "no mount 35" in text
    assert "compat_cross_pack" in text and "twin_multi" in text  # the review reasons are on the tile
    plain = world["page"].tile(FOOTLESS)
    assert plain["data-flipto"] == "" and plain["data-flipfrom"] == ""  # no measured anchor: nothing to flip


def test_attachment_tiles_are_grouped_by_slot_in_slot_order(world):
    ids = world["page"].ids("sec-attachments")
    slots = [world["by_id"][i]["attachment"]["slot"] for i in ids]
    order = [s for s in ATTACH_SLOTS if s in slots]
    assert [s for i, s in enumerate(slots) if i == 0 or s != slots[i - 1]] == order
    assert {s: slots.count(s) for s in order} == {"optic": 16, "muzzle": 6, "underbarrel": 5, "magazine": 8, "laser_light": 3, "sight_rear": 1}  # A2: no iron optics; one rear sight


def test_the_embedded_data_lists_every_candidate_host_pending_ones_marked(world):
    data = world["page"].data()
    assert data["schema"] == "weapon-attach-review/1" and data["slots"] == list(ATTACH_SLOTS)
    assert data["tiers"] == ["override", "twin", "same_pack_fit", "cross_pack_fit"]
    assert len(data["attachments"]) == 39 and len(data["hosts"]) == 50
    mag = data["attachments"][MAG]
    assert mag["slot"] == "magazine" and mag["kind"] == "standard" and mag["flip"] == {"from": "+z", "to": "-z"}
    rows = [(h["host"], h["tier"], h["pending"]) for h in mag["hosts"]]
    assert rows[:3] == [(ALPHA, "twin", False), (MOUNT_01, "twin", False), ("FAKE_Mount/SM_Wep_Rifle_Double_01", "cross_pack_fit", False)]
    assert rows[3:5] == [("FAKE_CompA/SM_Wep_Rifle_Beta_01", "same_pack_fit", True), ("FAKE_CompA/SM_Wep_Rifle_Epsilon_01", "same_pack_fit", True)]
    assert len(rows) == 38 and sum(1 for r in rows if r[2]) == 35  # 3 compatible, 35 with no mount (A5 item 0: two `SM_Prop_*` hosts dropped; A6 (W8n): the Nail_Gun, a tool-class host, dropped; Tom's two answers: one more tool-class host, a flame thrower, flare gun or stun gun, dropped)
    assert [h["score"] for h in mag["hosts"][:3]] == [0.95, 0.95, 0.5] and mag["hosts"][3]["score"] is None
    assert data["attachments"][FOOTLESS]["flip"] is None
    assert data["kinds"]["magazine"] == ["standard", "extended", "drum", "cell", "other"]


def test_pending_hosts_are_dimmed_by_the_script_and_the_page_ships_the_class(world):
    text = world["text"]
    assert "'hrow' + (h.pending ? ' dim' : '')" in text and "label.hrow.dim" in text
    assert "'no mount'" in text  # the chip a pending row carries


def test_the_mounts_table_data_has_all_five_slots_and_the_seat_kinds_of_an_eligible_host(world):
    hosts = world["page"].data()["hosts"]
    alpha = hosts[ALPHA]
    assert sorted(alpha["mounts"]) == sorted(ATTACH_SLOTS)
    assert alpha["mounts"]["optic"] == {"child": "SM_Wep_Rifle_Alpha_01_Scope", "confidence": 0.9,
                                       "occupied_by": ["SM_Wep_Rifle_Alpha_01_Scope"], "reason": None, "source": "child_node"}
    assert alpha["mounts"]["muzzle"]["source"] == "probe" and alpha["mounts"]["muzzle"]["occupied_by"] == []
    assert alpha["mounts"]["underbarrel"]["source"] == "none" and alpha["mounts"]["underbarrel"]["reason"] == "no_child_no_probe"
    assert alpha["nodes"] == ["SM_Wep_Rifle_Alpha_01_Mag", "SM_Wep_Rifle_Alpha_01_Scope"]
    assert world["page"].tile(ALPHA)["data-mounts"] == "1"
    assert "data-mounts" not in world["page"].tile("FAKE_Fantasy/SM_Wep_Sword_01")  # no mounts, no table


def test_the_no_mount_chip_count_equals_the_hosts_with_mount_missing(world):
    missing = [i for i, w in world["by_id"].items() if isinstance((w.get("geometry") or {}).get("mounts"), dict)
               and "mount_missing" in w["review"]["reasons"]]
    assert len(missing) == 14  # A4 (W8l): +6 hosts, a family-free underbarrel part now lists them while they have no underbarrel seat
    assert re.search(r'id="f-nomount"[^>]*>No mount \(14\)<', world["text"])
    flagged = [t["data-id"] for t in world["page"].tiles if "data-nomount" in t]
    assert sorted(flagged) == sorted(missing)


def test_previews_are_embedded_when_the_png_exists_and_skipped_when_it_does_not(world):
    page = world["page"]
    tile = page.tile(MAG)
    assert len(tile["_pv"]) == 1  # the pair whose PNG exists; the missing file and the path that climbs out are skipped
    src = tile["_pv"][0]["src"]
    assert src == "../previews/mag--alpha.png" and (world["out"] / src).resolve().is_file()
    assert "escape.png" not in world["text"] and "missing.png" not in world["text"]
    data = page.data()["attachments"][MAG]["hosts"]
    assert [h["preview"] for h in data][:3] == ["../previews/mag--alpha.png", None, None]
    assert all(not t["_pv"] for t in page.tiles if t["data-id"] != MAG)


def test_without_a_previews_folder_there_are_no_images_and_the_page_still_builds(world, tmp_path):
    dest = write_review_page(world["directory"], tmp_path / "bare", base_dir=world["tmp"], previews_dir=tmp_path / "nothing")
    page = Page(dest.read_text(encoding="utf-8"))
    assert not page.pv_imgs and len(page.ids("sec-attachments")) == 39


def test_the_page_makes_no_network_access_and_names_no_external_url(world):
    text = world["text"]
    for needle in ("http:", "https:", "ftp:", "//cdn", "fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "import(",
                   "@import", "<link", "window.open", "location.href", "eval(", "innerHTML"):
        assert needle not in text, needle
    for tag, attr, value in world["page"].urls:
        assert not value or value.startswith(("../", "./", "#", "data:")) or "://" not in value, (tag, attr, value)
        assert not value.startswith(("//", "/")), (tag, attr, value)


# --- in a browser: the corrections the panels write --------------------------------------------------------------------

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


@pytest.fixture()
def browser_page(world):
    _chromium()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = icons._launch_browser(pw, False)
        try:
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(world["path"].as_uri())
            page.evaluate("() => localStorage.clear()")
            page.reload()
            yield page
            assert not errors, errors
        finally:
            browser.close()


def open_tile(page, rid: str):
    page.locator(f'.tile[data-id="{rid}"]').first.evaluate("e => e.click()")


def corr_of(page) -> dict:
    return page.evaluate("() => window.__buildCorrections()")


def host_row(page, host: str):
    return page.locator("#hosts label.hrow", has_text=host).first


def test_in_chromium_flip_slot_kind_hosts_and_mounts_round_trip_into_valid_corrections(world, browser_page):
    page = browser_page
    open_tile(page, MAG)
    assert page.locator("#att").is_visible() and page.locator("#mnt").is_hidden()
    assert page.locator("#b-flip").inner_text() == "Flip forward" and "+z" in page.locator("#p-flip").inner_text()
    rows = page.locator("#hosts label.hrow")
    assert rows.count() == 38 and page.locator("#hosts label.hrow.dim").count() == 35  # A6 (W8n): the tool-class hosts (the Nail_Gun and one of the flame thrower, flare gun or stun gun hosts) are no candidate
    page.locator("#b-flip").click()
    assert page.locator("#b-flip").inner_text() == "Undo flip"
    host_row(page, MOUNT_01).locator("input").uncheck()  # remove an inferred host
    page.fill("#h-add", "FAKE_CompB/SM_Wep_Rifle_Delta_*")
    page.click("#b-hadd")
    page.select_option("#f-akind", "drum")
    got = corr_of(page)
    assert got == {"schema": "weapon-corrections/1", "corrections": [{
        "target": {"id": MAG}, "set": {"attachment_kind": "drum"}, "forward": "-z",
        "compatible": {"add": ["FAKE_CompB/SM_Wep_Rifle_Delta_*"], "remove": [MOUNT_01]}}]}
    assert C.validate_corrections(got) == []
    new, _warn = C.apply_corrections(got, ovr.empty_overrides())
    assert new["ids"][MAG] == {"set": {"attachment_kind": "drum"}, "forward": "-z",
                               "compatible": {"add": ["FAKE_CompB/SM_Wep_Rifle_Delta_*"], "remove": [MOUNT_01]}}
    assert page.locator("#raw").input_value().count("-z") >= 1  # the JSON box shows the same document
    # undo the flip and the removal: only the add and the kind remain
    page.locator("#b-flip").click()
    host_row(page, MOUNT_01).locator("input").check()
    assert "forward" not in corr_of(page)["corrections"][0] and "remove" not in corr_of(page)["corrections"][0]["compatible"]


def test_in_chromium_a_slot_change_resets_the_kind_and_the_mount_picker_writes_categorical_mounts(world, browser_page):
    page = browser_page
    open_tile(page, MAG)
    page.select_option("#f-aslot", "optic")
    assert page.locator("#f-akind").input_value() == ""
    page.select_option("#f-akind", "scope")
    got = corr_of(page)
    assert got["corrections"][0]["set"] == {"attachment_slot": "optic", "attachment_kind": "scope"}
    assert C.validate_corrections(got) == []
    page.locator("#b-clear").click()
    open_tile(page, ALPHA)
    assert page.locator("#mnt").is_visible() and page.locator("#att").is_hidden()
    assert page.locator("#mounts tr").count() == 1 + 7  # header plus one row per slot (A2: seven)
    assert page.locator("#mounts tr.dim").count() == 4  # underbarrel and laser_light have no seat; W8j: nor have sight_front and sight_rear (ALPHA's Scope is a body child, item 8 A)
    cells = [c.strip() for c in page.locator("#mounts tr").nth(1).locator("td").all_inner_texts()]
    assert cells[0] == "optic" and "child_node (SM_Wep_Rifle_Alpha_01_Scope)" in cells[1] and cells[3] == "0.90"
    page.select_option('select[aria-label="mount optic"]', "none")
    page.select_option('select[aria-label="mount underbarrel"]', "SM_Wep_Rifle_Alpha_01_Mag")
    got = corr_of(page)
    assert got["corrections"] == [{"target": {"id": ALPHA}, "mounts": {
        "optic": {"source": "none"}, "underbarrel": {"source": "child_node", "child": "SM_Wep_Rifle_Alpha_01_Mag"}}}]
    assert C.validate_corrections(got) == []
    new, _ = C.apply_corrections(got, ovr.empty_overrides())
    assert new["ids"][ALPHA]["mounts"]["optic"] == {"source": "none"}
    assert not any(isinstance(v, (int, float)) for m in new["ids"][ALPHA]["mounts"].values() for v in m.values())  # never a number


def test_in_chromium_a_family_correction_keeps_forward_and_mounts_on_an_exact_id_entry(world, browser_page):
    page = browser_page
    open_tile(page, MAG)
    page.locator("#b-flip").click()
    page.select_option("#f-akind", "extended")
    page.locator("#c-fam").check()
    got = corr_of(page)["corrections"]
    glob = world["by_id"][MAG]["family"]
    assert len(got) == 2  # one glob entry, one exact-id entry
    glob_entry = next(c for c in got if "glob" in c["target"])
    id_entry = next(c for c in got if "id" in c["target"])
    assert glob_entry["set"] == {"attachment_kind": "extended"} and "forward" not in glob_entry
    assert id_entry == {"target": {"id": MAG}, "forward": "-z"}
    assert glob and "*" in glob_entry["target"]["glob"]
    full = {"schema": "weapon-corrections/1", "corrections": got}
    assert C.validate_corrections(full) == []  # a glob target with forward would be exit 6: the page never writes one
    new, _ = C.apply_corrections(full, ovr.empty_overrides())
    assert new["ids"][MAG] == {"forward": "-z"} and new["globs"][glob_entry["target"]["glob"]]["set"] == {"attachment_kind": "extended"}


def test_in_chromium_a_footless_part_offers_no_flip(world, browser_page):
    page = browser_page
    open_tile(page, FOOTLESS)
    assert page.locator("#b-flip").is_hidden() and "nothing to flip" in page.locator("#p-flip").inner_text()


def test_in_chromium_the_no_mount_chip_filters_to_hosts_missing_a_mount(world, browser_page):
    page = browser_page
    visible = lambda: page.locator(".tile:visible").count()  # noqa: E731
    before = visible()
    page.click("#f-nomount")
    assert page.locator("#f-nomount").get_attribute("aria-pressed") == "true"
    shown = page.locator(".tile:visible").evaluate_all("els => els.map(e => e.getAttribute('data-id'))")
    assert len(shown) == 14 and visible() < before  # A4 (W8l): 9 + 6 hosts that gain mount_missing
    page.click("#f-nomount")
    assert visible() == before


def test_in_chromium_label_mode_writes_weapon_attach_labels_1(world, browser_page):
    page = browser_page
    assert page.locator("#dl-labels").is_hidden()
    page.check("#c-label")
    assert page.locator("#dl-labels").is_visible()
    open_tile(page, MAG)
    page.select_option('select[aria-label="label ' + ALPHA + '"]', "1")
    page.select_option('select[aria-label="label ' + MOUNT_01 + '"]', "0")
    labels = page.evaluate("() => window.__buildLabels()")
    assert labels == {"schema": "weapon-attach-labels/1", "pairs": [
        {"part": MAG, "host": ALPHA, "fits": True}, {"part": MAG, "host": MOUNT_01, "fits": False}]}
    assert page.locator("#lcount").inner_text() == "2"
    assert corr_of(page)["corrections"] == []  # labels are not corrections
    page.select_option('select[aria-label="label ' + MOUNT_01 + '"]', "")
    assert page.evaluate("() => window.__buildLabels()")["pairs"] == [{"part": MAG, "host": ALPHA, "fits": True}]


def test_a_flip_from_the_page_turns_the_anchor_when_the_directory_is_rebuilt(world, tmp_path):
    """The loop closes: the page's flip, applied as an override and rebuilt, gives the opposite forward."""
    corrections = {"schema": "weapon-corrections/1", "corrections": [{"target": {"id": MAG}, "forward": "-z"}]}
    new, _ = C.apply_corrections(corrections, ovr.empty_overrides())
    directory, _excluded, _cat, _root = X.build(tmp_path, overrides=new)
    anchor = {w["id"]: w for w in directory["weapons"]}[MAG]["attachment"]["anchor"]
    before = world["by_id"][MAG]["attachment"]["anchor"]
    assert before["forward"] == [0.0, 0.0, 1.0] and anchor["forward"] == [0.0, 0.0, -1.0]
    assert anchor["point"] == before["point"]  # the foot does not move; only the facing turns
    assert anchor["forward_source"] == "override"


# --- the forward correction key -------------------------------------------------------------------------------------------


def corr(*items) -> dict:
    return {"schema": "weapon-corrections/1", "corrections": list(items)}


def test_forward_must_be_a_signed_axis_and_an_exact_id():
    ok = C.validate_corrections(corr({"target": {"id": MAG}, "forward": "-z"}))
    assert ok == []
    for bad in ("up", "z", "+w", "", None, [0, 0, 1], 1):
        errs = C.validate_corrections(corr({"target": {"id": MAG}, "forward": bad}))
        assert errs and "forward" in errs[0], bad
    errs = C.validate_corrections(corr({"target": {"glob": "FAKE_CompA/SM_Wep_Rifle_Mag_*"}, "forward": "-z"}))
    assert errs == ["corrections[0]: globs[FAKE_CompA/SM_Wep_Rifle_Mag_*].forward: unknown key (forward is for exact ids only)"]


def test_forward_merges_into_the_id_override_and_a_later_one_replaces_it():
    first, _ = C.apply_corrections(corr({"target": {"id": MAG}, "set": {"attachment_kind": "drum"}, "forward": "-z"}),
                                   ovr.empty_overrides())
    assert first["ids"][MAG] == {"set": {"attachment_kind": "drum"}, "forward": "-z"}
    second, _ = C.apply_corrections(corr({"target": {"id": MAG}, "forward": "+x"}), first)
    assert second["ids"][MAG] == {"set": {"attachment_kind": "drum"}, "forward": "+x"}
    assert first["ids"][MAG]["forward"] == "-z"  # the input table is not modified


def test_a_forward_on_a_glob_is_exit_6_through_the_cli(world, tmp_path, monkeypatch, capsys):
    ovr_path = tmp_path / "weapon_overrides.json"
    ovr_path.write_text(json.dumps(ovr.empty_overrides()), encoding="utf-8")
    monkeypatch.setattr(ovr, "default_overrides_path", lambda: ovr_path)
    cfg = X.write_config(world["tmp"], world["cat"])
    before = ovr_path.read_bytes()
    for item in ({"target": {"glob": "FAKE_CompA/SM_Wep_Rifle_Mag_*"}, "forward": "-z"}, {"target": {"id": MAG}, "forward": "sideways"}):
        path = tmp_path / "c.json"
        path.write_text(json.dumps(corr(item)), encoding="utf-8")
        code, res = H.run(cfg, capsys, ["weapons", "apply-corrections", str(path)])
        assert code == 6, res
        assert ovr_path.read_bytes() == before  # nothing written
