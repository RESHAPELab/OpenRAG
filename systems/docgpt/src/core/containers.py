import logging.config
from pathlib import Path

from dependency_injector import containers, providers
from dependency_injector.providers import Factory, Singleton
from langchain_classic.memory import ConversationBufferMemory
from langchain_classic.memory.chat_memory import BaseChatMemory
from langchain_community.chat_message_histories import MongoDBChatMessageHistory
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_postgres import PGVector
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.vectorstores import VectorStore
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_text_splitters import TextSplitter

from src.adapters.assistant import ConversationalAssistantAdapter
from src.adapters.content import (
    GitCodeContentAdapter,
    GitWikiContentAdapter,
    LangSplitterByMetadata,
    PandocConverterAdapter,
    WebPageContentAdapter,
)
from src.port.assistant import AssistantPort
from src.port.content import ContentConverterPort, ContentPort
from src.logging.discord_logger import DiscordInteractionLogger


class Core(containers.DeclarativeContainer):
    config = providers.Configuration()

    logging = providers.Resource(
        logging.config.dictConfig,
        config=config.logging,
    )

    assets_path = providers.Singleton(Path, ".assets")


class AI(containers.DeclarativeContainer):
    config = providers.Configuration()

    llm: Singleton[BaseChatModel] = Singleton(
        ChatGoogleGenerativeAI,
        model=config.gemini.model_name,
        google_api_key=config.gemini.api_key,
        verbose=True,
    )

    gemini_embedding: Singleton[Embeddings] = Singleton(
        GoogleGenerativeAIEmbeddings,
        model="gemini-embedding-001",
        google_api_key=config.gemini.api_key,
    )

    hugging_embedding: Singleton[Embeddings] = Singleton(
        HuggingFaceBgeEmbeddings,
        model_name="all-MiniLM-L6-v2",
        # model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    # embeddings: Singleton[Embeddings] = gemini_embedding
    embeddings: Singleton[Embeddings] = hugging_embedding


class StorageAdapters(containers.DeclarativeContainer):
    config = providers.Configuration()
    ai = providers.DependenciesContainer()

    pg_vector: Singleton[VectorStore] = Singleton(
        PGVector,
        connection=config.vector.url,
        embeddings=ai.embeddings,
        collection_name="docgpt_embeddings",
        use_jsonb=True,
    )

    chroma: Singleton[VectorStore] = Singleton(
        Chroma,
        embedding_function=ai.embeddings,
        persist_directory=".localstorage",
    )

    def _vector_storage(
        backend: str,
        chroma_store: VectorStore,
        pg_store: VectorStore,
    ) -> VectorStore:
        return chroma_store if (backend or "pgvector").lower() == "chroma" else pg_store

    vector_storage: providers.Factory[VectorStore] = providers.Factory(
        _vector_storage,
        backend=config.vector.backend,
        chroma_store=chroma,
        pg_store=pg_vector,
    )

    memory_factory: providers.Factory[BaseChatMessageHistory] = providers.Factory(
        MongoDBChatMessageHistory,
        connection_string=config.memory.url,
    )


class ContentAdapters(containers.DeclarativeContainer):
    config = providers.Configuration()
    core = providers.DependenciesContainer()

    converter: Singleton[ContentConverterPort] = Singleton(PandocConverterAdapter)
    splitter_factory: Factory[LangSplitterByMetadata] = Factory(LangSplitterByMetadata)

    git_splitter: Singleton[TextSplitter] = Singleton(splitter_factory, "file_name")
    git_code: Singleton[ContentPort] = Singleton(
        GitCodeContentAdapter,
        splitter=git_splitter,
        assets_path=core.assets_path,
    )
    git_wiki: Singleton[ContentPort] = Singleton(
        GitWikiContentAdapter,
        splitter=git_splitter,
        assets_path=core.assets_path,
    )
    web: Singleton[ContentPort] = Singleton(WebPageContentAdapter, converter)


class AssistantAdapters(containers.DeclarativeContainer):
    config = providers.Configuration()
    ai = providers.DependenciesContainer()
    storage = providers.DependenciesContainer()

    memory: providers.Factory[BaseChatMemory] = providers.Factory(
        ConversationBufferMemory,
        chat_memory=storage.memory_factory,
        memory_key="chat_history",
        output_key="answer",
    )

    chat: Singleton[AssistantPort] = Singleton(
        ConversationalAssistantAdapter,
        llm=ai.llm,
        storage=storage.vector_storage,
        memory_factory=memory.provider,
        k=config.k,
        tokens_limit=config.tokens_limit.as_int(),
        score_threshold=config.score_threshold,
        distance_threshold=config.distance_threshold,
        log_raw_llm_answer=config.log_raw_llm_answer,
    )


class LoggingAdapters(containers.DeclarativeContainer):
    config = providers.Configuration()

    discord_logger: Singleton[DiscordInteractionLogger] = Singleton(
        DiscordInteractionLogger,
        dsn=config.storage.logs.url,
        rag_name=config.assistant.rag_name,
    )


class Integrations(containers.DeclarativeContainer):
    config = providers.Configuration()
    assistant = providers.DependenciesContainer()

    discord_token = config.discord.token


class Api(containers.DeclarativeContainer):
    config = providers.Configuration()

    port = config.port.as_int()


class Settings(containers.DeclarativeContainer):
    config = providers.Configuration()

    core = providers.Container(Core, config=config.core)
    ai = providers.Container(AI, config=config.ai)
    storage = providers.Container(StorageAdapters, config=config.storage, ai=ai)
    content = providers.Container(ContentAdapters, config=config.content, core=core)
    assistant = providers.Container(AssistantAdapters, config=config.assistant, ai=ai, storage=storage)
    logging = providers.Container(LoggingAdapters, config=config)
    app = providers.Container(Integrations, config=config.app, assistant=assistant)
    api = providers.Container(Api, config=config.api)
