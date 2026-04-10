"""
TXT report renderer
"""

import os
import config
import utils


def _build_daily_cost_chart(daily_costs):
    if not daily_costs:
        return []

    max_cost = max(cost for _, cost in daily_costs) or 1
    max_bar_width = 40
    lines = []
    for date_value, cost in daily_costs:
        bar_width = max(1, round((cost / max_cost) * max_bar_width))
        bar = "#" * bar_width
        lines.append(f"{date_value}: US$ {cost:,.2f} | {bar}")
    return lines


def write_bedrock_context_txt(base_txt_file, ultimo_dia, enriched_anomalies):
    """
    Write a dedicated TXT file with anomaly/resource context for Bedrock troubleshooting.
    """
    output_txt = base_txt_file.replace(".txt", "_bedrock_context.txt")
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("Anomalias correlacionadas para Bedrock:\n\n")
        for anomaly in enriched_anomalies or []:
            f.write(
                f"- {anomaly['service']} | {anomaly['usage_type']} | "
                f"dia {ultimo_dia}: US$ {anomaly['cost_today']:,.2f} | "
                f"media 7d: US$ {anomaly['avg_7d']:,.2f} | "
                f"delta: {anomaly['delta_pct']:,.2f}%\n"
            )
            for resource in anomaly.get("resources", []):
                resource_id = resource.get("resource_id") or "nao identificado"
                f.write(
                    f"  recurso: {resource.get('resource_type')} -> {resource_id} "
                    f"(confianca {resource.get('confidence', 'low')})\n"
                )
        f.write("\n")

    print(f"Bedrock context TXT salvo em: {output_txt}")
    return output_txt


def write_txt_report(data_inicio, data_fim, ultimo_dia, custo_medio, variacao_media,
                     aumentaram, reduziram, top_costs, daily_costs=None, sms_por_dia=None,
                     total_sms_7d=None, media_sms_7d=None, enriched_anomalies=None,
                     daily_top_services=None, account_label=None):
    """
    Write TXT report
    """
    output_dir = utils.ensure_output_dir()
    output_txt = os.path.join(output_dir, utils.get_output_filename("relatorio_custos", "txt"))

    def format_row(svc, var_usd, var_pct):
        return f"{svc.ljust(28)} {str(var_usd).rjust(10)} {str(var_pct).rjust(10)}"

    with open(output_txt, "w", encoding="utf-8") as f:
        if account_label:
            f.write(f"Custo de Cloud AWS conta {account_label}\n\n")
        f.write(f"Custo médio por dia: US$ {custo_medio:,.2f}\n\n")
        if daily_costs:
            f.write("Custos por dia na janela:\n\n")
            for line in _build_daily_cost_chart(daily_costs):
                f.write(f"{line}\n")
            f.write("\n")
        f.write(f"Variação média do custo em relação à média entre os dias {data_inicio} e {data_fim}: US$ {variacao_media:,.2f}\n")
        f.write("Tendência de estabilidade diária próxima de 0%.\n\n")

        # Aumentaram
        f.write(f"Serviços que aumentaram o custo em relação à média entre os dias {data_inicio} e {data_fim} US$:\n\n")
        f.write(format_row("Serviço", "Variação US$", "Variação %") + "\n")
        for svc, row in aumentaram.iterrows():
            f.write(format_row(
                svc.replace("($)", ""),
                f"+{row['Variação US$']:.2f}",
                f"+{row['Variação %']:.2f}%"
            ) + "\n")

        # Reduziram
        f.write(f"\nServiços que reduziram o custo em relação à média entre os dias {data_inicio} e {data_fim} US$:\n\n")
        f.write(format_row("Serviço", "Variação US$", "Variação %") + "\n")
        for svc, row in reduziram.head(5).iterrows():
            f.write(format_row(
                svc.replace("($)", ""),
                f"{row['Variação US$']:.2f}",
                f"{row['Variação %']:.2f}%"
            ) + "\n")

        # TOP services
        f.write(f"\nTOP {config.TOP_N_SERVICES} serviços em {ultimo_dia} por custo US$ (maiores custos):\n\n")
        for i, (svc, val) in enumerate(top_costs.items(), start=1):
            f.write(f"{i}. {svc.replace('($)','')}: US$ {val:,.2f}\n")

        # SMS if available
        if sms_por_dia is not None:
            f.write(f"\n\nAWS End User Messaging – Últimos 7 dias:\n\n")
            for _, row in sms_por_dia.iterrows():
                f.write(f"{row['Data']}: US$ {row['Custo($)']:,.2f}\n")
            f.write(f"\nTotal últimos 7 dias: US$ {total_sms_7d:,.2f}\n")
            f.write(f"Média diária (7 dias): US$ {media_sms_7d:,.2f}\n")

        if daily_top_services:
            f.write(f"\n\nTop {config.TOP_N_DAILY_SERVICES} serviços por dia na janela:\n\n")
            for date_value, services in daily_top_services.items():
                f.write(f"{date_value}:\n")
                for index, (service, cost) in enumerate(services, start=1):
                    f.write(f"  {index}. {service}: US$ {cost:,.2f}\n")
                f.write("\n")

    print(f"Relatório TXT salvo em: {output_txt}")
    return output_txt
