from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import client_key, require_api_key
from app.api.schemas.chat import ChatRequest, ChatResponse, ToolInfo

router = APIRouter()


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
