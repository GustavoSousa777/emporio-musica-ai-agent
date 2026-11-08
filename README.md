# Empório da Música: agente de atendimento

Protótipo de agente de atendimento para a Empório da Música (loja fictícia de instrumentos musicais em Campo Grande/MS), desenvolvido para o Desafio Técnico AI Engineer da Artefact.

> **Status:** em desenvolvimento. Concluídas: estrutura do projeto, ingestão e tratamento dos dados, serviços e regras de negócio (com testes). Próximas: RAG das políticas, agente com Google Gemini, API, exemplos de conversa e containerização.

## Estrutura

```
backend/            Python: agente, regras de negócio, RAG, dados
  app/core/         configuração, relógio, regras do manual, utilitários
  app/database/     schema, limpeza, validação e seed do SQLite
  app/services/     produtos, promoções, pedidos, devoluções, pagamento, frete, loja
  app/agent/        (Etapa 4) agente com function calling
  app/rag/          (Etapa 3) busca nas políticas
  app/api/          (Etapa 6) FastAPI
  data/raw/         CSVs originais
  data/policies/    manual de políticas (PDF)
  tests/
frontend/           (opcional) interface Next.js
examples/           conversas de exemplo
docs/               arquitetura, premissas e qualidade dos dados
```

## Como rodar localmente

Requisitos: Python 3.11+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env

python -m app.database.seed        # cria data/emporio.db e docs/data_quality.md
python -m pytest                   # executa os testes
```

A chave do Gemini (`GEMINI_API_KEY`) só será necessária a partir da etapa do agente.

### Data fixa para demonstrações

Regras que dependem de prazo (devolução em 7 dias) usam a data de hoje. Para reproduzir um cenário, defina `NOW_OVERRIDE` no `.env`, por exemplo `NOW_OVERRIDE=2025-10-28T10:00:00`.

## Decisões técnicas

*A preencher conforme as etapas avançam: abordagem do agente, modelo e provedor, retrieval, estratégia de prompt, persistência do histórico.*

Decisões já tomadas:

- **Regras em código, não no LLM.** Preço promocional, parcelas, frete, prazos de devolução e horário de funcionamento são funções testadas em `app/services`. O LLM só escolhe a ferramenta e redige a resposta.
- **Dados tratados no seed.** CSVs viram um SQLite com tipos corretos, `specs` em JSON e colunas normalizadas (sem acento e minúsculas) para busca tolerante a erros de digitação.
- **Inconsistências registradas.** O seed valida os dados e gera [docs/data_quality.md](docs/data_quality.md).
- **Privacidade.** Dados de pedido só são exibidos após verificação por e-mail ou telefone.

## Premissas

Interpretações de pontos ambíguos do enunciado e do manual: [docs/premissas.md](docs/premissas.md).

## Limitações conhecidas

*A preencher ao final.*

## Uso de assistentes de código

*A preencher ao final: quais ferramentas foram usadas e como.*

## Demo online

*Opcional, a preencher se o deploy for feito. Incluir as limitações da demo.*
