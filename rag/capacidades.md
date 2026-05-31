# Capacidades do agente — Brazil Purchase Orders AI

O agente responde em linguagem natural sobre pedidos de compra, clientes, produtos, erros e alertas.

## Arquitetura simples

| Camada | Responsabilidade |
|--------|-----------------|
| Endpoints REST | Alimentar os gráficos fixos do dashboard — não são usados pelo agente para análise |
| `analise_sql_livre` | **Única skill de análise** — toda pergunta de dados usa SQL direto no banco |

## Como o agente responde perguntas de dados

```
Usuário faz uma pergunta
      ↓
Orquestrador → consultar_analista()
      ↓
Sub-agente lê analise_sql_livre.md
      ↓
Escreve e executa SQL no PostgreSQL
      ↓
Processa resultado com pandas
      ↓
Responde com tabela ou gráfico
```

## Tipos de análise suportados

**Por tempo:** pedidos hoje, esta semana, este mês, últimos N dias, por dia/mês/ano

**Por cliente:** ranking de clientes, por canal, por estado, por regional

**Por produto:** mais pedidos, por grupo, por part_number, por especificação (ram, rom)

**Por status:** pedidos aprovados/pendentes/inconsistentes/rejeitados; itens por status

**Por erro:** quais erros ocorreram, por cliente, por tipo, frequência

**Por valor:** valor total, valor médio, distribuição por cliente ou produto

**Cruzamentos:** qualquer combinação das dimensões acima via JOIN

## Formatos de saída

- Tabela markdown
- Gráfico (barra, linha, pizza, dispersão)
- PDF com análise e gráficos
- Planilha Excel para download

## Períodos aceitos em linguagem natural

"hoje", "ontem", "esta semana", "semana passada", "últimos N dias", "este mês", "mês passado", "este ano", datas explícitas (ex: "de 01/05 a 28/05")

## Tarefas agendadas

O agente pode criar tarefas que rodam automaticamente.

**Relatórios periódicos:**
- "Toda segunda às 8h me manda o resumo de pedidos da semana"
- "Todo dia às 7h gera um PDF com os pedidos do dia anterior"
- "Todo primeiro do mês exporta os dados para Excel"

**Monitores com alertas:**
- "Me avise se chegarem mais de 50 pedidos com inconsistência hoje"
- "Alerta quando o total de aprovados ficar abaixo de 10 no dia"

Frequências: `once`, `daily`, `weekly`, `monthly`, `every_Xm`, `every_Xh`, `every_Xd`

**Gerenciamento:** "Liste as tarefas", "Pause a tarefa 003", "Delete a tarefa 001"
