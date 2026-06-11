# -*- coding: utf-8 -*-
"""
Servidor de mock para captura do mfg-dashboard.html no Figma.
Serve o HTML original + todos os endpoints que a página consome,
com dados simulados realistas (mesmos formatos de routers/brazil.py).

Uso:  python -m uvicorn figma_mock_server:app --port 8000
Estados extras p/ captura:  /?state=alerts|agenda|artifacts|audit|chathist|chartmodal|error
"""
import struct
import zlib
from pathlib import Path

from fastapi import FastAPI, Query, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

HTML_PATH = Path(__file__).parent / "mfg-dashboard.html"

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Script injetado: abre painéis/modais conforme ?state= para capturas de estado.
# Sem depender de timing: mata as transições CSS, dispara cedo (DOMContentLoaded)
# e re-dispara em seguida por garantia (handlers são idempotentes).
STATE_SCRIPT = """
<style>
  #alertsPanel, #agendaPanel, #artifactsPanel, #auditPanel,
  .chat-hist-panel, .chat-sidebar { transition: none !important; }
</style>
<script>
(function(){
  var st = new URLSearchParams(location.search).get('state');
  if (!st) return;
  function fire(){
    try {
      if (st==='alerts') openAlertsPanel();
      else if (st==='agenda') openAgenda();
      else if (st==='artifacts') openArtifacts();
      else if (st==='audit') openAudit();
      else if (st==='chathist') { openChat(); showHistory(); }
      else if (st==='chatclosed') closeChat();
      else if (st==='chatopen') openChat();
      else if (st==='customdate') {
        var sel = document.getElementById('kpiFromSel');
        sel.value = 'custom';
        document.getElementById('customFrom').value = '2026-01-01';
        document.getElementById('customTo').value = '2026-06-10';
        document.getElementById('customDatePicker').classList.add('visible');
      }
      else if (st==='taskcode') openTaskCode('T-101');
      else if (st==='auditcode') { openAudit(); openAuditCode(1); }
      else if (st==='runerror') {
        showRunError('Traceback (most recent call last):\\n  File "task_code.py", line 14, in <module>\\n    df = pd.read_sql(query, conn)\\npandas.errors.DatabaseError: Execution failed on sql: relation "brazil.order_item" does not exist\\nLINE 3:     FROM brazil.order_itens oi\\n                 ^\\nHINT: Perhaps you meant to reference the table "brazil.order_item".');
      }
      else if (st==='chartmodal') openChartModal('ordersMonthChart');
      else if (st==='error') {
        document.getElementById('errorOverlay').classList.remove('hidden');
        setApiOffline();
      }
      else if (st==='loading') {
        document.getElementById('loadingOverlay').classList.remove('hidden');
      }
    } catch(e) { console.error('state script:', e); }
  }
  document.addEventListener('DOMContentLoaded', function(){ setTimeout(fire, 600); });
  window.addEventListener('load', function(){ setTimeout(fire, 1500); setTimeout(fire, 3000); });
})();
</script>
"""


FIGMA_CAPTURE_TAG = '<script src="https://mcp.figma.com/mcp/html-to-design/capture.js" async></script>'


@app.get("/", response_class=HTMLResponse)
def index():
    html = HTML_PATH.read_text(encoding="utf-8")
    html = html.replace("</head>", FIGMA_CAPTURE_TAG + "\n</head>")
    return HTMLResponse(html.replace("</body>", STATE_SCRIPT + "\n</body>"))


# ── /brazil/orders/summary ────────────────────────────────────────────────────
MONTHS = [
    "2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
    "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12",
    "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
]
ORDERS_BY_MONTH = [380, 412, 455, 498, 530, 575, 612, 648, 690, 735, 760, 802,
                   845, 880, 921, 958, 1004, 1042]
UNIQUE_BY_MONTH = [42, 45, 49, 52, 55, 58, 61, 63, 66, 70, 72, 75,
                   78, 80, 83, 85, 87, 88]

