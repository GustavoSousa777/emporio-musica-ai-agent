from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.api.deps import client_key, require_api_key
from app.api.schemas.chat import (
    SESSION_ID_PATTERN,
    ChatRequest,
    ChatResponse,
    HistoryMessage,
    HistoryResponse,
    ToolInfo,
)

router = APIRouter()

HISTORY_DISPLAY_LIMIT = 100


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    state = request.app.state
    if state.agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agente indisponível: configuração incompleta no servidor.")
    retry_after = state.limiter.check(client_key(request))
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas mensagens em pouco tempo. Tente de novo em instantes.",
            headers={"Retry-After": str(retry_after)},
        )
    session_id = payload.session_id or uuid.uuid4().hex
    reply = state.agent.reply(session_id, payload.message)
    return ChatResponse(
        reply=reply.text,
        session_id=reply.session_id,
        tools=[ToolInfo(name=t.name, ok=t.ok) for t in reply.tools],
        escalated=reply.escalated,
        degraded=reply.degraded,
        model=reply.model,
        input_truncated=reply.input_truncated,
    )


@router.get(
    "/chat/{session_id}/history",
    response_model=HistoryResponse,
    dependencies=[Depends(require_api_key)],
)
def history(request: Request, session_id: str = Path(pattern=SESSION_ID_PATTERN)) -> HistoryResponse:
    agent = request.app.state.agent
    if agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agente indisponível: configuração incompleta no servidor.")
    messages = agent.conversations.history(session_id, HISTORY_DISPLAY_LIMIT)
    return HistoryResponse(
        session_id=session_id,
        messages=[HistoryMessage(role=m.role, text=m.text) for m in messages],
    )
