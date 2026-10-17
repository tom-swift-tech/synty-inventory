"""Weapon directory W6: the process lock, the export-target refusals, the default snapshot folder, the ignore rules.

Spec section 7 (failure modes) and 3.1 (layout). Everything is synthetic: fixture catalogs, throwaway git repositories
under the pytest tmp dir, fake process tables. Git is probed once; its tests skip when it is not installed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_helpers", Path(__file__).parent / "fixtures" / "weapons" / "review_helpers.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

from synty_inventory.cli import build_parser  # noqa: E402
from synty_inventory.weapons import EXIT_REFUSED, InputError, RefusalError, export as X, guards  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="git is not installed")
FAKE_CMD = "python -m synty_inventory weapons build"


def tree(root: Path) -> dict[str, tuple]:
    """Every path under ``root`` with its size: any file or directory created or rewritten changes it."""
    return {p.relative_to(root).as_posix(): (p.is_dir(), p.stat().st_size if p.is_file() else 0)
            for p in sorted(root.rglob("*"))}


def git(cwd: Path, *args: str) -> None:
    subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True)


def make_repo(path: Path, tracked: str | None) -> Path:
    """A git work tree at ``path``; ``tracked`` (a relative file name) is created and added to the index."""
    path.mkdir(parents=True)
    git(path, "init", "-q")
    (path / "readme.txt").write_text("game\n", encoding="utf-8")
    git(path, "add", "readme.txt")
    if tracked:
        (path / tracked).parent.mkdir(parents=True, exist_ok=True)
        (path / tracked).write_text("{}\n", encoding="utf-8")
        git(path, "add", tracked)
    return path


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# --- item 3: process lock ----------------------------------------------------------------------------------------------


def fake_table(monkeypatch, rows):
    monkeypatch.setattr(guards, "_list_processes", lambda: list(rows))


def test_another_inventory_process_blocks_and_the_message_names_its_pid(monkeypatch):
    fake_table(monkeypatch, [(4242, 1, FAKE_CMD), (5151, 1, "python -m pytest tests")])
    assert guards.other_inventory_processes() == [(4242, FAKE_CMD)]
    with pytest.raises(InputError) as err:
        guards.ensure_sole_runner()
    assert err.value.code == 2 and "4242" in str(err.value) and "5151" not in str(err.value)
    assert err.value.details == {"pids": [4242]}


def test_this_process_its_parent_and_the_launcher_chain_are_excluded(monkeypatch):
    me, parent = os.getpid(), os.getppid()
    launcher = r'"C:\Python\python.exe" "C:\Python\Scripts\synty-inventory.exe" weapons build'
    fake_table(monkeypatch, [
        (me, parent, launcher),  # this process
        (parent, 70001, launcher),  # the console-script launcher that started it
        (70001, 1, launcher),  # a virtualenv redirector above the launcher
        (4242, 1, launcher),  # a different process with the very same command line
    ])
    assert guards.other_inventory_processes() == [(4242, launcher)]
    fake_table(monkeypatch, [(me, parent, launcher), (parent, 70001, launcher), (70001, 1, launcher)])
    assert guards.other_inventory_processes() == []
    guards.ensure_sole_runner()  # and so it does not raise


@pytest.mark.parametrize("cmd,counts", [
    (r'"C:\Py\python.exe" "C:\Py\Scripts\synty-inventory.exe" weapons icons', True),
    ("synty-inventory weapons build", True),
    ("python -m synty_inventory scan", True),
    ('python -c "from synty_inventory.cli import main; main()"', True),
    ("python -m pytest tests/test_weapons_directory.py", False),
    ("python -m pytest --cov=synty_inventory tests", False),  # a bare mention of the package is not a run
    (r"python D:\tools\synty-inventory-notes\scan.py", False),
    ("python -m http.server 8765", False),
])
def test_which_command_lines_count_as_an_inventory_run(monkeypatch, cmd, counts):
    fake_table(monkeypatch, [(4242, 1, cmd)])
    assert bool(guards.other_inventory_processes()) is counts


def test_this_pytest_run_does_not_look_like_an_inventory_run():
    here = " ".join([sys.executable, "-m", "pytest", "tests/test_weapons_directory.py", "-o", "addopts=", "-q"])
    assert guards._INVENTORY_CMD.search(here) is None


def test_a_process_listing_that_fails_never_blocks(monkeypatch):
    def boom():
        raise OSError("no powershell here")

    monkeypatch.setattr(guards, "_list_windows", boom)
    monkeypatch.setattr(guards, "_list_proc", boom)
    assert guards._list_processes() == []
    guards.ensure_sole_runner()


def test_build_and_icons_refuse_to_start_beside_another_inventory_process_and_write_nothing(tmp_path, monkeypatch, capsys):
    cat = H.make_catalogs(tmp_path)
    cfg = H.write_config(tmp_path, cat)
    fake_table(monkeypatch, [(4242, 1, FAKE_CMD)])
    before = tree(tmp_path)
    code, out = H.run(cfg, capsys, ["weapons", "build"])
    assert code == 2 and out["ok"] is False and "4242" in out["error"]
    assert tree(tmp_path) == before and not (cat / "weapons").exists()  # nothing created, nothing touched

    monkeypatch.setattr(guards, "_list_processes", lambda: [])
    code, out = H.run(cfg, capsys, ["weapons", "build", "--no-geometry"])
    assert code == 0, out  # the lock is the only thing that stopped it
    fake_table(monkeypatch, [(4242, 1, FAKE_CMD)])
    before = tree(tmp_path)
    directory = (cat / "weapons" / "directory.json").read_bytes()
    code, out = H.run(cfg, capsys, ["weapons", "icons"])
    assert code == 2 and out["ok"] is False and "4242" in out["error"]
    assert tree(tmp_path) == before and (cat / "weapons" / "directory.json").read_bytes() == directory


# --- item 4: refusal to write into this repo or a repo that tracks *.synty* ---------------------------------------------


def test_the_library_root_is_the_checkout_that_holds_the_package():
    root = guards.repo_root()
    if root is None:
        pytest.skip("installed copy: no checkout around the package")
    assert (root / "pyproject.toml").is_file() and (root / "src" / "synty_inventory").is_dir()
    assert root == REPO


def test_a_target_inside_the_library_checkout_is_refused_and_one_beside_it_is_not(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    (lib / "docs").mkdir(parents=True)
    monkeypatch.setattr(guards, "repo_root", lambda: lib)
    for target in (lib / "snap.json", lib / "docs" / "deep" / "snap.json"):
        with pytest.raises(RefusalError) as err:
            guards.refuse_export_target(target)
        assert err.value.code == EXIT_REFUSED == 3
        assert not target.exists()
    guards.refuse_export_target(tmp_path / "game" / "snap.json")  # a sibling folder is fine
    guards.refuse_export_target(tmp_path / "library_notes" / "snap.json")  # same prefix, other folder


@needs_git
def test_a_git_work_tree_that_tracks_synty_files_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(guards, "repo_root", lambda: None)
    game = make_repo(tmp_path / "game", tracked="pack.synty")
    nested = make_repo(tmp_path / "game2", tracked="data/district.synty.json")  # a nested file name also counts
    for target in (game / "snap.json", game / "out" / "new" / "snap.json", nested / "x" / "snap.json"):
        with pytest.raises(RefusalError, match="tracks"):
            guards.refuse_export_target(target)
        assert not target.exists()


@needs_git
def test_a_git_work_tree_without_synty_files_and_a_path_in_no_repo_are_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(guards, "repo_root", lambda: None)
    clean = make_repo(tmp_path / "clean", tracked=None)
    (clean / "pack.synty").write_text("{}\n", encoding="utf-8")  # present but not tracked: not a marker
    guards.refuse_export_target(clean / "out" / "snap.json")
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # git must not find a repo above the throwaway folders
    guards.refuse_export_target(plain / "snap.json")


def test_without_git_the_work_tree_check_does_not_refuse(tmp_path, monkeypatch):
    monkeypatch.setattr(guards, "repo_root", lambda: None)
    monkeypatch.setattr(guards.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("git")))
    guards.refuse_export_target(tmp_path / "snap.json")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fixture catalogs + a measured directory; the checkout seam points elsewhere (the pytest tmp dir sits inside it)."""
    cat = H.make_catalogs(tmp_path, shared=True)
    root = H.make_threejs(tmp_path, cat)
    H.build_and_write(cat, threejs_v2_dir=root)
    monkeypatch.setattr(X, "_repo_root", lambda: None)
    return {"tmp": tmp_path, "cat": cat, "cfg": H.write_config(tmp_path, cat)}


