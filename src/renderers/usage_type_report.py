import html
import json
import os
from typing import Optional

import pandas as pd


def _format_currency(value: float) -> str:
    return f"US$ {value:,.2f}"


def _render_summary(start_date: str, end_date: str, min_total_usd: float, row_count: int) -> str:
    return (
        f"Relatório UsageType 30 dias\n"
        f"Período: {start_date} até {end_date}\n"
        f"Filtro de custo mínimo no período: US$ {min_total_usd:.2f}\n"
        f"UsageType(s) analisado(s): {row_count}\n"
        "\n"
    )


def _normalize_text(value: Optional[str]) -> str:
    return str(value or "").strip()


def write_usage_type_txt_report(output_dir: str, start_date: str, end_date: str, df_report: pd.DataFrame, min_total_usd: float):
    os.makedirs(output_dir, exist_ok=True)
    output_txt = os.path.join(output_dir, f"relatorio_usagetype_30d_{end_date}.txt")

    header = _render_summary(start_date, end_date, min_total_usd, len(df_report))
    column_names = [
        "UsageType",
        "Serviço",
        "Total período",
        "Participação %",
        "Média diária",
        "Máximo",
        "Mínimo",
        "Variação %",
        "Impacto US$/dia",
    ]
    widths = [40, 28, 14, 14, 12, 12, 12, 12, 14]

    def format_row(values):
        return " ".join(
            str(value).ljust(width)[:width] if idx < 2 else str(value).rjust(width)
            for idx, (value, width) in enumerate(zip(values, widths))
        )

    with open(output_txt, "w", encoding="utf-8") as f:
        f.write(header)
        if df_report.empty:
            f.write("Nenhum UsageType com custo total acima do limite informado.\n")
            print(f"Relatório TXT salvo em: {output_txt}")
            return output_txt

        f.write("Principais UsageTypes por participação de custo no período:\n")
        for _, row in df_report.sort_values("Participação %", ascending=False).head(10).iterrows():
            f.write(
                f"- {row['UsageType']} | {row['Serviço']} | "
                f"total 30d {row['Total 30d']:.2f} | "
                f"participação {row['Participação %']:.2f}%\n"
            )
        f.write("\n")

        f.write("Maiores variações recentes (%):\n")
        for _, row in df_report.sort_values("Variação %", ascending=False).head(10).iterrows():
            f.write(
                f"- {row['UsageType']} | {row['Serviço']} | "
                f"último dia {row['Último dia']:.2f} | "
                f"variação {row['Variação %']:.2f}%\n"
            )
        f.write("\n")

        f.write("Tendência de 7 dias vs período anterior:\n")
        for _, row in df_report.sort_values("∆7d vs prev", ascending=False).head(10).iterrows():
            f.write(
                f"- {row['UsageType']} | {row['Serviço']} | "
                f"∆7d vs prev {row['∆7d vs prev']:.2f} | "
                f"média 7d {row['Média últimos 7 dias']:.2f}\n"
            )
        f.write("\n")

        f.write("Detalhamento completo:\n\n")
        f.write(format_row(column_names) + "\n")
        f.write("-" * sum(widths) + "\n")

        for _, row in df_report.iterrows():
            f.write(format_row([
                _normalize_text(row["UsageType"]),
                _normalize_text(row["Serviço"]),
                f"{row['Total 30d']:.2f}",
                f"{row['Participação %']:.2f}%",
                f"{row['Média diária']:.2f}",
                f"{row['Máximo 30d']:.2f}",
                f"{row['Mínimo 30d']:.2f}",
                f"{row['Variação %']:.2f}%",
                f"{row['Impacto US$/dia']:+.2f}",
            ]) + "\n")

    print(f"Relatório TXT salvo em: {output_txt}")
    return output_txt


_CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"


