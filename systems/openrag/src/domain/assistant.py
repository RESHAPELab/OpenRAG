from dataclasses import dataclass, field
from typing import TypeAlias

Model: TypeAlias = str
Message: TypeAlias = str
SessionId: TypeAlias = str


@dataclass
class PromptResult:
    """Result from an assistant prompt, including the answer and retrieved context."""

    answer: str
    retrieved_context: str
    source_metadata: list[dict] = field(default_factory=list)
