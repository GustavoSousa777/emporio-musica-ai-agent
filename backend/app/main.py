from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.factory import build_agent
from app.api.ratelimit import RateLimiter
from app.api.routes import chat, health
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(agent=None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.agent is None:
            try:
                app.state.agent = build_agent(settings)
            except Exception as exc:
                logger.error("Não foi possível iniciar o agente: %s", exc)
                app.state.agent_error = str(exc)
        yield

    app = FastAPI(
        title="Empório da Música: agente de atendimento",
        version="1.0.0",
        description="Atendimento por texto com function calling e RAG das políticas da loja.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.agent = agent
    app.state.agent_error = None
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-API-Key"],
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("Erro inesperado em %s", request.url.path)
        return JSONResponse({"detail": "Erro interno. Tente de novo em instantes."}, status_code=500)

    app.include_router(chat.router)
    app.include_router(health.router)
    return app