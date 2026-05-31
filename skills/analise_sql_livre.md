# skill: analise_sql_livre
# descricao: Skill única de análise de dados — toda pergunta sobre pedidos, itens, clientes, erros, alertas ou produtos usa esta skill. Executa SQL direto no PostgreSQL e processa com pandas.
# palavras-chave: pedidos, itens, clientes, produtos, erros, alertas, sql, análise, gráfico, tabela, relatório, quantidade, valor, status, período, ranking, cruzamento, join

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

## Modo agendamento — task_code com ctx.sql()

Quando a análise for para agendamento (`[PARA_AGENDAMENTO]`), o `task_code` **deve usar `ctx.sql()`**.
Use f-string com `{from_date}` e `{to_date}` — nunca datas literais fixas.

```python
def run(from_date, to_date, ctx):
    rows = ctx.sql(f"""
        SELECT
            status::text AS status,
            COUNT(*) AS total
        FROM purchase_order
        WHERE issue_date::date BETWEEN '{from_date}' AND '{to_date}'
        GROUP BY status
        ORDER BY total DESC
    """)
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df['status'], df['total'], color='#60a5fa')
    ax.set_title(f'Pedidos por Status — {from_date} a {to_date}')
    plt.tight_layout()
    return ctx.save_chart(fig)
```

Para monitores (`every_Xm`/`every_Xh`), use `ctx.today()`:
```python
def run(from_date, to_date, ctx):
    hoje = ctx.today()
    rows = ctx.sql(f"""
        SELECT COUNT(*) AS total FROM purchase_order
        WHERE issue_date::date = '{hoje}' AND status::text = 'INCONSISTENCY'
    """)
    total = rows[0]['total']
    if total > 10:
        ctx.notify(f'{total} pedidos com inconsistência hoje', value=total, threshold=10)
    return f'Inconsistências hoje: {total}'
```

---

## PostgreSQL — regras críticas

| Regra | Como aplicar |
|-------|-------------|
| Schema | `search_path=brazil` — use nomes de tabela sem prefixo |
| Enums | Sempre converter com `::text` (ex: `status::text`, `channel::text`) |
| Data do pedido | `purchase_order.issue_date` — NÃO `date`, NÃO `order_date` |
| Hoje | `CURRENT_DATE` |
| Últimos N dias | `issue_date >= CURRENT_DATE - INTERVAL 'N days'` |
| Este mês | `DATE_TRUNC('month', issue_date) = DATE_TRUNC('month', CURRENT_DATE)` |
| Formatar data | `TO_CHAR(issue_date, 'YYYY-MM-DD')` ou `'YYYY-MM'` |
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
| **issue_date** | timestamp | **Data em que o cliente emitiu o pedido — dimensão temporal principal** |
| created_at | timestamp | Data de entrada no sistema (importação) |
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

Representa uma tentativa de resolver as inconsistências de um pedido.

| Coluna | Tipo | Significado |
|--------|------|-------------|
| id | integer PK | Identificador interno |
| purchase_order_id | integer | FK → purchase_order.id — pedido sendo resolvido |
| customer_id | integer | FK → customer.id |
| file_import_id | integer | FK → file_import.id |
| status | enum | `PROCESSED` (resolvido) · `REJECTED` (rejeitado) · `INCONSISTENCY` (ainda pendente) — cast: `status::text` |
| created_at | timestamp | Quando a resolução foi registrada — **dimensão temporal desta tabela** |
| notify_reject_date | timestamp | Quando o cliente foi notificado da rejeição |

---

### `alert_resolve_error_type` — erros de uma resolução (N:N)

Tabela de junção entre `alert_resolve` e `error_type`. Um alerta pode ter múltiplos erros.

| Coluna | Tipo | Significado |
|--------|------|-------------|
| alert_resolve_id | integer | FK → alert_resolve.id |
| error_type_id | integer | FK → error_type.id |

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
  Para: listar erros associados a cada resolução de alerta

customer (N) ──→ (1) city  [nullable]
  JOIN: customer.city_id = city.id
  Para: obter a cidade do cliente
```

---

## Dimensões disponíveis para análise

| Dimensão | Tabela.Coluna |
|----------|--------------|
| Tempo do pedido | `purchase_order.issue_date` |
| Tempo de entrada no sistema | `purchase_order.created_at` |
| Mês de entrega | `purchase_order.delivery_month` |
| Tempo da resolução | `alert_resolve.created_at` |
| Cliente | `customer.name` · `.channel` · `.state` · `.regional` · `.cnpj` |
| Status do pedido | `purchase_order.status::text` |
| Status do item | `order_item.status::text` |
| Status da resolução | `alert_resolve.status::text` |
| Motivo do erro | `error_type.name::text` |
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
