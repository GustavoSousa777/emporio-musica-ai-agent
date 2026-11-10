from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.agent.agent import MAX_INPUT_CHARS, SESSION_ID_MAX

SESSION_ID_PATTERN = rf"^[A-Za-z0-9_-]{{1,{SESSION_ID_MAX}}}$"


class ChatRequest(BaseModel):
    message: str = Field(max_length=MAX_INPUT_CHARS, examples=["Quanto custa o Takamine GD20?"])
    session_id: str | None = Field(
        default=None,
        pattern=SESSION_ID_PATTERN,
        description="Identifica a conversa. Se omitido, a API cria um e devolve na resposta.",
    )

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A mensagem não pode ser vazia.")
        return value


class ToolInfo(BaseModel):
    name: str
    ok: bool


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    tools: list[ToolInfo]
    escalated: bool
    degraded: bool
    model: str | None
    input_truncated: bool


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]
