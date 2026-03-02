from pydantic import BaseModel

__all__ = ("AssistantPromptResponse",)


class AssistantPromptResponse(BaseModel):
    question: str
    answer: str
    retrieved_context: str = ""
    source_count: int = 0
    session_id: str | None = None
