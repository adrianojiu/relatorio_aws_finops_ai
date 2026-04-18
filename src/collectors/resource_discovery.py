"""
Best-effort AWS resource discovery to correlate cost anomalies with concrete resources.
"""

from datetime import datetime, timedelta, timezone
import json

import boto3
import botocore
import config
from collectors import metrics_cloudwatch, metrics_messaging


def _build_session():
    return boto3.Session(profile_name=config.AWS_PROFILE, region_name=config.WORKLOAD_REGION)


def _tags_to_dict(tags):
    return {tag.get("Key"): tag.get("Value") for tag in (tags or []) if tag.get("Key")}


def _infer_ec2_context(tag_map):
    name = (tag_map.get("Name") or "").lower()
    nodegroup_name = (tag_map.get("eks:nodegroup-name") or "").lower()
    cluster_name = (tag_map.get("eks:cluster-name") or "").lower()
    autoscaling_group_name = (tag_map.get("aws:autoscaling:groupName") or "").lower()

    derived_context = {}
    notes = []

    if "pd-" in name:
        derived_context["workload_family"] = "ping_directory"
        if "primary" in name:
            derived_context["workload_role"] = "ping_directory_primary"
        elif "secondary" in name:
            derived_context["workload_role"] = "ping_directory_secondary"
        elif "tertiary" in name:
            derived_context["workload_role"] = "ping_directory_tertiary"
        elif "quaternary" in name:
            derived_context["workload_role"] = "ping_directory_quaternary"
            notes.append(
                "Instancia quaternaria de Ping Directory costuma executar relatorios, backups para S3 e limpeza da base."
            )

    if cluster_name == "prd-sso-fachada":
        derived_context["eks_cluster"] = "prd-sso-fachada"
        derived_context["workload_family"] = "credential_orchestration_apis"
        notes.append(
            "Cluster prd-sso-fachada executa APIs de orquestracao de credenciais, como credentials-management e reset."
        )
        if autoscaling_group_name.startswith("eks-app-"):
            derived_context["autoscaling_role"] = "fachada_apis"

    if "ping-access-app" in nodegroup_name or name == "ping-access-app":
        derived_context["eks_cluster"] = "prd-sso-ciam"
        derived_context["eks_nodegroup_role"] = "ping_access"
        derived_context["workload_family"] = "ping_access"
    elif "ping-pdp-app" in nodegroup_name or name == "ping-pdp-app":
        derived_context["eks_cluster"] = "prd-sso-ciam"
        derived_context["eks_nodegroup_role"] = "ping_pdp"
        derived_context["workload_family"] = "ping_pdp"
    elif "ping-federate-app" in nodegroup_name or name == "ping-federate-app":
        derived_context["eks_cluster"] = "prd-sso-ciam"
        derived_context["eks_nodegroup_role"] = "ping_federate"
        derived_context["workload_family"] = "ping_federate"

    if autoscaling_group_name.startswith("eks-ping-access") and cluster_name == "prd-sso-ciam":
        derived_context["autoscaling_role"] = "ping_access"
    elif autoscaling_group_name.startswith("eks-ping-pdp") and cluster_name == "prd-sso-ciam":
        derived_context["autoscaling_role"] = "ping_pdp"
    elif autoscaling_group_name.startswith("eks-ping-federate") and cluster_name == "prd-sso-ciam":
        derived_context["autoscaling_role"] = "ping_federate"

    if derived_context.get("eks_cluster") == "prd-sso-ciam":
        notes.append(
            "Cluster prd-sso-ciam executa Ping Access, Ping Federate e PDP em nodegroups baseados em EC2."
        )

    return derived_context, notes


def _infer_asg_context(group_name, tag_map):
    group_name_lower = (group_name or "").lower()
    cluster_name = (tag_map.get("eks:cluster-name") or "").lower()

    derived_context = {
        "autoscaling_group_name": group_name,
    }
    notes = []

    if group_name_lower.startswith("eks-ping-access") and cluster_name == "prd-sso-ciam":
        derived_context["eks_cluster"] = "prd-sso-ciam"
        derived_context["autoscaling_role"] = "ping_access"
        derived_context["workload_family"] = "ping_access"
    elif group_name_lower.startswith("eks-ping-pdp") and cluster_name == "prd-sso-ciam":
        derived_context["eks_cluster"] = "prd-sso-ciam"
        derived_context["autoscaling_role"] = "ping_pdp"
        derived_context["workload_family"] = "ping_pdp"
    elif group_name_lower.startswith("eks-ping-federate") and cluster_name == "prd-sso-ciam":
        derived_context["eks_cluster"] = "prd-sso-ciam"
        derived_context["autoscaling_role"] = "ping_federate"
        derived_context["workload_family"] = "ping_federate"
    elif group_name_lower.startswith("eks-app-") and cluster_name == "prd-sso-fachada":
        derived_context["eks_cluster"] = "prd-sso-fachada"
        derived_context["autoscaling_role"] = "fachada_apis"
        derived_context["workload_family"] = "credential_orchestration_apis"

    if "eks_cluster" in derived_context:
        notes.append(
            "Auto Scaling Group de nodegroup EKS identificado para correlacionar scaling de compute nos clusters."
        )

    return derived_context, notes


def _describe_instance_types_for_ids(ec2_client, instance_ids):
    """
    Resolve the instance types currently attached to an ASG from live EC2 instances.
    """
    if not instance_ids:
        return []

    observed_types = set()
    for index in range(0, len(instance_ids), 100):
        batch = instance_ids[index:index + 100]
        response = ec2_client.describe_instances(InstanceIds=batch)
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instance_type = instance.get("InstanceType")
                if instance_type:
                    observed_types.add(instance_type)

    return sorted(observed_types)


def _usage_type_matches_instance_types(usage_type, observed_instance_types):
    """
    Check whether the Cost Explorer usage type explicitly contains one of the ASG instance types.
    """
    usage_type_lower = (usage_type or "").lower()
    return any(instance_type.lower() in usage_type_lower for instance_type in (observed_instance_types or []))


def _infer_s3_context(bucket_name):
    bucket_name = (bucket_name or "").lower()
    bucket_context = config.KNOWN_S3_BUCKET_CONTEXT.get(bucket_name, {})
    derived_context = {
        key: value
        for key, value in bucket_context.items()
        if key != "notes"
    }
    notes = list(bucket_context.get("notes", []))
    return derived_context, notes


def _infer_messaging_queue_context(queue_name):
    queue_context = config.KNOWN_MESSAGING_QUEUE_CONTEXT.get(queue_name, {})
    derived_context = {
        key: value
        for key, value in queue_context.items()
        if key != "notes"
    }
    notes = list(queue_context.get("notes", []))
    return derived_context, notes


