"""Catalog schema helpers — keep fields aligned with the asset-viewer inventory."""

from __future__ import annotations

from typing import Any

CATALOG_VERSION = 1

REQUIRED_CATALOG = (
    "pack_id",
    "engine",
    "origin",
    "style",
    "units",
    "version",
    "scanned_at",
    "assets",
)
REQUIRED_ASSET = (
    "id",
    "name",
    "type",
    "category",
    "tags",
    "description",
    "semantic_role",
    "placement",
    "dimensions",
    "paths",
    "thumbnail",
    "ai_notes",
)
REQUIRED_PLACEMENT = (
    "mount",
    "height",
    "orientation",
    "attachment",
    "preferred_floors",
    "constraints",
    "preferred_contexts",
)
SEMANTIC_FIELDS = (
    "name",
    "type",
    "category",
    "tags",
    "description",
    "semantic_role",
    "placement",
    "ai_notes",
)


def empty_placement() -> dict[str, Any]:
    return {
        "mount": "ground",
        "height": "grade",
        "orientation": "upright",
        "attachment": "base_to_ground",
        "preferred_floors": [1],
        "constraints": [],
        "preferred_contexts": [],
    }


def empty_paths() -> dict[str, Any]:
    return {"prefab": None, "mesh": None, "materials": []}


def validate_catalog(doc: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["catalog is not an object"]
    for key in REQUIRED_CATALOG:
        if key not in doc:
            errors.append(f"missing catalog.{key}")
    if doc.get("units") != "meters":
        errors.append("units must be 'meters'")
    if doc.get("version") != CATALOG_VERSION:
        errors.append(f"version must be {CATALOG_VERSION}")
    assets = doc.get("assets")
    if not isinstance(assets, list):
        errors.append("assets must be a list")
        return errors
    seen: set[str] = set()
    for i, asset in enumerate(assets):
        prefix = f"assets[{i}]"
        if not isinstance(asset, dict):
            errors.append(f"{prefix} is not an object")
            continue
        for key in REQUIRED_ASSET:
            if key not in asset:
                errors.append(f"{prefix} missing {key}")
        aid = asset.get("id")
        if isinstance(aid, str):
            if aid in seen:
                errors.append(f"duplicate asset id {aid}")
            seen.add(aid)
        place = asset.get("placement")
        if isinstance(place, dict):
            for key in REQUIRED_PLACEMENT:
                if key not in place:
                    errors.append(f"{prefix}.placement missing {key}")
        else:
            errors.append(f"{prefix}.placement must be an object")
        dims = asset.get("dimensions")
        if not isinstance(dims, dict) or "approx" not in dims or "units" not in dims:
            errors.append(f"{prefix}.dimensions must have approx + units")
        elif not (
            isinstance(dims.get("approx"), list)
            and len(dims["approx"]) == 3
            and all(isinstance(n, (int, float)) for n in dims["approx"])
        ):
            errors.append(f"{prefix}.dimensions.approx must be [x,y,z] numbers")
        paths = asset.get("paths")
        if not isinstance(paths, dict):
            errors.append(f"{prefix}.paths must be an object")
        else:
            for key in ("prefab", "mesh", "materials"):
                if key not in paths:
                    errors.append(f"{prefix}.paths missing {key}")
    return errors
