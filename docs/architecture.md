# Arquitetura

Este documento cresce junto com o projeto. Estado atual: camada de dados e regras de negócio.

```
CSVs (data/raw) --seed--> SQLite --> services (regras determinísticas)
PDF (data/policies) --(Etapa 3)--> RAG
                                        \
                                         agente LLM + function calling (Etapa 4) --> API (Etapa 6) --> UI (Etapa 9)
```

## Camadas

- `app/core`: configuração, relógio (`NOW_OVERRIDE`), regras do manual (`rules.py`), dinheiro com `Decimal`, normalização de texto.
- `app/database`: schema, limpeza dos CSVs, validação e seed. Inconsistências viram linhas em `data_quality_issues` e o relatório `docs/data_quality.md`.
- `app/services`: uma função por pergunta de negócio (buscar produto, consultar pedido, checar devolução, calcular frete). Retornam modelos Pydantic e nunca dependem de LLM.

## Princípio

O LLM decide qual ferramenta chamar e redige a resposta. Toda conta (preço promocional, parcela, prazo, horário) é feita em código, para o resultado ser testável e reproduzível.

## A completar nas próximas etapas

RAG (Etapa 3), agente e persona (Etapa 4), API (Etapa 6), frontend (Etapa 9), containerização e deploy.