EXPORT = ["weapons", "export", "--game", "district7", "--packs", "FAKE_Modern"]


@needs_git
def test_export_into_a_git_repo_that_tracks_synty_files_exits_3_and_writes_nothing(world, capsys):
    game = make_repo(world["tmp"] / "game", tracked="pack.synty")
    before = tree(game)
    code, res = H.run(world["cfg"], capsys, [*EXPORT, "--out", str(game / "snaps" / "district7.json")])
    assert code == 3 and res["ok"] is False and "tracks" in res["error"]
    assert tree(game) == before and not (game / "snaps").exists()
    clean = make_repo(world["tmp"] / "clean", tracked=None)
    code, res = H.run(world["cfg"], capsys, [*EXPORT, "--out", str(clean / "snaps" / "district7.json")])
    assert code == 0, res
    assert (clean / "snaps" / "district7.json").is_file()


def test_export_into_the_library_checkout_exits_3_and_writes_nothing(world, capsys, monkeypatch):
    lib = world["tmp"] / "pretend_library"
    lib.mkdir()
    monkeypatch.setattr(guards, "repo_root", lambda: lib)
    monkeypatch.setattr(X, "_repo_root", guards.repo_root)  # the export seam follows the guard's function
    code, res = H.run(world["cfg"], capsys, [*EXPORT, "--out", str(lib / "deep" / "district7.json")])
    assert code == 3 and not (lib / "deep").exists()


