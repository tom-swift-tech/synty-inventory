"""Orchestrates one pack's ``scene-mine`` run: parse every scene, detect
duplicate layouts, extract the look + cameras from the first non-duplicate
scene, compute stats over the rest, and write the schema-validated
``scene-grammar/1`` JSON (spec ``s9_scene_grammar_spec.md``).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.resources
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from ..paths import posix
from . import stats
from .guid_index import GuidIndex
from .look_extract import extract_cameras, extract_look
from .unity_yaml import parse_scene

SCHEMA_NAME = "scene_grammar.v1.json"


class SceneMineError(Exception):
    """Base for scene-mine failures the CLI turns into an exit code."""


class OverviewSceneError(SceneMineError):
    """spec §7: a scene looks like Synty's catalogue ``Overview.unity`` grid
    rather than an authored layout -- refused even when named explicitly
    with ``--scene`` (AC8)."""

    def __init__(self, scene: str, placements: int, distinct: int) -> None:
        self.scene = scene
        self.placements = placements
        self.distinct = distinct
        super().__init__(
            f"{scene}: Overview heuristic fired -- {distinct} distinct assets across {placements} placements "
            f"({distinct / placements:.0%}, one-of-each; spec §7 as re-set 2026-09-06: >= {stats.MIN_LAYOUT_PLACEMENTS} "
            f"placements and distinct/placements >= {stats.OVERVIEW_DISTINCT_RATIO}); refusing to mine a catalogue "
            "grid as a layout"
        )


class ResolveRateError(SceneMineError):
    """spec AC3: a scene's resolved/placements ratio fell below the 0.95
    floor."""

    def __init__(self, scene: str, resolved: int, total: int, unresolved: list[dict]) -> None:
        self.scene = scene
        self.resolved = resolved
        self.total = total
        self.unresolved = unresolved
        rate = resolved / total if total else 1.0
        names = ", ".join(f"{u['guid']}({u['reason']}:{u['asset_path']})" for u in unresolved[:10])
        more = f" and {len(unresolved) - 10} more" if len(unresolved) > 10 else ""
        super().__init__(
            f"{scene}: resolve rate {rate:.4f} ({resolved}/{total}) is below the 0.95 floor (spec AC3): "
            f"{names}{more}"
        )


@dataclass(frozen=True)
class SceneGrammar:
    """The mined grammar (schema-shaped dict) plus the ``--report`` JSON."""

    doc: dict[str, Any]
    report: dict[str, Any]


def tool_version() -> str:
    """``importlib.metadata`` reads the installed dist's version; fall back
    to the in-tree constant when the worktree is not installed (e.g. running
    straight off ``pythonpath = ["src"]`` under pytest)."""
    try:
        return importlib.metadata.version("synty-inventory")
    except importlib.metadata.PackageNotFoundError:
        from .. import __version__

        return __version__


def _load_schema() -> dict:
    ref = importlib.resources.files("synty_inventory.data").joinpath(SCHEMA_NAME)
    return json.loads(ref.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _round_vec(v: Sequence[float], n: int = 4) -> list[float]:
    return [round(float(c), n) for c in v]


def _dedupe_key(placements: Sequence[dict]) -> tuple:
    """spec §5: a scene whose sorted ``(asset_id, pos_m, yaw_deg)`` multiset
    equals an earlier scene's is layout-identical (``Demo_TriplanarDirt`` vs
    ``Demo``: same layout, alternate ground material)."""
    return tuple(sorted((p["asset_id"], tuple(p["pos_m"]), p["yaw_deg"]) for p in placements))


def _diff_render_settings(first: Mapping[str, Any], other: Mapping[str, Any], scene: str) -> list[str]:
    diffs = []
    for key in sorted(set(first) | set(other)):
        if first.get(key) != other.get(key):
            diffs.append(f"{scene}: {key} differs (first={first.get(key)!r}, other={other.get(key)!r})")
    return diffs


def mine_pack(
    pack_id: str,
    scenes: Sequence[Path],
    catalog: dict,
    *,
    catalog_path: Path,
    adjacency_radius_m: float = 6.0,
    cell_m: float = 20.0,
    min_stats_placements: int = stats.MIN_LAYOUT_PLACEMENTS,
) -> SceneGrammar:
    """Mine every scene in ``scenes`` into one ``scene-grammar/1`` document.

    A scene with fewer than ``min_stats_placements`` resolved placements is
    ``stats_excluded``: it keeps its ``scenes[]`` row and may still supply the
    look and cameras (first non-duplicate scene), but contributes nothing to
    ``placements[]`` or the statistics -- Sci-Fi City's 16-object
    ``Demo_TriplanarDirt`` must not dilute the 2,357-placement Demo's density
    and spacing (2026-09-06). Tests on small fixtures lower the floor.

    Raises :class:`OverviewSceneError` / :class:`ResolveRateError` (CLI exit
    3), or lets ``unity_yaml.SceneParseError`` / ``guid_index.GuidIndexError``
    propagate (CLI exit 6). Nothing is written here -- :func:`write_grammar`
    does that after schema validation.
    """
    if not scenes:
        raise SceneMineError("no scenes to mine")
    extracted_root = Path(catalog["source"]["extracted"])
    index = GuidIndex.build(extracted_root)
    type_by_id = {a["id"]: a.get("type") for a in catalog.get("assets", []) or []}

    scene_rows: list[dict] = []
    scene_placements: list[list[dict]] = []  # one list per scene; [] for a duplicate
    all_unresolved: list[dict] = []
    warnings: list[str] = []
    seen_keys: dict[tuple, int] = {}
    look_doc: dict | None = None
    first_render_settings: Mapping[str, Any] | None = None
    render_diffs: list[str] = []
    cameras: list[dict] = []

    for i, scene_path in enumerate(scenes):
        scene_str = str(scene_path)
        scene_doc = parse_scene(scene_path, index, catalog)
        placements = [
            {
                "scene": i,
                "file_id": p.file_id,
                "asset_id": p.asset_id,
                "instance_name": p.instance_name,
                "pos_m": _round_vec(p.pos_m),
                "yaw_deg": p.yaw_deg,
                "pitch_deg": p.pitch_deg,
                "roll_deg": p.roll_deg,
                "scale": _round_vec(p.scale),
                "parent_path": p.parent_path,
                "static": p.static,
            }
            for p in scene_doc.placements
        ]
        scene_unresolved = [
            {
                "scene": i,
                "guid": u.guid,
                "asset_path": u.asset_path,
                "reason": u.reason,
                "instance_name": u.instance_name,
                "hint": u.hint,
            }
            for u in scene_doc.unresolved
        ]
        all_unresolved.extend(scene_unresolved)
        warnings.extend(scene_doc.warnings)

        check = stats.is_overview_scene(placements)
        if check.is_overview:
            raise OverviewSceneError(scene_str, check.placements, check.distinct)

        resolved = len(placements)
        total = resolved + len(scene_unresolved)
        if total and resolved / total < 0.95:
            raise ResolveRateError(scene_str, resolved, total, scene_unresolved)

        key = _dedupe_key(placements)
        dup_of = seen_keys.get(key)
        stats_excluded = resolved < min_stats_placements
        if dup_of is None:
            seen_keys[key] = i
        if dup_of is None and not stats_excluded:
            scene_placements.append(placements)
        else:
            # duplicate or below the floor: contributes to nothing but scenes[] (and, if it is the first
            # non-duplicate scene, the look + cameras below)
            scene_placements.append([])

        scene_rows.append(
            {
                "index": i,
                "path": _rel_scene_path(scene_path, extracted_root),
                "sha256": _sha256(scene_path),
                "placements": total,
                "resolved": resolved,
                "unresolved": len(scene_unresolved),
                "duplicate_of": dup_of,
                "stats_excluded": stats_excluded,
            }
        )

        if dup_of is None:
            if look_doc is None:
                look_doc, look_warnings = extract_look(scene_doc, index, extracted_root)
                warnings.extend(look_warnings)
                first_render_settings = scene_doc.render_settings
                # Cameras come from the same scene as the look: a camera is a vantage *in* one scene, and the
                # consumer (CaptureSyntyDemo) opens exactly this scene. Pooling every non-duplicate scene's
                # cameras put Demo_TriplanarDirt's "Main Camera" into the Sci-Fi City grammar (2026-09-06) --
                # same id, different scene, rendered against the wrong layout.
                cameras.extend(extract_cameras(scene_doc))
            elif scene_doc.render_settings is not None and first_render_settings is not None:
                render_diffs.extend(_diff_render_settings(first_render_settings, scene_doc.render_settings, scene_str))

    non_dup_placements = [p for lst in scene_placements for p in lst]
    non_dup_scene_lists = [lst for lst in scene_placements if lst]
    hist = stats.histogram(non_dup_placements)
    roles = stats.roles_for(hist.keys(), type_by_id)

    doc: dict[str, Any] = {
        "schema": "scene-grammar/1",
        "pack_id": pack_id,
        "catalog": {
            "path": posix(catalog_path),
            "version": catalog.get("version"),
            "sha256": _sha256(catalog_path),
        },
        "scenes": scene_rows,
        "placements": non_dup_placements,
        "unresolved": all_unresolved,
        "histogram": hist,
        "roles": roles,
        "adjacency": stats.adjacency(non_dup_scene_lists, adjacency_radius_m, hist),
        "spacing": stats.spacing(non_dup_scene_lists),
        "rotation": stats.rotation(non_dup_placements),
        "scale": stats.scale_stats(non_dup_placements),
        "ground": stats.ground(non_dup_scene_lists, roles),
        "density": stats.density(non_dup_scene_lists, cell_m, roles),
        "streets": stats.streets(non_dup_scene_lists, roles),
        "look": look_doc,
        "cameras": cameras,
        "provenance": {
            "tool": "synty-inventory scene-mine",
            "tool_version": tool_version(),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "adjacency_radius_m": adjacency_radius_m,
            "cell_m": cell_m,
        },
    }

    non_unit = [p for p in non_dup_placements if any(abs(c - 1.0) >= 1e-4 for c in p["scale"])]
    findings = {
        "non_unit_scale_placements": len(non_unit),
        "non_unit_scale_asset_ids": len({p["asset_id"] for p in non_unit}),
        "render_settings_diffs": sorted(render_diffs),
    }
    if any(findings.values()):
        doc["findings"] = findings
    sorted_warnings = sorted(set(warnings))
    if sorted_warnings:
        doc["warnings"] = sorted_warnings

    total_placements = sum(r["placements"] for r in scene_rows)
    total_resolved = sum(r["resolved"] for r in scene_rows)
    report = {
        "schema": "scene-mine-report/1",
        "pack_id": pack_id,
        "scenes": scene_rows,
        "resolve_rate": round(total_resolved / total_placements, 4) if total_placements else 1.0,
        "unresolved": all_unresolved,
        "findings": findings,
        "warnings": sorted_warnings,
    }
    return SceneGrammar(doc=doc, report=report)


def _rel_scene_path(scene_path: Path, extracted_root: Path) -> str:
    try:
        return posix(scene_path.resolve().relative_to(extracted_root.resolve()))
    except ValueError:
        return posix(scene_path)


def write_grammar(grammar: SceneGrammar, out: Path) -> Path:
    """Validate ``grammar.doc`` against ``scene_grammar.v1.json`` and write
    ``<out>/<pack_id>.scene_grammar.json``. Raises
    ``jsonschema.ValidationError`` and writes nothing on a schema violation
    (spec: "any schema violation -> raise, exit 6, nothing written")."""
    jsonschema.validate(grammar.doc, _load_schema())
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{grammar.doc['pack_id']}.scene_grammar.json"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(grammar.doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return dest
