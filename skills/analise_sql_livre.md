# skill: analise_sql_livre
# descricao: Skill única de análise de dados — toda pergunta sobre pedidos, itens, clientes, erros, alertas ou produtos usa esta skill. Executa SQL direto no PostgreSQL e processa com pandas.
# palavras-chave: pedidos, itens, clientes, produtos, erros, alertas, sql, análise, gráfico, tabela, relatório, quantidade, valor, status, período, ranking, cruzamento, join

---

## ⚠️ COLUNAS DE DATA — leia antes de escrever qualquer SQL

| Uso | Coluna correta | NUNCA use |
| --- | --- | --- |
| Data de entrada no sistema (filtros temporais) | `purchase_order.created_at` | ~~`import_date`~~ ~~`date`~~ |
| Data original informada pelo cliente | `purchase_order.issue_date` | ~~`order_date`~~ ~~`date`~~ |
| Mês de entrega desejado | `purchase_order.delivery_month` | — |
| Data do item | `order_item.created_at` | ~~`date`~~ |
| Data da resolução | `alert_resolve.created_at` | ~~`date`~~ |

**A dimensão temporal principal dos pedidos é `created_at`.** Para "pedidos deste mês", "pedidos de hoje", "pedidos por período" — use sempre `created_at`.

---

## Esta é a única skill de análise

Use para qualquer pergunta sobre dados: simples ou complexa, uma tabela ou várias, quantidade ou valor, listagem ou agrupamento. Não existe outra skill de consulta.

---

## Fluxo obrigatório

```
1. read_skill('analise_sql_livre.md')            ← você já está aqui
2. executar_sql(query=<SELECT...>, chave=<nome>)  ← executa SQL e injeta DataFrame
3. analisar_dataframe(script)                    ← processa com pandas e gera resultado
```

**Nunca use `chamar_api` para análises.** Calcule datas diretamente no SQL com funções PostgreSQL.

---

## Modo agendamento — duas tools distintas

### `schedule_task` — relatórios e gráficos recorrentes

Use para: "gere um relatório diário", "envie gráfico toda segunda", "planilha mensal".

```python
def run(from_date, to_date, ctx):
    rows = ctx.sql(f"""
        SELECT status::text AS status, COUNT(*) AS total
        FROM purchase_order
        WHERE created_at::date BETWEEN '{from_date}' AND '{to_date}'
        GROUP BY status ORDER BY total DESC
    """)
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df['status'], df['total'], color='#60a5fa')
    ax.set_title(f'Pedidos por Status — {from_date} a {to_date}')
    plt.tight_layout()
    return ctx.save_chart(fig)
```

### `schedule_monitor` — alertas e monitores de threshold

Use para: "me alerte se X > N", "notifique se não houver Y", "monitore Z e avise quando passar de N".

**NUNCA use `ctx.notify()` no task_code.** A condição fica em `condition_sql` + `condition_operator` + `condition_threshold` — o daemon avalia e notifica automaticamente.

O task_code do monitor apenas retorna o valor atual:

```python
def run(from_date, to_date, ctx):
    rows = ctx.sql(f"""
        SELECT COUNT(*) AS total FROM purchase_order
        WHERE created_at::date = '{from_date}'
    """)
    return f"Total de pedidos: {rows[0]['total']}"
```

### Padrões de condition_sql — use estes exatos, nunca invente nomes de tabela

| O usuário pediu | condition_sql | operator | threshold |
|---|---|---|---|
| total de pedidos hoje >= N | `SELECT COUNT(*) FROM purchase_order WHERE created_at::date = CURRENT_DATE` | `>=` | N |
| total de pedidos de todos os tempos >= N | `SELECT COUNT(*) FROM purchase_order` | `>=` | N |
| pedidos com inconsistência hoje > N | `SELECT COUNT(*) FROM purchase_order WHERE status::text = 'INCONSISTENCY' AND created_at::date = CURRENT_DATE` | `>` | N |
| valor total de pedidos hoje >= N | `SELECT COALESCE(SUM(oi.value_price_total),0) FROM order_item oi JOIN purchase_order po ON po.id=oi.purchase_order_id WHERE po.created_at::date = CURRENT_DATE` | `>=` | N |
| sem pedidos hoje (alerta se vazio) | `SELECT id FROM purchase_order WHERE created_at::date = CURRENT_DATE LIMIT 1` | `is_empty` | — |
| há pedidos pendentes | `SELECT id FROM purchase_order WHERE status::text = 'PENDING' LIMIT 1` | `is_not_empty` | — |
| clientes únicos hoje >= N | `SELECT COUNT(DISTINCT customer_id) FROM purchase_order WHERE created_at::date = CURRENT_DATE` | `>=` | N |

