"""Database helpers for the Responses DB Viewer.

Supports two backends:
  1. SQLite  -- any table (file-based, read-only)
  2. PostgreSQL -- any table (via psycopg DSN, read-only queries)

All access is read-only.  The module builds parameterised queries and
never mutates the underlying database.
"""

from __future__ import annotations

import io
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Well-known table schemas for smart defaults (dropdowns, timestamp column).
# Any table not listed here still works -- columns are auto-detected.
KNOWN_TABLES: dict[str, dict[str, Any]] = {
    "evaluation_logs": {
        "timestamp_col": "timestamp",
        "filterable_dropdowns": ["category", "model_name"],
    },
    "discord_interaction_logs": {
        "timestamp_col": "created_at",
        "filterable_dropdowns": ["rag_name", "source", "discord_user_id"],
    },
}


# ---------------------------------------------------------------------------
# Unified DB wrapper
# ---------------------------------------------------------------------------

class DBConn:
    """Thin wrapper that normalises SQLite and psycopg connections."""

    def __init__(self, raw_conn: Any, backend: str, table: str, columns: list[str]) -> None:
        self.raw = raw_conn
        self.backend = backend
        self.table = table
        self.columns = columns
        self.ph = "?" if backend == "sqlite" else "%s"

        known = KNOWN_TABLES.get(table, {})
        self.timestamp_col = known.get("timestamp_col") or _guess_timestamp_col(columns)
        self.filterable_dropdowns: list[str] = [
            c for c in known.get("filterable_dropdowns", []) if c in columns
        ]
        self.sortable: list[str] = [
            c for c in (["id", self.timestamp_col] + columns) if c in columns
        ]
        # deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for c in self.sortable:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        self.sortable = deduped

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if self.backend == "sqlite":
            cur = self.raw.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        else:
            from psycopg.rows import dict_row
            with self.raw.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                if cur.description is None:
                    return []
                return list(cur.fetchall())

    def execute_scalar(self, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> Any:
        if self.backend == "sqlite":
            return self.raw.execute(sql, params).fetchone()[0]
        else:
            with self.raw.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()[0]

    def close(self) -> None:
        self.raw.close()


def _guess_timestamp_col(columns: list[str]) -> str:
    """Heuristic: pick the first column that looks like a timestamp."""
    for candidate in ("created_at", "timestamp", "updated_at", "date", "ts"):
        if candidate in columns:
            return candidate
    return columns[1] if len(columns) > 1 else columns[0]


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def list_sqlite_tables(db_path: str | Path) -> list[str]:
    p = Path(db_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Database file not found: {p}")
    uri = f"file:{p.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    return tables


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def connect_sqlite(db_path: str | Path, table: str) -> DBConn:
    """Open a SQLite DB read-only for a specific table."""
    p = Path(db_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Database file not found: {p}")
    uri = f"file:{p.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    columns = _sqlite_columns(conn, table)
    if not columns:
        conn.close()
        raise ValueError(f"Table '{table}' not found or has no columns.")
    return DBConn(conn, "sqlite", table, columns)


def list_pg_tables(dsn: str) -> list[str]:
    import psycopg
    conn = psycopg.connect(dsn, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        tables = [row[0] for row in cur.fetchall()]
    conn.close()
    return tables


def _pg_columns(conn: Any, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def connect_postgresql(dsn: str, table: str) -> DBConn:
    """Open a PostgreSQL connection for a specific table."""
    import psycopg
    conn = psycopg.connect(dsn, autocommit=True)
    columns = _pg_columns(conn, table)
    if not columns:
        conn.close()
        raise ValueError(f"Table '{table}' not found or has no columns.")
    return DBConn(conn, "postgresql", table, columns)


# ---------------------------------------------------------------------------
# Dropdown helpers
# ---------------------------------------------------------------------------

def get_distinct_values(db: DBConn, column: str) -> list[str]:
    """Return sorted distinct non-NULL values for a column."""
    if column not in db.columns:
        raise ValueError(f"Invalid column '{column}' for table {db.table}")
    rows = db.execute(
        f"SELECT DISTINCT {column} FROM {db.table} "
        f"WHERE {column} IS NOT NULL ORDER BY {column}"
    )
    return [str(r[column]) for r in rows]


# ---------------------------------------------------------------------------
# Filter dataclass
# ---------------------------------------------------------------------------

@dataclass
class Filters:
    ts_from: Optional[str] = None
    ts_to: Optional[str] = None
    search_text: Optional[str] = None
    search_columns: list[str] | None = None
    has_rag: Optional[bool] = None
    has_llm: Optional[bool] = None
    missing_either: bool = False
    min_rag_len: Optional[int] = None
    min_llm_len: Optional[int] = None
    id_min: Optional[int] = None
    id_max: Optional[int] = None
    sort_col: str = ""
    sort_dir: str = "DESC"
    page: int = 1
    page_size: int = 50
    dropdown_filters: dict[str, str | None] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.dropdown_filters is None:
            self.dropdown_filters = {}


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def _where_clause(db: DBConn, f: Filters) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    ph = db.ph
    ts_col = db.timestamp_col

    for col, val in (f.dropdown_filters or {}).items():
        if val and col in db.columns:
            conditions.append(f"{col} = {ph}")
            params.append(val)

    if f.ts_from and ts_col:
        conditions.append(f"{ts_col} >= {ph}")
        params.append(f.ts_from)

    if f.ts_to and ts_col:
        conditions.append(f"{ts_col} <= {ph}")
        params.append(f.ts_to)

    if f.search_text:
        like = f"%{f.search_text}%"
        text_cols = f.search_columns or ["question", "rag_context", "rag_answer", "llm_answer"]
        valid_cols = [c for c in text_cols if c in db.columns]
        if valid_cols:
            conditions.append("(" + " OR ".join(f"{c} LIKE {ph}" for c in valid_cols) + ")")
            params.extend([like] * len(valid_cols))

    if f.has_rag is True and "rag_answer" in db.columns:
        conditions.append("rag_answer IS NOT NULL AND rag_answer != ''")
    elif f.has_rag is False and "rag_answer" in db.columns:
        conditions.append("(rag_answer IS NULL OR rag_answer = '')")

    if f.has_llm is True and "llm_answer" in db.columns:
        conditions.append("llm_answer IS NOT NULL AND llm_answer != ''")
    elif f.has_llm is False and "llm_answer" in db.columns:
        conditions.append("(llm_answer IS NULL OR llm_answer = '')")

    if f.missing_either:
        parts = []
        if "rag_answer" in db.columns:
            parts.append("(rag_answer IS NULL OR rag_answer = '')")
        if "llm_answer" in db.columns:
            parts.append("(llm_answer IS NULL OR llm_answer = '')")
        if parts:
            conditions.append("(" + " OR ".join(parts) + ")")

    if f.min_rag_len is not None and f.min_rag_len > 0 and "rag_answer" in db.columns:
        conditions.append(f"LENGTH(COALESCE(rag_answer, '')) >= {ph}")
        params.append(f.min_rag_len)

    if f.min_llm_len is not None and f.min_llm_len > 0 and "llm_answer" in db.columns:
        conditions.append(f"LENGTH(COALESCE(llm_answer, '')) >= {ph}")
        params.append(f.min_llm_len)

    if f.id_min is not None and "id" in db.columns:
        conditions.append(f"id >= {ph}")
        params.append(f.id_min)

    if f.id_max is not None and "id" in db.columns:
        conditions.append(f"id <= {ph}")
        params.append(f.id_max)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)
    return where, params


def _resolve_sort(db: DBConn, f: Filters) -> str:
    col = f.sort_col if f.sort_col in db.columns else db.timestamp_col
    if col not in db.columns:
        col = db.columns[0]
    direction = "ASC" if f.sort_dir.upper() == "ASC" else "DESC"
    return f"{col} {direction}"


def fetch_rows(db: DBConn, f: Filters) -> pd.DataFrame:
    where, params = _where_clause(db, f)
    order = _resolve_sort(db, f)
    ph = db.ph
    offset = (f.page - 1) * f.page_size

    sql = (
        f"SELECT * FROM {db.table} {where} "
        f"ORDER BY {order} "
        f"LIMIT {ph} OFFSET {ph}"
    )
    params.extend([f.page_size, offset])
    rows = db.execute(sql, params)
    if not rows:
        return pd.DataFrame(columns=db.columns)
    return pd.DataFrame(rows)


def fetch_count(db: DBConn, f: Filters) -> int:
    where, params = _where_clause(db, f)
    sql = f"SELECT COUNT(*) AS cnt FROM {db.table} {where}"
    return db.execute_scalar(sql, params)


def fetch_row_by_id(db: DBConn, row_id: int) -> dict[str, Any] | None:
    ph = db.ph
    pk = "id" if "id" in db.columns else db.columns[0]
    rows = db.execute(
        f"SELECT * FROM {db.table} WHERE {pk} = {ph}", (row_id,)
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Read-only SQL console
# ---------------------------------------------------------------------------

_FORBIDDEN_PREFIXES = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "REPLACE", "ATTACH", "DETACH", "REINDEX", "VACUUM", "PRAGMA",
    "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE", "GRANT",
    "TRUNCATE",
)


def validate_readonly(sql: str) -> str | None:
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "Empty query."
    first_word = stripped.split()[0].upper()
    if first_word == "EXPLAIN":
        parts = stripped.split()
        if len(parts) < 2:
            return "Incomplete EXPLAIN statement."
        rest = " ".join(parts[1:]).strip()
        if rest.upper().startswith("QUERY PLAN"):
            rest = rest[len("QUERY PLAN"):].strip()
        if rest.upper().startswith("ANALYZE"):
            rest = rest[len("ANALYZE"):].strip()
        return validate_readonly(rest)
    if first_word not in ("SELECT", "WITH"):
        return f"Only SELECT queries are allowed (got {first_word})."
    upper_words = set(stripped.upper().split())
    for kw in _FORBIDDEN_PREFIXES:
        if kw in upper_words:
            return f"Statement contains forbidden keyword: {kw}"
    return None


def run_readonly_sql(db: DBConn, sql: str) -> pd.DataFrame:
    err = validate_readonly(sql)
    if err:
        raise PermissionError(err)
    rows = db.execute(sql)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def to_jsonl_bytes(df: pd.DataFrame) -> bytes:
    lines: list[str] = []
    for _, row in df.iterrows():
        lines.append(json.dumps(row.to_dict(), ensure_ascii=False, default=str))
    return "\n".join(lines).encode("utf-8")
