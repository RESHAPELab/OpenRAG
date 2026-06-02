from __future__ import annotations

from pathlib import Path
from typing import Any
import os

import pytest

from src.logging.discord_logger import DiscordInteractionLogger


@pytest.fixture
def pg_dsn(tmp_path: Path) -> str:
    # This test assumes a running Postgres instance is available via DSN.
    # Prefer STORAGE_LOGS_URL if set; fall back to local default.
    return os.getenv("STORAGE_LOGS_URL", "postgresql://root:example@localhost:5432/postgres")


def test_discord_logger_schema_and_insert(pg_dsn: str) -> None:
    logger = DiscordInteractionLogger(dsn=pg_dsn, rag_name="test-rag")

    row_id = logger.log_interaction(
        question="What is DocGPT?",
        rag_answer="DocGPT is a documentation assistant.",
        rag_context='[{"source": "doc.md", "snippet": "DocGPT..."}]',
        llm_answer="Generic answer",
        discord_user_id="user123",
        discord_channel_id="channel123",
        discord_thread_id="thread123",
        discord_message_id="message123",
    )
    assert isinstance(row_id, int)


def test_discord_logger_export_csv(pg_dsn: str, tmp_path: Path) -> None:
    logger = DiscordInteractionLogger(dsn=pg_dsn, rag_name="test-rag")

    # Ensure at least one row exists
    logger.log_interaction(
        question="Q?",
        rag_answer="A",
        rag_context=None,
        llm_answer=None,
        discord_user_id=None,
        discord_channel_id=None,
        discord_thread_id=None,
        discord_message_id=None,
    )

    out_file = tmp_path / "logs.csv"
    logger.export_csv(out_file)

    contents = out_file.read_text(encoding="utf-8")
    assert "question" in contents
    assert "rag_answer" in contents

