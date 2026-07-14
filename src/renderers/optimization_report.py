"""
Renderer for the optimization report: HTML (4 tabs), TXT executive summary, and 3 CSV files.
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# ============================================================
# Helpers
# ============================================================

def _fmt_usd(value: float) -> str:
    return f"US$ {value:,.2f}"


def _fmt_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _behavior_badge(behavior: str) -> str:
    colors = {
        "Crescendo": ("badge-red", "↑ Crescendo"),
        "Caindo": ("badge-green", "↓ Caindo"),
        "Volátil": ("badge-yellow", "⚡ Volátil"),
        "Estável": ("badge-gray", "→ Estável"),
    }
    cls, label = colors.get(behavior, ("badge-gray", behavior))
    return f'<span class="badge {cls}">{label}</span>'


def _priority_badge(priority: str) -> str:
    colors = {
        "Alta": ("badge-red", "Alta"),
        "Média": ("badge-yellow", "Média"),
        "Baixa": ("badge-gray", "Baixa"),
    }
    cls, label = colors.get(priority, ("badge-gray", priority))
    return f'<span class="badge {cls}">{label}</span>'


def _tooltip(text: str, tip: str) -> str:
    """Ícone ⓘ com tooltip explicativo para termos técnicos."""
    escaped_tip = html.escape(tip, quote=True)
    return (
        f'{html.escape(text)}'
        f'<span class="ic inline-ic">i'
        f'<span class="tip">{escaped_tip}</span>'
        f'</span>'
    )


def _render_analysis_html(analysis_text: Optional[str]) -> str:
    """
    Converte texto livre da análise em HTML sem expor origem.

    Reconhece dois blocos separados pelo marcador 'BLOCO 2' (ou 'Serviços para investigação'):
    - Bloco 1: oportunidades com evidência determinística — cards azuis/verdes
    - Bloco 2: serviços para investigação — cards amarelos com label distinto
    """
    if not analysis_text or not analysis_text.strip():
        return (
            '<div class="analysis-shell">'
            '<div class="section-card empty-state">'
            '<p>Análise não disponível para esta execução.</p>'
            '<p class="hint">Execute com análise habilitada para preencher esta aba.</p>'
            '</div></div>'
        )

    # Separa o texto em dois blocos pelo marcador do Bloco 2
    bloco2_markers = ["BLOCO 2", "Serviços para investigação", "Serviços para investigacao"]
    split_idx = None
    for marker in bloco2_markers:
        idx = analysis_text.find(marker)
        if idx != -1:
            split_idx = idx
            break

    if split_idx is not None:
        text_bloco1 = analysis_text[:split_idx].strip()
        text_bloco2 = analysis_text[split_idx:].strip()
    else:
        text_bloco1 = analysis_text.strip()
        text_bloco2 = ""

    def _parse_blocks(text: str) -> list[tuple[str, list[str]]]:
        """Parseia texto em lista de (título, itens)."""
        lines = text.splitlines()
        blocks: list[tuple[str, list[str]]] = []
        current_title = ""
        current_items: list[str] = []

        def flush():
            if current_title or current_items:
                blocks.append((current_title, list(current_items)))

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("##") or (stripped.endswith(":") and len(stripped) < 80 and not stripped.startswith("-")):
                flush()
                current_title = stripped.lstrip("#").rstrip(":").strip()
                current_items = []
            elif stripped.startswith("-"):
                current_items.append(stripped.lstrip("- ").strip())
            else:
                if current_items or current_title:
                    current_items.append(stripped)
                else:
                    current_title = stripped
        flush()
        return blocks

    def _render_item(item: str) -> str:
        escaped = html.escape(item)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        return escaped

    parts = ['<div class="analysis-shell">']

    # --- Bloco 1: oportunidades determinísticas
    blocks1 = _parse_blocks(text_bloco1)
    for title, items in blocks1:
        if title:
            parts.append(f'<div class="section-card"><h3>{html.escape(title)}</h3>')
        else:
            parts.append('<div class="section-card">')
        if items:
            parts.append('<ul class="analysis-list">')
            for item in items:
                parts.append(f"<li>{_render_item(item)}</li>")
            parts.append("</ul>")
        parts.append("</div>")

    # --- Bloco 2: serviços para investigação (visual distinto)
    if text_bloco2:
        blocks2 = _parse_blocks(text_bloco2)
        parts.append(
            '<div class="investigation-section">'
            '<div class="investigation-header">'
            '<span class="investigation-badge">Investigação</span>'
            '<h3>Serviços sem regra mapeada — direção de investigação</h3>'
            '<p class="investigation-hint">Estes serviços estão crescendo mas não possuem evidência direta de desperdício. '
            'As sugestões abaixo indicam o que verificar — não são oportunidades confirmadas.</p>'
            '</div>'
        )
        for title, items in blocks2:
            # Pula o próprio título do bloco (já renderizado no header acima)
            bloco2_title_markers = ["BLOCO 2", "Serviços para investigação", "Serviços para investigacao"]
            if any(m.lower() in title.lower() for m in bloco2_title_markers):
                continue
            if title:
                parts.append(f'<div class="section-card investigation-card"><h4>{html.escape(title)}</h4>')
            else:
                parts.append('<div class="section-card investigation-card">')
            if items:
                parts.append('<ul class="analysis-list">')
                for item in items:
                    parts.append(f"<li>{_render_item(item)}</li>")
                parts.append("</ul>")
            parts.append("</div>")
        parts.append("</div>")  # fecha investigation-section

    parts.append("</div>")  # fecha analysis-shell
    return "\n".join(parts)


# ============================================================
# CSS
# ============================================================

def _css() -> str:
    return """
    :root {
        --red: #ef4444; --red-light: #fef2f2;
        --green: #22c55e; --green-light: #f0fdf4;
        --yellow: #f59e0b; --yellow-light: #fffbeb;
        --blue: #3b82f6; --blue-light: #eff6ff;
        --gray: #6b7280; --gray-light: #f9fafb;
        --border: #e5e7eb; --text: #111827; --text-muted: #6b7280;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: var(--gray-light); color: var(--text); font-size: 14px; }
    .header { background: #1e293b; color: white; padding: 20px 32px; }
    .header h1 { font-size: 1.4rem; font-weight: 700; }
    .header .subtitle { color: #94a3b8; font-size: 0.85rem; margin-top: 4px; }
    .tabs { display: flex; gap: 2px; background: #f1f5f9; padding: 8px 32px 0;
            border-bottom: 1px solid var(--border); }
    .tab { padding: 10px 20px; cursor: pointer; border-radius: 6px 6px 0 0;
           font-size: 0.85rem; font-weight: 500; color: var(--text-muted);
           background: transparent; border: none; }
    .tab.active { background: white; color: var(--text); border: 1px solid var(--border);
                  border-bottom: none; }
    .tab-content { display: none; padding: 24px 32px; }
    .tab-content.active { display: block; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 16px; margin-bottom: 24px; }
    .kpi-card { background: white; border: 1px solid var(--border); border-radius: 10px;
                padding: 16px; }
    .kpi-card .label { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; }
    .kpi-card .value { font-size: 1.4rem; font-weight: 700; }
    .kpi-card .sub { font-size: 0.75rem; color: var(--text-muted); margin-top: 4px; }
    .kpi-card.highlight { border-left: 4px solid var(--blue); }
    .kpi-card.warn { border-left: 4px solid var(--yellow); }
    .kpi-card.danger { border-left: 4px solid var(--red); }
    .kpi-card.good { border-left: 4px solid var(--green); }
    .section-card { background: white; border: 1px solid var(--border); border-radius: 10px;
                    padding: 20px; margin-bottom: 20px; }
    .section-card h2 { font-size: 1rem; font-weight: 600; margin-bottom: 16px; }
    .section-card h3 { font-size: 0.95rem; font-weight: 600; margin-bottom: 12px; color: #374151; }
    .chart-container { position: relative; height: 300px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th { background: #f8fafc; padding: 10px 12px; text-align: left; font-weight: 600;
         border-bottom: 2px solid var(--border); white-space: nowrap; cursor: pointer; }
    th:hover { background: #f1f5f9; }
    td { padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #f8fafc; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
             font-size: 0.75rem; font-weight: 600; }
    .badge-red { background: var(--red-light); color: var(--red); }
    .badge-green { background: var(--green-light); color: #15803d; }
    .badge-yellow { background: var(--yellow-light); color: #92400e; }
    .badge-gray { background: #f3f4f6; color: var(--gray); }
    .badge-blue { background: var(--blue-light); color: #1d4ed8; }
    .export-btn { display: inline-block; margin-bottom: 12px; padding: 7px 14px;
                  background: #f1f5f9; border: 1px solid var(--border); border-radius: 6px;
                  font-size: 0.8rem; cursor: pointer; color: var(--text); }
    .export-btn:hover { background: #e2e8f0; }
    .search-box { width: 100%; padding: 8px 12px; border: 1px solid var(--border);
                  border-radius: 6px; font-size: 0.85rem; margin-bottom: 12px; }
    .detail-cell { max-width: 380px; }
    .detail-preview { color: var(--text); }
    .detail-full { color: var(--text); white-space: pre-wrap; line-height: 1.6; }
    .expand-btn { display: inline; background: none; border: none; padding: 0 4px;
                  color: var(--blue); font-size: 0.78rem; cursor: pointer;
                  font-weight: 600; white-space: nowrap; }
    .expand-btn:hover { text-decoration: underline; }
    .ic { position: relative; display: inline-flex; align-items: center; justify-content: center;
          width: 16px; height: 16px; border-radius: 50%; background: #e2e8f0;
          color: var(--gray); font-size: 0.65rem; font-style: normal; font-weight: 700;
          cursor: help; vertical-align: middle; }
    .inline-ic { margin-left: 4px; }
    .ic .tip { display: none; position: absolute; bottom: 120%; left: 50%; transform: translateX(-50%);
               background: #1e293b; color: white; padding: 8px 12px; border-radius: 6px;
               font-size: 0.78rem; width: 260px; z-index: 99; line-height: 1.4; white-space: normal; }
    .ic:hover .tip { display: block; }
    .scatter-container { position: relative; height: 340px; }
    .analysis-shell { }
    .analysis-list { padding-left: 20px; }
    .analysis-list li { margin-bottom: 8px; line-height: 1.5; }
    .empty-state { text-align: center; padding: 40px; color: var(--text-muted); }
    .empty-state .hint { font-size: 0.8rem; margin-top: 8px; }
    .investigation-section { margin-top: 32px; border-top: 2px dashed #f59e0b; padding-top: 20px; }
    .investigation-header { margin-bottom: 16px; }
    .investigation-badge { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d;
        font-size: 0.7rem; font-weight: 700; padding: 2px 10px; border-radius: 12px;
        text-transform: uppercase; letter-spacing: 0.05em; }
    .investigation-header h3 { margin-top: 8px; font-size: 0.95rem; color: #92400e; }
    .investigation-hint { font-size: 0.8rem; color: var(--text-muted); margin-top: 4px; line-height: 1.4; }
    .investigation-card { border-left: 4px solid #f59e0b; background: #fffbeb; }
    .investigation-card h4 { font-size: 0.9rem; font-weight: 600; color: #78350f; margin-bottom: 10px; }
    .mom-positive { color: var(--red); font-weight: 600; }
    .mom-negative { color: #15803d; font-weight: 600; }
    .trend-positive { color: var(--red); }
    .trend-negative { color: #15803d; }
    .opportunities-summary { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
    .opp-pill { padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }
    """


# ============================================================
# JavaScript helpers
# ============================================================

def _js_export_csv(table_id: str, filename: str) -> str:
    """Gera função JS para exportar tabela HTML como CSV client-side."""
    return f"""
    function exportCSV_{table_id}() {{
        const table = document.getElementById('{table_id}');
        const rows = [];
        for (const row of table.querySelectorAll('tr')) {{
            const cols = [];
            for (const cell of row.querySelectorAll('th, td')) {{
                let text = cell.innerText.replace(/[\\n\\r]+/g, ' ').trim();
                text = text.replace(/"/g, '""');
                cols.push('"' + text + '"');
            }}
            rows.push(cols.join(','));
        }}
        const blob = new Blob([rows.join('\\n')], {{type: 'text/csv;charset=utf-8;'}});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '{filename}';
        a.click();
    }}
    """


def _js_sort_table(table_id: str) -> str:
    """Sort de tabela ao clicar no cabeçalho."""
    return f"""
    (function() {{
        const tbl = document.getElementById('{table_id}');
        if (!tbl) return;
        const ths = tbl.querySelectorAll('th');
        let lastCol = -1, asc = true;
        ths.forEach((th, col) => {{
            th.addEventListener('click', () => {{
                asc = (lastCol === col) ? !asc : true;
                lastCol = col;
                const rows = Array.from(tbl.querySelectorAll('tbody tr'));
                rows.sort((a, b) => {{
                    const av = a.cells[col]?.innerText.replace(/[^\\d.-]/g,'') || '';
                    const bv = b.cells[col]?.innerText.replace(/[^\\d.-]/g,'') || '';
                    const an = parseFloat(av), bn = parseFloat(bv);
                    if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
                    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
                }});
                const tbody = tbl.querySelector('tbody');
                rows.forEach(r => tbody.appendChild(r));
            }});
        }});
    }})();
    """


def _js_search_table(input_id: str, table_id: str) -> str:
    """Filtro de busca em tempo real."""
    return f"""
    document.getElementById('{input_id}').addEventListener('input', function() {{
        const q = this.value.toLowerCase();
        document.querySelectorAll('#{table_id} tbody tr').forEach(row => {{
            row.style.display = row.innerText.toLowerCase().includes(q) ? '' : 'none';
        }});
    }});
    """


# ============================================================
# Tab 1 — Visão Executiva
# ============================================================

def _tab_executive(unit_economics: dict, df_service_trends: pd.DataFrame, opportunities: list[dict]) -> str:
    ue = unit_economics
    daily_avg = ue.get("daily_avg_usd", 0.0)
    monthly_avgs = ue.get("monthly_avg_usd", [0.0, 0.0, 0.0])
    projected_annual = ue.get("projected_annual_usd", 0.0)
    trend = ue.get("trend_usd_per_day", 0.0)
    mom_growth = ue.get("cost_growth_pct_mom", [])
    daily_series = ue.get("daily_series", [])

    total_savings = sum(o["economia_estimada_usd_mes"] for o in opportunities)
    high_count = sum(1 for o in opportunities if o["prioridade"] == "Alta")
    medium_count = sum(1 for o in opportunities if o["prioridade"] == "Média")
    low_count = sum(1 for o in opportunities if o["prioridade"] == "Baixa")

    trend_class = "trend-positive" if trend > 0 else "trend-negative"
    trend_sign = "+" if trend > 0 else ""

    # KPI cards
    kpi_html = f"""
    <div class="kpi-grid">
        <div class="kpi-card highlight">
            <div class="label">Custo médio / dia</div>
            <div class="value">{_fmt_usd(daily_avg)}</div>
            <div class="sub">Média dos {len(daily_series)} dias do período</div>
        </div>
        <div class="kpi-card {'danger' if trend > 0 else 'good'}">
            <div class="label">{_tooltip('Tendência (US$/dia)', 'Variação média de custo por dia no período calculada por regressão linear. Positivo = custo crescendo; negativo = custo caindo.')}</div>
            <div class="value {trend_class}">{trend_sign}{trend:.4f}</div>
            <div class="sub">{'Custo crescendo ao longo do período' if trend > 0 else 'Custo reduzindo ao longo do período'}</div>
        </div>
        <div class="kpi-card warn">
            <div class="label">Projeção anual (últimos 30d)</div>
            <div class="value">{_fmt_usd(projected_annual)}</div>
            <div class="sub">Baseada na média dos últimos 30 dias × 365</div>
        </div>
        <div class="kpi-card {'danger' if total_savings > 0 else 'gray'}">
            <div class="label">Economia potencial identificada</div>
            <div class="value">{_fmt_usd(total_savings)}/mês</div>
            <div class="sub">{high_count} Alta · {medium_count} Média · {low_count} Baixa prioridade</div>
        </div>
    </div>
    """

    # Tabela evolução mensal
    monthly_rows = ""
    labels_m = ["Mês 1", "Mês 2", "Mês 3"]
    for i, avg in enumerate(monthly_avgs):
        mom_str = ""
        if i > 0 and len(mom_growth) >= i:
            g = mom_growth[i - 1]
            cls = "mom-positive" if g > 0 else "mom-negative"
            sign = "+" if g > 0 else ""
            mom_str = f'<span class="{cls}">{sign}{g:.1f}%</span>'
        monthly_rows += f"<tr><td>{labels_m[i]}</td><td>{_fmt_usd(avg)}/dia</td><td>{mom_str or '—'}</td></tr>"

    monthly_table = f"""
    <div class="section-card">
        <h2>Evolução mensal de custo médio/dia</h2>
        <table id="tbl_monthly">
            <thead><tr><th>Período</th><th>Custo médio/dia</th><th>Variação MoM</th></tr></thead>
            <tbody>{monthly_rows}</tbody>
        </table>
    </div>
    """

    # Gráfico de custo diário — Chart.js
    chart_labels = json.dumps([d["date"] for d in daily_series])
    chart_values = json.dumps([d["cost_usd"] for d in daily_series])

    # Média móvel 7 dias para suavização visual
    vals = [d["cost_usd"] for d in daily_series]
    ma7 = []
    for i in range(len(vals)):
        window = vals[max(0, i - 6): i + 1]
        ma7.append(round(sum(window) / len(window), 4))
    chart_ma7 = json.dumps(ma7)

    chart_html = f"""
    <div class="section-card">
        <h2>Custo diário total — {len(daily_series)} dias</h2>
        <div class="chart-container">
            <canvas id="chartDaily"></canvas>
        </div>
    </div>
    <script>
    (function() {{
        const ctx = document.getElementById('chartDaily').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {chart_labels},
                datasets: [
                    {{
                        label: 'Custo diário (US$)',
                        data: {chart_values},
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.07)',
                        borderWidth: 1.5,
                        pointRadius: 2,
                        tension: 0.3,
                        fill: true,
                    }},
                    {{
                        label: 'Média móvel 7d',
                        data: {chart_ma7},
                        borderColor: '#f59e0b',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.4,
                        borderDash: [5, 3],
                    }}
                ]
            }},
            options: {{
                responsive: true, maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'top' }},
                    tooltip: {{ callbacks: {{ label: ctx => 'US$ ' + ctx.parsed.y.toFixed(2) }} }}
                }},
                scales: {{
                    x: {{ ticks: {{ maxTicksLimit: 20, maxRotation: 45 }} }},
                    y: {{ ticks: {{ callback: v => 'US$ ' + v.toFixed(0) }} }}
                }}
            }}
        }});
    }})();
    </script>
    """

    # Resumo de oportunidades por categoria
    cat_counts: dict[str, int] = {}
    for o in opportunities:
        cat_counts[o["categoria"]] = cat_counts.get(o["categoria"], 0) + 1
    pills_html = '<div class="opportunities-summary">'
    cat_labels = {
        "rightsizing": "Rightsizing",
        "lifecycle_s3": "S3 Lifecycle",
        "log_retention": "Log Retention",
        "vpc_endpoints": "VPC Endpoints",
        "savings_plans": "Savings Plans",
        "backup_retention": "Backup/Snapshots",
        "idle_cleanup": "Recursos ociosos",
        "newer_generation": "Nova geração",
        "autoscaling": "Auto Scaling",
        "data_compression": "Compressão",
        "quota_controls": "Quotas",
    }
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        label = cat_labels.get(cat, cat)
        pills_html += f'<span class="opp-pill badge-blue">{label}: {cnt}</span>'
    pills_html += "</div>"

    return kpi_html + chart_html + monthly_table + f'<div class="section-card"><h2>Oportunidades por categoria</h2>{pills_html}</div>'


# ============================================================
# Tab 2 — Diagnóstico por Serviço
# ============================================================

def _tab_services(df_service_trends: pd.DataFrame, opportunities: list[dict]) -> str:
    if df_service_trends.empty:
        return '<div class="section-card empty-state"><p>Nenhum serviço encontrado com custo mínimo configurado.</p></div>'

    # Mapa de oportunidades por serviço
    opp_by_svc: dict[str, int] = {}
    for o in opportunities:
        opp_by_svc[o["servico"]] = opp_by_svc.get(o["servico"], 0) + 1

    rows_html = ""
    for _, row in df_service_trends.iterrows():
        svc = row["Serviço"]
        trend = row["Tendência (US$/dia)"]
        trend_class = "trend-positive" if trend > 0 else "trend-negative"
        trend_str = f'<span class="{trend_class}">{"+" if trend > 0 else ""}{trend:.4f}</span>'
        mom2 = row["Var MoM M2 (%)"]
        mom3 = row["Var MoM M3 (%)"]
        mom2_str = f'<span class="{"mom-positive" if mom2 > 0 else "mom-negative"}">{"+" if mom2 > 0 else ""}{mom2:.1f}%</span>'
        mom3_str = f'<span class="{"mom-positive" if mom3 > 0 else "mom-negative"}">{"+" if mom3 > 0 else ""}{mom3:.1f}%</span>'
        opp_count = opp_by_svc.get(svc, 0)
        opp_badge = f'<span class="badge badge-blue">{opp_count}</span>' if opp_count > 0 else "—"
        top_ut = html.escape(str(row["Top UsageType"]))

        rows_html += f"""<tr>
            <td><strong>{html.escape(svc)}</strong></td>
            <td>{_fmt_usd(row['Total 3M (US$)'])}</td>
            <td>{_fmt_usd(row['Média diária (US$)'])}</td>
            <td>{_behavior_badge(row['Comportamento'])}</td>
            <td>{_tooltip('Tendência (US$/dia)', 'Variação média de custo por dia calculada por regressão linear. Positivo = custo crescendo; negativo = cuindo.')} {trend_str}</td>
            <td>{mom2_str}</td>
            <td>{mom3_str}</td>
            <td title="{top_ut}">{top_ut[:50]}{'…' if len(top_ut) > 50 else ''}</td>
            <td>{opp_badge}</td>
        </tr>"""

    return f"""
    <div class="section-card">
        <h2>Diagnóstico por serviço — todos os serviços com custo relevante</h2>
        <input class="search-box" id="svc_search" placeholder="Filtrar por serviço, comportamento, usage type...">
        <button class="export-btn" onclick="exportCSV_tbl_services()">⬇ Exportar CSV</button>
        <table id="tbl_services">
            <thead><tr>
                <th>Serviço</th>
                <th>Total 3M</th>
                <th>Média/dia</th>
                <th>Comportamento</th>
                <th>{_tooltip('Tendência', 'Variação média de custo por dia calculada por regressão linear sobre todo o período. Positivo = custo crescendo; negativo = custo caindo.')}</th>
                <th>{_tooltip('Var MoM M2', 'Month-over-Month: variação percentual do custo médio/dia entre o 1º e o 2º mês do período. Positivo = custo subiu; negativo = custo caiu.')}</th>
                <th>{_tooltip('Var MoM M3', 'Month-over-Month: variação percentual do custo médio/dia entre o 2º e o 3º mês do período. Positivo = custo subiu; negativo = custo caiu.')}</th>
                <th>Top UsageType</th>
                <th>Oport.</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """


# ============================================================
# Tab 3 — Oportunidades Ranqueadas
# ============================================================

def _tab_opportunities(opportunities: list[dict]) -> str:
    if not opportunities:
        return '<div class="section-card empty-state"><p>Nenhuma oportunidade identificada para os critérios configurados.</p></div>'

    # Scatter plot: impacto × esforço
    scatter_data = json.dumps([
        {
            "x": o["esforco_score"],
            "y": o["impacto_score"],
            "label": f"{o['servico']} — {o['acao'][:40]}",
            "prioridade": o["prioridade"],
            "economia": o["economia_estimada_usd_mes"],
        }
        for o in opportunities
    ])

    color_map = {"Alta": "#ef4444", "Média": "#f59e0b", "Baixa": "#6b7280"}
    scatter_colors = json.dumps([color_map.get(o["prioridade"], "#6b7280") for o in opportunities])

    scatter_html = f"""
    <div class="section-card">
        <h2>Matriz impacto × facilidade
            <span class="ic inline-ic">i<span class="tip">
                Eixo X = facilidade de implementação (10 = mais fácil).<br>
                Eixo Y = impacto estimado (US$ de economia / mês normalizado).<br>
                Quadrante superior direito = fácil e de alto impacto — priorize aqui.
            </span></span>
        </h2>
        <div class="scatter-container">
            <canvas id="chartScatter"></canvas>
        </div>
    </div>
    <script>
    (function() {{
        const raw = {scatter_data};
        const colors = {scatter_colors};
        const ctx = document.getElementById('chartScatter').getContext('2d');
        new Chart(ctx, {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    data: raw,
                    backgroundColor: colors,
                    pointRadius: 8,
                    pointHoverRadius: 10,
                }}]
            }},
            options: {{
                responsive: true, maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{ callbacks: {{
                        label: ctx => [
                            ctx.raw.label,
                            'Economia: US$ ' + ctx.raw.economia.toFixed(2) + '/mês',
                            'Prioridade: ' + ctx.raw.prioridade,
                        ]
                    }} }}
                }},
                scales: {{
                    x: {{ min: 0, max: 11, title: {{ display: true, text: 'Facilidade (1=difícil, 10=fácil)' }} }},
                    y: {{ min: 0, title: {{ display: true, text: 'Impacto estimado (score)' }} }},
                }}
            }}
        }});
    }})();
    </script>
    """

    # Tabela de oportunidades com detalhe expansível inline
    # Cada linha tem um resumo (120 chars) e uma linha oculta com o detalhe completo.
    _DETAIL_PREVIEW_LEN = 120
    rows_html = ""
    for idx, o in enumerate(opportunities):
        detalhe_full = o.get("detalhe", "") or ""
        detalhe_esc = html.escape(detalhe_full)
        row_id = f"opp_detail_{idx}"

        if len(detalhe_full) > _DETAIL_PREVIEW_LEN:
            preview = html.escape(detalhe_full[:_DETAIL_PREVIEW_LEN].rstrip()) + "…"
            detail_cell = (
                f'<span class="detail-preview" id="prev_{row_id}">{preview} '
                f'<button class="expand-btn" onclick="toggleDetail(\'{row_id}\')" '
                f'aria-expanded="false">ver mais ▼</button></span>'
                f'<span class="detail-full" id="full_{row_id}" style="display:none">'
                f'{detalhe_esc} '
                f'<button class="expand-btn" onclick="toggleDetail(\'{row_id}\')" '
                f'aria-expanded="true">ver menos ▲</button></span>'
            )
        else:
            detail_cell = html.escape(detalhe_full)

        rows_html += f"""<tr>
            <td>{_priority_badge(o['prioridade'])}</td>
            <td>{html.escape(o.get('categoria','').replace('_', ' ').title())}</td>
            <td>{html.escape(o['servico'])}</td>
            <td>{html.escape(o['acao'])}</td>
            <td class="detail-cell">{detail_cell}</td>
            <td>{_fmt_usd(o['economia_estimada_usd_mes'])}/mês</td>
            <td>{o['esforco_score']}/10</td>
            <td>{o.get('horizonte','—')}</td>
            <td title="{html.escape(o.get('tecnica_gartner',''))}">{html.escape(o.get('tecnica_gartner','')[:30])}{'…' if len(o.get('tecnica_gartner','')) > 30 else ''}</td>
        </tr>"""

    table_html = f"""
    <div class="section-card">
        <h2>Oportunidades priorizadas</h2>
        <input class="search-box" id="opp_search" placeholder="Filtrar por serviço, categoria, ação...">
        <button class="export-btn" onclick="exportCSV_tbl_opp()">⬇ Exportar CSV</button>
        <table id="tbl_opp">
            <thead><tr>
                <th>Prioridade</th><th>Categoria</th><th>Serviço</th>
                <th>Ação recomendada</th><th>Detalhe</th>
                <th>{_tooltip('Economia est.', 'Estimativa de economia mensal em dólares caso a oportunidade seja implementada. Baseada em heurísticas conservadoras — o valor real pode variar.')}</th>
                <th>{_tooltip('Facilidade', 'Score de 1 a 10. Quanto maior, mais fácil de implementar sem risco operacional.')}</th>
                <th>{_tooltip('Horizonte', 'Prazo sugerido para implementação: Imediato = pode ser feito agora sem risco; 30 dias = requer planejamento técnico; 90 dias = mudança estrutural ou de compromisso.')}</th>
                <th>Técnica Gartner</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """

    return scatter_html + table_html


# ============================================================
# HTML completo
# ============================================================

def write_optimization_html_report(
    output_dir: Path,
    start_date: str,
    end_date: str,
    df_service_trends: pd.DataFrame,
    opportunities: list[dict],
    unit_economics: dict,
    analysis_text: Optional[str] = None,
) -> str:
    """
    Gera relatório HTML interativo com 4 abas.
    Retorna o caminho do arquivo gerado.
    """
    filename = f"relatorio_otimizacao_{end_date}.html"
    filepath = output_dir / filename

    tab_exec = _tab_executive(unit_economics, df_service_trends, opportunities)
    tab_svc = _tab_services(df_service_trends, opportunities)
    tab_opp = _tab_opportunities(opportunities)
    tab_ai = _render_analysis_html(analysis_text)

    # JavaScript: sort, search, export + toggle de detalhe expandível
    js_toggle_detail = """
