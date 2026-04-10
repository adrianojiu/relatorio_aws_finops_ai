"""
Correlation rules for matching cost anomalies to AWS resources and metrics.
"""

import config


def _build_s3_request_metrics():
    return [
        {
            "name": metric_definition["name"],
            "stat": metric_definition["stat"],
            "dimensions": [{"Name": "BucketName", "ValueFrom": "resource_id"}],
            "extra_dimensions": [{"Name": "FilterId", "ValueFrom": "s3_request_filter_id"}],
        }
        for metric_definition in config.S3_REQUEST_METRICS
    ]


def _build_firehose_metrics():
    return [
        {
            "name": metric_definition["name"],
            "stat": metric_definition["stat"],
            "dimensions": [{"Name": "DeliveryStreamName", "ValueFrom": "resource_id"}],
        }
        for metric_definition in config.FIREHOSE_METRICS
    ]


def _build_glue_metrics():
    return [
        {
            "name": metric_definition["name"],
            "stat": metric_definition["stat"],
            "dimensions": [{"Name": "JobName", "ValueFrom": "resource_id"}],
        }
        for metric_definition in config.GLUE_METRICS
    ]


def _build_load_balancer_metrics():
    return [
        {
            "name": metric_definition["name"],
            "stat": metric_definition["stat"],
            "dimensions": [{"Name": "LoadBalancer", "ValueFrom": "load_balancer_dimension"}],
            "applicable_types": metric_definition.get("types", []),
        }
        for metric_definition in config.LOAD_BALANCER_METRICS
    ]


def _build_nat_gateway_metrics():
    return [
        {
            "name": metric_definition["name"],
            "stat": metric_definition["stat"],
            "dimensions": [{"Name": "NatGatewayId", "ValueFrom": "resource_id"}],
        }
        for metric_definition in config.NAT_GATEWAY_METRICS
    ]


def _build_transit_gateway_metrics():
    return [
        {
            "name": metric_definition["name"],
            "stat": metric_definition["stat"],
            "dimensions": [{"Name": "TransitGateway", "ValueFrom": "resource_id"}],
        }
        for metric_definition in config.TRANSIT_GATEWAY_METRICS
    ]


