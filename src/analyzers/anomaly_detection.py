"""
Detect cost anomalies on top of daily service and usage type data.
"""

import pandas as pd
import config


def _is_s3_service(service_name):
    normalized = (service_name or "").strip().lower()
    return "simple storage service" in normalized or normalized == "s3"


def _build_complete_daily_costs(group, all_dates):
    """
    Reindex sparse Cost Explorer slices so missing days count as zero in the window.
    """
    normalized_group = group.copy()
    normalized_group["Data"] = normalized_group["Data"].astype(str)
    aggregated = (
        normalized_group.groupby("Data", as_index=False)["Custo($)"]
        .sum()
        .set_index("Data")
        .reindex(all_dates, fill_value=0.0)
        .reset_index()
        .rename(columns={"index": "Data"})
    )
    return aggregated


def _calculate_usage_type_metrics(usage_group, ultimo_dia, all_dates=None):
    """
    Reuse the same daily metric math for primary and complementary usage types.
    """
    reference_dates = sorted({str(date_value) for date_value in (all_dates or usage_group["Data"].tolist())})
    if not reference_dates:
        reference_dates = sorted(usage_group["Data"].astype(str).unique().tolist())

    complete_group = _build_complete_daily_costs(usage_group, reference_dates)
    cost_today_rows = complete_group[complete_group["Data"] == ultimo_dia]
    cost_today = float(cost_today_rows["Custo($)"].sum()) if not cost_today_rows.empty else 0.0
    avg_7d = float(complete_group["Custo($)"].mean()) if not complete_group.empty else 0.0
    delta_usd = cost_today - avg_7d
    delta_pct = 0.0 if avg_7d == 0 else (delta_usd / avg_7d) * 100
    return {
        "cost_today": round(cost_today, 4),
        "avg_7d": round(avg_7d, 4),
        "delta_usd": round(delta_usd, 4),
        "delta_pct": round(delta_pct, 2),
        "series": [
            {"date": row["Data"], "cost_usd": round(float(row["Custo($)"]), 4)}
            for _, row in complete_group.iterrows()
        ],
    }


def _extract_s3_storage_tier_candidates(usage_type_lower):
    """
    Surface likely S3 storage classes mentioned in the usage type string.
    """
    tier_markers = [
        ("deeparchive", "Deep Archive"),
        ("glacierir", "Glacier Instant Retrieval"),
        ("glacier", "Glacier Flexible Retrieval"),
        ("int-fa", "Intelligent-Tiering Frequent Access"),
        ("int-ia", "Intelligent-Tiering Infrequent Access"),
        ("int-aa", "Intelligent-Tiering Archive Access"),
        ("int-da", "Intelligent-Tiering Deep Archive Access"),
        ("onezone-ia", "One Zone-IA"),
        ("standard-ia", "Standard-IA"),
        ("reducedredundancy", "Reduced Redundancy"),
        ("standard", "Standard"),
    ]
    tiers = []
    for marker, label in tier_markers:
        if marker in usage_type_lower and label not in tiers:
            tiers.append(label)
    if "intelligent-tiering" in usage_type_lower and "Intelligent-Tiering" not in tiers:
        tiers.append("Intelligent-Tiering")
    return tiers


def _classify_s3_usage_type(usage_type):
    """
    Convert raw S3 usage types into families the prompt can reason about safely.
    """
    usage_type_text = str(usage_type or "")
    usage_type_lower = usage_type_text.lower()

    if "request" in usage_type_lower:
        family = "s3_requests"
    elif any(marker in usage_type_lower for marker in ["transition", "tiering", "intelligent-tiering"]):
        family = "s3_storage_class_transition"
    elif any(marker in usage_type_lower for marker in ["retrieval", "restore", "select-scanned", "select-returned"]):
        family = "s3_retrieval_restore"
    elif "earlydelete" in usage_type_lower:
        family = "s3_early_delete"
    elif any(marker in usage_type_lower for marker in ["datatransfer", "bandwidth", "bytes"]):
        family = "s3_data_transfer"
    elif any(marker in usage_type_lower for marker in ["inventory", "analytics", "tables", "objecttagging"]):
        family = "s3_inventory_and_analytics"
    elif "timedstorage" in usage_type_lower or "storage" in usage_type_lower:
        family = "s3_storage"
    else:
        family = "s3_other"

    tier_candidates = _extract_s3_storage_tier_candidates(usage_type_lower)
    summary = config.S3_USAGE_FAMILY_SUMMARIES.get(family, config.S3_USAGE_FAMILY_SUMMARIES["s3_other"])
    return {
        "cost_family": family,
        "summary": summary,
        # Only transition/storage/early-delete are strong signals for bucket tier change.
        "is_storage_class_change_signal": family in {"s3_storage_class_transition", "s3_storage", "s3_early_delete"},
        "storage_tier_candidates": tier_candidates,
    }


