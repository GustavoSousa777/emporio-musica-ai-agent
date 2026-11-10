# Listagem por categoria e faixa de preço (exemplo do enunciado)

- Cenário: `catalogo_violoes_ate_1000` (catalogo)
- Modelo: gemini-3.6-flash
- Data simulada (`NOW_OVERRIDE`): 2026-03-23T10:00:00

**Cliente:** Quais opções de violões disponíveis custando até R$1000?

_Ferramentas chamadas:_
- `search_products` {'category': 'violões', 'max_price': 1000, 'available_only': True}

**Assistente:** Temos ótimas opções de violões até R$ 1000 disponíveis na loja! Veja alguns destaques:

* **Tagima Memphis AC-39 (Nylon):** R$ 429,90 (ou R$ 408,41 no PIX)
* **Yamaha C40 (Nylon):** R$ 599,90 (ou R$ 569,91 no PIX)
* **Yamaha F310 (Aço):** R$ 699,90 (ou R$ 664,91 no PIX)
* **Tagima Dallas Tuner (Aço):** R$ 749,00 (ou R$ 711,55 no PIX)

Temos também outros modelos de marcas como Rozini, Giannini e Shelby nessa faixa de preço. Qual estilo você prefere, nylon ou aço?
