"""G1 S2: the dependency rule of the ``fit_*`` modules (docs/weapon_attach_geometry.md 6 AC144, Q-G7; plan S2 and P1 "a detector module imports ...").

AC144: every ``fit_*.py`` imports only the standard library, ``numpy`` and ``synty_inventory`` (a relative import is ``synty_inventory``), and
``pyproject.toml`` declares exactly the dependencies written out below. The import graph rule keeps S7's wiring free of cycles: a detector module
imports only ``fit_types`` and ``mount_probe`` of the package, and no ``fit_*`` module reaches ``geometry``, ``mounts``, ``compat`` or ``directory``.
Deliberate breaks, in a scratch copy: an ``import scipy`` in any ``fit_*`` file; a detector importing ``fit_geometry`` or ``geometry``; a new line in
``dependencies``.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEAPONS = ROOT / "src" / "synty_inventory" / "weapons"
FIT_FILES = ["fit_bore", "fit_geometry", "fit_locate", "fit_rails", "fit_types", "fit_well"]
DETECTORS = ["fit_bore", "fit_locate", "fit_rails", "fit_well"]
ALLOWED_TOP = set(sys.stdlib_module_names) | {"numpy", "synty_inventory", "__future__"}


def imports_of(path: Path):
    """``(top_level_modules, sibling_modules)``: the absolute top-level packages imported, and the names of the package siblings imported relatively."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top, siblings = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            top.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                top.add("synty_inventory")
                if node.module:
                    siblings.add(node.module.split(".")[0])
                else:  # `from . import x`
                    siblings.update(a.name for a in node.names)
            else:
                top.add((node.module or "").split(".")[0])
                if node.module and node.module.startswith("synty_inventory.weapons."):
                    siblings.add(node.module.split(".")[2])
    return top, siblings


def test_the_fit_modules_are_exactly_the_six_of_the_plan():
    assert sorted(p.stem for p in WEAPONS.glob("fit_*.py")) == FIT_FILES


@pytest.mark.parametrize("name", FIT_FILES)
def test_a_fit_module_imports_only_the_standard_library_numpy_and_synty_inventory(name):
    top, _ = imports_of(WEAPONS / f"{name}.py")
    assert top <= ALLOWED_TOP, sorted(top - ALLOWED_TOP)


@pytest.mark.parametrize("name", DETECTORS)
def test_a_detector_module_imports_only_fit_types_and_mount_probe_of_the_package(name):
    _, siblings = imports_of(WEAPONS / f"{name}.py")
    assert siblings <= {"fit_types", "mount_probe"}, sorted(siblings)


def test_fit_types_imports_nothing_of_the_package():
    _, siblings = imports_of(WEAPONS / "fit_types.py")
    assert siblings == set()


def test_the_facade_imports_only_the_fit_modules_so_it_closes_no_cycle():
    _, siblings = imports_of(WEAPONS / "fit_geometry.py")
    assert siblings <= {"fit_types", "fit_locate", "fit_rails", "fit_bore", "fit_well"}, sorted(siblings)
    assert not siblings & {"geometry", "mounts", "compat", "directory"}


def test_the_scan_catches_a_forbidden_import(tmp_path):
    bad = tmp_path / "fit_bad.py"
    bad.write_text("import scipy.spatial\nfrom trimesh import Trimesh\nfrom . import geometry\nfrom .mounts import x\nimport numpy as np\n", encoding="utf-8")
    top, siblings = imports_of(bad)
    assert top - ALLOWED_TOP == {"scipy", "trimesh"} and siblings == {"geometry", "mounts"}


def test_pyproject_declares_exactly_the_same_dependencies_as_before():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["numpy>=1.26", "PyYAML>=6.0", "jsonschema>=4.17"]
    assert project["optional-dependencies"] == {"dev": ["pytest>=8", "ruff>=0.6"], "render": ["Pillow>=10"]}
