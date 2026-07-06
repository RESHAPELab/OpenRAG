from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg
from psycopg.rows import dict_row


@dataclass
class DiscordInteractionLogEntry:
    rag_name: str
    question: str
    rag_answer: Optional[str] = None
    rag_context: Optional[str] = None
    llm_answer: Optional[str] = None
    discord_user_id: Optional[str] = None
    discord_channel_id: Optional[str] = None
    discord_thread_id: Optional[str] = None
    discord_message_id: Optional[str] = None
    bot_reply_message_id: Optional[str] = None
    candidate_a_answer: Optional[str] = None
    candidate_b_answer: Optional[str] = None
    feedback_selected_candidate: Optional[str] = None
    feedback_thumbs_up: Optional[bool] = None
    feedback_timestamp: Optional[datetime] = None


class DiscordInteractionLogger:
    """PostgreSQL-backed logger for Discord interactions."""

    def __init__(self, dsn: str, *, rag_name: str) -> None:
        self._dsn = dsn
        self._rag_name = rag_name
        # Use a simple connection-per-operation pattern; pool can be added later if needed.
        self._ensure_schema()

    def _get_conn(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._dsn)

    def _ensure_schema(self) -> None:
        with self._get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS discord_interaction_logs (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    rag_name TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'discord',
                    discord_user_id TEXT NULL,
                    discord_channel_id TEXT NULL,
                    discord_thread_id TEXT NULL,
                    discord_message_id TEXT NULL,
                    bot_reply_message_id TEXT NULL,
                    question TEXT NOT NULL,
                    rag_answer TEXT NULL,
                    rag_context TEXT NULL,
                    llm_answer TEXT NULL,
                    candidate_a_answer TEXT NULL,
                    candidate_b_answer TEXT NULL,
                    feedback_selected_candidate TEXT NULL,
                    feedback_thumbs_up BOOLEAN NULL,
                    feedback_timestamp TIMESTAMPTZ NULL
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_discord_logs_created_at ON discord_interaction_logs(created_at);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_discord_logs_rag_name ON discord_interaction_logs(rag_name);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_discord_logs_user_id ON discord_interaction_logs(discord_user_id);"
            )
            # Add bot_reply_message_id column if it doesn't exist yet (migration).
            cur.execute(
                """
                ALTER TABLE discord_interaction_logs
                ADD COLUMN IF NOT EXISTS bot_reply_message_id TEXT NULL;
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_discord_logs_bot_reply_msg ON discord_interaction_logs(bot_reply_message_id);"
            )
            conn.commit()

    def log_interaction(
        self,
        *,
        question: str,
        rag_answer: Optional[str],
        rag_context: Optional[str],
        llm_answer: Optional[str],
        discord_user_id: Optional[str],
        discord_channel_id: Optional[str],
        discord_thread_id: Optional[str],
        discord_message_id: Optional[str],
        bot_reply_message_id: Optional[str] = None,
        candidate_a_answer: Optional[str] = None,
        candidate_b_answer: Optional[str] = None,
    ) -> int:
        """Insert a single interaction log entry and return its row id."""
        with self._get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO discord_interaction_logs (
                    rag_name,
                    question,
                    rag_answer,
                    rag_context,
                    llm_answer,
                    discord_user_id,
                    discord_channel_id,
                    discord_thread_id,
                    discord_message_id,
                    bot_reply_message_id,
                    candidate_a_answer,
                    candidate_b_answer
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id;
                """,
                (
                    self._rag_name,
                    question,
                    rag_answer,
                    rag_context,
                    llm_answer,
                    discord_user_id,
                    discord_channel_id,
                    discord_thread_id,
                    discord_message_id,
                    bot_reply_message_id,
                    candidate_a_answer,
                    candidate_b_answer,
                ),
            )
            row_id = cur.fetchone()[0]
            conn.commit()
            return int(row_id)

    def log_entry(self, entry: DiscordInteractionLogEntry) -> int:
        return self.log_interaction(
            question=entry.question,
            rag_answer=entry.rag_answer,
            rag_context=entry.rag_context,
            llm_answer=entry.llm_answer,
            discord_user_id=entry.discord_user_id,
            discord_channel_id=entry.discord_channel_id,
            discord_thread_id=entry.discord_thread_id,
            discord_message_id=entry.discord_message_id,
            bot_reply_message_id=entry.bot_reply_message_id,
            candidate_a_answer=entry.candidate_a_answer,
            candidate_b_answer=entry.candidate_b_answer,
        )

    def log_feedback(
        self,
        *,
        bot_reply_message_id: str,
        thumbs_up: bool | None,
    ) -> bool:
        """Update feedback fields for a log row matched by the bot's reply message ID.

        Returns True if a row was updated, otherwise False.
        """
        with self._get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE discord_interaction_logs
                SET feedback_thumbs_up = %s,
                    feedback_timestamp = CASE
                        WHEN %s IS NULL THEN NULL
                        ELSE NOW()
                    END
                WHERE bot_reply_message_id = %s
                  AND rag_name = %s
                RETURNING id;
                """,
                (
                    thumbs_up,
                    thumbs_up,
                    bot_reply_message_id,
                    self._rag_name,
                ),
            )
            updated = cur.fetchone() is not None
            conn.commit()
            return updated

    def export_csv(
        self,
        output_path: str | Path,
        *,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        rag_name: Optional[str] = None,
    ) -> None:
        """Export all matching logs to a CSV file with all fields."""
        import csv

        conditions: list[str] = []
        params: list[Any] = []

        if from_ts is not None:
            conditions.append("created_at >= %s")
            params.append(from_ts)
        if to_ts is not None:
            conditions.append("created_at <= %s")
            params.append(to_ts)
        if rag_name is not None:
            conditions.append("rag_name = %s")
            params.append(rag_name)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT
                id,
                created_at,
                rag_name,
                source,
                discord_user_id,
                discord_channel_id,
                discord_thread_id,
                discord_message_id,
                question,
                rag_answer,
                rag_context,
                llm_answer,
                candidate_a_answer,
                candidate_b_answer,
                feedback_selected_candidate,
                feedback_thumbs_up,
                feedback_timestamp
            FROM discord_interaction_logs
            {where_clause}
            ORDER BY created_at ASC;
        """

        out_path = Path(output_path)

        with self._get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            rows: Iterable[dict[str, Any]] = cur.fetchall()

        rows_list = list(rows)
        if not rows_list:
            out_path.write_text("", encoding="utf-8")
            return

        fieldnames = list(rows_list[0].keys())
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_list)

