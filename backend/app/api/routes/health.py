from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.schemas.health import HealthResponse, LlmInfo, RagInfo
from app.core.config import get_settings

router = APIRouter()


def _database_ok(db_path: Path | str | None) -> tuple[bool, str | None]:
    path = Path(db_path) if db_path else get_settings().db_path
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    except sqlite3.Error as exc:
        return False, f"Banco da loja indisponível: {exc}"
    if not count:
        return False, "Banco da loja sem produtos. Rode python -m app.database.seed."
    return True, None


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    state = request.app.state
    settings = state.settings
    llm = LlmInfo(key_configured=bool(settings.gemini_api_key), models=list(settings.gemini_models))
    agent = state.agent
    if agent is None:
        body = HealthResponse(
            status="degraded", ready=False, database=False, llm=llm,
            detail=state.agent_error or "Agente não inicializado.",
        )
        return JSONResponse(body.model_dump(), status_code=503)

    database, detail = _database_ok(agent.db_path)
    retriever = agent.retriever
    rag = RagInfo(
        chunks=len(retriever.index.chunks),
        mode=retriever.mode,
        embeddings=retriever.index.has_vectors,
    )
    ready = database and rag.chunks > 0
    body = HealthResponse(
        status="ok" if ready else "degraded", ready=ready, database=database, rag=rag, llm=llm, detail=detail,
    )
    return JSONResponse(body.model_dump(), status_code=200 if ready else 503)
