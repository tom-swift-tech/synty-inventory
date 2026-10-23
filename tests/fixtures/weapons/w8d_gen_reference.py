"""Regenerate the W7 reference files of the W8d tests with the UNTOUCHED W7 tree (synty-inventory main, e6e82b6).

    python tests/fixtures/weapons/w8d_gen_reference.py <path of the W7 tree> <output folder>

The W7 tree is only read. The script copies its ``tests/fixtures/weapons`` folder into a temp folder, adds this tree's
W8 fixture modules (``w8a_attach``, ``w8c_compat``, ``w8d_world``, which reach engine code only through
``wfx.build``), and runs itself there with ``PYTHONPATH=<W7 tree>/src``. The temp copy matters: ``wfx`` puts the ``src``
beside the fixtures at the front of ``sys.path``, so loading the fixtures from this tree would shadow the W7 engine with
W8 code. The inner run asserts that the engine it imports is the W7 one (no ``WEAPON_ATTACH_VERSION``).

Outputs (``w8d_w7_*``): the W7 ``directory.json`` of the whole W8d world (compact JSON, gzip without a timestamp) and
the W7 ``weapons export --game ref --packs <the four attachment packs>`` for the default roles and for ``--roles all``.
"""

from __future__ import annotations

import contextlib
import gzip
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKS = "FAKE_Attach,FAKE_CompA,FAKE_CompB,FAKE_Mount"
OUT_NAMES = {"directory": "w8d_w7_directory.json.gz", "default": "w8d_w7_attach_default_export.json",
             "all": "w8d_w7_attach_roles_all_export.json"}
COPY = ("w8a_attach.py", "w8c_compat.py", "w8d_world.py", "w8d_gen_reference.py")


def outer(w7_tree: Path, out_dir: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        fixtures = Path(tmp) / "tests" / "fixtures" / "weapons"
        shutil.copytree(w7_tree / "tests" / "fixtures" / "weapons", fixtures,
                        ignore=shutil.ignore_patterns("__pycache__"))
        for name in COPY:
            shutil.copyfile(HERE / name, fixtures / name)
        env = {**os.environ, "PYTHONPATH": str(w7_tree / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        for key in list(env):
            if key.startswith("SYNTI_"):
                del env[key]
        out_dir.mkdir(parents=True, exist_ok=True)
        done = subprocess.run([sys.executable, str(fixtures / "w8d_gen_reference.py"), "--inner", str(w7_tree),
                               str(out_dir)], cwd=tmp, env=env, check=False)
        return done.returncode


def inner(w7_tree: Path, out_dir: Path) -> int:
    import synty_inventory
    import synty_inventory.weapons as weapons

    assert Path(synty_inventory.__file__).resolve().is_relative_to(w7_tree.resolve()), synty_inventory.__file__
    assert not hasattr(weapons, "WEAPON_ATTACH_VERSION"), "this is not the W7 engine"
    spec = importlib.util.spec_from_file_location("w8d_world", HERE / "w8d_world.py")
    world = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(world)
    from synty_inventory.cli import main
    from synty_inventory.weapons.directory import write_directory

    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        directory, excluded, cat, _root = world.build(tmp)
        write_directory(cat, directory, excluded)
        cfg = world.write_config(tmp, cat)
        text = json.dumps(json.loads((cat / "weapons" / "directory.json").read_text(encoding="utf-8")),
                          sort_keys=True, separators=(",", ":")) + "\n"
        with open(out_dir / OUT_NAMES["directory"], "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0,
                                                                                filename="") as gz:
            gz.write(text.encode("utf-8"))
        for key, roles in (("default", None), ("all", "all")):
            target = tmp / "game" / f"{key}.json"
            argv = ["--config", str(cfg), "weapons", "export", "--game", "ref", "--packs", PACKS, "--out", str(target)]
            if roles:
                argv += ["--roles", roles]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(argv)
            assert code == 0, buf.getvalue()
            shutil.copyfile(target, out_dir / OUT_NAMES[key])
    print("wrote", ", ".join(OUT_NAMES.values()), "to", out_dir)
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--inner":
        sys.exit(inner(Path(sys.argv[2]), Path(sys.argv[3])))
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(outer(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
