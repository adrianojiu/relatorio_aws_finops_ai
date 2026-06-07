"""Testes unitarios para o parser de analise IA em `src/renderers/html_report.py`.

Regressao: o relatorio HTML quebrava silenciosamente quando o modelo emitia os
drivers em negrito (`**N. Titulo**`) em vez de heading (`### N. Titulo`), ou em
prosa sem os rotulos **Causa provavel:** / **Evidencias:**. O parser passou a
aceitar ambos os formatos e a usar o corpo livre como fallback.
"""

from renderers.html_report import _parse_ai_analysis, _build_ai_tab


# Formato estruturado que o prompt agora exige: heading + rotulos em negrito.
AI_TEXT_STRUCTURED = """## Resumo executivo
- bullet um
- bullet dois

## Principais drivers

### 1. AWS Glue — SAE1-ETL-DPU-Hour | `desvio esperado`
**Causa provavel:** spike isolado distorceu a media
**Evidencias:** custo voltou ao patamar normal
**Confianca:** media

---

### 2. EC2 - Other — SAE1-NatGateway-Bytes | `anomalia real`
**Causa provavel:** crescimento progressivo do gateway principal
**Evidencias:** +23,5% em bytes e conexoes acima da media
**Confianca:** media

## Recomendacoes

1. **Investigar NAT**: olhar VPC Flow Logs.

**ANALISE CONCLUIDA**
"""

# Formato legado/variante: titulo em negrito e classificacao em linha separada,
# corpo escrito em prosa (sem os rotulos causa/evidencias).
AI_TEXT_BOLD_PROSE = """## Resumo executivo
- resumo unico

## Principais drivers

**1. AWS End User Messaging — SAE1-OutboundSMS-BR | desvio esperado**
**Classificação:** `desvio esperado`
Custo de $128,37 contra media de $190,14 (-32,5%). Filas SQS com queda proporcional.
**Confiança:** alta.

---

**2. Amazon GuardDuty — SAE1-PaidS3DataEventsAnalyzed**
**Classificação:** `efeito em cascata`
Custo de $78,15 (-14,4%). Segue o volume de eventos S3 do bucket lider.
**Confiança:** alta.

## Recomendacoes

1. **Habilitar metricas**: configurar request metrics no bucket.

**ANALISE CONCLUIDA**
"""


class TestParseAiAnalysisStructured:
    """Formato estruturado com heading e rotulos em negrito."""

    def test_parses_all_drivers(self):
        data = _parse_ai_analysis(AI_TEXT_STRUCTURED)
        assert len(data["drivers"]) == 2

    def test_extracts_classification(self):
        data = _parse_ai_analysis(AI_TEXT_STRUCTURED)
        classes = [d["classification"] for d in data["drivers"]]
        assert classes == ["desvio esperado", "anomalia real"]

    def test_extracts_labeled_fields(self):
        data = _parse_ai_analysis(AI_TEXT_STRUCTURED)
        first = data["drivers"][0]
        assert first["causa"]
        assert first["evidencias"]
        assert first["confianca"] == "media"

    def test_confianca_does_not_absorb_next_section(self):
        # Sem '---' entre o ultimo driver e Recomendacoes, a confianca nao pode
        # capturar a secao seguinte.
        data = _parse_ai_analysis(AI_TEXT_STRUCTURED)
        assert data["drivers"][1]["confianca"] == "media"
        assert len(data["recommendations"]) == 1


class TestParseAiAnalysisBoldProse:
    """Formato em negrito com corpo em prosa (sem rotulos causa/evidencias)."""

    def test_parses_bold_titles(self):
        data = _parse_ai_analysis(AI_TEXT_BOLD_PROSE)
        assert len(data["drivers"]) == 2

    def test_title_has_no_residual_asterisks(self):
        data = _parse_ai_analysis(AI_TEXT_BOLD_PROSE)
        assert not data["drivers"][0]["title"].endswith("*")
        assert "AWS End User Messaging" in data["drivers"][0]["title"]

    def test_body_fallback_populated(self):
        # Sem rotulos, o corpo livre deve ser preenchido para nao perder conteudo.
        data = _parse_ai_analysis(AI_TEXT_BOLD_PROSE)
        first = data["drivers"][0]
        assert not first["causa"]
        assert first["body"]
        assert "$128,37" in first["body"]

    def test_body_excludes_section_header(self):
        # O cabecalho "## Principais drivers" nao pode vazar para o corpo.
        data = _parse_ai_analysis(AI_TEXT_BOLD_PROSE)
        assert "Principais drivers" not in data["drivers"][0]["body"]


class TestBuildAiTab:
    """Renderizacao da aba de IA a partir dos dados parseados."""

    def test_renders_one_card_per_driver(self):
        html = _build_ai_tab(_parse_ai_analysis(AI_TEXT_STRUCTURED))
        assert html.count('class="driver-card"') == 2

    def test_classification_summary_counts(self):
        html = _build_ai_tab(_parse_ai_analysis(AI_TEXT_STRUCTURED))
        # 1 anomalia real, 1 desvio esperado, 0 cascata
        assert '<div class="cls-count">1</div>' in html

    def test_bold_prose_renders_fallback_section(self):
        html = _build_ai_tab(_parse_ai_analysis(AI_TEXT_BOLD_PROSE))
        assert html.count('class="driver-card"') == 2
        assert "<strong>Análise</strong>" in html
