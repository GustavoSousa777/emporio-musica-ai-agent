"""Fixtures: banco SQLite gerado a partir dos CSVs reais, em pasta temporária."""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from app.database.connection import get_connection
from app.database.seed import seed_database


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "emporio.db"
    seed_database(db_path=path)
    return path


@pytest.fixture()
def conn(db_path):
    connection = get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture()
def mutable_conn(db_path, tmp_path):
    """Cópia do banco para testes que alteram dados."""
    copy = tmp_path / "copy.db"
    shutil.copy(db_path, copy)
    connection = get_connection(copy)
    yield connection
    connection.close()


# Dados de verificação reais da base (clientes dos pedidos usados nos testes)
CUSTOMERS = {
    # order_id: (e-mail, telefone)
    1: ("pedro.oliveira@jmail.com", "(67) 98432-1098"),   # entregue, PIX
    8: ("anacarol.ferreira@coldmail.com", "(67) 99654-7821"),  # enviado
}


@pytest.fixture()
def customers():
    return CUSTOMERS


# --- Fixtures do RAG e do agente (Etapas 3 e 4) ------------------------------------------
@pytest.fixture(scope="session")
def lexical_index():
    """Índice das políticas só com BM25: não chama API nem precisa de chave."""
    from app.rag.retriever import build_index

    return build_index(lexical_only=True)


@pytest.fixture(scope="session")
def retriever(lexical_index):
    from app.rag.retriever import Retriever

    return Retriever(lexical_index, embedder=None, mode="lexical")


@pytest.fixture()
def conversations(tmp_path):
    from app.agent.memory import ConversationStore

    return ConversationStore(tmp_path / "conversations.db")
