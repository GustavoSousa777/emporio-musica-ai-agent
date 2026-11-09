"""Atalho: python -m app.rag.build_index [--lexical-only] [--query "..."]"""
from app.rag.retriever import main

if __name__ == "__main__":
    raise SystemExit(main())
