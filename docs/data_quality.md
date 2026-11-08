# Qualidade dos dados

Relatório gerado automaticamente por `python -m app.database.seed`.
Não edite à mão; as decisões de negócio sobre cada ponto estão em [premissas.md](premissas.md).

## Volume carregado

| Tabela | Linhas |
|---|---|
| categories | 9 |
| products | 65 |
| customers | 50 |
| promotions | 25 |
| orders | 20 |
| order_items | 22 |

## Resumo

- Erros: 0
- Avisos: 9
- Informações: 3

## Inconsistências detectadas

### EMPTY_CATEGORY (Informação, 3)

- category 6: Categoria 'Instrumentos de Sopro (Madeiras)' não tem nenhum produto no catálogo (o manual cita esses instrumentos, mas a base não tem itens).
- category 7: Categoria 'Instrumentos de Sopro (Metais)' não tem nenhum produto no catálogo (o manual cita esses instrumentos, mas a base não tem itens).
- category 8: Categoria 'Cordas Orquestrais' não tem nenhum produto no catálogo (o manual cita esses instrumentos, mas a base não tem itens).

### ACTIVE_WITHOUT_STOCK (Aviso, 1)

- product 96: Giannini GF-3D Dreadnought Sunburst está 'active' mas com estoque 0. O agente deve tratá-lo como indisponível.

### DUPLICATE_EMAIL (Aviso, 1)

- customer 11,43: E-mail repetido em clientes distintos (Bruno Carvalho Martins | Bruno Martins): possível cliente duplicado.

### INSTALLMENT_BELOW_POLICY (Aviso, 3)

- order 9: Parcelado em 6x de R$ 58,32, abaixo da parcela mínima de R$ 80,00 (manual 3.1).
- order 16: Parcelado em 6x de R$ 71,65, abaixo da parcela mínima de R$ 80,00 (manual 3.1).
- order 18: Parcelado em 12x de R$ 38,33, abaixo da parcela mínima de R$ 100,00 (manual 3.1).

### ORDERED_UNAVAILABLE_PRODUCT (Aviso, 2)

- order 3: Pedido contém 'Kala KA-ABP-CTG Barítono Cedar' (produto 130) com status 'coming_soon'.
- order 14: Pedido contém 'Kala KA-ABP-CTG Barítono Cedar' (produto 130) com status 'coming_soon'.

### ORDER_TOTAL_MISMATCH (Aviso, 2)

- order 3: Total do pedido (R$ 3.450,00) difere da soma dos itens a preço atual (R$ 3.498,00); diferença de R$ -48,00. O agente usa o total do pedido.
- order 20: Total do pedido (R$ 1.400,00) difere da soma dos itens a preço atual (R$ 1.488,00); diferença de R$ -88,00. O agente usa o total do pedido.

## Inconsistências do manual de políticas (PDF)

Não são detectáveis pelo seed; foram encontradas na leitura e tratadas em `app/core/rules.py`.

- Telefone: capa e seção 1.2 informam (67) 3341-4444; a seção 7 cita o WhatsApp (67) 3321-4500.
- E-mail: a seção 1.2 grafa `empóriodamusica` com acento; a capa grafa sem acento.
- Parcelamento: a tabela da seção 3 fala em parcela mínima de R$ 100 para todo o crédito; a seção 3.1 define faixas (3x sem mínimo, 4x a 6x com R$ 80, 7x a 12x com R$ 100).
- Catálogo: o manual cita "mais de 300 instrumentos" e sopros/cordas orquestrais; a base tem 65 produtos e nenhum de sopro ou cordas orquestrais.
- Garantia: 4.2 fala em troca por defeito em 30 dias; 8.1 fala em garantia legal de 90 dias.
