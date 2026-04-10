"""
Correlate cost anomalies with AWS resources and prepare Bedrock payloads.
"""

import config
from mappings.correlation_rules import find_rule_for_service
from collectors import resource_discovery


def enrich_anomalies(anomalies, start_date, end_date, anchor_day, enable_aws_lookup=True):
    """
    Attach correlation rules, candidate AWS resources and metrics to anomalies.
    """
    enriched = []
    for anomaly in anomalies:
        rule = find_rule_for_service(anomaly["service"], anomaly.get("usage_type"))
        resources = resource_discovery.discover_and_enrich_resources(
            anomaly=anomaly,
            rule=rule,
            start_date=start_date,
            end_date=end_date,
            enable_aws_lookup=enable_aws_lookup,
        )

        enriched.append(
            {
                **anomaly,
                "anchor_day": anchor_day,
                "resource_type": rule.get("resource_type") if rule else None,
                "possible_impacted_services": rule.get("possible_impacted_services", []) if rule else [],
                "hypothesis": rule.get("hypothesis") if rule else None,
                "resources": resources,
            }
        )
    return enriched


def build_bedrock_payload(
    data_inicio,
    data_fim,
    ultimo_dia,
    custo_medio,
    custo_ultimo_dia,
    variacao_media,
    variacao_media_pct,
    daily_costs,
    top_costs,
    enriched_anomalies,
    contexto_operacional,
    business_event_calendar=None,
):
    """
    Prepare a structured payload for causal FinOps analysis in Bedrock.
    """
    selected_anomalies = enriched_anomalies[: config.BEDROCK_MAX_ANALYSIS_ANOMALIES]

    return {
        "period": {
            "start": data_inicio,
            "end": data_fim,
            "anchor_day": ultimo_dia,
            "reference_day": ultimo_dia,
        },
        "summary": {
            "average_cost_7d": float(round(custo_medio, 4)),
            "cost_anchor_day": float(round(custo_ultimo_dia, 4)),
            "cost_reference_day": float(round(custo_ultimo_dia, 4)),
            "delta_usd": float(round(variacao_media, 4)),
            "delta_pct": float(round(variacao_media_pct, 2)),
        },
        "daily_total_costs": [
            {"date": str(date_value), "cost_usd": float(round(float(cost), 4))}
            for date_value, cost in daily_costs
        ],
        "contexto_operacional": [line.strip() for line in contexto_operacional.splitlines() if line.strip()],
        "business_event_calendar": business_event_calendar or {},
        "top_services": [{"service": service, "cost_usd": float(round(float(cost), 4))} for service, cost in top_costs.items()],
        "anomaly_selection": {
            "selected_for_ai": len(selected_anomalies),
            "total_available": len(enriched_anomalies),
            "selection_rule": "Top anomalies already sorted upstream; payload compacted before sending to Bedrock.",
        },
        "anomalies": [_compact_anomaly_for_bedrock(anomaly) for anomaly in selected_anomalies],
    }


def _compact_anomaly_for_bedrock(anomaly):
    """
    Remove low-signal verbosity from anomaly payloads before sending them to the LLM.
    """
    return {
        "service": anomaly.get("service"),
        "usage_type": anomaly.get("usage_type"),
        "complementary_usage_types": anomaly.get("complementary_usage_types", []),
        "anchor_day": anomaly.get("anchor_day"),
        "reference_day": anomaly.get("anchor_day"),
        "cost_today": anomaly.get("cost_today"),
        "cost_reference_day": anomaly.get("cost_today"),
        "avg_7d": anomaly.get("avg_7d"),
        "delta_usd": anomaly.get("delta_usd"),
        "delta_pct": anomaly.get("delta_pct"),
        "days_present": anomaly.get("days_present"),
        "series": anomaly.get("series", []),
        "resource_type": anomaly.get("resource_type"),
        "possible_impacted_services": anomaly.get("possible_impacted_services", []),
        "hypothesis": anomaly.get("hypothesis"),
        "resources": [_compact_resource_for_bedrock(resource) for resource in anomaly.get("resources", [])],
    }


def _compact_resource_for_bedrock(resource):
    """
    Keep the best signal from resources and metric summaries without sending full metric series.
    """
    return {
        "resource_type": resource.get("resource_type"),
        "resource_id": resource.get("resource_id"),
        "resource_arn": resource.get("resource_arn"),
        "tags": resource.get("tags", {}),
        "derived_context": resource.get("derived_context", {}),
        "confidence": resource.get("confidence"),
        "possible_impacted_services": resource.get("possible_impacted_services", []),
        "hypothesis": resource.get("hypothesis"),
        "notes": resource.get("notes", []),
        "query_activity": resource.get("query_activity", []),
        "athena_query_activity": resource.get("athena_query_activity", []),
        "metrics": {
            metric_name: _compact_metric_for_bedrock(metric_name, metric_data)
            for metric_name, metric_data in resource.get("metrics", {}).items()
        },
    }


def _compact_metric_for_bedrock(metric_name, metric_data):
    compact_metric = {
        "stat": metric_data.get("stat"),
        "today": metric_data.get("today"),
        "avg_7d": metric_data.get("avg_7d"),
        "delta": metric_data.get("delta"),
        "delta_pct": metric_data.get("delta_pct"),
        "peak_date": metric_data.get("peak_date"),
        "peak_value": metric_data.get("peak_value"),
        "min_date": metric_data.get("min_date"),
        "min_value": metric_data.get("min_value"),
    }

    if metric_name in config.BEDROCK_PRIORITY_METRIC_SERIES:
        compact_metric["series"] = metric_data.get("series", [])

    return compact_metric
