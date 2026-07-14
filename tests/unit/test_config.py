"""Testes unitarios para `src/config.py` e contratos de configuracao compartilhada."""

import importlib
import os
from datetime import date


PROJECT_CONTEXT_FIXTURE = """# Projeto CIAM

## Contexto para Bedrock

Este e o contexto operacional do ambiente CIAM.
PDP significa Policy Decision Point.

## Regras de negocio

Aqui vao as regras que nao interessam para o Bedrock.
"""


def _reload_config():
    """Recarrega o modulo para refletir variaveis de ambiente alteradas nos testes."""
    import config as cfg

    return importlib.reload(cfg)


class TestDefaultValues:
    """Verifica constantes padrao importantes do projeto."""

    def test_analysis_days_default(self):
        import config as cfg

        assert cfg.ANALYSIS_DAYS == 15

    def test_offset_days_default(self):
        import config as cfg

        assert cfg.OFFSET_DAYS == 2

    def test_report_retention_months_default(self):
        import config as cfg

        assert cfg.REPORT_RETENTION_MONTHS == 13

    def test_min_daily_cost_usd_default(self):
        import config as cfg

        assert cfg.MIN_DAILY_COST_USD == 20.0

    def test_min_percent_variation_default(self):
        import config as cfg

        assert cfg.MIN_PERCENT_VARIATION == 30.0

    def test_min_absolute_variation_usd_default(self):
        import config as cfg

        assert cfg.MIN_ABSOLUTE_VARIATION_USD == 5.0

    def test_top_n_anomalies_default(self):
        import config as cfg

        assert cfg.TOP_N_ANOMALIES == 10

    def test_aws_region_defaults(self):
        import config as cfg

        assert cfg.AWS_REGION == "us-east-1"
        assert cfg.COST_EXPLORER_REGION == "us-east-1"
        assert cfg.BEDROCK_REGION == "us-east-1"

    def test_bedrock_defaults(self):
        import config as cfg

        assert cfg.ENABLE_BEDROCK is False
        assert cfg.BEDROCK_MODEL_ID == "amazon.nova-pro-v1:0"
        assert cfg.BEDROCK_MAX_TOKENS == 8000
        assert cfg.BEDROCK_TEMPERATURE == 0.2
        assert cfg.BEDROCK_MAX_ANALYSIS_ANOMALIES == 4

    def test_special_services_and_patterns(self):
        import config as cfg

        assert "AWS End User Messaging" in cfg.SPECIAL_SERVICES
        assert "End User Messaging" in cfg.SPECIAL_SERVICES
        assert any("OutboundSMS" in item for item in cfg.SMS_COMPLEMENTARY_USAGE_TYPE_PATTERNS)
        assert any("DeliveryAttempts" in item for item in cfg.SMS_COMPLEMENTARY_USAGE_TYPE_PATTERNS)

    def test_api_operation_services(self):
        import config as cfg

        assert "Amazon Simple Storage Service" in cfg.API_OPERATION_SERVICES
        assert "AmazonCloudWatch" in cfg.API_OPERATION_SERVICES
        assert "AWS End User Messaging" in cfg.API_OPERATION_SERVICES
        assert "EC2 - Other" in cfg.API_OPERATION_SERVICES

    def test_priority_scaling_metric(self):
        import config as cfg

        assert cfg.EKS_PRIMARY_SCALING_METRIC == "GroupTotalInstances"
        assert "GroupTotalInstances" in cfg.BEDROCK_PRIORITY_METRIC_SERIES