def _resolve_s3_request_filter_id(client, bucket_name, derived_context):
    """
    Resolve the CloudWatch request metrics configuration ID for a bucket.
    """
    configured_filter_id = derived_context.get("request_metrics_filter_id")
    if configured_filter_id:
        return configured_filter_id

    fallback_filter_id = None

    try:
        paginator = client.get_paginator("list_bucket_metrics_configurations")
        for page in paginator.paginate(Bucket=bucket_name):
            for config_item in page.get("MetricsConfigurationList", []):
                config_id = config_item.get("Id")
                if not config_id:
                    continue
                metrics_filter = config_item.get("Filter")
                if not metrics_filter:
                    return config_id
                if config_id.lower() == config.DEFAULT_S3_REQUEST_FILTER_ID.lower():
                    return config_id
                if fallback_filter_id is None:
                    fallback_filter_id = config_id
        return fallback_filter_id
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return configured_filter_id


def _normalize_s3_bucket_region(location_constraint):
    if location_constraint in (None, ""):
        return "us-east-1"
    if location_constraint == "EU":
        return "eu-west-1"
    return location_constraint


def _list_s3_buckets(session):
    client = session.client("s3")
    response = client.list_buckets()
    resources = []
    for bucket in response.get("Buckets", []):
        bucket_name = bucket["Name"]
        derived_context, notes = _infer_s3_context(bucket_name)
        request_filter_id = _resolve_s3_request_filter_id(client, bucket_name, derived_context)
        bucket_region = None
        try:
            location_response = client.get_bucket_location(Bucket=bucket_name)
            bucket_region = _normalize_s3_bucket_region(location_response.get("LocationConstraint"))
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
            bucket_region = config.WORKLOAD_REGION
        if request_filter_id:
            derived_context["s3_request_filter_id"] = request_filter_id
        if bucket_region:
            derived_context["bucket_region"] = bucket_region
        resources.append(
            {
                "resource_id": bucket_name,
                "cloudwatch_region": bucket_region or config.WORKLOAD_REGION,
                "derived_context": derived_context,
                "resource_notes": notes,
            }
        )
    resources.sort(
        key=lambda item: (
            0 if item.get("derived_context", {}).get("bucket_role") else 1,
            item.get("resource_id") or "",
        )
    )
    return resources


def _list_lambda_functions(session):
    client = session.client("lambda")
    paginator = client.get_paginator("list_functions")
    resources = []
    for page in paginator.paginate():
        for function in page.get("Functions", []):
            resources.append(
                {"resource_id": function["FunctionName"], "resource_arn": function.get("FunctionArn")}
            )
    return resources


def _list_sqs_queues(session):
    client = session.client("sqs")
    response = client.list_queues()
    resources = []
    for queue_url in response.get("QueueUrls", []):
        queue_name = queue_url.rstrip("/").split("/")[-1]
        resources.append({"resource_id": queue_name, "resource_arn": queue_url})
    return resources


def _list_messaging_queues(session):
    all_queues = _list_sqs_queues(session)
    selected = []
    allowed_names = set(config.KNOWN_MESSAGING_QUEUE_CONTEXT.keys())

    for queue in all_queues:
        queue_name = queue.get("resource_id")
        if queue_name not in allowed_names:
            continue
        derived_context, notes = _infer_messaging_queue_context(queue_name)
        selected.append(
            {
                "resource_id": queue_name,
                "resource_arn": queue.get("resource_arn"),
                "derived_context": derived_context,
                "resource_notes": notes,
            }
        )

    return selected


def _list_step_functions(session):
    client = session.client("stepfunctions")
    paginator = client.get_paginator("list_state_machines")
    resources = []
    for page in paginator.paginate():
        for machine in page.get("stateMachines", []):
            resources.append({"resource_id": machine["name"], "resource_arn": machine["stateMachineArn"]})
    return resources


def _list_dynamodb_tables(session):
    client = session.client("dynamodb")
    paginator = client.get_paginator("list_tables")
    resources = []
    for page in paginator.paginate():
        for table_name in page.get("TableNames", []):
            resources.append({"resource_id": table_name})
    return resources


def _list_firehose_streams(session):
    client = session.client("firehose")
    paginator = client.get_paginator("list_delivery_streams")
    resources = []
    for page in paginator.paginate():
        for stream_name in page.get("DeliveryStreamNames", []):
            known_context = config.KNOWN_FIREHOSE_STREAM_CONTEXT.get(stream_name, {})
            derived_context = {}
            notes = []
            if known_context:
                if known_context.get("stream_role"):
                    derived_context["stream_role"] = known_context["stream_role"]
                notes.extend(known_context.get("notes", []))

            if stream_name.startswith("prd-sso-fachada-"):
                derived_context.setdefault("workload_family", "fachada_apis")
                derived_context.setdefault("eks_cluster", "prd-sso-fachada")

            resources.append(
                {
                    "resource_id": stream_name,
                    "derived_context": derived_context,
                    "resource_notes": notes,
                }
            )
    return resources


def _list_glue_jobs(session):
    client = session.client("glue")
    paginator = client.get_paginator("get_jobs")
    resources = []
    for page in paginator.paginate():
        for job in page.get("Jobs", []):
            resources.append({"resource_id": job["Name"]})
    return resources


def _list_relevant_ecr_repositories(session):
    client = session.client("ecr")
    paginator = client.get_paginator("describe_repositories")
    resources = []
    known_repositories = set(config.KNOWN_ECR_REPOSITORY_CONTEXT.keys())

    for page in paginator.paginate():
        for repository in page.get("repositories", []):
            repository_name = repository.get("repositoryName")
            if repository_name not in known_repositories:
                continue

            known_context = config.KNOWN_ECR_REPOSITORY_CONTEXT.get(repository_name, {})
            derived_context = {}
            notes = list(known_context.get("notes", []))
            if known_context.get("repository_role"):
                derived_context["repository_role"] = known_context["repository_role"]

            if repository_name.startswith("pingidentity/"):
                derived_context.setdefault("eks_cluster", "prd-sso-ciam")
                derived_context.setdefault("workload_family", "ping_identity_images")
            elif repository_name.startswith("prd-sso-fachada-"):
                derived_context.setdefault("eks_cluster", "prd-sso-fachada")
                derived_context.setdefault("workload_family", "credential_orchestration_apis")

            resources.append(
                {
                    "resource_id": repository_name,
                    "resource_arn": repository.get("repositoryArn"),
                    "derived_context": derived_context,
                    "resource_notes": notes,
                    "cloudwatch_region": config.WORKLOAD_REGION,
                }
            )

    return resources


def _list_backup_vaults(session):
    client = session.client("backup")
    paginator = client.get_paginator("list_backup_vaults")
    resources = []

    for page in paginator.paginate():
        for vault in page.get("BackupVaultList", []):
            vault_name = vault.get("BackupVaultName")
            resources.append(
                {
                    "resource_id": vault_name,
                    "resource_arn": vault.get("BackupVaultArn"),
                    "derived_context": {
                        "workload_family": "aws_backup",
                        "backup_scope": "ec2_and_s3_complementary_evidence",
                    },
                    "resource_notes": [
                        "AWS Backup entra como evidencia complementar para snapshots, recovery points e crescimento de vault."
                    ],
                    "cloudwatch_region": config.WORKLOAD_REGION,
                }
            )

    return resources