function toggleDetail(rowId) {
    var prev = document.getElementById('prev_' + rowId);
    var full = document.getElementById('full_' + rowId);
    if (!prev || !full) return;
    var isExpanded = full.style.display !== 'none';
    prev.style.display = isExpanded ? '' : 'none';
    full.style.display = isExpanded ? 'none' : '';
}
"""
    js_blocks = "\n".join([
        js_toggle_detail,
        _js_sort_table("tbl_services"),
        _js_sort_table("tbl_opp"),
        _js_search_table("svc_search", "tbl_services"),
        _js_search_table("opp_search", "tbl_opp"),
        _js_export_csv("tbl_services", f"servicos_{end_date}.csv"),
        _js_export_csv("tbl_opp", f"oportunidades_{end_date}.csv"),
    ])

    total_days = (
        datetime.strptime(end_date, "%Y-%m-%d").date()
        - datetime.strptime(start_date, "%Y-%m-%d").date()
    ).days + 1

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatório de Otimização AWS — {start_date} a {end_date}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>{_css()}</style>
</head>
<body>
<div class="header">
    <h1>Relatório de Otimização de Custos AWS</h1>
    <div class="subtitle">Período: {start_date} a {end_date} ({total_days} dias) · Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
<div class="tabs">
    <button class="tab active" onclick="showTab('exec',this)">Visão Executiva</button>
    <button class="tab" onclick="showTab('svc',this)">Diagnóstico por Serviço</button>
    <button class="tab" onclick="showTab('opp',this)">Oportunidades</button>
    <button class="tab" onclick="showTab('ai',this)">Análise</button>
</div>
<div id="tab-exec" class="tab-content active">{tab_exec}</div>
<div id="tab-svc" class="tab-content">{tab_svc}</div>
<div id="tab-opp" class="tab-content">{tab_opp}</div>
<div id="tab-ai" class="tab-content">{tab_ai}</div>
<script>
function showTab(name, btn) {{
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    btn.classList.add('active');
}}
{js_blocks}
</script>
</body>
</html>"""

    filepath.write_text(html_content, encoding="utf-8")
    print(f"  HTML gerado: {filepath}")
    return str(filepath)


