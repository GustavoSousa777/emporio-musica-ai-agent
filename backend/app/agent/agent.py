from __future__ import annotations

import json
import logging
from contextlib import closing
from pathlib import Path
from typing import Any

from app.agent.memory import ConversationStore
from app.agent.models import AgentReply, LLMClient, Message, ToolCall, ToolResult, ToolTrace
from app.agent.prompts import build_system_prompt
from app.agent.tools import ToolContext, Toolset
from app.core.clock import get_now
from app.core.gemini_failover import LLMUnavailableError
from app.core.rules import STORE_INFO
from app.database.connection import get_connection
from app.rag.retriever import Retriever

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_INPUT_CHARS = 2000
HISTORY_LIMIT = 20
SESSION_ID_MAX = 64
SENSITIVE_ARGS = {"email", "phone"}

UNAVAILABLE_MESSAGE = (
    "Estou com uma instabilidade aqui e não consegui consultar o sistema agora. "
    "Tenta de novo em alguns minutinhos? Se for urgente, chama a loja no WhatsApp "
    f"{STORE_INFO['whatsapp']} ou no telefone {STORE_INFO['phone']}."
)
NO_ANSWER_MESSAGE = (
    "Não consegui concluir essa consulta agora. Pode reformular ou me dar mais detalhes? "
    f"Se preferir, fale com a equipe no WhatsApp {STORE_INFO['whatsapp']}."
)
EMPTY_INPUT_MESSAGE = "Oi! Não recebi sua mensagem. Como posso te ajudar?"


def _trace_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: ("***" if k in SENSITIVE_ARGS and v else v) for k, v in args.items()}


def _summary(response: dict[str, Any], limit: int = 160) -> str:
    text = json.dumps(response, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        retriever: Retriever,
        conversations: ConversationStore,
        db_path: Path | str | None = None,
        toolset: Toolset | None = None,
        now: Any = None,
    ):
        self.llm = llm
        self.retriever = retriever
        self.conversations = conversations
        self.db_path = db_path
        self.toolset = toolset or Toolset()
        self._now = now

    def reply(self, session_id: str, user_text: str) -> AgentReply:
        session_id = (session_id or "").strip()[:SESSION_ID_MAX]
        if not session_id:
            raise ValueError("session_id é obrigatório.")
        user_text = (user_text or "").strip()
        if not user_text:
            return AgentReply(text=EMPTY_INPUT_MESSAGE, session_id=session_id)
        truncated = len(user_text) > MAX_INPUT_CHARS
        user_text = user_text[:MAX_INPUT_CHARS]

        now = get_now(self._now)
        system = build_system_prompt(now)
        messages = self.conversations.history(session_id, HISTORY_LIMIT)
        messages.append(Message(role="user", text=user_text))

        traces: list[ToolTrace] = []
        escalated = False
        model_used: str | None = None
        final_text = ""

        with closing(get_connection(self.db_path)) as conn:
            ctx = ToolContext(conn, self.retriever, self.conversations, session_id, now)
            try:
                for _ in range(MAX_TOOL_ROUNDS + 1):
                    turn = self.llm.generate(messages, system, self.toolset.specs)
                    model_used = turn.model or model_used
                    if not turn.tool_calls:
                        final_text = turn.text
                        break
                    messages.append(
                        Message(
                            role="assistant", text=turn.text, tool_calls=turn.tool_calls,
                            raw=turn.raw, model=turn.model,
                        )
                    )
                    results: list[ToolResult] = []
                    for call in turn.tool_calls:
                        response, ok = self.toolset.run(call.name, call.args, ctx)
                        results.append(ToolResult(call.name, response))
                        traces.append(ToolTrace(call.name, _trace_args(call.args), ok, _summary(response)))
                        if call.name == "escalate_to_human" and response.get("registered"):
                            escalated = True
                    messages.append(Message(role="tool", tool_results=results))
                else:
                    logger.warning("Limite de %d rodadas de ferramenta atingido (sessão %s)", MAX_TOOL_ROUNDS, session_id)
            except LLMUnavailableError as exc:
                logger.warning("LLM indisponível: %s", exc)
                return AgentReply(
                    text=UNAVAILABLE_MESSAGE, session_id=session_id, tools=traces,
                    escalated=escalated, model=model_used, degraded=True, input_truncated=truncated,
                )

        if not final_text:
            return AgentReply(
                text=NO_ANSWER_MESSAGE, session_id=session_id, tools=traces,
                escalated=escalated, model=model_used, degraded=True, input_truncated=truncated,
            )

        self.conversations.append(session_id, "user", user_text)
        self.conversations.append(session_id, "assistant", final_text)
        return AgentReply(
            text=final_text, session_id=session_id, tools=traces, escalated=escalated,
            model=model_used, input_truncated=truncated,
        )
