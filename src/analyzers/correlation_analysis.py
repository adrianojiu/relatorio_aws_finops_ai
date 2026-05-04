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


def _extract_s3_cloudtrail_tier_context(resources):
    """
    Summarize whether any S3 candidate brought CloudTrail evidence relevant to the anomaly.
    """
    if not resources:
        return {
            "status": "not_collected",
            "summary": "Nenhum recurso S3 candidato foi enriquecido com CloudTrail para esta anomalia.",
        }

    matched_contexts = []
    no_match_contexts = []
    tier_change_matched_contexts = []
    for resource in resources:
        cloudtrail_activity = resource.get("cloudtrail_s3_activity")
        if not cloudtrail_activity:
            continue
        if cloudtrail_activity.get("lookup_status") == "matched":
            tier_change_evidence = cloudtrail_activity.get("tier_change_evidence") or {}
            matched_contexts.append(
                {
                    "bucket": resource.get("resource_id"),
                    "top_event_names": cloudtrail_activity.get("top_event_names", []),
                    "top_usernames": cloudtrail_activity.get("top_usernames", []),
                    "matched_events_count": cloudtrail_activity.get("matched_events_count"),
                }
            )
            if tier_change_evidence.get("status") == "matched":
                tier_change_matched_contexts.append(
                    {
                        "bucket": resource.get("resource_id"),
                        "matched_events_count": tier_change_evidence.get("matched_events_count"),
                        "top_event_names": tier_change_evidence.get("top_event_names", []),
                        "sample_matches": tier_change_evidence.get("sample_matches", []),
                    }
                )
        elif cloudtrail_activity.get("lookup_status") == "no_matches":
            no_match_contexts.append(resource.get("resource_id"))

    if tier_change_matched_contexts:
        return {
            "status": "matched",
            "summary": "CloudTrail trouxe eventos compativeis com mudanca de tier/classe em ao menos um bucket S3 candidato.",
            "matched_buckets": matched_contexts,
            "tier_change_matched_buckets": tier_change_matched_contexts,
        }
    if matched_contexts:
        return {
            "status": "matched",
            "summary": "CloudTrail trouxe eventos para ao menos um bucket S3 candidato desta anomalia, mas sem sinal direto de tier/classe.",
            "matched_buckets": matched_contexts,
        }
    if no_match_contexts:
        return {
            "status": "no_matches",
            "summary": "CloudTrail foi consultado para buckets S3 candidatos, mas nao retornou eventos relevantes nas datas-alvo.",
            "queried_buckets_without_matches": no_match_contexts,
        }
    return {
        "status": "not_collected",
        "summary": "Nenhum contexto adicional de CloudTrail foi anexado aos buckets S3 candidatos desta anomalia.",
    }


def _attach_s3_tier_cloudtrail_context(enriched_anomalies):
    """
    Add CloudTrail lookup status into the S3 tier verdict so the LLM can stay consistent.
    """
    updated = []
    for anomaly in enriched_anomalies:
        if not _is_s3_cost_anomaly(anomaly):
            updated.append(anomaly)
            continue

        tier_change_analysis = dict(anomaly.get("s3_tier_change_analysis") or {})
        s3_driver_analysis = dict(anomaly.get("s3_driver_analysis") or {})
        if tier_change_analysis:
            cloudtrail_context = _extract_s3_cloudtrail_tier_context(
                anomaly.get("resources") or []
            )
            tier_change_analysis["cloudtrail_context"] = cloudtrail_context
            if cloudtrail_context.get("status") == "matched" and cloudtrail_context.get("tier_change_matched_buckets"):
                tier_change_analysis["status"] = "supported"
                tier_change_analysis["summary"] = (
                    "Ha evidencia de CloudTrail compativel com mudanca de classe/tier em bucket S3 candidato."
                )
                if s3_driver_analysis:
                    s3_driver_analysis["confidence"] = "high"
                    s3_driver_analysis["narrative_summary"] = (
                        (s3_driver_analysis.get("narrative_summary") or "").split(" Mudanca de tier/classe")[0].strip()
                        + " Mudanca de tier/classe aparece como componente principal ou claramente corroborado."
                    ).strip()

        updated.append(
            {
                **anomaly,
                "s3_tier_change_analysis": tier_change_analysis or anomaly.get("s3_tier_change_analysis"),
                "s3_driver_analysis": s3_driver_analysis or anomaly.get("s3_driver_analysis"),
            }
        )
    return updated


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
    enriched = _attach_s3_guardduty_correlations(enriched)
    return _attach_s3_tier_cloudtrail_context(enriched)


