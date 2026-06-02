from __future__ import annotations

from typing import Any

import pytest
from dependency_injector.providers import Factory
from langchain_classic.memory import ConversationBufferMemory
from langchain_core.documents import Document

from src.adapters.assistant import ConversationalAssistantAdapter


class DummyLLM:
    def invoke(self, input, *, config=None, **kwargs):
        class Result:
            content = f"raw:{input}"

        return Result()


class DummyStorage:
    def as_retriever(self, **kwargs):
        class DummyRetriever:
            def get_relevant_documents(self, query: str, *, run_manager=None):
                return [
                    Document(
                        page_content="dummy content",
                        metadata={"source": "dummy.md"},
                    )
                ]

            def invoke(self, query: str, *, config=None, **kwargs):
                return self.get_relevant_documents(query)

        return DummyRetriever()


@pytest.fixture
def assistant() -> ConversationalAssistantAdapter:
    llm = DummyLLM()
    storage = DummyStorage()
    memory_factory: Factory[ConversationBufferMemory] = Factory(ConversationBufferMemory)
    return ConversationalAssistantAdapter(
        llm=llm,
        storage=storage,
        memory_factory=memory_factory,
        log_raw_llm_answer=True,
    )


def test_prompt_with_metadata_returns_answer_and_context(
    assistant: ConversationalAssistantAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build_chain(self, memory):
        class FakeChain:
            def __call__(self, params: dict[str, Any]) -> dict[str, Any]:
                return {
                    "answer": "test answer",
                    "source_documents": [
                        Document(
                            page_content="dummy content",
                            metadata={"source": "dummy.md"},
                        )
                    ],
                }

        return FakeChain()

    monkeypatch.setattr(ConversationalAssistantAdapter, "_build_chain", fake_build_chain)

    result = assistant.prompt_with_metadata("Hello", session_id="session-1")
    assert result["answer"] == "test answer"
    assert "rag_context" in result
    assert "llm_answer" in result

