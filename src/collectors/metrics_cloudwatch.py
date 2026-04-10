"""
CloudWatch metric collection helpers.
"""

from datetime import datetime, timedelta
import boto3
import botocore
import config


def _get_resource_value(resource, field_name):
    value = resource.get(field_name)
    if value not in (None, ""):
        return value

    derived_context = resource.get("derived_context", {})
    return derived_context.get(field_name)


def build_cloudwatch_client(region_name=None):
    """
    Build a CloudWatch client using the configured AWS profile.
    """
    session = boto3.Session(
        profile_name=config.AWS_PROFILE,
        region_name=region_name or config.WORKLOAD_REGION,
    )
    return session.client("cloudwatch")


def _build_dimensions(metric_definition, resource):
    dimensions = []
    for definition in metric_definition.get("dimensions", []):
        if "Value" in definition:
            value = definition["Value"]
        else:
            value = _get_resource_value(resource, definition["ValueFrom"])
            if value in (None, ""):
                return None
        dimensions.append({"Name": definition["Name"], "Value": value})

    for extra in metric_definition.get("extra_dimensions", []):
        if "ValueFrom" in extra:
            value = _get_resource_value(resource, extra["ValueFrom"])
            if value in (None, ""):
                return None
            dimensions.append({"Name": extra["Name"], "Value": value})
        else:
            dimensions.append({"Name": extra["Name"], "Value": extra["Value"]})

    return dimensions


def fetch_metric_series(client, namespace, metric_definition, resource, start_date, end_date):
    """
    Fetch a daily metric series and summarize it for the analysis window.
    """
    if not namespace or not metric_definition:
        return None

    dimensions = _build_dimensions(metric_definition, resource)
    if not dimensions:
        return None
    if any(not dimension["Value"] for dimension in dimensions):
        return None

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    try:
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_definition["name"],
            Dimensions=dimensions,
            StartTime=start_dt,
            EndTime=end_dt,
            Period=86400,
            Statistics=[metric_definition["stat"]],
        )
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return None

    datapoints = response.get("Datapoints", [])
    if not datapoints:
        return None

    datapoints.sort(key=lambda item: item["Timestamp"])
    stat_name = metric_definition["stat"]
    values = [float(point.get(stat_name, 0.0)) for point in datapoints]
    if not values:
        return None

    today_value = values[-1]
    avg_7d = sum(values) / len(values)
    delta_value = today_value - avg_7d
    delta_pct = 0.0 if avg_7d == 0 else (delta_value / avg_7d) * 100
    peak_point = max(datapoints, key=lambda point: float(point.get(stat_name, 0.0)))
    min_point = min(datapoints, key=lambda point: float(point.get(stat_name, 0.0)))

    return {
        "stat": stat_name,
        "today": round(today_value, 4),
        "avg_7d": round(avg_7d, 4),
        "delta": round(delta_value, 4),
        "delta_pct": round(delta_pct, 2),
        "peak_date": peak_point["Timestamp"].strftime("%Y-%m-%d"),
        "peak_value": round(float(peak_point.get(stat_name, 0.0)), 4),
        "min_date": min_point["Timestamp"].strftime("%Y-%m-%d"),
        "min_value": round(float(min_point.get(stat_name, 0.0)), 4),
        "series": [
            {"date": point["Timestamp"].strftime("%Y-%m-%d"), "value": round(float(point.get(stat_name, 0.0)), 4)}
            for point in datapoints
        ],
    }


def collect_cloudwatch_metrics(resource, rule, start_date, end_date):
    """
    Collect and summarize CloudWatch metrics for a resource candidate.
    """
    namespace = rule.get("namespace")
    if not namespace or not rule.get("metrics"):
        return {}

    cloudwatch_region = resource.get("cloudwatch_region") or config.WORKLOAD_REGION
    try:
        client = build_cloudwatch_client(region_name=cloudwatch_region)
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return {}

    metrics_summary = {}

    for metric_definition in rule.get("metrics", []):
        metric_namespace = metric_definition.get("namespace_override", namespace)
        metric_summary = fetch_metric_series(
            client=client,
            namespace=metric_namespace,
            metric_definition=metric_definition,
            resource=resource,
            start_date=start_date,
            end_date=end_date,
        )
        if metric_summary is not None:
            metrics_summary[metric_definition["name"]] = metric_summary

    return metrics_summary
