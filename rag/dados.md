# Schema e semântica do banco — Brazil Purchase Orders

## Banco de dados

PostgreSQL, schema `brazil`. A ferramenta `executar_sql` já define `search_path=brazil`, portanto use os nomes das tabelas sem prefixo (ex: `purchase_order`, não `brazil.purchase_order`).

**Regra crítica:** colunas do tipo enum DEVEM ser convertidas com `::text` nas queries (ex: `status::text`, `channel::text`).

---

## Entidades e o que cada uma representa

### `purchase_order` — o pedido de compra

Representa um pedido feito por um cliente. É a entidade central do sistema.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| order_number | varchar | Número do pedido conforme enviado pelo cliente |
| file_import_id | integer | Qual arquivo originou este pedido (→ file_import) |
| customer_id | integer | Cliente que fez o pedido (→ customer) |
| customer_name | varchar | Nome do cliente desnormalizado — use customer.name para análises por cliente |
| issue_date | timestamp | Data em que o cliente emitiu o pedido (informada pelo cliente no arquivo) |
| **created_at** | timestamp | **Data em que o pedido entrou no sistema — principal dimensão temporal para análises** |
| delivery_month | timestamp | Mês em que o cliente deseja receber os produtos |
| status | enum | Estado atual do pedido: `APPROVED` (aprovado), `INCONSISTENCY` (tem problemas, aguarda resolução), `PENDING` (em análise), `REJECTED` (rejeitado) |
| customer_usage_order | enum | Tipo de uso do pedido pelo cliente: `CU1` ou `CU2` |
| justification_reject | text | Texto explicando por que o pedido foi rejeitado |

---

### `order_item` — um item dentro de um pedido

Cada pedido tem um ou mais itens. Um item representa uma linha do pedido: um produto/acessório específico, com quantidade e valor. O status do item é **independente** do status do pedido.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| purchase_order_id | integer | Pedido ao qual este item pertence (→ purchase_order) |
| product_id | integer (nullable) | Produto do catálogo associado a este item (→ product). NULL = produto não encontrado no catálogo |
| accessory_id | integer (nullable) | Acessório do catálogo associado (→ accessory). NULL = acessório não encontrado |
| item_number | integer | Posição do item dentro do pedido (1, 2, 3...) |
| status | enum | Estado do item: `APPROVED`, `INCONSISTENCY`, `PENDING`, `REJECTED`. **Não confundir com tipo de erro** |
| quantity | integer | Quantidade de unidades pedidas |
| value_price_total | numeric | Valor monetário total do item (preço × quantidade) |
| product_group | varchar | Grupo do produto: `SMARTPHONE`, `TABLET`, `ACESSÓRIO`, etc. |
| local_market_name | varchar | Nome comercial local do produto (como consta no pedido do cliente) |
| local_color | varchar | Cor do produto conforme pedido |
| delivery_week | varchar | Semana de entrega desejada (formato livre) |
| **error_type_id** | integer (nullable) | **Tipo de erro do item (→ error_type). Preenchido quando o item tem status INCONSISTENCY. Para obter o nome do erro, faça JOIN com error_type** |
| created_at | timestamp | Data de criação do item no sistema |

> **Atenção:** `order_item.status = 'INCONSISTENCY'` indica que o item tem problema, mas o **motivo** do erro está em `error_type.name` via `error_type_id`. Nunca use o status como descrição do erro.

---

### `customer` — o cliente

Empresa que faz pedidos. Um cliente pode ter vários pedidos.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| name | varchar | Razão social completa |
| customer_short | varchar | Nome abreviado para exibição |
| cnpj | varchar | CNPJ do cliente |
| channel | enum | Canal de venda (ex: varejo, operadora, distribuidor) — cast: `channel::text` |
| state | enum | Estado (UF) onde o cliente está localizado — cast: `state::text` |
| regional | varchar | Regional comercial à qual o cliente pertence |
| city_id | integer (nullable) | Cidade do cliente (→ city) |
| sold_customer_number | varchar | Código sold-to do cliente no ERP |
| ship_customer_number | varchar | Código ship-to do cliente no ERP |

