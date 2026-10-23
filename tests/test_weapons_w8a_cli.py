"""W8a: the CLI surface and the default export (docs/weapon_attachments.md 3.6, 3.7, D-10).

``attach-preview`` is registered (built in W8d, tested in test_weapons_w8d_preview.py; ``attach-eval`` was built in W8c and is
tested in test_weapons_w8c_eval.py). The export flags are registered, and ``--attachments`` is honoured from W8d (see
test_weapons_w8d_export.py). A default export of part records carries no ``attachment`` key.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_here = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8a_attach", _here / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)
_spec2 = importlib.util.spec_from_file_location("review_helpers", _here / "review_helpers.py")
H = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(H)

from synty_inventory.cli import build_parser  # noqa: E402
from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import guards  # noqa: E402
from synty_inventory.weapons.export import check_snapshot, export_snapshot  # noqa: E402

SCOPE = f"{A.PACK}/SM_Wep_Rifle_Scope_01"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    for key in H.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def cfg(tmp_path):
    return H.write_config(tmp_path, tmp_path / "catalogs")


@pytest.mark.parametrize("argv", [
    ["weapons", "attach-preview"],
    ["weapons", "attach-preview", "--out", "o", "--ids", "A/b", "--limit", "5", "--plan"],
])
def test_attach_preview_is_registered_and_wants_a_built_directory(cfg, capsys, monkeypatch, argv):
    monkeypatch.setattr(export_mod, "_repo_root", lambda: None)  # pytest's tmp dirs sit inside this checkout
    code, out = H.run(cfg, capsys, argv)
    assert code == 2 and out["ok"] is False  # exit 2 (bad input), not the argparse usage error
    assert "no weapon directory" in out["error"] and "hint" not in out  # a real verb now, not the "not built" stub


def test_the_export_attachment_flags_parse_with_their_defaults():
    base = ["weapons", "export", "--game", "g", "--packs", "A", "--out", "o.json"]
    args = build_parser().parse_args(base)
    assert args.attachments is False and args.min_compat_tier == "same_pack_fit" and args.keep_foreign_hosts is False
    args = build_parser().parse_args(base + ["--attachments", "--min-compat-tier", "twin", "--keep-foreign-hosts"])
    assert args.attachments is True and args.min_compat_tier == "twin" and args.keep_foreign_hosts is True
    with pytest.raises(SystemExit):
        build_parser().parse_args(base + ["--min-compat-tier", "bogus"])


def test_a_default_export_of_part_records_has_no_attachment_key_and_passes_the_snapshot_check(tmp_path):
    directory, *_ = A.build(tmp_path)
    parts = [w for w in directory["weapons"] if w["role"] == "part"]
    assert any(w["attachment"] for w in parts)  # the directory itself has them
    snap = export_snapshot(directory, game="g", pack_ids=None, ids=None, roles={"whole", "part"}, engines={"all"},
                           frame="item", profile="private", pack_meta={}, rules_digest=directory["rules_digest"],
                           overrides_digest=directory["overrides_digest"])
    assert {w["role"] for w in snap["weapons"]} == {"whole", "part"}
    assert all("attachment" not in w for w in snap["weapons"])
    assert check_snapshot(json.loads(json.dumps(snap))) == []
    assert snap["generated_from"]["rules_digest"] == "7b9829af37328fe7"
    public = export_snapshot(directory, game="g", pack_ids=None, ids=None, roles={"whole", "part"}, engines={"all"},
                             frame="item", profile="public", pack_meta={}, rules_digest=directory["rules_digest"],
                             overrides_digest=directory["overrides_digest"])
    assert all("attachment" not in w for w in public["weapons"])