def _build_usage_type_entry(usage_type, usage_group, ultimo_dia, usage_type_context=None, all_dates=None):
    """
    Standardize complementary usage type entries so renderers and Bedrock see one schema.
    """
    metrics = _calculate_usage_type_metrics(usage_group, ultimo_dia, all_dates=all_dates)
    entry = {
        "usage_type": usage_type,
        **metrics,
    }
    if usage_type_context:
        entry["usage_type_context"] = usage_type_context
    return entry


def _build_sms_complementary_usage_types(service_rows, ultimo_dia):
    """
    Keep the SMS-specific complementary usage types that help reconcile traffic volume.
    """
    complementary_usage_types = []
    service_dates = sorted(service_rows["Data"].astype(str).unique().tolist())
    for pattern in config.SMS_COMPLEMENTARY_USAGE_TYPE_PATTERNS:
        matching_rows = service_rows[service_rows["UsageType"].str.contains(pattern, case=False, na=False)].copy()
        if matching_rows.empty:
            continue

        grouped = (
            matching_rows.groupby(["Data", "UsageType"], as_index=False)["Custo($)"]
            .sum()
            .sort_values(["UsageType", "Data"])
        )
        for usage_type, usage_group in grouped.groupby("UsageType"):
            complementary_usage_types.append(
                _build_usage_type_entry(
                    usage_type=usage_type,
                    usage_group=usage_group,
                    ultimo_dia=ultimo_dia,
                    all_dates=service_dates,
                )
            )
    return complementary_usage_types


def _build_s3_complementary_usage_types(anomaly, service_rows, ultimo_dia):
    """
    Expose sibling S3 usage types so the model can spot class transitions and paired movements.
    """
    service_dates = sorted(service_rows["Data"].astype(str).unique().tolist())
    grouped = (
        service_rows.groupby(["Data", "UsageType"], as_index=False)["Custo($)"]
        .sum()
        .sort_values(["UsageType", "Data"])
    )

    complementary_usage_types = []
    for usage_type, usage_group in grouped.groupby("UsageType"):
        if usage_type == anomaly.get("usage_type"):
            continue

        metrics = _calculate_usage_type_metrics(usage_group, ultimo_dia, all_dates=service_dates)
        if (
            abs(metrics["delta_usd"]) < config.MIN_ABSOLUTE_VARIATION_USD
            and abs(metrics["delta_pct"]) < config.MIN_PERCENT_VARIATION
            and metrics["cost_today"] < config.MIN_DAILY_COST_USD
        ):
            continue

        complementary_usage_types.append(
            {
                "usage_type": usage_type,
                **metrics,
                "usage_type_context": _classify_s3_usage_type(usage_type),
            }
        )

    complementary_usage_types.sort(
        key=lambda item: (abs(item["delta_usd"]), abs(item["delta_pct"]), item["cost_today"]),
        reverse=True,
    )
    return complementary_usage_types[: config.S3_MAX_COMPLEMENTARY_USAGE_TYPES]


def _build_api_operation_entry(operation_name, operation_group, ultimo_dia, all_dates=None):
    """
    Standardize API operation summaries attached to anomalies.
    """
    metrics = _calculate_usage_type_metrics(operation_group, ultimo_dia, all_dates=all_dates)
    return {
        "operation": operation_name,
        **metrics,
    }


def _is_material_cost_signal(cost_signal):
    """
    Decide if a cost signal is strong enough to influence the S3 tier-change verdict.
    """
    return (
        abs(float(cost_signal.get("delta_usd", 0.0) or 0.0)) >= config.MIN_ABSOLUTE_VARIATION_USD
        or abs(float(cost_signal.get("delta_pct", 0.0) or 0.0)) >= config.MIN_PERCENT_VARIATION
        or float(cost_signal.get("cost_today", 0.0) or 0.0) >= config.MIN_DAILY_COST_USD
    )


