"""Conversa pelo terminal: python -m app.agent.cli [--session ID] [--show-tools]"""
from __future__ import annotations

import argparse
import logging
import uuid

from app.agent.factory import build_agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atendimento da Empório da Música pelo terminal.")
    parser.add_argument("--session", default=None, help="session_id (padrão: novo a cada execução)")
    parser.add_argument("--show-tools", action="store_true", help="mostra as ferramentas usadas")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    agent = build_agent()
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
        reply = agent.reply(session, text)
        print(f"\nAssistente: {reply.text}\n")
        if args.show_tools:
            for trace in reply.tools:
                print(f"  [tool] {trace.name} {trace.args} -> {'ok' if trace.ok else 'erro'}")
            if reply.tools:
                print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
