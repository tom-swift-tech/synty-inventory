"""Derived SQLite + FTS5 search index (roadmap Phase 2).

The JSON catalogs remain the source of record. ``search.db`` is a derived,
gitignored artifact rebuilt deterministically by ``rebuild_index`` (which
every scan/enrich path already calls) or by ``scan --index``. It is
invisible to agents: ``query.search_assets`` uses it as a fast
candidate-retrieval layer when it is present and fresh, and silently falls
back to the linear catalog walk when it is absent, stale, or unusable.
Ranking stays with ``query._score`` either way; the DB path adds a capped
BM25 bonus for prose relevance. Gauntlet's ``search_db`` gate pins DB row
counts against the catalogs so a stale or partial build cannot lie.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DB_NAME = "search.db"
SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE assets(
  id TEXT NOT NULL,
  pack TEXT NOT NULL,
  type TEXT,
  role TEXT,
  placeable INTEGER NOT NULL,
  measured INTEGER NOT NULL,
  record TEXT NOT NULL
);
CREATE INDEX idx_assets_pack ON assets(pack);
CREATE INDEX idx_assets_id ON assets(id);
CREATE VIRTUAL TABLE fts USING fts5(
  name, description, tags, extra, tokenize='porter unicode61'
);
CREATE TABLE sockets(
  asset_rowid INTEGER NOT NULL,
  role TEXT,
  axis TEXT,
  source TEXT
);
CREATE TABLE kits(
  pack TEXT NOT NULL,
  family TEXT NOT NULL,
  role TEXT,
  asset_id TEXT NOT NULL
);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""


def db_path(catalogs_dir: Path) -> Path:
    return catalogs_dir / DB_NAME


def _catalog_files(catalogs_dir: Path) -> list[Path]:
    """Pack catalogs only — same filter as ``load_all_catalogs``."""
    if not catalogs_dir.is_dir():
        return []
    return [
        p
        for p in sorted(catalogs_dir.glob("*.json"))
        if p.name != "index.json" and not p.name.startswith("_")
    ]


def is_fresh(catalogs_dir: Path) -> bool:
    """True when the DB exists and is at least as new as every pack catalog.

    A hand-edited or re-scanned catalog makes the DB stale; search then falls
    back to the linear walk (correct over fast) until the next rebuild.
    """
    db = db_path(catalogs_dir)
    if not db.is_file():
        return False
    files = _catalog_files(catalogs_dir)
    if not files:
        return False
    try:
        db_m = db.stat().st_mtime
        return all(p.stat().st_mtime <= db_m for p in files)
    except OSError:
        return False


def _fts_extra(asset: dict) -> str:
    """Prose-adjacent structure not covered by name/description/tags —
    mirrors ``query._haystack`` so the FTS candidate set is a superset of
    what the linear scorer can reward."""
    place = asset.get("placement") or {}
    module = asset.get("module") or {}
    part = asset.get("part") or {}
    bits = [
        asset.get("id") or "",
        asset.get("type") or "",
        asset.get("semantic_role") or "",
        asset.get("semantic_detail") or "",
        asset.get("ai_notes") or "",
        " ".join(asset.get("category") or []),
        place.get("mount") or "",
        place.get("attachment") or "",
        place.get("height") or "",
        " ".join(place.get("constraints") or []),
        " ".join(place.get("preferred_contexts") or []),
        module.get("family") or "",
        module.get("role") or "",
        part.get("class") or "",
    ]
    return " ".join(b for b in bits if b)


def build(catalogs_dir: Path) -> Path | None:
    """Deterministic full rebuild: tmp file, then atomic replace.

    Returns the DB path, or None when SQLite lacks FTS5 (search then uses
    the linear fallback forever — degraded speed, identical results).
    """
    from .catalog import load_all_catalogs  # local: catalog imports us back

    docs = sorted(load_all_catalogs(catalogs_dir), key=lambda d: d.get("pack_id") or "")
    dest = db_path(catalogs_dir)
    tmp = dest.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        try:
            con.executescript(_DDL)
        except sqlite3.OperationalError as exc:  # no FTS5 in this build
            con.close()
            tmp.unlink(missing_ok=True)
            import sys

            print(f"warning: search.db not built ({exc}); search uses linear fallback", file=sys.stderr)
            return None
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        rowid = 0
        for doc in docs:
            pid = doc.get("pack_id") or ""
            for asset in doc.get("assets") or []:
                rowid += 1
                part = asset.get("part") or {}
                module = asset.get("module") or {}
                con.execute(
                    "INSERT INTO assets(rowid, id, pack, type, role, placeable, measured, record)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (
                        rowid,
                        asset.get("id") or "",
                        pid,
                        asset.get("type"),
                        asset.get("semantic_role"),
                        0 if asset.get("placeable") is False else 1,
                        1 if (asset.get("bounds") or {}).get("source") == "measured" else 0,
                        json.dumps(asset, ensure_ascii=False, sort_keys=True),
                    ),
                )
                con.execute(
                    "INSERT INTO fts(rowid, name, description, tags, extra) VALUES(?,?,?,?,?)",
                    (
                        rowid,
                        asset.get("name") or "",
                        asset.get("description") or "",
                        " ".join(asset.get("tags") or []),
                        _fts_extra(asset),
                    ),
                )
                for face in part.get("sockets") or []:
                    if isinstance(face, dict):
                        con.execute(
                            "INSERT INTO sockets(asset_rowid, role, axis, source) VALUES(?,?,?,?)",
                            (rowid, face.get("role"), face.get("axis"), face.get("source")),
                        )
                if module.get("family"):
                    con.execute(
                        "INSERT INTO kits(pack, family, role, asset_id) VALUES(?,?,?,?)",
                        (pid, module["family"], module.get("role"), asset.get("id") or ""),
                    )
        con.execute(
            "INSERT INTO meta(key, value) VALUES('packs', ?)",
            (json.dumps([d.get("pack_id") for d in docs]),),
        )
        con.commit()
    finally:
        con.close()
    os.replace(tmp, dest)
    return dest


def _connect_ro(catalogs_dir: Path) -> sqlite3.Connection | None:
    try:
        con = sqlite3.connect(f"file:{db_path(catalogs_dir).as_posix()}?mode=ro", uri=True)
        (ver,) = con.execute("PRAGMA user_version").fetchone()
        if ver != SCHEMA_VERSION:
            con.close()
            return None
        return con
    except sqlite3.Error:
        return None


def candidates(
    catalogs_dir: Path, query: str
) -> list[tuple[str, dict, float]] | None:
    """(pack_id, asset, bm25_bonus) triples for ranking, or None when the
    DB is absent/stale/unusable — the caller then walks the catalogs.

    Non-empty query: prefix-OR token MATCH (porter-stemmed), so the
    candidate set covers everything the linear scorer could reward, plus
    stemmed prose hits it could not. Empty query: every row (filters-only
    search). BM25 bonus is capped so ``query._score`` stays dominant and
    the ``search_police`` gate semantics cannot flip.
    """
    from .query import tokenize  # local: query imports us back

    if not is_fresh(catalogs_dir):
        return None
    con = _connect_ro(catalogs_dir)
    if con is None:
        return None
    try:
        tokens = tokenize(query)
        out: list[tuple[str, dict, float]] = []
        if tokens:
            match = " OR ".join(f'"{t}"*' for t in tokens)
            rows = con.execute(
                "SELECT a.pack, a.record, bm25(fts) FROM fts"
                " JOIN assets a ON a.rowid = fts.rowid"
                " WHERE fts MATCH ? ORDER BY a.pack, a.id",
                (match,),
            ).fetchall()
            for pack, record, rank in rows:
                bonus = min(8.0, max(0.0, -float(rank)))
                out.append((pack, json.loads(record), bonus))
        else:
            rows = con.execute(
                "SELECT pack, record FROM assets ORDER BY pack, id"
            ).fetchall()
            out = [(pack, json.loads(record), 0.0) for pack, record in rows]
        return out
    except sqlite3.Error:
        return None
    finally:
        con.close()


def row_counts(catalogs_dir: Path) -> dict | None:
    """Counts for the gauntlet ``search_db`` gate; None if unreadable."""
    con = _connect_ro(catalogs_dir)
    if con is None:
        return None
    try:
        (total,) = con.execute("SELECT COUNT(*) FROM assets").fetchone()
        (placeable,) = con.execute("SELECT COUNT(*) FROM assets WHERE placeable = 1").fetchone()
        (fts,) = con.execute("SELECT COUNT(*) FROM fts").fetchone()
        return {"assets": total, "placeable": placeable, "fts": fts}
    except sqlite3.Error:
        return None
    finally:
        con.close()