# ============================================================
# TXT executivo
# ============================================================

def write_optimization_txt_report(
    output_dir: Path,
    start_date: str,
    end_date: str,
    df_service_trends: pd.DataFrame,
    opportunities: list[dict],
    unit_economics: dict,
    analysis_text: Optional[str] = None,
) -> str:
    """
    Gera relatório TXT executivo.
    Retorna o caminho do arquivo gerado.
    """
    filename = f"relatorio_otimizacao_{end_date}.txt"
    filepath = output_dir / filename

    total_days = (
        datetime.strptime(end_date, "%Y-%m-%d").date()
        - datetime.strptime(start_date, "%Y-%m-%d").date()
    ).days + 1

    ue = unit_economics
    daily_avg = ue.get("daily_avg_usd", 0.0)
    monthly_avgs = ue.get("monthly_avg_usd", [])
    projected_annual = ue.get("projected_annual_usd", 0.0)
    trend = ue.get("trend_usd_per_day", 0.0)
    mom_growth = ue.get("cost_growth_pct_mom", [])
    total_savings = sum(o["economia_estimada_usd_mes"] for o in opportunities)

    lines = [
        "=" * 72,
        "RELATÓRIO DE OTIMIZAÇÃO DE CUSTOS AWS",
        f"Período: {start_date} a {end_date} ({total_days} dias)",
        f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 72,
        "",
        "UNIT ECONOMICS",
        "-" * 40,
        f"  Custo médio/dia:          {_fmt_usd(daily_avg)}",
    ]

    labels_m = ["Mês 1", "Mês 2", "Mês 3"]
    for i, avg in enumerate(monthly_avgs):
        mom_str = ""
        if i > 0 and len(mom_growth) >= i:
            g = mom_growth[i - 1]
            mom_str = f"  ({'+' if g >= 0 else ''}{g:.1f}% vs mês anterior)"
        lines.append(f"  {labels_m[i]} (média/dia):    {_fmt_usd(avg)}{mom_str}")

    trend_sign = "+" if trend > 0 else ""
    lines += [
        f"  Tendência*:                {trend_sign}{trend:.4f} US$/dia",
        f"  Projeção anual (ult. 30d): {_fmt_usd(projected_annual)}",
        f"  Economia potencial:        {_fmt_usd(total_savings)}/mês",
        "",
        "  * Tendência = variação média de custo por dia calculada por regressão",
        "    linear sobre todo o período. Positivo = custo crescendo.",
        "",
    ]

    # Top oportunidades Alta Prioridade
    high = [o for o in opportunities if o["prioridade"] == "Alta"]
    if high:
        lines += ["TOP OPORTUNIDADES — ALTA PRIORIDADE", "-" * 40]
        for i, o in enumerate(high[:10], 1):
            lines.append(f"  {i}. [{o['categoria'].replace('_',' ').upper()}] {o['servico']}")
            lines.append(f"     Ação:     {o['acao']}")
            if o.get("detalhe"):
                lines.append(f"     Detalhe:  {o['detalhe']}")
            lines.append(f"     Economia: {_fmt_usd(o['economia_estimada_usd_mes'])}/mês  |  Horizonte: {o['horizonte']}")
            lines.append(f"     Gartner:  {o.get('tecnica_gartner', '')}")
            lines.append("")

    # Diagnóstico top 15 serviços
    lines += ["DIAGNÓSTICO POR SERVIÇO (top 15 por custo)", "-" * 40]
    if not df_service_trends.empty:
        col_w = [38, 14, 12, 12, 14]
        header = (
            f"  {'Serviço':<{col_w[0]}} {'Total 3M':>{col_w[1]}} "
            f"{'Média/dia':>{col_w[2]}} {'Comportamento':<{col_w[3]}} "
            f"{'Tend. US$/dia':>{col_w[4]}}"
        )
        lines.append(header)
        lines.append("  " + "-" * (sum(col_w) + 4))
        for _, row in df_service_trends.head(15).iterrows():
            svc = str(row["Serviço"])[:col_w[0]]
            trend_val = row["Tendência (US$/dia)"]
            trend_str = f"{'+' if trend_val >= 0 else ''}{trend_val:.4f}"
            lines.append(
                f"  {svc:<{col_w[0]}} {_fmt_usd(row['Total 3M (US$)']):>{col_w[1]}} "
                f"{_fmt_usd(row['Média diária (US$)']):>{col_w[2]}} "
                f"{row['Comportamento']:<{col_w[3]}} {trend_str:>{col_w[4]}}"
            )
    lines.append("")

    # Análise textual
    if analysis_text and analysis_text.strip():
        lines += ["", "ANÁLISE DO PERÍODO", "=" * 72, "", analysis_text.strip(), ""]

    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"  TXT gerado: {filepath}")
    return str(filepath)


