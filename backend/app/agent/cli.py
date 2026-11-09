"""Conversa pelo terminal: python -m app.agent.cli [--session ID] [--show-tools] [--now 2026-03-23T10:00:00]

Comandos durante a conversa: /nova (nova sessão, apaga o contexto), /ferramentas (liga ou desliga o rastro), sair."""
from __future__ import annotations

import argparse
import logging
import uuid

from app.agent.factory import build_agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atendimento da Empório da Música pelo terminal.")
    parser.add_argument("--session", default=None, help="session_id (padrão: novo a cada execução)")
    parser.add_argument("--show-tools", action="store_true", help="mostra as ferramentas usadas")
    parser.add_argument("--now", default=None, help="fixa a data de hoje (ISO 8601), ex.: 2025-10-28T10:00:00")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    agent = build_agent(now=args.now)
    show_tools = args.show_tools
    session = args.session or uuid.uuid4().hex[:12]
    print(f"Sessão {session}. Digite 'sair' para encerrar.\n")
    while True:
        try:
            text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in {"sair", "exit", "quit"}:
            break
        if text.lower() == "/nova":
            session = uuid.uuid4().hex[:12]
            print(f"Nova sessão {session}.\n")
            continue
        if text.lower() == "/ferramentas":
            show_tools = not show_tools
            print(f"Rastro das ferramentas {'ligado' if show_tools else 'desligado'}.\n")
            continue
        if not text:
            continue
        reply = agent.reply(session, text)
        print(f"\nAssistente: {reply.text}\n")
        if show_tools:
            for trace in reply.tools:
                print(f"  [tool] {trace.name} {trace.args} -> {'ok' if trace.ok else 'erro'}")
            if reply.tools:
                print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
