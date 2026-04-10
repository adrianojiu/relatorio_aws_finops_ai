"""
Best-effort metrics for messaging flows using supporting AWS queues.
"""

import botocore
import config
from collectors import metrics_cloudwatch


def collect_messaging_metrics(resource, _rule, start_date, end_date):
    """
    Collect SQS metrics that can explain End User Messaging cost behavior.
    """
    resource_id = resource.get("resource_id")
    if not resource_id:
        return {}

    try:
        client = metrics_cloudwatch.build_cloudwatch_client()
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return {}

    metrics_summary = {}
    for metric_definition in config.MESSAGING_SQS_METRICS:
        query_definition = {
            **metric_definition,
            "dimensions": [{"Name": "QueueName", "ValueFrom": "resource_id"}],
        }
        metric_summary = metrics_cloudwatch.fetch_metric_series(
            client=client,
            namespace="AWS/SQS",
            metric_definition=query_definition,
            resource=resource,
            start_date=start_date,
            end_date=end_date,
        )
        if metric_summary is not None:
            metrics_summary[metric_definition["name"]] = metric_summary

    return metrics_summary
