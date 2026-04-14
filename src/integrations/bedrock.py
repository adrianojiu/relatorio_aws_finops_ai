"""
AWS Bedrock integration for AI analysis
"""

import boto3
import json
import os
from botocore.config import Config as BotoConfig
import config


def _load_prompt_template():
    prompt_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "prompts",
        "finops_analysis.txt",
    )
    if not os.path.exists(prompt_file):
        return None
    with open(prompt_file, "r", encoding="utf-8") as file_handle:
        return file_handle.read().strip()


def build_bedrock_prompt(report_data, context_operational):
    """
    Build the final prompt text sent to Bedrock.
    """
    prompt_template = _load_prompt_template()
    selected_anomalies = report_data.get("anomalies", [])
    selected_topics = [
        f"- {item.get('service')} | {item.get('usage_type') or 'sem usage_type'}"
        for item in selected_anomalies
    ]
    selected_topics_text = "\n".join(selected_topics) if selected_topics else "- Nenhuma anomalia selecionada"

    if prompt_template:
        return (
            f"{prompt_template}\n\n"
            f"Contexto operacional consolidado:\n{context_operational}\n\n"
            f"Itens selecionados para analise principal nesta execucao:\n{selected_topics_text}\n\n"
            "Instrucoes adicionais:\n"
            # Reinforce a short executive answer even when the payload is rich in detail.
            "- Entregue resposta curta, objetiva e executiva.\n"
            "- Selecione apenas os drivers que realmente mudam a leitura do dia.\n"
            "- Evite repetir contexto e detalhes tecnicos que ja nao alteram conclusao.\n"
            "- Restrinja conclusoes e recomendacoes aos itens selecionados para analise principal nesta execucao.\n"
            "- Nao crie recomendacoes sobre S3, GuardDuty ou qualquer outro tema que nao esteja entre os itens selecionados, salvo se forem apenas citados como contexto secundario de um item principal.\n"
            "- Use a janela consolidada que termina no dia de referencia.\n"
            "- Priorize causalidade entre custo, recurso AWS e metricas associadas.\n"
            "- Diferencie hipoteses fortes de hipoteses fracas.\n"
            "- Aponte se uma anomalia de um recurso pode explicar custo em outros servicos.\n\n"
            f"Dados estruturados do relatorio:\n{json.dumps(report_data, indent=2, ensure_ascii=False)}"
        )

    return (
        "Analise o relatorio estruturado abaixo e identifique anomalias, recursos provaveis, "
        "correlacoes operacionais e recomendacoes.\n\n"
        f"Contexto operacional:\n{context_operational}\n\n"
        f"Dados do relatorio:\n{json.dumps(report_data, indent=2, ensure_ascii=False)}"
    )


def _build_openai_messages(prompt):
    """
    Build OpenAI-compatible chat messages.
    """
    return [
        {
            "role": "system",
            "content": "You are a senior FinOps analyst specialized in AWS cost investigation.",
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]


def _build_deepseek_prompt(prompt):
    """
    Wrap the prompt in DeepSeek's recommended instruction format.
    """
    return (
        "<｜begin▁of▁sentence｜><｜User｜>"
        f"{prompt}"
        "<｜Assistant｜><think>\n"
    )


def _build_meta_prompt(prompt):
    """
    Wrap the prompt using Meta Llama Instruct formatting.
    """
    return (
        "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n"
        f"{prompt}\n"
        "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
    )


def _build_request_payload(model_id, prompt):
    """
    Build a provider-specific InvokeModel payload.
    """
    if _is_anthropic_model(model_id):
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": config.BEDROCK_MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        }
                    ],
                }
            ],
        }

    if _is_nova_model(model_id):
        return {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt,
                        }
                    ],
                }
            ],
            "inferenceConfig": {
                "maxTokens": config.BEDROCK_MAX_TOKENS,
                "temperature": config.BEDROCK_TEMPERATURE,
            },
        }

    if _is_openai_model(model_id):
        return {
            "model": model_id,
            "messages": _build_openai_messages(prompt),
            "max_completion_tokens": config.BEDROCK_MAX_TOKENS,
            "temperature": config.BEDROCK_TEMPERATURE,
            "stream": False,
        }

    if _is_deepseek_model(model_id):
        return {
            "prompt": _build_deepseek_prompt(prompt),
            "max_tokens": config.BEDROCK_MAX_TOKENS,
            "temperature": config.BEDROCK_TEMPERATURE,
            "top_p": 0.9,
        }

    if _is_meta_model(model_id):
        max_gen_len = min(config.BEDROCK_MAX_TOKENS, 2048)
        return {
            "prompt": _build_meta_prompt(prompt),
            "max_gen_len": max_gen_len,
            "temperature": config.BEDROCK_TEMPERATURE,
            "top_p": 0.9,
        }

    raise ValueError(
        f"Modelo Bedrock nao suportado pela integracao atual: {model_id}. "
        "Use um modelo anthropic.*, amazon.nova*, openai.*, deepseek.*, meta.llama*, "
        "ou inference profile equivalente."
    )