**Tabelas corretas:** `purchase_order`, `order_item`, `customer`, `product` — **NUNCA** `orders`, `pedidos`, `items`.

Exemplo de criação — "alertar se total de pedidos hoje >= 160":

```python
schedule_monitor(
    name="Monitor de Pedidos",
    description="Alerta se total de pedidos do dia >= 160",
    frequency="every_5m",
    condition_sql="SELECT COUNT(*) FROM purchase_order WHERE created_at::date = CURRENT_DATE",
    condition_operator=">=",
    condition_threshold=160,
)
```

---

## PostgreSQL — regras críticas

| Regra | Como aplicar |
|-------|-------------|
| Schema | `search_path=brazil` — use nomes de tabela sem prefixo |
| Enums | Sempre converter com `::text` (ex: `status::text`, `channel::text`) |
| Data principal do pedido | `purchase_order.created_at` — NÃO `date`, NÃO `order_date` |
| Hoje | `CURRENT_DATE` |
| Últimos N dias | `created_at >= CURRENT_DATE - INTERVAL 'N days'` |
| Este mês | `DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)` |
| Formatar data | `TO_CHAR(created_at, 'YYYY-MM-DD')` ou `'YYYY-MM'` |
| Apenas SELECT | Qualquer outro comando será rejeitado |
| Sem SELECT * | Liste sempre as colunas necessárias |

---

## Modelo de dados — o que cada tabela representa

### `purchase_order` — pedido de compra

Entidade central. Cada linha é um pedido feito por um cliente, originado de um arquivo importado.

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| order_number | varchar | Número do pedido conforme enviado pelo cliente |
| customer_id | integer | FK → customer.id |
| customer_name | varchar | Nome do cliente desnormalizado — prefira JOIN com customer.name |
| file_import_id | integer | FK → file_import.id — qual arquivo originou este pedido |
| issue_date | timestamp | Data em que o cliente emitiu o pedido (informada no arquivo) |
| **created_at** | timestamp | **Data de entrada no sistema — dimensão temporal principal** |
| delivery_month | timestamp | Mês em que o cliente deseja receber os produtos |
| status | enum | `APPROVED` · `INCONSISTENCY` · `PENDING` · `REJECTED` — cast: `status::text` |
| customer_usage_order | enum | `CU1` · `CU2` — cast: `customer_usage_order::text` |
| justification_reject | text | Motivo da rejeição (texto livre) |

---

### `order_item` — item de um pedido

Cada pedido tem 1..N itens. Um item é uma linha do pedido: produto específico, quantidade e valor. O status do item é **independente** do status do pedido.

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| purchase_order_id | integer | FK → purchase_order.id |
| product_id | integer (nullable) | FK → product.id. NULL = produto não encontrado no catálogo |
| accessory_id | integer (nullable) | FK → accessory.id. NULL = acessório não encontrado |
| item_number | integer | Posição do item no pedido (1, 2, 3...) |
| status | enum | `APPROVED` · `INCONSISTENCY` · `PENDING` · `REJECTED` — cast: `status::text` |
| quantity | integer | Quantidade de unidades pedidas |
| value_price_total | numeric | Valor monetário total do item |
| product_group | varchar | Família: `SMARTPHONE` · `TABLET` · `ACESSÓRIO` etc. |
| local_market_name | varchar | Nome comercial local do produto (como consta no pedido) |
| local_color | varchar | Cor do produto conforme pedido |
| delivery_week | varchar | Semana de entrega desejada |
| **error_type_id** | integer (nullable) | **FK → error_type.id. Preenchido quando o item tem erro. Para o motivo, faça JOIN com error_type** |
| created_at | timestamp | Data de criação do item no sistema |

