from abc import ABC, abstractmethod
from typing import Any

from src.domain.assistant import Message, SessionId


class AssistantPort(ABC):
    @abstractmethod
    def clear_history(self, session_id: SessionId) -> None:
        ...

    @abstractmethod
    def prompt(
        self,
        message: Message,
        *,
        session_id: SessionId | None = None,
    ) -> Message:
        ...

    @abstractmethod
    def prompt_with_metadata(
        self,
        message: Message,
        *,
        session_id: SessionId | None = None,
    ) -> dict[str, Any]:
        """Return answer plus RAG context/raw LLM answer for logging."""
        ...