def _extract_load_balancer_dimension(load_balancer_arn):
    marker = "loadbalancer/"
    if marker not in (load_balancer_arn or ""):
        return None
    return load_balancer_arn.split(marker, 1)[1]


def _list_load_balancers(session):
    client = session.client("elbv2")
    paginator = client.get_paginator("describe_load_balancers")
    resources = []
    known_load_balancers = config.KNOWN_LOAD_BALANCER_CONTEXT

    for page in paginator.paginate():
        for load_balancer in page.get("LoadBalancers", []):
            load_balancer_name = load_balancer.get("LoadBalancerName")
            if load_balancer_name not in known_load_balancers:
                continue

            known_context = known_load_balancers[load_balancer_name]
            derived_context = {
                "lb_type": known_context.get("lb_type", load_balancer.get("Type")),
                "lb_scheme": known_context.get("lb_scheme", load_balancer.get("Scheme")),
                "lb_role": known_context.get("lb_role"),
                "load_balancer_dimension": _extract_load_balancer_dimension(load_balancer.get("LoadBalancerArn")),
                "cloudwatch_namespace": (
                    "AWS/ApplicationELB"
                    if known_context.get("lb_type", load_balancer.get("Type")) == "application"
                    else "AWS/NetworkELB"
                ),
            }

            resources.append(
                {
                    "resource_id": load_balancer_name,
                    "resource_arn": load_balancer.get("LoadBalancerArn"),
                    "derived_context": derived_context,
                    "resource_notes": list(known_context.get("notes", [])),
                    "cloudwatch_region": config.WORKLOAD_REGION,
                }
            )

    return resources


def _list_nat_gateways(session):
    client = session.client("ec2")
    paginator = client.get_paginator("describe_nat_gateways")
    resources = []

    for page in paginator.paginate():
        for nat_gateway in page.get("NatGateways", []):
            resources.append(
                {
                    "resource_id": nat_gateway.get("NatGatewayId"),
                    "resource_arn": nat_gateway.get("NatGatewayArn"),
                    "derived_context": {
                        "workload_family": "nat_gateway",
                    },
                    "resource_notes": [
                        "NAT Gateway identificado para correlacao direta com usage types NatGateway-Bytes."
                    ],
                }
            )

    return resources


def _list_transit_gateways(session):
    client = session.client("ec2")
    paginator = client.get_paginator("describe_transit_gateways")
    resources = []

    for page in paginator.paginate():
        for transit_gateway in page.get("TransitGateways", []):
            resources.append(
                {
                    "resource_id": transit_gateway.get("TransitGatewayId"),
                    "resource_arn": transit_gateway.get("TransitGatewayArn"),
                    "derived_context": {
                        "workload_family": "transit_gateway",
                    },
                    "resource_notes": [
                        "Transit Gateway identificado para correlacao direta com usage types TransitGateway-Bytes."
                    ],
                }
            )

    return resources


def _list_log_groups(session):
    client = session.client("logs")
    paginator = client.get_paginator("describe_log_groups")
    resources = []
    for page in paginator.paginate():
        for group in page.get("logGroups", []):
            resources.append({"resource_id": group["logGroupName"]})
    return resources


def _build_logs_client(session):
    return session.client("logs", region_name=config.WORKLOAD_REGION)


def _build_cloudtrail_client(session, region_name=None):
    return session.client("cloudtrail", region_name=region_name or config.WORKLOAD_REGION)


def _build_athena_client(session):
    return session.client("athena", region_name=config.WORKLOAD_REGION)


def _normalize_text(value):
    return (value or "").strip().lower()


def _extract_cloudtrail_startquery_match(event, log_group_name, query_time, query_create_time_ms):
    raw_event = event.get("CloudTrailEvent")
    if not raw_event:
        return None

    try:
        parsed = json.loads(raw_event)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    request_parameters = parsed.get("requestParameters") or {}
    request_log_groups = []
    if request_parameters.get("logGroupName"):
        request_log_groups.append(request_parameters.get("logGroupName"))
    request_log_groups.extend(request_parameters.get("logGroupNames") or [])
    request_log_groups = [item for item in request_log_groups if item]
    if log_group_name not in request_log_groups:
        return None

    event_time = event.get("EventTime")
    if not event_time:
        return None

    delta_seconds = abs((event_time - query_time).total_seconds())
    return {
        "event_time": event_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "event_name": event.get("EventName"),
        "event_source": event.get("EventSource"),
        "username": event.get("Username") or (parsed.get("userIdentity") or {}).get("arn"),
        "source_ip": parsed.get("sourceIPAddress"),
        "user_agent": parsed.get("userAgent"),
        "matched_log_groups": request_log_groups,
        "time_delta_seconds": round(delta_seconds, 1),
        "match_confidence": (
            "high"
            if delta_seconds <= 300
            else "medium"
        ),
    }


def _extract_cloudtrail_startqueryexecution_match(event, query_execution_id, query_time):
    cloudtrail_event = event.get("CloudTrailEvent")
    if not cloudtrail_event:
        return None

    try:
        event_payload = json.loads(cloudtrail_event)
    except (TypeError, json.JSONDecodeError):
        return None

    response_elements = event_payload.get("responseElements") or {}
    matched_query_execution_id = response_elements.get("queryExecutionId")
    if matched_query_execution_id != query_execution_id:
        return None

    event_time = event.get("EventTime")
    if event_time is None:
        return None

    delta_seconds = abs((event_time - query_time).total_seconds())
    user_identity = event_payload.get("userIdentity") or {}
    session_issuer = (
        ((user_identity.get("sessionContext") or {}).get("sessionIssuer") or {})
        if isinstance(user_identity, dict)
        else {}
    )
    username = (
        user_identity.get("arn")
        or user_identity.get("userName")
        or session_issuer.get("arn")
        or session_issuer.get("userName")
    )

    request_parameters = event_payload.get("requestParameters") or {}
    query_execution_context = request_parameters.get("queryExecutionContext") or {}
    result_configuration = request_parameters.get("resultConfiguration") or {}

    return {
        "event_time": event_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "event_name": event.get("EventName"),
        "event_source": event.get("EventSource"),
        "username": username,
        "source_ip": event_payload.get("sourceIPAddress"),
        "user_agent": event_payload.get("userAgent"),
        "workgroup": request_parameters.get("workGroup"),
        "database": query_execution_context.get("database"),
        "catalog": query_execution_context.get("catalog"),
        "output_location": result_configuration.get("outputLocation"),
        "time_delta_seconds": round(delta_seconds, 2),
        "match_confidence": "high" if delta_seconds <= 300 else "medium",
    }


def _lookup_cloudtrail_startquery_context(session, log_group_name, create_time_ms):
    client = _build_cloudtrail_client(session)
    query_time = datetime.fromtimestamp(create_time_ms / 1000, tz=timezone.utc)
    window = timedelta(hours=config.CLOUDTRAIL_LOOKUP_WINDOW_HOURS)
    start_time = query_time - window
    end_time = query_time + window

    try:
        paginator = client.get_paginator("lookup_events")
        matches = []
        for page in paginator.paginate(
            LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": "StartQuery"}],
            StartTime=start_time,
            EndTime=end_time,
        ):
            for event in page.get("Events", []):
                match = _extract_cloudtrail_startquery_match(
                    event=event,
                    log_group_name=log_group_name,
                    query_time=query_time,
                    query_create_time_ms=create_time_ms,
                )
                if match:
                    matches.append(match)

        matches.sort(key=lambda item: item.get("time_delta_seconds", 999999))
        return matches[: config.CLOUDTRAIL_MAX_MATCHES_PER_QUERY]
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return []