> **Armadilha:** `order_item.status = 'INCONSISTENCY'` indica que há um problema, mas o **motivo** está em `error_type.name` via `error_type_id`. Nunca use o status como descrição do erro.

---

### `customer` — cliente

Empresa que realiza pedidos.

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| name | varchar | Razão social completa |
| customer_short | varchar | Nome abreviado |
| cnpj | varchar | CNPJ |
| channel | enum | Canal de venda — cast: `channel::text` |
| state | enum | Estado (UF) — cast: `state::text` |
| regional | varchar | Regional comercial |
| city_id | integer (nullable) | FK → city.id |
| sold_customer_number | varchar | Código sold-to no ERP |
| ship_customer_number | varchar | Código ship-to no ERP |

---

### `error_type` — tipos de erro possíveis

Dicionário de erros. Para saber POR QUÊ um item tem inconsistência, faça JOIN aqui.

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| name | enum | Nome do erro — cast: `name::text` |

Valores conhecidos: `CNPJ_CUSTOMER_NOT_IDENTIFIED` · `CNPJ_DELIVERY_NOT_IDENTIFIED` · `PART_NUMBER_NOT_IDENTIFIED` · `INCORRECT_QUANTITY` · `NOT_FOUND_DELIVERY_MONTH` · `ACCESSORY_MISSING_FOR_BUNDLE` · `ACCESSORY_NOT_MAPPED_TO_BUNDLE`

---

### `alert_resolve` — resolução de inconsistências

Representa uma tentativa de resolver as inconsistências de um pedido. **O status real de cada `alert_resolve` é o status do `purchase_order` associado** (`purchase_order.status`, via `purchase_order_id`) — `INCONSISTENCY` (pendente de análise), `REJECTED` (rejeitado) ou `PROCESSED` (resolvido/processado).

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| purchase_order_id | integer | FK → purchase_order.id — pedido sendo resolvido. **JOIN com purchase_order para saber o status real (INCONSISTENCY/REJECTED/PROCESSED)** |
| customer_id | integer | FK → customer.id (pode ser NULL quando o erro é justamente "cliente/CNPJ não identificado") |
| file_import_id | integer | FK → file_import.id |
| created_at | timestamp | Quando a resolução foi registrada — **dimensão temporal desta tabela** |
| resolved_at | timestamp | Preenchido quando o alerta foi tratado. NULL = ainda pendente |
| notify_reject_date | timestamp | Quando o cliente foi notificado da rejeição |

> ⚠️ **NÃO use `resolved_at IS NOT NULL` como filtro de "resolvido"** — isso não separa corretamente pendentes/rejeitados/processados. Use `purchase_order.status::text` para isso.

---

### `alert_resolve_error_type` — erros de uma resolução (N:N) — **APENAS para pedidos INCONSISTENCY/REJECTED**

Tabela de junção entre `alert_resolve` e `error_type`. Um alerta pode ter múltiplos erros.

| Coluna | Tipo | Significado |
|--------|------|-------------|
| alert_resolve_id | integer | FK → alert_resolve.id |
| error_type_id | integer | FK → error_type.id |

> ⚠️ **ARMADILHA CRÍTICA — tipos de erro de pedidos PROCESSED não estão aqui.**
> Quando um `alert_resolve` é **processado** (`purchase_order.status = 'PROCESSED'`), seus registros em `alert_resolve_error_type` são **removidos/movidos** para `order_snapshot_item_issue` (campo `alert_name`). Um `LEFT JOIN alert_resolve_error_type` para um pedido `PROCESSED` retornará `NULL` (apareceria como "Sem tipo"), o que é **enganoso** — não significa que o pedido não teve erros.
>
> **Para obter o tipo de erro de um alerta, use sempre esta regra combinada:**
> | Status do `purchase_order` | De onde vem o tipo de erro |
> |---|---|
> | `INCONSISTENCY` ou `REJECTED` | `alert_resolve_error_type` → `error_type.name` |
> | `PROCESSED` | `order_snapshot_item_issue.alert_name` (via `order_snapshot.purchase_order_id = alert_resolve.purchase_order_id`) — **já é o nome do tipo, não precisa JOIN com `error_type`** |