def _classify_s3_usage_type_for_period_context(usage_type):
    """
    Keep a lightweight S3 family hint in the broad period context block.
    """
    usage_type_text = str(usage_type or "").lower()
    if "request" in usage_type_text:
        return "s3_requests"
    if any(marker in usage_type_text for marker in ["transition", "tiering", "intelligent-tiering"]):
        return "s3_storage_class_transition"
    if any(marker in usage_type_text for marker in ["retrieval", "restore"]):
        return "s3_retrieval_restore"
    if "earlydelete" in usage_type_text:
        return "s3_early_delete"
    if any(marker in usage_type_text for marker in ["datatransfer", "bandwidth", "bytes"]):
        return "s3_data_transfer"
    if "timedstorage" in usage_type_text or "storage" in usage_type_text:
        return "s3_storage"
    return "s3_other"


def _build_top_services_period_context(df_service_period=None, reference_day=None):
    if df_service_period is None or df_service_period.empty:
        return []

    period_days = max(df_service_period["Data"].astype(str).nunique(), 1)
    grouped = (
        df_service_period.groupby("Serviço", as_index=False)["Custo($)"]
        .agg(total_period_usd="sum")
    )
    if reference_day:
        reference_costs = (
            df_service_period[df_service_period["Data"] == reference_day]
            .groupby("Serviço", as_index=False)["Custo($)"]
            .sum()
            .rename(columns={"Custo($)": "reference_day_cost_usd"})
        )
        grouped = grouped.merge(reference_costs, on="Serviço", how="left")
    else:
        grouped["reference_day_cost_usd"] = 0.0

    grouped["reference_day_cost_usd"] = grouped["reference_day_cost_usd"].fillna(0.0)
    # Divide by the full analyzed window so sparse rows do not look artificially "normal".
    grouped["avg_daily_usd"] = grouped["total_period_usd"] / period_days
    grouped["delta_vs_avg_usd"] = grouped["reference_day_cost_usd"] - grouped["avg_daily_usd"]
    grouped = grouped.sort_values(["total_period_usd", "reference_day_cost_usd"], ascending=False)
    grouped = grouped.head(config.TOP_N_PERIOD_CONTEXT_ITEMS)

    return [
        {
            "service": row["Serviço"],
            "total_period_usd": float(round(row["total_period_usd"], 4)),
            "avg_daily_usd": float(round(row["avg_daily_usd"], 4)),
            "reference_day_cost_usd": float(round(row["reference_day_cost_usd"], 4)),
            "delta_vs_avg_usd": float(round(row["delta_vs_avg_usd"], 4)),
        }
        for _, row in grouped.iterrows()
    ]


def _build_top_usage_types_period_context(timeseries_period_df=None, reference_day=None):
    if timeseries_period_df is None or timeseries_period_df.empty:
        return []

    period_days = max(timeseries_period_df["Data"].astype(str).nunique(), 1)
    grouped = (
        timeseries_period_df.groupby(["Serviço", "UsageType"], as_index=False)["Custo($)"]
        .agg(total_period_usd="sum")
    )
    if reference_day:
        reference_costs = (
            timeseries_period_df[timeseries_period_df["Data"] == reference_day]
            .groupby(["Serviço", "UsageType"], as_index=False)["Custo($)"]
            .sum()
            .rename(columns={"Custo($)": "reference_day_cost_usd"})
        )
        grouped = grouped.merge(reference_costs, on=["Serviço", "UsageType"], how="left")
    else:
        grouped["reference_day_cost_usd"] = 0.0

    grouped["reference_day_cost_usd"] = grouped["reference_day_cost_usd"].fillna(0.0)
    # Use the full window as denominator so one-day charges remain visible as outliers.
    grouped["avg_daily_usd"] = grouped["total_period_usd"] / period_days
    grouped["delta_vs_avg_usd"] = grouped["reference_day_cost_usd"] - grouped["avg_daily_usd"]
    grouped = grouped.sort_values(["total_period_usd", "reference_day_cost_usd"], ascending=False)
    grouped = grouped.head(config.TOP_N_PERIOD_CONTEXT_ITEMS)

    result = []
    for _, row in grouped.iterrows():
        usage_type_context = None
        if str(row["Serviço"]) == "Amazon Simple Storage Service":
            usage_type_context = _classify_s3_usage_type_for_period_context(row["UsageType"])
        result.append(
            {
                "service": row["Serviço"],
                "usage_type": row["UsageType"],
                "usage_type_context": usage_type_context,
                "total_period_usd": float(round(row["total_period_usd"], 4)),
                "avg_daily_usd": float(round(row["avg_daily_usd"], 4)),
                "reference_day_cost_usd": float(round(row["reference_day_cost_usd"], 4)),
                "delta_vs_avg_usd": float(round(row["delta_vs_avg_usd"], 4)),
            }
        )
    return result


