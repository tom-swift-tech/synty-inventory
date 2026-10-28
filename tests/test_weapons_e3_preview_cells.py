"""E3 C3: ``index.json`` names each picture's cell on ``sheet.png`` (errata E3.10, carried item 3).

``index.json`` is sorted by (part, host) and merged with earlier runs; ``sheet.png`` holds this run's pictures in job order minus the failed
renders. So the index position says nothing about the sheet position, and each entry carries a ``cell``: the 0-based, row-major cell of
its picture on the sheet the same run wrote. A run that writes a sheet sets ``cell`` on its own entries and clears it on the kept
(older) ones, whose pictures are no longer on the new sheet; a run without a sheet leaves the keys of the last sheet alone.
Synthetic pairs only: a stub renderer paints each part one flat colour, so the sheet pixels say which picture sits where.
"""

from __future__ import annotations

import json

import numpy as np

from synty_inventory.weapons import preview
from synty_inventory.weapons.icons import RenderError
from synty_inventory.weapons.preview import decode_png

SIZE = 8
# part -> the flat colour its stub render is painted in (opaque, so flatten() keeps it as is)
COLOUR = {"part_a": (10, 200, 30), "part_b": (20, 190, 40), "part_c": (30, 180, 50), "part_d": (40, 170, 60), "part_e": (50, 160, 70)}


class ColourStub:
    """One flat, opaque picture per part; ``fail`` parts raise like a renderer that could not draw them."""

    def __init__(self, fail=()):
        self.fail = set(fail)

    def render_pair(self, job, size):
        if job["part"] in self.fail:
            raise RenderError("boom")
        px = np.empty((size, size, 4), dtype=np.uint8)
        px[..., :3], px[..., 3] = COLOUR[job["part"]], 255
        return px


def job(part, host="host_x"):
    return {"part": part, "host": host, "slot": "optic", "tier": "twin", "score": 1.0}


def index_of(out):
    return {p["part"]: p for p in json.loads((out / "index.json").read_text(encoding="utf-8"))["pairs"]}


def cell_colour(out, cell, cols):
    """The sheet's colour at the middle of the given row-major cell of a grid with ``cols`` columns."""
    sheet = decode_png((out / "sheet.png").read_bytes())
    r, c = divmod(cell, cols)
    return tuple(int(v) for v in sheet[r * SIZE + SIZE // 2, c * SIZE + SIZE // 2, :3])


def test_index_cell_matches_the_sheet_position_for_unsorted_jobs(tmp_path):
    out = tmp_path / "pv"
    # job order c, b, a; b fails, so the sheet holds c then a, while the index is sorted a, c
    report = preview.render_pairs(ColourStub(fail={"part_b"}), [job("part_c"), job("part_b"), job("part_a")], out, SIZE, sheet=True)
    assert report["rendered"] == 2 and [f["part"] for f in report["failed"]] == ["part_b"]
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))["pairs"]
    assert [p["part"] for p in index] == ["part_a", "part_c"]  # index order is not the sheet order
    assert [p.get("cell") for p in index] == [1, 0]
    for p in index:  # the cell holds this entry's own picture
        assert cell_colour(out, p["cell"], cols=2) == COLOUR[p["part"]], p["part"]
    assert [p.get("cell") for p in report["pairs"]] == [1, 0]  # the report carries the same entries


def test_cell_follows_row_major_order_in_a_wider_grid(tmp_path):
    out = tmp_path / "pv"
    order = ["part_e", "part_c", "part_a", "part_d", "part_b"]  # 5 pictures: 3 columns, 2 rows
    preview.render_pairs(ColourStub(), [job(p) for p in order], out, SIZE, sheet=True)
    index = index_of(out)
    assert {p: index[p]["cell"] for p in order} == {"part_e": 0, "part_c": 1, "part_a": 2, "part_d": 3, "part_b": 4}
    for part, entry in index.items():
        assert cell_colour(out, entry["cell"], cols=3) == COLOUR[part], part


