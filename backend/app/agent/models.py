"""Tipos neutros do agente (independentes do SDK do Gemini)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    name: str
    response: dict[str, Any]


@dataclass
class Message:
    """Uma mensagem da conversa.

    role: "user", "assistant" (resposta do modelo, com ou sem chamadas de ferramenta)
          ou "tool" (resultados das ferramentas, devolvidos ao modelo).
    raw/model: conteúdo original do provedor e o modelo que o gerou. O Gemini 3 exige
    reenviar as "thought signatures" junto das chamadas de ferramenta, então o conteúdo
    original é preservado enquanto o mesmo modelo continua respondendo.
    """

    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: Any = None
    model: str | None = None


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall]
    raw: Any = None
    model: str | None = None


@dataclass
class ToolTrace:
    name: str
    args: dict[str, Any]
    ok: bool
    summary: str


@dataclass
class AgentReply:
    text: str
    session_id: str
    tools: list[ToolTrace] = field(default_factory=list)
    escalated: bool = False
    model: str | None = None
    degraded: bool = False  # True quando a resposta foi um aviso de indisponibilidade
    input_truncated: bool = False


class LLMClient(Protocol):
    def generate(self, messages: list[Message], system: str, tools: Any) -> LLMTurn: ...
