from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db_posh import posh_query, posh_query_one

router = APIRouter(tags=["brazil"])


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
        clauses.append("po.issue_date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("po.issue_date <= %s")
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
        ORDER BY po.issue_date DESC
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
        clauses.append("po.issue_date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("po.issue_date <= %s")
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
            po.issue_date,
            po.customer_name
        FROM brazil.order_item oi
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        {where}
        ORDER BY po.issue_date DESC, oi.item_number
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )


# ── summaries ─────────────────────────────────────────────────────────────────

@router.get("/orders/summary")
def orders_summary(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
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
        date_clause += " AND po.issue_date >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.issue_date <= %s"
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

    from datetime import date, timedelta
    use_daily = False
    if from_date and to_date:
        try:
            delta = date.fromisoformat(to_date) - date.fromisoformat(from_date)
            use_daily = delta.days <= 31
        except ValueError:
            pass
    elif from_date:
        use_daily = True

    period_fmt = "YYYY-MM-DD" if use_daily else "YYYY-MM"

    by_month = posh_query(
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

    top_customers = posh_query(
        f"""
        SELECT
            c.name AS customer,
            c.id AS customer_id,
            COUNT(po.id) AS total_orders
        FROM brazil.purchase_order po
        JOIN brazil.customer c ON c.id = po.customer_id
        WHERE 1=1 {date_clause}
        GROUP BY c.id, c.name
        ORDER BY total_orders DESC
        LIMIT 10
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
        date_clause += " AND po.issue_date >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.issue_date <= %s"
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
            p.product_group,
            COUNT(oi.id) AS times_ordered,
            COALESCE(SUM(oi.quantity), 0) AS total_qty
        FROM brazil.order_item oi
        JOIN brazil.product p ON p.id = oi.product_id
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        WHERE oi.product_id IS NOT NULL {date_clause}
        GROUP BY p.id, p.part_number, p.market_name, p.product_group
        ORDER BY total_qty DESC
        LIMIT 10
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
            COUNT(*) FILTER (WHERE oi.error_type_id IS NOT NULL) AS with_error,
            COUNT(*) FILTER (WHERE oi.error_type_id IS NULL)     AS without_error
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
        "error_ratio": error_ratio or {"with_error": 0, "without_error": 0},
    }


@router.get("/alert-resolves/by-status")
def alert_resolves_by_status(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    """Contagem de alert_resolves por status, filtrado por created_at."""
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND ar.created_at >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND ar.created_at <= %s"
        params.append(to_date + " 23:59:59")

    return posh_query(
        f"""
        SELECT
            ar.status::text AS status,
            COUNT(*) AS total
        FROM brazil.alert_resolve ar
        WHERE 1=1 {date_clause}
        GROUP BY ar.status
        ORDER BY total DESC
        """,
        params,
    )


@router.get("/order-items/errors-by-type")
def order_items_errors_by_type(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    """Contagem de itens com erro, agrupada por tipo de erro."""
    date_clause = ""
    params: list = []
    if from_date:
        date_clause += " AND po.issue_date >= %s"
        params.append(from_date)
    if to_date:
        date_clause += " AND po.issue_date <= %s"
        params.append(to_date + " 23:59:59")

    return posh_query(
        f"""
        SELECT
            et.name AS error_type,
            COUNT(*) AS total
        FROM brazil.order_item oi
        JOIN brazil.purchase_order po ON po.id = oi.purchase_order_id
        JOIN brazil.error_type et ON et.id = oi.error_type_id
        WHERE oi.error_type_id IS NOT NULL {date_clause}
        GROUP BY et.name
        ORDER BY total DESC
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