# --- item 6: --out is optional ------------------------------------------------------------------------------------------


def test_the_export_out_option_is_optional_in_the_parser():
    args = build_parser().parse_args(["weapons", "export", "--game", "g", "--packs", "A"])
    assert args.export_out is None
    args = build_parser().parse_args(["weapons", "export", "--game", "g", "--packs", "A", "--out", "x.json"])
    assert args.export_out == "x.json"


def test_export_without_out_writes_under_the_catalogs_snapshots_folder(world, capsys):
    cat = world["cat"]
    code, res = H.run(world["cfg"], capsys, EXPORT)
    default = cat / "weapons" / "snapshots" / "district7.json"
    assert code == 0, res
    assert default.is_file() and json.loads(default.read_text(encoding="utf-8"))["generated_from"]["filter"]["game"] == "district7"
    assert X.validate_snapshot(default) == []
    assert X.default_snapshot_path(cat, "district7") == default
    assert sorted(p.name for p in (cat / "weapons" / "snapshots").iterdir()) == ["district7.json"]


def test_the_default_snapshot_path_is_refused_when_the_catalogs_sit_inside_the_checkout(world, capsys, monkeypatch):
    monkeypatch.setattr(X, "_repo_root", lambda: world["tmp"])  # the catalogs dir is below this "checkout"
    code, res = H.run(world["cfg"], capsys, EXPORT)
    assert code == 3 and res["ok"] is False
    assert not (world["cat"] / "weapons" / "snapshots").exists()


def test_an_explicit_out_wins_over_the_default(world, capsys):
    out = world["tmp"] / "game_repo" / "mine.json"
    code, res = H.run(world["cfg"], capsys, [*EXPORT, "--out", str(out)])
    assert code == 0, res
    assert out.is_file() and not (world["cat"] / "weapons" / "snapshots").exists()


def test_an_explicit_out_inside_the_catalogs_dir_is_still_refused(world, capsys):
    target = world["cat"] / "weapons" / "snapshots" / "x.json"
    code, res = H.run(world["cfg"], capsys, [*EXPORT, "--out", str(target)])
    assert code == 3 and not target.exists()


@pytest.mark.parametrize("game", ["a/b", "a\\b", "..", "../up", "C:evil", ".", "x.", "", " pad"])
def test_a_game_name_that_is_not_a_safe_file_stem_is_bad_input_without_out(world, capsys, game):
    before = tree(world["tmp"])
    code, res = H.run(world["cfg"], capsys, ["weapons", "export", "--game", game, "--packs", "FAKE_Modern"])
    assert code == 2 and res["ok"] is False and "--game" in res["error"]
    assert tree(world["tmp"]) == before


def test_such_a_game_name_is_fine_when_an_explicit_out_names_the_file(world, capsys):
    out = world["tmp"] / "game_repo" / "mine.json"
    code, res = H.run(world["cfg"], capsys, ["weapons", "export", "--game", "a/b", "--packs", "FAKE_Modern", "--out", str(out)])
    assert code == 0, res


# --- item 7: the tracked fixture catalogs are not ignored ----------------------------------------------------------------


def _in_git_checkout() -> bool:
    if GIT is None:
        return False
    done = subprocess.run([GIT, "rev-parse", "--is-inside-work-tree"], cwd=REPO, capture_output=True, text=True)
    return done.returncode == 0 and done.stdout.strip() == "true"


@pytest.mark.skipif(not _in_git_checkout(), reason="needs git and a git checkout")
def test_no_tracked_fixture_file_is_matched_by_an_ignore_rule():
    done = subprocess.run([GIT, "ls-files", "-ci", "--exclude-standard"], cwd=REPO, capture_output=True, text=True, check=True)
    ignored_but_tracked = [ln for ln in done.stdout.splitlines() if ln.startswith("tests/fixtures/weapons/")]
    assert ignored_but_tracked == []


@pytest.mark.skipif(not _in_git_checkout(), reason="needs git and a git checkout")
def test_the_fixture_catalogs_are_reincluded_but_generated_catalogs_stay_ignored():
    def ignored(rel: str) -> bool:
        done = subprocess.run([GIT, "check-ignore", "--no-index", "-q", rel], cwd=REPO)
        return done.returncode == 0

    assert not ignored("tests/fixtures/weapons/catalogs/FAKE_Modern.json")
    assert not ignored("tests/fixtures/weapons/catalogs/FAKE_New.json")  # a new synthetic fixture needs no `add -f`
    assert ignored("catalogs/anything.json") and ignored("tests/fixtures/other/catalogs/x.json")
