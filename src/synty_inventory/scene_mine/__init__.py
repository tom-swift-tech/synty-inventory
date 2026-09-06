"""Mine a Synty pack's demo ``.unity`` scenes into a scene-grammar JSON
(spec ``tasks/s9_scene_grammar_spec.md``). See ``mine.mine_pack`` for the
entry point and ``synty_inventory.cli.cmd_scene_mine`` for the CLI."""

from __future__ import annotations

from .guid_index import GuidIndex, GuidIndexError
from .look_extract import extract_cameras, extract_look
from .mine import OverviewSceneError, ResolveRateError, SceneGrammar, SceneMineError, mine_pack, write_grammar
from .unity_yaml import Placement, SceneDoc, SceneParseError, UnityDoc, UnresolvedRef, field, iter_docs, parse_scene

__all__ = [
    "GuidIndex",
    "GuidIndexError",
    "extract_cameras",
    "extract_look",
    "OverviewSceneError",
    "ResolveRateError",
    "SceneGrammar",
    "SceneMineError",
    "mine_pack",
    "write_grammar",
    "Placement",
    "SceneDoc",
    "SceneParseError",
    "UnityDoc",
    "UnresolvedRef",
    "field",
    "iter_docs",
    "parse_scene",
]
