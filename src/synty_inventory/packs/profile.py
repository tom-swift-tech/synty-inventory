"""``pack-profile``: derive ``<catalogs>/pack_profiles/<pack_id>.json``
(``pack-profile/1``, spec §4.3) from an existing catalog + curated tables.

Everything except ``setting``/``era``/``palette`` is rule-derived straight off
catalog fields (``type``, ``semantic_role``, ``module.family``, counts,
``files.*``, ``kind``) -- no VLM call needed for AC1 to pass. ``setting``/
``era`` come from the curated ``data/pack_settings.yaml`` table (one entry
per cataloged pack_id) and only *change* under an optional VLM refinement
pass; ``palette`` is measured from cheaply-available preview images when
present, else left null. A human-override YAML always wins last (F13's
6-tier provenance precedence, ``merge.PROVENANCE_RANK``): ``rules`` <
``vlm`` < ``human``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files as pkg_files
from pathlib import Path

import yaml

from ..sources.godot import SLUG_PACK_OVERRIDES

SCHEMA = "pack-profile/1"

# spec §4.3 controlled vocab
PACK_CLASSES = frozenset(
    {"environment", "addon", "characters", "animation", "interface", "fx", "map_demo"}
)
SETTINGS = frozenset(
    {
        "modern_city",
        "scifi_city",
        "scifi_frontier",
        "space",
        "fantasy",
        "post_apoc",
        "military",
        "western",
        "horror",
        "nature",
        "generic",
    }
)
# open low->high scale (spec: "prehistoric...far_future", not a closed enum)
# -- pack_settings.yaml's header documents this same list.
ERAS = (
    "prehistoric",
    "ancient",
    "colonial",
    "medieval",
    "industrial",
    "modern",
    "near_future",
    "far_future",
)

# A pack is "environment" (spec rule) only if it is both big *and* actually
# builds a place: a shell/module kit or a ground/road surface. A prop-only
# pack of 500 chairs never qualifies no matter its count.
_ENVIRONMENT_ROLES = frozenset({"building_shell", "ground_surface", "road_surface"})
_ENVIRONMENT_MIN_PLACEABLE = 150
_ADDON_MAX_ASSETS = 40  # spec AC1: strictly "< 40" -> addon, checked first


def _settings_table_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "pack_settings.yaml"


@lru_cache(maxsize=1)
def load_settings_table() -> dict[str, dict]:
    """``pack_id`` -> ``{setting, era}`` from the curated table.

    Loaded straight off the filesystem (not ``importlib.resources``) so an
    editable-install dev tree picks up edits immediately -- matches how
    ``paths.py``/``knowledge.py`` treat other ``data/*`` tables, except this
    one is YAML (spec-mandated filename) rather than JSON, so it is read
    directly rather than through ``pkg_files`` (whose packaged-wheel path
    needs a ``pyproject.toml`` ``package-data`` entry for ``*.yaml`` that
    does not exist yet -- follow-on for whoever owns that file).
    """
    path = _settings_table_path()
    if not path.is_file():
        raise RuntimeError(f"pack_settings.yaml missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"pack_settings.yaml malformed (expected a mapping): {path}")
    return data


def setting_and_era(pack_id: str) -> tuple[str | None, str | None]:
    """Curated ``(setting, era)`` for ``pack_id``, or ``(None, None)`` when
    the table has no entry -- callers report this rather than guess."""
    row = load_settings_table().get(pack_id)
    if not row:
        return None, None
    return row.get("setting"), row.get("era")


def classify_pack(pack_id: str, assets: list[dict]) -> str:
    """spec §4.3 ``pack_class`` rule, in the order that makes AC1 hold:

    1. ``< 40`` assets is *always* ``addon`` -- this must win over every
       prefix rule below it (a small ``INTERFACE_*``/``ANIMATION_*`` pack is
       still an addon, not "interface"/"animation").
    2. Prefix/suffix rules for the non-environment classes.
    3. The environment rule (>= 150 placeable *and* a building/shell or
       terrain role).
    4. Everything else is ``addon`` (the spec's implicit catch-all).
    """
    n = len(assets)
    if n < _ADDON_MAX_ASSETS:
        return "addon"
    if pack_id.startswith("ANIMATION_"):
        return "animation"
    if pack_id.startswith("INTERFACE_"):
        return "interface"
    if pack_id.startswith("SIDEKICK_"):
        return "characters"
    if pack_id.endswith("_Map"):
        return "map_demo"
    if pack_id.endswith("_FX") or "Particle_FX" in pack_id:
        return "fx"
    placeable = [a for a in assets if a.get("placeable") is not False]
    has_environment_role = any(
        (a.get("semantic_role") in _ENVIRONMENT_ROLES) or (a.get("type") or "").startswith("building/shell")
        for a in assets
    )
    if len(placeable) >= _ENVIRONMENT_MIN_PLACEABLE and has_environment_role:
        return "environment"
    return "addon"


def role_counts(assets: list[dict]) -> dict[str, int]:
    """Counts keyed by ``semantic_role`` (falling back to ``type`` for the
    handful of assets with no semantic role yet) -- spec's "counts per
    type/semantic_role"."""
    counts: dict[str, int] = {}
    for a in assets:
        key = a.get("semantic_role") or a.get("type") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def kit_families(assets: list[dict]) -> list[str]:
    fams = {(a.get("module") or {}).get("family") for a in assets}
    return sorted(f for f in fams if f)


@lru_cache(maxsize=1)
def _package_recipe_packs() -> dict[str, set[str]]:
    """pack_id -> set of package recipe ids that name it in ``packs``."""
    out: dict[str, set[str]] = {}
    recipes_dir = pkg_files("synty_inventory").joinpath("recipes")
    for entry in recipes_dir.iterdir():
        if not entry.name.endswith(".json"):
            continue
        try:
            rec = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rid = rec.get("id")
        for pid in rec.get("packs") or []:
            out.setdefault(pid, set()).add(rid)
    return out


def grammar_available(pack_id: str, catalogs_dir: Path | None) -> bool:
    """True when a package/user recipe names this pack, or a mined
    ``<pack_id>.scene_grammar.json`` sidecar exists next to its catalog."""
    if pack_id in _package_recipe_packs():
        return True
    if catalogs_dir is None:
        return False
    catalogs_dir = Path(catalogs_dir)
    if (catalogs_dir / f"{pack_id}.scene_grammar.json").is_file():
        return True
    user_recipes = catalogs_dir / "recipes"
    if user_recipes.is_dir():
        for entry in user_recipes.glob("*.json"):
            try:
                rec = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if pack_id in (rec.get("packs") or []):
                return True
    return False


@lru_cache(maxsize=1)
def _pack_id_to_slug() -> dict[str, str]:
    out: dict[str, str] = {}
    for slug, pack_id in SLUG_PACK_OVERRIDES.items():
        out.setdefault(pack_id, slug)
    return out


def _report_has_fatal_errors(report: dict) -> bool:
    """``godot_convert``'s ``conversion_report.json`` -- ``validate`` block
    carries ``import_exit_code``/``log_error_count`` (``dangling_ref_count``
    is a warning, not treated as fatal: every observed real report has 0 of
    all three, so this is conservative but unverified against a real
    failure)."""
    validate = report.get("validate") or {}
    exit_code = validate.get("import_exit_code")
    log_errors = validate.get("log_error_count")
    if exit_code not in (0, None):
        return True
    if isinstance(log_errors, int) and log_errors > 0:
        return True
    return False


def godot_ready(pack_id: str, godot_root: Path | None) -> bool:
    """spec: registered in ``SLUG_PACK_OVERRIDES`` *and* the export folder's
    ``conversion_report.json`` (when one exists) has no fatal errors.

    Synty-shipped exports (e.g. ``polygon-city-01``, ``polygon-sci-fi-city-01``)
    are converted by Synty, not by ``godot_convert``, so they never get a
    ``conversion_report.json`` -- a missing report is not itself a failure,
    it just means there is nothing to check (registration already implies
    the export was vetted before the override was added)."""
    slug = _pack_id_to_slug().get(pack_id)
    if slug is None:
        return False
    if godot_root is None:
        return True
    report_path = Path(godot_root) / slug / "conversion_report.json"
    if not report_path.is_file():
        return True
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not _report_has_fatal_errors(report)


def characters_rig(pack_id: str, assets: list[dict]) -> str | None:
    if pack_id.startswith("SIDEKICK_"):
        return "sidekick"
    if any(a.get("type") == "character" and a.get("placeable") is not False for a in assets):
        return "polygon_humanoid"
    return None


_PALETTE_MAX_IMAGES = 6


def measure_palette(pack_id: str, catalogs_dir: Path | None) -> tuple[dict | None, str]:
    """Pixel-stat palette from whatever preview PNGs already exist under
    ``<catalogs>/previews/<pack_id>/`` (extracted by ``scan --extract-previews``
    for a subset of packs -- signage/character/weapon previews). Cheap: no
    GLB decode, no render. Most packs have no previews on disk, so this
    usually returns ``(None, "rules")`` -- the spec's documented degraded
    case (F13's wording for an unreachable VLM applies just as well to "no
    cheap source" here).

    Returns ``(palette_or_none, provenance_tier)``.
    """
    if catalogs_dir is None:
        return None, "rules"
    preview_dir = Path(catalogs_dir) / "previews" / pack_id
    if not preview_dir.is_dir():
        return None, "rules"
    images = sorted(preview_dir.glob("*.png"))[:_PALETTE_MAX_IMAGES]
    if not images:
        return None, "rules"
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None, "rules"

    samples = []
    for img_path in images:
        try:
            with Image.open(img_path) as im:
                arr = np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
        except (OSError, ValueError):
            continue
        samples.append(arr.reshape(-1, 3))
    if not samples:
        return None, "rules"
    pixels = np.concatenate(samples, axis=0)
    mean_rgb = pixels.mean(axis=0)
    mx = pixels.max(axis=1)
    mn = pixels.min(axis=1)
    saturation = float(((mx - mn) / np.where(mx == 0, 1, mx)).mean())
    brightness = float(pixels.mean())
    palette = {
        "dominant_rgb": [[round(float(c), 4) for c in mean_rgb]],
        "saturation": round(saturation, 4),
        "brightness": round(brightness, 4),
    }
    return palette, "measured"


def ollama_reachable(url: str, *, timeout: float = 1.5) -> bool:
    """Fast one-shot probe (F13: a down local VLM must not cost 126x the
    per-call timeout) -- ``GET /api/tags``, not a chat call."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False


def make_vlm_refine(*, catalogs_dir: Path | None, model: str, url: str, timeout: int = 60):
    """``vlm_refine(pack_id, assets) -> {"setting":..., "era":...} | None``
    for ``build_pack_profile``. Only packs with extracted preview PNGs (see
    ``measure_palette``'s docstring -- same cheap-source constraint) get a
    VLM opinion; everything else stays on the rules table, which is not a
    failure, just nothing to show the model."""
    from ..vlm import query_local_vlm

    def refine(pack_id: str, assets: list[dict]) -> dict | None:  # noqa: ARG001 (assets kept for symmetry/future use)
        if catalogs_dir is None:
            return None
        preview_dir = Path(catalogs_dir) / "previews" / pack_id
        if not preview_dir.is_dir():
            return None
        images = sorted(preview_dir.glob("*.png"))[:3]
        if not images:
            return None
        prompt = (
            "You classify a Synty low-poly asset PACK (not a single asset) for a "
            f"game pipeline. Pack id: {pack_id!r}.\n"
            "Return ONLY JSON with keys 'setting' and 'era'.\n"
            f"setting must be exactly one of: {sorted(SETTINGS)}\n"
            f"era must be exactly one of: {list(ERAS)}\n"
        )
        return query_local_vlm(images, prompt, url=url, model=model, timeout=timeout, max_attempts=1)

    return refine


def build_pack_profile(
    doc: dict,
    *,
    catalogs_dir: Path | None = None,
    godot_root: Path | None = None,
    human_override: dict | None = None,
    vlm_refine=None,
) -> dict:
    """One ``pack-profile/1`` record for an already-loaded catalog ``doc``.

    ``vlm_refine``, if given, is ``(pack_id, assets) -> {"setting": ..., "era": ...} | None``
    -- already probed for reachability by the caller (see ``cli.py``); a
    ``None`` return (unreachable/timeout/bad reply) is F13's degraded path
    and leaves ``setting``/``era`` on the rules table. ``human_override`` is
    ``{"setting": ..., "era": ..., "pack_class": ..., "characters_rig": ...}``
    for this one pack_id (caller pre-selects the row), applied last.
    """
    pack_id = doc["pack_id"]
    assets = doc.get("assets") or []

    provenance: dict[str, str] = {}

    pclass = classify_pack(pack_id, assets)
    provenance["pack_class"] = "rules"

    setting, era = setting_and_era(pack_id)
    provenance["setting"] = "rules"
    provenance["era"] = "rules"

    if vlm_refine is not None:
        refined = vlm_refine(pack_id, assets)
        if refined:
            new_setting = refined.get("setting")
            if new_setting in SETTINGS:
                setting = new_setting
                provenance["setting"] = "vlm"
            new_era = refined.get("era")
            if new_era:
                era = new_era
                provenance["era"] = "vlm"

    palette, palette_prov = measure_palette(pack_id, catalogs_dir)
    provenance["palette"] = palette_prov

    rig = characters_rig(pack_id, assets)
    provenance["characters_rig"] = "rules"

    ready = godot_ready(pack_id, godot_root)
    provenance["godot_ready"] = "rules"

    profile = {
        "schema": SCHEMA,
        "pack_id": pack_id,
        "pack_class": pclass,
        "setting": setting,
        "era": era,
        "palette": palette,
        "role_counts": role_counts(assets),
        "kit_families": kit_families(assets),
        "grammar_available": grammar_available(pack_id, catalogs_dir),
        "godot_ready": ready,
        "characters_rig": rig,
        "provenance": provenance,
    }

    if human_override:
        for field in ("pack_class", "setting", "era", "characters_rig", "godot_ready", "grammar_available"):
            if field in human_override and human_override[field] is not None:
                profile[field] = human_override[field]
                provenance[field] = "human"
        if "palette" in human_override:
            profile["palette"] = human_override["palette"]
            provenance["palette"] = "human"

    return profile