def _is_material_s3_storage_signal(cost_signal):
    """
    Storage/tier signals should not be considered material just because the daily base cost is high.
    """
    delta_usd = abs(float(cost_signal.get("delta_usd", 0.0) or 0.0))
    delta_pct = abs(float(cost_signal.get("delta_pct", 0.0) or 0.0))
    return (
        delta_usd >= config.S3_TIER_CHANGE_MIN_VARIATION_USD
        or delta_pct >= config.S3_TIER_CHANGE_MIN_VARIATION_PCT
    )


def _build_s3_tier_change_analysis(anomaly):
    """
    Produce an explicit verdict so the LLM must say whether tier/class change is supported.
    """
    usage_type_context = anomaly.get("usage_type_context") or {}
    complementary_usage_types = anomaly.get("complementary_usage_types") or []
    top_api_operations = anomaly.get("top_api_operations") or []

    storage_cost_signals = []
    if usage_type_context.get("is_storage_class_change_signal") and _is_material_s3_storage_signal(anomaly):
        storage_cost_signals.append(
            {
                "source": "primary_usage_type",
                "usage_type": anomaly.get("usage_type"),
                "delta_usd": anomaly.get("delta_usd"),
                "delta_pct": anomaly.get("delta_pct"),
                "storage_tier_candidates": usage_type_context.get("storage_tier_candidates", []),
            }
        )

    for item in complementary_usage_types:
        item_context = item.get("usage_type_context") or {}
        if not item_context.get("is_storage_class_change_signal"):
            continue
        if not _is_material_s3_storage_signal(item):
            continue
        storage_cost_signals.append(
            {
                "source": "complementary_usage_type",
                "usage_type": item.get("usage_type"),
                "delta_usd": item.get("delta_usd"),
                "delta_pct": item.get("delta_pct"),
                "storage_tier_candidates": item_context.get("storage_tier_candidates", []),
            }
        )

    transition_operation_markers = {
        "lifecycletransition",
        "copyobject",
        "transition",
        "putbucketlifecycleconfiguration",
        "restoreobject",
    }
    transition_operation_signals = []
    for operation in top_api_operations:
        normalized_operation = str(operation.get("operation") or "").replace(" ", "").lower()
        if any(marker in normalized_operation for marker in transition_operation_markers):
            transition_operation_signals.append(
                {
                    "operation": operation.get("operation"),
                    "delta_usd": operation.get("delta_usd"),
                    "delta_pct": operation.get("delta_pct"),
                }
            )

    request_operation_driver = None
    if top_api_operations:
        request_operation_driver = max(
            top_api_operations,
            key=lambda item: (
                abs(float(item.get("delta_usd", 0.0) or 0.0)),
                abs(float(item.get("delta_pct", 0.0) or 0.0)),
                float(item.get("cost_today", 0.0) or 0.0),
            ),
        )

    if storage_cost_signals and transition_operation_signals:
        status = "supported"
        summary = (
            "Ha evidencia combinada de custo por storage/transicao e API operations "
            "compativeis com mudanca de classe/tier."
        )
    elif storage_cost_signals:
        status = "inconclusive"
        summary = (
            "Ha sinal de custo compativel com mudanca de classe/tier, mas sem API operation "
            "forte o suficiente para fechar causalidade sozinho."
        )
    else:
        status = "not_supported"
        summary = (
            "O payload nao trouxe evidencia material de storage/transicao; o sinal dominante atual "
            "parece ligado a requests ou outra operacao custosa."
        )

    return {
        "status": status,
        "summary": summary,
        "request_cost_driver": {
            "usage_type": anomaly.get("usage_type"),
            "cost_family": usage_type_context.get("cost_family"),
            "top_api_operation": request_operation_driver.get("operation") if request_operation_driver else None,
            "top_api_operation_delta_usd": request_operation_driver.get("delta_usd") if request_operation_driver else None,
            "top_api_operation_delta_pct": request_operation_driver.get("delta_pct") if request_operation_driver else None,
        },
        "storage_cost_signals": storage_cost_signals,
        "transition_operation_signals": transition_operation_signals,
    }


