from pathlib import Path
from types import SimpleNamespace

from synty_inventory.cli import attach_extracted_previews, cmd_validate, emit_json


class _LegacyStdout:
    """Mimic a Windows console that cannot encode arrows."""

    def __init__(self, encoding: str = "cp1252"):
        self.encoding = encoding
        self.chunks: list[str] = []

    def write(self, text: str) -> int:
        text.encode(self.encoding)
        self.chunks.append(text)
        return len(text)


def test_emit_json_survives_legacy_console():
    stream = _LegacyStdout("cp1252")
    emit_json({"detail": "police->x; note: cafe\u2192bar"}, stream)
    assert stream.chunks
    joined = "".join(stream.chunks)
    assert "police" in joined


def test_validate_missing_dir_fails(tmp_path: Path, capsys):
    missing = tmp_path / "no-such-catalogs"
    code = cmd_validate(SimpleNamespace(out=missing, pack=None), {})
    assert code != 0
    err = capsys.readouterr().err
    assert "not found" in err


def test_validate_empty_dir_fails(tmp_path: Path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    code = cmd_validate(SimpleNamespace(out=empty, pack=None), {})
    assert code != 0
    err = capsys.readouterr().err
    assert "no catalogs" in err


def test_attach_extracted_previews_overwrites_placeholder(tmp_path: Path):
    dest = tmp_path / "previews" / "FakePack"
    dest.mkdir(parents=True)
    written = dest / "SM_Prop_Sign_Police_01.png"
    written.write_bytes(b"png")
    assets = [
        {
            "id": "SM_Prop_Sign_Police_01",
            "thumbnail": "previews/SM_Prop_Sign_Police_01.png",
        }
    ]
    attach_extracted_previews(assets, [str(written)], tmp_path)
    assert assets[0]["thumbnail"] == "previews/FakePack/SM_Prop_Sign_Police_01.png"
