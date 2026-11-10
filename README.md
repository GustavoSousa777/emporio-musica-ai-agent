# Empório da Música: agente de atendimento

Protótipo de um agente de atendimento por mensagem de texto para a Empório da Música, loja fictícia de instrumentos musicais de Campo Grande/MS. Feito para o Desafio Técnico AI Engineer da Artefact.

O agente responde dúvidas de horário, preço, estoque, frete, pagamento, pedidos, trocas e garantia usando **só** os dados e o manual de políticas fornecidos. Ele sabe quando consultar dados (preço, estoque, pedido) e quando consultar políticas (troca, horário, pagamento), recusa com simpatia o que está fora do escopo e encaminha a um atendente humano quando precisa.

- Conversas de exemplo: [examples/](examples/)
- API HTTP: [docs/api.md](docs/api.md)
- Resultado da avaliação com o Gemini de verdade: [docs/avaliacao_ao_vivo.md](docs/avaliacao_ao_vivo.md)
- Premissas sobre ambiguidades: [docs/premissas.md](docs/premissas.md)
- Qualidade dos dados: [docs/data_quality.md](docs/data_quality.md)

## Como funciona

```
mensagem do cliente
      |
      v
  agente (Gemini, function calling, no máximo 6 rodadas de ferramentas)
      |
      +--> ferramentas de dados  --> serviços em Python --> SQLite (produtos, promoções, pedidos...)
      +--> search_policies       --> RAG híbrido (BM25 + embeddings) --> manual de políticas (PDF)
      +--> escalate_to_human     --> protocolo ATD-0000N, registrado em SQLite
      |
      v
resposta em português, com a persona da loja
```

A regra central: **o LLM decide qual ferramenta chamar e redige a resposta. Toda conta é feita em código.** Preço promocional, parcelas, frete, prazo de devolução e horário de funcionamento são funções determinísticas e testadas em `backend/app/services`. Assim o resultado é reproduzível e o modelo não tem como errar uma conta.

## Como rodar