def _score_s3_driver_signal(signal):
    """
    Rank S3 families by combining absolute delta, relative delta and current daily cost.
    """
    delta_usd = abs(float(signal.get("delta_usd", 0.0) or 0.0))
    delta_pct = abs(float(signal.get("delta_pct", 0.0) or 0.0))
    cost_today = float(signal.get("cost_today", 0.0) or 0.0)
    return round((delta_usd * 4.0) + min(delta_pct, 300.0) + (cost_today * 0.3), 4)


def _summarize_s3_operation_family(top_api_operations):
    """
    Translate dominant S3 operations into a higher-level operational family.
    """
    if not top_api_operations:
        return {
            "family": "unknown",
            "summary": "Nao houve API operation suficiente no payload para classificar o padrao operacional dominante.",
        }

    top_operation = max(
        top_api_operations,
        key=lambda item: (
            abs(float(item.get("delta_usd", 0.0) or 0.0)),
            abs(float(item.get("delta_pct", 0.0) or 0.0)),
            float(item.get("cost_today", 0.0) or 0.0),
        ),
    )
    operation_name = str(top_operation.get("operation") or "")
    operation_key = operation_name.replace(" ", "").lower()

    if any(token in operation_key for token in ["listbucket", "getobject", "headobject", "selectobjectcontent"]):
        family = "request_read"
        summary = "O padrao operacional dominante parece ligado a leitura/listagem de objetos."
    elif any(token in operation_key for token in ["putobject", "copyobject", "copymultipartupload", "completemultipartupload"]):
        family = "request_write"
        summary = "O padrao operacional dominante parece ligado a escrita/copia de objetos."
    elif any(token in operation_key for token in ["lifecycletransition", "putbucketlifecycleconfiguration", "putbucketintelligenttieringconfiguration"]):
        family = "tier_transition_operation"
        summary = "O padrao operacional dominante parece compativel com lifecycle ou mudanca de tier/classe."
    elif any(token in operation_key for token in ["restoreobject", "glacier", "retrieval"]):
        family = "retrieval_restore_operation"
        summary = "O padrao operacional dominante parece ligado a retrieval ou restore de dados frios."
    else:
        family = "other_operation"
        summary = f"A operacao dominante observada foi `{operation_name}`."

    return {
        "family": family,
        "summary": summary,
        "top_operation": operation_name,
        "top_operation_delta_usd": top_operation.get("delta_usd"),
        "top_operation_delta_pct": top_operation.get("delta_pct"),
    }


def _build_s3_driver_analysis(anomaly):
    """
    Build a smarter family-based diagnosis so the LLM can separate request and storage narratives.
    """
    usage_type_context = anomaly.get("usage_type_context") or {}
    complementary_usage_types = anomaly.get("complementary_usage_types") or []
    top_api_operations = anomaly.get("top_api_operations") or []
    tier_change_analysis = anomaly.get("s3_tier_change_analysis") or {}

    family_signals = []
    primary_signal = {
        "source": "primary_usage_type",
        "usage_type": anomaly.get("usage_type"),
        "cost_family": usage_type_context.get("cost_family", "s3_other"),
        "summary": usage_type_context.get("summary"),
        "cost_today": anomaly.get("cost_today"),
        "avg_7d": anomaly.get("avg_7d"),
        "delta_usd": anomaly.get("delta_usd"),
        "delta_pct": anomaly.get("delta_pct"),
    }
    primary_signal["score"] = _score_s3_driver_signal(primary_signal)
    family_signals.append(primary_signal)

    for item in complementary_usage_types:
        item_context = item.get("usage_type_context") or {}
        signal = {
            "source": "complementary_usage_type",
            "usage_type": item.get("usage_type"),
            "cost_family": item_context.get("cost_family", "s3_other"),
            "summary": item_context.get("summary"),
            "cost_today": item.get("cost_today"),
            "avg_7d": item.get("avg_7d"),
            "delta_usd": item.get("delta_usd"),
            "delta_pct": item.get("delta_pct"),
        }
        signal["score"] = _score_s3_driver_signal(signal)
        family_signals.append(signal)

    operation_family = _summarize_s3_operation_family(top_api_operations)
    ranked_family_signals = sorted(
        family_signals,
        key=lambda item: (item.get("score", 0.0), abs(float(item.get("delta_usd", 0.0) or 0.0))),
        reverse=True,
    )

    primary_driver = ranked_family_signals[0] if ranked_family_signals else None
    secondary_driver = None
    if len(ranked_family_signals) > 1:
        for candidate in ranked_family_signals[1:]:
            if candidate.get("cost_family") != primary_driver.get("cost_family"):
                secondary_driver = candidate
                break

    tier_status = tier_change_analysis.get("status")
    if tier_status == "supported":
        confidence = "high"
    elif tier_status == "inconclusive":
        confidence = "medium"
    elif primary_driver and primary_driver.get("cost_family") == "s3_requests":
        confidence = "high"
    else:
        confidence = "medium"

    narrative = []
    if primary_driver:
        narrative.append(
            f"Driver principal por custo: {primary_driver.get('cost_family')} via `{primary_driver.get('usage_type')}`."
        )
    if operation_family.get("summary"):
        narrative.append(operation_family["summary"])
    if tier_status == "supported":
        narrative.append("Mudanca de tier/classe aparece como componente principal ou claramente corroborado.")
    elif tier_status == "inconclusive":
        narrative.append("Mudanca de tier/classe aparece como fator contribuinte possivel, mas nao dominante.")
    else:
        narrative.append("Mudanca de tier/classe nao aparece como driver principal com o payload atual.")

    return {
        "confidence": confidence,
        "primary_driver": primary_driver,
        "secondary_driver": secondary_driver,
        "operation_family": operation_family,
        "family_ranking": ranked_family_signals[:4],
        "narrative_summary": " ".join(narrative),
    }


