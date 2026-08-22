"""Resolve library roots from env and config.yaml. Never hardcodes machine paths."""

from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

try:
    import yaml
except ImportError:  # stdlib fallback — config.yaml is simple key: value
    yaml = None

_PACKAGE_DIR = Path(__file__).resolve().parent
EXAMPLE_NAME = "config.example.yaml"
SKILL_NAME = "skill.md"
CONFIG_NAME = "config.yaml"

# key -> environment variable. No default path values live here.
CONFIG_KEYS: dict[str, str] = {
    "unity_root": "SYNTI_UNITY_ROOT",
    "extracted_root": "SYNTI_EXTRACTED_ROOT",
    "threejs_v2": "SYNTI_THREEJS_V2",
    "viewer_data": "SYNTI_VIEWER_DATA",
    "catalogs": "SYNTI_CATALOGS",
    "godot_root": "SYNTI_GODOT_ROOT",
    "unreal_root": "SYNTI_UNREAL_ROOT",
    "synty_glb_root": "SYNTI_SYNTY_GLB_ROOT",
}

REQUIRED_KEYS = ("unity_root", "extracted_root", "catalogs")
CONFIG_FILE_ENV = "SYNTI_CONFIG"

# Non-path string settings, same env-override-then-file precedence as
# CONFIG_KEYS/resolve_config but never coerced through _as_path (a URL or a
# model tag is not a filesystem path). Used by the local Ollama VLM backend
# (review.py / vlm.py) — see resolve_settings().
SETTING_KEYS: dict[str, str] = {
    "vlm_local_url": "SYNTI_VLM_LOCAL_URL",
    "vlm_local_model": "SYNTI_VLM_LOCAL_MODEL",
}
SETTING_DEFAULTS: dict[str, str] = {
    "vlm_local_url": "http://localhost:11434",
    "vlm_local_model": "gemma4:26b",
}


class ConfigError(ValueError):
    """Missing or unreadable path configuration."""


def checkout_root() -> Path | None:
    """Repo root when running from a src checkout / editable install."""
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").is_file() and (root / "src" / "synty_inventory").is_dir():
        return root
    return None


def example_file() -> Path:
    """config.example.yaml shipped in the package, else the checkout copy."""
    packaged = _PACKAGE_DIR / EXAMPLE_NAME
    if packaged.is_file():
        return packaged
    root = checkout_root()
    if root is not None:
        return root / EXAMPLE_NAME
    return packaged


def skill_file() -> Path:
    """Bundled skill markdown (package data)."""
    packaged = _PACKAGE_DIR / SKILL_NAME
    if packaged.is_file():
        return packaged
    root = checkout_root()
    if root is not None:
        return root / "skill" / "SKILL.md"
    return packaged


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw or ":" not in raw:
            continue
        key, val = raw.split(":", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _as_path(raw: str, base: Path) -> Path:
    text = str(raw).strip()
    path = Path(text).expanduser()
    # Drive-letter paths (C:/...) are absolute on Windows but relative on
    # POSIX — without this, Linux CI joins them onto the config directory.
    if path.is_absolute() or PureWindowsPath(text).is_absolute():
        return path
    return base / path


def find_config_file(explicit: Path | None = None) -> Path | None:
    """Return the config file to read, or None if none was requested/found.

    Search order: --config / explicit, SYNTI_CONFIG, cwd/config.yaml,
    <tool checkout>/config.yaml. The example file is never auto-loaded.
    """
    if explicit is not None:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
        return path
    env = os.environ.get(CONFIG_FILE_ENV)
    if env:
        path = Path(env).expanduser()
        if not path.is_file():
            raise ConfigError(f"{CONFIG_FILE_ENV} points at a missing file: {path}")
        return path
    cwd = Path.cwd() / CONFIG_NAME
    if cwd.is_file():
        return cwd
    tool = checkout_root()
    if tool is not None and (tool / CONFIG_NAME).is_file():
        return tool / CONFIG_NAME
    return None


def resolve_config(config_path: Path | None = None) -> dict:
    """Return paths, per-key sources, and the config file used. Does not raise on missing keys."""
    path = find_config_file(config_path)
    file_cfg = _load_yaml(path) if path else {}
    file_base = path.parent if path else Path.cwd()
    resolved: dict[str, Path] = {}
    sources: dict[str, str] = {}
    for key, env_name in CONFIG_KEYS.items():
        env_raw = os.environ.get(env_name)
        if env_raw:
            resolved[key] = _as_path(env_raw, Path.cwd())
            sources[key] = "env"
            continue
        file_raw = file_cfg.get(key)
        if file_raw:
            resolved[key] = _as_path(str(file_raw), file_base)
            sources[key] = "file"
            continue
        sources[key] = "unset"
    return {
        "config_file": path,
        "example_file": example_file(),
        "paths": resolved,
        "sources": sources,
    }


def resolve_settings(config_path: Path | None = None) -> dict[str, str]:
    """Resolve SETTING_KEYS (non-path config): env var, then config.yaml,
    then SETTING_DEFAULTS. Same file/precedence lookup as resolve_config,
    but values are read as plain strings, never turned into a Path."""
    path = find_config_file(config_path)
    file_cfg = _load_yaml(path) if path else {}
    out: dict[str, str] = {}
    for key, env_name in SETTING_KEYS.items():
        env_raw = os.environ.get(env_name)
        if env_raw:
            out[key] = env_raw
            continue
        file_raw = file_cfg.get(key)
        if file_raw:
            out[key] = str(file_raw)
            continue
        out[key] = SETTING_DEFAULTS[key]
    return out


def missing_required(resolved: dict[str, Path]) -> list[str]:
    return [key for key in REQUIRED_KEYS if key not in resolved]


def load_config(config_path: Path | None = None, *, require: bool = True) -> dict[str, Path]:
    meta = resolve_config(config_path)
    resolved: dict[str, Path] = meta["paths"]
    if require:
        missing = missing_required(resolved)
        if missing:
            looked = meta["config_file"] or f"no {CONFIG_NAME} found"
            example = meta["example_file"]
            env_hint = ", ".join(CONFIG_KEYS[k] for k in missing)
            raise ConfigError(
                f"missing required path(s): {', '.join(missing)}. "
                f"Copy {example.name} to {CONFIG_NAME} and set your machine paths "
                f"(looked at {looked}), or set {env_hint}."
            )
    return resolved


def require_path(cfg: dict[str, Path], key: str) -> Path:
    val = cfg.get(key)
    if val is None:
        env = CONFIG_KEYS.get(key, key.upper())
        raise ConfigError(
            f"{key} is not configured. Set it in {CONFIG_NAME} or {env}. "
            f"See {EXAMPLE_NAME}."
        )
    return val


def posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def rel_posix(path: Path, root: Path) -> str:
    try:
        return posix(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return posix(path)
