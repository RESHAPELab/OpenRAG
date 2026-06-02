from abc import ABC, abstractmethod
from typing import Any

from src.domain.assistant import Message, PromptResult, SessionId


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
    ) -> PromptResult:
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

    @abstractmethod
    def generate_title(self, question: Message, answer: str) -> str:
        """Generate a short thread title from a Q&A pair using a direct LLM call (no RAG)."""
        ...
