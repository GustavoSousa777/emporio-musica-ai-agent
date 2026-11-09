"""Cliente do Gemini para o agente: function calling com failover entre modelos.

Detalhes importantes do Gemini 3 com ferramentas:
- As "thought signatures" devolvidas junto das chamadas de função precisam voltar na
  requisição seguinte. Enquanto o mesmo modelo continua respondendo, reenviamos o
  conteúdo original (`Message.raw`). Se o failover trocar de modelo no meio do ciclo de
  ferramentas, reconstruímos a mensagem a partir do texto e usamos a assinatura de
  contorno documentada ("skip_thought_signature_validator").
- Desligamos o function calling automático do SDK: o loop é nosso (app/agent/agent.py),
  assim conseguimos validar argumentos, registrar as ferramentas usadas e limitar rodadas.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any, Callable

from app.agent.models import LLMTurn, Message, ToolCall
from app.core.gemini_failover import LLMUnavailableError, ModelPool, classify_error

logger = logging.getLogger(__name__)

TIMEOUT_MS = 40_000
# Valor documentado pelo Google para pular a validação quando a assinatura original não existe.
# O SDK serializa bytes em base64, então enviamos os bytes que, codificados, resultam no texto.
DUMMY_SIGNATURE = base64.urlsafe_b64decode("skip_thought_signature_validator")


def make_client(api_key: str):
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def to_contents(messages: list[Message], model: str) -> list[Any]:
    """Converte as mensagens neutras em `Content` do Gemini para o modelo informado."""
    from google.genai import types

    contents: list[Any] = []
    for msg in messages:
        if msg.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg.text)]))
        elif msg.role == "assistant":
            if msg.raw is not None and msg.model == model:
                contents.append(msg.raw)
                continue
            parts: list[Any] = []
            if msg.text:
                parts.append(types.Part.from_text(text=msg.text))
            for call in msg.tool_calls:
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(name=call.name, args=call.args),
                        thought_signature=DUMMY_SIGNATURE,
                    )
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))
        else:  # tool
            parts = [
                types.Part.from_function_response(name=r.name, response=r.response) for r in msg.tool_results
            ]
            contents.append(types.Content(role="user", parts=parts))
    return contents


def to_tools(specs: Any) -> list[Any]:
    from google.genai import types

    declarations = [
        types.FunctionDeclaration(name=s.name, description=s.description, parameters_json_schema=s.parameters)
        for s in specs
    ]
    return [types.Tool(function_declarations=declarations)]


def parse_response(response: Any, model: str) -> LLMTurn:
    candidates = getattr(response, "candidates", None) or []
    content = candidates[0].content if candidates else None
    parts = (content.parts if content is not None else None) or []
    text = "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
    calls = [
        ToolCall(name=p.function_call.name, args=dict(p.function_call.args or {}))
        for p in parts
        if getattr(p, "function_call", None)
    ]
    return LLMTurn(text=text.strip(), tool_calls=calls, raw=content, model=model)


class GeminiLLM:
    def __init__(
        self,
        api_key: str | None,
        pool: ModelPool,
        thinking_level: str | None = None,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if client is None and not api_key:
            raise ValueError("GEMINI_API_KEY não configurada.")
        self.pool = pool
        self.thinking_level = thinking_level
        self._client = client if client is not None else make_client(api_key)
        self._sleep = sleep

    def _config(self, system: str, tools: Any):
        from google.genai import types

        kwargs: dict[str, Any] = {
            "system_instruction": system,
            "tools": to_tools(tools),
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if self.thinking_level:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self.thinking_level)
        return types.GenerateContentConfig(**kwargs)

    def _call(self, model: str, messages: list[Message], system: str, tools: Any):
        config = self._config(system, tools)
        contents = to_contents(messages, model)
        for attempt in (1, 2):
            try:
                return self._client.models.generate_content(model=model, contents=contents, config=config)
            except Exception as exc:  # noqa: BLE001 - classificado abaixo
                if attempt == 1 and classify_error(exc).retry_same_model:
                    self._sleep(2.0)
                    continue
                raise

    def generate(self, messages: list[Message], system: str, tools: Any) -> LLMTurn:
        last_error: BaseException | None = None
        for model in self.pool.candidates():
            try:
                response = self._call(model, messages, system, tools)
                return parse_response(response, model)
            except Exception as exc:  # noqa: BLE001
                info = classify_error(exc)
                if not info.switch_model:
                    raise
                seconds = self.pool.block(model, info)
                logger.warning("Modelo %s falhou (%s); bloqueado por %.0fs", model, info.text[:200], seconds)
                last_error = exc
        raise LLMUnavailableError(
            f"Nenhum modelo respondeu: {last_error}",
            wait_seconds=self.pool.wait_seconds(),
            daily_quota=self.pool.all_daily(),
        )
