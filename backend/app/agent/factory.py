"""Monta o agente com as configurações do ambiente (.env)."""
from __future__ import annotations

from app.agent.agent import Agent
from app.agent.gemini_llm import GeminiLLM
from app.agent.memory import ConversationStore
from app.agent.models import LLMClient
from app.core.config import Settings, get_settings
from app.core.gemini_failover import ModelPool
from app.database.connection import ensure_database
from app.rag.retriever import Retriever, load_retriever


def build_agent(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    retriever: Retriever | None = None,
    conversations: ConversationStore | None = None,
    now: str | None = None,
) -> Agent:
    settings = settings or get_settings()
    if llm is None:
        if not settings.gemini_api_key:
            raise ValueError("Defina GEMINI_API_KEY no backend/.env para usar o agente.")
        llm = GeminiLLM(
            settings.gemini_api_key,
            ModelPool(settings.gemini_models),
            thinking_level=settings.gemini_thinking_level,
        )
    db_path = ensure_database(settings.db_path)
    return Agent(
        llm=llm,
        retriever=retriever or load_retriever(settings),
        conversations=conversations or ConversationStore(settings.conversations_db_path),
        db_path=db_path,
        now=now,
    )