def _lookup_cloudtrail_startqueryexecution_context(session, query_execution_id, submission_time):
    client = _build_cloudtrail_client(session)
    query_time = submission_time.astimezone(timezone.utc)
    window = timedelta(hours=config.CLOUDTRAIL_LOOKUP_WINDOW_HOURS)
    start_time = query_time - window
    end_time = query_time + window

    try:
        paginator = client.get_paginator("lookup_events")
        matches = []
        for page in paginator.paginate(
            LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": "StartQueryExecution"}],
            StartTime=start_time,
            EndTime=end_time,
        ):
            for event in page.get("Events", []):
                match = _extract_cloudtrail_startqueryexecution_match(
                    event=event,
                    query_execution_id=query_execution_id,
                    query_time=query_time,
                )
                if match:
                    matches.append(match)

        matches.sort(key=lambda item: item.get("time_delta_seconds", 999999))
        return matches[: config.CLOUDTRAIL_MAX_MATCHES_PER_QUERY]
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return []


def _extract_cloudtrail_s3_bucket_match(event, bucket_name, target_time):
    raw_event = event.get("CloudTrailEvent")
    if not raw_event:
        return None

    try:
        parsed = json.loads(raw_event)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    request_parameters = parsed.get("requestParameters") or {}
    matched_via = None
    request_bucket_name = request_parameters.get("bucketName")
    if _normalize_text(request_bucket_name) == _normalize_text(bucket_name):
        matched_via = "request_parameters.bucketName"

    if matched_via is None:
        for resource in parsed.get("resources", []) or []:
            resource_arn = (resource.get("ARN") or resource.get("arn") or "").strip()
            if resource_arn.startswith(f"arn:aws:s3:::{bucket_name}"):
                matched_via = "resources.arn"
                break

    if matched_via is None:
        for resource in event.get("Resources", []) or []:
            resource_name = (resource.get("ResourceName") or "").strip()
            if resource_name == bucket_name:
                matched_via = "event.resources"
                break

    if matched_via is None:
        return None

    event_time = event.get("EventTime")
    if event_time is None:
        return None

    user_identity = parsed.get("userIdentity") or {}
    session_issuer = (
        ((user_identity.get("sessionContext") or {}).get("sessionIssuer") or {})
        if isinstance(user_identity, dict)
        else {}
    )
    username = (
        user_identity.get("arn")
        or user_identity.get("userName")
        or session_issuer.get("arn")
        or session_issuer.get("userName")
        or event.get("Username")
    )

    delta_seconds = abs((event_time - target_time).total_seconds())
    return {
        "event_id": event.get("EventId"),
        "event_time": event_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "event_name": event.get("EventName"),
        "event_source": event.get("EventSource"),
        "event_category": parsed.get("eventCategory"),
        "read_only": parsed.get("readOnly"),
        "username": username,
        "source_ip": parsed.get("sourceIPAddress"),
        "user_agent": parsed.get("userAgent"),
        "matched_via": matched_via,
        "time_delta_seconds": round(delta_seconds, 1),
    }


def _summarize_cloudtrail_s3_matches(matches, lookup_region, target_dates):
    if matches is None:
        return {
            "lookup_status": "unavailable",
            "lookup_region": lookup_region,
            "target_dates": target_dates,
        }

    if not matches:
        return {
            "lookup_status": "no_matches",
            "lookup_region": lookup_region,
            "target_dates": target_dates,
            "matched_events_count": 0,
        }

    event_name_counts = {}
    username_counts = {}
    data_event_count = 0

    for match in matches:
        event_name = match.get("event_name") or "unknown"
        username = match.get("username") or "unknown"
        event_name_counts[event_name] = event_name_counts.get(event_name, 0) + 1
        username_counts[username] = username_counts.get(username, 0) + 1
        if match.get("event_category") == "Data":
            data_event_count += 1

    def _top_items(counter_map):
        ranked = sorted(counter_map.items(), key=lambda item: (-item[1], item[0]))
        return [
            {"value": value, "count": count}
            for value, count in ranked[: config.S3_CLOUDTRAIL_MAX_SUMMARY_ITEMS]
        ]

    return {
        "lookup_status": "matched",
        "lookup_region": lookup_region,
        "target_dates": target_dates,
        "matched_events_count": len(matches),
        "matched_data_events_count": data_event_count,
        "top_event_names": _top_items(event_name_counts),
        "top_usernames": _top_items(username_counts),
        "sample_matches": matches[: config.S3_CLOUDTRAIL_MAX_MATCHES],
    }


def _build_target_datetime_for_date(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)


def _determine_s3_cloudtrail_target_dates(anomaly, metrics_summary):
    target_dates = []
    anchor_day = anomaly.get("anchor_day")
    if anchor_day:
        target_dates.append(anchor_day)

    all_requests = metrics_summary.get("AllRequests") or {}
    peak_date = all_requests.get("peak_date")
    if peak_date and peak_date != anchor_day:
        anchor_dt = datetime.strptime(anchor_day, "%Y-%m-%d").date() if anchor_day else None
        peak_dt = datetime.strptime(peak_date, "%Y-%m-%d").date()
        if anchor_dt is None or abs((anchor_dt - peak_dt).days) <= config.S3_CLOUDTRAIL_PEAK_LOOKBACK_DAYS:
            target_dates.append(peak_date)

    return list(dict.fromkeys(target_dates))


def _lookup_cloudtrail_s3_bucket_context(session, bucket_name, target_dates, region_name):
    client = _build_cloudtrail_client(session, region_name=region_name)
    collected_matches = []
    seen_event_ids = set()

    try:
        for target_date in target_dates:
            target_time = _build_target_datetime_for_date(target_date)
            start_time = target_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = target_time.replace(hour=23, minute=59, second=59, microsecond=999999)

            paginator = client.get_paginator("lookup_events")
            for page in paginator.paginate(
                LookupAttributes=[{"AttributeKey": "EventSource", "AttributeValue": "s3.amazonaws.com"}],
                StartTime=start_time,
                EndTime=end_time,
            ):
                for event in page.get("Events", []):
                    match = _extract_cloudtrail_s3_bucket_match(
                        event=event,
                        bucket_name=bucket_name,
                        target_time=target_time,
                    )
                    if not match:
                        continue

                    event_id = match.get("event_id")
                    if event_id and event_id in seen_event_ids:
                        continue
                    if event_id:
                        seen_event_ids.add(event_id)
                    collected_matches.append(match)

                    if len(collected_matches) >= config.S3_CLOUDTRAIL_LOOKUP_MAX_EVENTS:
                        break

                if len(collected_matches) >= config.S3_CLOUDTRAIL_LOOKUP_MAX_EVENTS:
                    break

            if len(collected_matches) >= config.S3_CLOUDTRAIL_LOOKUP_MAX_EVENTS:
                break
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return _summarize_cloudtrail_s3_matches(None, region_name, target_dates)

    collected_matches.sort(
        key=lambda item: (
            item.get("time_delta_seconds", 999999),
            item.get("event_time") or "",
        )
    )
    return _summarize_cloudtrail_s3_matches(collected_matches, region_name, target_dates)


