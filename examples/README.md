# Conversas de exemplo

Geradas a partir de execuções reais do agente com o Gemini. Cada arquivo traz a data simulada (`NOW_OVERRIDE`), o modelo, as ferramentas chamadas em cada turno e a resposta.

| Arquivo | Situação |
|---|---|
| `01_catalogo_violoes_ate_1000.md` | catálogo |
| `02_catalogo_preco_takamine_gd20.md` | preço do Takamine GD20 (promoção inativa) |
| `03_loja_endereco.md` | endereço e horário |
| `04_devolucao_arrependimento_no_prazo.md` | devolução, com data simulada de 28/10/2025 |
| `05_escopo_acessorios.md` | fora de escopo |

Para regerar (a partir de `backend/`, com `GEMINI_API_KEY` no `.env`):

```bash
python -m app.eval --live --export-examples ../examples \
  --id catalogo_violoes_ate_1000 --id catalogo_preco_takamine_gd20 \
  --id loja_endereco --id devolucao_arrependimento_no_prazo --id escopo_acessorios
```

Cada cenário já traz a sua data (`now`), então a devolução usa 28/10/2025 sem mexer no `.env`. Só os cenários que passaram nas checagens são gravados, na ordem dos `--id`.