def build_usage_type_timeseries(df):
    """
    Normalize the input into daily cost series by service and usage type.
    """
    required_columns = {"Data", "Serviço", "Custo($)"}
    missing = required_columns - set(df.columns)
    if missing:
        raise KeyError(f"Colunas obrigatorias ausentes para analise de anomalias: {sorted(missing)}")

    df_normalized = df.copy()
    if "UsageType" not in df_normalized.columns:
        df_normalized["UsageType"] = "Total"

    df_normalized["Data"] = df_normalized["Data"].astype(str)
    df_normalized["Serviço"] = df_normalized["Serviço"].astype(str)
    df_normalized["UsageType"] = df_normalized["UsageType"].fillna("Total").astype(str)
    df_normalized["Custo($)"] = pd.to_numeric(df_normalized["Custo($)"], errors="coerce").fillna(0.0)

    return (
        df_normalized.groupby(["Data", "Serviço", "UsageType"], as_index=False)["Custo($)"]
        .sum()
        .sort_values(["Serviço", "UsageType", "Data"])
    )


def calculate_anomalies(timeseries_df, data_inicio, data_fim, ultimo_dia):
    """
    Calculate daily anomaly metrics by service and usage type within the consolidated window.
    """
    df_window = timeseries_df[
        (timeseries_df["Data"] >= data_inicio) & (timeseries_df["Data"] <= data_fim)
    ].copy()

    anomalies = []
    grouped = df_window.groupby(["Serviço", "UsageType"])
    window_dates = sorted(df_window["Data"].astype(str).unique().tolist())

    for (service, usage_type), group in grouped:
        group = group.sort_values("Data")
        if group.empty:
            continue

        metrics = _calculate_usage_type_metrics(group, ultimo_dia, all_dates=window_dates)
        cost_today_rows = [item for item in metrics["series"] if item["date"] == ultimo_dia]
        if not cost_today_rows:
            continue

        anomalies.append(
            {
                "service": service,
                "usage_type": usage_type,
                "cost_today": metrics["cost_today"],
                "avg_7d": metrics["avg_7d"],
                "delta_usd": metrics["delta_usd"],
                "delta_pct": metrics["delta_pct"],
                "days_present": int(group["Data"].nunique()),
                "series": metrics["series"],
            }
        )

    anomalies.sort(key=lambda item: (item["delta_usd"], item["cost_today"]), reverse=True)
    return anomalies


