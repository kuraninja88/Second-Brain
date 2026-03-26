"""
SQLite metadata store.

Two tables:
  papers     — one row per paper from the Literature Review Excel matrix
  index_log  — tracks which files have been indexed (hash-based change detection)
"""
import sqlite3
from pathlib import Path
from typing import Optional
import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                author        TEXT,
                year          TEXT,
                reference     TEXT,
                theme         TEXT,
                rq_focus      TEXT,
                theory        TEXT,
                data_sample   TEXT,
                variables     TEXT,
                methodology   TEXT,
                key_findings  TEXT,
                novelty       TEXT,
                limitations   TEXT,
                notes         TEXT,
                relevant_quote TEXT,
                citation      TEXT,
                source_file   TEXT
            );

            CREATE TABLE IF NOT EXISTS index_log (
                file_path    TEXT PRIMARY KEY,
                file_hash    TEXT NOT NULL,
                last_indexed TEXT NOT NULL,
                chunk_count  INTEGER DEFAULT 0,
                source_type  TEXT,
                quality      TEXT DEFAULT 'ok'
            );
        """)


# ─── Papers table ─────────────────────────────────────────────────────────────

def upsert_paper(row: dict):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO papers
                (author, year, reference, theme, rq_focus, theory, data_sample,
                 variables, methodology, key_findings, novelty, limitations,
                 notes, relevant_quote, citation, source_file)
            VALUES
                (:author, :year, :reference, :theme, :rq_focus, :theory,
                 :data_sample, :variables, :methodology, :key_findings,
                 :novelty, :limitations, :notes, :relevant_quote,
                 :citation, :source_file)
        """, row)


def clear_papers_from_source(source_file: str):
    with _conn() as conn:
        conn.execute("DELETE FROM papers WHERE source_file = ?", (source_file,))


def delete_papers_by_author_year(author: str, year: str):
    """Delete all papers matching first author word + year — used to clear Excel duplicates before re-extraction."""
    if not author:
        return
    first_word = author.split()[0].strip(".,;:")
    if not first_word:
        return
    with _conn() as conn:
        conn.execute(
            "DELETE FROM papers WHERE author LIKE ? AND (? = '' OR year = ?)",
            (f"%{first_word}%", year, year),
        )


def get_all_themes() -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT theme FROM papers WHERE theme IS NOT NULL AND theme != '' ORDER BY theme"
        ).fetchall()
    return [r["theme"] for r in rows]


def get_papers_by_theme(theme: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM papers WHERE theme LIKE ?", (f"%{theme}%",)
        ).fetchall()
    return [dict(r) for r in rows]


def search_papers(query: str) -> list[dict]:
    """Text search across all paper fields — author, title, theme, methodology, findings, etc."""
    like = f"%{query}%"
    with _conn() as conn:
        rows = conn.execute("""
            SELECT * FROM papers
            WHERE author     LIKE ? OR reference   LIKE ? OR theme      LIKE ?
               OR rq_focus   LIKE ? OR theory      LIKE ? OR data_sample LIKE ?
               OR variables  LIKE ? OR methodology LIKE ? OR key_findings LIKE ?
               OR novelty    LIKE ? OR limitations LIKE ? OR notes       LIKE ?
            LIMIT 50
        """, (like,) * 12).fetchall()
    return [dict(r) for r in rows]


def get_paper_count() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]


def get_all_papers() -> list[dict]:
    """Return all papers from the matrix, ordered by author then year."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM papers ORDER BY author, year"
        ).fetchall()
    return [dict(r) for r in rows]


def paper_exists_for(author: str, year: str) -> bool:
    """
    Return True if the papers table already has a row matching this author + year.
    Used to avoid duplicating Excel-sourced entries with LLM-extracted ones.
    """
    if not author:
        return False
    first_word = author.split()[0].strip(".,;:")
    if not first_word:
        return False
    with _conn() as conn:
        row = conn.execute("""
            SELECT id FROM papers
            WHERE author LIKE ?
              AND (? = '' OR year = ?)
            LIMIT 1
        """, (f"%{first_word}%", year, year)).fetchone()
    return row is not None


def find_pdf_for_paper(author: str, year: str) -> Optional[str]:
    """
    Try to find an indexed PDF whose filename matches this paper's author & year.
    Returns the file_path string, or None if not found.
    """
    if not author:
        return None
    # Use first word of author string (typically last name)
    first_word = author.split()[0].strip(".,;:")
    if not first_word:
        return None
    like_author = f"%{first_word}%"
    like_year   = f"%{year}%" if year else "%"
    with _conn() as conn:
        row = conn.execute("""
            SELECT file_path FROM index_log
            WHERE source_type = 'pdf'
              AND file_path LIKE ?
              AND file_path LIKE ?
            LIMIT 1
        """, (like_author, like_year)).fetchone()
    return row["file_path"] if row else None


# ─── Index log table ──────────────────────────────────────────────────────────

def get_file_hash(file_path: str) -> Optional[str]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT file_hash FROM index_log WHERE file_path = ?", (file_path,)
        ).fetchone()
    return row["file_hash"] if row else None


def update_index_log(file_path: str, file_hash: str, chunk_count: int,
                     source_type: str, quality: str = "ok"):
    from datetime import datetime
    with _conn() as conn:
        conn.execute("""
            INSERT INTO index_log (file_path, file_hash, last_indexed, chunk_count, source_type, quality)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash    = excluded.file_hash,
                last_indexed = excluded.last_indexed,
                chunk_count  = excluded.chunk_count,
                source_type  = excluded.source_type,
                quality      = excluded.quality
        """, (file_path, file_hash, datetime.now().isoformat(), chunk_count, source_type, quality))


def get_all_indexed_files() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM index_log ORDER BY last_indexed DESC").fetchall()
    return [dict(r) for r in rows]


def get_indexed_file_count() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM index_log").fetchone()[0]


def get_last_indexed() -> Optional[str]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT MAX(last_indexed) as ts FROM index_log"
        ).fetchone()
    return row["ts"] if row else None


def remove_from_index(file_path: str):
    with _conn() as conn:
        conn.execute("DELETE FROM index_log WHERE file_path = ?", (file_path,))
