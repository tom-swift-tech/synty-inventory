"""Slim per-call projection of catalog records (roadmap Phase 1).

The catalogs are ~3.7 KB per record on disk — harmless there, lethal in an
agent's context. Every list-returning verb (``search``, ``suggest``,
``recipe``, ``kit``) therefore emits slim rows (~150 B): id, pack, type,
role, measured size, socket count, kit family/role, one file path for the
target engine. ``--fields a,b,c`` widens rows with named full-record fields;
``details <id>`` remains the full record. Gauntlet's ``token_budget`` gate
pins this so it cannot regress.
"""

from __future__ import annotations


def primary_file(asset: dict, engine: str | None) -> str | None:
    """The one file an agent instantiates for the target engine.

    Same contract as ``query.engine_files`` (semantics never change with
    engine; only which path is surfaced) collapsed to a single path with
    GLB fallback. ``--fields files`` recovers the full dict.
    """
    files = asset.get("files") or {}
    eng = (engine or "").lower()
    if eng == "unity":
        return files.get("unity_prefab") or files.get("unity_mesh") or files.get("glb")
    if eng == "unreal":
        return files.get("unreal_uasset") or files.get("glb")
    if eng == "godot":
        return files.get("godot_scene") or files.get("glb")
    # threejs / all / unspecified
    return files.get("glb") or files.get("unity_prefab") or files.get("godot_scene") or files.get("unreal_uasset")


def _round3(vals) -> list[float] | None:
    if not isinstance(vals, (list, tuple)) or len(vals) != 3:
        return None
    try:
        return [round(float(v), 2) for v in vals]
    except (TypeError, ValueError):
        return None


def slim_row(
    pack_id: str,
    asset: dict,
    *,
    engine: str | None = None,
    fields: list[str] | None = None,
    score: float | None = None,
) -> dict:
    """Project one catalog record to a slim result row.

    Optional facts (sockets, kit, kit_role, glb_node) appear only when
    present — absence means "not that kind of asset", and omitting keeps
    rows tight. ``fields`` copies named top-level record fields verbatim
    (``files`` honours ``engine`` via the full per-engine dict).
    """
    module = asset.get("module") or {}
    part = asset.get("part") or {}
    row: dict = {
        "id": asset.get("id"),
        "pack": pack_id,
        "type": asset.get("type"),
        "role": asset.get("semantic_role"),
        "size": _round3((asset.get("bounds") or {}).get("size")),
        "file": primary_file(asset, engine),
    }
    sockets = len(part.get("sockets") or [])
    if sockets:
        row["sockets"] = sockets
    slots = len((asset.get("mech") or {}).get("slots") or [])
    if slots:
        row["slots"] = slots
    if module.get("family"):
        row["kit"] = module["family"]
    if module.get("role"):
        row["kit_role"] = module["role"]
    if part.get("class"):
        row["part_class"] = part["class"]
    node = (asset.get("files") or {}).get("glb_node")
    if node:
        row["glb_node"] = node
    if score is not None:
        row["score"] = round(score, 2)
    for f in fields or []:
        if f in row and f != "files":
            continue
        if f == "files":
            from .query import engine_files  # local import; query imports this module

            row["files"] = engine_files(asset, engine)
        else:
            row[f] = asset.get(f)
    return row