def filter_relevant_anomalies(anomalies):
    """
    Keep only anomalies relevant enough to justify metric enrichment.
    """
    filtered = [
        item
        for item in anomalies
        if item["cost_today"] >= config.MIN_DAILY_COST_USD
        or abs(item["delta_pct"]) >= config.MIN_PERCENT_VARIATION
    ]
    filtered.sort(key=lambda item: (abs(item["delta_usd"]), item["cost_today"]), reverse=True)
    return filtered[: config.TOP_N_ANOMALIES]


def enrich_complementary_usage_types(anomalies, timeseries_df, ultimo_dia):
    """
    Attach complementary Cost Explorer usage types and semantic hints for selected anomaly families.
    """
    if timeseries_df is None or timeseries_df.empty:
        return anomalies

    enriched = []
    for anomaly in anomalies:
        service_rows = timeseries_df[timeseries_df["Serviço"] == anomaly.get("service")].copy()
        updated_anomaly = dict(anomaly)
        complementary_usage_types = []

        if anomaly.get("service") in config.SPECIAL_SERVICES:
            complementary_usage_types.extend(
                _build_sms_complementary_usage_types(service_rows=service_rows, ultimo_dia=ultimo_dia)
            )

        if _is_s3_service(anomaly.get("service")):
            updated_anomaly["usage_type_context"] = _classify_s3_usage_type(anomaly.get("usage_type"))
            complementary_usage_types.extend(
                _build_s3_complementary_usage_types(
                    anomaly=anomaly,
                    service_rows=service_rows,
                    ultimo_dia=ultimo_dia,
                )
            )

        if complementary_usage_types:
            updated_anomaly["complementary_usage_types"] = complementary_usage_types

        enriched.append(updated_anomaly)

    return enriched


def enrich_api_operations(anomalies, operation_timeseries_df, ultimo_dia):
    """
    Attach top API operations for the allowlisted services in phase 1.
    """
    if operation_timeseries_df is None or operation_timeseries_df.empty:
        return anomalies

    operation_df = operation_timeseries_df.copy()
    operation_df["Serviço"] = operation_df["Serviço"].astype(str)
    operation_df["ApiOperation"] = operation_df["ApiOperation"].fillna("Unknown").astype(str)
    operation_dates = sorted(operation_df["Data"].astype(str).unique().tolist())

    enriched = []
    for anomaly in anomalies:
        service_name = anomaly.get("service")
        updated_anomaly = dict(anomaly)
        if service_name not in config.API_OPERATION_SERVICES:
            enriched.append(updated_anomaly)
            continue

        service_rows = operation_df[operation_df["Serviço"] == service_name].copy()
        if service_rows.empty:
            enriched.append(updated_anomaly)
            continue

        grouped = (
            service_rows.groupby(["Data", "ApiOperation"], as_index=False)["Custo($)"]
            .sum()
            .sort_values(["ApiOperation", "Data"])
        )

        top_api_operations = []
        for operation_name, operation_group in grouped.groupby("ApiOperation"):
            entry = _build_api_operation_entry(
                operation_name=operation_name,
                operation_group=operation_group,
                ultimo_dia=ultimo_dia,
                all_dates=operation_dates,
            )
            if (
                abs(entry["delta_usd"]) < config.MIN_ABSOLUTE_VARIATION_USD
                and abs(entry["delta_pct"]) < config.MIN_PERCENT_VARIATION
                and entry["cost_today"] < config.MIN_DAILY_COST_USD
            ):
                continue
            top_api_operations.append(entry)

        top_api_operations.sort(
            key=lambda item: (abs(item["delta_usd"]), abs(item["delta_pct"]), item["cost_today"]),
            reverse=True,
        )
        if top_api_operations:
            updated_anomaly["top_api_operations"] = top_api_operations[: config.MAX_API_OPERATIONS_PER_ANOMALY]

        enriched.append(updated_anomaly)

    return enriched


def enrich_s3_tier_change_analysis(anomalies):
    """
    Attach an explicit S3 tier/class-change verdict so the prompt can require a clear answer.
    """
    enriched = []
    for anomaly in anomalies:
        updated_anomaly = dict(anomaly)
        if _is_s3_service(anomaly.get("service")):
            updated_anomaly["s3_tier_change_analysis"] = _build_s3_tier_change_analysis(updated_anomaly)
            updated_anomaly["s3_driver_analysis"] = _build_s3_driver_analysis(updated_anomaly)
        enriched.append(updated_anomaly)
    return enriched
