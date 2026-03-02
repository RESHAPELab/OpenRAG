from functools import lru_cache
import json
from typing import Any

from dependency_injector.providers import Factory
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.memory.chat_memory import BaseChatMemory
from langchain_core.language_models import BaseChatModel
from langchain_core.vectorstores import VectorStore

from src.core.prompts import CONDENSE_QUESTION_PROMPT, QA_PROMPT
from src.domain.assistant import Message, SessionId
from src.port.assistant import AssistantPort


class ConversationalAssistantAdapter(AssistantPort):
    def __init__(
        self,
        llm: BaseChatModel,
        storage: VectorStore,
        memory_factory: Factory[BaseChatMemory],
        *,
        k: int = 100,
        tokens_limit: int = 4_000,
        score_threshold: float | None = 0.9,
        distance_threshold: float | None = None,
        log_raw_llm_answer: bool | str = False,
    ) -> None:
        self._llm = llm

        self._storage = storage
        self._memory_factory = memory_factory
        self._k = k
        self._tokens_limit = tokens_limit
        self._score_threshold = score_threshold
        self._distance_threshold = distance_threshold
        if isinstance(log_raw_llm_answer, bool):
            self._log_raw_llm_answer = log_raw_llm_answer
        else:
            self._log_raw_llm_answer = str(log_raw_llm_answer).lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

    @lru_cache
    def _get_memory(self, session_id: SessionId) -> BaseChatMemory:
        return self._memory_factory(chat_memory__session_id=session_id)

    def clear_history(self, session_id: SessionId) -> None:
        self._get_memory(session_id).clear()

    def _build_search_kwargs(self) -> dict[str, Any]:
        """Build retriever search kwargs, only include non-None values."""
        search_kwargs: dict[str, Any] = {"k": self._k}
        if self._score_threshold is not None:
            search_kwargs["score_threshold"] = self._score_threshold
        if self._distance_threshold is not None:
            search_kwargs["distance_threshold"] = self._distance_threshold
        return search_kwargs

    def _build_chain(self, memory: BaseChatMemory | None) -> ConversationalRetrievalChain:
        search_kwargs = self._build_search_kwargs()

        return ConversationalRetrievalChain.from_llm(
            llm=self._llm,
            condense_question_prompt=CONDENSE_QUESTION_PROMPT,
            retriever=self._storage.as_retriever(
                search_type="similarity",
                search_kwargs=search_kwargs,
            ),
            combine_docs_chain_kwargs={"prompt": QA_PROMPT},
            get_chat_history=lambda v: v,
            memory=memory,
            verbose=True,
            return_source_documents=True,
            # max_tokens_limit disabled due to Gemini API compatibility issue
            # max_tokens_limit=self._tokens_limit,
        )

    def prompt(self, message: Message, *, session_id: SessionId | None = None) -> str:
        result = self.prompt_with_metadata(message, session_id=session_id)
        return result["answer"]

    def prompt_with_metadata(
        self,
        message: Message,
        *,
        session_id: SessionId | None = None,
    ) -> dict[str, Any]:
        memory = self._get_memory(session_id) if session_id else None
        qa = self._build_chain(memory)

        qa_params: dict[str, Any] = {"question": message}
        if not memory:
            qa_params["chat_history"] = ""

        response: dict[str, Any] = qa(qa_params)
        answer = response.get("answer", "")

        source_docs = response.get("source_documents") or []

        # Derive RAG context for logging.
        # Prefer chain-returned source documents; fall back to a standalone
        # retrieval for compatibility across chain versions.
        rag_context: str | None = None
        if not source_docs:
            retriever = self._storage.as_retriever(
                search_type="similarity",
                search_kwargs=self._build_search_kwargs(),
            )
            # Support both classic retrievers (with get_relevant_documents)
            # and Runnable-style retrievers (with invoke).
            get_docs = getattr(retriever, "get_relevant_documents", None)
            if callable(get_docs):
                source_docs = get_docs(message)
            else:
                source_docs = retriever.invoke(message)

        if source_docs:
            snippets: list[dict[str, Any]] = []
            for doc in source_docs[:5]:
                page_content = getattr(doc, "page_content", "")
                metadata = getattr(doc, "metadata", {}) or {}
                source = metadata.get("source") or metadata.get("file_path") or ""
                snippets.append(
                    {
                        "source": source,
                        "snippet": page_content[:500],
                    }
                )
            rag_context = json.dumps(snippets, ensure_ascii=False)

        llm_answer: str | None = None
        if self._log_raw_llm_answer:
            try:
                raw = self._llm.invoke(message)
                content = getattr(raw, "content", None)
                llm_answer = content if isinstance(content, str) else str(raw)
            except Exception:
                llm_answer = None

        return {
            "answer": answer,
            "rag_context": rag_context,
            "llm_answer": llm_answer,
            "source_documents": source_docs,
        }
