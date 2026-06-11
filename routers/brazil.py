from datetime import date as _date, timedelta as _timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db_posh import posh_query, posh_query_one

router = APIRouter(tags=["brazil"])


def _gen_periods(from_date: str, to_date: str, granularity: str) -> list[str]:
    """Gera todos os rótulos de período entre from_date e to_date (inclusive)."""
    start = _date.fromisoformat(from_date)
    end   = _date.fromisoformat(to_date)
    result = []

    if granularity == "day":
        cur = start
        while cur <= end:
            result.append(cur.strftime("%Y-%m-%d"))
            cur += _timedelta(days=1)

    elif granularity == "week":
        cur = start - _timedelta(days=start.weekday())   # segunda-feira da semana inicial
        while cur <= end:
            result.append(cur.strftime("%Y-%m-%d"))
            cur += _timedelta(weeks=1)

    elif granularity == "month":
        cur = _date(start.year, start.month, 1)
        end_m = _date(end.year, end.month, 1)
        while cur <= end_m:
            result.append(cur.strftime("%Y-%m"))
            cur = _date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)

    elif granularity == "year":
        for y in range(start.year, end.year + 1):
            result.append(str(y))

    return result


# ── purchase orders ───────────────────────────────────────────────────────────

@router.get("/purchase-orders")
def list_purchase_orders(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    limit: int = Query(default=50, le=500),
    offset: int = 0,
):
    """
    Lista purchase orders do schema brazil com filtros opcionais.

    Exemplos:
      /brazil/purchase-orders?status=APPROVED&from=2025-01-01&to=2025-12-31
      /brazil/purchase-orders?customer_id=5&limit=100
    """
    clauses = []
    params: list = []

    if status:
        clauses.append("po.status::text = %s")
        params.append(status)
    if customer_id:
        clauses.append("po.customer_id = %s")
        params.append(customer_id)
    if from_date:
        clauses.append("po.created_at >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("po.created_at <= %s")
        params.append(to_date + " 23:59:59")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = posh_query(
        f"""
        SELECT
            po.id,
            po.order_number,
            po.customer_name,
            po.customer_id,
            c.name AS customer,
            po.status::text AS status,
            po.issue_date,
            po.delivery_month,
            po.customer_usage_order::text AS customer_usage_order,
            po.created_at
        FROM brazil.purchase_order po
        LEFT JOIN brazil.customer c ON c.id = po.customer_id
        {where}
        ORDER BY po.created_at DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )
    return rows


@router.get("/purchase-orders/{order_id}")
def get_purchase_order(order_id: int):
    """Detalhes de uma purchase order, incluindo seus itens."""
    order = posh_query_one(
        """
        SELECT
            po.*,
            po.status::text AS status,
            po.customer_usage_order::text AS customer_usage_order,
            c.name AS customer,
            c.cnpj AS customer_cnpj,
            c.channel::text AS customer_channel
        FROM brazil.purchase_order po
        LEFT JOIN brazil.customer c ON c.id = po.customer_id
        WHERE po.id = %s
        """,
        (order_id,),
    )
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order não encontrada.")

    items = posh_query(
        """
        SELECT
            oi.id,
            oi.item_number,
            oi.status::text AS status,
            oi.quantity,
            oi.value_price_total,
            oi.product_group,
            oi.local_market_name,
            oi.local_color,
            oi.delivery_week,
            p.part_number,
            p.market_name,
            p.ean
        FROM brazil.order_item oi
        LEFT JOIN brazil.product p ON p.id = oi.product_id
        WHERE oi.purchase_order_id = %s
        ORDER BY oi.item_number
        """,
        (order_id,),
    )
    order["items"] = items
    return order


# ── order items ───────────────────────────────────────────────────────────────

@router.get("/order-items")
def list_order_items(
    status: Optional[str] = None,
    product_group: Optional[str] = None,
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
):
    """Lista itens de pedido com filtros opcionais."""
    clauses = []
    params: list = []

    if status:
        clauses.append("oi.status::text = %s")
        params.append(status)
    if product_group:
        clauses.append("oi.product_group ILIKE %s")
        params.append(f"%{product_group}%")
    if from_date:
        clauses.append("po.created_at >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("po.created_at <= %s")
        params.append(to_date + " 23:59:59")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    return posh_query(
        f"""
        SELECT
            oi.id,
            oi.item_number,
            oi.status::text AS status,
            oi.quantity,
            oi.value_price_total,
            oi.product_group,
            oi.local_market_name,
            oi.local_color,
            oi.delivery_week,
            po.order_number,
            po.created_at,
            po.customer_name
        FROM brazil.order_item oi
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        {where}
        ORDER BY po.created_at DESC, oi.item_number
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )


# ── summaries ─────────────────────────────────────────────────────────────────

@router.get("/orders/summary")
def orders_summary(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    group_by: str = Query(default="name", pattern="^(name|cnpj)$"),
):
    """
    Resumo agregado dos pedidos:
    - total e quantidade por status
    - volume de pedidos por mês
    - top 10 clientes por número de pedidos
    """
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND po.created_at >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.created_at <= %s"
        params.append(to_date + " 23:59:59")

    by_status = posh_query(
        f"""
        SELECT status::text AS status, COUNT(*) AS total
        FROM brazil.purchase_order po
        WHERE 1=1 {date_clause}
        GROUP BY status
        ORDER BY total DESC
        """,
        params,
    )

    use_daily = False
    if from_date and to_date:
        try:
            delta = _date.fromisoformat(to_date) - _date.fromisoformat(from_date)
            use_daily = delta.days <= 31
        except ValueError:
            pass
    elif from_date:
        use_daily = True

    period_fmt = "YYYY-MM-DD" if use_daily else "YYYY-MM"

    by_month_raw = posh_query(
        f"""
        SELECT
            TO_CHAR(created_at, '{period_fmt}') AS month,
            COUNT(*) AS total_orders,
            COUNT(DISTINCT customer_id) AS unique_customers
        FROM brazil.purchase_order po
        WHERE 1=1 {date_clause}
        GROUP BY month
        ORDER BY month
        """,
        params,
    )

    if from_date and to_date:
        gran = "day" if use_daily else "month"
        actual_months = {r["month"]: r for r in by_month_raw}
        by_month = [
            actual_months.get(p, {"month": p, "total_orders": 0, "unique_customers": 0})
            for p in _gen_periods(from_date, to_date, gran)
        ]
    else:
        by_month = by_month_raw

    if group_by == "cnpj":
        tc_select = "c.cnpj AS customer_cnpj, c.name AS customer,"
        tc_group  = "c.cnpj, c.name"
    else:
        # Agrupa pela raiz do CNPJ (8 primeiros dígitos) — mesma empresa pode
        # ter filiais com CNPJs diferentes e pequenas variações de nome.
        # Usa o nome do primeiro cliente (por id) do grupo como rótulo.
        tc_select = "(array_agg(c.name ORDER BY c.id))[1] AS customer,"
        tc_group  = "LEFT(c.cnpj, 8)"

    top_customers = posh_query(
        f"""
        SELECT
            {tc_select}
            COUNT(DISTINCT po.id) AS total_orders,
            COALESCE(SUM(oi.quantity)           FILTER (WHERE po.status::text != 'REJECTED'), 0) AS total_items,
            ROUND(COALESCE(SUM(oi.value_price_total) FILTER (WHERE po.status::text != 'REJECTED'), 0)::numeric, 2) AS total_value,
            COUNT(DISTINCT po.id) FILTER (WHERE po.status::text = 'PROCESSED')     AS cnt_processed,
            COUNT(DISTINCT po.id) FILTER (WHERE po.status::text = 'INCONSISTENCY') AS cnt_inconsistency,
            COUNT(DISTINCT po.id) FILTER (WHERE po.status::text = 'REJECTED')      AS cnt_rejected
        FROM brazil.purchase_order po
        JOIN brazil.customer c ON c.id = po.customer_id
        LEFT JOIN brazil.order_item oi ON oi.purchase_order_id = po.id
        WHERE 1=1 {date_clause}
        GROUP BY {tc_group}
        ORDER BY total_orders DESC
        """,
        params,
    )

    unique_customers = posh_query_one(
        f"""
        SELECT COUNT(DISTINCT customer_id) AS total
        FROM brazil.purchase_order po
        WHERE 1=1 {date_clause}
        """,
        params,
    )

    by_delivery_month = posh_query(
        f"""
        SELECT
            TO_CHAR(delivery_month, 'YYYY-MM') AS month,
            COUNT(*) AS total_orders
        FROM brazil.purchase_order po
        WHERE delivery_month IS NOT NULL {date_clause}
        GROUP BY month
        ORDER BY month
        """,
        params,
    )

    return {
        "by_status": by_status,
        "by_month": by_month,
        "top_customers": top_customers,
        "unique_customers_total": unique_customers["total"] if unique_customers else 0,
        "by_delivery_month": by_delivery_month,
        "period_granularity": "day" if use_daily else "month",
    }


@router.get("/order-items/summary")
def order_items_summary(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    """
    Resumo de itens de pedido:
    - quantidade e valor total por status
    - top 10 produtos mais pedidos
    - itens por product_group
    """
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND po.created_at >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.created_at <= %s"
        params.append(to_date + " 23:59:59")

    by_status = posh_query(
        f"""
        SELECT
            oi.status::text AS status,
            COUNT(*) AS total_items,
            COALESCE(SUM(oi.quantity), 0) AS total_qty,
            ROUND(COALESCE(SUM(oi.value_price_total), 0)::numeric, 2) AS total_value
        FROM brazil.order_item oi
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        WHERE 1=1 {date_clause}
        GROUP BY oi.status
        ORDER BY total_items DESC
        """,
        params,
    )

    top_products = posh_query(
        f"""
        SELECT
            p.part_number,
            p.market_name,
            (array_agg(oi.local_market_name) FILTER (WHERE oi.local_market_name IS NOT NULL))[1] AS local_market_name,
            p.product_group,
            COUNT(oi.id) AS times_ordered,
            COALESCE(SUM(oi.quantity), 0) AS total_qty
        FROM brazil.order_item oi
        JOIN brazil.product p ON p.id = oi.product_id
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        WHERE oi.product_id IS NOT NULL {date_clause}
        GROUP BY p.id, p.part_number, p.market_name, p.product_group
        ORDER BY total_qty DESC
        """,
        params,
    )

    by_group = posh_query(
        f"""
        SELECT
            COALESCE(oi.product_group, 'N/A') AS product_group,
            COUNT(*) AS total_items,
            COALESCE(SUM(oi.quantity), 0) AS total_qty
        FROM brazil.order_item oi
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        WHERE 1=1 {date_clause}
        GROUP BY oi.product_group
        ORDER BY total_qty DESC
        """,
        params,
    )

    error_ratio = posh_query_one(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE oi.error_type_id IS NOT NULL)                    AS with_error,
            COUNT(*) FILTER (WHERE oi.error_type_id IS NULL)                        AS without_error,
            COUNT(DISTINCT po.id)                                                    AS total_orders,
            COUNT(DISTINCT po.id) FILTER (WHERE oi.error_type_id IS NOT NULL)       AS orders_with_inconsistency,
            ROUND(
                COUNT(*) FILTER (WHERE oi.error_type_id IS NOT NULL)::numeric
                / NULLIF(COUNT(DISTINCT po.id) FILTER (WHERE oi.error_type_id IS NOT NULL), 0),
                1
            )                                                                        AS avg_items_per_affected_order
        FROM brazil.order_item oi
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        WHERE 1=1 {date_clause}
        """,
        params,
    )

    return {
        "by_status": by_status,
        "top_products": top_products,
        "by_product_group": by_group,
        "error_ratio": error_ratio or {
            "with_error": 0, "without_error": 0,
            "total_orders": 0, "orders_with_inconsistency": 0, "avg_items_per_affected_order": 0,
        },
    }


@router.get("/customers")
def list_customers():
    """Clientes agrupados pelo CNPJ raiz (8 primeiros dígitos), ordenados por valor total de vendas desc."""
    return posh_query(
        """
        SELECT
            LEFT(REGEXP_REPLACE(c.cnpj, '[^0-9]', '', 'g'), 8) AS cnpj_root,
            MIN(c.name) AS name,
            COALESCE(SUM(oi.value_price_total), 0) AS total_value
        FROM brazil.customer c
        LEFT JOIN brazil.purchase_order po ON po.customer_id = c.id
        LEFT JOIN brazil.order_item oi ON oi.purchase_order_id = po.id
        WHERE c.cnpj IS NOT NULL AND c.cnpj != ''
        GROUP BY cnpj_root
        ORDER BY total_value DESC, name
        """,
        [],
    )


@router.get("/customers/filter-options")
def customer_filter_options():
    """Valores distintos de canal, estado e cidade para popular filtros do gráfico."""
    channels = posh_query(
        "SELECT DISTINCT channel::text AS value FROM brazil.customer"
        " WHERE channel IS NOT NULL ORDER BY value", [],
    )
    states = posh_query(
        "SELECT DISTINCT state::text AS value FROM brazil.customer"
        " WHERE state IS NOT NULL ORDER BY value", [],
    )
    cities = posh_query(
        "SELECT DISTINCT ci.name AS value FROM brazil.customer c"
        " JOIN brazil.city ci ON ci.id = c.city_id"
        " WHERE c.city_id IS NOT NULL ORDER BY value", [],
    )
    return {
        "channels": [r["value"] for r in channels],
        "states":   [r["value"] for r in states],
        "cities":   [r["value"] for r in cities],
    }


@router.get("/order-items/value-trend")
def order_items_value_trend(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    cnpj_root: Optional[str] = None,
    channel: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    granularity: str = Query(default="month", pattern="^(day|week|month|year)$"),
):
    """Valor vendido ao longo do tempo com filtros opcionais de cliente e dimensões."""
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND po.created_at >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.created_at <= %s"
        params.append(to_date + " 23:59:59")

    need_customer = bool(cnpj_root or channel or state or city)
    customer_join = "JOIN brazil.customer c ON c.id = po.customer_id" if need_customer else ""
    city_join     = "JOIN brazil.city ci ON ci.id = c.city_id"        if city          else ""

    dim_clause = ""
    if cnpj_root:
        dim_clause += " AND LEFT(REGEXP_REPLACE(c.cnpj, '[^0-9]', '', 'g'), 8) = %s"
        params.append(cnpj_root)
    if channel:
        dim_clause += " AND c.channel::text = %s"
        params.append(channel)
    if state:
        dim_clause += " AND c.state::text = %s"
        params.append(state)
    if city:
        dim_clause += " AND ci.name = %s"
        params.append(city)

    # label da série: nome representativo do filtro ativo
    if cnpj_root:
        row = posh_query_one(
            "SELECT MIN(name) AS name FROM brazil.customer"
            " WHERE LEFT(REGEXP_REPLACE(cnpj, '[^0-9]', '', 'g'), 8) = %s",
            (cnpj_root,),
        )
        series_name = row["name"] if row else cnpj_root
    elif channel:
        series_name = channel
    elif state:
        series_name = state
    elif city:
        series_name = city
    else:
        series_name = "Todos os clientes"

    period_expr = {
        "day":   "TO_CHAR(po.created_at, 'YYYY-MM-DD')",
        "week":  "TO_CHAR(DATE_TRUNC('week', po.created_at), 'YYYY-MM-DD')",
        "month": "TO_CHAR(po.created_at, 'YYYY-MM')",
        "year":  "TO_CHAR(po.created_at, 'YYYY')",
    }[granularity]

    rows = posh_query(
        f"""
        SELECT
            {period_expr} AS period,
            ROUND(COALESCE(SUM(oi.value_price_total), 0)::numeric, 2) AS total_value
        FROM brazil.order_item oi
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        {customer_join}
        {city_join}
        WHERE 1=1 {date_clause} {dim_clause}
        GROUP BY period
        ORDER BY period
        """,
        params,
    )

    actual = {r["period"]: float(r["total_value"]) for r in rows}

    if from_date and to_date:
        all_periods = _gen_periods(from_date, to_date, granularity)
        labels = all_periods
        data   = [actual.get(p, 0.0) for p in all_periods]
    else:
        labels = list(actual.keys())
        data   = list(actual.values())

    return {
        "labels": labels,
        "series": [{"name": series_name, "data": data}],
        "granularity": granularity,
    }


@router.get("/alert-resolves/by-status")
def alert_resolves_by_status(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    """
    Contagem de alertas por tipo de erro, agrupados por status do pedido:
    - Inconsistência / Rejeitado: vêm de alert_resolve (alertas ainda não resolvidos
      ou que geraram rejeição; alertas efetivamente resolvidos são removidos da tabela)
    - Processado: vêm de order_snapshot_item_issue (alert_name já é o nome do tipo)
    """
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND po.created_at >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.created_at <= %s"
        params.append(to_date + " 23:59:59")

    return posh_query(
        f"""
        SELECT
            CASE po.status::text
                WHEN 'INCONSISTENCY' THEN 'Inconsistência'
                WHEN 'REJECTED'      THEN 'Rejeitado'
            END AS category,
            COALESCE(et.name::text, 'Sem tipo') AS error_type,
            COUNT(*) AS total
        FROM brazil.alert_resolve ar
        JOIN brazil.purchase_order po ON po.id = ar.purchase_order_id
        LEFT JOIN brazil.alert_resolve_error_type aret ON aret.alert_resolve_id = ar.id
        LEFT JOIN brazil.error_type et ON et.id = aret.error_type_id
        WHERE po.status::text IN ('INCONSISTENCY', 'REJECTED') {date_clause}
        GROUP BY 1, 2

        UNION ALL

        SELECT
            'Processado' AS category,
            i.alert_name AS error_type,
            COUNT(*) AS total
        FROM brazil.order_snapshot_item_issue i
        JOIN brazil.order_snapshot os ON os.id = i.order_snapshot_id
        JOIN brazil.purchase_order po ON po.id = os.purchase_order_id
        WHERE po.status::text = 'PROCESSED' {date_clause}
        GROUP BY 1, 2
        """,
        params + params,
    )


@router.get("/alert-resolves/pending-count")
def alert_resolves_pending_count():
    """Contagem de alert_resolves pendentes (resolved_at IS NULL)."""
    return posh_query(
        "SELECT COUNT(*) AS total FROM brazil.alert_resolve WHERE resolved_at IS NULL",
        [],
    )


@router.get("/alert-resolves/by-dim")
def alert_resolves_by_dim(
    group_by: str = Query(default="name", pattern="^(name|cnpj|state|city|channel)$"),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    """Alertas resolvidos agrupados por dimensão de cliente + tipo de erro (top 20)."""
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND po.created_at >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.created_at <= %s"
        params.append(to_date + " 23:59:59")

    if group_by == "name":
        label_select  = "c.name"
        second_select = "c.cnpj"
        group_expr    = "c.name, c.cnpj"
        join_city     = ""
    elif group_by == "cnpj":
        label_select  = "c.cnpj"
        second_select = "c.name"
        group_expr    = "c.cnpj, c.name"
        join_city     = ""
    elif group_by == "state":
        label_select  = "COALESCE(c.state::text, 'N/A')"
        second_select = "NULL"
        group_expr    = "c.state"
        join_city     = ""
    elif group_by == "city":
        label_select  = "COALESCE(ci.name, 'N/A')"
        second_select = "NULL"
        group_expr    = "ci.name"
        join_city     = "LEFT JOIN brazil.city ci ON ci.id = c.city_id"
    else:  # channel
        label_select  = "COALESCE(c.channel::text, 'N/A')"
        second_select = "NULL"
        group_expr    = "c.channel"
        join_city     = ""

    return posh_query(
        f"""
        WITH base AS (
            SELECT
                {label_select} AS label,
                {second_select}::text AS secondary,
                COALESCE(et.name::text, 'Sem tipo') AS error_type,
                COUNT(*) AS cnt
            FROM brazil.alert_resolve ar
            JOIN brazil.purchase_order po ON po.id = ar.purchase_order_id
            JOIN brazil.customer c ON c.id = po.customer_id
            {join_city}
            LEFT JOIN brazil.alert_resolve_error_type aret ON aret.alert_resolve_id = ar.id
            LEFT JOIN brazil.error_type et ON et.id = aret.error_type_id
            WHERE po.status::text IN ('INCONSISTENCY', 'REJECTED') {date_clause}
            GROUP BY {group_expr}, et.name

            UNION ALL

            -- Pedidos PROCESSED: o tipo de erro original foi removido de
            -- alert_resolve_error_type e movido para order_snapshot_item_issue
            -- (campo alert_name já é o nome do tipo, sem necessidade de mapeamento)
            SELECT
                {label_select} AS label,
                {second_select}::text AS secondary,
                i.alert_name AS error_type,
                COUNT(*) AS cnt
            FROM brazil.alert_resolve ar
            JOIN brazil.purchase_order po ON po.id = ar.purchase_order_id
            JOIN brazil.customer c ON c.id = po.customer_id
            {join_city}
            JOIN brazil.order_snapshot os ON os.purchase_order_id = ar.purchase_order_id
            JOIN brazil.order_snapshot_item_issue i ON i.order_snapshot_id = os.id
            WHERE po.status::text = 'PROCESSED' {date_clause}
            GROUP BY {group_expr}, i.alert_name
        ),
        ranked AS (
            SELECT label, secondary,
                   SUM(cnt) AS label_total,
                   ROW_NUMBER() OVER (ORDER BY SUM(cnt) DESC) AS rn
            FROM base
            GROUP BY label, secondary
        )
        SELECT b.label, b.secondary, b.error_type, SUM(b.cnt) AS cnt
        FROM base b
        JOIN ranked r ON r.label IS NOT DISTINCT FROM b.label
                     AND r.secondary IS NOT DISTINCT FROM b.secondary
        WHERE r.rn <= 20
        GROUP BY b.label, b.secondary, b.error_type, r.label_total
        ORDER BY r.label_total DESC, b.label, b.error_type
        """,
        params + params,
    )


@router.get("/orders/by-customer-dim")
def orders_by_customer_dim(
    group_by: str = Query(default="channel", pattern="^(channel|state|city)$"),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    """Pedidos agregados por dimensão de cliente: channel, state ou city."""
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND po.created_at >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.created_at <= %s"
        params.append(to_date + " 23:59:59")

    if group_by == "channel":
        select_label = "COALESCE(c.channel::text, 'N/A') AS label"
        group_expr   = "c.channel::text"
        join_city    = ""
    elif group_by == "state":
        select_label = "COALESCE(c.state::text, 'N/A') AS label"
        group_expr   = "c.state::text"
        join_city    = ""
    else:  # city
        select_label = "COALESCE(ci.name, 'N/A') AS label"
        group_expr   = "ci.name"
        join_city    = "LEFT JOIN brazil.city ci ON ci.id = c.city_id"

    return posh_query(
        f"""
        SELECT
            {select_label},
            COUNT(DISTINCT po.id) AS total_orders,
            COALESCE(SUM(oi.quantity), 0) AS total_items,
            ROUND(COALESCE(SUM(oi.value_price_total), 0)::numeric, 2) AS total_value
        FROM brazil.purchase_order po
        JOIN brazil.customer c ON c.id = po.customer_id
        LEFT JOIN brazil.order_item oi ON oi.purchase_order_id = po.id
        {join_city}
        WHERE 1=1 {date_clause}
        GROUP BY {group_expr}
        ORDER BY total_orders DESC
        """,
        params,
    )



# ── catálogos ─────────────────────────────────────────────────────────────────

@router.get("/customers")
def list_customers(
    search: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = Query(default=100, le=500),
):
    """Lista clientes, com busca por nome/CNPJ e filtro por canal."""
    clauses = []
    params: list = []

    if search:
        clauses.append("(c.name ILIKE %s OR c.cnpj ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    if channel:
        clauses.append("c.channel::text = %s")
        params.append(channel)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    return posh_query(
        f"""
        SELECT
            c.id,
            c.name,
            c.customer_short,
            c.cnpj,
            c.channel::text AS channel,
            c.state::text AS state,
            c.regional,
            ct.name AS city
        FROM brazil.customer c
        LEFT JOIN brazil.city ct ON ct.id = c.city_id
        {where}
        ORDER BY c.name
        LIMIT %s
        """,
        params + [limit],
    )


@router.get("/products")
def list_products(
    search: Optional[str] = None,
    product_group: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=500),
):
    """Lista produtos do catálogo brazil."""
    clauses = []
    params: list = []

    if search:
        clauses.append("(p.part_number ILIKE %s OR p.market_name ILIKE %s OR p.local_market_name ILIKE %s)")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if product_group:
        clauses.append("p.product_group ILIKE %s")
        params.append(f"%{product_group}%")
    if status:
        clauses.append("p.status::text = %s")
        params.append(status)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    return posh_query(
        f"""
        SELECT
            p.id,
            p.part_number,
            p.product_group,
            p.market_name,
            p.local_market_name,
            p.local_color,
            p.ean,
            p.origin,
            p.status::text AS status,
            p.ram,
            p.rom
        FROM brazil.product p
        {where}
        ORDER BY p.product_group, p.part_number
        LIMIT %s
        """,
        params + [limit],
    )
