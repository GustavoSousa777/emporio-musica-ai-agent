from __future__ import annotations

from pydantic import BaseModel


class RagInfo(BaseModel):
    chunks: int
    mode: str
    embeddings: bool


class LlmInfo(BaseModel):
    key_configured: bool
    models: list[str]


class HealthResponse(BaseModel):
    status: str
    ready: bool
    database: bool
    rag: RagInfo | None = None
    llm: LlmInfo
    detail: str | None = None