def _extract_response_text(model_id, response_body):
    """
    Extract text from a provider-specific InvokeModel response.
    """
    if _is_anthropic_model(model_id):
        content = response_body.get("content", [])
        if content:
            return content[0].get("text")
        return None

    if _is_nova_model(model_id):
        output = response_body.get("output", {})
        message = output.get("message", {})
        for item in message.get("content", []):
            if "text" in item:
                return item["text"]
        return None

    if _is_openai_model(model_id):
        choices = response_body.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return message.get("content")
        return None

    if _is_deepseek_model(model_id):
        choices = response_body.get("choices", [])
        if choices:
            return choices[0].get("text")
        return None

    if _is_meta_model(model_id):
        return response_body.get("generation")

    return None


def extract_response_metadata(model_id, response_body):
    """
    Extract provider-specific metadata useful for debugging truncation and token usage.
    """
    metadata = {
        "model_id": model_id,
        "provider": _detect_provider(model_id),
        "raw_keys": sorted(response_body.keys()),
    }

    if _is_anthropic_model(model_id):
        metadata["stop_reason"] = response_body.get("stop_reason")
        metadata["usage"] = response_body.get("usage")
    elif _is_nova_model(model_id):
        metadata["stop_reason"] = response_body.get("stopReason")
        metadata["usage"] = response_body.get("usage")
    elif _is_openai_model(model_id) or _is_deepseek_model(model_id):
        metadata["finish_reasons"] = [choice.get("finish_reason") for choice in response_body.get("choices", [])]
        metadata["usage"] = response_body.get("usage")
    elif _is_meta_model(model_id):
        metadata["stop_reason"] = response_body.get("stop_reason")
        metadata["prompt_token_count"] = response_body.get("prompt_token_count")
        metadata["generation_token_count"] = response_body.get("generation_token_count")

    return metadata


def _detect_provider(model_id):
    if _is_anthropic_model(model_id):
        return "anthropic"
    if _is_nova_model(model_id):
        return "amazon_nova"
    if _is_openai_model(model_id):
        return "openai"
    if _is_deepseek_model(model_id):
        return "deepseek"
    if _is_meta_model(model_id):
        return "meta_llama"
    return "unknown"


def _is_anthropic_model(model_id):
    """
    Accept direct model IDs, inference profile IDs and ARNs for Anthropic.
    """
    return (
        model_id.startswith("anthropic.")
        or model_id.startswith("us.anthropic.")
        or model_id.startswith("global.anthropic.")
        or "anthropic." in model_id
    )


def _is_nova_model(model_id):
    """
    Accept direct model IDs, inference profile IDs and ARNs for Amazon Nova.
    """
    return (
        model_id.startswith("amazon.nova")
        or model_id.startswith("us.amazon.nova")
        or model_id.startswith("global.amazon.nova")
        or "amazon.nova" in model_id
    )


def _is_openai_model(model_id):
    """
    Accept direct model IDs, inference profile IDs and ARNs for OpenAI.
    """
    return (
        model_id.startswith("openai.")
        or model_id.startswith("us.openai.")
        or model_id.startswith("global.openai.")
        or "openai." in model_id
    )


def _is_deepseek_model(model_id):
    """
    Accept direct model IDs, inference profile IDs and ARNs for DeepSeek.
    """
    return (
        model_id.startswith("deepseek.")
        or model_id.startswith("us.deepseek.")
        or model_id.startswith("global.deepseek.")
        or "deepseek." in model_id
    )


def _is_meta_model(model_id):
    """
    Accept direct model IDs, inference profile IDs and ARNs for Meta Llama.
    """
    return (
        model_id.startswith("meta.llama")
        or model_id.startswith("us.meta.llama")
        or model_id.startswith("global.meta.llama")
        or "meta.llama" in model_id
    )


def analyze_with_bedrock(report_data, context_operational):
    """
    Send report data to Bedrock for AI analysis
    """
    if not config.ENABLE_BEDROCK:
        return None

    session = boto3.Session(profile_name=config.AWS_PROFILE, region_name=config.BEDROCK_REGION)
    client_config = BotoConfig(connect_timeout=60, read_timeout=3600)
    bedrock = session.client("bedrock-runtime", config=client_config)
    prompt = build_bedrock_prompt(report_data, context_operational)
    request_payload = _build_request_payload(config.BEDROCK_MODEL_ID, prompt)

    response = bedrock.invoke_model(
        modelId=config.BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(request_payload),
    )

    result = json.loads(response["body"].read())
    return {
        "text": _extract_response_text(config.BEDROCK_MODEL_ID, result),
        "metadata": extract_response_metadata(config.BEDROCK_MODEL_ID, result),
    }