def write_usage_type_html_report(
    output_dir: str,
    start_date: str,
    end_date: str,
    df_report: pd.DataFrame,
    report_labels: list[str],
    forecast_labels: list[str],
    usage_type_chart_data: list[dict],
    total_daily_values: list[float],
    variation_chart_data: list[dict],
    variation_pct_chart_data: list[dict],
    top_anomalies: list[dict] = None,
    weekly_pattern_labels: list[str] = None,
    weekly_pattern_data: list[dict] = None,
):
    os.makedirs(output_dir, exist_ok=True)
    output_html = os.path.join(output_dir, f"relatorio_usagetype_30d_{end_date}.html")

    import config as _config  # importado localmente para não criar dependência circular

    escaped_start = html.escape(start_date)
    escaped_end = html.escape(end_date)
    total_count = len(df_report)
    forecast_days = _config.USAGE_TYPE_REPORT_FORECAST_DAYS

    # ── KPI cards ─────────────────────────────────────────────────────────────
    _badge_map = {
        "Crescendo": ("badge-growing",  "🔴 Crescendo"),
        "Caindo":    ("badge-declining","🟢 Caindo"),
        "Volátil":   ("badge-volatile", "🟡 Volátil"),
        "Estável":   ("badge-stable",   "⚪ Estável"),
    }

    def _kpi_card(label, value, sub="", extra_class=""):
        return (
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value {extra_class}">{value}</div>'
            + (f'<div class="kpi-sub">{sub}</div>' if sub else "")
            + '</div>'
        )

    kpi_html = '<div class="kpi-row">'
    if not df_report.empty:
        total_periodo = df_report["Total 30d"].sum()
        avg_daily_total = df_report["Média diária"].sum()
        kpi_html += _kpi_card("Total período", f"US$ {total_periodo:,.2f}",
                               f"{total_count} UsageTypes · US$ {avg_daily_total:,.2f}/dia em média")

        pos = df_report[df_report["Impacto US$/dia"] > 0]
        if not pos.empty:
            r = pos.loc[pos["Impacto US$/dia"].idxmax()]
            kpi_html += _kpi_card("Crescendo mais",
                                   html.escape(str(r["UsageType"])),
                                   f"+US$ {r['Impacto US$/dia']:.2f}/dia · {html.escape(str(r['Serviço']))}",
                                   "kpi-up")

        neg = df_report[df_report["Impacto US$/dia"] < 0]
        if not neg.empty:
            r = neg.loc[neg["Impacto US$/dia"].idxmin()]
            kpi_html += _kpi_card("Caindo mais",
                                   html.escape(str(r["UsageType"])),
                                   f"US$ {r['Impacto US$/dia']:.2f}/dia · {html.escape(str(r['Serviço']))}",
                                   "kpi-down")

        if "CV" in df_report.columns:
            r = df_report.loc[df_report["CV"].idxmax()]
            kpi_html += _kpi_card("Mais volátil",
                                   html.escape(str(r["UsageType"])),
                                   f"Variação diária média de {r['CV']*100:.0f}% da média · {html.escape(str(r['Serviço']))}")

        proj_daily = float((df_report["Média diária"] + df_report["Impacto US$/dia"] * 30).clip(lower=0).sum())
        delta_proj = proj_daily - avg_daily_total
        delta_cls = "kpi-up" if delta_proj > 0 else "kpi-down"
        delta_str = f"+US$ {delta_proj:,.2f}/dia vs hoje" if delta_proj >= 0 else f"US$ {delta_proj:,.2f}/dia vs hoje"
        kpi_html += _kpi_card("Projeção diária em 30d", f"US$ {proj_daily:,.2f}/dia", delta_str, delta_cls)

    kpi_html += '</div>'

    # ── Seção de anomalias ────────────────────────────────────────────────────
    anomaly_rows = ""
    if top_anomalies:
        for a in top_anomalies:
            direction_cls = "color:#b91c1c;font-weight:600" if a["direction"] == "Alta" else "color:#065f46;font-weight:600"
            arrow = "↑" if a["direction"] == "Alta" else "↓"
            anomaly_rows += (
                "<tr>"
                f"<td>{html.escape(a['date'])}</td>"
                f"<td>{html.escape(a['usage_type'])}</td>"
                f"<td>{html.escape(a['service'])}</td>"
                f"<td>US$ {a['cost']:.2f}</td>"
                f"<td>US$ {a['mean']:.2f}</td>"
                f"<td>{a['z_score']:+.2f}</td>"
                f"<td style='{direction_cls}'>{arrow} {html.escape(a['direction'])}</td>"
                "</tr>"
            )

    anomaly_html = ""
    def _ath(label, tip):
        """Cabeçalho de coluna da tabela de anomalias com ícone de informação."""
        return (
            f'<th>{label}'
            f'<span class="ic">i<span class="tip">{tip}</span></span>'
            f'</th>'
        )

    if anomaly_rows:
        anomaly_html = (
            '<div class="section-card">'
            '<h2>Dias com comportamento anômalo</h2>'
            '<p class="chart-desc">Cada linha é um dia em que um UsageType se comportou de forma muito diferente do normal dele próprio — '
            'não do período inteiro, mas da média histórica daquele item específico. '
            'Ordenado pelo mais extremo primeiro.</p>'
            '<div style="overflow-x:auto"><table class="anomaly-table"><thead><tr>'
            + _ath("Data",
                   "Dia em que a anomalia foi detectada.")
            + _ath("UsageType",
                   "Tipo de consumo que teve o comportamento fora do normal.")
            + _ath("Serviço",
                   "Serviço AWS ao qual o UsageType pertence.")
            + _ath("Custo no dia",
                   "Quanto custou especificamente neste dia anômalo.")
            + _ath("Média do período",
                   "Quanto este UsageType custa por dia em média, calculado sobre todo o período analisado. "
                   "É a referência para comparar se o dia foi normal ou não.")
            + _ath("Z-score",
                   "Mede o quanto este dia se distanciou da média, em unidades de desvio padrão. "
                   "Pense assim: z=2 significa que o dia foi tão fora do padrão que só aconteceria em ~5% dos dias por acaso. "
                   "z=3 seria em ~0,3% dos dias. Quanto maior o valor absoluto, mais extrema a anomalia. "
                   "Positivo = custo acima do normal; negativo = custo abaixo do normal.")
            + _ath("Direção",
                   "↑ Alta = o custo deste dia foi muito acima do habitual — pode indicar uso inesperado, pico de tráfego ou incidente. "
                   "↓ Queda = o custo foi muito abaixo do normal — pode indicar parada de serviço, falta de dados ou mudança de configuração.")
            + '</tr></thead><tbody>' + anomaly_rows + '</tbody></table></div>'
            + '</div>'  # fecha section-card
        )

    # ── JSON do padrão semanal ────────────────────────────────────────────────
    weekly_labels_json = json.dumps(weekly_pattern_labels or [])
    weekly_data_json   = json.dumps(weekly_pattern_data   or [])

    # ── Linhas da tabela ──────────────────────────────────────────────────────
    rows_html = []
    for _, row in df_report.iterrows():
        comp = str(row.get("Comportamento", "Estável"))
        badge_cls, badge_label = _badge_map.get(comp, ("badge-stable", comp))
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(str(row['UsageType']))}</td>"
            f"<td>{html.escape(str(row['Serviço']))}</td>"
            f'<td><span class="badge {badge_cls}">{badge_label}</span></td>'
            f"<td>{row['Total 30d']:.2f}</td>"
            f"<td>{row['Participação %']:.2f}%</td>"
            f"<td>{row['Média diária']:.2f}</td>"
            f"<td>{row['Máximo 30d']:.2f}</td>"
            f"<td>{row['Mínimo 30d']:.2f}</td>"
            f"<td>{row['Variação %']:.2f}%</td>"
            f"<td>{row['Impacto US$/dia']:+.2f}</td>"
            "</tr>"
        )

    def _th(col, label, tip):
        return (
            f'<th class="sortable" data-column="{col}">'
            f'{label}<span class="ic">i<span class="tip">{tip}</span></span>'
            f'</th>'
        )

    body_table = (
        '<div class="section-card">'
        '<h2>Detalhamento por UsageType</h2>'
        '<p class="chart-desc">Todos os UsageTypes identificados no período, com custo total, participação, tendência e impacto diário. '
        'Clique no cabeçalho de qualquer coluna para ordenar.</p>'
        '<div style="overflow-x:auto">'
        '<table id="usageTypeTable"><thead><tr>'
        + _th(0, "UsageType",      "Identificador do tipo de consumo dentro do serviço AWS (ex: BoxUsage:c6i.2xlarge, SnapshotUsage).")
        + _th(1, "Serviço",        "Serviço AWS ao qual o UsageType pertence (ex: EC2, S3, GuardDuty).")
        + _th(2, "Status",         "Como o custo deste item se comportou ao longo do período: 🔴 Crescendo = o custo está subindo consistentemente mais de 1% por dia em relação à própria média — atenção redobrada. 🟢 Caindo = o custo está caindo consistentemente mais de 1% por dia — tendência favorável. 🟡 Volátil = o custo oscila muito de um dia para o outro (variação diária maior que 50% da média) — difícil prever, pode esconder picos. ⚪ Estável = comportamento regular, sem tendência forte de alta ou baixa.")
        + _th(3, "Total período",  "Custo total em US$ acumulado em todos os dias do período analisado.")
        + _th(4, "Participação %", "Percentual que este UsageType representa no custo total do período, considerando todos os UsageTypes incluídos.")
        + _th(5, "Média diária",   "Custo médio por dia, calculado sobre todos os dias do período (incluindo dias com custo zero).")
        + _th(6, "Máximo",         "Maior custo registrado em um único dia dentro do período analisado.")
        + _th(7, "Mínimo",         "Menor custo registrado em um único dia dentro do período analisado.")
        + _th(8, "Variação %",      "Variação percentual do custo do último dia em relação à média diária do período.")
        + _th(9, "Impacto US$/dia", "Tendência diária de custo em US$: o quanto o custo está subindo ou caindo por dia em média, calculado sobre todo o período. Ex: +3.40 = custo cresce ~US$3,40 por dia; -1.20 = custo cai ~US$1,20 por dia. Diferente da Variação %: considera o volume absoluto — um item de US$500 subindo devagar tem impacto maior que um de US$5 subindo muito. Base para o ranking do gráfico de variação %.")
        + '</tr></thead><tbody>'
        + "".join(rows_html)
        + "</tbody></table>"
        + '</div>'   # fecha overflow-x:auto
        + '</div>'   # fecha section-card
    )

    report_labels_json = json.dumps(report_labels)
    forecast_labels_json = json.dumps(forecast_labels)
    usage_type_chart_data_json = json.dumps(usage_type_chart_data)
    total_daily_values_json = json.dumps(total_daily_values)
    variation_chart_data_json = json.dumps(variation_chart_data)
    variation_pct_chart_data_json = json.dumps(variation_pct_chart_data)

    html_content = fr"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Relatório UsageType</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; color: #1a202c; margin: 24px; }}
    h1 {{ margin-bottom: 0.2em; }}
    .meta {{ margin-bottom: 0.5rem; color: #4a5568; }}
    .hint {{ margin-bottom: 1rem; color: #2d3748; font-size: 0.95rem; }}
    .chart-controls {{ display: flex; gap: 8px; margin-bottom: 20px; align-items: center; }}
    .chart-controls span {{ font-size: 0.9rem; color: #4a5568; margin-right: 4px; }}
    .ctrl-btn {{
      padding: 6px 14px; border: 1px solid #cbd5e0; border-radius: 6px;
      background: #f7fafc; cursor: pointer; font-size: 0.9rem; color: #2d3748;
      transition: all 0.15s;
    }}
    .ctrl-btn.active {{ background: #2563eb; color: #fff; border-color: #2563eb; font-weight: bold; }}
    .ctrl-btn:hover:not(.active) {{ background: #edf2f7; }}
    .chart-row {{ display: grid; grid-template-columns: 1fr; gap: 24px; margin-bottom: 24px; }}
    .chart-card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08); }}
    .chart-card h2 {{ margin-top: 0; font-size: 1rem; margin-bottom: 4px; }}
    .chart-desc {{ margin: 0 0 12px 0; font-size: 0.85rem; color: #718096; }}
    .chart-container {{ position: relative; min-height: 360px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
    th, td {{ border: 1px solid #cbd5e0; padding: 8px; text-align: left; }}
    th {{ background: #edf2f7; cursor: pointer; user-select: none; white-space: nowrap; }}
    tr:nth-child(even) {{ background: #f7fafc; }}
    .summary {{ margin-bottom: 1rem; }}
    .note {{ color: #4a5568; font-size: 0.9rem; margin-top: 1rem; }}
    th.asc::after {{ content: ' ▲'; }}
    th.desc::after {{ content: ' ▼'; }}
    /* ── Section cards ── */
    .section-card {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:16px; box-shadow:0 1px 4px rgba(15,23,42,0.08); margin-bottom:24px; }}
    .section-card h2 {{ margin-top:0; font-size:1rem; margin-bottom:4px; }}
    .anomaly-table {{ border-collapse:collapse; width:100%; font-size:0.88rem; }}
    .anomaly-table th, .anomaly-table td {{ border:1px solid #e2e8f0; padding:7px 10px; text-align:left; }}
    .anomaly-table th {{ background:#edf2f7; white-space:nowrap; position:relative; overflow:visible; }}
    .anomaly-table tr:nth-child(even) {{ background:#f7fafc; }}
    /* tooltip da tabela de anomalias abre para baixo para não ser cortado pelo overflow-x:auto */
    .anomaly-table .ic .tip {{ bottom: auto; top: 130%; left: 50%; transform: translateX(-50%); }}
    /* ── KPI cards ── */
    .kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .kpi-card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 4px rgba(15,23,42,0.07); }}
    .kpi-label {{ font-size: 0.7rem; color: #718096; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }}
    .kpi-value {{ font-size: 1.05rem; font-weight: 700; color: #1a202c; word-break: break-word; }}
    .kpi-sub {{ font-size: 0.78rem; color: #4a5568; margin-top: 4px; }}
    .kpi-up {{ color: #b91c1c; }}
    .kpi-down {{ color: #065f46; }}
    /* ── Badges de comportamento ── */
    .badge {{ display: inline-block; padding: 2px 9px; border-radius: 12px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
    .badge-growing  {{ background: #fee2e2; color: #b91c1c; }}
    .badge-declining {{ background: #d1fae5; color: #065f46; }}
    .badge-volatile {{ background: #fef9c3; color: #92400e; }}
    .badge-stable   {{ background: #f1f5f9; color: #475569; }}
    /* ── Ícone de informação com tooltip ── */
    .ic {{
      display: inline-flex; align-items: center; justify-content: center;
      width: 14px; height: 14px; border-radius: 50%;
      background: #a0aec0; color: #fff;
      font-size: 9px; font-weight: bold; font-style: normal;
      cursor: help; margin-left: 5px; position: relative;
      vertical-align: middle; flex-shrink: 0;
    }}
    .ic .tip {{
      visibility: hidden; opacity: 0;
      width: 230px; background: #2d3748; color: #e2e8f0;
      font-size: 12px; font-weight: normal; line-height: 1.5;
      text-align: left; white-space: normal;
      border-radius: 6px; padding: 8px 10px;
      position: absolute; z-index: 200;
      bottom: 130%; left: 50%; transform: translateX(-50%);
      pointer-events: none;
      transition: opacity 0.15s;
    }}
    .ic:hover .tip {{ visibility: visible; opacity: 1; }}
    .anomaly-table .ic:hover {{ z-index: 300; }}
  </style>
</head>
<body>
  <h1>Relatório UsageType</h1>
  <div class="meta">Período: {escaped_start} até {escaped_end}</div>
  <div class="meta">UsageTypes incluídos: {total_count}</div>
  <div class="hint">Clique no cabeçalho de qualquer coluna para ordenar por maior/menor valor.</div>

  {kpi_html}

  <div class="chart-controls">
    <span>Visualização:</span>
    <button class="ctrl-btn active" data-mode="line" onclick="setMode('line')">━ Linhas</button>
    <button class="ctrl-btn" data-mode="bar" onclick="setMode('bar')">▐▐ Barras empilhadas</button>
  </div>

  <div class="chart-row">
    <div class="chart-card">
      <h2>Uso diário — custo por UsageType (US$)</h2>
      <p class="chart-desc">Custo diário em US$ por UsageType no período analisado. Identifica picos pontuais, sazonalidade e dias de maior gasto. A categoria "Others" agrega todos os UsageTypes fora do top 10.
        <span style="display:inline-flex;align-items:center;gap:5px;margin-left:8px;font-size:0.82rem;color:#c53030;font-weight:600;">
          <svg width="10" height="10"><circle cx="5" cy="5" r="5" fill="#ef4444"/></svg>
          Ponto vermelho = dia com anomalia detectada
        </span>
      </p>
      <div class="chart-container">
        <canvas id="dailyUsageChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h2>Tendência futura por UsageType — próximos {forecast_days} dias (US$)</h2>
      <p class="chart-desc">Projeção linear de custo em US$ para os {forecast_days} dias após o fim do relatório, calculada com base em toda a janela do período. Referência de trajetória esperada — não é previsão definitiva.</p>
      <div class="chart-container">
        <canvas id="trendChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h2>Variação percentual diária por UsageType (%)</h2>
      <p class="chart-desc">Variação percentual do custo de cada UsageType em relação ao dia anterior. Exibe os top 10 por maior "Impacto US$/dia" — os que mais crescem em termos financeiros reais. Detecta mudanças bruscas e outliers diários.</p>
      <div class="chart-container">
        <canvas id="variationPctChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h2>Padrão semanal — custo médio por dia da semana (US$)</h2>
      <p class="chart-desc">Custo médio de cada UsageType por dia da semana ao longo do período. Revela sazonalidade semanal — ex: picos às segundas, quedas nos fins de semana. Ajuda a distinguir comportamento esperado de anomalia real.</p>
      <div class="chart-container">
        <canvas id="weeklyChart"></canvas>
      </div>
    </div>
  </div>

  {anomaly_html}

  {body_table}
  <div class="note">Relatório gerado a partir de dados do Cost Explorer.</div>

  <script>
    // ── Dados vindos do backend ──────────────────────────────────────────────
    const reportLabels       = {report_labels_json};
    const forecastLabels     = {forecast_labels_json};
    const usageTypeChartData = {usage_type_chart_data_json};
    const totalDailyValues   = {total_daily_values_json};
    const variationPctData   = {variation_pct_chart_data_json};
    const weeklyLabels       = {weekly_labels_json};
    const weeklyData         = {weekly_data_json};

    // ── Paleta de cores ──────────────────────────────────────────────────────
    // 10 cores para o top 10 + cor neutra para "Others"
    const COLORS = [
      '#2563eb','#10b981','#ea580c','#a855f7','#06b6d4',
      '#eab308','#ef4444','#14b8a6','#f97316','#8b5cf6',
    ];
    const OTHERS_COLOR = '#78716c';

    // ── Instâncias dos gráficos ──────────────────────────────────────────────
    let charts = {{ daily: null, trend: null, varPct: null, weekly: null }};
    let currentMode = 'line';

    // ── Helpers de formatação ────────────────────────────────────────────────
    function fmtVal(raw, unit) {{
      if (raw === null || raw === undefined) return null;
      return unit === '%' ? raw.toFixed(2) + '%' : 'US$ ' + raw.toFixed(2);
    }}

    // Plugin: esmaece datasets não-ativos via globalAlpha durante o draw.
    Chart.register({{
      id: 'legendHighlight',
      beforeDatasetDraw(chart, args) {{
        const active = chart._activeLegendIdx;
        if (active === undefined || active === -1) return;
        if (args.index !== active) {{
          chart.ctx.save();
          chart.ctx.globalAlpha = 0.07;
        }}
      }},
      afterDatasetDraw(chart, args) {{
        const active = chart._activeLegendIdx;
        if (active === undefined || active === -1) return;
        if (args.index !== active) chart.ctx.restore();
      }},
    }});

    // ── Tooltip DOM customizado ──────────────────────────────────────────────
    // Tooltip completamente fora do ciclo do Chart.js → sem race conditions.
    function createTooltipEl(container) {{
      const el = document.createElement('div');
      el.style.cssText = [
        'position:absolute','pointer-events:none','z-index:50',
        'background:rgba(22,22,32,0.93)','color:#fff',
        'border-radius:8px','padding:10px 14px',
        'font-size:12px','font-family:Arial,sans-serif',
        'box-shadow:0 4px 14px rgba(0,0,0,0.35)',
        'max-width:460px','line-height:1.65',
        'opacity:0','transition:opacity 0.08s ease',
      ].join(';');
      container.style.position = 'relative';
      container.appendChild(el);
      return el;
    }}

    function renderTooltip(chart, ttEl, mouseEvent, activeIdx, unit) {{
      const allEls = chart.getElementsAtEventForMode(mouseEvent, 'index', {{intersect: false}}, false);
      if (allEls.length === 0) {{ ttEl.style.opacity = '0'; return; }}

      const xIdx    = allEls[0].index;
      const dateStr = chart.data.labels[xIdx];
      let html = `<div style="font-weight:600;margin-bottom:6px;font-size:13px">${{dateStr}}</div>`;

      allEls.forEach(el => {{
        const di  = el.datasetIndex;
        const ds  = chart.data.datasets[di];
        const val = ds.data[xIdx];
        if (val === null || val === undefined) return;
        const formatted = fmtVal(val, unit) || val;
        const color     = ds.backgroundColor || ds.borderColor || '#888';
        const isActive  = activeIdx === -1 || di === activeIdx;
        const marker    = (activeIdx !== -1 && di === activeIdx) ? '▶ ' : '   ';
        const weight    = (activeIdx !== -1 && di === activeIdx) ? '600' : '400';
        html += `<div style="display:flex;align-items:center;gap:6px;margin:2px 0;
                   opacity:${{isActive ? 1 : 0.28}};font-weight:${{weight}}">
          <span style="width:10px;height:10px;border-radius:2px;background:${{color}};
            display:inline-block;flex-shrink:0"></span>
          <span>${{marker}}${{ds.label}}: ${{formatted}}</span>
        </div>`;
      }});

      ttEl.innerHTML = html;

      // Posicionamento: evita transbordar à direita ou ao fundo.
      const cw  = chart.canvas.offsetWidth;
      const ch  = chart.canvas.offsetHeight;
      const rect = chart.canvas.getBoundingClientRect();
      const mx  = mouseEvent.clientX - rect.left;
      const my  = mouseEvent.clientY - rect.top;
      const tw  = Math.min(460, cw * 0.55);
      const left = (mx + 20 + tw > cw) ? mx - tw - 15 : mx + 15;
      ttEl.style.left    = left + 'px';
      ttEl.style.top     = Math.max(0, my - 20) + 'px';
      ttEl.style.opacity = '1';
    }}

    // Conecta hover direto no canvas: sem passar pelo ciclo de rendering do Chart.js.
    function setupHover(chart, unit) {{
      chart._activeLegendIdx = -1;
      const ttEl = createTooltipEl(chart.canvas.parentNode);
      chart._ttEl = ttEl;

      chart.canvas.addEventListener('mousemove', (e) => {{
        const nearest = chart.getElementsAtEventForMode(e, 'nearest', {{intersect: false}}, false);
        const newIdx  = nearest.length > 0 ? nearest[0].datasetIndex : -1;
        chart.canvas.style.cursor = newIdx !== -1 ? 'crosshair' : 'default';
        if (chart._activeLegendIdx !== newIdx) {{
          chart._activeLegendIdx = newIdx;
          chart.render();  // redesenha o canvas com globalAlpha correto
        }}
        renderTooltip(chart, ttEl, e, newIdx, unit);
      }});

      chart.canvas.addEventListener('mouseleave', () => {{
        chart._activeLegendIdx = -1;
        chart.render();
        ttEl.style.opacity = '0';
      }});
    }}

    function scaleOptions(unit, stacked) {{
      return {{
        x: {{
          stacked: !!stacked,
          ticks: {{ color: '#4a5568', maxRotation: 45, minRotation: 30 }},
          grid: {{ color: 'rgba(203,213,224,0.5)' }},
        }},
        y: {{
          stacked: !!stacked,
          title: {{ display: true, text: unit, color: '#4a5568', font: {{ weight: 'bold' }} }},
          ticks: {{ color: '#4a5568' }},
          grid: {{ color: 'rgba(203,213,224,0.5)' }},
        }},
      }};
    }}

    // ── Builders de datasets ─────────────────────────────────────────────────
    function lineDatasets(data, key, showAnomalies = true) {{
      return data.map((item, i) => {{
        const color  = COLORS[i % COLORS.length];
        const values = item[key];
        const anom   = showAnomalies ? new Set(item.anomaly_indices || []) : new Set();
        return {{
          label: item.UsageType,
          data: values,
          borderColor: color,
          backgroundColor: color,
          fill: false,
          tension: 0.25,
          // Dias anômalos: ponto maior e vermelho; normal: ponto pequeno na cor da série.
          pointRadius: values.map((_, j) => anom.has(j) ? 7 : 2),
          pointBackgroundColor: values.map((_, j) => anom.has(j) ? '#ef4444' : color),
          pointBorderColor: values.map((_, j) => anom.has(j) ? '#fff' : color),
          pointBorderWidth: values.map((_, j) => anom.has(j) ? 2 : 0),
          pointHoverRadius: 6,
        }};
      }});
    }}

    // Datasets empilhados com "Others" opcional (apenas quando totalDaily fornecido).
    function stackedDatasets(data, key, totalDaily) {{
      const ds = data.map((item, i) => ({{
        label: item.UsageType,
        data: item[key].map(v => v === null ? 0 : v),
        backgroundColor: COLORS[i % COLORS.length],
        borderColor: COLORS[i % COLORS.length],
        borderWidth: 0,
        stack: 'stack0',
      }}));
      if (totalDaily) {{
        const othersData = totalDaily.map((total, i) => {{
          const top10Sum = data.reduce((s, item) => s + (item[key][i] || 0), 0);
          return Math.max(0, total - top10Sum);
        }});
        ds.push({{
          label: 'Others',
          data: othersData,
          backgroundColor: OTHERS_COLOR,
          borderColor: OTHERS_COLOR,
          borderWidth: 0,
          stack: 'stack0',
        }});
      }}
      return ds;
    }}

    // ── Builder principal ────────────────────────────────────────────────────
    function buildChart(canvasId, labels, datasets, unit, type, stacked) {{
      const ctx = document.getElementById(canvasId).getContext('2d');
      const isBar = type === 'bar';
      const useStacked = isBar && stacked !== false;
      const chart = new Chart(ctx, {{
        type: isBar ? 'bar' : 'line',
        data: {{ labels, datasets }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ position: 'bottom' }},
            tooltip: {{ enabled: false }},  // tooltip nativo desabilitado — usando DOM customizado
          }},
          scales: scaleOptions(unit, useStacked),
        }},
      }});
      setupHover(chart, unit);
      return chart;
    }}

    // ── Toggle global de visualização ────────────────────────────────────────
    function setMode(mode) {{
      currentMode = mode;
      document.querySelectorAll('.ctrl-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.mode === mode)
      );
      // Remove tooltips DOM antigos antes de destruir os gráficos.
      Object.values(charts).forEach(c => {{ if (c && c._ttEl) c._ttEl.remove(); }});
      Object.values(charts).forEach(c => c && c.destroy());

      // Gráfico semanal: sempre barras agrupadas (7 pontos, independente do modo).
      const weeklyDs = weeklyData.map((item, i) => ({{
        label: item.UsageType,
        data: item.values,
        backgroundColor: COLORS[i % COLORS.length],
        borderColor: COLORS[i % COLORS.length],
        borderWidth: 0,
      }}));

      if (mode === 'line') {{
        charts.daily  = buildChart('dailyUsageChart',  reportLabels,   lineDatasets(usageTypeChartData, 'daily_values', true),     'US$', 'line');
        charts.trend  = buildChart('trendChart',        forecastLabels, lineDatasets(usageTypeChartData, 'forecast_values', false), 'US$', 'line');
        charts.varPct = buildChart('variationPctChart', reportLabels,   lineDatasets(variationPctData,   'variation_pct_values'), '%', 'line');
      }} else {{
        charts.daily  = buildChart('dailyUsageChart',  reportLabels,   stackedDatasets(usageTypeChartData, 'daily_values',    totalDailyValues), 'US$', 'bar');
        charts.trend  = buildChart('trendChart',        forecastLabels, stackedDatasets(usageTypeChartData, 'forecast_values', null),             'US$', 'bar');
        charts.varPct = buildChart('variationPctChart', reportLabels,   stackedDatasets(variationPctData, 'variation_pct_values', null), '%', 'bar');
      }}
      charts.weekly = buildChart('weeklyChart', weeklyLabels, weeklyDs, 'US$', 'bar', false);
    }}

    // ── Ordenação da tabela ──────────────────────────────────────────────────
    const table = document.getElementById('usageTypeTable');
    const getCellValue = (row, idx) => {{
      const text = row.children[idx].textContent.trim();
      const n = parseFloat(text.replace(/[\.\,\%\s]/g, '.'));
      return Number.isFinite(n) && text.match(/[0-9]/) ? n : text.toLowerCase();
    }};
    const comparer = (idx, asc) => (a, b) => {{
      const v1 = getCellValue(asc ? a : b, idx);
      const v2 = getCellValue(asc ? b : a, idx);
      return typeof v1 === 'number' && typeof v2 === 'number' ? v1 - v2 : v1.localeCompare(v2);
    }};
    table.querySelectorAll('th.sortable').forEach(th => {{
      th.addEventListener('click', () => {{
        const tbody = table.tBodies[0];
        const rows  = Array.from(tbody.querySelectorAll('tr'));
        const col   = Number(th.dataset.column);
        const asc   = !th.classList.contains('asc');
        rows.sort(comparer(col, asc)).forEach(r => tbody.appendChild(r));
        table.querySelectorAll('th.sortable').forEach(h => h.classList.remove('asc', 'desc'));
        th.classList.toggle('asc', asc);
        th.classList.toggle('desc', !asc);
      }});
    }});

    // ── Inicializa em modo linha ─────────────────────────────────────────────
    setMode('line');
  </script>
</body>
</html>"""

    with open(output_html, "w", encoding="utf-8") as fh:
        fh.write(html_content)

    print(f"Relatório HTML salvo em: {output_html}")
    return output_html
