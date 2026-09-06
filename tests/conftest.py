"""Per-session pytest ``basetemp``.

pytest's default ``tmp_path`` root is one shared, numbered ``<system temp>/pytest-of-<user>/pytest-N`` tree. Two
sessions running at once (a builder's suite beside the lead's, or this repo's suite beside map_builder's under
the same user) race on the numbering and on the keep-last-3 cleanup, which deletes the other session's live
``tmp_path`` directories mid-run -- the "parallel pytest collision" seen 2026-09-06. It is a basetemp problem,
not a reason to run suites one at a time: give every session its own root under ``.pytest_tmp/`` (gitignored)
and prune roots older than a day. An explicit ``--basetemp`` on the command line still wins.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

PYTEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".pytest_tmp"
PRUNE_AFTER_S = 24 * 3600


@pytest.hookimpl(tryfirst=True)  # before _pytest.tmpdir reads config.option.basetemp
def pytest_configure(config: pytest.Config) -> None:
    if config.option.basetemp:
        return
    PYTEST_TMP_ROOT.mkdir(exist_ok=True)
    cutoff = time.time() - PRUNE_AFTER_S
    for old in PYTEST_TMP_ROOT.iterdir():
        try:
            if old.is_dir() and old.stat().st_mtime < cutoff:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass  # another session may be pruning the same directory
    stamp = time.strftime("%Y%m%d-%H%M%S")
    config.option.basetemp = str(PYTEST_TMP_ROOT / f"session-{stamp}-{os.getpid()}")
