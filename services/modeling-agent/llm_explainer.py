"""
AI-ADES LLM 연동 — SHAP 분석 결과 자연어 설명

.env의 LLM_PROVIDER 값에 따라 ollama / claude / openai 중 하나로 런타임 전환한다.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

PROMPT_TEMPLATE = """레이저 가공 AI 분석 결과입니다.
소재 조건: M1 {m1_length}mm + M2 {m2_length}mm
SHAP 분석: {shap_dict}
예측 결과: Depth={pred_depth}μm, 판정={pred_quality}

운영자에게 OK 달성을 위한 파라미터 조정 방향을
2~3문장으로 설명해주세요.
반드시 한국어로만 답변하고, 한자나 중국어, 영어 단어를 섞지 마세요."""


def _build_prompt(context: dict) -> str:
    return PROMPT_TEMPLATE.format(
        m1_length=context["m1_length"],
        m2_length=context["m2_length"],
        shap_dict=context["shap_dict"],
        pred_depth=context["pred_depth"],
        pred_quality=context["pred_quality"],
    )


def _call_ollama(prompt: str) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    resp = requests.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


def _call_claude(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_openai(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content.strip()


def generate_explanation(context: dict) -> str:
    """
    SHAP 분석 결과를 자연어로 설명한다.

    Args:
        context: m1_length, m2_length, shap_dict, pred_depth, pred_quality 포함

    Returns:
        LLM이 생성한 한국어 설명 (실패 시 안내 메시지)
    """
    prompt = _build_prompt(context)
    provider = os.getenv("LLM_PROVIDER", "ollama")

    try:
        if provider == "ollama":
            return _call_ollama(prompt)
        if provider == "claude":
            return _call_claude(prompt)
        if provider == "openai":
            return _call_openai(prompt)
        return f"알 수 없는 LLM_PROVIDER 입니다: {provider}"
    except Exception as exc:
        return f"LLM 설명 생성에 실패했습니다 ({provider}): {exc}"