def _normalize_logs_query_definition_map(client):
    definitions_by_signature = {}

    try:
        paginator = client.get_paginator("describe_query_definitions")
        for page in paginator.paginate():
            for query_definition in page.get("queryDefinitions", []):
                query_string = (query_definition.get("queryString") or "").strip()
                for log_group_name in query_definition.get("logGroupNames", []) or []:
                    signature = (log_group_name, query_string)
                    definitions_by_signature[signature] = {
                        "query_definition_id": query_definition.get("queryDefinitionId"),
                        "query_definition_name": query_definition.get("name"),
                    }
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return {}

    return definitions_by_signature


def _collect_log_group_query_activity(session, log_group_name, start_date, end_date):
    client = _build_logs_client(session)
    definitions_by_signature = _normalize_logs_query_definition_map(client)

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=timezone.utc)
    start_epoch_ms = int(start_dt.timestamp() * 1000)
    end_epoch_ms = int(end_dt.timestamp() * 1000)

    query_activity = []
    next_token = None

    try:
        while len(query_activity) < config.LOGS_QUERY_METADATA_MAX_QUERIES:
            request = {
                "logGroupName": log_group_name,
                "maxResults": config.LOGS_QUERY_METADATA_MAX_QUERIES,
            }
            if next_token:
                request["nextToken"] = next_token

            response = client.describe_queries(**request)
            queries = response.get("queries", [])
            if not queries:
                break

            for query in queries:
                create_time_ms = int(query.get("createTime", 0) or 0)
                if create_time_ms and create_time_ms < start_epoch_ms:
                    continue
                if create_time_ms and create_time_ms >= end_epoch_ms:
                    continue

                query_id = query.get("queryId")
                query_string = (query.get("queryString") or "").strip()
                if not query_id:
                    continue

                query_statistics = {}
                try:
                    query_result = client.get_query_results(queryId=query_id)
                    query_statistics = query_result.get("statistics", {}) or {}
                except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
                    query_statistics = {}

                signature = (log_group_name, query_string)
                definition_match = definitions_by_signature.get(signature, {})
                query_activity.append(
                    {
                        "query_id": query_id,
                        "query_definition_id": definition_match.get("query_definition_id"),
                        "query_definition_name": definition_match.get("query_definition_name"),
                        "execution_origin": "query_definition" if definition_match else "unknown",
                        "status": query.get("status"),
                        "create_time": datetime.fromtimestamp(
                            create_time_ms / 1000 if create_time_ms else start_dt.timestamp(),
                            tz=timezone.utc,
                        ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "log_groups": [log_group_name],
                        "bytes_scanned": round(float(query_statistics.get("bytesScanned", 0.0)), 4),
                        "records_matched": round(float(query_statistics.get("recordsMatched", 0.0)), 4),
                        "records_scanned": round(float(query_statistics.get("recordsScanned", 0.0)), 4),
                        "cloudtrail_matches": _lookup_cloudtrail_startquery_context(
                            session=session,
                            log_group_name=log_group_name,
                            create_time_ms=create_time_ms,
                        ),
                    }
                )
                if len(query_activity) >= config.LOGS_QUERY_METADATA_MAX_QUERIES:
                    break

            if len(query_activity) >= config.LOGS_QUERY_METADATA_MAX_QUERIES:
                break

            next_token = response.get("nextToken")
            if not next_token:
                break
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return []

    query_activity.sort(
        key=lambda item: (
            float(item.get("bytes_scanned", 0.0)),
            item.get("create_time") or "",
        ),
        reverse=True,
    )
    return query_activity[: config.LOGS_QUERY_METADATA_MAX_QUERIES]


def _collect_athena_query_activity(session, bucket_name, start_date, end_date):
    client = _build_athena_client(session)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=timezone.utc)
    bucket_marker = _normalize_text(bucket_name)

    collected_queries = []

    try:
        workgroups_response = client.list_work_groups()
        workgroups = [
            item.get("Name")
            for item in workgroups_response.get("WorkGroups", [])[: config.ATHENA_QUERY_METADATA_MAX_WORKGROUPS]
            if item.get("Name")
        ]
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return []

    for workgroup in workgroups:
        next_token = None
        try:
            while len(collected_queries) < config.ATHENA_QUERY_METADATA_MAX_QUERIES * 3:
                request = {
                    "WorkGroup": workgroup,
                    "MaxResults": config.ATHENA_QUERY_METADATA_MAX_QUERIES,
                }
                if next_token:
                    request["NextToken"] = next_token

                response = client.list_query_executions(**request)
                execution_ids = response.get("QueryExecutionIds", [])
                if not execution_ids:
                    break

                batch = client.batch_get_query_execution(QueryExecutionIds=execution_ids)
                for query_execution in batch.get("QueryExecutions", []):
                    status = query_execution.get("Status") or {}
                    statistics = query_execution.get("Statistics") or {}
                    submission_time = status.get("SubmissionDateTime")
                    if submission_time is None:
                        continue
                    submission_time = submission_time.astimezone(timezone.utc)
                    if submission_time < start_dt:
                        continue
                    if submission_time >= end_dt:
                        continue

                    query_text = query_execution.get("Query") or ""
                    result_configuration = query_execution.get("ResultConfiguration") or {}
                    output_location = result_configuration.get("OutputLocation") or ""
                    query_execution_context = query_execution.get("QueryExecutionContext") or {}

                    text_match = bucket_marker and bucket_marker in _normalize_text(query_text)
                    output_match = bucket_marker and bucket_marker in _normalize_text(output_location)
                    if not text_match and not output_match:
                        continue

                    query_execution_id = query_execution.get("QueryExecutionId")
                    if not query_execution_id:
                        continue

                    collected_queries.append(
                        {
                            "query_execution_id": query_execution_id,
                            "workgroup": query_execution.get("WorkGroup") or workgroup,
                            "state": status.get("State"),
                            "submission_time": submission_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "completion_time": (
                                status.get("CompletionDateTime").astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                                if status.get("CompletionDateTime")
                                else None
                            ),
                            "data_scanned_bytes": round(float(statistics.get("DataScannedInBytes", 0.0)), 4),
                            "engine_execution_time_ms": round(float(statistics.get("EngineExecutionTimeInMillis", 0.0)), 4),
                            "total_execution_time_ms": round(float(statistics.get("TotalExecutionTimeInMillis", 0.0)), 4),
                            "query_queue_time_ms": round(float(statistics.get("QueryQueueTimeInMillis", 0.0)), 4),
                            "database": query_execution_context.get("Database"),
                            "catalog": query_execution_context.get("Catalog"),
                            "output_location": output_location or None,
                            "bucket_match_type": (
                                "query_and_output" if text_match and output_match
                                else "query_text" if text_match
                                else "output_location"
                            ),
                            "cloudtrail_matches": _lookup_cloudtrail_startqueryexecution_context(
                                session=session,
                                query_execution_id=query_execution_id,
                                submission_time=submission_time,
                            ),
                        }
                    )

                next_token = response.get("NextToken")
                if not next_token:
                    break
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
            continue

    collected_queries.sort(
        key=lambda item: (
            float(item.get("data_scanned_bytes", 0.0)),
            item.get("submission_time") or "",
        ),
        reverse=True,
    )
    return collected_queries[: config.ATHENA_QUERY_METADATA_MAX_QUERIES]


