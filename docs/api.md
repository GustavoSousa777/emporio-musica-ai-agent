# API HTTP

FastAPI em `backend/app/main.py`. Documentação interativa em `/docs`.

```bash
cd backend
uvicorn app.main:create_app --factory
```

## POST /chat

Corpo:

```json
{"message": "Quanto custa o Takamine GD20?", "session_id": "opcional"}
```

- `message`: 1 a 2000 caracteres, não pode ser só espaços.
- `session_id`: letras, números, `_` e `-`, até 64 caracteres. Se omitido, a API gera um e devolve. Reenvie o mesmo para continuar a conversa.

Resposta 200:

```json
{
  "reply": "O Takamine GD20 custa ...",
  "session_id": "3f9c0b7e5d2a4c1e8b6a7d90c1e2f345",
  "tools": [{"name": "search_products", "ok": true}],
  "escalated": false,
  "degraded": false,
  "model": "gemini-3.8-flash",
  "input_truncated": false
}
```

`tools` traz só nome e status, sem argumentos, para não expor e-mail ou telefone. `degraded` é `true` quando o modelo estava indisponível e a resposta é o aviso de contingência (a API ainda responde 200).

| Código | Quando |
|---|---|
| 401 | `API_KEY` configurada e cabeçalho `X-API-Key` ausente ou errado |
| 422 | corpo inválido (mensagem vazia ou longa demais, `session_id` inválido) |
| 429 | limite de taxa excedido; vem com `Retry-After` |
| 500 | erro inesperado; a mensagem não revela detalhes |
| 503 | agente não iniciou (por exemplo, sem `GEMINI_API_KEY`) |

## GET /health

Sempre aberto, sem exigir chave. Devolve 200 com `status: "ok"` quando o banco da loja e o índice das políticas estão carregados, e 503 com `status: "degraded"` e `detail` caso contrário. É o que o `HEALTHCHECK` do Docker usa.

## Variáveis (backend/.env)

| Variável | Padrão | Função |
|---|---|---|
| `CORS_ORIGINS` | vazio | origens liberadas, separadas por vírgula |
| `RATE_LIMIT_PER_MINUTE` | 30 | mensagens por minuto por IP em `/chat` (0 desliga) |
| `API_KEY` | vazio | se preenchida, `/chat` exige `X-API-Key` |
| `TRUST_PROXY` | false | usa o primeiro IP de `X-Forwarded-For` como cliente |

Só habilite `TRUST_PROXY` atrás de um proxy que sobrescreva esse cabeçalho. O limite de taxa fica em memória, por processo.

## Testes

`backend/tests/test_api.py` usa um LLM roteirizado: não precisa de rede nem de chave.
