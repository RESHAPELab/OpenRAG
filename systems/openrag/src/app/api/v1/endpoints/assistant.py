import logging

from fastapi import APIRouter, Body, Depends, status

from src.app.api.deps import get_assistant
from src.core.interaction_logger import get_logger
from src.domain.assistant import Message, SessionId
from src.domain.responses import AssistantPromptResponse
from src.port.assistant import AssistantPort

__all__ = ("ROUTER",)

log = logging.getLogger(__name__)

ROUTER = APIRouter(prefix="/assistant", tags=['Assistant'])

@ROUTER.post("/prompt",
            description='Send a query to the assistant, passing the active session.',
            summary='Send a query to the assistant, passing the active session.')
async def prompt(
    message: Message = Body(...),
    session_id: SessionId | None = Body(None),
    assistant: AssistantPort = Depends(get_assistant),
) -> AssistantPromptResponse:
    result = assistant.prompt(message, session_id=session_id)

    # Log the interaction
    interaction_logger = get_logger()
    if interaction_logger:
        try:
            interaction_logger.log(
                session_id=session_id or "anonymous",
                question=message,
                answer=result.answer,
                retrieved_context=result.retrieved_context,
                source_metadata=result.source_metadata,
            )
        except Exception:
            log.exception("Failed to log interaction")

    return AssistantPromptResponse(
        question=message,
        session_id=session_id,
        answer=result.answer,
        retrieved_context=result.retrieved_context,
        source_count=len(result.source_metadata),
    )

@ROUTER.delete("/history/{session_id}",
               description='Delete a session given the identifier.',
               summary='Delete a session given the identifier.',
               status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(
    session_id: SessionId,
    assistant: AssistantPort = Depends(get_assistant),
) -> None:
    assistant.clear_history(session_id)
