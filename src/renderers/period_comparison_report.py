"""
Renderer do relatório HTML de comparação entre dois períodos de custo AWS.

Gera um único HTML autocontido (CSS/JS inline, Chart.js via CDN) com abas
"Por Serviço" e "Por Tipo de Uso", replicando o padrão visual já usado nos
demais relatórios HTML do projeto.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pandas as pd

import config


def _short_service_name(service: str) -> str:
    """Abrevia o nome de serviço da AWS para exibição compacta em gráficos/tabelas."""
    return config.PERIOD_COMPARISON_SERVICE_SHORT_NAMES.get(service, service)


def _aggregate_by_service(df: pd.DataFrame) -> dict[str, float]:
    """Soma custo total por Serviço (nome abreviado) dentro de um período."""
    if df.empty:
        return {}
    df = df.assign(Serviço=df["Serviço"].map(_short_service_name))
    return df.groupby("Serviço")["Custo($)"].sum().to_dict()


def _aggregate_by_usage_type(df: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Soma custo total por (UsageType, Serviço abreviado) dentro de um período."""
    if df.empty:
        return {}
    df = df.assign(Serviço=df["Serviço"].map(_short_service_name))
    grouped = df.groupby(["UsageType", "Serviço"])["Custo($)"].sum()
    return {key: value for key, value in grouped.items()}


