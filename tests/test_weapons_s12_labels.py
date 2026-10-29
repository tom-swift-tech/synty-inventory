"""S12 wiring: the hand-labels file, the draw's refusals and the labels normalizer (docs/weapon_attach_geometry.md 3.10, 4.4; AC141, INV-26).

Synthetic ids only. The draw tests use a literal directory: one slot (optic), three parts each listing the same 20 hosts at ``same_pack_fit``, so the optic
slot has 60 listed pairs and the draw takes the 8 lowest sha256("spotcheck-1|" + part + "|" + host). ``key`` below is this file's own copy of that hash.

Hand count for test B (``labelled_skipped``): 3 boolean pairs = 3 (part, host); one ``part2`` pair = 2; one ``excluded`` entry = 1; one ``excluded``
entry with ``part2`` = 2; total 8, all distinct (the test asserts it).

The normalizer cases are worked by hand in ``RECORDS`` (arrival index = position after sorting by (at, card)):

  idx  key                   fits   slot
  0    P1 / H1               yes    optic          idx 0 and 1 are identical: one pair, one duplicate collapsed
  1    P1 / H1               yes
  2    P2 / H1               yes    muzzle         idx 2 yes, idx 4 no: a conflict, excluded
  3    P3 / H2               no     optic          idx 3 no, idx 5 skip: a conflict (a skip is an answer), excluded
  4    P2 / H1               no
  5    P3 / H2               skip
  6    P4 / H3               skip   magazine       skip only: excluded (reason skip)
  7    P5 + P6 / H4          yes    magazine       a two-part record: ONE pair
  8    P7 / H5               no     optic

  records 9, distinct keys 6, duplicates collapsed 1; pairs 3 (yes 2, no 1, two-part 1; optic 2, magazine 1);
  excluded 3 (skip 1, conflict 2; muzzle 1, optic 1, magazine 1); conflicts [2, 4] yes/no and [3, 5] no/skip.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("review_helpers")

from synty_inventory.weapons import guards, spotcheck as SP  # noqa: E402
from synty_inventory.weapons.directory import DIRECTORY_NAME, weapons_dir  # noqa: E402
from synty_inventory.weapons.eval import evaluate, load_labels, validate_labels  # noqa: E402

SCHEMA = "weapon-attach-labels/1"
PARTS = ("Q/Part_a", "Q/Part_b", "Q/Part_c")
HOSTS = [f"Q/Host_{i:02d}" for i in range(20)]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    for key_ in H.ENV_KEYS:
        monkeypatch.delenv(key_, raising=False)


def key(part, host):
    return hashlib.sha256(f"spotcheck-1|{part}|{host}".encode("utf-8")).hexdigest()


def directory(**header):
    weapons = [{"id": p, "role": "part", "attachment": {"slot": "optic", "pending_hosts": [],
                                                       "compatible_hosts": [{"host": h, "tier": "same_pack_fit", "score": 0.5} for h in HOSTS]}}
               for p in PARTS]
    doc = {"schema": "weapon-directory/1", "attach_rules_digest": "0123456789abcdef", "attach_version": 14, "fit_digest": "fedcba9876543210", "weapons": weapons}
    for name, value in header.items():
        if value is None:
            doc.pop(name, None)
        else:
            doc[name] = value
    return doc


def ranked():
    """All 60 listed pairs, lowest hash first."""
    return sorted((key(p, h), p, h) for p in PARTS for h in HOSTS)


def other_part(part, skip=()):
    return next(p for p in PARTS if p != part and p not in skip)


def setup(tmp_path, labels_doc=None, **header):
    dpath = tmp_path / "directory.json"
    dpath.write_text(json.dumps(directory(**header)), encoding="utf-8")
    labels = tmp_path / "labels.json"
    if labels_doc is not None:
        labels.write_text(json.dumps(labels_doc), encoding="utf-8")
    return {"dir": dpath, "labels": labels, "out": tmp_path / "spotcheck.json", "cfg": H.write_config(tmp_path, tmp_path)}


def draw(files, capsys, *extra, with_labels=True):
    argv = ["weapons", "attach-spotcheck", "--draw", "--directory", str(files["dir"]), "--file", str(files["out"]), *extra]
    if with_labels:
        argv += ["--labels", str(files["labels"])]
    return H.run(files["cfg"], capsys, argv)


def a_valid_labels(tmp_path):
    return {"schema": SCHEMA, "pairs": [{"part": "Q/Part_a", "host": HOSTS[19], "fits": True}]}


# -- the draw's refusals ------------------------------------------------------------------------------------------


def test_a_bare_draw_with_no_committed_labels_file_exits_2_naming_the_path_and_writes_nothing(tmp_path, capsys, monkeypatch):
    files = setup(tmp_path)
    absent = tmp_path / "nowhere" / "weapon_attach_labels.json"
    monkeypatch.setattr(SP, "default_labels_path", lambda: absent)
    code, out = draw(files, capsys, with_labels=False)
    assert code == 2 and out["ok"] is False and str(absent) in out["error"]
    assert not files["out"].exists()


def test_labels_with_selected_pairs_part2_and_excluded_are_all_skipped_and_counted(tmp_path, capsys):
    c = ranked()
    (_, p0, h0), (_, p1, h1), (_, p2, h2), (_, p3, h3), (_, p4, h4), (_, p5, h5) = c[:6]
    q3, q5 = other_part(p3), other_part(p5)
    doc = {"schema": SCHEMA,
           "pairs": [{"part": p0, "host": h0, "fits": True}, {"part": p1, "host": h1, "fits": False}, {"part": p2, "host": h2, "fits": True},
                     {"part": p3, "part2": q3, "host": h3, "fits": True}],
           "excluded": [{"part": p4, "host": h4}, {"part": p5, "part2": q5, "host": h5}]}
    skipped = {(p0, h0), (p1, h1), (p2, h2), (p3, h3), (q3, h3), (p4, h4), (p5, h5), (q5, h5)}
    assert len(skipped) == 8  # the hand count: 3 + 2 + 1 + 2, no overlap among them
    files = setup(tmp_path, doc)
    code, out = draw(files, capsys)
    assert code == 0 and out["labelled_skipped"] == 8
    drawn = {(p["part"], p["host"]) for p in json.loads(files["out"].read_text(encoding="utf-8"))["pairs"]}
    assert len(drawn) == 8 and not drawn & skipped
    assert drawn == {(p, h) for _k, p, h in [x for x in c if (x[1], x[2]) not in skipped][:8]}
    # control: the same draw with one far-away label picks the 6 lowest-hash pairs first, so the exclusion is what moved them
    other = tmp_path / "control"
    other.mkdir()
    control = setup(other, {"schema": SCHEMA, "pairs": [{"part": c[-1][1], "host": c[-1][2], "fits": True}]})
    code, out = draw(control, capsys)
    assert code == 0 and out["labelled_skipped"] == 1
    drawn = {(p["part"], p["host"]) for p in json.loads(control["out"].read_text(encoding="utf-8"))["pairs"]}
    assert {(p0, h0), (p1, h1), (p2, h2), (p3, h3), (p4, h4), (p5, h5)} <= drawn


def test_a_labels_file_with_no_pair_exits_2_and_writes_nothing(tmp_path, capsys):
    files = setup(tmp_path, {"schema": SCHEMA, "pairs": []})
    code, out = draw(files, capsys)
    assert code == 2 and out["ok"] is False and not files["out"].exists()


def test_a_labels_file_with_only_excluded_entries_and_no_pair_exits_2(tmp_path, capsys):
    files = setup(tmp_path, {"schema": SCHEMA, "pairs": [], "excluded": [{"part": "Q/Part_a", "host": HOSTS[0]}]})
    code, _out = draw(files, capsys)
    assert code == 2 and not files["out"].exists()


def test_a_labels_file_that_breaks_the_schema_keeps_exit_6(tmp_path, capsys):
    files = setup(tmp_path, {"schema": SCHEMA, "pairs": [{"part": "Q/Part_a", "host": HOSTS[0], "fits": True, "extra": 1}]})
    code, _out = draw(files, capsys)
    assert code == 6 and not files["out"].exists()


@pytest.mark.parametrize(("header", "needle"), [
    ({"attach_version": 13}, "attach_version"),
    ({"fit_digest": None}, "fit_digest"),  # the key is absent
    ({"fit_digest": ""}, "fit_digest"),
])
def test_r7_a_stale_or_pre_attach_directory_exits_2_naming_the_header_key(tmp_path, capsys, header, needle):
    files = setup(tmp_path, a_valid_labels(tmp_path), **header)
    code, out = draw(files, capsys)
    assert code == 2 and out["ok"] is False and needle in out["error"]
    assert not files["out"].exists()
    if "attach_version" in header:
        assert "13" in out["error"]  # the value found


def test_r7_the_header_check_comes_before_the_labels_check(tmp_path, capsys):
    files = setup(tmp_path, None, attach_version=13)  # no labels file either
    code, out = draw(files, capsys)
    assert code == 2 and "attach_version" in out["error"]


def test_r7_a_current_directory_draws(tmp_path, capsys):
    files = setup(tmp_path, a_valid_labels(tmp_path), attach_version=14, fit_digest="0123456789abcdef")
    code, out = draw(files, capsys)
    assert code == 0 and out["drawn"] == 8 and files["out"].exists()


def test_an_existing_spot_check_file_still_wins_with_exit_6(tmp_path, capsys):
    files = setup(tmp_path, None, attach_version=13)  # every other refusal is also present
    files["out"].write_text("{}", encoding="utf-8")
    code, _out = draw(files, capsys)
    assert code == 6 and files["out"].read_text(encoding="utf-8") == "{}"


# -- the validator --------------------------------------------------------------------------------------------------


def base_doc():
    return {"schema": SCHEMA,
            "pairs": [{"part": "Q/P1", "host": "Q/H1", "fits": True}, {"part": "Q/P2", "part2": "Q/P3", "host": "Q/H1", "fits": False}],
            "excluded": [{"part": "Q/P4", "host": "Q/H2"}, {"part": "Q/P5", "part2": "Q/P6", "host": "Q/H2"}]}


def test_validator_accepts_part2_and_excluded_and_an_old_file():
    assert validate_labels(base_doc()) == []
    assert validate_labels({"schema": SCHEMA, "pairs": [{"part": "Q/P1", "host": "Q/H1", "fits": True}]}) == []


@pytest.mark.parametrize("mutate", [
    lambda d: d["pairs"][1].update(part2="Q/P2"),  # part2 == part
    lambda d: d["pairs"][0].update(unknown=1),  # an unknown pair key
    lambda d: d["pairs"][1].update(part2="nopack"),  # an ill-formed id
    lambda d: d["excluded"][0].update(fits=True),  # fits in an excluded entry
    lambda d: d["excluded"][1].update(extra=1),
    lambda d: d["excluded"].append({"part": "Q/P1", "host": "Q/H1"}),  # a key in both pairs and excluded
    lambda d: d["excluded"].append({"part": "Q/P2", "part2": "Q/P3", "host": "Q/H1"}),  # a two-part key in both
    lambda d: d["pairs"].append(dict(d["pairs"][1])),  # (part, part2, host) twice in pairs
    lambda d: d["excluded"].append(dict(d["excluded"][0])),  # twice in excluded
    lambda d: d.update(extra=[]),  # an unknown top-level key
    lambda d: d.update(excluded="x"),
    lambda d: d["excluded"].append("x"),
])
def test_validator_refuses(mutate):
    doc = base_doc()
    mutate(doc)
    assert validate_labels(doc)


def test_the_same_part_and_host_with_and_without_part2_are_two_different_keys():
    doc = base_doc()
    doc["pairs"].append({"part": "Q/P2", "host": "Q/H1", "fits": True})  # P2 / H1 beside P2 + P3 / H1
    assert validate_labels(doc) == []


# -- attach-eval ----------------------------------------------------------------------------------------------------

EVAL_HOSTS = ("Q/H1", "Q/H2", "Q/H3", "Q/H4")


def eval_directory():
    def part(pid, slot, listed):
        return {"id": pid, "role": "part", "kind": "attachment", "hold_class": None,
                "attachment": {"slot": slot, "pending_hosts": [], "compatible_hosts": [{"host": h, "tier": "same_pack_fit"} for h in listed]}}

    weapons = [{"id": h, "role": "whole", "kind": "ranged", "hold_class": "long_gun", "attachment": None} for h in EVAL_HOSTS]
    weapons += [part("Q/Front", "sight_front", EVAL_HOSTS), part("Q/Rear", "sight_rear", ("Q/H1", "Q/H3")),
                {"id": "Q/Plain", "role": "part", "kind": "other", "hold_class": None, "attachment": None}]
    return {"weapons": weapons}


def test_eval_a_part2_pair_is_predicted_only_when_both_parts_are():
    pairs = [
        {"part": "Q/Front", "part2": "Q/Rear", "host": "Q/H1", "fits": True},   # both listed: TP
        {"part": "Q/Front", "part2": "Q/Rear", "host": "Q/H2", "fits": True},   # only Front listed: FN
        {"part": "Q/Front", "part2": "Q/Rear", "host": "Q/H3", "fits": False},  # both listed: FP
        {"part": "Q/Front", "part2": "Q/Rear", "host": "Q/H4", "fits": False},  # only Front listed: TN
        {"part": "Q/Front", "host": "Q/H2", "fits": True},                      # a single-part pair judges as before: TP
    ]
    result = evaluate(eval_directory(), pairs)
    got = result["default"]
    assert (got["tp"], got["fn"], got["fp"], got["tn"]) == (2, 1, 1, 1)
    assert result["pairs"] == 5 and result["skipped"] == []
    assert result["label_era"]["pairs"] == 5  # the slot of a two-part pair is the part's (a label-era slot here)
    assert (result["with_cross_pack"]["tp"], result["same_pack_only"]["tp"]) == (2, 2)


def test_eval_a_part2_pair_is_skipped_unless_both_parts_are_attachment_records():
    pairs = [{"part": "Q/Front", "part2": "Q/Plain", "host": "Q/H1", "fits": True},
             {"part": "Q/Front", "part2": "Q/Nowhere", "host": "Q/H1", "fits": True},
             {"part": "Q/Front", "part2": "Q/Rear", "host": "Q/H1", "fits": True}]
    result = evaluate(eval_directory(), pairs)
    assert result["pairs"] == 1
    assert [s["reason"] for s in result["skipped"]] == ["part_not_an_attachment", "part_not_an_attachment"]


def test_eval_ignores_the_excluded_entries(tmp_path, capsys):
    cat = tmp_path / "cat"
    wdir = weapons_dir(cat)
    wdir.mkdir(parents=True)
    (wdir / DIRECTORY_NAME).write_text(json.dumps(eval_directory()), encoding="utf-8")
    pairs = [{"part": "Q/Front", "part2": "Q/Rear", "host": "Q/H1", "fits": True}, {"part": "Q/Front", "host": "Q/H2", "fits": True}]
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps({"schema": SCHEMA, "pairs": pairs}), encoding="utf-8")
    with_excluded = tmp_path / "with_excluded.json"
    with_excluded.write_text(json.dumps({"schema": SCHEMA, "pairs": pairs, "excluded": [{"part": "Q/Front", "host": "Q/H3"}, {"part": "Q/Front", "part2": "Q/Rear", "host": "Q/H4"}]}),
                             encoding="utf-8")
    assert load_labels(with_excluded) == pairs
    cfg = H.write_config(tmp_path, cat)
    code1, out1 = H.run(cfg, capsys, ["weapons", "attach-eval", "--labels", str(plain)])
    code2, out2 = H.run(cfg, capsys, ["weapons", "attach-eval", "--labels", str(with_excluded)])
    assert code1 == code2 == 0 and out1["pairs"] == out2["pairs"] == 2
    out1.pop("labels"), out2.pop("labels")
    assert out1 == out2


# -- the normalizer -------------------------------------------------------------------------------------------------


def rec(at, card, part, host, fits, slot, part2=None, **more):
    r = {"at": at, "card": card, "fits": fits, "host_id": host, "part_id": part, "slot": slot, **more}
    if part2 is not None:
        r["part2_id"] = part2
    return r


RECORDS = [
    rec("2026-10-20T10:00:01Z", "c1", "Q/P1", "Q/H1", "yes", "optic"),
    rec("2026-10-20T10:00:02Z", "c2", "Q/P1", "Q/H1", "yes", "optic", **{"def": "d"}),
    rec("2026-10-20T10:00:03Z", "c3", "Q/P2", "Q/H1", "yes", "muzzle"),
    rec("2026-10-20T10:00:04Z", "c4", "Q/P3", "Q/H2", "no", "optic"),
    rec("2026-10-20T10:00:05Z", "c5", "Q/P2", "Q/H1", "no", "muzzle"),
    rec("2026-10-20T10:00:06Z", "c6", "Q/P3", "Q/H2", "skip", "optic"),
    rec("2026-10-20T10:00:07Z", "c7", "Q/P4", "Q/H3", "skip", "magazine"),
    rec("2026-10-20T10:00:08Z", "c8", "Q/P5", "Q/H4", "yes", "magazine", part2="Q/P6"),
    rec("2026-10-20T10:00:09Z", "c9", "Q/P7", "Q/H5", "no", "optic", other_key=1),
]


def test_normalizer_hand_worked_export():
    from synty_inventory.weapons.labels_store import normalize

    doc, report = normalize(list(reversed(RECORDS)))  # the input order is not the arrival order
    assert doc == {"schema": SCHEMA,
                   "pairs": [{"part": "Q/P1", "host": "Q/H1", "fits": True},
                             {"part": "Q/P5", "part2": "Q/P6", "host": "Q/H4", "fits": True},
                             {"part": "Q/P7", "host": "Q/H5", "fits": False}],
                   "excluded": [{"part": "Q/P2", "host": "Q/H1"}, {"part": "Q/P3", "host": "Q/H2"}, {"part": "Q/P4", "host": "Q/H3"}]}
    assert report == {
        "records": 9, "distinct_keys": 6, "identical_duplicates_collapsed": 1,
        "pairs": {"total": 3, "yes": 2, "no": 1, "two_part": 1, "per_slot": {"magazine": 1, "optic": 2}},
        "excluded": {"total": 3, "by_reason": {"skip": 1, "conflict": 2}, "per_slot": {"magazine": 1, "muzzle": 1, "optic": 1}},
        "conflicts": [{"indices": [2, 4], "values": ["yes", "no"]}, {"indices": [3, 5], "values": ["no", "skip"]}],
    }
    assert validate_labels(doc) == []
    assert "slot" not in json.dumps(doc) and "other_key" not in json.dumps(doc) and "def" not in json.dumps(doc)  # unknown keys dropped, slot never written


def test_normalizer_report_holds_no_id():
    from synty_inventory.weapons.labels_store import normalize

    _doc, report = normalize(RECORDS)
    text = json.dumps(report)
    assert "Q/" not in text and "H1" not in text


def test_normalizer_a_yes_no_group_and_a_no_skip_group_are_conflicts_with_values_in_arrival_order():
    from synty_inventory.weapons.labels_store import normalize

    records = [rec("2026-01-01T00:00:02Z", "b", "Q/A", "Q/B", "no", "optic"), rec("2026-01-01T00:00:01Z", "a", "Q/A", "Q/B", "yes", "optic"),
               rec("2026-01-01T00:00:03Z", "c", "Q/A", "Q/C", "skip", "optic"), rec("2026-01-01T00:00:03Z", "d", "Q/A", "Q/C", "no", "optic")]
    doc, report = normalize(records)
    assert doc["pairs"] == [] and doc["excluded"] == [{"part": "Q/A", "host": "Q/B"}, {"part": "Q/A", "host": "Q/C"}]
    assert report["conflicts"] == [{"indices": [0, 1], "values": ["yes", "no"]}, {"indices": [2, 3], "values": ["skip", "no"]}]


def test_normalizer_a_null_part2_id_reads_as_absent():
    from synty_inventory.weapons.labels_store import normalize

    one = rec("2026-01-01T00:00:01Z", "a", "Q/A", "Q/B", "yes", "optic", part2_id=None)
    two = rec("2026-01-01T00:00:02Z", "b", "Q/A", "Q/B", "yes", "optic")
    doc, report = normalize([one, two])
    assert doc["pairs"] == [{"part": "Q/A", "host": "Q/B", "fits": True}] and report["identical_duplicates_collapsed"] == 1


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(fits="maybe"),
    lambda r: r.update(fits=True),
    lambda r: r.pop("fits"),
    lambda r: r.pop("host_id"),
    lambda r: r.pop("part_id"),
    lambda r: r.pop("at"),
    lambda r: r.pop("card"),
    lambda r: r.update(card=7),
    lambda r: r.update(part_id="nopack"),
    lambda r: r.update(host_id=""),
    lambda r: r.update(part2_id=5),  # a non-string part2_id
    lambda r: r.update(part2_id="bad"),
    lambda r: r.update(part2_id=r["part_id"]),
])
def test_normalizer_refuses_a_bad_record(mutate):
    from synty_inventory.weapons import InputError
    from synty_inventory.weapons.labels_store import normalize

    records = copy.deepcopy(RECORDS)
    mutate(records[3])
    with pytest.raises(InputError):
        normalize(records)


def write_export(folder: Path, records, names=None):
    folder.mkdir(exist_ok=True)
    for i, r in enumerate(records):
        (folder / (names[i] if names else f"card_{i:02d}.json")).write_text(json.dumps(r), encoding="utf-8")


def test_normalizer_cli_writes_a_valid_lf_file_and_two_runs_give_identical_bytes(tmp_path, capsys):
    from synty_inventory.weapons.labels_store import main

    export = tmp_path / "export"
    write_export(export, RECORDS)
    out1, out2 = tmp_path / "one.json", tmp_path / "two.json"
    assert main(["--export", str(export), "--out", str(out1)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True and report["records"] == 9 and report["pairs"]["total"] == 3
    assert main(["--export", str(export), "--out", str(out2)]) == 0
    capsys.readouterr()
    data = out1.read_bytes()
    assert data == out2.read_bytes() and b"\r" not in data and data.endswith(b"}\n") and not data.endswith(b"\n\n")
    assert data == (json.dumps(json.loads(data), indent=1) + "\n").encode("utf-8")
    assert validate_labels(json.loads(data)) == []


def test_normalizer_arrival_order_is_at_then_card_not_the_file_name(tmp_path, capsys):
    from synty_inventory.weapons.labels_store import main

    export = tmp_path / "export"
    names = [f"z_{len(RECORDS) - i:02d}.json" for i in range(len(RECORDS))]  # file-name order is the reverse of arrival order
    write_export(export, RECORDS, names)
    assert main(["--export", str(export), "--out", str(tmp_path / "o.json")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["conflicts"] == [{"indices": [2, 4], "values": ["yes", "no"]}, {"indices": [3, 5], "values": ["no", "skip"]}]


def test_normalizer_cli_refuses_without_writing(tmp_path, capsys):
    from synty_inventory.weapons.labels_store import main

    export = tmp_path / "export"
    bad = copy.deepcopy(RECORDS)
    bad[2]["fits"] = "maybe"
    write_export(export, bad)
    out = tmp_path / "o.json"
    assert main(["--export", str(export), "--out", str(out)]) != 0
    assert not out.exists()
    assert "Traceback" not in capsys.readouterr().err


def test_normalizer_cli_refuses_an_out_folder_that_does_not_exist(tmp_path, capsys):
    from synty_inventory.weapons.labels_store import main

    export = tmp_path / "export"
    write_export(export, RECORDS)
    out = tmp_path / "missing_folder" / "o.json"
    code = main(["--export", str(export), "--out", str(out)])
    captured = capsys.readouterr()
    assert code != 0 and not out.parent.exists() and "does not exist" in captured.err and "Traceback" not in captured.err


@pytest.mark.parametrize("content", ["[]", json.dumps([RECORDS[0]]), "3", "{not json", json.dumps({"unrelated": 1})])
def test_normalizer_refuses_a_json_file_that_is_not_one_record(tmp_path, content):
    from synty_inventory.weapons.labels_store import main

    export = tmp_path / "export"
    write_export(export, RECORDS)
    (export / "extra.json").write_text(content, encoding="utf-8")
    out = tmp_path / "o.json"
    assert main(["--export", str(export), "--out", str(out)]) != 0 and not out.exists()


def test_normalizer_reads_the_folder_non_recursively(tmp_path, capsys):
    from synty_inventory.weapons.labels_store import main

    export = tmp_path / "export"
    write_export(export, RECORDS)
    (export / "nested").mkdir()
    (export / "nested" / "stray.json").write_text("{not even json", encoding="utf-8")  # below the folder: never read
    (export / "notes.txt").write_text("x", encoding="utf-8")
    assert main(["--export", str(export), "--out", str(tmp_path / "o.json")]) == 0
    assert json.loads(capsys.readouterr().out)["records"] == 9


def test_normalizer_refuses_a_missing_or_empty_export_folder(tmp_path):
    from synty_inventory.weapons.labels_store import main

    (tmp_path / "empty").mkdir()
    assert main(["--export", str(tmp_path / "empty"), "--out", str(tmp_path / "o.json")]) != 0
    assert main(["--export", str(tmp_path / "absent"), "--out", str(tmp_path / "o.json")]) != 0
    assert not (tmp_path / "o.json").exists()
