"""
Correlate cost anomalies with AWS resources and prepare Bedrock payloads.
"""

from concurrent.futures import ThreadPoolExecutor

import config
from mappings.correlation_rules import find_rule_for_service
from collectors import resource_discovery


def _is_s3_cost_anomaly(anomaly):
    service_name = (anomaly.get("service") or "").lower()
    return "simple storage service" in service_name or service_name == "s3"


def _is_guardduty_s3_data_events_anomaly(anomaly):
    service_name = (anomaly.get("service") or "").lower()
    usage_type = (anomaly.get("usage_type") or "").lower()
    return "guardduty" in service_name and "paids3dataeventsanalyzed" in usage_type


def _build_guardduty_correlation(guardduty_anomaly):
    if not guardduty_anomaly:
        return {
            "status": "not_present_in_selected_anomalies",
        }

    delta_pct = float(guardduty_anomaly.get("delta_pct", 0.0) or 0.0)
    delta_usd = float(guardduty_anomaly.get("delta_usd", 0.0) or 0.0)
    if delta_usd > 0 and delta_pct > 0:
        signal = "supports_s3_hypothesis"
    elif delta_usd < 0 and delta_pct < 0:
        signal = "does_not_reinforce"
    else:
        signal = "mixed"

    return {
        "status": "present",
        "signal": signal,
        "service": guardduty_anomaly.get("service"),
        "usage_type": guardduty_anomaly.get("usage_type"),
        "reference_day": guardduty_anomaly.get("anchor_day"),
        "cost_reference_day": guardduty_anomaly.get("cost_today"),
        "avg_7d": guardduty_anomaly.get("avg_7d"),
        "delta_usd": guardduty_anomaly.get("delta_usd"),
        "delta_pct": guardduty_anomaly.get("delta_pct"),
    }


def _attach_s3_guardduty_correlations(enriched_anomalies):
    guardduty_anomaly = next(
        (item for item in enriched_anomalies if _is_guardduty_s3_data_events_anomaly(item)),
        None,
    )
    guardduty_correlation = _build_guardduty_correlation(guardduty_anomaly)

    enriched = []
    for anomaly in enriched_anomalies:
        if _is_s3_cost_anomaly(anomaly):
            enriched.append(
                {
                    **anomaly,
                    "guardduty_correlation": guardduty_correlation,
                }
            )
            continue
        enriched.append(anomaly)
    return enriched


def _enrich_single_anomaly(anomaly, start_date, end_date, anchor_day, enable_aws_lookup):
    """
    Enrich one anomaly end-to-end so parallel workers keep the current decision flow intact.
    """
    rule = find_rule_for_service(anomaly["service"], anomaly.get("usage_type"))
    resources = resource_discovery.discover_and_enrich_resources(
        anomaly=anomaly,
        rule=rule,
        start_date=start_date,
        end_date=end_date,
        enable_aws_lookup=enable_aws_lookup,
    )

    return {
        **anomaly,
        "anchor_day": anchor_day,
        "resource_type": rule.get("resource_type") if rule else None,
        "possible_impacted_services": rule.get("possible_impacted_services", []) if rule else [],
        "hypothesis": rule.get("hypothesis") if rule else None,
        "resources": resources,
    }


def enrich_anomalies(anomalies, start_date, end_date, anchor_day, enable_aws_lookup=True):
    """
    Attach correlation rules, candidate AWS resources and metrics to anomalies.
    """
    # Keep a small pool to reduce wall time without overwhelming AWS APIs or changing ranking order.
    with ThreadPoolExecutor(max_workers=2) as executor:
        enriched = list(
            executor.map(
                lambda anomaly: _enrich_single_anomaly(
                    anomaly,
                    start_date=start_date,
                    end_date=end_date,
                    anchor_day=anchor_day,
                    enable_aws_lookup=enable_aws_lookup,
                ),
                anomalies,
            )
        )
    return _attach_s3_guardduty_correlations(enriched)


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
        "guardduty_correlation": anomaly.get("guardduty_correlation"),
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
        "observed_instance_types": resource.get("derived_context", {}).get("observed_instance_types", []),
        "confidence": resource.get("confidence"),
        "possible_impacted_services": resource.get("possible_impacted_services", []),
        "hypothesis": resource.get("hypothesis"),
        "notes": resource.get("notes", []),
        "query_activity": resource.get("query_activity", []),
        "athena_query_activity": resource.get("athena_query_activity", []),
        "cloudtrail_s3_activity": resource.get("cloudtrail_s3_activity"),
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