---

### `product` — catálogo de produtos

Produtos que podem ser pedidos. Um item de pedido pode apontar para um produto do catálogo.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| part_number | varchar | Código único do produto no catálogo |
| market_name | varchar | Nome comercial internacional |
| local_market_name | varchar | Nome comercial no mercado local |
| product_group | varchar | Família de produto: `SMARTPHONE`, `TABLET`, etc. |
| local_color | varchar | Cor do produto |
| status | enum | `ACTIVE` (disponível) ou `INACTIVE` (descontinuado) |
| ram | varchar | Memória RAM (ex: `8GB`) |
| rom | varchar | Armazenamento interno (ex: `256GB`) |
| ean | varchar | Código de barras EAN |
| origin | varchar | Origem do produto |

---

### `accessory` — catálogo de acessórios

Acessórios (capas, carregadores, etc.) que podem ser pedidos. Estrutura similar a product, porém sem ram/rom.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| part_number | varchar | Código único do acessório |
| market_name | varchar | Nome comercial |
| local_market_name | varchar | Nome local |
| product_group | varchar | Grupo do acessório |
| status | enum | `ACTIVE` ou `INACTIVE` |
| ean | varchar | EAN |

---

### `error_type` — tipos de erro possíveis

Descreve os tipos de inconsistência que podem ocorrer em um item de pedido.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| name | enum | Nome do erro (ex: `CNPJ_CUSTOMER_NOT_IDENTIFIED`, `PART_NUMBER_NOT_IDENTIFIED`, `INCORRECT_QUANTITY`, `NOT_FOUND_DELIVERY_MONTH`, `ACCESSORY_MISSING_FOR_BUNDLE`, `ACCESSORY_NOT_MAPPED_TO_BUNDLE`) |

> Esta tabela é o dicionário de erros. Para saber POR QUÊ um item tem inconsistência, faça JOIN: `order_item.error_type_id → error_type.id` e leia `error_type.name`.

---

### `alert_resolve` — resolução de alertas de inconsistência

Representa uma tentativa de resolver as inconsistências de um pedido. Criada quando um operador analisa e tenta aprovar ou rejeitar um pedido inconsistente.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| purchase_order_id | integer | Pedido que está sendo resolvido (→ purchase_order) |
| customer_id | integer | Cliente do pedido (→ customer) |
| file_import_id | integer | Arquivo de origem (→ file_import) |
| status | enum | Resultado da tentativa de resolução: `PROCESSED` (resolvido com sucesso), `REJECTED` (resolução rejeitada), `INCONSISTENCY` (ainda inconsistente) |
| resolved_at | timestamp | Quando o alerta foi resolvido. **NULL = pendente (ainda não resolvido)**. Não NULL = já resolvido. |
| created_at | timestamp | Quando a resolução foi registrada |
| notify_reject_date | timestamp | Quando o cliente foi notificado da rejeição |

---

### `alert_resolve_error_type` — erros associados a uma resolução

Tabela de junção N:N entre `alert_resolve` e `error_type`. Um alerta de resolução pode estar associado a múltiplos tipos de erro simultaneamente.

| Coluna | Tipo | O que significa |
|--------|------|-----------------|
| alert_resolve_id | integer | → alert_resolve.id |
| error_type_id | integer | → error_type.id |

---

### `file_import` — arquivos importados

Registra cada arquivo de pedidos recebido dos clientes.

| Coluna | Tipo | O que significa no negócio |
|--------|------|---------------------------|
| id | integer PK | Identificador interno |
| file_name | varchar | Nome original do arquivo |
| file_extension | varchar | Extensão do arquivo |
| date_registered | timestamp | Data e hora da importação |

---

### `city` — cidades

Tabela auxiliar de cidades vinculadas a clientes.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | integer PK | Identificador interno |
| name | varchar | Nome da cidade |

---

## Grafo de relacionamentos

