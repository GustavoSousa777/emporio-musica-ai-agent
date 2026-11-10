"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useEffect, useMemo, useRef, useState } from "react";
import Logo from "@/components/Logo";
import RichText from "@/components/RichText";
import type { ChatMessage } from "@/lib/types";

const STORAGE_KEY = "emporio:session";
const SESSION_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

const SUGGESTIONS = [
  "Quais violões vocês têm até R$ 1.000?",
  "Quanto custa o Takamine GD20?",
  "Qual o horário de funcionamento?",
  "Quero devolver um pedido",
];

const CAPABILITIES = [
  "Preço, estoque e promoções dos instrumentos",
  "Frete, prazos e formas de pagamento",
  "Status de pedidos, trocas e garantia",
  "Endereço e horário da loja",
];

const TOOL_LABELS: Record<string, string> = {
  search_products: "Catálogo",
  list_categories: "Catálogo",
  get_promotion_status: "Promoção",
  get_payment_options: "Pagamento",
  calculate_shipping: "Frete",
  get_store_info: "Loja",
  get_opening_status: "Horário",
  get_order_status: "Pedido",
  check_return_eligibility: "Devolução",
  search_policies: "Políticas",
  escalate_to_human: "Atendente",
};

type Boot = { sessionId: string; initial: ChatMessage[] };

function newSessionId() {
  return crypto.randomUUID();
}

function readStoredSession(): string | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value && SESSION_PATTERN.test(value) ? value : null;
  } catch {
    return null;
  }
}

function storeSession(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {}
}

async function loadHistory(sessionId: string): Promise<ChatMessage[]> {
  try {
    const response = await fetch(`/api/chat?session_id=${encodeURIComponent(sessionId)}`);
    if (!response.ok) return [];
    const data = (await response.json()) as { messages: { role: "user" | "assistant"; text: string }[] };
    return data.messages.map((message, index) => ({
      id: `history-${index}`,
      role: message.role,
      parts: [{ type: "text", text: message.text }],
    }));
  } catch {
    return [];
  }
}

function messageText(message: ChatMessage) {
  return message.parts
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

function Header({ onReset, disabled }: { onReset?: () => void; disabled?: boolean }) {
  return (
    <header className="header">
      <Logo />
      <div className="brand">
        <h1>Empório da Música</h1>
        <p>
          <span className="live" aria-hidden="true" />
          Atendimento virtual · Instrumentos musicais
        </p>
      </div>
      {onReset && (
        <button type="button" className="ghost" onClick={onReset} disabled={disabled}>
          Nova conversa
        </button>
      )}
    </header>
  );
}

function Equalizer({ label }: { label: string }) {
  return (
    <div className="eq" role="status" aria-label={label}>
      <span />
      <span />
      <span />
      <span />
      <span />
    </div>
  );
}

function ChatPanel({ boot, onReset }: { boot: Boot; onReset: () => void }) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport<ChatMessage>({
        api: "/api/chat",
        prepareSendMessagesRequest: ({ id, messages }) => {
          const last = messages[messages.length - 1];
          return { body: { session_id: id, message: last ? messageText(last) : "" } };
        },
      }),
    [],
  );

  const { messages, sendMessage, status, error, clearError } = useChat<ChatMessage>({
    id: boot.sessionId,
    messages: boot.initial,
    transport,
  });

  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const busy = status === "submitted" || status === "streaming";

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status]);

  function send(text: string) {
    const value = text.trim();
    if (!value || busy) return;
    clearError();
    sendMessage({ text: value });
    setInput("");
  }

  return (
    <div className="card">
      <Header onReset={onReset} disabled={busy} />

      <section className="thread" aria-live="polite">
        {messages.length === 0 && (
          <div className="welcome">
            <h2>Oi! Sou o atendente virtual da Empório da Música.</h2>
            <p>Posso te ajudar com:</p>
            <ul className="checks">
              {CAPABILITIES.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <div className="chips">
              {SUGGESTIONS.map((text) => (
                <button key={text} type="button" className="chip" onClick={() => send(text)}>
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => {
          const meta = message.parts.find((part) => part.type === "data-meta");
          const tools = meta?.type === "data-meta" ? meta.data.tools : [];
          const escalated = meta?.type === "data-meta" && meta.data.escalated;
          const text = messageText(message);
          if (!text) return null;
          return (
            <div key={message.id} className={`row ${message.role}`}>
              <div className="bubble">
                {message.role === "assistant" ? <RichText text={text} /> : <p>{text}</p>}
                {message.role === "assistant" && (tools.length > 0 || escalated) && (
                  <div className="tags">
                    {escalated && <span className="tag alert">Encaminhado à equipe</span>}
                    {[...new Set(tools.map((tool) => TOOL_LABELS[tool.name] ?? tool.name))].map((label) => (
                      <span key={label} className="tag">
                        {label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {status === "submitted" && (
          <div className="row assistant">
            <div className="bubble typing">
              <Equalizer label="Digitando" />
            </div>
          </div>
        )}

        {error && (
          <div className="error" role="alert">
            {error.message || "Algo deu errado. Tente de novo."}
          </div>
        )}
        <div ref={endRef} />
      </section>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send(input);
            }
          }}
          placeholder="Escreva sua mensagem"
          rows={1}
          maxLength={2000}
          aria-label="Mensagem"
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Enviar
        </button>
      </form>
    </div>
  );
}

export default function Chat() {
  const [boot, setBoot] = useState<Boot | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = readStoredSession();
      const sessionId = stored ?? newSessionId();
      storeSession(sessionId);
      const initial = stored ? await loadHistory(sessionId) : [];
      if (!cancelled) setBoot({ sessionId, initial });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function reset() {
    const sessionId = newSessionId();
    storeSession(sessionId);
    setBoot({ sessionId, initial: [] });
  }

  return (
    <main className="stage">
      <div className="orb orb-pink" aria-hidden="true" />
      <div className="orb orb-violet" aria-hidden="true" />
      <div className="orb orb-cyan" aria-hidden="true" />
      {boot ? (
        <ChatPanel key={boot.sessionId} boot={boot} onReset={reset} />
      ) : (
        <div className="card">
          <Header />
          <section className="thread loading">
            <Equalizer label="Carregando" />
          </section>
        </div>
      )}
    </main>
  );
}