def test_a_run_without_a_sheet_keeps_the_older_cell_keys(tmp_path):
    out = tmp_path / "pv"
    preview.render_pairs(ColourStub(), [job("part_b"), job("part_a")], out, SIZE, sheet=True)
    assert {p: e["cell"] for p, e in index_of(out).items()} == {"part_b": 0, "part_a": 1}
    sheet_before = (out / "sheet.png").read_bytes()
    preview.render_pairs(ColourStub(), [job("part_c")], out, SIZE)  # no sheet: the sheet on disk is still the first run's
    index = index_of(out)
    assert index["part_a"]["cell"] == 1 and index["part_b"]["cell"] == 0
    assert "cell" not in index["part_c"]  # its picture is not on any sheet
    assert (out / "sheet.png").read_bytes() == sheet_before
    for part in ("part_a", "part_b"):  # the kept cells still point at their pictures
        assert cell_colour(out, index[part]["cell"], cols=2) == COLOUR[part]


def test_a_new_sheet_clears_the_cell_of_every_kept_entry(tmp_path):
    out = tmp_path / "pv"
    preview.render_pairs(ColourStub(), [job("part_b"), job("part_a")], out, SIZE, sheet=True)
    preview.render_pairs(ColourStub(), [job("part_d"), job("part_c")], out, SIZE, sheet=True)
    index = index_of(out)
    assert sorted(index) == ["part_a", "part_b", "part_c", "part_d"]  # the older pairs are still listed
    assert "cell" not in index["part_a"] and "cell" not in index["part_b"]  # but they are not on this sheet
    assert (index["part_d"]["cell"], index["part_c"]["cell"]) == (0, 1)


def test_a_sheet_run_where_every_render_fails_leaves_the_old_sheet_and_cells(tmp_path):
    out = tmp_path / "pv"
    preview.render_pairs(ColourStub(), [job("part_b"), job("part_a")], out, SIZE, sheet=True)
    preview.render_pairs(ColourStub(fail={"part_c"}), [job("part_c")], out, SIZE, sheet=True)  # no picture, so no new sheet is written
    index = index_of(out)
    assert (index["part_b"]["cell"], index["part_a"]["cell"]) == (0, 1)
    assert cell_colour(out, index["part_a"]["cell"], cols=2) == COLOUR["part_a"]


def seed_older_run(out, parts=("part_x", "part_y")):
    """An index (and its pictures) as an earlier sheet-writing run left it, hand-written so the guards below do not lean on the code under test."""
    out.mkdir(parents=True)
    pairs = []
    for cell, part in enumerate(parts):
        name = preview.pair_file(part, "host_x")
        (out / name).write_bytes(b"stub")  # the index only needs the file to exist
        pairs.append({"part": part, "host": "host_x", "slot": "optic", "tier": "twin", "score": 1.0, "file": name, "cell": cell})
    (out / "index.json").write_text(json.dumps({"schema": "weapon-attach-preview/1", "pairs": pairs}, indent=1, sort_keys=True), encoding="utf-8")


def test_guard_seeded_cell_keys_survive_a_run_without_a_sheet(tmp_path):
    out = tmp_path / "pv"
    seed_older_run(out)
    preview.render_pairs(ColourStub(), [job("part_c")], out, SIZE)
    index = index_of(out)
    assert (index["part_x"]["cell"], index["part_y"]["cell"]) == (0, 1) and "cell" not in index["part_c"]


def test_guard_seeded_cell_keys_are_cleared_when_a_new_sheet_is_written(tmp_path):
    out = tmp_path / "pv"
    seed_older_run(out)
    preview.render_pairs(ColourStub(), [job("part_c")], out, SIZE, sheet=True)
    index = index_of(out)
    assert sorted(index) == ["part_c", "part_x", "part_y"]
    assert "cell" not in index["part_x"] and "cell" not in index["part_y"] and index["part_c"]["cell"] == 0
