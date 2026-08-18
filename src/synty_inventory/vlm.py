"""Optional VLM enrichment. Off unless --vlm is passed and a key is set."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


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
        "grok-2-vision-1212" if os.environ.get("XAI_API_KEY") else "gpt-4o-mini"
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
