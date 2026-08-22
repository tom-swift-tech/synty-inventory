"""Local Ollama VLM backend: request shape, JSON-retry, no-key requirement."""

import json
from pathlib import Path

from synty_inventory import vlm


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _image(tmp_path: Path, name: str = "still.png") -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return p


def test_local_backend_needs_no_api_key(monkeypatch, tmp_path):
    """Unlike the hosted path, the local backend never checks env for a key."""
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SYNTI_VLM_API_KEY", raising=False)
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse({"message": {"content": '{"name": "Crate"}'}})

    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)
    result = vlm.query_local_vlm([_image(tmp_path)], "describe it", url="http://localhost:11434", model="gemma4:e4b")
    assert result == {"name": "Crate"}
    assert calls[0]["model"] == "gemma4:e4b"
    assert calls[0]["format"] == "json"
    assert len(calls[0]["messages"][0]["images"]) == 1


def test_local_backend_hits_the_ollama_chat_endpoint(monkeypatch, tmp_path):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _FakeResponse({"message": {"content": "{}"}})

    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)
    vlm.query_local_vlm([_image(tmp_path)], "p", url="http://example:1234/", model="m")
    assert seen["url"] == "http://example:1234/api/chat"


def test_json_retry_recovers_from_one_bad_reply(monkeypatch, tmp_path):
    replies = iter(
        [
            _FakeResponse({"message": {"content": "not json at all"}}),
            _FakeResponse({"message": {"content": '{"name": "Second try"}'}}),
        ]
    )

    def fake_urlopen(req, timeout=None):
        return next(replies)

    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)
    result = vlm.query_local_vlm([_image(tmp_path)], "p", max_attempts=3)
    assert result == {"name": "Second try"}


def test_returns_none_after_exhausting_retries(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse({"message": {"content": "still not json"}})

    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)
    result = vlm.query_local_vlm([_image(tmp_path)], "p", max_attempts=2)
    assert result is None


def test_returns_none_on_connection_error(monkeypatch, tmp_path):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)
    result = vlm.query_local_vlm([_image(tmp_path)], "p", max_attempts=2)
    assert result is None


def test_no_images_short_circuits_without_a_request(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout=None):
        raise AssertionError("should not be called with zero images")

    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)
    result = vlm.query_local_vlm([tmp_path / "missing.png"], "p")
    assert result is None


def test_extracts_json_object_wrapped_in_prose():
    text = 'Sure, here you go:\n{"name": "Wrapped"}\nHope that helps!'
    assert vlm._parse_json_object(text) == {"name": "Wrapped"}


def test_defaults_match_setting_defaults():
    from synty_inventory.paths import SETTING_DEFAULTS

    assert vlm.LOCAL_DEFAULT_URL == SETTING_DEFAULTS["vlm_local_url"]
    assert vlm.LOCAL_DEFAULT_MODEL == SETTING_DEFAULTS["vlm_local_model"]
    assert SETTING_DEFAULTS["vlm_local_model"] == "gemma4:26b"
