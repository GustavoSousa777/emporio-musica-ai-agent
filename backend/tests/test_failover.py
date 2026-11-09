from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.gemini_failover import (
    LLMUnavailableError,
    ModelPool,
    classify_error,
    seconds_until_quota_reset,
)
from app.rag.embeddings import embed_with_failover


class FakeAPIError(Exception):
    def __init__(self, code, details=None, message="erro"):
        super().__init__(message)
        self.code = code
        self.details = details


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


DAILY = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
PER_MINUTE = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"retryDelay": "34s"}]}}


def test_429_por_dia_e_detectado_como_cota_diaria():
    info = classify_error(FakeAPIError(429, DAILY))
    assert info.daily_quota and info.switch_model and not info.retry_same_model


def test_429_por_minuto_le_o_retry_delay():
    info = classify_error(FakeAPIError(429, PER_MINUTE))
    assert not info.daily_quota and info.retry_after == 34.0


@pytest.mark.parametrize("code", [500, 503])
def test_5xx_tenta_de_novo_e_troca(code):
    info = classify_error(FakeAPIError(code))
    assert info.retry_same_model and info.switch_model


def test_404_troca_sem_retentar():
    info = classify_error(FakeAPIError(404))
    assert info.switch_model and not info.retry_same_model


def test_400_nao_troca_de_modelo():
    assert not classify_error(FakeAPIError(400)).switch_model


def test_erro_de_conexao_por_nome_da_classe():
    class APIConnectionError(Exception):
        pass

    info = classify_error(APIConnectionError("sem rede"))
    assert info.is_connection and info.switch_model


def test_pool_bloqueia_e_libera_com_o_tempo():
    clock = Clock()
    pool = ModelPool(["a", "b"], clock=clock)
    seconds = pool.block("a", classify_error(FakeAPIError(429, PER_MINUTE)))
    assert seconds == 34.0 and pool.candidates() == ["b"]
    clock.t += 35
    assert pool.candidates() == ["a", "b"]


def test_pool_404_bloqueia_por_uma_hora():
    pool = ModelPool(["a", "b"], clock=Clock())
    assert pool.block("a", classify_error(FakeAPIError(404))) == 3600.0


def test_pool_cota_diaria_bloqueia_ate_a_virada_do_dia():
    pacific = ZoneInfo("America/Los_Angeles")
    pool = ModelPool(["a"], clock=Clock(), wall_now=lambda: datetime(2026, 3, 23, 22, 0, tzinfo=pacific))
    assert pool.block("a", classify_error(FakeAPIError(429, DAILY))) == 2 * 3600
    assert pool.all_daily()


def test_seconds_until_quota_reset_tem_piso_de_1s():
    pacific = ZoneInfo("America/Los_Angeles")
    assert seconds_until_quota_reset(datetime(2026, 3, 23, 23, 0, tzinfo=pacific)) == 3600


def test_todos_bloqueados_devolve_o_que_volta_primeiro():
    clock = Clock()
    pool = ModelPool(["a", "b"], clock=clock)
    pool.block("a", classify_error(FakeAPIError(429, PER_MINUTE)))
    pool.block("b", classify_error(FakeAPIError(429, None)))  # 60 s padrão
    assert pool.all_blocked() and pool.candidates() == ["a"]
    assert pool.wait_seconds() == 34.0


def test_pool_exige_ao_menos_um_modelo():
    with pytest.raises(ValueError):
        ModelPool([])


# --- embeddings com failover ----------------------------------------------------------------
class StubEmbedder:
    dims = 2

    def __init__(self, model, error=None):
        self.model, self.error = model, error

    def embed_documents(self, texts, titles=None):
        if self.error:
            raise self.error
        return [[1.0, 0.0] for _ in texts]


def test_embedding_passa_para_o_proximo_modelo_quando_a_cota_acaba():
    errors = {"m1": FakeAPIError(429, DAILY)}
    vectors, embedder = embed_with_failover(
        ["x", "y"], None, ["m1", "m2"], lambda model: StubEmbedder(model, errors.get(model))
    )
    assert embedder.model == "m2" and len(vectors) == 2


def test_embedding_erro_de_requisicao_nao_troca_de_modelo():
    with pytest.raises(FakeAPIError):
        embed_with_failover(["x"], None, ["m1", "m2"], lambda model: StubEmbedder(model, FakeAPIError(400)))


def test_embedding_todos_falham_levanta_indisponivel_com_flag_diaria():
    with pytest.raises(LLMUnavailableError) as info:
        embed_with_failover(["x"], None, ["m1", "m2"], lambda model: StubEmbedder(model, FakeAPIError(429, DAILY)))
    assert info.value.daily_quota


def test_504_troca_de_modelo_sem_retentar():
    info = classify_error(FakeAPIError(504))
    assert info.switch_model and not info.retry_same_model