def _should_collect_athena_query_activity(anomaly, candidate, metrics_summary):
    if candidate.get("resource_id") is None:
        return False

    service_name = (anomaly.get("service") or "").lower()
    usage_type = (anomaly.get("usage_type") or "").lower()
    if "guardduty" not in service_name and "s3" not in service_name:
        return False

    if "paids3dataeventsanalyzed" not in usage_type and "simple storage service" not in service_name and service_name != "s3":
        return False

    all_requests = metrics_summary.get("AllRequests") or {}
    if not all_requests:
        return False

    peak_date = all_requests.get("peak_date")
    anomaly_anchor_day = anomaly.get("anchor_day")
    today_value = float(all_requests.get("today", 0.0) or 0.0)
    avg_value = float(all_requests.get("avg_7d", 0.0) or 0.0)
    delta_pct = float(all_requests.get("delta_pct", 0.0) or 0.0)

    if peak_date == anomaly_anchor_day:
        return True
    if today_value > 0 and avg_value > 0 and today_value >= avg_value * 1.2:
        return True
    if delta_pct >= 20.0:
        return True

    return False


def _should_collect_s3_cloudtrail_activity(anomaly, candidate, metrics_summary):
    if candidate.get("resource_id") is None:
        return False

    service_name = (anomaly.get("service") or "").lower()
    usage_type = (anomaly.get("usage_type") or "").lower()
    if "guardduty" not in service_name and "simple storage service" not in service_name and service_name != "s3":
        return False

    if "paids3dataeventsanalyzed" not in usage_type and "requests" not in usage_type:
        return False

    all_requests = metrics_summary.get("AllRequests") or {}
    if not all_requests:
        return False

    today_value = float(all_requests.get("today", 0.0) or 0.0)
    avg_value = float(all_requests.get("avg_7d", 0.0) or 0.0)
    peak_date = all_requests.get("peak_date")
    anchor_day = anomaly.get("anchor_day")

    if peak_date == anchor_day:
        return True
    if avg_value > 0 and today_value >= avg_value * config.S3_CLOUDTRAIL_TODAY_TO_AVG_RATIO:
        return True

    return False


def _list_ec2_instances(session):
    client = session.client("ec2")
    paginator = client.get_paginator("describe_instances")
    resources = []
    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                tag_map = _tags_to_dict(instance.get("Tags"))
                derived_context, notes = _infer_ec2_context(tag_map)
                resources.append(
                    {
                        "resource_id": instance["InstanceId"],
                        "resource_arn": instance.get("InstanceArn"),
                        "autoscaling_group_name": tag_map.get("aws:autoscaling:groupName"),
                        "tags": tag_map,
                        "derived_context": derived_context,
                        "resource_notes": notes,
                    }
                )
    return resources


def _list_relevant_autoscaling_groups(session):
    client = session.client("autoscaling")
    ec2_client = session.client("ec2")
    paginator = client.get_paginator("describe_auto_scaling_groups")
    resources = []

    for page in paginator.paginate():
        for group in page.get("AutoScalingGroups", []):
            group_name = group["AutoScalingGroupName"]
            tag_map = _tags_to_dict(group.get("Tags"))
            derived_context, notes = _infer_asg_context(group_name, tag_map)
            if "eks_cluster" not in derived_context:
                continue

            instance_ids = [
                instance.get("InstanceId")
                for instance in group.get("Instances", [])
                if instance.get("InstanceId")
            ]
            observed_instance_types = _describe_instance_types_for_ids(ec2_client, instance_ids)
            if observed_instance_types:
                derived_context["observed_instance_types"] = observed_instance_types
                notes.append(
                    "Tipos de instancia observados no ASG durante a descoberta: "
                    + ", ".join(observed_instance_types)
                )

            resources.append(
                {
                    "resource_id": None,
                    "autoscaling_group_name": group_name,
                    "tags": tag_map,
                    "derived_context": derived_context,
                    "resource_notes": notes,
                }
            )

    return resources


RESOURCE_DISCOVERY_HANDLERS = {
    "s3_bucket": _list_s3_buckets,
    "messaging_application": _list_messaging_queues,
    "lambda_function": _list_lambda_functions,
    "sqs_queue": _list_sqs_queues,
    "step_function": _list_step_functions,
    "dynamodb_table": _list_dynamodb_tables,
    "firehose_stream": _list_firehose_streams,
    "glue_job": _list_glue_jobs,
    "load_balancer": _list_load_balancers,
    "nat_gateway": _list_nat_gateways,
    "transit_gateway": _list_transit_gateways,
    "log_group": _list_log_groups,
    "compute_resource": _list_ec2_instances,
}


def _score_resource(metrics_summary):
    if not metrics_summary:
        return 0.0

    deltas = [abs(metric["delta_pct"]) for metric in metrics_summary.values() if metric is not None]
    values = [metric["today"] for metric in metrics_summary.values() if metric is not None]
    score = sum(deltas) + (sum(values) / max(len(values), 1))
    return round(score, 2)


