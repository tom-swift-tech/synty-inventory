"""Refusals that protect the library and the machine, shared by the ``weapons`` verbs (docs/weapon_directory.md section 7).

Two guards live here, both pure decisions over the environment so tests can aim them elsewhere:

- ``ensure_sole_runner``: ``weapons build`` and ``weapons icons`` write cache files (geometry cache, icons,
  directory.json). Two inventory processes at once corrupt each other, so a second one refuses to start (exit 2) and
  names the pid it found. A process listing that cannot be made never blocks: a guard that fails closed on a locked-down
  machine would make the verbs unusable.
- ``refuse_export_target``: a snapshot is pack-derived data for a *game's* private repo (INV-1). It is refused (exit 3)
  inside this checkout and inside any git work tree that tracks ``*.synty*`` files (a marker of a pack-derived tree).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from . import InputError, RefusalError

# A command line that runs this tool: the console script (``synty-inventory`` / ``synty-inventory.exe``), the module
# (``-m synty_inventory``) or its entry point (``synty_inventory.cli`` / ``synty_inventory/cli.py``). A bare mention such as
# ``pytest --cov=synty_inventory`` or a path that merely contains the package name does not start a run, so it does not count.
_INVENTORY_CMD = re.compile(
    r"(?i)(?:^|[\s\"'\\/])synty-inventory(?:\.exe)?(?=$|[\s\"'])"
    r"|-m\s+synty_inventory(?=$|[\s\"'.])"
    r"|synty_inventory[\\/.]cli(?:\.py)?(?=$|[\s\"'])"
)
_POWERSHELL_LIST = (
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='synty-inventory.exe'\" "
    "| ForEach-Object { '{0}|{1}|{2}' -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }"
)
_LIST_TIMEOUT_S = 20
_GIT_TIMEOUT_S = 30


# --- process lock ------------------------------------------------------------------------------------------------------


def _list_processes() -> list[tuple[int, int, str]]:
    """``[(pid, parent pid, command line)]`` of the python processes on this machine; ``[]`` when it cannot be listed.

    Windows asks PowerShell (CIM), POSIX reads ``/proc``. Tests replace this function with a fake.
    """
    try:
        if sys.platform == "win32":
            return _list_windows()
        return _list_proc()
    except Exception:  # noqa: BLE001 - an unreadable process table must not block the verb (and logs nothing)
        return []


def _list_windows() -> list[tuple[int, int, str]]:
    done = subprocess.run(["powershell", "-NoProfile", "-Command", _POWERSHELL_LIST], capture_output=True, text=True,
                          timeout=_LIST_TIMEOUT_S, check=False)
    rows: list[tuple[int, int, str]] = []
    for line in done.stdout.splitlines():
        pid, _, rest = line.partition("|")
        ppid, _, cmdline = rest.partition("|")
        if pid.strip().isdigit() and ppid.strip().isdigit():
            rows.append((int(pid), int(ppid), cmdline.strip()))
    return rows


def _list_proc() -> list[tuple[int, int, str]]:
    rows: list[tuple[int, int, str]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            ppid = int(stat[stat.rindex(")") + 2:].split()[1])  # fields after "(comm)": state, ppid, ...
        except (OSError, ValueError):
            continue
        rows.append((int(entry.name), ppid, cmdline))
    return rows


def other_inventory_processes() -> list[tuple[int, str]]:
    """``[(pid, command line)]`` of other running inventory processes, excluding this process and its ancestors.

    The console-script launcher that started us (and, on Windows, a virtualenv redirector above it) carries the same
    command line as this process: walking the whole parent chain keeps every one of them out of the answer.
    """
    rows = _list_processes()
    parent = {pid: ppid for pid, ppid, _ in rows}
    mine = {os.getpid(), os.getppid()}
    nxt = parent.get(os.getppid())
    while nxt and nxt not in mine:  # a stale (reused) pid can only add a row that is not an inventory process anyway
        mine.add(nxt)
        nxt = parent.get(nxt)
    return sorted((pid, cmd) for pid, _ppid, cmd in rows if pid not in mine and _INVENTORY_CMD.search(cmd))


def ensure_sole_runner() -> None:
    """Raise ``InputError`` (exit 2) naming the pid(s) when another inventory process is running."""
    others = other_inventory_processes()
    if others:
        pids = ", ".join(str(pid) for pid, _ in others)
        raise InputError(
            f"another synty-inventory process is running (pid {pids}); `weapons build` and `weapons icons` write cache "
            "files and must not overlap with it: wait for it to finish, then run again",
            details={"pids": [pid for pid, _ in others]})


# --- export target -----------------------------------------------------------------------------------------------------


def repo_root() -> Path | None:
    """The checkout that holds the ``synty_inventory`` package (resolved from this file), or None for an installed copy.

    A function, so tests can aim it at a throwaway directory.
    """
    root = Path(__file__).resolve().parents[3]
    if (root / "pyproject.toml").is_file() and (root / "src" / "synty_inventory").is_dir():
        return root
    return None


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _git(args: list[str], cwd: Path) -> str | None:
    """stdout of ``git <args>`` run in ``cwd``; None when git is missing or the command fails."""
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=_GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def tracked_synty_work_tree(directory: Path) -> Path | None:
    """The git work tree around ``directory`` when it tracks any ``*.synty*`` file, else None (also without git)."""
    start = directory
    while not start.exists() and start != start.parent:  # the output folder may not exist yet
        start = start.parent
    top = _git(["rev-parse", "--show-toplevel"], start)
    if not top or not top.strip():
        return None
    work_tree = Path(top.strip()).resolve()
    listed = _git(["ls-files", "--", "*.synty*"], work_tree)
    return work_tree if listed and listed.strip() else None


_UNSET = object()


def refuse_export_target(path: Path, *, repo=_UNSET) -> None:
    """Raise ``RefusalError`` (exit 3) when ``path`` would put a snapshot in this checkout or in a git work tree that
    tracks ``*.synty*`` files. Nothing is written or created. ``repo`` overrides ``repo_root()`` (``export`` passes its
    own seam so a test can aim it)."""
    target = Path(path).resolve()
    parent = target.parent
    root = repo_root() if repo is _UNSET else repo
    if root is not None and _inside(parent, Path(root).resolve()):
        raise RefusalError(
            "refusing to write a snapshot inside this repository (it is pack-derived data for a game's private repo, INV-1)",
            details={"root": Path(root).name})
    tree = tracked_synty_work_tree(parent)
    if tree is not None:
        raise RefusalError(
            "refusing to write a snapshot into a git repository that tracks *.synty* files "
            "(it is pack-derived data for a game's private repo, INV-1)", details={"root": tree.name})