CUSTOMERS = [
    ("Distribuidora Horizonte LTDA", "12.345.678/0001-90"),
    ("Magazine Estrela S.A.",        "23.456.789/0001-01"),
    ("Atacadão Nacional",            "34.567.890/0001-12"),
    ("Eletro Mais Comércio",         "45.678.901/0001-23"),
    ("TecnoCenter Distribuição",     "56.789.012/0001-34"),
    ("Rede Conecta Varejo",          "67.890.123/0001-45"),
    ("Mega Eletrônicos BR",          "78.901.234/0001-56"),
    ("Comercial Andrade & Filhos",   "89.012.345/0001-67"),
    ("NorteSul Atacado",             "90.123.456/0001-78"),
    ("Via Digital Comércio",         "01.234.567/0001-89"),
    ("Prime Tech Distribuidora",     "11.222.333/0001-44"),
    ("Eletrônica Pioneira",          "22.333.444/0001-55"),
    ("Grupo Vale Verde",             "33.444.555/0001-66"),
    ("Casa do Celular MG",           "44.555.666/0001-77"),
    ("Top Mobile Distribuição",      "55.666.777/0001-88"),
    ("Infomax Atacadista",           "66.777.888/0001-99"),
    ("Connect Brasil Telecom",       "77.888.999/0001-00"),
    ("Smart Shop Varejo",            "88.999.000/0001-11"),
    ("Distribuidora Atlântico",      "99.000.111/0001-22"),
    ("JC Eletro Comercial",          "10.111.222/0001-33"),
    ("Planeta Cell Atacado",         "20.222.333/0001-44"),
    ("FastPhone Distribuição",       "30.333.444/0001-55"),
    ("Universo Mobile LTDA",         "40.444.555/0001-66"),
]

TC_ORDERS = [1240, 1105, 980, 875, 790, 715, 660, 598, 540, 486, 430, 384,
             341, 305, 272, 240, 211, 184, 158, 134, 92, 68, 45]


