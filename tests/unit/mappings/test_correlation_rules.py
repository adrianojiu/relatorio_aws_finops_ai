"""Testes unitarios para `src/mappings/correlation_rules.py`."""


class TestFindRuleForService:
    """Valida o matching entre servico/usage type e regras de correlacao."""

    def test_rule_s3(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon Simple Storage Service", "Requests-Tier1")

        assert rule is not None
        assert rule["resource_type"] == "s3_bucket"
        assert rule["namespace"] == "AWS/S3"
        assert any(metric["name"] == "AllRequests" for metric in rule["metrics"])

    def test_rule_guardduty_for_s3_data_events(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon GuardDuty", "SAE1-PaidS3DataEventsAnalyzed")

        assert rule is not None
        assert rule["resource_type"] == "s3_bucket"
        assert "bucket" in rule["hypothesis"].lower()

    def test_rule_vpc_transit_gateway(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon VPC", "TransitGateway-Bytes")

        assert rule is not None
        assert rule["resource_type"] == "transit_gateway"
        assert rule["namespace"] == "AWS/TransitGateway"

    def test_rule_ec2_other_natgateway(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("EC2 - Other", "NatGateway-Bytes")

        assert rule is not None
        assert rule["resource_type"] == "nat_gateway"
        assert rule["namespace"] == "AWS/NATGateway"

    def test_rule_firehose(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon Kinesis Firehose", None)

        assert rule is not None
        assert rule["resource_type"] == "firehose_stream"
        assert rule["namespace"] == "AWS/Firehose"

    def test_rule_glue(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("AWS Glue", None)

        assert rule is not None
        assert rule["resource_type"] == "glue_job"
        assert rule["namespace"] == "Glue"

    def test_rule_load_balancer(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Elastic Load Balancing", "LoadBalancing-Usage")

        assert rule is not None
        assert rule["resource_type"] == "load_balancer"

    def test_rule_end_user_messaging(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("AWS End User Messaging", "OutboundSMS-BR-Standard")

        assert rule is not None
        assert rule["resource_type"] == "messaging_application"
        assert "sms" in rule["hypothesis"].lower()

    def test_rule_compute_covers_eks(self):
        from mappings import correlation_rules as cr
        import config

        rule = cr.find_rule_for_service("Amazon Elastic Kubernetes Service", "EKS-Usage")

        assert rule is not None
        assert rule["resource_type"] == "compute_resource"
        assert any(metric["name"] == config.EKS_PRIMARY_SCALING_METRIC for metric in rule["metrics"])

    def test_rule_cloudwatch(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("AmazonCloudWatch", "DataScanned-Bytes")

        assert rule is not None
        assert rule["resource_type"] == "log_group"
        assert rule["namespace"] == "AWS/Logs"

    def test_no_match_unknown_service(self):
        from mappings import correlation_rules as cr

        assert cr.find_rule_for_service("SomeRandomService", "SomeUsageType") is None

    def test_no_match_when_usage_type_pattern_does_not_match(self):
        from mappings import correlation_rules as cr

        assert cr.find_rule_for_service("Amazon GuardDuty", "SomeOtherGuardDutyMetric") is None


class TestMetricTemplates:
    """Valida a estrutura das metricas declarativas dentro das regras."""

    def test_s3_rule_contains_request_metric_with_filter_dimension(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon Simple Storage Service", "Requests-Tier1")
        request_metric = next(metric for metric in rule["metrics"] if metric["name"] == "AllRequests")

        assert request_metric["dimensions"] == [{"Name": "BucketName", "ValueFrom": "resource_id"}]
        assert request_metric["extra_dimensions"] == [{"Name": "FilterId", "ValueFrom": "s3_request_filter_id"}]

    def test_nat_gateway_rule_declares_nat_dimension(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("EC2 - Other", "NatGateway-Bytes")

        assert all(metric["dimensions"][0]["Name"] == "NatGatewayId" for metric in rule["metrics"])

    def test_transit_gateway_rule_prioritizes_bytes_metrics(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon VPC", "TransitGateway-Bytes")
        metric_names = {metric["name"] for metric in rule["metrics"]}

        assert metric_names == {"BytesIn", "BytesOut"}

    def test_load_balancer_metrics_expose_applicable_types(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("ELB", "LoadBalancing-Usage")

        assert any("applicable_types" in metric for metric in rule["metrics"])
        assert all(metric["dimensions"][0]["Name"] == "LoadBalancer" for metric in rule["metrics"])

    def test_firehose_metrics_use_delivery_stream_dimension(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon Kinesis Firehose", None)

        assert all(metric["dimensions"][0]["Name"] == "DeliveryStreamName" for metric in rule["metrics"])

    def test_glue_metrics_use_job_name_dimension(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("AWS Glue", None)

        assert all(metric["dimensions"][0]["Name"] == "JobName" for metric in rule["metrics"])

    def test_compute_rule_contains_ec2_and_autoscaling_dimensions(self):
        from mappings import correlation_rules as cr

        rule = cr.find_rule_for_service("Amazon Elastic Kubernetes Service", "EKS-Usage")
        dimension_names = {metric["dimensions"][0]["Name"] for metric in rule["metrics"]}

        assert "InstanceId" in dimension_names
        assert "AutoScalingGroupName" in dimension_names


class TestCorrelationRulesCatalog:
    """Valida a consistencia minima do catalogo declarativo."""

    def test_correlation_rules_is_list(self):
        from mappings import correlation_rules as cr

        assert isinstance(cr.CORRELATION_RULES, list)
        assert cr.CORRELATION_RULES

    def test_each_rule_has_required_keys(self):
        from mappings import correlation_rules as cr

        for rule in cr.CORRELATION_RULES:
            assert "service_names" in rule
            assert "resource_type" in rule
            assert "metrics" in rule
            assert "hypothesis" in rule
            assert isinstance(rule["metrics"], list)

    def test_main_services_can_be_resolved(self):
        from mappings import correlation_rules as cr

        assert cr.find_rule_for_service("Amazon Simple Storage Service", None) is not None
        assert cr.find_rule_for_service("Amazon GuardDuty", "SAE1-PaidS3DataEventsAnalyzed") is not None
        assert cr.find_rule_for_service("EC2 - Other", "NatGateway-Bytes") is not None
        assert cr.find_rule_for_service("AWS End User Messaging", None) is not None
