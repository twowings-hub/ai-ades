"""
AI-ADES Execution Agent — Auto DOE 제안 설명 LLM (멀티 프로바이더)

.env LLM_PROVIDER 값에 따라 ollama / claude / openai 중 하나로 런타임 전환한다.
Phase 4 /admin/llm/switch 에서 reinitialize(provider, model)을 호출해
재시작 없이 전환할 수 있도록 모듈 내부 상태(_STATE)로 관리한다.
"""
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

PROMPT_TEMPLATE = """당신은 CO2 레이저로 Glass(M1)+Film(M2) 적층 소재를 절단하는 공정의 가공 조건 최적화 전문가입니다.
아래는 AI Auto DOE가 제안한 다음 실험 조건과, 모델 예측의 근거(SHAP 기여도)입니다.

[소재 조건] M1 {m1_length}mm + M2 {m2_length}mm, Thickness {thickness}μm
[제안 파라미터] Speed={speed}mm/s, Defocus={defocus}mm, Frequency={frequency}kHz, Power={power}W
[모델 예측] Depth={pred_depth}μm → 판정 {pred_quality}
[목표] OK 판정 = Depth {depth_ok_min}μm 초과 ~ {depth_ok_max}μm 이하
[시도] {doe_attempt}회차

[SHAP — 각 변수가 이 Depth 예측에 기여한 정도 (양수=Depth를 키운 방향, 음수=줄인 방향)]
{shap_summary}

[국소 What-if — 한 파라미터만 한 단계 바꿨을 때 모델이 예측한 Depth 변화 (조정 방향 판단의 직접 근거)]
{whatif_summary}

[참고: 변수 관계] 에너지 밀도 = Power / Speed (클수록 Depth가 커지는 경향). 즉 Power를 올리거나 Speed를 낮추면 에너지 밀도가 커집니다.

전문가로서 아래를 2~4문장의 한국어로 설명하세요.
1) 위 SHAP 상위 변수를 근거로, 현재 조건이 왜 그렇게 예측됐는지 해석.
2) 판정이 OK이면 이 조건이 적절한 이유를, OK가 아니면 운영자가 조정 가능한 4개 파라미터(Speed/Defocus/Frequency/Power) 중 무엇을 어느 방향으로 바꾸면 OK에 가까워질지 한 가지를 구체적으로 제안. 이때 위 '국소 What-if'의 Depth 변화량을 직접 근거로 삼아 방향과 크기를 정하세요. 단, 탐색공간(Speed 200/500/1000, Defocus 0~4, Frequency 100/200, Power 2.8~59.8) 안에서만 제안하세요.
3) 이는 모델 기반 제안이므로 실측 확인이 필요하다는 점을 한 문장으로 덧붙이세요.

반드시 한국어 한글로만 답변하고, 한자나 중국어, 영어 단어를 섞지 마세요."""