def _score_resource_with_context(resource_payload):
    """
    Score resources with workload-aware emphasis.
    """
    metrics_summary = resource_payload.get("metrics", {})
    if not metrics_summary:
        return 0.0

    derived_context = resource_payload.get("derived_context", {})
    resource_type = resource_payload.get("resource_type")
    anomaly = resource_payload.get("anomaly_context", {})
    workload_role = derived_context.get("autoscaling_role") or derived_context.get("eks_nodegroup_role")
    observed_instance_types = derived_context.get("observed_instance_types", [])
    usage_type_match = _usage_type_matches_instance_types(
        anomaly.get("usage_type"),
        observed_instance_types,
    )

    is_eks_workload = (
        derived_context.get("eks_cluster") in {"prd-sso-ciam", "prd-sso-fachada"}
        or resource_type == "autoscaling_group"
    )
    is_ping_directory = derived_context.get("workload_family") == "ping_directory"
    is_known_s3_bucket = bool(derived_context.get("bucket_role"))

    if is_eks_workload:
        score = 0.0
        for metric_name, pct_weight, peak_weight in (
            ("GroupTotalInstances", 6.0, 1.0),
            ("GroupDesiredCapacity", 2.5, 0.3),
            ("GroupInServiceInstances", 2.0, 0.3),
        ):
            metric = metrics_summary.get(metric_name)
            if metric:
                score += abs(metric.get("delta_pct", 0.0)) * pct_weight
                score += float(metric.get("peak_value", 0.0)) * peak_weight

        cpu_metric = metrics_summary.get("CPUUtilization")
        if cpu_metric:
            score += abs(cpu_metric.get("delta_pct", 0.0)) * 0.3

        # Match the ASG's observed instance type with the Cost Explorer usage type before
        # treating it as a primary compute driver.
        if usage_type_match:
            score += 180
        elif observed_instance_types and anomaly.get("usage_type"):
            score -= 120

        # PDP is the default primary compute suspect for Claro TV+ event-driven demand unless
        # another nodegroup shows clearly stronger and better-aligned evidence.
        if workload_role == "ping_pdp":
            score += 120
        elif workload_role in {"ping_access", "ping_federate"}:
            score += 35
        elif workload_role == "fachada_apis":
            score -= 35
        return round(score, 2)

    score = _score_resource(metrics_summary)
    if is_eks_workload:
        return round(score, 2)

    if is_ping_directory:
        for metric_name in ("NetworkIn", "NetworkOut"):
            metric = metrics_summary.get(metric_name)
            if metric:
                score += abs(metric.get("delta_pct", 0.0)) * 2

    if is_known_s3_bucket:
        score += 500
        for metric_name in ("AllRequests",):
            metric = metrics_summary.get(metric_name)
            if metric:
                score += abs(metric.get("delta_pct", 0.0)) * 2
                if metric.get("peak_date") == resource_payload.get("anomaly_anchor_day"):
                    score += 300

    return round(score, 2)


def _collect_metrics(resource, rule, start_date, end_date):
    if rule["resource_type"] == "messaging_application":
        return metrics_messaging.collect_messaging_metrics(resource, rule, start_date, end_date)
    if rule["resource_type"] == "load_balancer":
        load_balancer_type = resource.get("derived_context", {}).get("lb_type")
        filtered_metrics = [
            metric
            for metric in rule.get("metrics", [])
            if not metric.get("applicable_types") or load_balancer_type in metric.get("applicable_types", [])
        ]
        if not filtered_metrics:
            return {}
        load_balancer_rule = {
            "resource_type": "load_balancer",
            "namespace": resource.get("derived_context", {}).get("cloudwatch_namespace"),
            "metrics": filtered_metrics,
        }
        return metrics_cloudwatch.collect_cloudwatch_metrics(resource, load_balancer_rule, start_date, end_date)
    return metrics_cloudwatch.collect_cloudwatch_metrics(resource, rule, start_date, end_date)


def _usage_type_supports_backup_correlation(usage_type):
    usage_type_lower = (usage_type or "").lower()
    backup_indicators = (
        "snapshot",
        "backup",
        "recoverypoint",
        "recovery-point",
        "ebs:snapshot",
        "ebssnapshot",
    )
    network_exclusions = (
        "natgateway",
        "transitgateway",
        "datatransfer",
        "dataxfer",
        "publicipv4",
        "loadbalancer",
    )
    if any(exclusion in usage_type_lower for exclusion in network_exclusions):
        return False
    return any(indicator in usage_type_lower for indicator in backup_indicators)


