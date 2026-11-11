# Empório da Música: agente de atendimento

Agente de atendimento por texto para a Empório da Música, a loja fictícia de instrumentos musicais de Campo Grande/MS do desafio técnico de AI Engineer da Artefact. Ele responde dúvidas de horário, preço, estoque, frete, pagamento, pedidos, trocas e garantia usando os CSVs e o manual de políticas da loja, recusa o que foge do escopo e passa para um atendente humano quando precisa.

## Demonstração online (bônus)

https://emporio-frontend.niceocean-f7122f5d.brazilsouth.azurecontainerapps.io

O enunciado não pede deploy. Publiquei a interface no Azure Container Apps para quem quiser testar sem instalar nada. O passo a passo está em [docs/deploy-azure.md](docs/deploy-azure.md).

Pontos para quem for testar:

- A primeira resposta pode demorar. O agente usa o plano gratuito do Gemini e às vezes troca de modelo no meio da conversa.
- A cota diária do Gemini é limitada. Se acabar, o agente responde com um aviso de instabilidade e os contatos da loja.
- A demo usa a data real. Os pedidos entregues da base são antigos, então um pedido de devolução aparece como fora do prazo. O caso dentro do prazo está em [examples/04_devolucao_arrependimento_no_prazo.md](examples/04_devolucao_arrependimento_no_prazo.md), gerado com data fixa.
- Para testar consulta de pedido: pedido 8 com o e-mail anacarol.ferreira@coldmail.com.
- O histórico de conversa do servidor se perde se o container reiniciar.

## O que o enunciado pede e onde está

| Pedido do enunciado | Onde está |
|---|---|
| Python como linguagem principal | `backend/` (Python 3.11 ou superior). A interface web, em TypeScript, é um extra |
| Persona alinhada com a loja | `backend/app/agent/prompts.py` e a seção Prompt abaixo |
| Responder com base no contexto disponibilizado | O agente só afirma o que as ferramentas retornam: SQLite montado a partir dos CSVs e busca no manual em PDF |
| Saber quando consultar dados e quando consultar políticas | 11 ferramentas em `backend/app/agent/tools.py`. Dados: produtos, promoções, pedidos, frete, pagamento e loja. Políticas: `search_policies`. Os cenários de avaliação conferem qual ferramenta o modelo escolheu |
| Lidar com perguntas fora do escopo | Regras no prompt, cenários `escopo_*` na avaliação e [examples/05_escopo_acessorios.md](examples/05_escopo_acessorios.md) |
| Decisões técnicas justificadas | Seção Decisões técnicas |
| Como rodar | Seção Como rodar |
| Limitações e o que faria com mais tempo | Seções com esses nomes |
| Uso de assistentes de código | Seção com esse nome |
| 3 a 5 conversas de exemplo | [examples/](examples/), com 5 conversas geradas pelo agente de verdade |
| Histórico de commits | `git log`: um commit por etapa, sem force-push |

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

O modelo escolhe a ferramenta e escreve a resposta. As contas (preço promocional, parcelas, frete, prazo de devolução, horário de funcionamento) são feitas em código, em `backend/app/services`, e têm testes. Assim o modelo não tem como errar uma conta.

## Como rodar

