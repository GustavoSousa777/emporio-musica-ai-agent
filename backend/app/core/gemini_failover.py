"""Failover entre modelos do Gemini quando a cota acaba ou o modelo falha.

Mesma ideia do cliente do mentor-de-dados (lista de modelos de reserva e bloqueio
temporário de quem falhou), com um acréscimo: quando o erro 429 indica limite DIÁRIO,
o modelo fica bloqueado até a virada do dia (meia-noite no fuso do Pacífico, quando a
cota diária do Google AI Studio é renovada) em vez de ser retentado a cada minuto.

  429 (cota)          -> troca de modelo; bloqueio por retry-after, ou 60 s, ou até o fim do dia
  404 (modelo sumiu)  -> troca de modelo; bloqueio de 1 hora
  5xx / conexão       -> uma nova tentativa no mesmo modelo e, se falhar, troca; bloqueio de 30 s
  demais erros (400)  -> não troca: provavelmente é um bug da requisição
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

QUOTA_RESET_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_RATE_LIMIT_BLOCK = 60.0
SERVER_ERROR_BLOCK = 30.0
MODEL_NOT_FOUND_BLOCK = 3600.0

_DAILY_MARKERS = ("perday", "per day", "requestsperday", "daily")
_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", re.IGNORECASE)
_CONNECTION_ERROR_NAMES = (
    "APIConnectionError", "APITimeoutError", "ConnectError", "ReadTimeout", "TransportError",
)


class LLMUnavailableError(RuntimeError):
    """Todos os modelos estão bloqueados ou falharam."""

    def __init__(self, message: str, wait_seconds: float | None = None, daily_quota: bool = False):
        super().__init__(message)
        self.wait_seconds = wait_seconds
        self.daily_quota = daily_quota


@dataclass(frozen=True)
class ErrorInfo:
    code: int | None
    is_connection: bool
    daily_quota: bool
    retry_after: float | None
    text: str

    @property
    def switch_model(self) -> bool:
        return (
            self.is_connection
            or self.code in (404, 429)
            or (self.code is not None and self.code >= 500)
        )

    @property
    def retry_same_model(self) -> bool:
        # 504 (DEADLINE_EXCEEDED) já gastou o tempo limite inteiro: repetir no mesmo modelo só dobra a espera.
        if self.code == 504:
            return False
        return self.is_connection or (self.code is not None and self.code >= 500)


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _retry_after(exc: BaseException, text: str) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    value = headers.get("retry-after") if headers else None
    try:
        seconds = float(value) if value is not None else None
    except (TypeError, ValueError):
        seconds = None
    if seconds is None:
        match = _RETRY_DELAY_RE.search(text)
        seconds = float(match.group(1)) if match else None
    return seconds if seconds and seconds > 0 else None


def classify_error(exc: BaseException) -> ErrorInfo:
    body = getattr(exc, "details", None)
    text = " | ".join(part for part in (str(exc)[:600], str(body)[:900] if body else "") if part)
    code = _status_code(exc)
    is_connection = any(cls.__name__ in _CONNECTION_ERROR_NAMES for cls in type(exc).__mro__)
    daily = code == 429 and any(marker in text.lower() for marker in _DAILY_MARKERS)
    return ErrorInfo(code, is_connection, daily, _retry_after(exc, text), text)


def seconds_until_quota_reset(now: datetime | None = None) -> float:
    """Segundos até a próxima meia-noite do Pacífico (renovação da cota diária)."""
    current = (now or datetime.now(QUOTA_RESET_TZ)).astimezone(QUOTA_RESET_TZ)
    midnight = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1.0, (midnight - current).total_seconds())


class ModelPool:
    """Lista ordenada de modelos com bloqueio temporário de quem falhou."""

    def __init__(
        self,
        models: list[str] | tuple[str, ...],
        clock: Callable[[], float] = time.monotonic,
        wall_now: Callable[[], datetime] | None = None,
    ):
        if not models:
            raise ValueError("Informe ao menos um modelo.")
        self.models = list(dict.fromkeys(models))
        self._clock = clock
        self._wall_now = wall_now or (lambda: datetime.now(QUOTA_RESET_TZ))
        self._blocked_until: dict[str, float] = {}
        self._daily: set[str] = set()

    def block_seconds(self, info: ErrorInfo) -> float:
        if info.code == 429:
            if info.daily_quota:
                return seconds_until_quota_reset(self._wall_now())
            return info.retry_after or DEFAULT_RATE_LIMIT_BLOCK
        if info.code == 404:
            return MODEL_NOT_FOUND_BLOCK
        return SERVER_ERROR_BLOCK

    def block(self, model: str, info: ErrorInfo) -> float:
        seconds = self.block_seconds(info)
        self._blocked_until[model] = self._clock() + seconds
        if info.daily_quota:
            self._daily.add(model)
        else:
            self._daily.discard(model)
        return seconds

    def remaining(self, model: str) -> float:
        return max(0.0, self._blocked_until.get(model, 0.0) - self._clock())

    def available(self) -> list[str]:
        return [m for m in self.models if self.remaining(m) <= 0]

    def candidates(self) -> list[str]:
        """Modelos livres; se todos estiverem bloqueados, o que volta primeiro."""
        free = self.available()
        return free or [min(self.models, key=self.remaining)]

    def all_blocked(self) -> bool:
        return not self.available()

    def wait_seconds(self) -> float:
        return min(self.remaining(m) for m in self.models)

    def all_daily(self) -> bool:
        return all(m in self._daily and self.remaining(m) > 0 for m in self.models)