RESULT_PROMPT_TEMPLATE = """레이저 가공 AI Auto DOE 실험 결과 보고입니다.
소재 조건: M1 {m1_length}mm + M2 {m2_length}mm
가공 파라미터: Speed={speed}mm/s, Defocus={defocus}mm, Frequency={frequency}kHz, Power={power}W
예측값: Kerf={pred_kerf}μm, Depth={pred_depth}μm, 예측 판정={pred_quality}
실측값: Kerf={actual_kerf}μm, Depth={actual_depth}μm, 실측 판정={quality}
시도 횟수: {doe_attempt}회차

위 실험 결과를 보고서에 기록할 메모로 2~3문장으로 작성해주세요.
실측 판정 결과와 예측값 대비 실측값의 차이를 짧게 언급하고, 특이사항이 있다면 포함하세요.
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


# SHAP feature 키 → 프롬프트용 한국어 라벨 (원본 입력 + 파생 변수)
_FEATURE_LABELS_KO = {
    "speed": "Speed(속도)",
    "defocus": "Defocus(초점)",
    "frequency": "Frequency(주파수)",
    "power": "Power(출력)",
    "thickness": "Thickness(두께)",
    "m1_length": "M1 길이",
    "m2_length": "M2 길이",
    "energy_density": "에너지 밀도(Power/Speed)",
    "normalized_power": "정규화 출력",
    "power_x_defocus": "출력×초점",
    "freq_x_power": "주파수×출력",
    "thickness_ratio": "두께 비율",
}


def _format_shap(shap_values: dict | None, top_n: int = 5) -> str:
    """SHAP 기여도를 |값| 큰 순으로 상위 top_n개만 프롬프트용 문자열로 만든다."""
    if not shap_values:
        return "(SHAP 정보 없음)"
    items = sorted(shap_values.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
    lines = []
    for feat, val in items:
        label = _FEATURE_LABELS_KO.get(feat, feat)
        direction = "Depth를 키움" if val >= 0 else "Depth를 줄임"
        lines.append(f"- {label}: {val:+.2f} ({direction})")
    return "\n".join(lines)


def _build_prompt(context: dict) -> str:
    return PROMPT_TEMPLATE.format(
        m1_length=context["m1_length"],
        m2_length=context["m2_length"],
        thickness=context.get("thickness", "-"),
        speed=context["speed"],
        defocus=context["defocus"],
        frequency=context["frequency"],
        power=context["power"],
        pred_depth=context["pred_depth"],
        pred_quality=context["pred_quality"],
        depth_ok_min=context.get("depth_ok_min", 0.0),
        depth_ok_max=context.get("depth_ok_max", 25.0),
        shap_summary=_format_shap(context.get("shap_values")),
        whatif_summary=context.get("whatif_summary") or "(국소 민감도 정보 없음)",
        doe_attempt=context["doe_attempt"],
    )


def _build_result_prompt(context: dict) -> str:
    return RESULT_PROMPT_TEMPLATE.format(
        m1_length=context["m1_length"],
        m2_length=context["m2_length"],
        speed=context["speed"],
        defocus=context["defocus"],
        frequency=context["frequency"],
        power=context["power"],
        pred_kerf=context["pred_kerf"],
        pred_depth=context["pred_depth"],
        pred_quality=context["pred_quality"],
        actual_kerf=context["actual_kerf"],
        actual_depth=context["actual_depth"],
        quality=context["quality"],
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
        max_tokens=1024,
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


# 한자/중국어 문자(CJK 통합 한자 + 중국어 전각 문장부호) 검출용. 한글(Hangul)은 이 범위에
# 포함되지 않으므로 매칭되면 무조건 한자/중국어가 섞여 있다는 의미이다.
_HANJA_PATTERN = re.compile(r"[一-鿿，。：；！？]")

RETRY_NOTE = "\n\n(주의: 이전 답변에 한자/중국어가 섞여 있었습니다. 한자나 중국어를 전혀 사용하지 말고 한국어 한글로만 다시 작성해주세요.)"


def _call_provider(prompt: str, provider: str | None = None):
    provider = provider or _STATE["provider"]

    if provider == "ollama":
        return _call_ollama(prompt)
    if provider == "claude":
        return _call_claude(prompt)
    if provider == "openai":
        return _call_openai(prompt)
    return None


def _call_llm(prompt: str, provider: str | None = None):
    """
    LLM을 호출한다. provider를 지정하면 전역 설정(_STATE) 대신 해당 프로바이더를 사용한다
    (예: 채팅 전용으로 Claude를 쓰고 싶을 때).

    응답에 한자/중국어가 섞여 있으면 한 번 더 강화된 지시와 함께 재시도한다.
    재시도에도 한자/중국어가 섞여 있으면 (일부만 제거하면 문장이 깨지므로) None을 반환한다.
    실패 시 None을 반환한다.
    """
    try:
        result = _call_provider(prompt, provider)
        if result and _HANJA_PATTERN.search(result):
            result = _call_provider(prompt + RETRY_NOTE, provider)
            if result and _HANJA_PATTERN.search(result):
                return None
        return result
    except Exception:
        return None


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
    return _call_llm(_build_prompt(context))


def generate_result_evaluation(context: dict):
    """
    실험 결과(예측값 vs 실측값)를 보고용 메모 형태로 평가한다.

    Args:
        context: m1_length, m2_length, speed, defocus, frequency, power,
                 pred_kerf, pred_depth, pred_quality,
                 actual_kerf, actual_depth, quality, doe_attempt 포함

    Returns:
        LLM이 생성한 한국어 평가 메모. 실패 시 None을 반환한다
        (LLM 실패가 /doe/evaluate 전체 응답을 막아서는 안 됨. 운영자가 직접 작성하면 됨).
    """
    return _call_llm(_build_result_prompt(context))