def discover_and_enrich_resources(anomaly, rule, start_date, end_date, enable_aws_lookup=True):
    """
    Best-effort resource discovery with metric enrichment for an anomaly.
    """
    if rule is None:
        return []

    resource_type = rule["resource_type"]
    if not enable_aws_lookup:
        return [
            {
                "resource_type": resource_type,
                "resource_id": None,
                "confidence": "low",
                "metrics": {},
                "possible_impacted_services": rule.get("possible_impacted_services", []),
                "hypothesis": rule.get("hypothesis"),
                "notes": ["Lookup AWS desabilitado para esta execucao; correlacao baseada apenas em regras."],
                "score": 0.0,
            }
        ]

    handler = RESOURCE_DISCOVERY_HANDLERS.get(resource_type)
    if handler is None:
        return []

    try:
        session = _build_session()
        candidates = handler(session)
        autoscaling_candidates = (
            _list_relevant_autoscaling_groups(session)
            if resource_type == "compute_resource"
            else []
        )
        ecr_candidates = (
            _list_relevant_ecr_repositories(session)
            if resource_type == "compute_resource"
            else []
        )
        backup_candidates = (
            _list_backup_vaults(session)
            if resource_type == "compute_resource"
            and _usage_type_supports_backup_correlation(anomaly.get("usage_type"))
            else []
        )
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return [
            {
                "resource_type": resource_type,
                "resource_id": None,
                "confidence": "low",
                "metrics": {},
                "possible_impacted_services": rule.get("possible_impacted_services", []),
                "hypothesis": rule.get("hypothesis"),
                "notes": ["Falha ao listar recursos AWS para correlacao automatica."],
            }
        ]

    enriched = []
    for candidate in candidates[: config.MAX_CANDIDATE_RESOURCES]:
        try:
            metrics_summary = _collect_metrics(candidate, rule, start_date, end_date)
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
            metrics_summary = {}
        query_activity = []
        athena_query_activity = []
        cloudtrail_s3_activity = None
        athena_lookup_attempted = False
        if resource_type == "log_group":
            try:
                query_activity = _collect_log_group_query_activity(
                    session=session,
                    log_group_name=candidate.get("resource_id"),
                    start_date=start_date,
                    end_date=end_date,
                )
            except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
                query_activity = []
        if resource_type == "s3_bucket" and _should_collect_athena_query_activity(
            anomaly=anomaly,
            candidate=candidate,
            metrics_summary=metrics_summary,
        ):
            athena_lookup_attempted = True
            try:
                athena_query_activity = _collect_athena_query_activity(
                    session=session,
                    bucket_name=candidate.get("resource_id"),
                    start_date=start_date,
                    end_date=end_date,
                )
            except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
                athena_query_activity = []
        if resource_type == "s3_bucket" and _should_collect_s3_cloudtrail_activity(
            anomaly=anomaly,
            candidate=candidate,
            metrics_summary=metrics_summary,
        ):
            cloudtrail_s3_activity = _lookup_cloudtrail_s3_bucket_context(
                session=session,
                bucket_name=candidate.get("resource_id"),
                target_dates=_determine_s3_cloudtrail_target_dates(anomaly, metrics_summary),
                region_name=candidate.get("derived_context", {}).get("bucket_region") or config.WORKLOAD_REGION,
            )
        candidate_confidence = (
            "medium"
            if metrics_summary or query_activity or athena_query_activity or cloudtrail_s3_activity
            else "low"
        )
        candidate_payload = {
            "resource_type": resource_type,
            "resource_id": candidate.get("resource_id"),
            "resource_arn": candidate.get("resource_arn"),
            "tags": candidate.get("tags", {}),
            "derived_context": candidate.get("derived_context", {}),
            "anomaly_context": {
                "service": anomaly.get("service"),
                "usage_type": anomaly.get("usage_type"),
                "anchor_day": anomaly.get("anchor_day"),
            },
            "anomaly_anchor_day": anomaly.get("anchor_day"),
            "confidence": candidate_confidence,
            "metrics": metrics_summary,
            "query_activity": query_activity,
            "athena_query_activity": athena_query_activity,
            "cloudtrail_s3_activity": cloudtrail_s3_activity,
            "possible_impacted_services": rule.get("possible_impacted_services", []),
            "hypothesis": rule.get("hypothesis"),
        }
        notes = list(candidate.get("resource_notes", []))
        if not metrics_summary:
            notes.append("Nenhuma metrica encontrada para o recurso no periodo consolidado.")
        if resource_type == "log_group" and not query_activity:
            notes.append("Nenhum metadado de query do CloudWatch Logs foi encontrado no periodo consolidado.")
        if resource_type == "s3_bucket" and athena_lookup_attempted and not athena_query_activity:
            notes.append("Nenhum metadado relevante de query do Athena foi encontrado para este bucket no periodo consolidado.")
        if (
            resource_type == "s3_bucket"
            and cloudtrail_s3_activity
            and cloudtrail_s3_activity.get("lookup_status") == "no_matches"
        ):
            notes.append("Nenhum evento relevante de CloudTrail para este bucket foi encontrado nas datas-alvo da anomalia.")
        if notes:
            candidate_payload["notes"] = notes
        candidate_payload["score"] = _score_resource_with_context(candidate_payload)
        enriched.append(candidate_payload)

    enriched.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    if resource_type == "s3_bucket":
        resources_with_metrics = [item for item in enriched if item.get("metrics")]
        known_without_metrics = [
            item for item in enriched
            if item.get("derived_context", {}).get("bucket_role") and not item.get("metrics")
        ]
        top_resources = resources_with_metrics + [
            item for item in known_without_metrics if item not in resources_with_metrics
        ]
        if not top_resources:
            top_resources = enriched
    else:
        top_resources = enriched[: config.MAX_RESOURCES_PER_ANOMALY]

    if resource_type == "compute_resource":
        autoscaling_enriched = []
        for candidate in autoscaling_candidates:
            try:
                metrics_summary = _collect_metrics(candidate, rule, start_date, end_date)
            except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
                metrics_summary = {}

            candidate_payload = {
                "resource_type": "autoscaling_group",
                "resource_id": candidate.get("autoscaling_group_name"),
                "resource_arn": None,
                "autoscaling_group_name": candidate.get("autoscaling_group_name"),
                "tags": candidate.get("tags", {}),
                "derived_context": candidate.get("derived_context", {}),
                "anomaly_context": {
                    "service": anomaly.get("service"),
                    "usage_type": anomaly.get("usage_type"),
                    "anchor_day": anomaly.get("anchor_day"),
                },
                "confidence": "medium" if metrics_summary else "low",
                "metrics": metrics_summary,
                "possible_impacted_services": rule.get("possible_impacted_services", []),
                "hypothesis": "Scaling de nodegroups EKS pode explicar aumento de custo de compute.",
                "notes": list(candidate.get("resource_notes", [])),
            }
            candidate_payload["score"] = _score_resource_with_context(candidate_payload)
            autoscaling_enriched.append(candidate_payload)

        autoscaling_enriched.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        top_resources.extend(autoscaling_enriched)

        ecr_enriched = []
        ecr_rule = {
            "resource_type": "ecr_repository",
            "namespace": "AWS/ECR",
            "metrics": [
                {
                    "name": metric_definition["name"],
                    "stat": metric_definition["stat"],
                    "dimensions": [{"Name": "RepositoryName", "ValueFrom": "resource_id"}],
                }
                for metric_definition in config.ECR_METRICS
            ],
        }
        for candidate in ecr_candidates:
            try:
                metrics_summary = metrics_cloudwatch.collect_cloudwatch_metrics(
                    candidate,
                    ecr_rule,
                    start_date,
                    end_date,
                )
            except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
                metrics_summary = {}

            candidate_payload = {
                "resource_type": "ecr_repository",
                "resource_id": candidate.get("resource_id"),
                "resource_arn": candidate.get("resource_arn"),
                "tags": candidate.get("tags", {}),
                "derived_context": candidate.get("derived_context", {}),
                "confidence": "medium" if metrics_summary else "low",
                "metrics": metrics_summary,
                "possible_impacted_services": ["EKS", "EC2", "ECR"],
                "hypothesis": "Pulls de imagem no ECR podem reforcar evidencias de rollout, restart ou scale-out no EKS.",
                "notes": list(candidate.get("resource_notes", [])) + [
                    "ECR e evidencia complementar de atividade operacional; nao deve ser tratado como causa principal isolada."
                ],
            }
            candidate_payload["score"] = _score_resource(metrics_summary) * 0.2
            ecr_enriched.append(candidate_payload)

        ecr_enriched.sort(key=lambda item: item.get("resource_id") or "")
        top_resources.extend(ecr_enriched)

        backup_enriched = []
        backup_rule = {
            "resource_type": "backup_vault",
            "namespace": "AWS/Backup",
            "metrics": [
                {
                    "name": metric_definition["name"],
                    "stat": metric_definition["stat"],
                    "dimensions": [{"Name": "BackupVaultName", "ValueFrom": "resource_id"}],
                }
                for metric_definition in config.AWS_BACKUP_METRICS
            ],
        }
        for candidate in backup_candidates:
            try:
                metrics_summary = metrics_cloudwatch.collect_cloudwatch_metrics(
                    candidate,
                    backup_rule,
                    start_date,
                    end_date,
                )
            except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
                metrics_summary = {}

            candidate_payload = {
                "resource_type": "backup_vault",
                "resource_id": candidate.get("resource_id"),
                "resource_arn": candidate.get("resource_arn"),
                "tags": candidate.get("tags", {}),
                "derived_context": candidate.get("derived_context", {}),
                "confidence": "medium" if metrics_summary else "low",
                "metrics": metrics_summary,
                "possible_impacted_services": ["EC2", "EBS", "S3", "AWS Backup"],
                "hypothesis": "AWS Backup pode reforcar evidencias de snapshots, recovery points e copias relacionadas a EC2 ou S3.",
                "notes": list(candidate.get("resource_notes", [])) + [
                    "AWS Backup deve ser tratado como evidencia complementar, nao como causa principal isolada."
                ],
            }
            candidate_payload["score"] = _score_resource(metrics_summary) * 0.2
            backup_enriched.append(candidate_payload)

        backup_enriched.sort(key=lambda item: item.get("resource_id") or "")
        top_resources.extend(backup_enriched)

        # Keep the best compute candidates first so the LLM sees the most plausible
        # explanation before lower-signal or merely complementary evidence.
        top_resources.sort(key=lambda item: item.get("score", 0.0), reverse=True)

    if not top_resources:
        return [
            {
                "resource_type": resource_type,
                "resource_id": None,
                "confidence": "low",
                "metrics": {},
                "possible_impacted_services": rule.get("possible_impacted_services", []),
                "hypothesis": rule.get("hypothesis"),
                "notes": ["Nenhum recurso candidato encontrado para a anomalia."],
                "score": 0.0,
            }
        ]

    return top_resources