```
purchase_order (1) ──────────────────── (N) order_item
    via: order_item.purchase_order_id → purchase_order.id
    para que serve: obter data, cliente e status do pedido ao qual o item pertence

purchase_order (N) ──────────────────── (1) customer
    via: purchase_order.customer_id → customer.id
    para que serve: segmentar pedidos por canal, estado, regional, CNPJ

purchase_order (N) ──────────────────── (1) file_import
    via: purchase_order.file_import_id → file_import.id
    para que serve: rastrear qual arquivo originou o pedido

order_item (N) ──────────────────────── (1) product  [nullable]
    via: order_item.product_id → product.id
    para que serve: obter part_number, market_name, ram, rom do produto pedido
    NULL = produto não identificado no catálogo (inconsistência)

order_item (N) ──────────────────────── (1) accessory  [nullable]
    via: order_item.accessory_id → accessory.id
    para que serve: obter dados do acessório pedido
    NULL = acessório não identificado no catálogo

order_item (N) ──────────────────────── (1) error_type  [nullable]
    via: order_item.error_type_id → error_type.id
    para que serve: obter o MOTIVO do erro do item (ex: "PART_NUMBER_NOT_IDENTIFIED")
    NULL = item sem erro

alert_resolve (N) ───────────────────── (1) purchase_order
    via: alert_resolve.purchase_order_id → purchase_order.id
    para que serve: saber qual pedido está sendo resolvido

alert_resolve (N) ───────────────────── (1) customer
    via: alert_resolve.customer_id → customer.id
    para que serve: agrupar resoluções por cliente

alert_resolve (N) ────────── (N) error_type  [via alert_resolve_error_type]
    via: alert_resolve_error_type.alert_resolve_id + alert_resolve_error_type.error_type_id
    para que serve: listar os tipos de erro associados a cada resolução de alerta

customer (N) ────────────────────────── (1) city  [nullable]
    via: customer.city_id → city.id
    para que serve: obter a cidade do cliente
```

---

## Dimensões de análise disponíveis

Ao construir queries, o agente pode cruzar qualquer combinação das dimensões abaixo:

**Tempo:** `purchase_order.created_at` (entrada no sistema — dimensão principal), `purchase_order.issue_date` (data original do cliente), `purchase_order.delivery_month` (entrega prevista), `alert_resolve.created_at`

**Cliente:** `customer.name`, `customer.channel`, `customer.state`, `customer.regional`, `customer.cnpj`

**Produto:** `product.part_number`, `product.market_name`, `product.product_group`, `product.ram`, `product.rom`, `order_item.product_group` (como consta no pedido)

**Erro:** `error_type.name` (motivo do erro), `order_item.error_type_id IS NOT NULL` (tem erro ou não)

**Status:** `purchase_order.status` (status do pedido), `order_item.status` (status do item), `alert_resolve.status` (resultado da resolução)

**Volume/Valor:** `order_item.quantity` (unidades), `order_item.value_price_total` (valor monetário)

**Arquivo de origem:** `file_import.file_name`, `file_import.date_registered`

---

## API REST — endpoints disponíveis

Base URL: `http://localhost:8000/brazil`

Todos os endpoints de data usam `from` e `to` no formato `YYYY-MM-DD`.

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/brazil/purchase-orders` | Lista purchase orders (filtros: status, customer_id, from/to por created_at) |
| GET | `/brazil/purchase-orders/{id}` | Detalhes de uma PO com seus itens |
| GET | `/brazil/order-items` | Lista itens (filtros: status, product_group, from/to por created_at da PO) |
| GET | `/brazil/orders/summary` | Resumo agregado de pedidos (from/to por created_at) |
| GET | `/brazil/order-items/summary` | Resumo de itens com error_ratio (from/to por created_at) |
| GET | `/brazil/alert-resolves/by-status` | Contagem de alertas resolvidos por tipo de erro (from/to por resolved_at) |
| GET | `/brazil/alert-resolves/by-dim` | Top 20 alertas resolvidos agrupados por dimensão (name/cnpj/state/city/channel) com breakdown por tipo de erro |
| GET | `/brazil/customers` | Lista clientes (filtros: search, channel) |
| GET | `/brazil/products` | Lista produtos (filtros: search, product_group, status) |

Para análises não cobertas pelos endpoints, use `executar_sql` com SQL direto no banco.
