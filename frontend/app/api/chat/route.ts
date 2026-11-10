import { createUIMessageStream, createUIMessageStreamResponse } from "ai";
import type { BackendReply, ChatMessage } from "@/lib/types";

export const maxDuration = 120;

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;
const SESSION_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

const ERROR_MESSAGES: Record<number, string> = {
  401: "A interface não está autorizada a falar com o atendimento.",
  422: "Não consegui entender essa mensagem. Confira se ela não está vazia nem muito longa.",
  429: "Muitas mensagens em pouco tempo. Espere um instante e tente de novo.",
  503: "O atendimento está fora do ar no momento. Tente de novo em alguns minutos.",
};

function failure(message: string, status: number) {
  return new Response(message, { status, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

export async function POST(request: Request) {
  let payload: { message?: unknown; session_id?: unknown };
  try {
    payload = await request.json();
  } catch {
    return failure("Requisição inválida.", 400);
  }

  const message = typeof payload.message === "string" ? payload.message.trim() : "";
  const sessionId = typeof payload.session_id === "string" ? payload.session_id : "";
  if (!message || !SESSION_PATTERN.test(sessionId)) {
    return failure(ERROR_MESSAGES[422], 422);
  }

  let backend: Response;
  try {
    backend = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(BACKEND_API_KEY ? { "X-API-Key": BACKEND_API_KEY } : {}),
      },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal: AbortSignal.timeout(110_000),
      cache: "no-store",
    });
  } catch {
    return failure("Não consegui falar com o atendimento. Verifique se o backend está no ar.", 502);
  }

  if (!backend.ok) {
    const text = ERROR_MESSAGES[backend.status] ?? "Algo deu errado do nosso lado. Tente de novo em instantes.";
    return failure(text, backend.status === 429 ? 429 : 502);
  }

  const data = (await backend.json()) as BackendReply;

  const stream = createUIMessageStream<ChatMessage>({
    execute: ({ writer }) => {
      const id = crypto.randomUUID();
      writer.write({ type: "text-start", id });
      writer.write({ type: "text-delta", id, delta: data.reply });
      writer.write({ type: "text-end", id });
      writer.write({
        type: "data-meta",
        data: { tools: data.tools, escalated: data.escalated, degraded: data.degraded },
      });
    },
  });

  return createUIMessageStreamResponse({ stream });
}

export async function GET(request: Request) {
  const sessionId = new URL(request.url).searchParams.get("session_id") ?? "";
  if (!SESSION_PATTERN.test(sessionId)) {
    return failure("Sessão inválida.", 422);
  }

  try {
    const backend = await fetch(`${BACKEND_URL}/chat/${sessionId}/history`, {
      headers: BACKEND_API_KEY ? { "X-API-Key": BACKEND_API_KEY } : undefined,
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });
    if (!backend.ok) {
      return failure("Não foi possível carregar o histórico.", 502);
    }
    return Response.json(await backend.json());
  } catch {
    return failure("Não consegui falar com o atendimento.", 502);
  }
}