def _aggregate_daily_total(df: pd.DataFrame, start_date: str, end_date: str) -> list[float]:
    """Série diária de custo total, com zero nos dias sem registro no Cost Explorer."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    days = (end - start).days + 1

    daily_totals = {}
    if not df.empty:
        daily_totals = df.groupby("Data")["Custo($)"].sum().to_dict()

    return [
        round(daily_totals.get((start + timedelta(days=i)).strftime("%Y-%m-%d"), 0.0), 2)
        for i in range(days)
    ]


def _build_services_rows(df_a: pd.DataFrame, df_b: pd.DataFrame) -> list[list]:
    totals_a = _aggregate_by_service(df_a)
    totals_b = _aggregate_by_service(df_b)
    services = sorted(set(totals_a) | set(totals_b))
    return [
        [service, round(totals_a.get(service, 0.0), 2), round(totals_b.get(service, 0.0), 2)]
        for service in services
    ]


def _build_usage_type_rows(df_a: pd.DataFrame, df_b: pd.DataFrame) -> list[list]:
    totals_a = _aggregate_by_usage_type(df_a)
    totals_b = _aggregate_by_usage_type(df_b)
    keys = sorted(set(totals_a) | set(totals_b))
    rows = []
    for usage_type, service in keys:
        amount_a = totals_a.get((usage_type, service), 0.0)
        amount_b = totals_b.get((usage_type, service), 0.0)
        rows.append([f"{usage_type} ({service})", round(amount_a, 2), round(amount_b, 2)])
    return rows


def write_period_comparison_html(
    output_dir: str,
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    account_label: str,
    region_label: str,
    period_a_label: str,
    period_b_label: str,
) -> str:
    """
    Monta e grava o HTML comparativo entre dois períodos de custo.
    Retorna o caminho do arquivo gerado.
    """
    total_a = round(float(df_a["Custo($)"].sum()) if not df_a.empty else 0.0, 2)
    total_b = round(float(df_b["Custo($)"].sum()) if not df_b.empty else 0.0, 2)
    delta_abs = round(total_b - total_a, 2)
    delta_pct = (delta_abs / total_a * 100) if total_a else 0.0

    services_rows = _build_services_rows(df_a, df_b)
    usage_rows = _build_usage_type_rows(df_a, df_b)

    daily_a = _aggregate_daily_total(df_a, period_a_start, period_a_end)
    daily_b = _aggregate_daily_total(df_b, period_b_start, period_b_end)
    daily_len = min(len(daily_a), len(daily_b))
    daily_labels = [f"Dia {i + 1}" for i in range(daily_len)]

    trend_class = "up" if delta_abs >= 0 else "down"
    delta_sign = "+" if delta_abs >= 0 else ""

    html = _TEMPLATE.format(
        title=f"AWS Cost — Comparativo {period_a_label} vs {period_b_label}",
        account_label=account_label,
        region_label=region_label,
        period_a_label=period_a_label,
        period_b_label=period_b_label,
        total_a=f"${total_a:,.2f}",
        total_b=f"${total_b:,.2f}",
        days_a=(datetime.strptime(period_a_end, "%Y-%m-%d") - datetime.strptime(period_a_start, "%Y-%m-%d")).days + 1,
        days_b=(datetime.strptime(period_b_end, "%Y-%m-%d") - datetime.strptime(period_b_start, "%Y-%m-%d")).days + 1,
        delta_abs_str=f"{delta_sign}${abs(delta_abs):,.2f}",
        delta_pct_str=f"{delta_sign}{delta_pct:.1f}%",
        trend_class=trend_class,
        total_b_raw=total_b,
        services_json=json.dumps(services_rows, ensure_ascii=False),
        usage_json=json.dumps(usage_rows, ensure_ascii=False),
        daily_labels_json=json.dumps(daily_labels, ensure_ascii=False),
        daily_a_json=json.dumps(daily_a[:daily_len], ensure_ascii=False),
        daily_b_json=json.dumps(daily_b[:daily_len], ensure_ascii=False),
        min_pct_chart_usd=100.0,
    )

    os.makedirs(output_dir, exist_ok=True)
    filename = f"comparativo_{period_a_end}_vs_{period_b_end}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath


_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f5f6f8;
    color: #1a1a2e;
    font-size: 14px;
    min-height: 100vh;
  }}

  header {{
    background: #fff;
    border-bottom: 1px solid #e2e4ea;
    padding: 20px 32px;
    display: flex;
    align-items: baseline;
    gap: 12px;
  }}
  header h1 {{ font-size: 17px; font-weight: 600; color: #1a1a2e; }}
  header span {{ font-size: 13px; color: #6b7280; }}

  .summary {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    padding: 20px 32px;
    background: #fff;
    border-bottom: 1px solid #e2e4ea;
  }}
  .kpi {{ display: flex; flex-direction: column; gap: 4px; }}
  .kpi-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #9ca3af; font-weight: 500; }}
  .kpi-value {{ font-size: 22px; font-weight: 600; color: #1a1a2e; }}
  .kpi-value.up {{ color: #dc2626; }}
  .kpi-value.down {{ color: #059669; }}
  .kpi-sub {{ font-size: 12px; color: #6b7280; }}

  .tabs-bar {{ display: flex; gap: 0; padding: 0 32px; background: #fff; border-bottom: 1px solid #e2e4ea; }}
  .tab-btn {{
    padding: 12px 20px; font-size: 13px; font-weight: 500; color: #6b7280;
    border: none; background: none; cursor: pointer; border-bottom: 2px solid transparent;
    transition: color .15s, border-color .15s;
  }}
  .tab-btn.active {{ color: #2563eb; border-bottom-color: #2563eb; }}
  .tab-btn:hover:not(.active) {{ color: #374151; }}

  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  .content {{ padding: 24px 32px; }}

  .chart-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .chart-card {{ background: #fff; border: 1px solid #e2e4ea; padding: 20px; }}
  .chart-title {{ font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: #9ca3af; margin-bottom: 16px; }}
  .chart-wrap {{ position: relative; width: 100%; }}

  .legend {{ display: flex; gap: 20px; margin-bottom: 12px; font-size: 12px; color: #6b7280; }}
  .legend span {{ display: flex; align-items: center; gap: 5px; }}
  .legend-dot {{ width: 10px; height: 10px; flex-shrink: 0; }}

  .table-card {{ background: #fff; border: 1px solid #e2e4ea; overflow: hidden; }}
  .table-header {{ display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid #e2e4ea; }}
  .table-title {{ font-size: 13px; font-weight: 600; color: #374151; }}
  .search-input {{
    padding: 6px 12px; border: 1px solid #e2e4ea; font-size: 12px; outline: none;
    width: 200px; color: #374151; background: #f9fafb;
  }}
  .search-input:focus {{ border-color: #2563eb; background: #fff; }}

  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{
    padding: 10px 16px; text-align: left; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .06em; color: #9ca3af; background: #f9fafb;
    border-bottom: 1px solid #e2e4ea; cursor: pointer; user-select: none; white-space: nowrap;
  }}
  thead th:hover {{ color: #374151; }}
  thead th.sorted-asc::after {{ content: ' ↑'; }}
  thead th.sorted-desc::after {{ content: ' ↓'; }}
  thead th.num {{ text-align: right; }}

  tbody tr {{ border-bottom: 1px solid #f0f1f5; transition: background .1s; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: #f9fafb; }}

  td {{ padding: 10px 16px; font-size: 13px; color: #374151; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; font-size: 12.5px; }}
  td.name {{ font-weight: 500; color: #1a1a2e; max-width: 260px; }}

  .pill {{ display: inline-flex; align-items: center; gap: 3px; font-size: 11.5px; font-weight: 600; padding: 2px 8px; }}
  .pill.up {{ background: #fef2f2; color: #dc2626; }}
  .pill.down {{ background: #f0fdf4; color: #059669; }}
  .pill.neutral {{ background: #f3f4f6; color: #6b7280; }}

  .bar-mini {{ display: flex; align-items: center; gap: 6px; }}
  .bar-mini-track {{ flex: 1; height: 4px; background: #e2e4ea; overflow: hidden; }}
  .bar-mini-fill {{ height: 100%; }}

  .no-results {{ text-align: center; padding: 40px; color: #9ca3af; font-size: 13px; }}

  .svc-tag {{
    font-size: 10px; font-weight: 500; color: #6b7280; background: #f3f4f6;
    padding: 1px 5px; margin-left: 5px; vertical-align: middle; white-space: nowrap;
  }}

  @media (max-width: 900px) {{
    .chart-row {{ grid-template-columns: 1fr; }}
    .summary {{ grid-template-columns: repeat(2, 1fr); }}
    header, .summary, .tabs-bar, .content {{ padding-left: 16px; padding-right: 16px; }}
  }}
</style>
</head>
<body>

<header>
  <h1>AWS Cost — Comparativo {period_a_label} vs {period_b_label}</h1>
  <span>Conta {account_label} · {region_label}</span>
</header>

<div class="summary">
  <div class="kpi">
    <span class="kpi-label">{period_a_label}</span>
    <span class="kpi-value">{total_a}</span>
    <span class="kpi-sub">{days_a} dias</span>
  </div>
  <div class="kpi">
    <span class="kpi-label">{period_b_label}</span>
    <span class="kpi-value">{total_b}</span>
    <span class="kpi-sub">{days_b} dias</span>
  </div>
  <div class="kpi">
    <span class="kpi-label">Variação absoluta</span>
    <span class="kpi-value {trend_class}">{delta_abs_str}</span>
    <span class="kpi-sub">vs período anterior</span>
  </div>
  <div class="kpi">
    <span class="kpi-label">Variação %</span>
    <span class="kpi-value {trend_class}">{delta_pct_str}</span>
  </div>
</div>

<div class="tabs-bar">
  <button class="tab-btn active" onclick="switchTab('services', this)">Por Serviço</button>
  <button class="tab-btn" onclick="switchTab('usage', this)">Por Tipo de Uso</button>
</div>

<div id="tab-services" class="tab-panel active">
  <div class="content">
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-title">Custo por serviço (top 10)</div>
        <div class="legend">
          <span><span class="legend-dot" style="background:#3b82f6;"></span>{period_a_label}</span>
          <span><span class="legend-dot" style="background:#10b981;"></span>{period_b_label}</span>
        </div>
        <div class="chart-wrap" style="height:300px;"><canvas id="svcBarChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Variação % por serviço — acima de ${min_pct_chart_usd:.0f}, ordem por impacto real (Δ$)</div>
        <div class="legend">
          <span><span class="legend-dot" style="background:#dc2626;"></span>Subiu</span>
          <span><span class="legend-dot" style="background:#059669;"></span>Caiu</span>
        </div>
        <div class="chart-wrap" style="height:300px;"><canvas id="svcPctChart"></canvas></div>
      </div>
    </div>

    <div class="chart-card" style="margin-bottom:24px;">
      <div class="chart-title">Custo diário — {period_a_label} vs {period_b_label}</div>
      <div class="legend">
        <span><span class="legend-dot" style="background:#3b82f6;"></span>{period_a_label}</span>
        <span><span class="legend-dot" style="background:#10b981;"></span>{period_b_label}</span>
      </div>
      <div class="chart-wrap" style="height:300px;"><canvas id="dailyLineChart"></canvas></div>
    </div>

    <div class="table-card">
      <div class="table-header">
        <span class="table-title">Todos os serviços</span>
        <input class="search-input" type="text" placeholder="Filtrar serviço..." oninput="filterTable('svc-tbody', this.value)">
      </div>
      <table>
        <thead>
          <tr>
            <th onclick="sortTable('svc-tbody',0,false)">Serviço</th>
            <th class="num" onclick="sortTable('svc-tbody',1,true)">{period_a_label}</th>
            <th class="num" onclick="sortTable('svc-tbody',2,true)">{period_b_label}</th>
            <th class="num" onclick="sortTable('svc-tbody',3,true)">Δ Absoluto</th>
            <th class="num" onclick="sortTable('svc-tbody',4,true)">Δ %</th>
            <th class="num">Share {period_b_label}</th>
          </tr>
        </thead>
        <tbody id="svc-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<div id="tab-usage" class="tab-panel">
  <div class="content">
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-title">Tipo de uso — top 10 por custo {period_b_label}</div>
        <div class="legend">
          <span><span class="legend-dot" style="background:#3b82f6;"></span>{period_a_label}</span>
          <span><span class="legend-dot" style="background:#10b981;"></span>{period_b_label}</span>
        </div>
        <div class="chart-wrap" style="height:300px;"><canvas id="usageBarChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Variação % por tipo de uso — acima de ${min_pct_chart_usd:.0f}, ordem por impacto real (Δ$)</div>
        <div class="legend">
          <span><span class="legend-dot" style="background:#dc2626;"></span>Subiu</span>
          <span><span class="legend-dot" style="background:#059669;"></span>Caiu</span>
        </div>
        <div class="chart-wrap" style="height:300px;"><canvas id="usageDeltaChart"></canvas></div>
      </div>
    </div>

    <div class="chart-card" style="margin-bottom:24px;">
      <div class="chart-title">Custo diário — {period_a_label} vs {period_b_label}</div>
      <div class="legend">
        <span><span class="legend-dot" style="background:#3b82f6;"></span>{period_a_label}</span>
        <span><span class="legend-dot" style="background:#10b981;"></span>{period_b_label}</span>
      </div>
      <div class="chart-wrap" style="height:300px;"><canvas id="dailyLineChartUsage"></canvas></div>
    </div>

    <div class="table-card">
      <div class="table-header">
        <span class="table-title">Todos os tipos de uso</span>
        <input class="search-input" type="text" placeholder="Filtrar tipo de uso..." oninput="filterTable('usage-tbody', this.value)">
      </div>
      <table>
        <thead>
          <tr>
            <th onclick="sortTable('usage-tbody',0,false)">Tipo de uso</th>
            <th class="num" onclick="sortTable('usage-tbody',1,true)">{period_a_label}</th>
            <th class="num" onclick="sortTable('usage-tbody',2,true)">{period_b_label}</th>
            <th class="num" onclick="sortTable('usage-tbody',3,true)">Δ Absoluto</th>
            <th class="num" onclick="sortTable('usage-tbody',4,true)">Δ %</th>
            <th class="num">Share {period_b_label}</th>
          </tr>
        </thead>
        <tbody id="usage-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const fmt = v => '$' + Math.abs(v).toLocaleString('en-US', {{minimumFractionDigits:2, maximumFractionDigits:2}});
const fmtPct = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
const TOTAL_B = {total_b_raw};
const MIN_PCT_CHART_USD = {min_pct_chart_usd};
const LABEL_A = "{period_a_label}";
const LABEL_B = "{period_b_label}";

Chart.defaults.elements.bar.borderRadius = 0;
Chart.defaults.elements.bar.borderSkipped = 'start';

const servicesData = {services_json};
const usageData = {usage_json};

function enrich(data) {{
  return data.map(([name, a, b]) => {{
    const delta = b - a;
    const pct = a === 0 ? null : ((b - a) / a) * 100;
    return {{ name, a, b, delta, pct }};
  }});
}}

function renderTable(tbodyId, rows) {{
  const isUsage = tbodyId === 'usage-tbody';
  const tbody = document.getElementById(tbodyId);
  const maxB = Math.max(...rows.map(r => r.b), 1);
  tbody.innerHTML = rows.map(r => {{
    const pctVal = r.pct;
    const pillClass = pctVal === null ? 'neutral' : (pctVal > 0.5 ? 'up' : pctVal < -0.5 ? 'down' : 'neutral');
    const pillTxt = pctVal === null ? '—' : fmtPct(pctVal);
    const deltaStr = r.delta >= 0 ? '+' + fmt(r.delta) : '-' + fmt(r.delta);
    const deltaColor = r.delta > 0.5 ? '#dc2626' : r.delta < -0.5 ? '#059669' : '#6b7280';
    const share = ((r.b / TOTAL_B) * 100).toFixed(1);
    const barPct = Math.round((r.b / maxB) * 100);

    let displayName = r.name;
    if (isUsage) {{
      displayName = r.name.replace(/\\(([^)]+)\\)$/, (_, svc) => `<span class="svc-tag">${{svc}}</span>`);
    }}

    return `<tr data-name="${{r.name.toLowerCase()}}">
      <td class="name">${{displayName}}</td>
      <td class="num">${{fmt(r.a)}}</td>
      <td class="num">${{fmt(r.b)}}</td>
      <td class="num" style="color:${{deltaColor}}; font-weight:600;">${{deltaStr}}</td>
      <td class="num"><span class="pill ${{pillClass}}">${{pillTxt}}</span></td>
      <td class="num">
        <div class="bar-mini">
          <div class="bar-mini-track"><div class="bar-mini-fill" style="width:${{barPct}}%; background:#3b82f6;"></div></div>
          <span style="min-width:36px; font-size:11px; color:#6b7280;">${{share}}%</span>
        </div>
      </td>
    </tr>`;
  }}).join('');
}}

const svcRows = enrich(servicesData);
const usageRows = enrich(usageData);
renderTable('svc-tbody', svcRows);
renderTable('usage-tbody', usageRows);

function filterTable(tbodyId, query) {{
  const q = query.toLowerCase();
  const rows = document.querySelectorAll(`#${{tbodyId}} tr`);
  let found = 0;
  rows.forEach(tr => {{
    if (tr.id === 'no-results') {{ tr.remove(); return; }}
    const show = tr.dataset.name.includes(q);
    tr.style.display = show ? '' : 'none';
    if (show) found++;
  }});
  const existing = document.getElementById('no-results');
  if (existing) existing.remove();
  if (found === 0) {{
    const tbody = document.getElementById(tbodyId);
    const tr = document.createElement('tr');
    tr.id = 'no-results';
    tr.innerHTML = '<td colspan="6" class="no-results">Nenhum resultado encontrado.</td>';
    tbody.appendChild(tr);
  }}
}}

let sortState = {{}};
function sortTable(tbodyId, colIdx, isNum) {{
  const key = tbodyId + '-' + colIdx;
  const asc = sortState[key] !== true;
  sortState[key] = asc;

  const tbody = document.getElementById(tbodyId);
  const rows = Array.from(tbody.querySelectorAll('tr[data-name]'));
  rows.sort((a, b) => {{
    const aVal = a.cells[colIdx].textContent.replace(/[$+,\\-%]/g,'').trim();
    const bVal = b.cells[colIdx].textContent.replace(/[$+,\\-%]/g,'').trim();
    if (isNum) return asc ? parseFloat(aVal) - parseFloat(bVal) : parseFloat(bVal) - parseFloat(aVal);
    return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  }});
  rows.forEach(r => tbody.appendChild(r));

  document.querySelectorAll('thead th').forEach(th => th.classList.remove('sorted-asc','sorted-desc'));
  const ths = tbody.closest('table').querySelectorAll('thead th');
  ths[colIdx].classList.add(asc ? 'sorted-asc' : 'sorted-desc');
}}

function makeBarChart(id, labels, a, b) {{
  new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels, datasets: [
      {{ label: LABEL_A, data: a, backgroundColor: '#3b82f6' }},
      {{ label: LABEL_B, data: b, backgroundColor: '#10b981' }}
    ] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.dataset.label + ': $' + ctx.parsed.y.toLocaleString('en-US',{{minimumFractionDigits:0,maximumFractionDigits:0}}) }} }} }},
      scales: {{
        x: {{ ticks: {{ font:{{size:10}}, maxRotation:35, autoSkip:false }}, grid:{{display:false}} }},
        y: {{ ticks: {{ callback: v => '$'+(v/1000).toFixed(0)+'k', font:{{size:10}} }}, grid:{{color:'#f0f1f5'}} }}
      }}
    }}
  }});
}}

function makePctChart(id, rows) {{
  const filtered = rows
    .filter(r => r.b >= MIN_PCT_CHART_USD && r.pct !== null && Math.abs(r.delta) >= 1)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 12);

  const labels = filtered.map(r => r.name);
  const pcts   = filtered.map(r => Math.round(r.pct * 10) / 10);
  const deltas = filtered.map(r => r.delta);
  const colors = pcts.map(v => v > 0 ? '#dc2626' : '#059669');

  new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ data: pcts, backgroundColor: colors }}] }},
    options: {{
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => {{
          const pct = (ctx.parsed.x >= 0 ? '+' : '') + ctx.parsed.x.toFixed(1) + '%';
          const dlt = deltas[ctx.dataIndex];
          const sign = dlt >= 0 ? '+' : '-';
          return ' ' + pct + '  (' + sign + '$' + Math.abs(dlt).toFixed(0) + ')';
        }} }} }} }},
      scales: {{
        x: {{ ticks: {{ callback: v => (v>=0?'+':'')+v.toFixed(0)+'%', font:{{size:10}} }}, grid:{{color:'#f0f1f5'}} }},
        y: {{ ticks: {{ font:{{size:10}} }}, grid:{{display:false}} }}
      }}
    }}
  }});
}}

const svcTop10 = [...svcRows].sort((a,b)=>b.b-a.b).slice(0,10);
makeBarChart('svcBarChart', svcTop10.map(r=>r.name), svcTop10.map(r=>r.a), svcTop10.map(r=>r.b));
makePctChart('svcPctChart', svcRows);

const usageTop10 = [...usageRows].sort((a,b)=>b.b-a.b).slice(0,10);
makeBarChart('usageBarChart', usageTop10.map(r=>r.name), usageTop10.map(r=>r.a), usageTop10.map(r=>r.b));
makePctChart('usageDeltaChart', usageRows);

const dailyLabels = {daily_labels_json};
const dailyA = {daily_a_json};
const dailyB = {daily_b_json};

function makeDailyLineChart(id) {{
  new Chart(document.getElementById(id), {{
    type: 'line',
    data: {{
      labels: dailyLabels,
      datasets: [
        {{ label: LABEL_A, data: dailyA, borderColor: '#3b82f6', backgroundColor: '#3b82f6', pointRadius: 3, borderWidth: 2, tension: 0.25, fill: false }},
        {{ label: LABEL_B, data: dailyB, borderColor: '#10b981', backgroundColor: '#10b981', pointRadius: 3.5, borderWidth: 2, tension: 0.25, fill: false, borderDash: [6,3] }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{ legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.dataset.label + ': $' + ctx.parsed.y.toLocaleString('en-US',{{minimumFractionDigits:0,maximumFractionDigits:0}}) }} }} }},
      scales: {{
        x: {{ ticks: {{ font:{{size:10}}, maxRotation:0 }}, grid:{{display:false}} }},
        y: {{ beginAtZero: true, ticks: {{ callback: v => '$'+(v/1000).toFixed(1)+'k', font:{{size:10}} }}, grid:{{color:'#f0f1f5'}} }}
      }}
    }}
  }});
}}
makeDailyLineChart('dailyLineChart');
makeDailyLineChart('dailyLineChartUsage');

function switchTab(name, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>
"""
