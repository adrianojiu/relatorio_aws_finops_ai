"""
Testes unitarios para src/collectors/compute_optimizer.py

Usa mocks de boto3 (unittest.mock) para simular respostas do Compute Optimizer
sem depender de credenciais ou chamadas reais a AWS.

Cobre:
  - get_ec2_recommendations: parsing de recomendacoes EC2 e extracao de savings/CPU
  - get_asg_recommendations: parsing de recomendacoes de Auto Scaling Group
  - get_ecs_recommendations: parsing de recomendacoes ECS
  - collect_all_recommendations: agregacao das tres fontes
  - comportamento fail-safe: excecao da API retorna lista vazia, nunca propaga
"""
from unittest.mock import MagicMock, patch

import pytest


def _paginator_returning(pages):
    paginator = MagicMock()
    paginator.paginate.return_value = pages
    return paginator


class TestGetEc2Recommendations:
    def test_parses_recommendation_with_savings_and_cpu(self):
        from collectors import compute_optimizer

        page = {
            "instanceRecommendations": [
                {
                    "instanceArn": "arn:aws:ec2:us-east-1:123:instance/i-abc",
                    "instanceName": "ping-directory-primary",
                    "currentInstanceType": "r6i.4xlarge",
                    "finding": "OVER_PROVISIONED",
                    "utilizationMetrics": [
                        {"name": "CPU", "statistic": "AVERAGE", "value": 8.5},
                    ],
                    "recommendationOptions": [
                        {
                            "instanceType": "r6i.2xlarge",
                            "savingsOpportunity": {
                                "estimatedMonthlySavings": {"value": 120.5}
                            },
                        }
                    ],
                }
            ]
        }
        client = MagicMock()
        client.get_paginator.return_value = _paginator_returning([page])

        with patch("collectors.compute_optimizer._build_client", return_value=client):
            result = compute_optimizer.get_ec2_recommendations()

        assert len(result) == 1
        rec = result[0]
        assert rec["resource_type"] == "ec2_instance"
        assert rec["current_type"] == "r6i.4xlarge"
        assert rec["recommended_type"] == "r6i.2xlarge"
        assert rec["finding"] == "OVER_PROVISIONED"
        assert rec["cpu_utilization_avg_pct"] == 8.5
        assert rec["savings_usd_monthly"] == 120.5

    def test_recommendation_without_options_has_empty_recommended_type(self):
        from collectors import compute_optimizer

        page = {
            "instanceRecommendations": [
                {
                    "instanceArn": "arn:aws:ec2:us-east-1:123:instance/i-xyz",
                    "currentInstanceType": "t3.medium",
                    "finding": "OPTIMIZED",
                    "recommendationOptions": [],
                }
            ]
        }
        client = MagicMock()
        client.get_paginator.return_value = _paginator_returning([page])

        with patch("collectors.compute_optimizer._build_client", return_value=client):
            result = compute_optimizer.get_ec2_recommendations()

        assert result[0]["recommended_type"] == ""
        assert result[0]["savings_usd_monthly"] == 0.0

    def test_api_error_returns_empty_list(self):
        from collectors import compute_optimizer

        with patch("collectors.compute_optimizer._build_client", side_effect=Exception("AccessDenied")):
            result = compute_optimizer.get_ec2_recommendations()

        assert result == []


class TestGetAsgRecommendations:
    def test_parses_asg_recommendation(self):
        from collectors import compute_optimizer

        page = {
            "autoScalingGroupRecommendations": [
                {
                    "autoScalingGroupArn": "arn:aws:autoscaling:us-east-1:123:autoScalingGroup:x",
                    "autoScalingGroupName": "ping-pdp-app",
                    "finding": "OVER_PROVISIONED",
                    "currentConfiguration": {"instanceType": "m5.xlarge"},
                    "recommendationOptions": [
                        {
                            "configuration": {"instanceType": "m5.large"},
                            "savingsOpportunity": {
                                "estimatedMonthlySavings": {"value": 45.0}
                            },
                        }
                    ],
                }
            ]
        }
        client = MagicMock()
        client.get_paginator.return_value = _paginator_returning([page])

        with patch("collectors.compute_optimizer._build_client", return_value=client):
            result = compute_optimizer.get_asg_recommendations()

        assert len(result) == 1
        assert result[0]["resource_type"] == "asg"
        assert result[0]["resource_name"] == "ping-pdp-app"
        assert result[0]["recommended_type"] == "m5.large"
        assert result[0]["savings_usd_monthly"] == 45.0

    def test_api_error_returns_empty_list(self):
        from collectors import compute_optimizer

        with patch("collectors.compute_optimizer._build_client", side_effect=Exception("Throttling")):
            result = compute_optimizer.get_asg_recommendations()

        assert result == []


class TestGetEcsRecommendations:
    def test_parses_ecs_recommendation_and_extracts_service_name(self):
        from collectors import compute_optimizer

        page = {
            "ecsServiceRecommendations": [
                {
                    "serviceArn": "arn:aws:ecs:us-east-1:123:service/cluster/my-service",
                    "finding": "OVER_PROVISIONED",
                    "currentServiceConfiguration": {"cpu": "1024", "memory": "2048"},
                    "recommendationOptions": [
                        {
                            "containerRecommendations": [{"cpu": 512, "memory": 1024}],
                            "savingsOpportunity": {
                                "estimatedMonthlySavings": {"value": 10.0}
                            },
                        }
                    ],
                }
            ]
        }
        client = MagicMock()
        client.get_paginator.return_value = _paginator_returning([page])

        with patch("collectors.compute_optimizer._build_client", return_value=client):
            result = compute_optimizer.get_ecs_recommendations()

        assert result[0]["resource_name"] == "my-service"
        assert result[0]["current_type"] == "cpu=1024 mem=2048"

    def test_api_error_returns_empty_list(self):
        from collectors import compute_optimizer

        with patch("collectors.compute_optimizer._build_client", side_effect=Exception("Unavailable")):
            result = compute_optimizer.get_ecs_recommendations()

        assert result == []


class TestCollectAllRecommendations:
    def test_aggregates_all_three_sources(self):
        from collectors import compute_optimizer

        ec2_rec = [{"resource_type": "ec2_instance", "savings_usd_monthly": 100.0}]
        asg_rec = [{"resource_type": "asg", "savings_usd_monthly": 50.0}]
        ecs_rec = [{"resource_type": "ecs_service", "savings_usd_monthly": 0.0}]

        with patch("collectors.compute_optimizer.get_ec2_recommendations", return_value=ec2_rec), \
             patch("collectors.compute_optimizer.get_asg_recommendations", return_value=asg_rec), \
             patch("collectors.compute_optimizer.get_ecs_recommendations", return_value=ecs_rec):
            result = compute_optimizer.collect_all_recommendations()

        assert len(result) == 3
        assert result == ec2_rec + asg_rec + ecs_rec

    def test_partial_failure_does_not_break_aggregation(self):
        from collectors import compute_optimizer

        with patch("collectors.compute_optimizer.get_ec2_recommendations", return_value=[]), \
             patch("collectors.compute_optimizer.get_asg_recommendations", return_value=[{"savings_usd_monthly": 20.0}]), \
             patch("collectors.compute_optimizer.get_ecs_recommendations", return_value=[]):
            result = compute_optimizer.collect_all_recommendations()

        assert len(result) == 1