---

### `order_snapshot` — snapshot do pedido no momento do processamento

Criado quando um pedido é processado/resolvido. Liga `alert_resolve`/`purchase_order` aos itens com problema (`order_snapshot_item_issue`).

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| purchase_order_id | integer | FK → purchase_order.id — **mesmo pedido do `alert_resolve`** |
| order_number | varchar | Número do pedido |
| customer_id | integer (nullable) | FK → customer.id |
| payload | jsonb | Snapshot completo do pedido no momento do processamento |
| error_type_ids | jsonb | IDs de tipos de erro associados ao snapshot |
| failure_reason | varchar | Motivo de falha, se houver |
| resolved_by_user_id | integer (nullable) | Usuário que resolveu |
| resolved_at | timestamp | Quando foi resolvido |
| created_at | timestamp | Data de criação do snapshot |

---

### `order_snapshot_item_issue` — itens com problema de um snapshot (pedidos PROCESSED)

Cada linha é um item específico que apresentou um alerta/inconsistência durante o processamento de um pedido `PROCESSED`. **`alert_name` é o nome do tipo de erro pronto para uso — não precisa mapear para `error_type`.**

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| order_snapshot_id | integer | FK → order_snapshot.id |
| item_name | varchar | Nome/descrição do item conforme o pedido |
| part_number | varchar (nullable) | Código do produto, se identificado |
| **alert_name** | varchar | **Nome do tipo de erro/alerta deste item — equivalente a `error_type.name`, já pronto** (ex: `PART_NUMBER_NOT_IDENTIFIED`) |
| resolved_product_id | integer (nullable) | FK → product.id, se o item foi resolvido para um produto |
| resolved_accessory_id | integer (nullable) | FK → accessory.id, se resolvido para um acessório |
| resolved_at | timestamp | Quando o item foi resolvido |
| created_at | timestamp | Data de criação |

---

### `product` — catálogo de produtos

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| part_number | varchar | Código único do produto |
| market_name | varchar | Nome comercial internacional |
| local_market_name | varchar | Nome comercial local |
| product_group | varchar | Família: `SMARTPHONE` · `TABLET` etc. |
| local_color | varchar | Cor |
| status | enum | `ACTIVE` · `INACTIVE` — cast: `status::text` |
| ram | varchar | Memória RAM (ex: `8GB`) |
| rom | varchar | Armazenamento (ex: `256GB`) |
| ean | varchar | Código de barras EAN |
| origin | varchar | Origem do produto |

---

### `accessory` — catálogo de acessórios

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| part_number | varchar | Código único |
| market_name | varchar | Nome comercial |
| local_market_name | varchar | Nome local |
| product_group | varchar | Grupo do acessório |
| status | enum | `ACTIVE` · `INACTIVE` — cast: `status::text` |
| ean | varchar | EAN |

---

### `file_import` — arquivos importados

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| file_name | varchar | Nome do arquivo recebido do cliente |
| file_extension | varchar | Extensão |
| date_registered | timestamp | Data/hora da importação |

---

### `city` — cidades

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| name | varchar | Nome da cidade |

---

## Grafo de relacionamentos