def _top_customers():
    rows = []
    for (name, cnpj), orders in zip(CUSTOMERS, TC_ORDERS):
        rej = max(1, orders // 28)
        inc = max(2, orders // 11)
        pen = max(1, orders // 16)
        rows.append({
            "customer": name,
            "customer_cnpj": cnpj,
            "total_orders": orders,
            "total_items": orders * 3 + 57,
            "total_value": round(orders * 4231.75, 2),
            "cnt_approved": orders - rej - inc - pen,
            "cnt_inconsistency": inc,
            "cnt_rejected": rej,
            "cnt_pending": pen,
        })
    return rows


@app.get("/brazil/orders/summary")
def orders_summary(group_by: str = Query(default="name")):
    return {
        "by_status": [
            {"status": "APPROVED", "total": 9482},
            {"status": "INCONSISTENCY", "total": 1236},
            {"status": "PENDING", "total": 864},
            {"status": "REJECTED", "total": 418},
        ],
        "by_month": [
            {"month": m, "total_orders": o, "unique_customers": u}
            for m, o, u in zip(MONTHS, ORDERS_BY_MONTH, UNIQUE_BY_MONTH)
        ],
        "top_customers": _top_customers(),
        "unique_customers_total": 412,
        "by_delivery_month": [
            {"month": m, "total_orders": o} for m, o in zip(MONTHS, ORDERS_BY_MONTH)
        ],
        "period_granularity": "month",
    }


# ── /brazil/order-items/summary ───────────────────────────────────────────────
TOP_PRODUCTS = [
    ("XT2341-3", "MOTO G84 5G", 9650),
    ("XT2335-2", "MOTO G54 5G", 8420),
    ("XT2303-1", "EDGE 40 NEO", 7180),
    ("XT2251-4", "MOTO E22", 6540),
    ("XT2201-6", "EDGE 30 ULTRA", 5870),
    ("XT2167-9", "MOTO G32", 5230),
    ("PA-88231", "CARREG. TURBO 30W", 4610),
    ("PA-77412", "FONE BUDS+", 3950),
    ("XT2129-5", "MOTO G60S", 3120),
    ("XT2043-7", "MOTO E40", 2480),
]


@app.get("/brazil/order-items/summary")
def order_items_summary():
    return {
        "by_status": [
            {"status": "APPROVED", "total_items": 26480, "total_qty": 89342, "total_value": 41214380.00},
            {"status": "PENDING", "total_items": 3214, "total_qty": 10871, "total_value": 5642190.00},
            {"status": "INCONSISTENCY", "total_items": 3102, "total_qty": 9456, "total_value": 4889340.00},
            {"status": "REJECTED", "total_items": 1212, "total_qty": 3870, "total_value": 1766570.00},
        ],
        "top_products": [
            {"part_number": pn, "market_name": mn, "product_group": "SMARTPHONE",
             "times_ordered": q // 9, "total_qty": q}
            for pn, mn, q in TOP_PRODUCTS
        ],
        "by_product_group": [
            {"product_group": "SMARTPHONE", "total_items": 26120, "total_qty": 88410},
            {"product_group": "ACESSORIO", "total_items": 7888, "total_qty": 25129},
        ],
        "error_ratio": {
            "with_error": 3842,
            "without_error": 30166,
            "total_orders": 12000,
            "orders_with_inconsistency": 1236,
            "avg_items_per_affected_order": 3.1,
        },
    }


# ── /brazil/alert-resolves/* ──────────────────────────────────────────────────
ERROR_TYPES = ["Preço divergente", "Cadastro incompleto", "Prazo inválido",
               "Quantidade inválida"]


@app.get("/brazil/alert-resolves/by-status")
def alert_resolves_by_status():
    return [
        {"status": "Preço divergente", "total": 642},
        {"status": "Cadastro incompleto", "total": 415},
        {"status": "Prazo inválido", "total": 289},
        {"status": "Quantidade inválida", "total": 174},
        {"status": "Sem tipo", "total": 96},
    ]


@app.get("/brazil/alert-resolves/pending-count")
def alert_resolves_pending_count():
    return [{"total": 37}]


DIM_LABELS = {
    "state": ["SP", "MG", "RJ", "PR", "RS", "SC", "BA", "AM", "GO", "PE",
              "CE", "DF", "ES", "MT", "MS", "PA", "PB", "RN", "AL", "SE"],
    "city": ["São Paulo", "Belo Horizonte", "Rio de Janeiro", "Curitiba",
             "Porto Alegre", "Florianópolis", "Salvador", "Manaus", "Goiânia",
             "Recife", "Fortaleza", "Brasília", "Vitória", "Cuiabá",
             "Campo Grande", "Belém", "João Pessoa", "Natal", "Maceió", "Aracaju"],
    "channel": ["VAREJO", "DISTRIBUIDOR", "ATACADO", "E-COMMERCE", "OPERADORA"],
}


@app.get("/brazil/alert-resolves/by-dim")
def alert_resolves_by_dim(group_by: str = Query(default="name")):
    rows = []
    if group_by in ("name", "cnpj"):
        entries = [
            (n if group_by == "name" else c, c if group_by == "name" else n)
            for n, c in CUSTOMERS[:20]
        ]
    else:
        entries = [(lbl, None) for lbl in DIM_LABELS[group_by]]
    base = 188
    for i, (label, secondary) in enumerate(entries):
        total = max(6, base - i * 9)
        split = [total // 2, total // 3, total - total // 2 - total // 3]
        for et, cnt in zip(ERROR_TYPES[: 3], split):
            if cnt > 0:
                rows.append({"label": label, "secondary": secondary,
                             "error_type": et, "cnt": cnt})
    return rows


# ── /brazil/orders/by-customer-dim ────────────────────────────────────────────
DIM_ORDERS = {
    "channel": [4820, 3610, 1950, 1120, 500],
    "state": [3940, 1870, 1520, 1180, 1020, 840, 760, 520, 350, 290,
              240, 210, 180, 150, 130, 110, 95, 80, 65, 50],
    "city": [3650, 1740, 1430, 1090, 940, 780, 700, 480, 330, 270,
             225, 195, 168, 140, 120, 102, 88, 74, 60, 46],
}


@app.get("/brazil/orders/by-customer-dim")
def orders_by_customer_dim(group_by: str = Query(default="channel")):
    labels = DIM_LABELS[group_by]
    values = DIM_ORDERS[group_by]
    return [
        {"label": lbl, "total_orders": v, "total_items": v * 3 + 41,
         "total_value": round(v * 4187.50, 2)}
        for lbl, v in zip(labels, values)
    ]


# ── /brazil/order-items/value-trend ───────────────────────────────────────────
TREND_MONTH = [1450000, 1592000, 1738000, 1905000, 2080000, 2244000,
               2410000, 2596000, 2770000, 2958000, 3125000, 3340000,
               3552000, 3718000, 3940000, 4172000, 4456000, 4810000]


@app.get("/brazil/order-items/value-trend")
def value_trend(
    granularity: str = Query(default="month"),
    cnpj_root: str = Query(default=None),
    channel: str = Query(default=None),
    state: str = Query(default=None),
    city: str = Query(default=None),
):
    name = cnpj_root and "Distribuidora Horizonte LTDA" or channel or state or city or "Todos os clientes"
    if granularity == "year":
        labels = ["2025", "2026"]
        data = [sum(TREND_MONTH[:12]), sum(TREND_MONTH[12:])]
    elif granularity == "week":
        labels = [f"2026-{m:02d}-{d:02d}" for m, d in
                  [(1, 5), (1, 12), (1, 19), (1, 26), (2, 2), (2, 9), (2, 16), (2, 23),
                   (3, 2), (3, 9), (3, 16), (3, 23), (3, 30), (4, 6), (4, 13), (4, 20),
                   (4, 27), (5, 4), (5, 11), (5, 18), (5, 25), (6, 1), (6, 8)]]
        data = [820000 + i * 31000 for i in range(len(labels))]
    elif granularity == "day":
        labels = [f"2026-06-{d:02d}" for d in range(1, 11)]
        data = [148000, 156000, 162000, 151000, 170000, 175000, 168000, 182000, 188000, 195000]
    else:
        labels = MONTHS
        data = TREND_MONTH
    return {"labels": labels, "series": [{"name": name, "data": data}],
            "granularity": granularity}


# ── catálogos ─────────────────────────────────────────────────────────────────
@app.get("/brazil/customers")
def list_customers():
    return [
        {"cnpj_root": c.replace(".", "").replace("/", "").replace("-", "")[:8],
         "name": n, "total_value": 1000000 - i * 50000}
        for i, (n, c) in enumerate(CUSTOMERS[:10])
    ]


@app.get("/brazil/customers/filter-options")
def filter_options():
    return {
        "channels": ["ATACADO", "DISTRIBUIDOR", "E-COMMERCE", "OPERADORA", "VAREJO"],
        "states": ["AM", "BA", "GO", "MG", "PR", "RJ", "RS", "SC", "SP"],
        "cities": ["Belo Horizonte", "Campinas", "Curitiba", "Manaus",
                   "Porto Alegre", "Rio de Janeiro", "Salvador", "São Paulo"],
    }


# ── chat ──────────────────────────────────────────────────────────────────────
@app.get("/chat/history")
def chat_history(session_id: str = Query(default="")):
    return []


@app.get("/chat/sessions")
def chat_sessions(user_id: str = Query(default="")):
    return [
        {"session_id": "s1", "title": "Análise de defeitos por turno", "message_count": 8},
        {"session_id": "s2", "title": "Top 10 clientes do mês", "message_count": 5},
        {"session_id": "s3", "title": "Relatório de inconsistências em PDF", "message_count": 12},
    ]


@app.post("/chart-snapshot")
def chart_snapshot():
    return {"ok": True}


# ── tarefas (agenda) ──────────────────────────────────────────────────────────
TASKS = [
    {
        "id": "T-101", "name": "Relatório diário de pedidos", "status": "active",
        "frequency": "daily", "time": "08:00", "notify": True,
        "description": "Gera PDF com o resumo de pedidos do dia anterior e envia por email.",
        "email": "operacoes@empresa.com.br", "next_run": "2026-06-11 08:00",
        "retry_count": 0, "max_retries": 3, "date_range": None,
        "condition_sql": None, "condition_operator": None,
        "condition_threshold": None, "condition_state": False,
        "runs": [
            {"status": "success", "started_at": "2026-06-10T08:00:12", "ended_at": "2026-06-10T08:00:58", "error": None},
            {"status": "success", "started_at": "2026-06-09T08:00:09", "ended_at": "2026-06-09T08:00:51", "error": None},
            {"status": "error", "started_at": "2026-06-08T08:00:11", "ended_at": "2026-06-08T08:02:44",
             "error": "TimeoutError: conexão com o serviço de email excedeu 120s"},
        ],
    },
    {
        "id": "T-102", "name": "Alerta de inconsistências", "status": "active",
        "frequency": "every_30m", "time": "", "notify": True,
        "description": "Monitora itens com inconsistência nas últimas 24h e dispara alerta acima do limite.",
        "email": None, "next_run": "2026-06-10 10:30",
        "retry_count": 1, "max_retries": 3, "date_range": None,
        "condition_sql": "SELECT COUNT(*) FROM order_item WHERE error_type_id IS NOT NULL",
        "condition_operator": ">", "condition_threshold": 50, "condition_state": True,
        "runs": [
            {"status": "running", "started_at": "2026-06-10T10:00:02", "ended_at": None, "error": None},
            {"status": "success", "started_at": "2026-06-10T09:30:01", "ended_at": "2026-06-10T09:30:18", "error": None},
        ],
    },
    {
        "id": "T-103", "name": "Fechamento semanal em Excel", "status": "paused",
        "frequency": "weekly", "weekday": "monday", "time": "07:30", "notify": False,
        "description": "Exporta planilha consolidada de pedidos, itens e valores da semana.",
        "email": "gestao@empresa.com.br", "next_run": "2026-06-15 07:30",
        "retry_count": 0, "max_retries": 3, "date_range": "últimos 7 dias",
        "condition_sql": None, "condition_operator": None,
        "condition_threshold": None, "condition_state": False,
        "runs": [
            {"status": "success", "started_at": "2026-06-08T07:30:05", "ended_at": "2026-06-08T07:31:22", "error": None},
        ],
    },
]


@app.get("/tasks")
def tasks(user_id: str = Query(default="")):
    return TASKS


@app.get("/tasks/{task_id}/code")
def task_code(task_id: str, user_id: str = Query(default="")):
    return {
        "name": "Relatório diário de pedidos",
        "task_code": (
            "import pandas as pd\n\n"
            "# Busca pedidos do dia anterior\n"
            "df = run_sql(\"\"\"\n"
            "    SELECT po.id, c.name AS cliente, po.status, po.created_at\n"
            "    FROM brazil.purchase_order po\n"
            "    JOIN brazil.customer c ON c.id = po.customer_id\n"
            "    WHERE po.created_at::date = CURRENT_DATE - 1\n"
            "\"\"\")\n\n"
            "resumo = df.groupby('status').size().to_dict()\n"
            "fig = plot_bar(resumo, title='Pedidos por status — ontem')\n"
            "pdf = make_pdf(title='Relatório diário de pedidos',\n"
            "               charts=[fig], table=df.head(50))\n"
            "send_email(to=task.email, subject='Relatório diário',\n"
            "           attachments=[pdf])\n"
        ),
        "instructions": None,
        "versions": [
            {"version": 2, "created_at": "2026-06-05T10:12:00",
             "code": "import pandas as pd\ndf = run_sql('SELECT * FROM brazil.purchase_order')\nmake_pdf(df)"},
            {"version": 1, "created_at": "2026-06-01T09:00:00",
             "code": "df = run_sql('SELECT count(*) FROM purchase_order')\nprint(df)"},
        ],
    }


@app.get("/tasks/code-audit/summary")
def code_audit_summary():
    return [
        {"id": 1, "task_id": "T-102", "phase": "create", "attempt": 1,
         "error": "SyntaxError: invalid syntax (linha 12) — f-string sem fechamento",
         "code": "import pandas as pd\n\ndf = run_sql(\"SELECT * FROM order_item\")\nprint(f\"total: {len(df)\")",
         "created_at": "2026-06-08T14:22:10"},
        {"id": 2, "task_id": "T-101", "phase": "run", "attempt": 2,
         "error": "NameError: name 'df_orders' is not defined",
         "code": "total = df_orders['value'].sum()\nmake_pdf(total)",
         "created_at": "2026-06-07T08:01:33"},
        {"id": 3, "task_id": "T-103", "phase": "create", "attempt": 3,
         "error": "Import de 'requests' bloqueado no sandbox — use apenas módulos permitidos",
         "code": "import requests\nresp = requests.get('https://api.exemplo.com')",
         "created_at": "2026-06-05T07:30:48"},
        {"id": 4, "task_id": "T-101", "phase": "run", "attempt": 1,
         "error": "KeyError: 'total_value'",
         "code": "valor = row['total_value']",
         "created_at": "2026-06-04T08:00:27"},
    ]


# ── alertas ───────────────────────────────────────────────────────────────────
ALERTS = [
    {"id": "a1", "message": "Inconsistências acima do limite: 62 itens nas últimas 24h",
     "value": 62, "threshold": 50, "created_at": "2026-06-10T09:42:00",
     "read": False, "task_id": "T-102", "task_name": "Alerta de inconsistências"},
    {"id": "a2", "message": "Pedidos rejeitados subiram 18% em relação à semana anterior",
     "value": 118, "threshold": 100, "created_at": "2026-06-10T08:15:00",
     "read": False, "task_id": "T-102", "task_name": "Alerta de inconsistências"},
    {"id": "a3", "message": "Relatório diário de pedidos enviado com sucesso",
     "value": None, "threshold": None, "created_at": "2026-06-10T08:01:00",
     "read": True, "task_id": "T-101", "task_name": "Relatório diário de pedidos"},
    {"id": "a4", "message": "Tarefa T-103 pausada pelo usuário",
     "value": None, "threshold": None, "created_at": "2026-06-09T16:30:00",
     "read": True, "task_id": "T-103", "task_name": "Fechamento semanal em Excel"},
]


@app.get("/alerts")
def alerts(all: bool = Query(default=False), user_id: str = Query(default="")):
    if all:
        return ALERTS
    return [a for a in ALERTS if not a["read"]]


@app.post("/alerts/read-all")
def alerts_read_all(user_id: str = Query(default="")):
    return {"ok": True}


# ── artifacts ─────────────────────────────────────────────────────────────────
@app.get("/artifacts")
def artifacts():
    return [
        {"id": "11111111-1111-1111-1111-111111111111", "type": "pdf",
         "filename": "relatorio_pedidos_2026-06-09.pdf", "label": "Relatório de pedidos",
         "created_at": "2026-06-10T08:00:55", "origin": "task", "task_id": "T-101",
         "session_id": "task_T-101"},
        {"id": "22222222-2222-2222-2222-222222222222", "type": "excel",
         "filename": "fechamento_semana23.xlsx", "label": "Fechamento semanal",
         "created_at": "2026-06-08T07:31:20", "origin": "task", "task_id": "T-103",
         "session_id": "task_T-103"},
        {"id": "33333333-3333-3333-3333-333333333333", "type": "chart",
         "filename": "tendencia_valor_mensal.png", "label": "Tendência de valor",
         "created_at": "2026-06-09T15:12:00", "origin": "chat", "task_id": None,
         "session_id": "s1"},
        {"id": "44444444-4444-4444-4444-444444444444", "type": "pdf",
         "filename": "analise_clientes_top10.pdf", "label": "Análise de clientes",
         "created_at": "2026-06-09T11:40:00", "origin": "chat", "task_id": None,
         "session_id": "s2"},
        {"id": "55555555-5555-5555-5555-555555555555", "type": "excel",
         "filename": "top_produtos_2026.xlsx", "label": "Top produtos",
         "created_at": "2026-06-08T17:05:00", "origin": "chat", "task_id": None,
         "session_id": "s2"},
    ]


# ── widgets customizados ──────────────────────────────────────────────────────
@app.get("/dashboard-widgets")
def dashboard_widgets(user_id: str = Query(default="")):
    return [
        {"id": "w1", "title": "Pedidos por canal — últimos 30 dias"},
        {"id": "w2", "title": "Ticket médio por estado (R$)"},
    ]


@app.get("/dashboard-widgets/{widget_id}/data")
def widget_data(widget_id: str):
    if widget_id == "w1":
        return {
            "type": "bar",
            "data": {
                "labels": ["VAREJO", "DISTRIBUIDOR", "ATACADO", "E-COMMERCE", "OPERADORA"],
                "datasets": [{
                    "label": "Pedidos",
                    "data": [432, 318, 176, 98, 41],
                    "backgroundColor": ["rgba(96,165,250,.8)", "rgba(52,211,153,.8)",
                                        "rgba(251,191,36,.8)", "rgba(167,139,250,.8)",
                                        "rgba(248,113,113,.8)"],
                    "borderRadius": 3,
                }],
            },
            "options": {},
        }
    return {
        "type": "line",
        "data": {
            "labels": ["SP", "MG", "RJ", "PR", "RS", "SC", "BA"],
            "datasets": [{
                "label": "Ticket médio",
                "data": [4870, 4420, 4615, 4180, 4032, 3940, 3710],
                "borderColor": "#38bdf8",
                "backgroundColor": "rgba(56,189,248,0.10)",
                "fill": True,
                "tension": 0.35,
            }],
        },
        "options": {},
    }


# ── imagem placeholder p/ artifacts tipo chart ────────────────────────────────
def _chart_png() -> bytes:
    w, h = 640, 320
    bg = (13, 21, 38)
    grid = (24, 36, 56)
    px = [[bg] * w for _ in range(h)]
    for gy in range(40, h - 30, 50):
        for x in range(30, w - 20):
            px[gy][x] = grid
    bars = [(50, 140, (56, 189, 248)), (120, 190, (96, 165, 250)),
            (190, 110, (56, 189, 248)), (260, 230, (52, 211, 153)),
            (330, 170, (96, 165, 250)), (400, 250, (56, 189, 248)),
            (470, 200, (52, 211, 153)), (540, 265, (56, 189, 248))]
    for x0, bh, color in bars:
        for y in range(h - 30 - bh, h - 30):
            for x in range(x0, x0 + 52):
                px[y][x] = color
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


_PNG_CACHE = _chart_png()


@app.get("/chart/{chart_id}")
def chart_image(chart_id: str):
    return Response(content=_PNG_CACHE, media_type="image/png")
