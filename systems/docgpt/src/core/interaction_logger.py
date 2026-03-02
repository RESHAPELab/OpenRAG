"""
Interaction Logger for DocGPT

Automatically logs every RAG interaction (question, retrieved context, answer)
to CSV and JSONL files. Each row is appended immediately after the interaction
so nothing is lost if the process crashes.

Files are created per bot run (timestamped at startup) inside the output directory.

Usage:
    from src.core.interaction_logger import init_logger, get_logger

    # At startup (e.g. in main.py)
    init_logger(output_dir="logs")

    # On each interaction (e.g. in discord.py or api endpoint)
    logger = get_logger()
    if logger:
        logger.log(session_id="123", question="...", answer="...", retrieved_context="...")
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "timestamp",
    "session_id",
    "question",
    "retrieved_context",
    "answer",
    "source_count",
]


class InteractionLogger:
    """
    Logs each RAG interaction to CSV and JSONL files.

    Creates a pair of timestamped files at initialisation and appends
    one row/line per interaction for crash-resilient persistence.
    """

    def __init__(self, output_dir: str = "logs") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        # Create timestamped filenames (one pair per bot run)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._csv_path = self._output_dir / f"interactions_{ts}.csv"
        self._jsonl_path = self._output_dir / f"interactions_{ts}.jsonl"

        # Write CSV header
        with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()

        logger.info(
            "Interaction logger initialised — CSV: %s, JSONL: %s",
            self._csv_path,
            self._jsonl_path,
        )

    def log(
        self,
        *,
        session_id: str,
        question: str,
        answer: str,
        retrieved_context: str,
        source_metadata: list[dict] | None = None,
    ) -> None:
        """Log a single interaction, appending to both CSV and JSONL."""
        timestamp = datetime.now().isoformat(timespec="seconds")
        source_count = len(source_metadata) if source_metadata else 0

        csv_row = {
            "timestamp": timestamp,
            "session_id": session_id,
            "question": question,
            "retrieved_context": retrieved_context,
            "answer": answer,
            "source_count": source_count,
        }

        # JSONL row includes the full source metadata for detailed analysis
        jsonl_row = {
            **csv_row,
            "source_metadata": source_metadata or [],
        }

        with self._lock:
            # Append to CSV
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writerow(csv_row)

            # Append to JSONL (one JSON object per line)
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(jsonl_row, ensure_ascii=False) + "\n")

        logger.debug(
            "Logged interaction [session=%s]: %s",
            session_id,
            question[:60] + ("..." if len(question) > 60 else ""),
        )

    @property
    def csv_path(self) -> Path:
        """Path to the CSV log file for this run."""
        return self._csv_path

    @property
    def jsonl_path(self) -> Path:
        """Path to the JSONL log file for this run."""
        return self._jsonl_path


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: InteractionLogger | None = None


def init_logger(output_dir: str = "logs") -> InteractionLogger:
    """Create (or re-create) the global InteractionLogger singleton."""
    global _instance
    _instance = InteractionLogger(output_dir)
    return _instance


def get_logger() -> InteractionLogger | None:
    """Return the global InteractionLogger, or None if not yet initialised."""
    return _instance
