"""Weapon directory W2f: the geometry cache fingerprint includes a digest of geometry.py, so a code change at the same
WEAPON_GEOMETRY_VERSION rebuilds the entry instead of serving stale geometry. Bounds are literals."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

import synty_inventory.weapons as pkg
from synty_inventory.weapons import geometry as G
from synty_inventory.weapons.geometry import measure_cached
from synty_inventory.weapons.rules import load_rules

_spec = importlib.util.spec_from_file_location(
    "make_glbs_w2f_cache", Path(__file__).parent / "fixtures" / "weapons" / "make_glbs.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture()
def sword_root(tmp_path):
    M.write_glb(tmp_path / "s.glb", [{"name": "s", "mesh": M.bar(0.0, 0.9, 0.02, 0.005)}])
    return tmp_path


def args(root, rules):
    return (root, "s.glb", None, 1.0, "sword", "melee", "whole", rules)


def test_code_digest_is_the_first_12_hex_of_the_sha256():
    assert G.code_digest(b"abc") == "ba7816bf8f01"  # sha256("abc") = ba7816bf 8f01cfea 414140de ...


def test_code_digest_changes_when_the_text_changes():
    assert G.code_digest(b"x = 1\n") != G.code_digest(b"x = 2\n")


def test_code_digest_is_the_same_for_crlf_and_lf_text():
    lf = b"def f():\n    return 1\n"
    assert G.code_digest(lf.replace(b"\n", b"\r\n")) == G.code_digest(lf)


def test_the_module_digest_is_the_digest_of_its_own_source():
    assert re.fullmatch(r"[0-9a-f]{12}", G._CODE_DIGEST)
    assert G._CODE_DIGEST == G.code_digest(Path(G.__file__).read_bytes())


def test_a_written_cache_entry_carries_the_version_and_the_digest(sword_root, rules):
    cache: dict = {}
    measure_cached(*args(sword_root, rules), cache, genre="fantasy")
    version = cache["s.glb"]["version"]
    assert re.fullmatch(r"5\+[0-9a-f]{12}", version)
    assert version == "5+" + G.code_digest(Path(G.__file__).read_bytes())


def test_the_directory_header_keeps_the_plain_integer_version():
    # directory.json's generated_from.geometry_version is the schema's integer; only the cache entry carries the digest
    assert pkg.WEAPON_GEOMETRY_VERSION == 5 and isinstance(pkg.WEAPON_GEOMETRY_VERSION, int)


def test_an_entry_written_under_another_code_digest_is_not_served(sword_root, rules, monkeypatch):
    cache: dict = {}
    monkeypatch.setattr(G, "_CODE_DIGEST", "000000000000")
    measure_cached(*args(sword_root, rules), cache, genre="fantasy")
    assert cache["s.glb"]["version"] == "5+000000000000"
    cache["s.glb"]["by_inputs"][next(iter(cache["s.glb"]["by_inputs"]))]["geometry"]["length_m"] = 999.0  # poison it
    assert measure_cached(*args(sword_root, rules), cache, genre="fantasy")[1] is True  # same digest: served
    monkeypatch.undo()  # the real digest differs: the entry is rebuilt
    fresh, was = measure_cached(*args(sword_root, rules), cache, genre="fantasy")
    assert was is False and fresh["geometry"]["length_m"] == 0.9
    assert re.fullmatch(r"5\+[0-9a-f]{12}", cache["s.glb"]["version"]) and not cache["s.glb"]["version"].endswith("0" * 12)


def test_a_legacy_entry_with_a_bare_integer_version_is_not_served(sword_root, rules):
    cache: dict = {}
    measure_cached(*args(sword_root, rules), cache, genre="fantasy")
    cache["s.glb"]["version"] = 5  # the pre-digest format at the same integer version
    cache["s.glb"]["by_inputs"][next(iter(cache["s.glb"]["by_inputs"]))]["geometry"]["length_m"] = 999.0
    fresh, was = measure_cached(*args(sword_root, rules), cache, genre="fantasy")
    assert was is False and fresh["geometry"]["length_m"] == 0.9
