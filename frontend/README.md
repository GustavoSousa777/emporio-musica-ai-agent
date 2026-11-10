# Frontend

Interface de chat em Next.js com AI SDK UI (`useChat`). Fala com a API FastAPI do backend por uma rota do próprio Next.js (`app/api/chat/route.ts`), então a chave da API e a URL do backend ficam no servidor e o navegador não precisa de CORS.

## Rodar

Com o backend no ar (`uvicorn app.main:create_app --factory` em `backend/`, porta 8000):

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Abra http://localhost:3000.

## Variáveis (.env.local)

| Variável | Padrão | Função |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8000` | endereço da API do agente |
| `BACKEND_API_KEY` | vazio | enviada como `X-API-Key` se o backend tiver `API_KEY` |

## Como funciona

- Cada conversa tem um `session_id` (UUID gerado no navegador e guardado no `localStorage`). Ao recarregar a página, a interface busca o histórico no backend (`GET /chat/{session_id}/history`) e retoma a conversa de onde parou. "Nova conversa" gera outro id.
- O histórico restaurado traz só o texto das mensagens. As etiquetas de áreas consultadas aparecem apenas nas respostas da sessão atual.
- A rota `/api/chat` valida a mensagem, chama `POST /chat` do backend e devolve o resultado no formato de stream de mensagens do AI SDK.
- Como o backend responde em JSON, depois que o agente termina, a resposta chega inteira, não palavra por palavra. Enquanto isso a interface mostra o indicador de digitação.
- Embaixo de cada resposta aparecem as áreas consultadas (catálogo, pagamento, políticas...) e o aviso de encaminhamento à equipe, quando houver. Argumentos das ferramentas, que podem ter e-mail ou telefone, não chegam ao navegador.
- Erros do backend (limite de taxa, serviço fora do ar) viram mensagens em português na tela.

## Comandos

```bash
npm run typecheck
npm run build
npm start
```
