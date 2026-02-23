from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass
class EvaluationLogEntry:
    timestamp: Optional[str] = None
    category: Optional[str] = None
    model_name: Optional[str] = None
    question: str | None = None
    rag_context: Optional[str] = None
    rag_answer: Optional[str] = None
    llm_answer: Optional[str] = None


class EvaluationLogger:
    """SQLite-backed logger for evaluation runs."""

    def __init__(self, db_path: str | Path = "evaluation_logs.db") -> None:
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                category TEXT,
                model_name TEXT,
                question TEXT NOT NULL,
                rag_context TEXT,
                rag_answer TEXT,
                llm_answer TEXT
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_category ON evaluation_logs(category);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_model ON evaluation_logs(model_name);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON evaluation_logs(timestamp);"
        )
        self._conn.commit()

    def log(
        self,
        timestamp: Optional[str],
        category: Optional[str],
        model_name: Optional[str],
        question: str,
        rag_context: Optional[str],
        rag_answer: Optional[str],
        llm_answer: Optional[str],
    ) -> int:
        """Insert a single log entry and return its row id."""
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO evaluation_logs (
                timestamp, category, model_name, question,
                rag_context, rag_answer, llm_answer
            ) VALUES (
                COALESCE(?, datetime('now')), ?, ?, ?, ?, ?, ?
            );
            """,
            (
                timestamp,
                category,
                model_name,
                question,
                rag_context,
                rag_answer,
                llm_answer,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def log_entry(self, entry: EvaluationLogEntry) -> int:
        """Insert a single EvaluationLogEntry."""
        return self.log(
            timestamp=entry.timestamp,
            category=entry.category,
            model_name=entry.model_name,
            question=entry.question or "",
            rag_context=entry.rag_context,
            rag_answer=entry.rag_answer,
            llm_answer=entry.llm_answer,
        )

    def log_batch(self, entries: Iterable[EvaluationLogEntry]) -> list[int]:
        """Insert multiple entries in one transaction."""
        rows: list[tuple[Any, ...]] = []
        for e in entries:
            rows.append(
                (
                    e.timestamp,
                    e.category,
                    e.model_name,
                    e.question or "",
                    e.rag_context,
                    e.rag_answer,
                    e.llm_answer,
                )
            )

        cur = self._conn.cursor()
        cur.executemany(
            """
            INSERT INTO evaluation_logs (
                timestamp, category, model_name, question,
                rag_context, rag_answer, llm_answer
            ) VALUES (
                COALESCE(?, datetime('now')), ?, ?, ?, ?, ?, ?
            );
            """,
            rows,
        )
        self._conn.commit()
        start_id = cur.lastrowid - len(rows) + 1 if rows else 0
        return [start_id + i for i in range(len(rows))] if rows else []

    def query(
        self,
        *,
        category: Optional[str] = None,
        model_name: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Retrieve logged entries with optional filtering."""
        conditions: list[str] = []
        params: list[Any] = []

        if category is not None:
            conditions.append("category = ?")
            params.append(category)
        if model_name is not None:
            conditions.append("model_name = ?")
            params.append(model_name)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(limit)

        cur = self._conn.cursor()
        cur.execute(
            f"""
            SELECT
                id,
                timestamp,
                category,
                model_name,
                question,
                rag_context,
                rag_answer,
                llm_answer
            FROM evaluation_logs
            {where_clause}
            ORDER BY timestamp DESC
            {limit_clause};
            """,
            params,
        )
        columns = [d[0] for d in cur.description or []]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def export_csv(
        self,
        output_path: str | Path,
        *,
        category: Optional[str] = None,
        model_name: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> None:
        """Export logs to a CSV file for analysis."""
        rows = self.query(category=category, model_name=model_name, limit=limit)
        if not rows:
            Path(output_path).write_text("", encoding="utf-8")
            return

        fieldnames = list(rows[0].keys())
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def close(self) -> None:
        if getattr(self, "_conn", None) is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> "EvaluationLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

