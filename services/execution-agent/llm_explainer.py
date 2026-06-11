"""
AI-ADES Execution Agent — Auto DOE 제안 설명 LLM (멀티 프로바이더)

.env LLM_PROVIDER 값에 따라 ollama / claude / openai 중 하나로 런타임 전환한다.
Phase 4 /admin/llm/switch 에서 reinitialize(provider, model)을 호출해
재시작 없이 전환할 수 있도록 모듈 내부 상태(_STATE)로 관리한다.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

PROMPT_TEMPLATE = """레이저 가공 AI Auto DOE 제안입니다.
소재 조건: M1 {m1_length}mm + M2 {m2_length}mm
제안 파라미터: Speed={speed}mm/s, Defocus={defocus}mm, Frequency={frequency}kHz, Power={power}W
예측 결과: Depth={pred_depth}μm, 판정={pred_quality}
시도 횟수: {doe_attempt}회차

운영자에게 이 조건을 추천하는 이유를 2~3문장으로 설명해주세요.
반드시 한국어로만 답변하고, 한자나 중국어, 영어 단어를 섞지 마세요."""

# Phase 4 /admin/llm/switch 에서 reinitialize()로 갱신되는 런타임 상태
_STATE = {
    "provider": os.getenv("LLM_PROVIDER", "ollama"),
    "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
}


def reinitialize(provider: str, model: str):
    """LLM 프로바이더/모델을 재시작 없이 런타임에 전환한다 (Phase 4 /admin/llm/switch 대상)."""
    _STATE["provider"] = provider
    _STATE["model"] = model


def _build_prompt(context: dict) -> str:
    return PROMPT_TEMPLATE.format(
        m1_length=context["m1_length"],
        m2_length=context["m2_length"],
        speed=context["speed"],
        defocus=context["defocus"],
        frequency=context["frequency"],
        power=context["power"],
        pred_depth=context["pred_depth"],
        pred_quality=context["pred_quality"],
        doe_attempt=context["doe_attempt"],
    )


def _call_ollama(prompt: str) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    resp = requests.post(
        f"{base_url}/api/generate",
        json={"model": _STATE["model"], "prompt": prompt, "stream": False},
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


def generate_explanation(context: dict):
    """
    Auto DOE 제안 사유를 자연어로 설명한다.

    Args:
        context: m1_length, m2_length, speed, defocus, frequency, power,
                 pred_depth, pred_quality, doe_attempt 포함

    Returns:
        LLM이 생성한 한국어 설명. 실패 시 None을 반환한다
        (LLM 실패가 /doe/suggest 전체 응답을 막아서는 안 됨).
    """
    prompt = _build_prompt(context)
    provider = _STATE["provider"]

    try:
        if provider == "ollama":
            return _call_ollama(prompt)
        if provider == "claude":
            return _call_claude(prompt)
        if provider == "openai":
            return _call_openai(prompt)
        return None
    except Exception:
        return None