class TestEnvVarOverrides:
    """Valida sobrescritas principais via variaveis de ambiente."""

    def test_aws_profile_env(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "meu-profile-teste")

        cfg = _reload_config()

        assert cfg.AWS_PROFILE == "meu-profile-teste"

    def test_bedrock_model_id_env(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-20241022")

        cfg = _reload_config()

        assert cfg.BEDROCK_MODEL_ID == "anthropic.claude-sonnet-20241022"

    def test_cost_explorer_region_env(self, monkeypatch):
        monkeypatch.setenv("COST_EXPLORER_REGION", "sa-east-1")

        cfg = _reload_config()

        assert cfg.COST_EXPLORER_REGION == "sa-east-1"

    def test_bedrock_region_env(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_REGION", "eu-west-1")

        cfg = _reload_config()

        assert cfg.BEDROCK_REGION == "eu-west-1"

    def test_sns_topic_arn_env(self, monkeypatch):
        monkeypatch.setenv("FINOPS_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:test-topic")

        cfg = _reload_config()

        assert cfg.SNS_TOPIC_ARN == "arn:aws:sns:us-east-1:123456789012:test-topic"

    def test_s3_bucket_env(self, monkeypatch):
        monkeypatch.setenv("FINOPS_S3_BUCKET", "my-finops-bucket")

        cfg = _reload_config()

        assert cfg.S3_REPORT_BUCKET == "my-finops-bucket"


class TestProjectContextLoading:
    """Valida leitura de PROJECT_CONTEXT.md e recorte para Bedrock."""

    def test_load_project_context_file_exists(self, monkeypatch, tmp_path):
        import config as cfg

        context_file = tmp_path / "PROJECT_CONTEXT.md"
        context_file.write_text(PROJECT_CONTEXT_FIXTURE, encoding="utf-8")
        monkeypatch.setattr(cfg, "PROJECT_CONTEXT_FILE", str(context_file))

        result = cfg.load_project_context()

        assert "Contexto para Bedrock" in result
        assert "PDP significa Policy Decision Point" in result

    def test_load_project_context_file_missing(self, monkeypatch, tmp_path):
        import config as cfg

        monkeypatch.setattr(cfg, "PROJECT_CONTEXT_FILE", str(tmp_path / "inexistente.md"))

        assert cfg.load_project_context() == ""

    def test_extract_markdown_section_found(self):
        import config as cfg

        text = (
            "# Titulo\n\n"
            "## Contexto para Bedrock\n\n"
            "Aqui vai o contexto operacional.\n\n"
            "## Outra Secao\n\n"
            "Outros dados."
        )

        result = cfg._extract_markdown_section(text, "Contexto para Bedrock")

        assert "Aqui vai o contexto operacional" in result
        assert "Outra Secao" not in result

    def test_extract_markdown_section_not_found(self):
        import config as cfg

        assert cfg._extract_markdown_section("## Outra Secao\n\nDados.", "Contexto para Bedrock") == ""

    def test_load_bedrock_context_uses_curated_section(self, monkeypatch, tmp_path):
        import config as cfg

        context_file = tmp_path / "PROJECT_CONTEXT.md"
        context_file.write_text(PROJECT_CONTEXT_FIXTURE, encoding="utf-8")
        monkeypatch.setattr(cfg, "PROJECT_CONTEXT_FILE", str(context_file))

        result = cfg.load_bedrock_context()

        assert "PDP significa Policy Decision Point" in result
        assert "Regras de negocio" not in result
        assert "Contexto para Bedrock" not in result

    def test_load_bedrock_context_falls_back_to_full_text(self, monkeypatch, tmp_path):
        import config as cfg

        context_file = tmp_path / "PROJECT_CONTEXT.md"
        context_file.write_text("## Outra Secao\n\nDados sem bedrock.", encoding="utf-8")
        monkeypatch.setattr(cfg, "PROJECT_CONTEXT_FILE", str(context_file))

        result = cfg.load_bedrock_context()

        assert "Outra Secao" in result


class TestRetentionCutoff:
    """Valida o helper de retencao em `src/utils.py`."""

    def test_retention_cutoff_13_months(self, monkeypatch):
        import utils

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 4, 15)

        monkeypatch.setattr(utils, "date", FrozenDate)

        assert utils._retention_cutoff(13) == date(2025, 3, 1)

    def test_retention_cutoff_1_month(self, monkeypatch):
        import utils

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 4, 15)

        monkeypatch.setattr(utils, "date", FrozenDate)

        assert utils._retention_cutoff(1) == date(2026, 3, 1)

    def test_retention_cutoff_handles_year_boundary(self, monkeypatch):
        import utils

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 1, 10)

        monkeypatch.setattr(utils, "date", FrozenDate)

        assert utils._retention_cutoff(13) == date(2024, 12, 1)


class TestKnownContextDictionaries:
    """Garante consistencia minima dos dicionarios de contexto conhecido."""

    def test_known_s3_bucket_context_has_required_keys(self):
        import config as cfg

        for bucket_name, context in cfg.KNOWN_S3_BUCKET_CONTEXT.items():
            assert "bucket_role" in context, f"bucket {bucket_name} sem 'bucket_role'"
            assert "request_metrics_filter_id" in context, f"bucket {bucket_name} sem 'request_metrics_filter_id'"
            assert isinstance(context.get("notes", []), list), f"bucket {bucket_name} sem 'notes' como lista"

    def test_known_messaging_queue_context_has_required_keys(self):
        import config as cfg

        for queue_name, context in cfg.KNOWN_MESSAGING_QUEUE_CONTEXT.items():
            assert "queue_role" in context, f"queue {queue_name} sem 'queue_role'"
            assert isinstance(context.get("notes", []), list), f"queue {queue_name} sem 'notes' como lista"

    def test_known_firehose_stream_context_has_required_keys(self):
        import config as cfg

        for stream_name, context in cfg.KNOWN_FIREHOSE_STREAM_CONTEXT.items():
            assert "stream_role" in context, f"firehose {stream_name} sem 'stream_role'"

    def test_known_load_balancer_context_has_required_keys(self):
        import config as cfg

        for lb_name, context in cfg.KNOWN_LOAD_BALANCER_CONTEXT.items():
            assert "lb_type" in context, f"lb {lb_name} sem 'lb_type'"
            assert "lb_role" in context, f"lb {lb_name} sem 'lb_role'"

    def test_s3_usage_family_summaries_has_expected_families(self):
        import config as cfg

        expected_families = {
            "s3_requests",
            "s3_storage_class_transition",
            "s3_storage",
            "s3_retrieval_restore",
            "s3_early_delete",
            "s3_data_transfer",
            "s3_inventory_and_analytics",
            "s3_other",
        }

        assert set(cfg.S3_USAGE_FAMILY_SUMMARIES) == expected_families

    def test_business_event_calendar_file_path_is_configured(self):
        import config as cfg

        assert cfg.BUSINESS_EVENT_CALENDAR_FILE.endswith("Régua de Pushs_SMS Now Online.xlsx")
        assert os.path.basename(cfg.BUSINESS_EVENT_CALENDAR_FILE) == "Régua de Pushs_SMS Now Online.xlsx"
