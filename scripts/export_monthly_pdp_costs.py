#!/usr/bin/env python3
"""
Exporta dois CSVs mensais do Cost Explorer:
- todos os servicos
- somente PDP

Formato de saida alinhado aos exemplos da pasta export_monthly.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import boto3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config


SERVICE_LABEL_OVERRIDES = {
    "Amazon CloudWatch": "CloudWatch",
    "Amazon Simple Storage Service": "S3",
    "Amazon Virtual Private Cloud": "VPC",
    "Amazon Athena": "Athena",
    "Amazon DynamoDB": "DynamoDB",
    "Amazon Route 53": "Route 53",
    "Amazon Simple Queue Service": "SQS",
    "Amazon Simple Notification Service": "SNS",
    "AmazonCloudWatch": "CloudWatch",
    "AWS Backup": "Backup",
    "AWS CloudFormation": "CloudFormation",
    "AWS CloudTrail": "CloudTrail",
    "AWS Config": "Config",
    "AWS Cost Explorer": "Cost Explorer",
    "AWS End User Messaging": "End User Messaging",
    "AWS Glue": "Glue",
    "AWS Key Management Service": "Key Management Service",
    "AWS Lambda": "Lambda",
    "AWS Secrets Manager": "Secrets Manager",
    "AWS Step Functions": "Step Functions",
    "Amazon Elastic Compute Cloud - Compute": "EC2-Instances",
    "Amazon Elastic Compute Cloud - Other": "EC2-Other",
    "Amazon Elastic Container Registry (ECR)": "EC2 Container Registry (ECR)",
    "Amazon GuardDuty": "GuardDuty",
    "Amazon Kinesis Firehose": "Kinesis Firehose",
    "Amazon QuickSight": "QuickSight",
    "Amazon Redshift": "Redshift",
    "AWS Security Hub": "Security Hub",
    "AWS Systems Manager": "Systems Manager",
    "AWS Transfer Family": "Transfer Family",
    "Claude Sonnet 4.6 (Bedrock Edition)": "Claude Sonnet 4.6 ( Bedrock Edition)",
    "EC2 - Other": "EC2-Other",
    "EC2 - Instances": "EC2-Instances",
    "Elastic Load Balancing": "Elastic Load Balancing",
    "Amazon ElastiCache": "ElastiCache",
    "Amazon Elastic Kubernetes Service": "Elastic Container Service for Kubernetes",
    "Savings Plans for AWS Compute usage": "Savings Plans for  Compute usage",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta CSVs mensais do Cost Explorer para todos os servicos e somente PDP."
    )
    parser.add_argument(
        "--month",
        required=True,
        help="Mes de referencia no formato YYYY-MM. Ex.: 2026-03",
    )
    parser.add_argument(
        "--aws-profile",
        default=config.AWS_PROFILE,
        help=f"Perfil AWS CLI. Padrao: {config.AWS_PROFILE}",
    )
    parser.add_argument(
        "--cost-explorer-region",
        default=config.COST_EXPLORER_REGION,
        help=f"Regiao do Cost Explorer. Padrao: {config.COST_EXPLORER_REGION}",
    )
    parser.add_argument(
        "--output-dir",
        default=config.MONTHLY_EXPORT_OUTPUT_DIR,
        help=f"Diretorio de saida. Padrao: {config.MONTHLY_EXPORT_OUTPUT_DIR}",
    )
    return parser.parse_args()


def month_bounds(month_str: str) -> Tuple[str, str]:
    start = datetime.strptime(f"{month_str}-01", "%Y-%m-%d").date()
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start.isoformat(), next_month.isoformat()


def iter_month_days(start_inclusive: str, end_exclusive: str) -> Iterable[str]:
    current = datetime.strptime(start_inclusive, "%Y-%m-%d").date()
    end = datetime.strptime(end_exclusive, "%Y-%m-%d").date()
    while current < end:
        yield current.isoformat()
        current += timedelta(days=1)


def cost_explorer_client(profile: str, region: str):
    session = boto3.Session(profile_name=profile, region_name=region)
    return session.client("ce", region_name=region)


def tag_filter(include_pdp: bool) -> Dict:
    base = {
        "Tags": {
            "Key": "aws:autoscaling:groupName",
            "Values": config.PDP_AUTOSCALING_GROUP_TAG_VALUES,
            "MatchOptions": ["EQUALS"],
        }
    }
    if include_pdp:
        return base
    return {}


def fetch_monthly_daily_service_costs(client, start: str, end: str, include_pdp: bool) -> Dict[str, Dict[str, Decimal]]:
    results: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    token = None
    while True:
        request = {
            "TimePeriod": {"Start": start, "End": end},
            "Granularity": "DAILY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        }
        request_filter = tag_filter(include_pdp)
        if request_filter:
            request["Filter"] = request_filter
        if token:
            request["NextPageToken"] = token
        response = client.get_cost_and_usage(**request)
        for day in response.get("ResultsByTime", []):
            day_key = day["TimePeriod"]["Start"]
            for group in day.get("Groups", []):
                service_name = normalize_service_label(group["Keys"][0])
                amount = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
                results[day_key][service_name] += amount
        token = response.get("NextPageToken")
        if not token:
            return results


def normalize_service_label(service_name: str) -> str:
    return SERVICE_LABEL_OVERRIDES.get(service_name, service_name)


def ordered_services(results: Dict[str, Dict[str, Decimal]]) -> List[str]:
    totals: Dict[str, Decimal] = defaultdict(Decimal)
    for day_data in results.values():
        for service, amount in day_data.items():
            totals[service] += amount
    return [service for service, _ in sorted(totals.items(), key=lambda item: (-item[1], item[0]))]


def decimal_to_str(value: Decimal) -> str:
    if value == 0:
        return ""
    normalized = value.normalize()
    return format(normalized, "f")


def write_csv(path: Path, start: str, end: str, results: Dict[str, Dict[str, Decimal]]) -> None:
    services = ordered_services(results)
    header = ["Service"] + [f"{service}($)" for service in services] + ["Total costs($)"]
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(header)

        totals_row = ["Service total"]
        grand_total = Decimal("0")
        for service in services:
            service_total = sum((results.get(day, {}).get(service, Decimal("0")) for day in iter_month_days(start, end)), Decimal("0"))
            totals_row.append(decimal_to_str(service_total))
            grand_total += service_total
        totals_row.append(decimal_to_str(grand_total))
        writer.writerow(totals_row)

        for day in iter_month_days(start, end):
            row = [day]
            day_total = Decimal("0")
            for service in services:
                amount = results.get(day, {}).get(service, Decimal("0"))
                row.append(decimal_to_str(amount))
                day_total += amount
            row.append(decimal_to_str(day_total))
            writer.writerow(row)


def monthly_output_path(output_dir: Path, base_filename: str, month_str: str) -> Path:
    base_path = Path(base_filename)
    return output_dir / f"{base_path.stem}-{month_str}{base_path.suffix}"


def main() -> None:
    args = parse_args()
    start, end = month_bounds(args.month)
    client = cost_explorer_client(args.aws_profile, args.cost_explorer_region)
    output_dir = Path(args.output_dir)

    all_services = fetch_monthly_daily_service_costs(
        client=client,
        start=start,
        end=end,
        include_pdp=False,
    )
    with_pdp = fetch_monthly_daily_service_costs(
        client=client,
        start=start,
        end=end,
        include_pdp=True,
    )

    all_services_path = monthly_output_path(
        output_dir,
        config.MONTHLY_EXPORT_ALL_SERVICES_FILENAME,
        args.month,
    )
    with_pdp_path = monthly_output_path(
        output_dir,
        config.MONTHLY_EXPORT_ONLY_PDP_FILENAME,
        args.month,
    )

    write_csv(all_services_path, start, end, all_services)
    write_csv(with_pdp_path, start, end, with_pdp)

    print(f"CSV com todos os servicos salvo em: {all_services_path}")
    print(f"CSV somente PDP salvo em: {with_pdp_path}")


if __name__ == "__main__":
    main()
