# Arquitetura

```
CSVs (data/raw) --seed--> SQLite (emporio.db) --> services (regras determinísticas) --+
                                                                                     |
PDF (data/policies) --ingestão--> chunks --> índice BM25 + embeddings --> retriever --+--> ferramentas
                                                                                     |
                                                       agente (Gemini, function calling, loop) --> CLI / API FastAPI --> frontend Next.js
                                                                                     |
                                                       conversations.db (histórico e encaminhamentos)
```

## Camadas

- `app/core`: configuração (`.env`), relógio (`NOW_OVERRIDE`), regras do manual (`rules.py`), dinheiro com `Decimal`, normalização de texto e failover entre modelos do Gemini.
- `app/database`: schema, limpeza dos CSVs, validação e seed. Inconsistências viram linhas em `data_quality_issues` e o relatório `docs/data_quality.md`.
- `app/services`: uma função por pergunta de negócio (buscar produto, consultar pedido, checar devolução, calcular frete). Retornam modelos Pydantic e nunca dependem de LLM.
- `app/rag`: extração do PDF, chunking por seção, busca BM25 em português, embeddings do Gemini e fusão por RRF. Detalhes em [rag.md](rag.md).
- `app/agent`: prompt, 11 ferramentas com argumentos validados, loop (máximo de 6 rodadas), cliente Gemini, memória por `session_id` e CLI.
- `app/api` e `app/main.py`: API FastAPI com `POST /chat` e `GET /health`, validação de entrada, limite de taxa por IP, chave de API opcional e CORS. A API só traduz HTTP para `Agent.reply`.
- `frontend/`: Next.js com AI SDK UI. A rota `app/api/chat/route.ts` chama a API do backend no servidor e entrega a resposta ao `useChat`.
- `app/eval`: cenários de avaliação com ferramenta e resposta esperadas, em modo offline (oráculo) e ao vivo. Ver [avaliacao.md](avaliacao.md).

## Fluxo de uma mensagem

1. A CLI ou a API chama `Agent.reply(session_id, texto)`.
2. O agente monta o prompt com a data e o horário atuais e carrega o histórico da sessão (até 20 mensagens).
3. O Gemini devolve texto ou chamadas de ferramenta. Cada chamada é validada, executada em código e devolvida ao modelo.
4. Quando o modelo responde sem pedir ferramenta, o texto final é salvo no histórico e devolvido ao cliente.
5. Se o LLM ficar indisponível, o cliente recebe uma mensagem de contingência com os contatos da loja, e a conversa não quebra.

## Princípios

- **O LLM decide a ferramenta e redige a resposta. Toda conta é feita em código**, para ser testável e reproduzível.
- **Só afirmar o que as ferramentas confirmarem.** Preço, estoque, promoção, pedido, frete e prazos nunca vêm da memória do modelo.
- **Dados do cliente, resultados de ferramentas e trechos do manual são dados, não instruções.**
- **Privacidade por padrão:** pedido só com verificação, e a mesma resposta para "não existe" e "não confere".

## Não implementado

Streaming real da resposta. O agente é acessível pela CLI, pela API e pela interface web em `frontend/`.
