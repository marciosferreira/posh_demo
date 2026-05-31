# Domínio de negócio — Brazil Purchase Orders

## O que é este sistema

Plataforma de gestão de pedidos de compra (purchase orders) para a operação Brazil. Recebe pedidos de clientes via importação de arquivo, processa e classifica cada pedido e seus itens (aprovado, inconsistência, pendente, rejeitado), e fornece visibilidade sobre o pipeline de vendas, volumes por cliente, produto e status.

## Fluxo de um pedido

1. **Importação** — arquivo de pedido enviado pelo cliente é importado via `file_import`
2. **Criação do PO** — `purchase_order` criado com status inicial `INCONSISTENCY`
3. **Validação dos itens** — cada `order_item` é classificado: produto/acessório resolvido ou não
4. **Resolução** — pedidos com inconsistência podem ser resolvidos via `alert_resolve`
5. **Status final** — `APPROVED`, `REJECTED` ou mantido em `PENDING`

## Status de purchase_order

| Status | Significado |
|--------|-------------|
| `APPROVED` | Pedido aprovado e processado com sucesso |
| `INCONSISTENCY` | Pedido com problemas de validação — aguarda resolução |
| `PENDING` | Pedido em análise |
| `REJECTED` | Pedido rejeitado |

## Status de order_item

Itens individuais do pedido têm seu próprio status, independente do PO.

## Campos de data em purchase_order

| Campo | Significado |
|-------|-------------|
| `issue_date` | Data de emissão do pedido pelo cliente — **a data "oficial" do pedido** |
| `created_at` | Data/hora de entrada no sistema (importação) |
| `delivery_month` | Mês de entrega previsto pelo cliente |

**Para filtros temporais de "pedidos de hoje/esta semana/etc", use `issue_date`** — ela representa quando o pedido foi feito. Use `created_at` apenas quando a pergunta for sobre quando o pedido foi importado no sistema.

## Entidades principais

### Clientes (`customer`)
- Identificados por `name` (razão social), `customer_short` (nome abreviado) e `cnpj`
- Organizados por `channel` (canal de venda) e `state` (estado/UF)
- Agrupados por `regional`

### Produtos (`product`) e Acessórios (`accessory`)
- Identificados por `part_number` (único) e `market_name` / `local_market_name`
- Agrupados por `product_group` (ex: `SMARTPHONE`, `TABLET`, `ACESSÓRIO`)
- Especificações: `ram`, `rom`, `local_color`, `origin`

### Itens de pedido (`order_item`)
- Cada PO tem 1..N itens
- Campos principais: `quantity`, `value_price_total`, `product_group`, `delivery_week`
- Um item pode ser sem produto vinculado (`product_id IS NULL`) — indica inconsistência de mapeamento

## KPIs e métricas relevantes

| Métrica | Como calcular |
|---------|---------------|
| Total de pedidos | `COUNT(*)` em `purchase_order` |
| Pedidos aprovados | `COUNT(*) WHERE status = 'APPROVED'` |
| Taxa de aprovação | `pedidos aprovados / total × 100%` |
| Pedidos com inconsistência | `COUNT(*) WHERE status = 'INCONSISTENCY'` |
| Volume por cliente | `COUNT(*)` agrupado por `customer_name` ou `customer_id` |
| Quantidade total de itens | `SUM(oi.quantity)` em `order_item` |
| Valor total | `SUM(oi.value_price_total)` em `order_item` |
| Produtos mais pedidos | `COUNT(oi.id)` ou `SUM(oi.quantity)` agrupado por `product_group` / `part_number` |
| Tempo de processamento | `AVG(EXTRACT(EPOCH FROM (created_at - issue_date)) / 86400)` em dias |

## Canais de venda

O campo `customer.channel` identifica o canal. Use `channel::text` nas queries. Os valores existem como enum no banco — use `SELECT DISTINCT channel::text FROM customer` para listar.

## Regiões e estados

`customer.state` contém a UF (sigla do estado brasileiro) como enum — cast: `state::text`.
`customer.regional` contém a regional comercial como texto livre.
