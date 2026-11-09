# RAG das políticas e agente

## RAG (backend/app/rag)

| Etapa | Arquivo | O que faz |
|---|---|---|
| Extração | `ingestion.py` | Lê o PDF com pdfplumber, remove cabeçalho, rodapé e capa, e detecta títulos pelo tamanho da fonte (14 pt = "3.", 12 pt = "3.1") |
| Chunking | `ingestion.py` | Um chunk por seção ou subseção (25 chunks). Cada chunk leva o título da seção-mãe. Tabelas ficam inteiras no mesmo chunk |
| Busca lexical | `lexical.py` | BM25 em português (sem acento, radical de 4 letras) com expansão de vocabulário ("devolver" → "arrependimento") |
| Embeddings | `embeddings.py` | Gemini (`gemini-embedding-001` ou `-2`), vetores normalizados, lotes de 10 com pausa |
| Índice | `retriever.py` | JSON em `data/index/policies_index.json`; reconstruído se o PDF mudar |
| Busca | `Retriever.search(query, k)` | BM25 + embeddings fundidos por RRF. Se o embedding falhar (cota, rede), usa só BM25 |

Decisões:
- O manual tem 8 páginas e caberia no prompt. O RAG foi mantido porque a regra do case é consultar políticas sob demanda, e o índice escala para manuais maiores.
- Sem chave, o RAG funciona só com BM25 (`RAG_MODE=lexical`), o que torna os testes offline e gratuitos.
- Todo o texto do manual vem de trechos recuperados. O agente não responde política de memória.

Pendente: calibrar `DEFAULT_MIN_SEMANTIC` (0.45) com chave real. Ele só filtra trechos sem nenhum termo em comum com a pergunta.

## Agente (backend/app/agent)

| Arquivo | Papel |
|---|---|
| `prompts.py` | Persona (informal e profissional), regras de escopo, privacidade e segurança |
| `tools.py` | 11 ferramentas com argumentos validados por Pydantic (o mesmo modelo gera o schema do Gemini) |
| `agent.py` | Loop: mensagem → ferramentas (máx. 6 rodadas) → resposta. Trata falhas sem derrubar a conversa |
| `gemini_llm.py` | Function calling do Gemini com failover entre modelos |
| `memory.py` | Histórico por `session_id` e fila de encaminhamentos (`handoffs`) em `data/conversations.db` |
| `factory.py`, `cli.py` | Montagem a partir do `.env` e conversa pelo terminal |

Failover (`app/core/gemini_failover.py`): erro 429 ou 404 troca de modelo; 5xx e queda de conexão tentam de novo antes de trocar; limite diário bloqueia o modelo até a virada do dia (meia-noite do Pacífico). Ao trocar de modelo no meio do ciclo de ferramentas, o histórico é reconstruído com a assinatura de contorno das "thought signatures" do Gemini 3.

Limites conhecidos:
- Os nomes dos modelos de reserva (`GEMINI_FALLBACK_MODELS`) precisam ser conferidos no AI Studio.
- A busca híbrida gasta uma chamada de embedding por pergunta nova (com cache por texto).
- A memória guarda só o texto das mensagens, não os resultados das ferramentas.