# ============================================================
# CSVs
# ============================================================

def write_optimization_csvs(
    output_dir: Path,
    end_date: str,
    df_service_trends: pd.DataFrame,
    opportunities: list[dict],
    unit_economics: dict,
) -> list[str]:
    """
    Gera 3 arquivos CSV para análise externa.
    Retorna lista de caminhos gerados.
    """
    generated = []

    # 1. Oportunidades
    opp_path = output_dir / f"relatorio_otimizacao_{end_date}_oportunidades.csv"
    with open(opp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "prioridade", "categoria", "tecnica_gartner", "servico",
            "acao", "detalhe", "economia_estimada_usd_mes",
            "impacto_score", "esforco_score", "horizonte",
        ])
        writer.writeheader()
        for o in opportunities:
            writer.writerow({k: o.get(k, "") for k in writer.fieldnames})
    generated.append(str(opp_path))
    print(f"  CSV oportunidades: {opp_path}")

    # 2. Serviços
    svc_path = output_dir / f"relatorio_otimizacao_{end_date}_servicos.csv"
    if not df_service_trends.empty:
        df_service_trends.to_csv(svc_path, index=False, encoding="utf-8")
    else:
        svc_path.write_text("Sem dados de serviço.", encoding="utf-8")
    generated.append(str(svc_path))
    print(f"  CSV serviços: {svc_path}")

    # 3. Unit economics (série diária)
    ue_path = output_dir / f"relatorio_otimizacao_{end_date}_unit_economics.csv"
    daily_series = unit_economics.get("daily_series", [])
    vals = [d["cost_usd"] for d in daily_series]
    with open(ue_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["data", "custo_total_usd", "media_movel_7d_usd", "media_movel_30d_usd"])
        for i, d in enumerate(daily_series):
            window7 = vals[max(0, i - 6): i + 1]
            window30 = vals[max(0, i - 29): i + 1]
            ma7 = round(sum(window7) / len(window7), 4)
            ma30 = round(sum(window30) / len(window30), 4)
            writer.writerow([d["date"], d["cost_usd"], ma7, ma30])
    generated.append(str(ue_path))
    print(f"  CSV unit economics: {ue_path}")

    return generated