Requisitos: Python 3.11 ou superior e uma chave do Google AI Studio (https://aistudio.google.com/apikey). Node 20 ou superior só para a interface web, e Docker só se quiser usar o compose.

### Agente no terminal

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Preencha `GEMINI_API_KEY=` no `backend/.env`, sem aspas. O `.env` está no `.gitignore`.

```bash
python -m app.database.seed        # cria data/emporio.db a partir dos CSVs e gera docs/data_quality.md
python -m app.rag.build_index      # opcional: gera o índice com embeddings. Sem ele a busca usa só BM25
python -m app.agent.cli            # conversa com o agente no terminal
```

Opções da CLI: `--session ID` retoma uma conversa, `--show-tools` mostra as ferramentas chamadas e `--now 2025-10-28T10:00:00` fixa a data de hoje.

### API HTTP

```bash
cd backend
uvicorn app.main:create_app --factory --reload     # documentação em http://localhost:8000/docs
```

```bash
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "Quanto custa o Takamine GD20?"}'
curl localhost:8000/health
```

Rotas, variáveis e códigos de erro em [docs/api.md](docs/api.md).

### Interface web

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev                                         # http://localhost:3000
```

Precisa da API rodando em `localhost:8000`. Mais detalhes em [frontend/README.md](frontend/README.md).

### Docker

```bash
cp backend/.env.example backend/.env     # preencha GEMINI_API_KEY
docker compose up --build
```

O compose sobe a API em `localhost:8000` e a interface em `localhost:3000`. A imagem do backend já traz o banco da loja e o índice das políticas (só BM25). O histórico de conversas e o índice com embeddings ficam no volume `backend_state`.

### Data fixa para demonstrações

Os pedidos entregues da base são de 2025 até fevereiro de 2026, e a regra de arrependimento depende da data de hoje. Para reproduzir um caso, defina `NOW_OVERRIDE` no `.env`, por exemplo `NOW_OVERRIDE=2025-10-28T10:00:00`. Sem isso o agente usa a data real.

## Exemplos de conversa

Em [examples/](examples/), geradas com o Gemini de verdade:

| Arquivo | Situação |
|---|---|
| `01_catalogo_violoes_ate_1000.md` | violões até R$ 1.000, consulta ao catálogo |
| `02_catalogo_preco_takamine_gd20.md` | preço do Takamine GD20, que tem promoção inativa |
| `03_loja_endereco.md` | endereço e horário da loja |
| `04_devolucao_arrependimento_no_prazo.md` | arrependimento: regra de 7 dias aplicada em código, com data fixa |
| `05_escopo_acessorios.md` | pergunta fora do escopo (a loja não vende acessórios) |

Para gerar de novo, dentro de `backend/`:

```bash
python -m app.eval --live --export-examples ../examples \
  --id catalogo_violoes_ate_1000 --id catalogo_preco_takamine_gd20 \
  --id loja_endereco --id devolucao_arrependimento_no_prazo --id escopo_acessorios
```

## Decisões técnicas e justificativas

### Abordagem: function calling com loop próprio

O problema tem poucas ferramentas e um fluxo curto, então não usei framework de agentes. Um loop explícito (`app/agent/agent.py`) me deixa validar os argumentos de cada chamada com Pydantic, limitar as rodadas, registrar o rastro das ferramentas e tratar falhas sem derrubar a conversa. O mesmo modelo Pydantic gera o JSON Schema enviado ao Gemini, então só existe uma definição de cada ferramenta.

### Modelo e provedor: Google Gemini

Uso o Gemini para gerar respostas (function calling) e para os embeddings, com uma única chave. Como o plano gratuito tem limite diário, escrevi um failover entre modelos (`app/core/gemini_failover.py`): erro 429 ou 404 troca de modelo, erro 5xx tenta de novo antes de trocar, e cota diária esgotada bloqueia o modelo até a virada do dia. Os nomes ficam no `.env` (`GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`), porque mudam com frequência.

### Retrieval das políticas: RAG híbrido

O PDF tem 8 páginas e é dividido em 25 chunks, um por seção ou subseção, cada um com o título da seção-mãe. As tabelas ficam inteiras no mesmo chunk. A busca combina BM25 em português (sem acento, com expansão de vocabulário, por exemplo "devolver" leva a "arrependimento") e embeddings do Gemini, fundidos por RRF. Se o embedding falhar por cota ou rede, cai para só BM25. O manual caberia inteiro no prompt, mas mantive o RAG porque o enunciado pede consulta sob demanda e porque o índice serve para manuais maiores. Detalhes em [docs/rag.md](docs/rag.md).

### Prompt

A persona é informal e profissional, com mensagens curtas de chat e no máximo um emoji. A regra principal é afirmar só o que as ferramentas confirmarem. O prompt também define o escopo (a loja não vende acessórios), a privacidade em pedidos e a segurança: mensagens do cliente, resultados de ferramentas e trechos do manual são tratados como dados, nunca como ordens, o que protege contra prompt injection.

### Interface

Fiz três, nesta ordem. Primeiro a CLI. O agente é uma classe (`Agent.reply(session_id, texto)`) que não depende de interface, então depois expus a mesma lógica numa API FastAPI e, por cima dela, numa interface web em Next.js com AI SDK UI. O enunciado pede foco no agente, e por isso as duas últimas vieram depois do núcleo testado. A interface mostra a resposta inteira de uma vez, porque a API não faz streaming.

### Persistência do histórico

Dois SQLites separados. Um guarda os dados da loja e é recriado pelo seed. O outro (`data/conversations.db`) guarda o histórico por `session_id` e os encaminhamentos à equipe, então recriar a base da loja não apaga conversas. O histórico guarda só o texto das mensagens, sem os resultados das ferramentas. Na interface web, o `session_id` fica no `localStorage` e a página busca o histórico em `GET /chat/{session_id}/history` ao abrir, então a conversa volta depois de recarregar.

### Tratamento dos dados

Os CSVs viram um SQLite com tipos corretos, `specs` em JSON e colunas normalizadas (sem acento, minúsculas) para a busca tolerar erro de digitação. O seed valida os dados e registra as inconsistências em [docs/data_quality.md](docs/data_quality.md): 0 erros, 9 avisos e 3 informações.

### Privacidade

Dados de pedido só aparecem com o número do pedido mais o e-mail ou telefone cadastrados. "Pedido não existe" e "dados não conferem" geram a mesma resposta, para não revelar quais pedidos existem. E-mail e telefone são mascarados no rastro das ferramentas.

## Armadilhas nos dados e no manual

As decisões completas estão em [docs/premissas.md](docs/premissas.md). As principais:

- Promoção inativa: só vale `is_active = 1`. O Takamine GD20 tem promoção inativa, então o agente informa o preço cheio e não promete o desconto antigo.
- O desconto de 5% do PIX não vale sobre preço já promocional. A regra está em código.
- Produto esgotado, descontinuado ou "em breve" recebe o status real e alternativas, em vez de só olhar o estoque.
- `total_brl` não bate com a soma dos itens nos pedidos 3 e 20. O agente usa o total registrado.
- O manual traz dois telefones e o e-mail grafado com e sem acento. O agente informa os dois telefones, cada um com seu rótulo, e usa o e-mail sem acento.
- Para o arrependimento, a base só tem a data prevista de entrega. Uso essa data como data de recebimento e o agente avisa quando o prazo está perto do limite.

## Testes e avaliação

Os comandos abaixo rodam dentro de `backend/`.

```bash
python -m pytest                                   # mais de 300 testes, sem rede e sem chave
python -m app.eval --core                          # cenários rápidos, offline (ferramentas e dados, sem LLM)
python -m app.eval --live --core --report ../docs/avaliacao_ao_vivo.md   # com o Gemini de verdade
python -m app.eval --list                          # lista os 30 cenários
```

No modo `--live` o modelo decide sozinho, e para cada cenário o eval confere as ferramentas chamadas, os dados retornados e o texto da resposta (por exemplo: não prometer desconto de promoção encerrada, não vazar dado de outro cliente, não revelar o prompt). O resultado da última execução está em [docs/avaliacao_ao_vivo.md](docs/avaliacao_ao_vivo.md). Como funciona o eval: [docs/avaliacao.md](docs/avaliacao.md).

## Limitações conhecidas

- Latência. Em execuções ao vivo, alguns cenários levaram dezenas de segundos. O eval mostra o modelo usado e os avisos de failover para identificar a causa, mas não resolvi isso por completo.
- Os nomes dos modelos de reserva dependem da conta do AI Studio e precisam ser conferidos no `.env`. Um nome inexistente só bloqueia aquele modelo por um tempo, e o agente passa ao próximo.
- O limiar semântico do RAG (`DEFAULT_MIN_SEMANTIC = 0.45`) não foi calibrado com perguntas rotuladas. Ele só filtra trechos sem nenhum termo em comum com a pergunta.
- A busca híbrida gasta uma chamada de embedding por pergunta nova (há cache por texto).
- O agente só consulta. Ele não altera, cancela nem reembolsa pedidos, e nesses casos encaminha à equipe.
- O manual não define região metropolitana. Assumi só Campo Grande para frete grátis, e fora dela o agente informa modalidades e prazos sem inventar valor.
- Sem streaming real: a API responde em JSON depois que o agente termina.
- Na demo do Azure o disco é efêmero, o backend roda em uma réplica e a cota do Gemini é a do plano gratuito.
- A avaliação cobre cenários escritos por mim. Não garante o comportamento em todas as conversas reais.

## O que faria com mais tempo

- Streaming da resposta palavra por palavra, na API e na interface.
- Calibrar o limiar do RAG com um conjunto de perguntas rotuladas e medir a recuperação.
- Registrar tempo e modelo de cada chamada ao LLM e investigar a latência a fundo.
- Avaliar também com um segundo modelo como juiz, além das checagens por padrão de texto.
- Conectar o encaminhamento à equipe a um canal real (e-mail ou WhatsApp) em vez de só registrar o protocolo.
- Guardar o histórico num banco gerenciado, para não depender do disco do container.

## Uso de assistentes de código

Usei o Claude (Anthropic) em conversas no chat durante todo o projeto: para discutir a arquitetura, escrever e revisar código, testes e documentação, e para interpretar os resultados da avaliação ao vivo. Trabalhei por etapas (dados, RAG, ferramentas, agente, avaliação, API, exemplos, Docker, interface, deploy) com um commit por etapa. Em cada uma eu pedia os arquivos, rodava os testes e a avaliação na minha máquina, devolvia os erros e as saídas e decidia o que aceitar, corrigir ou descartar.

As decisões de direção foram minhas: usar o Gemini com failover entre modelos (a partir de como já tratava limite de cota em outro projeto meu), pedir a persistência do histórico na interface, definir a identidade visual e publicar a demo no Azure como bônus. Um exemplo de ajuste feito no processo: a avaliação ao vivo reprovou um cenário de segurança porque a checagem exigia uma frase exata de recusa, embora o agente não tivesse vazado nada. Corrigi a checagem e acrescentei ao prompt uma recusa curta e simpática.

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
  Dockerfile
frontend/          interface de chat em Next.js (AI SDK UI)
docs/              arquitetura, premissas, qualidade dos dados, RAG, avaliação, API e deploy
examples/          conversas de exemplo
docker-compose.yml
.github/workflows/ publicação das imagens no GHCR
```