CORRELATION_RULES = [
    {
        "service_names": ["Amazon GuardDuty", "GuardDuty"],
        "usage_type_patterns": ["SAE1-PaidS3DataEventsAnalyzed"],
        "resource_type": "s3_bucket",
        "namespace": "AWS/S3",
        "metrics": _build_s3_request_metrics(),
        "possible_impacted_services": ["S3", "Athena", "Glue", "Lambda"],
        "hypothesis": (
            "Quando o usage type for S3 Data Events analisados pelo GuardDuty, o bucket com pico de requests "
            "ou erros no mesmo periodo e o candidato mais forte para explicar o spike de custo."
        ),
    },
    {
        "service_names": ["Amazon Simple Storage Service", "S3"],
        "resource_type": "s3_bucket",
        "namespace": "AWS/S3",
        "metrics": [
            {
                "name": "BucketSizeBytes",
                "stat": "Average",
                "dimensions": [{"Name": "BucketName", "ValueFrom": "resource_id"}],
                "extra_dimensions": [{"Name": "StorageType", "Value": "StandardStorage"}],
            },
            {
                "name": "NumberOfObjects",
                "stat": "Average",
                "dimensions": [{"Name": "BucketName", "ValueFrom": "resource_id"}],
                "extra_dimensions": [{"Name": "StorageType", "Value": "AllStorageTypes"}],
            },
        ] + _build_s3_request_metrics(),
        "possible_impacted_services": ["GuardDuty", "Backup", "Athena", "Glue", "Data Transfer"],
        "hypothesis": (
            "Bucket com aumento de requests ou erros pode explicar custo direto de S3 "
            "e custos derivados em servicos como GuardDuty, Backup, Athena e Glue."
        ),
    },
    {
        "service_names": ["AWS End User Messaging", "End User Messaging"],
        "resource_type": "messaging_application",
        "namespace": None,
        "metrics": [
            {"name": "SmsPublished", "stat": "Sum"},
            {"name": "SmsDeliverySuccessRate", "stat": "Average"},
        ],
        "possible_impacted_services": ["SQS", "Lambda", "Step Functions"],
        "hypothesis": (
            "Aumento no volume de SMS, reducao de entrega ou retries pode explicar o aumento de custo."
        ),
    },
    {
        "service_names": ["AmazonCloudWatch", "CloudWatch", "AmazonCloudWatch Logs", "CloudWatch Logs"],
        "resource_type": "log_group",
        "namespace": "AWS/Logs",
        "metrics": [
            {
                "name": "IncomingBytes",
                "stat": "Sum",
                "dimensions": [{"Name": "LogGroupName", "ValueFrom": "resource_id"}],
            }
        ],
        "possible_impacted_services": ["Lambda", "EKS", "EC2", "GuardDuty"],
        "hypothesis": (
            "Aumento de ingestao de logs pode explicar custo de CloudWatch Logs e indicar explosao de erros."
        ),
    },
    {
        "service_names": ["AWS Lambda", "Lambda"],
        "resource_type": "lambda_function",
        "namespace": "AWS/Lambda",
        "metrics": [
            {
                "name": "Invocations",
                "stat": "Sum",
                "dimensions": [{"Name": "FunctionName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "Duration",
                "stat": "Average",
                "dimensions": [{"Name": "FunctionName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "Errors",
                "stat": "Sum",
                "dimensions": [{"Name": "FunctionName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "Throttles",
                "stat": "Sum",
                "dimensions": [{"Name": "FunctionName", "ValueFrom": "resource_id"}],
            },
        ],
        "possible_impacted_services": ["CloudWatch Logs", "SQS", "DynamoDB", "S3", "AWS End User Messaging"],
        "hypothesis": (
            "Mais invocacoes, duracao, erros ou throttles podem explicar custo anormal e efeitos em cascata."
        ),
    },
    {
        "service_names": ["Amazon Simple Queue Service", "SQS"],
        "resource_type": "sqs_queue",
        "namespace": "AWS/SQS",
        "metrics": [
            {
                "name": "NumberOfMessagesSent",
                "stat": "Sum",
                "dimensions": [{"Name": "QueueName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "NumberOfMessagesReceived",
                "stat": "Sum",
                "dimensions": [{"Name": "QueueName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "ApproximateNumberOfMessagesVisible",
                "stat": "Average",
                "dimensions": [{"Name": "QueueName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "ApproximateAgeOfOldestMessage",
                "stat": "Maximum",
                "dimensions": [{"Name": "QueueName", "ValueFrom": "resource_id"}],
            },
        ],
        "possible_impacted_services": ["Lambda", "AWS End User Messaging", "Step Functions"],
        "hypothesis": (
            "Pico de mensagens, envelhecimento de fila ou reprocessamento pode indicar anomalia em fluxos de OTP."
        ),
    },
    {
        "service_names": ["AWS Step Functions", "Step Functions"],
        "resource_type": "step_function",
        "namespace": "AWS/States",
        "metrics": [
            {
                "name": "ExecutionsStarted",
                "stat": "Sum",
                "dimensions": [{"Name": "StateMachineArn", "ValueFrom": "resource_arn"}],
            },
            {
                "name": "ExecutionsFailed",
                "stat": "Sum",
                "dimensions": [{"Name": "StateMachineArn", "ValueFrom": "resource_arn"}],
            },
            {
                "name": "ExecutionsAborted",
                "stat": "Sum",
                "dimensions": [{"Name": "StateMachineArn", "ValueFrom": "resource_arn"}],
            },
            {
                "name": "ExecutionTime",
                "stat": "Average",
                "dimensions": [{"Name": "StateMachineArn", "ValueFrom": "resource_arn"}],
            },
        ],
        "possible_impacted_services": ["Lambda", "SQS", "DynamoDB", "AWS End User Messaging"],
        "hypothesis": "Retries, loops ou falhas em state machines podem gerar custo anormal.",
    },
    {
        "service_names": ["Amazon DynamoDB", "DynamoDB"],
        "resource_type": "dynamodb_table",
        "namespace": "AWS/DynamoDB",
        "metrics": [
            {
                "name": "ConsumedReadCapacityUnits",
                "stat": "Sum",
                "dimensions": [{"Name": "TableName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "ConsumedWriteCapacityUnits",
                "stat": "Sum",
                "dimensions": [{"Name": "TableName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "ReadThrottleEvents",
                "stat": "Sum",
                "dimensions": [{"Name": "TableName", "ValueFrom": "resource_id"}],
            },
            {
                "name": "WriteThrottleEvents",
                "stat": "Sum",
                "dimensions": [{"Name": "TableName", "ValueFrom": "resource_id"}],
            },
        ],
        "possible_impacted_services": ["Lambda", "Step Functions", "APIs"],
        "hypothesis": (
            "Aumento de leitura, escrita ou throttling pode indicar carga anormal ou uso ineficiente."
        ),
    },
    {
        "service_names": ["Amazon Kinesis Firehose", "Firehose"],
        "resource_type": "firehose_stream",
        "namespace": "AWS/Firehose",
        "metrics": _build_firehose_metrics(),
        "possible_impacted_services": ["S3", "Glue", "Athena"],
        "hypothesis": "Aumento de volume entregue pode explicar custo anormal de ingestao.",
    },
    {
        "service_names": ["AWS Glue", "Glue"],
        "resource_type": "glue_job",
        "namespace": "Glue",
        "metrics": _build_glue_metrics(),
        "possible_impacted_services": ["S3", "Athena", "Firehose"],
        "hypothesis": (
            "Jobs com maior duracao, volume ou falhas podem explicar aumento de custo em processamento."
        ),
    },
    {
        "service_names": ["Amazon Elastic Load Balancing", "Elastic Load Balancing", "ELB"],
        "resource_type": "load_balancer",
        "namespace": None,
        "metrics": _build_load_balancer_metrics(),
        "possible_impacted_services": ["EKS", "EC2", "CloudWatch Logs", "Data Transfer"],
        "hypothesis": (
            "Requests, bytes processados, fluxos e erros em load balancers podem explicar variacoes de LCU e trafego da plataforma."
        ),
    },
    {
        "service_names": ["EC2 - Other", "EC2-Other"],
        "usage_type_patterns": ["NatGateway-Bytes"],
        "resource_type": "nat_gateway",
        "namespace": "AWS/NATGateway",
        "metrics": _build_nat_gateway_metrics(),
        "possible_impacted_services": ["EKS", "S3", "NAT Gateway", "Data Transfer"],
        "hypothesis": (
            "Bytes e conexoes do NAT Gateway podem explicar variacao de custo em usage types NatGateway-Bytes."
        ),
    },
    {
        "service_names": ["Amazon Virtual Private Cloud", "Amazon VPC", "VPC"],
        "usage_type_patterns": ["TransitGateway-Bytes"],
        "resource_type": "transit_gateway",
        "namespace": "AWS/TransitGateway",
        "metrics": _build_transit_gateway_metrics(),
        "possible_impacted_services": ["EKS", "Load Balancer", "Ping Directory", "Data Transfer"],
        "hypothesis": (
            "BytesIn e BytesOut do Transit Gateway ajudam a confirmar se o custo foi causado por aumento real de trafego de rede."
        ),
    },
    {
        "service_names": ["Amazon Elastic Compute Cloud - Compute", "EC2 - Other", "EC2-Other", "Amazon Elastic Kubernetes Service", "EKS"],
        "resource_type": "compute_resource",
        "namespace": "AWS/EC2",
        "metrics": [
            {
                "name": "NetworkIn",
                "stat": "Sum",
                "dimensions": [{"Name": "InstanceId", "ValueFrom": "resource_id"}],
            },
            {
                "name": "NetworkOut",
                "stat": "Sum",
                "dimensions": [{"Name": "InstanceId", "ValueFrom": "resource_id"}],
            },
            {
                "name": "CPUUtilization",
                "stat": "Average",
                "dimensions": [{"Name": "InstanceId", "ValueFrom": "resource_id"}],
            },
            {
                "name": "GroupDesiredCapacity",
                "stat": "Maximum",
                "dimensions": [{"Name": "AutoScalingGroupName", "ValueFrom": "autoscaling_group_name"}],
                "namespace_override": "AWS/AutoScaling",
            },
            {
                "name": "GroupTotalInstances",
                "stat": "Maximum",
                "dimensions": [{"Name": "AutoScalingGroupName", "ValueFrom": "autoscaling_group_name"}],
                "namespace_override": "AWS/AutoScaling",
            },
            {
                "name": "GroupInServiceInstances",
                "stat": "Average",
                "dimensions": [{"Name": "AutoScalingGroupName", "ValueFrom": "autoscaling_group_name"}],
                "namespace_override": "AWS/AutoScaling",
            },
        ],
        "possible_impacted_services": ["Data Transfer", "NAT Gateway", "CloudWatch Logs", "Load Balancer"],
        "hypothesis": (
            "Para workloads em EKS, aumento de quantidade de instancias ou permanencia em servico "
            "nos nodegroups tende a explicar melhor o custo de compute do que trafego de rede isolado."
        ),
    },
]


def find_rule_for_service(service_name, usage_type=None):
    """
    Resolve the best correlation rule for a Cost Explorer service name and usage type.
    """
    service_name_lower = (service_name or "").lower()
    usage_type_lower = (usage_type or "").lower()
    for rule in CORRELATION_RULES:
        for candidate in rule["service_names"]:
            if candidate.lower() in service_name_lower or service_name_lower in candidate.lower():
                usage_type_patterns = rule.get("usage_type_patterns")
                if usage_type_patterns:
                    if any(pattern.lower() in usage_type_lower for pattern in usage_type_patterns):
                        return rule
                    continue
                return rule
    return None