Requisitos: Python 3.11 ou superior e uma chave do Google AI Studio (https://aistudio.google.com/apikey).

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Edite `backend/.env` e preencha `GEMINI_API_KEY=` com a sua chave (sem aspas). O `.env` está no `.gitignore`.

```bash
python -m app.database.seed        # cria data/emporio.db a partir dos CSVs e gera docs/data_quality.md
python -m app.rag.build_index      # (opcional) gera o índice com embeddings; sem ele a busca usa só BM25
python -m app.agent.cli            # conversa com o agente no terminal
```

Opções da CLI: `--session ID` (retoma uma conversa) e `--show-tools` (mostra quais ferramentas o agente chamou).

### API HTTP

```bash
cd backend
uvicorn app.main:create_app --factory --reload     # http://localhost:8000/docs
```

```bash
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "Quanto custa o Takamine GD20?"}'
curl localhost:8000/health
```

Detalhes, variáveis e códigos de erro em [docs/api.md](docs/api.md).

### Docker

```bash
cp backend/.env.example backend/.env     # preencha GEMINI_API_KEY
docker compose up --build
curl localhost:8000/health
```

A imagem já traz o banco da loja e o índice das políticas (BM25). O histórico de conversas e o índice com embeddings ficam no volume `backend_state`. Para trocar a porta do host: `HOST_PORT=8080 docker compose up`.

### Data fixa para demonstrações

Todos os pedidos entregues da base são antigos (2025 a fevereiro de 2026), e a regra de arrependimento depende da data de hoje. Para reproduzir um cenário, defina `NOW_OVERRIDE` no `.env`, por exemplo `NOW_OVERRIDE=2025-10-28T10:00:00`. Sem isso o agente usa a data real.

### Testes e avaliação

```bash
python -m pytest                                   # testes unitários e de integração, sem rede e sem chave
python -m app.eval --core                          # cenários rápidos, offline (ferramentas e dados, sem LLM)
python -m app.eval --live --core --report ../docs/avaliacao_ao_vivo.md   # com o Gemini de verdade
python -m app.eval --list                          # lista os cenários
```

Para gerar as conversas de exemplo a partir de execuções reais:

```bash
python -m app.eval --live --export-examples ../examples \
  --id catalogo_preco_takamine_gd20 --id catalogo_violoes_ate_1000 \
  --id devolucao_arrependimento_no_prazo --id escopo_acessorios
```

O modo `--live` roda cenários em que o modelo decide sozinho e confere, para cada um, as ferramentas chamadas, os dados retornados e o texto da resposta (por exemplo: não prometer desconto de promoção encerrada, não vazar dado de outro cliente, não revelar o prompt). Com `--export-examples PASTA` ele grava as conversas que passaram como arquivos markdown, que é como se geram os exemplos de `examples/` (comando na seção abaixo).

## Decisões técnicas e justificativas

**Abordagem: function calling com loop próprio, sem framework de agentes.** O problema tem poucas ferramentas e fluxo curto. Um loop explícito (`app/agent/agent.py`) me deixa validar os argumentos de cada chamada com Pydantic, limitar as rodadas, registrar o rastro das ferramentas e tratar falhas sem derrubar a conversa. Um framework adicionaria abstração sem resolver nada disso. O mesmo modelo Pydantic gera o JSON Schema enviado ao Gemini, então não há duas definições para manter em sincronia.

**Modelo e provedor: Google Gemini.** Usado para geração (function calling) e para embeddings, com uma única chave. Como o plano gratuito tem limite diário, há um **failover entre modelos** (`app/core/gemini_failover.py`): erro 429 ou 404 troca de modelo, erro 5xx tenta de novo antes de trocar, e cota diária esgotada bloqueia o modelo até a virada do dia. Os nomes dos modelos ficam no `.env` (`GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`).

**Retrieval das políticas: RAG híbrido.** O PDF (8 páginas) é dividido em 25 chunks, um por seção ou subseção, cada um com o título da seção-mãe, e as tabelas ficam inteiras no mesmo chunk. A busca combina BM25 em português (sem acento, com expansão de vocabulário, por exemplo "devolver" leva a "arrependimento") e embeddings do Gemini, fundidos por RRF. Se o embedding falhar por cota ou rede, o sistema cai para só BM25. O manual caberia inteiro no prompt, mas mantive o RAG porque o enunciado pede consulta sob demanda e porque o índice escala para manuais maiores. Detalhes em [docs/rag.md](docs/rag.md).

**Prompt.** Persona informal e profissional, mensagens curtas de chat e no máximo um emoji. A "regra de ouro" é só afirmar o que as ferramentas confirmarem. O prompt também define o escopo (a loja não vende acessórios), a privacidade em pedidos e a segurança: mensagens do cliente, resultados de ferramentas e trechos do manual são tratados como **dados**, não como ordens, o que protege contra prompt injection.

**Persistência.** Dois SQLites separados. Um guarda os dados da loja e é recriado pelo seed. O outro (`data/conversations.db`) guarda o histórico por `session_id` e os encaminhamentos à equipe, e por isso recriar a base da loja não apaga conversas. O histórico guarda só o texto das mensagens, não os resultados das ferramentas.

**Interface: CLI.** O enunciado dá liberdade e pede foco no agente, então a interface é um terminal (`python -m app.agent.cli`). O agente é uma classe (`Agent.reply(session_id, texto)`) independente da interface, o que permitiu expor a mesma lógica por uma API FastAPI (`app/main.py`) sem alterar o agente.

**Tratamento dos dados.** Os CSVs viram um SQLite com tipos corretos, `specs` em JSON e colunas normalizadas (sem acento, minúsculas) para busca tolerante a erro de digitação. O seed valida os dados e registra as inconsistências em [docs/data_quality.md](docs/data_quality.md) (0 erros, 9 avisos, 3 informações).

**Privacidade.** Dados de pedido só aparecem com número do pedido mais e-mail ou telefone cadastrados. "Pedido não existe" e "dados não conferem" geram a mesma resposta, para não revelar quais pedidos existem. E-mail e telefone são mascarados no rastro das ferramentas.

## Armadilhas encontradas nos dados e no manual

As decisões completas estão em [docs/premissas.md](docs/premissas.md). As principais:

- **Promoção inativa:** só vale `is_active = 1`. O Takamine GD20 tem promoção inativa, então o agente informa o preço cheio e nunca promete o desconto antigo.
- **PIX não é cumulativo:** o desconto de 5% não vale sobre preço já promocional (regra em código).
- **Estoque e status:** produto esgotado, descontinuado ou "em breve" recebe o status real e alternativas, em vez de só olhar o estoque.
- **Totais divergentes:** `total_brl` não bate com a soma dos itens nos pedidos 3 e 20. O agente usa o total registrado.
- **Contatos duplicados no manual:** dois telefones e e-mail com e sem acento. O agente informa os dois telefones, cada um com seu rótulo, e usa o e-mail sem acento.
- **Arrependimento:** a base só tem a data prevista de entrega. Ela é usada como data de recebimento e o agente avisa isso quando o prazo está próximo do limite.

## Limitações conhecidas

- **Latência.** Em execuções ao vivo, alguns cenários levaram dezenas de segundos. O eval agora mostra o modelo usado e os avisos de failover para identificar a causa, mas ainda não resolvi isso por completo.
- **Nomes dos modelos de reserva** dependem da conta do AI Studio e precisam ser conferidos no `.env`. Um nome inexistente só bloqueia aquele modelo por um tempo e o agente passa ao próximo.
- **Limiar semântico do RAG** (`DEFAULT_MIN_SEMANTIC = 0.45`) não foi calibrado com um conjunto de perguntas. Ele só filtra trechos sem nenhum termo em comum com a pergunta.
- **A busca híbrida** gasta uma chamada de embedding por pergunta nova (há cache por texto).
- **O agente só consulta.** Ele não altera, cancela nem reembolsa pedidos: nesses casos encaminha à equipe.
- **Região metropolitana** não é definida no manual. Assumi apenas Campo Grande para frete grátis. Fora dela o agente informa modalidades e prazos, sem inventar valor.
- **Sem interface web nem streaming.** A API responde em JSON, depois que o agente termina.
- A avaliação cobre cenários escritos por mim. Não é uma garantia contra todas as conversas reais.

## O que faria com mais tempo

- Streaming da resposta na API e uma interface web simples.
- Calibrar o limiar do RAG com um conjunto de perguntas rotuladas e medir a recuperação.
- Registrar tempo e modelo de cada chamada ao LLM e investigar a latência a fundo.
- Avaliar também com um segundo modelo como juiz, além das checagens por padrão de texto.
- Conectar o encaminhamento à equipe a um canal real (e-mail ou WhatsApp) em vez de só registrar o protocolo.

## Uso de assistentes de código

Usei o **Claude (Anthropic)** em conversas no chat durante todo o desenvolvimento: para discutir a arquitetura, escrever e revisar partes do código, dos testes e da documentação, e para analisar os resultados da avaliação e propor ajustes de prompt. Eu defini o problema, escolhi as decisões listadas acima, rodei os testes e a avaliação ao vivo na minha máquina e fui o responsável por aceitar, corrigir ou rejeitar cada sugestão. Um exemplo concreto: a avaliação ao vivo reprovou um cenário de segurança porque a checagem exigia uma frase exata de recusa, embora o agente não tivesse vazado nada. Corrigimos a checagem e acrescentamos ao prompt uma recusa curta e simpática.

## Estrutura do repositório

```
backend/
  app/core/        configuração, relógio (NOW_OVERRIDE), regras do manual, dinheiro, failover do Gemini
  app/database/    schema, limpeza, validação e seed do SQLite
  app/services/    produtos, promoções, pagamentos, frete, pedidos, devoluções, loja
  app/rag/         extração do PDF, chunking, BM25, embeddings, índice e retriever
  app/agent/       prompt, ferramentas, loop, cliente Gemini, memória, CLI
  app/api/         rotas /chat e /health, esquemas, limite de taxa e chave de API
  app/main.py      criação do app FastAPI
  app/eval/        cenários de avaliação (offline e ao vivo) e exportação de exemplos
  data/raw/        CSVs originais
  data/policies/   manual de políticas (PDF)
  tests/
Dockerfile em backend/ e docker-compose.yml na raiz
docs/              arquitetura, premissas, qualidade dos dados, RAG e avaliação
examples/          conversas de exemplo
frontend/          reservado, sem implementação
```
