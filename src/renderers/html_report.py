"""
HTML report renderer — two-tab layout: cost overview and AI analysis.
Uses Chart.js (CDN) for interactive charts; no other external dependencies.
"""

import json
import os
import re

import config
import utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(text):
    """Escape HTML special characters."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _inline_md(text):
    """Convert **bold** and `code` to HTML inline elements."""
    text = _esc(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def _classification_badge(classification):
    """Return an HTML badge for the anomaly classification."""
    norm = (classification or "").strip().lower()
    if norm == "anomalia real":
        css = "badge-anomalia"
        label = "ANOMALIA REAL"
    elif norm == "efeito em cascata":
        css = "badge-cascata"
        label = "EFEITO EM CASCATA"
    else:
        css = "badge-esperado"
        label = "DESVIO ESPERADO"
    return f'<span class="badge {css}">{label}</span>'


def _delta_html(value, suffix="%"):
    """Format a signed delta value with colored span."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _esc(str(value))
    css = "positive" if v > 0 else "negative" if v < 0 else ""
    sign = "+" if v > 0 else ""
    return f'<span class="{css}">{sign}{v:,.2f}{suffix}</span>'


# ---------------------------------------------------------------------------
# AI analysis parser
# ---------------------------------------------------------------------------

def _parse_ai_analysis(ai_text):
    """
    Parse the AI narrative markdown into structured Python dicts for HTML rendering.
    Returns None when no text is provided.
    """
    if not ai_text:
        return None

    text = re.sub(r"^AI Analysis:\s*\n+", "", ai_text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"^AI Analysis\s*\n+", "", text, flags=re.IGNORECASE)

    result = {
        "executive_summary": [],
        "drivers": [],
        "recommendations": [],
    }

    # Executive summary bullets
    exec_match = re.search(
        r"##\s+Resumo\s+executivo\s*\n(.*?)(?=\n##\s|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if exec_match:
        for line in exec_match.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                result["executive_summary"].append(line[2:].strip())
            elif line and line != "---":
                result["executive_summary"].append(line)

    # Driver sections
    driver_blocks = re.split(r"\n---\n", text)
    driver_re = re.compile(
        r"###\s+\d+\.\s+(.*?)[\n]"
        r"\*\*Classifica[çc][aã]o:\*\*\s*`([^`]+)`",
        re.IGNORECASE,
    )
    for block in driver_blocks:
        m = driver_re.search(block)
        if not m:
            continue
        title = m.group(1).strip()
        classification = m.group(2).strip()

        def _extract(label, src):
            pat = re.search(
                rf"\*\*{label}[:\s]*\*\*\s*(.*?)(?=\n\*\*|\Z)", src, re.DOTALL | re.IGNORECASE
            )
            return pat.group(1).strip() if pat else ""

        result["drivers"].append({
            "title": title,
            "classification": classification,
            "causa": _extract("Causa prov[aá]vel", block),
            "evidencias": _extract("Evid[eê]ncias", block),
            "confianca": _extract("Confian[çc]a", block),
        })

    # Recommendations
    recs_match = re.search(
        r"##\s+Recomenda[çc][oõ]es\s*\n(.*?)(?=\n##\s|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if recs_match:
        recs_text = recs_match.group(1).strip()
        rec_items = re.findall(
            r"\d+\.\s+\*\*([^*]+)\*\*[:\s]*(.*?)(?=\n\d+\.|\n---|\*\*ANALISE|\Z)",
            recs_text, re.DOTALL,
        )
        for rec_title, rec_body in rec_items:
            result["recommendations"].append({
                "title": rec_title.strip(".: "),
                "body": " ".join(rec_body.strip().splitlines()),
            })

    return result


# ---------------------------------------------------------------------------
# Section builders — return HTML strings
# ---------------------------------------------------------------------------

def _build_kpi_cards(custo_medio, custo_ultimo_dia, variacao_media, ultimo_dia):
    custo_ultimo = custo_ultimo_dia if custo_ultimo_dia is not None else 0.0
    var_css = "positive" if variacao_media > 0 else "negative" if variacao_media < 0 else ""
    var_sign = "+" if variacao_media > 0 else ""
    return f"""
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Custo médio diário</div>
    <div class="kpi-value">US$ {custo_medio:,.2f}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Dia de referência ({_esc(ultimo_dia)})</div>
    <div class="kpi-value">US$ {custo_ultimo:,.2f}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Variação vs. média</div>
    <div class="kpi-value {var_css}">{var_sign}US$ {variacao_media:,.2f}</div>
  </div>
</div>
"""


def _build_daily_chart_section(daily_labels, daily_values):
    if not daily_labels:
        return ""
    labels_json = json.dumps(daily_labels)
    values_json = json.dumps(daily_values)
    return f"""
<section class="card">
  <h2>Custos por dia na janela</h2>
  <div class="chart-container"><canvas id="dailyCostChart"></canvas></div>
</section>
<script>
(function() {{
  var ctx = document.getElementById('dailyCostChart').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels_json},
      datasets: [{{
        label: 'Custo (US$)',
        data: {values_json},
        backgroundColor: 'rgba(192,29,38,0.75)',
        borderColor: 'rgba(192,29,38,1)',
        borderWidth: 1,
        borderRadius: 4,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{
        label: function(ctx) {{ return ' US$ ' + ctx.parsed.y.toLocaleString('pt-BR', {{minimumFractionDigits:2}}); }}
      }}}} }},
      scales: {{
        y: {{ beginAtZero: true, ticks: {{ callback: function(v) {{ return 'US$ ' + v.toLocaleString('pt-BR'); }} }} }},
        x: {{ grid: {{ display: false }} }}
      }}
    }}
  }});
}})();
</script>
"""


def _build_variation_section(aumentaram, reduziram, data_inicio, data_fim):
    def _table_rows(df, positive):
        rows = ""
        for svc, row in df.iterrows():
            svc_name = _esc(str(svc).replace("($)", "").strip())
            var_usd = float(row["Variação US$"])
            var_pct = float(row["Variação %"])
            sign = "+" if positive else ""
            usd_html = f'<span class="{"positive" if positive else "negative"}">{sign}{var_usd:,.2f}</span>'
            pct_html = f'<span class="{"positive" if positive else "negative"}">{sign}{var_pct:.2f}%</span>'
            rows += f"<tr><td>{svc_name}</td><td>{usd_html}</td><td>{pct_html}</td></tr>\n"
        return rows

    html = f"""
<section class="card">
  <h2>Variação de serviços <small>({_esc(data_inicio)} a {_esc(data_fim)})</small></h2>
  <div class="two-col">
    <div>
      <h3 class="section-label increase">&#9650; Serviços que aumentaram</h3>
      <table class="data-table">
        <thead><tr><th>Serviço</th><th>US$</th><th>%</th></tr></thead>
        <tbody>{_table_rows(aumentaram, True)}</tbody>
      </table>
    </div>
    <div>
      <h3 class="section-label decrease">&#9660; Serviços que reduziram</h3>
      <table class="data-table">
        <thead><tr><th>Serviço</th><th>US$</th><th>%</th></tr></thead>
        <tbody>{_table_rows(reduziram, False)}</tbody>
      </table>
    </div>
  </div>
</section>
"""
    return html


def _build_top_services_section(top_costs, ultimo_dia):
    # top_costs pode ser pandas Series ou dict — evitar bool() ambíguo
    if top_costs is None or (hasattr(top_costs, "empty") and top_costs.empty) or len(top_costs) == 0:
        return ""
    # .items() funciona tanto para dict quanto para pd.Series; evita .values() ambíguo
    labels = [str(k).replace("($)", "").strip() for k, _ in top_costs.items()]
    values = [round(float(v), 2) for _, v in top_costs.items()]
    labels_json = json.dumps(labels)
    values_json = json.dumps(values)

    rows = ""
    for i, (svc, val) in enumerate(top_costs.items(), start=1):
        rows += f"<tr><td>{i}</td><td>{_esc(str(svc).replace('($)', '').strip())}</td><td>US$ {float(val):,.2f}</td></tr>\n"

    return f"""
<section class="card">
  <h2>TOP {len(top_costs)} serviços em {_esc(ultimo_dia)}</h2>
  <div class="two-col">
    <div>
      <table class="data-table">
        <thead><tr><th>#</th><th>Serviço</th><th>Custo US$</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <div class="chart-container chart-medium">
      <canvas id="topServicesChart"></canvas>
    </div>
  </div>
</section>
<script>
(function() {{
  var ctx = document.getElementById('topServicesChart').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels_json},
      datasets: [{{
        data: {values_json},
        backgroundColor: [
          'rgba(192,29,38,0.80)','rgba(220,80,80,0.75)','rgba(240,120,90,0.70)',
          'rgba(255,160,110,0.65)','rgba(255,190,130,0.60)','rgba(255,210,150,0.55)',
          'rgba(200,170,220,0.60)','rgba(140,180,230,0.65)','rgba(100,160,210,0.70)',
          'rgba(80,140,200,0.75)'
        ],
        borderRadius: 4,
      }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{
        label: function(ctx) {{ return ' US$ ' + ctx.parsed.x.toLocaleString('pt-BR', {{minimumFractionDigits:2}}); }}
      }}}} }},
      scales: {{
        x: {{ beginAtZero: true, ticks: {{ callback: function(v) {{ return 'US$ ' + v.toLocaleString('pt-BR'); }} }} }},
        y: {{ grid: {{ display: false }} }}
      }}
    }}
  }});
}})();
</script>
"""


def _build_sms_section(sms_labels, sms_values, total_sms_30d, media_sms_30d):
    if not sms_labels:
        return ""
    import config as _cfg
    days = _cfg.SMS_ANALYSIS_DAYS
    labels_json = json.dumps(sms_labels)
    values_json = json.dumps(sms_values)
    total_html = f"US$ {total_sms_30d:,.2f}" if total_sms_30d is not None else "—"
    media_html = f"US$ {media_sms_30d:,.2f}" if media_sms_30d is not None else "—"
    return f"""
<section class="card">
  <h2>AWS End User Messaging — últimos {days} dias</h2>
  <div class="kpi-grid kpi-small">
    <div class="kpi-card"><div class="kpi-label">Total {days} dias</div><div class="kpi-value">{total_html}</div></div>
    <div class="kpi-card"><div class="kpi-label">Média diária ({days}d)</div><div class="kpi-value">{media_html}</div></div>
  </div>
  <div class="chart-container chart-medium"><canvas id="smsChart"></canvas></div>
</section>
<script>
(function() {{
  var ctx = document.getElementById('smsChart').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: {labels_json},
      datasets: [{{
        label: 'SMS (US$)',
        data: {values_json},
        borderColor: 'rgba(192,29,38,1)',
        backgroundColor: 'rgba(192,29,38,0.08)',
        tension: 0.3,
        pointBackgroundColor: 'rgba(192,29,38,1)',
        fill: true,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{
        label: function(ctx) {{ return ' US$ ' + ctx.parsed.y.toLocaleString('pt-BR', {{minimumFractionDigits:2}}); }}
      }}}} }},
      scales: {{
        y: {{ beginAtZero: false, ticks: {{ callback: function(v) {{ return 'US$ ' + v.toLocaleString('pt-BR'); }} }} }}
      }}
    }}
  }});
}})();
</script>
"""


def _build_daily_top_services_section(daily_top_services):
    if not daily_top_services:
        return ""

    tabs_nav = ""
    tabs_content = ""
    for i, (date_str, services) in enumerate(daily_top_services.items()):
        active = "active" if i == 0 else ""
        tabs_nav += f'<button class="day-tab {active}" data-day="{_esc(date_str)}">{_esc(date_str)}</button>\n'
        rows = ""
        for j, (svc, cost) in enumerate(services, start=1):
            rows += f"<tr><td>{j}</td><td>{_esc(str(svc))}</td><td>US$ {float(cost):,.2f}</td></tr>\n"
        tabs_content += f"""
<div id="day-{_esc(date_str)}" class="day-panel {active}">
  <table class="data-table">
    <thead><tr><th>#</th><th>Serviço</th><th>Custo US$</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
"""

    return f"""
<section class="card">
  <h2>Top serviços por dia na janela</h2>
  <div class="day-tabs">{tabs_nav}</div>
  <div class="day-panels">{tabs_content}</div>
</section>
<script>
(function() {{
  document.querySelectorAll('.day-tab').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      document.querySelectorAll('.day-tab').forEach(function(b) {{ b.classList.remove('active'); }});
      document.querySelectorAll('.day-panel').forEach(function(p) {{ p.classList.remove('active'); }});
      btn.classList.add('active');
      document.getElementById('day-' + btn.dataset.day).classList.add('active');
    }});
  }});
}})();
</script>
"""


def _build_ai_tab(ai_data):
    """Build the HTML content for the AI analysis tab."""
    if not ai_data:
        return """
<div class="card empty-state">
  <svg viewBox="0 0 64 64" width="48" height="48" fill="none" stroke="#c0c0c0" stroke-width="2">
    <circle cx="32" cy="32" r="28"/><line x1="32" y1="20" x2="32" y2="36"/><circle cx="32" cy="44" r="2" fill="#c0c0c0"/>
  </svg>
  <p>Análise via Bedrock não disponível para este relatório.</p>
  <p class="hint">Execute com <code>--enable-bedrock</code> para gerar a análise de IA.</p>
</div>
"""

    # Classification summary
    counts = {"anomalia real": 0, "desvio esperado": 0, "efeito em cascata": 0}
    for driver in ai_data.get("drivers", []):
        key = (driver.get("classification") or "").strip().lower()
        if key in counts:
            counts[key] += 1

    summary_cards = f"""
<div class="classification-summary">
  <div class="cls-card cls-anomalia">
    <div class="cls-label">ANOMALIA REAL</div>
    <div class="cls-count">{counts['anomalia real']}</div>
  </div>
  <div class="cls-card cls-esperado">
    <div class="cls-label">DESVIO ESPERADO</div>
    <div class="cls-count">{counts['desvio esperado']}</div>
  </div>
  <div class="cls-card cls-cascata">
    <div class="cls-label">EFEITO EM CASCATA</div>
    <div class="cls-count">{counts['efeito em cascata']}</div>
  </div>
</div>
"""

    # Executive summary
    exec_html = ""
    exec_items = ai_data.get("executive_summary", [])
    if exec_items:
        items_html = "".join(f"<li>{_inline_md(item)}</li>" for item in exec_items)
        exec_html = f"""
<section class="card">
  <h2>Resumo Executivo</h2>
  <ul class="exec-list">{items_html}</ul>
</section>
"""

    # Driver cards
    drivers_html = ""
    for driver in ai_data.get("drivers", []):
        badge = _classification_badge(driver.get("classification", ""))
        title_html = _inline_md(driver.get("title", ""))
        causa_html = _inline_md(driver.get("causa", ""))
        ev_html = _inline_md(driver.get("evidencias", ""))
        conf_html = _esc(driver.get("confianca", ""))
        conf_block = f'<p class="confianca"><strong>Confiança:</strong> {conf_html}</p>' if conf_html else ""

        causa_block = f'<div class="driver-section"><strong>Causa provável</strong><p>{causa_html}</p></div>' if causa_html else ""
        ev_block = f'<div class="driver-section"><strong>Evidências</strong><p>{ev_html}</p></div>' if ev_html else ""

        drivers_html += f"""
<div class="driver-card">
  <div class="driver-header">
    {badge}
    <h3 class="driver-title">{title_html}</h3>
  </div>
  <div class="driver-body">
    {causa_block}
    {ev_block}
    {conf_block}
  </div>
</div>
"""

    drivers_section = ""
    if drivers_html:
        drivers_section = f"""
<section class="card">
  <h2>Principais Drivers</h2>
  <div class="drivers-grid">{drivers_html}</div>
</section>
"""

    # Recommendations
    recs_html = ""
    recs = ai_data.get("recommendations", [])
    if recs:
        items = ""
        for i, rec in enumerate(recs, start=1):
            title_html = _esc(rec.get("title", ""))
            body_html = _inline_md(rec.get("body", ""))
            title_part = f"<strong>{i}. {title_html}</strong><br>" if title_html else f"<strong>{i}.</strong> "
            items += f"<li>{title_part}{body_html}</li>\n"
        recs_html = f"""
<section class="card">
  <h2>Recomendações</h2>
  <ol class="rec-list">{items}</ol>
</section>
"""

    return summary_cards + exec_html + drivers_section + recs_html


# ---------------------------------------------------------------------------
# CSS + HTML template
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f4f6f8; color: #2d3748; font-size: 14px; line-height: 1.6; }
a { color: #c01d26; }

/* Header */
.report-header { background: #fff; border-bottom: 3px solid #c01d26; padding: 20px 32px;
  display: flex; align-items: center; gap: 16px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.report-header h1 { font-size: 20px; color: #c01d26; font-weight: 700; flex: 1; }
.report-header .meta { font-size: 12px; color: #718096; }

/* Tabs */
.tab-nav { display: flex; background: #fff; border-bottom: 2px solid #e2e8f0; padding: 0 32px; gap: 4px; }
.tab-btn { padding: 12px 24px; background: none; border: none; border-bottom: 3px solid transparent;
  cursor: pointer; font-size: 14px; font-weight: 600; color: #718096; transition: all .2s; margin-bottom: -2px; }
.tab-btn:hover { color: #c01d26; }
.tab-btn.active { color: #c01d26; border-bottom-color: #c01d26; }

/* Content */
.tab-pane { display: none; padding: 24px 32px; max-width: 1200px; margin: 0 auto; }
.tab-pane.active { display: block; }

/* Cards */
.card { background: #fff; border-radius: 8px; padding: 20px 24px; margin-bottom: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07); }
.card h2 { font-size: 15px; font-weight: 700; color: #c01d26; margin-bottom: 14px;
  padding-bottom: 8px; border-bottom: 1px solid #f0f0f0; }
.card h2 small { font-size: 12px; color: #718096; font-weight: 400; }

/* KPI grid */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px; }
.kpi-grid.kpi-small { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-bottom: 14px; }
.kpi-card { background: #fff; border-radius: 8px; padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07); border-left: 4px solid #c01d26; }
.kpi-label { font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: #718096; margin-bottom: 6px; }
.kpi-value { font-size: 22px; font-weight: 700; color: #2d3748; }
.kpi-value.positive { color: #c01d26; }
.kpi-value.negative { color: #3182ce; }

/* Charts */
.chart-container { position: relative; min-height: 260px; }
.chart-container.chart-medium { min-height: 200px; }

/* Two column layout */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
@media (max-width: 768px) { .two-col { grid-template-columns: 1fr; } }

/* Tables */
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { background: #f7f8fa; text-align: left; padding: 8px 10px;
  font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: #718096;
  border-bottom: 2px solid #e2e8f0; }
.data-table td { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: #fafafa; }

/* Positive/negative values */
.positive { color: #c01d26; font-weight: 600; }
.negative { color: #3182ce; font-weight: 600; }

/* Section labels */
.section-label { font-size: 13px; font-weight: 600; margin-bottom: 10px; }
.section-label.increase { color: #c01d26; }
.section-label.decrease { color: #3182ce; }

/* Day tabs */
.day-tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 14px; }
.day-tab { padding: 5px 12px; background: #f4f6f8; border: 1px solid #e2e8f0;
  border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 500; color: #718096; }
.day-tab.active { background: #c01d26; color: #fff; border-color: #c01d26; }
.day-panel { display: none; }
.day-panel.active { display: block; }

/* Classification summary */
.classification-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 20px; }
.cls-card { border-radius: 8px; padding: 16px 20px; text-align: center; }
.cls-card.cls-anomalia { background: #fff5f5; border: 1px solid #fed7d7; }
.cls-card.cls-esperado  { background: #f0fff4; border: 1px solid #c6f6d5; }
.cls-card.cls-cascata   { background: #ebf8ff; border: 1px solid #bee3f8; }
.cls-label { font-size: 11px; text-transform: uppercase; letter-spacing: .5px; font-weight: 700; margin-bottom: 6px; }
.cls-card.cls-anomalia .cls-label { color: #c53030; }
.cls-card.cls-esperado  .cls-label { color: #276749; }
.cls-card.cls-cascata   .cls-label { color: #2b6cb0; }
.cls-count { font-size: 28px; font-weight: 800; }
.cls-card.cls-anomalia .cls-count { color: #c53030; }
.cls-card.cls-esperado  .cls-count { color: #276749; }
.cls-card.cls-cascata   .cls-count { color: #2b6cb0; }

/* Badges */
.badge { display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 11px; font-weight: 700; letter-spacing: .4px; text-transform: uppercase; }
.badge-anomalia { background: #fff5f5; color: #c53030; border: 1px solid #fed7d7; }
.badge-esperado  { background: #f0fff4; color: #276749; border: 1px solid #c6f6d5; }
.badge-cascata   { background: #ebf8ff; color: #2b6cb0; border: 1px solid #bee3f8; }

/* Driver cards */
.drivers-grid { display: grid; gap: 14px; }
.driver-card { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.driver-header { padding: 12px 16px; background: #fafbfc; border-bottom: 1px solid #e2e8f0;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.driver-title { font-size: 14px; font-weight: 600; color: #2d3748; flex: 1; min-width: 200px; }
.driver-body { padding: 12px 16px; }
.driver-section { margin-bottom: 10px; }
.driver-section strong { font-size: 12px; text-transform: uppercase; letter-spacing: .4px;
  color: #718096; display: block; margin-bottom: 4px; }
.driver-section p { font-size: 13px; color: #4a5568; }
.confianca { font-size: 12px; color: #718096; padding-top: 8px;
  border-top: 1px dashed #e2e8f0; margin-top: 8px; }
.confianca code { background: #f4f6f8; padding: 1px 5px; border-radius: 3px; font-size: 11px; }

/* Executive list */
.exec-list { padding-left: 0; list-style: none; }
.exec-list li { padding: 7px 0 7px 18px; border-bottom: 1px solid #f4f6f8;
  position: relative; font-size: 13px; }
.exec-list li:last-child { border-bottom: none; }
.exec-list li::before { content: "▸"; color: #c01d26; position: absolute; left: 0; }

/* Recommendations */
.rec-list { padding-left: 0; list-style: none; counter-reset: rec-counter; }
.rec-list li { padding: 10px 0 10px 28px; border-bottom: 1px solid #f4f6f8;
  position: relative; font-size: 13px; counter-increment: rec-counter; }
.rec-list li:last-child { border-bottom: none; }
.rec-list li::before { content: counter(rec-counter); background: #c01d26; color: #fff;
  width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 700; position: absolute; left: 0; top: 10px; }

/* Empty state */
.empty-state { text-align: center; padding: 48px 24px; color: #a0aec0; }
.empty-state p { margin: 12px 0 0; font-size: 15px; }
.empty-state .hint { font-size: 13px; color: #cbd5e0; margin-top: 8px; }
.empty-state svg { margin: 0 auto; }
code { background: #f4f6f8; padding: 2px 6px; border-radius: 4px;
  font-family: 'Courier New', monospace; font-size: 12px; }
"""

_CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"


def _build_html(
    account_label, ultimo_dia, data_inicio, data_fim,
    custo_medio, custo_ultimo_dia, variacao_media,
    daily_labels, daily_values,
    aumentaram, reduziram,
    top_costs,
    sms_labels, sms_values, total_sms_30d, media_sms_30d,
    daily_top_services,
    ai_data,
):
    header_label = _esc(account_label or "AWS")
    meta_label = f"Janela: {_esc(data_inicio)} a {_esc(data_fim)} | Dia de referência: {_esc(ultimo_dia)}"

    tab1 = (
        _build_kpi_cards(custo_medio, custo_ultimo_dia, variacao_media, ultimo_dia) +
        _build_daily_chart_section(daily_labels, daily_values) +
        _build_variation_section(aumentaram, reduziram, data_inicio, data_fim) +
        _build_top_services_section(top_costs, ultimo_dia) +
        _build_sms_section(sms_labels, sms_values, total_sms_30d, media_sms_30d) +
        _build_daily_top_services_section(daily_top_services)
    )
    tab2 = _build_ai_tab(ai_data)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FinOps AWS — {header_label}</title>
  <script src="{_CHARTJS_CDN}"></script>
  <style>{_CSS}</style>
</head>
<body>

<header class="report-header">
  <h1>Relatório FinOps AWS</h1>
  <div>
    <div style="font-weight:600;color:#2d3748">{header_label}</div>
    <div class="meta">{meta_label}</div>
  </div>
</header>

<nav class="tab-nav">
  <button class="tab-btn active" data-tab="overview">&#128200; Visão Geral</button>
  <button class="tab-btn" data-tab="ai">&#129302; Análise de Anomalias</button>
</nav>

<div id="tab-overview" class="tab-pane active">{tab1}</div>
<div id="tab-ai" class="tab-pane">{tab2}</div>

<script>
document.querySelectorAll('.tab-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.tab-pane').forEach(function(p) {{ p.classList.remove('active'); }});
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }});
}});
</script>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_html_report(
    data_inicio, data_fim, ultimo_dia, custo_medio, variacao_media,
    aumentaram, reduziram, top_costs, daily_costs=None, sms_por_dia=None,
    total_sms_30d=None, media_sms_30d=None, enriched_anomalies=None,
    daily_top_services=None, account_label=None, ai_analysis=None,
    custo_ultimo_dia=None,
):
    """
    Generate a two-tab HTML report and write it to the output directory.
    Returns the path to the generated file.
    """
    output_dir = utils.ensure_output_dir()
    output_html = os.path.join(output_dir, utils.get_output_filename("aws-relatorio-custos", "html"))

    # Prepare chart data
    daily_labels, daily_values = [], []
    for date_str, cost in (daily_costs or []):
        daily_labels.append(str(date_str))
        daily_values.append(round(float(cost), 2))

    sms_labels, sms_values = [], []
    if sms_por_dia is not None:
        for _, row in sms_por_dia.iterrows():
            sms_labels.append(str(row["Data"]))
            sms_values.append(round(float(row["Custo($)"]), 2))

    # Derive custo_ultimo_dia from daily_costs if not explicitly provided
    if custo_ultimo_dia is None and daily_costs:
        ultimo_day_costs = [c for d, c in daily_costs if str(d) == str(ultimo_dia)]
        custo_ultimo_dia = float(ultimo_day_costs[0]) if ultimo_day_costs else 0.0

    ai_data = _parse_ai_analysis(ai_analysis)

    html_content = _build_html(
        account_label=account_label,
        ultimo_dia=ultimo_dia,
        data_inicio=data_inicio,
        data_fim=data_fim,
        custo_medio=custo_medio,
        custo_ultimo_dia=custo_ultimo_dia or 0.0,
        variacao_media=variacao_media,
        daily_labels=daily_labels,
        daily_values=daily_values,
        aumentaram=aumentaram,
        reduziram=reduziram,
        top_costs=top_costs,
        sms_labels=sms_labels,
        sms_values=sms_values,
        total_sms_30d=total_sms_30d,
        media_sms_30d=media_sms_30d,
        daily_top_services=daily_top_services,
        ai_data=ai_data,
    )

    with open(output_html, "w", encoding="utf-8") as fh:
        fh.write(html_content)

    print(f"Relatório HTML salvo em: {output_html}")
    return output_html
