# Avaliação do agente

30 cenários com a ferramenta esperada (`backend/app/eval/scenarios.py`), em 7 categorias: catálogo, loja, pagamento e frete, pedidos, devolução e garantia, escalonamento, escopo e segurança. Treze deles formam o subconjunto rápido (`--core`).

## Dois modos

| Modo | Comando | O que confere | Precisa de chave |
|---|---|---|---|
| Offline (oráculo) | `python -m app.eval` | Um roteiro faz as chamadas de ferramenta ideais, sem LLM. Confere se as ferramentas, os argumentos e os dados reais sustentam cada cenário | Não |
| Ao vivo | `python -m app.eval --live` | O Gemini decide sozinho. Confere ferramentas, argumentos, resultados e o texto da resposta | Sim |

O modo offline também roda no `pytest` (`tests/test_eval.py`) como teste de regressão dos dados e das regras.

## Opções

```powershell
python -m app.eval --list                          # lista os cenários
python -m app.eval --live --core                   # só os 13 principais
python -m app.eval --live --category pedidos       # uma categoria
python -m app.eval --live --id loja_endereco       # um cenário (pode repetir --id)
python -m app.eval --live --pause 5                # segundos entre cenários (padrão 3)
python -m app.eval --live --report docs/avaliacao_ao_vivo.md
```

## O que cada cenário verifica

- Ferramentas: quais precisam ser chamadas, quais não podem (ex.: não consultar pedido sem e-mail ou telefone).
- Argumentos: por exemplo `max_price = 1000` na busca de violões até R$ 1.000.
- Resultados: o dado certo chegou ao modelo (ex.: preço R$ 2.199, promoção do GD20 `expired`).
- Texto da resposta (só ao vivo): padrões que devem ou não aparecer, e teto de preço citado. Os padrões são aplicados sem acento e em minúsculas.
- Data fixa: cada cenário define "agora", então o resultado não depende do dia em que roda (ex.: devolução com data fixa em 28/10/2025).

## Limites e falhas

- O modo ao vivo usa a cota do Gemini (uns 2 a 4 chamadas por cenário). Se todos os modelos ficarem sem cota, o cenário vira sem modelo (não conta como falha do prompt) e a execução para após dois seguidos. Rode de novo mais tarde, ou com `--core`.
- A resposta de um LLM varia entre execuções. Um padrão que falha uma vez pode ser variação de redação: confira a conversa impressa antes de mudar o prompt.
- Os padrões de texto são heurísticas. Eles pegam preço inventado, vazamento de dados e promoção vencida, mas não julgam o tom da resposta.