def _build_top_api_operations_period_context(operation_timeseries_period_df=None, reference_day=None):
    if operation_timeseries_period_df is None or operation_timeseries_period_df.empty:
        return []

    period_days = max(operation_timeseries_period_df["Data"].astype(str).nunique(), 1)
    grouped = (
        operation_timeseries_period_df.groupby(["Serviço", "ApiOperation"], as_index=False)["Custo($)"]
        .agg(total_period_usd="sum")
    )
    if reference_day:
        reference_costs = (
            operation_timeseries_period_df[operation_timeseries_period_df["Data"] == reference_day]
            .groupby(["Serviço", "ApiOperation"], as_index=False)["Custo($)"]
            .sum()
            .rename(columns={"Custo($)": "reference_day_cost_usd"})
        )
        grouped = grouped.merge(reference_costs, on=["Serviço", "ApiOperation"], how="left")
    else:
        grouped["reference_day_cost_usd"] = 0.0

    grouped["reference_day_cost_usd"] = grouped["reference_day_cost_usd"].fillna(0.0)
    # Keep period context numerically consistent with the anomaly window logic.
    grouped["avg_daily_usd"] = grouped["total_period_usd"] / period_days
    grouped["delta_vs_avg_usd"] = grouped["reference_day_cost_usd"] - grouped["avg_daily_usd"]
    grouped = grouped.sort_values(["total_period_usd", "reference_day_cost_usd"], ascending=False)
    grouped = grouped.head(config.TOP_N_PERIOD_CONTEXT_ITEMS)

    return [
        {
            "service": row["Serviço"],
            "api_operation": row["ApiOperation"],
            "total_period_usd": float(round(row["total_period_usd"], 4)),
            "avg_daily_usd": float(round(row["avg_daily_usd"], 4)),
            "reference_day_cost_usd": float(round(row["reference_day_cost_usd"], 4)),
            "delta_vs_avg_usd": float(round(row["delta_vs_avg_usd"], 4)),
        }
        for _, row in grouped.iterrows()
    ]


def _build_period_cost_context(df_service_period=None, timeseries_period_df=None, operation_timeseries_period_df=None, reference_day=None):
    """
    Send broad cost rankings as secondary context without changing current diagnosis logic.
    """
    return {
        "instruction": (
            "IA, estes sao os principais custos do periodo analisado. "
            "Use-os apenas como contexto complementar do periodo, sem substituir a analise principal das anomalias do dia."
        ),
        "top_services": _build_top_services_period_context(
            df_service_period=df_service_period,
            reference_day=reference_day,
        ),
        "top_usage_types": _build_top_usage_types_period_context(
            timeseries_period_df=timeseries_period_df,
            reference_day=reference_day,
        ),
        "top_api_operations": _build_top_api_operations_period_context(
            operation_timeseries_period_df=operation_timeseries_period_df,
            reference_day=reference_day,
        ),
    }


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
    df_service_period=None,
    timeseries_period_df=None,
    operation_timeseries_period_df=None,
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
        "period_cost_context": _build_period_cost_context(
            df_service_period=df_service_period,
            timeseries_period_df=timeseries_period_df,
            operation_timeseries_period_df=operation_timeseries_period_df,
            reference_day=ultimo_dia,
        ),
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
        "usage_type_context": anomaly.get("usage_type_context"),
        "complementary_usage_types": anomaly.get("complementary_usage_types", []),
        "top_api_operations": anomaly.get("top_api_operations", []),
        "s3_tier_change_analysis": anomaly.get("s3_tier_change_analysis"),
        "s3_driver_analysis": anomaly.get("s3_driver_analysis"),
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
