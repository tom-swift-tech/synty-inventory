"""Optional VLM enrichment. Off unless --vlm is passed and a key is set.

Two independent backends live here:
  - the hosted API path below (xAI/OpenAI-compatible, needs an API key) used
    by `scan --vlm` / `enrich --vlm` for a light unreviewed draft pass;
  - `query_local_vlm`, a local Ollama backend (no key, no upload) used by
    `review.py` to produce the threejs-v2 `catalog.json` reviewed entries.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

from .paths import SETTING_DEFAULTS

LOCAL_DEFAULT_URL = SETTING_DEFAULTS["vlm_local_url"]
LOCAL_DEFAULT_MODEL = SETTING_DEFAULTS["vlm_local_model"]
HOSTED_DEFAULT_MODEL = "grok-4.6"
HOSTED_XAI_BASE = "https://api.x.ai/v1"


def vlm_available() -> bool:
    return bool(os.environ.get("XAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("SYNTI_VLM_API_KEY"))


def _endpoint() -> tuple[str, str, str]:
    key = (
        os.environ.get("SYNTI_VLM_API_KEY")
        or os.environ.get("XAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    base = (
        os.environ.get("SYNTI_VLM_BASE_URL")
        or ("https://api.x.ai/v1" if os.environ.get("XAI_API_KEY") else "https://api.openai.com/v1")
    )
    model = os.environ.get("SYNTI_VLM_MODEL") or (
        HOSTED_DEFAULT_MODEL if os.environ.get("XAI_API_KEY") else "gpt-4o-mini"
    )
    return key, base.rstrip("/"), model


def enrich_asset_vlm(asset: dict, image_path: Path | None = None) -> dict | None:
    """Draft description/tags/placement from name + optional preview. Returns None on skip/fail."""
    if not vlm_available():
        return None
    key, base, model = _endpoint()
    prompt = (
        "You inventory a Synty low-poly game asset for an autonomous Unity scene builder.\n"
        "Return ONLY JSON with keys: description, tags (array of short slugs), "
        "semantic_role (snake_case), placement (mount, height, orientation, attachment, "
        "preferred_floors, constraints, preferred_contexts), ai_notes.\n"
        f"Asset id: {asset.get('id')}\n"
        f"Name: {asset.get('name')}\n"
        f"Type: {asset.get('type')}\n"
        f"Existing description: {asset.get('description')}\n"
    )
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image_path and image_path.is_file():
        import base64

        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        draft = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    changed = False
    if isinstance(draft.get("description"), str) and draft["description"].strip():
        asset["description"] = draft["description"].strip()
        asset.setdefault("provenance", {})["description"] = "vlm"
        changed = True
    if isinstance(draft.get("semantic_role"), str) and draft["semantic_role"].strip():
        asset["semantic_role"] = draft["semantic_role"].strip()
        asset.setdefault("provenance", {})["semantic_role"] = "vlm"
        changed = True
    if isinstance(draft.get("ai_notes"), str) and draft["ai_notes"].strip():
        asset["ai_notes"] = draft["ai_notes"].strip()
        asset.setdefault("provenance", {})["ai_notes"] = "vlm"
        changed = True
    if isinstance(draft.get("tags"), list):
        for t in draft["tags"]:
            if isinstance(t, str) and t and t not in asset["tags"]:
                asset["tags"].append(t)
        changed = True
    if isinstance(draft.get("placement"), dict):
        place = asset.setdefault("placement", {})
        for key in (
            "mount",
            "height",
            "orientation",
            "attachment",
            "preferred_floors",
            "constraints",
            "preferred_contexts",
        ):
            if draft["placement"].get(key) not in (None, "", []):
                place[key] = draft["placement"][key]
        asset.setdefault("provenance", {})["placement"] = "vlm"
        changed = True
    return asset if changed else None


def _image_content(path: Path) -> dict | None:
    """OpenAI-compatible image_url block for one still on disk."""
    path = Path(path)
    if not path.is_file():
        return None
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
    }


def query_hosted_vlm(
    image_paths: Sequence[Path],
    prompt: str,
    *,
    model: str | None = None,
    timeout: int = 180,
    temperature: float = 0.0,
    max_attempts: int = 3,
) -> dict | None:
    """Ask a hosted vision model (Grok 4.6 on xAI by default) to return JSON.

    Used by ``synty-inventory vision``. Does not mutate an asset. Returns the
    parsed object, or None once attempts are exhausted.
    """
    if not vlm_available():
        return None
    key, base, default_model = _endpoint()
    model = model or default_model
    content: list[dict] = [{"type": "text", "text": prompt}]
    for raw in image_paths:
        block = _image_content(Path(raw))
        if block is not None:
            content.append(block)
    if len(content) < 2:
        return None
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    # Grok 4.x defaults to high reasoning; catalog JSON does not need it.
    if str(model).startswith("grok-4"):
        body["reasoning"] = {"effort": "low"}
    data = json.dumps(body).encode("utf-8")
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for _ in range(max(1, max_attempts)):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            return _parse_json_object(text)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
            continue
    return None


def _parse_json_object(text: str) -> dict:
    """Pull the first {...} object out of a model reply and parse it.

    Raises ValueError when nothing parseable is found, so the retry loop in
    `query_local_vlm` treats a malformed reply the same as a network error.
    Ollama's ``format: "json"`` keeps gemma4 honest almost always, but a
    low-end quant can still wrap the object in stray prose.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in VLM reply")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("VLM reply JSON is not an object")
    return obj


def query_local_vlm(
    image_paths: Sequence[Path],
    prompt: str,
    *,
    url: str = LOCAL_DEFAULT_URL,
    model: str = LOCAL_DEFAULT_MODEL,
    temperature: float = 0.1,
    timeout: int = 600,
    max_attempts: int = 3,
) -> dict | None:
    """Ask a local Ollama vision model to describe `image_paths`.

    No API key, no upload — everything stays on localhost. Retries up to
    `max_attempts` times on a connection error, timeout, or a reply that
    doesn't parse as a JSON object (covers both an unreachable Ollama and an
    occasional malformed completion). Returns the parsed object, or None once
    attempts are exhausted; callers must treat None as "skip this asset",
    never abort the batch.
    """
    images_b64 = []
    for p in image_paths:
        path = Path(p)
        if path.is_file():
            images_b64.append(base64.b64encode(path.read_bytes()).decode("ascii"))
    if not images_b64:
        return None
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": images_b64}],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
    }
    endpoint = url.rstrip("/") + "/api/chat"
    data = json.dumps(body).encode("utf-8")
    for _ in range(max(1, max_attempts)):
        try:
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            content = (payload.get("message") or {}).get("content") or ""
            return _parse_json_object(content)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
            continue
    return None
