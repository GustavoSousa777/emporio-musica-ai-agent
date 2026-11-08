# Premissas e decisões sobre ambiguidades

O enunciado pede que ambiguidades sejam resolvidas com uma interpretação razoável e documentadas.
Cada decisão está implementada em `backend/app/core/rules.py` (constantes) ou no serviço indicado.
As inconsistências dos dados estão em [data_quality.md](data_quality.md).

## Manual de políticas

| Tema | Ambiguidade | Decisão |
|---|---|---|
| Contato | Capa e seção 1.2 dão (67) 3341-4444; a seção 7 dá o WhatsApp (67) 3321-4500. | O agente informa os dois, cada um com seu rótulo. |
| E-mail | A seção 1.2 grafa `empóriodamusica` com acento. | Usa a grafia da capa, sem acento (domínio válido). |
| Parcelamento | A tabela diz parcela mínima de R$ 100 em todo o crédito; a seção 3.1 define faixas. | Vale a 3.1 por ser mais específica: 1x livre, 2x a 3x parcela >= R$ 50, 4x a 6x >= R$ 80, 7x a 12x >= R$ 100. |
| PIX x promoção | O desconto de 5% do PIX "não se aplica a preços já promocionais". | Produto com promoção ativa não recebe preço PIX. |
| Frete grátis | "Acima de R$ 500,00". | Estritamente maior que R$ 500; exatamente R$ 500 paga R$ 35. |
| Região metropolitana | O manual não define. | Apenas Campo Grande. As outras cidades da base seguem a entrega por transportadora. |
| Frete fora da região | O valor depende de CEP, peso e dimensões. | O agente informa modalidades e prazos e não inventa preço. |
| Arrependimento | Prazo de 7 dias a partir do recebimento; a base só tem a data prevista de entrega. | A data prevista de entrega é usada como data de recebimento. |
| Canal da compra | O direito de arrependimento vale para compras online; a base não tem canal. | Todos os pedidos são tratados como online. |
| Defeito | 4.2 fala em 30 dias da compra; 8.1 fala em garantia legal de 90 dias do recebimento. | Até 30 dias da compra: troca pela loja. De 31 a 90 dias do recebimento: garantia legal, acionada com o fabricante (a loja intermedia). Depois: garantia do fabricante. |
| Itens não elegíveis | 4.4 cita boquilhas, personalizados e "venda final". | Só boquilhas são detectáveis nos dados; as demais exceções vão para a equipe. |
| Feriados | A loja fecha em feriados. | Lista simplificada: nacionais, estadual de MS e aniversário de Campo Grande. |

## Dados

| Tema | Decisão |
|---|---|
| Promoções | Só vale `is_active = 1`. Não há datas, então "encerrada" significa inativa. Com mais de uma ativa, vale a de maior desconto. |
| Preço em filtros | A faixa de preço usa o preço efetivo (com promoção ativa). |
| Estoque zero | Produto `active` com estoque 0 é tratado como indisponível e recebe alternativas. |
| Produtos `coming_soon` e `discontinued` | Aparecem em busca por nome (com o status), mas não em listagens por categoria. |
| Total do pedido | O agente usa `total_brl` e não recalcula a partir dos itens. |
| Status de pedido | `pending` = aguardando pagamento; `confirmed` = pago, ainda não despachado. |
| Categorias vazias | Sopros e cordas orquestrais existem na tabela, mas sem produtos; o agente não oferece esses itens. |

## Privacidade

- Pedido só é exibido com o número do pedido mais e-mail e/ou telefone cadastrados.
- "Pedido não existe" e "dados não conferem" geram a mesma resposta, para não revelar quais pedidos existem.
- Os serviços recebem parâmetros tipados; o agente não escreve SQL.
