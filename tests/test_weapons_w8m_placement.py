"""W8m: placement and export of ``seat_shift_m`` (docs/weapon_attachments.md 5.4 and 7; AC114).

World: ``w8m_world`` (pack FAKE_W8M). Expected positions are the hand-worked numbers of that module: a part's foot centre is its anchor point,
so the matrix sends (0, 0, 0) to where the part's contact face is centred.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8m_world", FIX / "w8m_world.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
W = M.W
_hspec = importlib.util.spec_from_file_location("review_helpers", FIX / "review_helpers.py")
H = importlib.util.module_from_spec(_hspec)
_hspec.loader.exec_module(H)

from synty_inventory.weapons import export as export_mod, preview  # noqa: E402
from synty_inventory.weapons.attach import place  # noqa: E402
from synty_inventory.weapons.directory import write_directory  # noqa: E402


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w8m_placement")
    mp = pytest.MonkeyPatch()
    for key in H.ENV_KEYS:
        mp.delenv(key, raising=False)
    mp.setattr(export_mod, "_repo_root", lambda: None)  # the pytest tmp dir sits inside this checkout
    directory, excluded, cat, root = W.build(tmp, M.world())
    write_directory(cat, directory, excluded)
    out = tmp / "game_repo"
    out.mkdir()
    yield {"tmp": tmp, "cfg": H.write_config(tmp, cat, []), "directory": directory, "out": out, "root": root,
           "by_id": W.by_id(directory)}
    mp.undo()


def job(world, part: str, case: str) -> dict:
    p, h = world["by_id"][M.pid(part)], world["by_id"][M.hid(case)]
    entry = next(e for e in p["attachment"]["compatible_hosts"] if e["host"] == h["id"])
    pair = {"part": p["id"], "host": h["id"], "slot": p["attachment"]["slot"], "tier": entry["tier"], "score": entry["score"],
            "twin": entry["tier"] == "twin"}
    return preview.build_job(pair, p, h, world["root"])


def translate(v) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = v
    return m


def foot(matrix) -> list:
    """Where the part's foot centre (its anchor point, the contact face's middle) lands."""
    return [round(float(c), 6) for c in (np.asarray(matrix) @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]]


# --- AC114: build_job ----------------------------------------------------------------------------------------------------------


def test_a_keyed_optic_pair_is_placed_translate_shift_up_after_place(world):
    p, h = world["by_id"][M.pid(M.SCOPE_PART)], world["by_id"][M.hid("Hover")]
    mount = h["geometry"]["mounts"]["optic"]
    entry = next(e for e in p["attachment"]["compatible_hosts"] if e["host"] == h["id"])
    assert entry["seat_shift_m"] == -0.011
    want = translate(-0.011 * np.asarray(mount["up"])) @ place(p["attachment"]["anchor"], mount)
    got = np.asarray(job(world, M.SCOPE_PART, "Hover")["matrix"])
    assert np.allclose(got, want, atol=1e-9)
    assert foot(got) == [0.0, 0.1, 0.0]  # the seat is 0.111; the contact face now rests on the body top at 0.100


def test_a_sunk_optic_goes_up_and_an_underbarrel_part_moves_along_minus_y(world):
    assert foot(job(world, M.SCOPE_PART, "Sunk")["matrix"]) == [0.0, 0.1, 0.0]  # seat 0.092, +0.008
    # the grip hangs below its seat: its top face is the contact face; the mount's up is -y, so +0.0377 lowers it from 0.0377 to 0.0
    assert foot(job(world, M.GRIP_PART, "UbSunk")["matrix"]) == [0.0, 0.0, 0.0]
    assert foot(job(world, M.GRIP_PART, "UbGap")["matrix"]) == [0.0, 0.0, 0.0]  # seat -0.012, shift -0.012 along -y: +0.012
    p, h = world["by_id"][M.pid(M.GRIP_PART)], world["by_id"][M.hid("UbGap")]
    mount = h["geometry"]["mounts"]["underbarrel"]
    want = translate(-0.012 * np.asarray(mount["up"])) @ place(p["attachment"]["anchor"], mount)
    assert np.allclose(np.asarray(job(world, M.GRIP_PART, "UbGap")["matrix"]), want, atol=1e-9)


def test_a_pair_with_no_key_is_placed_exactly_as_place_does(world):
    p, h = world["by_id"][M.pid(M.SCOPE_PART)], world["by_id"][M.hid("Near")]
    assert all("seat_shift_m" not in e for e in p["attachment"]["compatible_hosts"] if e["host"] == h["id"])
    mount = h["geometry"]["mounts"]["optic"]
    got = job(world, M.SCOPE_PART, "Near")["matrix"]
    assert np.array_equal(np.asarray(got), np.asarray(place(p["attachment"]["anchor"], mount)))  # byte-identical, not just close
    assert foot(got) == [0.0, 0.1029, 0.0]


def test_a_part_never_keyed_keeps_the_matrix_of_place(world):
    p, h = world["by_id"][M.pid(M.MAG_PART)], world["by_id"][M.hid("Misc")]
    mount = h["geometry"]["mounts"]["magazine"]
    got = job(world, M.MAG_PART, "Misc")["matrix"]
    assert np.array_equal(np.asarray(got), np.asarray(place(p["attachment"]["anchor"], mount)))


# --- AC114: export ---------------------------------------------------------------------------------------------------------------


def export(world, capsys, *flags, name="snap.json"):
    out = world["out"] / name
    code, _ = H.run(world["cfg"], capsys, ["weapons", "export", "--game", "ref", "--packs", M.PACK, "--roles", "all", *flags, "--out", str(out)])
    assert code == 0
    return json.loads(out.read_text(encoding="utf-8")), out


def entries(doc: dict, part: str) -> dict:
    rec = next(w for w in doc["weapons"] if w["id"] == M.pid(part))
    return {e["host"]: e for e in rec["attachment"]["compatible_hosts"]}


def test_export_carries_the_key_unchanged_in_both_frames(world, capsys):
    for frame in ("asset", "item"):
        doc, _ = export(world, capsys, "--attachments", "--frame", frame, name=f"{frame}.json")
        got = entries(doc, M.SCOPE_PART)
        assert got[M.hid("Hover")]["seat_shift_m"] == -0.011, frame  # a scalar along the mount's up: the frame does not touch it
        assert got[M.hid("Sunk")]["seat_shift_m"] == 0.008, frame
        assert got[M.hid("Far90")]["seat_shift_m"] == -0.06, frame
        assert "seat_shift_m" not in got[M.hid("Near")], frame
        grip = entries(doc, M.GRIP_PART)
        assert grip[M.hid("UbGap")]["seat_shift_m"] == -0.012 and grip[M.hid("UbSunk")]["seat_shift_m"] == 0.0377, frame


def test_the_default_export_has_no_key_and_no_attachment_block(world, capsys):
    doc, out = export(world, capsys, name="default.json")
    assert "seat_shift_m" not in out.read_text(encoding="utf-8") and all("attachment" not in w for w in doc["weapons"])


def validate(world, capsys, snapshot: Path):
    return H.run(world["cfg"], capsys, ["weapons", "validate", "--snapshot", str(snapshot)])


def broken(world, capsys, name, edit):
    doc, _ = export(world, capsys, "--attachments", name=f"good_{name}.json")
    edit({w["id"]: w for w in doc["weapons"]})
    path = world["out"] / f"bad_{name}.json"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:  # the validator wants LF
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return validate(world, capsys, path)


def set_key(part: str, host_case: str, value):
    def edit(recs):
        for e in recs[M.pid(part)]["attachment"]["compatible_hosts"]:
            if e["host"] == M.hid(host_case):
                e["seat_shift_m"] = value
    return edit


def test_a_good_snapshot_with_keys_validates(world, capsys):
    doc, out = export(world, capsys, "--attachments", name="good.json")
    code, res = validate(world, capsys, out)
    assert code == 0 and res["errors"] == [] and entries(doc, M.SCOPE_PART)[M.hid("Hover")]["seat_shift_m"] == -0.011


@pytest.mark.parametrize("value", [0.0601, -0.0601, 0.5, "0.01", None, True])
def test_exit_6_on_a_key_above_60_mm_or_not_a_number(world, capsys, value):
    code, res = broken(world, capsys, "bound", set_key(M.SCOPE_PART, "Hover", value))
    assert code == 6 and any("seat_shift_m" in e for e in res["errors"]), res["errors"]


def test_the_60_mm_bound_itself_is_valid(world, capsys):
    for v in (0.06, -0.06):
        code, res = broken(world, capsys, "edge", set_key(M.SCOPE_PART, "Hover", v))
        assert code == 0, res["errors"]


def test_exit_6_on_a_key_on_a_slot_other_than_optic_or_underbarrel(world, capsys):
    code, res = broken(world, capsys, "mag", lambda recs: recs[M.pid(M.MAG_PART)]["attachment"]["compatible_hosts"][0].update(seat_shift_m=0.01))
    assert code == 6 and any("seat_shift_m" in e for e in res["errors"]), res["errors"]
    code, res = broken(world, capsys, "sil", lambda recs: recs[M.pid(M.SILENCER_PART)]["attachment"]["compatible_hosts"][0].update(seat_shift_m=-0.01))
    assert code == 6 and any("seat_shift_m" in e for e in res["errors"]), res["errors"]