```
purchase_order (1) ──→ (N) order_item
  JOIN: order_item.purchase_order_id = purchase_order.id
  Para: obter data, cliente e status do pedido ao qual o item pertence

purchase_order (N) ──→ (1) customer
  JOIN: purchase_order.customer_id = customer.id
  Para: segmentar pedidos por canal, estado, regional, CNPJ

purchase_order (N) ──→ (1) file_import
  JOIN: purchase_order.file_import_id = file_import.id
  Para: rastrear qual arquivo originou o pedido

order_item (N) ──→ (1) product  [nullable]
  JOIN: order_item.product_id = product.id
  Para: obter part_number, market_name, ram, rom do produto
  NULL = produto não identificado no catálogo

order_item (N) ──→ (1) accessory  [nullable]
  JOIN: order_item.accessory_id = accessory.id
  Para: obter dados do acessório
  NULL = acessório não identificado

order_item (N) ──→ (1) error_type  [nullable]
  JOIN: order_item.error_type_id = error_type.id
  Para: obter o MOTIVO do erro (ex: PART_NUMBER_NOT_IDENTIFIED)
  NULL = item sem erro

alert_resolve (N) ──→ (1) purchase_order
  JOIN: alert_resolve.purchase_order_id = purchase_order.id
  Para: saber qual pedido está sendo resolvido

alert_resolve (N) ──→ (1) customer
  JOIN: alert_resolve.customer_id = customer.id
  Para: agrupar resoluções por cliente

alert_resolve (N) ↔ (N) error_type  [via alert_resolve_error_type]
  JOIN: alert_resolve_error_type art
        ON art.alert_resolve_id = alert_resolve.id
        AND art.error_type_id = error_type.id
  Para: listar erros de alertas INCONSISTENCY/REJECTED
  ⚠️ NÃO retorna nada para alertas PROCESSED (ver order_snapshot_item_issue)

order_snapshot (N) ──→ (1) purchase_order
  JOIN: order_snapshot.purchase_order_id = purchase_order.id
  Para: localizar o snapshot de um pedido PROCESSED
  (mesmo purchase_order_id de alert_resolve)

order_snapshot (1) ──→ (N) order_snapshot_item_issue
  JOIN: order_snapshot_item_issue.order_snapshot_id = order_snapshot.id
  Para: obter os tipos de erro (alert_name) de pedidos PROCESSED

customer (N) ──→ (1) city  [nullable]
  JOIN: customer.city_id = city.id
  Para: obter a cidade do cliente
```

---

## Dimensões disponíveis para análise

| Dimensão | Tabela.Coluna |
|----------|--------------|
| Tempo do pedido (principal) | `purchase_order.created_at` |
| Data original do cliente | `purchase_order.issue_date` |
| Mês de entrega | `purchase_order.delivery_month` |
| Tempo da resolução | `alert_resolve.created_at` |
| Cliente | `customer.name` · `.channel` · `.state` · `.regional` · `.cnpj` |
| Status do pedido | `purchase_order.status::text` |
| Status do item | `order_item.status::text` |
| Status do alerta (`alert_resolve`) | `purchase_order.status::text` via JOIN em `purchase_order_id` — `INCONSISTENCY` (pendente) · `REJECTED` · `PROCESSED` |
| Motivo do erro (INCONSISTENCY/REJECTED) | `error_type.name::text` via `alert_resolve_error_type` |
| Motivo do erro (PROCESSED) | `order_snapshot_item_issue.alert_name` via `order_snapshot` |
| Tem erro ou não | `order_item.error_type_id IS NOT NULL` |
| Produto | `product.part_number` · `.market_name` · `.product_group` · `.ram` · `.rom` |
| Família de produto | `order_item.product_group` (como consta no pedido) |
| Volume | `order_item.quantity` |
| Valor | `order_item.value_price_total` |
| Arquivo de origem | `file_import.file_name` · `.date_registered` |

---

## Ambiente Python (analisar_dataframe)

| Variável | Biblioteca |
|----------|-----------|
| `pd` | pandas |
| `np` | numpy |
| `plt` | matplotlib.pyplot |
| `stats` | scipy.stats |

Atribua `result = fig` para gráfico ou `result = df` para tabela.

Cores padrão do sistema: aprovado `#34d399` · inconsistência `#f87171` · pendente `#fbbf24` · rejeitado `#94a3b8` · volume `#60a5fa` · valor `#a78bfa`

Datas no eixo X: `pd.to_datetime(df['col']).dt.strftime('%d/%m')`
