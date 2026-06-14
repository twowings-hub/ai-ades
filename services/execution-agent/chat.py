"""
AI-ADES Execution Agent — 실험 결과 기반 AI 채팅(Q&A)

운영자가 실험 이력/레시피 등 시스템 데이터를 자연어로 질의할 수 있도록,
DB 요약 정보를 프롬프트 컨텍스트로 주입해 LLM이 답변을 생성한다 (RAG 없는 간단한 방식).
"""
import os

from dotenv import load_dotenv

from db import get_connection
from llm_explainer import _call_llm

load_dotenv()

# 프롬프트에 포함할 최근 실험 건수
CHAT_CONTEXT_RECENT_LIMIT = int(os.getenv("CHAT_CONTEXT_RECENT_LIMIT", 10))

# AI 채팅 전용 LLM 프로바이더 (다른 LLM 호출(AI 평가/설명)은 LLM_PROVIDER 설정을 그대로 사용)
CHAT_LLM_PROVIDER = os.getenv("CHAT_LLM_PROVIDER", "ollama")

# 시스템 소개/사용법 — DB 데이터가 아닌 고정 안내문 (운영자가 "이 시스템 뭐야",
# "어떻게 사용해" 같은 질문을 할 때 참고)
# 메뉴 추가/변경 시 frontend/src/components/Layout.jsx의 nav도 함께 업데이트할 것
SYSTEM_GUIDE = """AI-ADES(AI Autonomous Data Evaluation System)는 CO2 레이저로 Glass(M1) + Film(M2)
적층 소재를 절단할 때, AI가 최적의 레이저 가공 조건(Speed, Defocus, Frequency, Power)을
자동으로 찾아주는 시스템입니다. 기존에는 수동으로 30~50회 실험이 필요했지만, 이 시스템을 쓰면
5~7회 정도로 줄이는 것을 목표로 합니다. 운영자는 AI가 제안한 조건을 검토하고 승인 버튼만
누르면 됩니다 (Human-in-the-Loop).

판정 기준:
- OK: Depth가 0μm 초과 25μm 이하
- 과가공: Depth가 0μm
- 미가공: Depth가 25μm 초과
- NG: Defect(불량) 감지

화면 메뉴 구성과 사용법:
- 실험 조건: M1(Glass)/M2(Film) 소재 종류, 길이, 두께 등 소재 정보를 입력하고 AI Auto DOE 제안을 요청하는 화면입니다.
- AI 제안 승인: AI가 제안한 Speed/Defocus/Frequency/Power 조건과 예측 결과(Depth, 판정)를 확인하고 승인 또는 거부하는 화면입니다.
- 결과 보고: 승인된 조건으로 실제 레이저 가공을 한 뒤, 실측한 Kerf/Depth 값과 판정 결과를 입력하는 화면입니다. AI 평가로 채우기 버튼으로 결과 메모를 자동 생성할 수 있습니다.
- 레시피 조회: 과거 실험에서 OK 판정을 받아 승인된 소재 조합별 추천 가공 조건(레시피) 목록을 조회하는 화면입니다.
- 실험 이력: 지금까지 진행한 모든 실험의 입력값/가공 조건/측정 결과와 설명을 조회하는 화면입니다.
- AI 채팅: 지금 사용 중인 이 화면으로, 시스템에 저장된 데이터에 대해 자연어로 질문할 수 있습니다.
- 관리자: 소재 종류 관리, AI 모델 재학습, LLM 프로바이더 전환, 알림 설정, 메일 서버(SMTP) 설정 등 시스템 설정을 관리하는 화면입니다."""


CHAT_SYSTEM_TEMPLATE = """당신은 CO2 레이저 가공 AI Auto DOE 시스템(AI-ADES)의 운영 데이터를 설명하는 어시스턴트입니다.
아래는 시스템 소개/사용법과, 현재 시스템에 저장된 실험/레시피 데이터 요약입니다. 이 정보를 바탕으로 운영자의 질문에 답변하세요.

[시스템 소개 및 사용법]
{system_guide}

[전체 실험 현황]
{summary}

[등록된 소재 종류]
{material_types}

[최신 AI 모델 성능]
{model_metrics}

[플라즈마 측정 현황]
{plasma}

[승인된 레시피 목록]
{recipes}

[최근 실험 {recent_limit}건 — "최근에 어떤 실험을 했는지" 질문에만 참고. 통계/비율 계산에는 사용 금지]
{recent}

[소재 조합별 현황 — 건수/비율/통계 질문은 반드시 이 표의 값을 그대로 사용. 직접 계산하지 말 것]
{by_material}

답변 규칙:
- 화면이 일반 텍스트만 표시하므로 마크다운 문법(#, *, |, ---, ``` 등)을 사용하지 말고 줄바꿈과 "-" 목록만 사용하세요.
- 문장은 한국어로 작성하되, M1/M2, Speed/Defocus/Frequency/Power, Depth/Kerf, OK 같은
  소재/파라미터/판정 명칭은 영어 표기 그대로 사용하세요 (예: "엠원" 대신 "M1").
  단, 한자나 중국어는 절대 사용하지 마세요.
- 위 데이터에 없는 내용은 추측하지 말고 모른다고 답변하세요.
- 판정 기준: Depth는 0μm 초과 25μm 이하일 때 OK, 0이면 과가공, 25μm 초과면 미가공입니다.
- 특정 소재 조합의 건수/비율/OK 비율을 물으면 [소재 조합별 현황] 표에서 해당 조합 행을 찾아
  그 행에 적힌 총 건수/OK 건수/OK 비율(%)을 그대로 답변하세요. [최근 실험] 목록의 건수를 세서
  답변하면 안 됩니다."""


def _fetch_summary(cur) -> str:
    cur.execute("SELECT quality, COUNT(*) FROM experiments GROUP BY quality")
    rows = cur.fetchall()
    total = sum(count for _, count in rows)
    parts = [f"전체 {total}건"] + [f"{quality}: {count}건" for quality, count in rows]
    return ", ".join(parts)


def _fetch_by_material(cur) -> str:
    cur.execute(
        """
        SELECT m1_glass, m1_length_mm, m2_film, m2_length_mm,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE quality = 'OK') AS ok_count
        FROM experiments
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 4
        """
    )
    lines = [
        f"- {m1_glass} {m1_length}mm + {m2_film} {m2_length}mm: 총 {total}건, OK {ok_count}건, "
        f"OK 비율 {ok_count / total * 100:.1f}%"
        for m1_glass, m1_length, m2_film, m2_length, total, ok_count in cur.fetchall()
    ]
    return "\n".join(lines) if lines else "(데이터 없음)"


def _fetch_material_types(cur) -> str:
    cur.execute(
        """
        SELECT category, name, description
        FROM material_types
        WHERE is_active = true
        ORDER BY category, name
        """
    )
    lines = [
        f"- [{category.upper()}] {name}" + (f" — {description}" if description else "")
        for category, name, description in cur.fetchall()
    ]
    return "\n".join(lines) if lines else "(데이터 없음)"


def _fetch_model_metrics(cur) -> str:
    cur.execute(
        """
        SELECT trained_at, n_experiments, kerf_r2, kerf_rmse, depth_r2, depth_rmse,
               quality_accuracy, quality_f1_macro
        FROM model_metrics
        ORDER BY trained_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        return "(학습 이력 없음)"

    trained_at, n_experiments, kerf_r2, kerf_rmse, depth_r2, depth_rmse, quality_acc, quality_f1 = row
    return (
        f"- 최근 학습 시각: {trained_at}, 학습 데이터 {n_experiments}건\n"
        f"- Kerf 예측: R2={kerf_r2}, RMSE={kerf_rmse}μm\n"
        f"- Depth 예측: R2={depth_r2}, RMSE={depth_rmse}μm\n"
        f"- 품질(OK/과가공/미가공/NG) 분류: Accuracy={quality_acc}, F1(macro)={quality_f1}"
    )


def _fetch_plasma(cur) -> str:
    cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE result = 'OK') FROM plasma_measurements")
    total, ok_count = cur.fetchone()
    return f"총 {total}건의 플라즈마 측정 데이터 보유 (정상 판정 {ok_count}건)"


def _fetch_recipes(cur) -> str:
    cur.execute(
        """
        SELECT m1_glass, m1_length_mm, m2_film, m2_length_mm, thickness_um,
               speed, defocus, frequency, power, pred_depth_um, pred_quality
        FROM recipes
        WHERE status = 'approved'
        ORDER BY created_at DESC
        """
    )
    lines = [
        f"- {m1_glass} {m1_length}mm + {m2_film} {m2_length}mm, Thickness {thickness}μm -> "
        f"Speed={speed}, Defocus={defocus}, Frequency={frequency}, Power={power} "
        f"(예측 Depth={depth}μm, {quality})"
        for m1_glass, m1_length, m2_film, m2_length, thickness, speed, defocus, frequency, power, depth, quality
        in cur.fetchall()
    ]
    return "\n".join(lines) if lines else "(승인된 레시피 없음)"


def _fetch_recent(cur, limit: int) -> str:
    cur.execute(
        """
        SELECT exp_no, m1_glass, m1_length_mm, m2_film, m2_length_mm, thickness_um,
               speed, defocus, frequency, power, kerf_um, depth_um, quality, notes
        FROM experiments
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    lines = []
    for (
        exp_no, m1_glass, m1_length, m2_film, m2_length, thickness,
        speed, defocus, frequency, power, kerf, depth, quality, notes,
    ) in cur.fetchall():
        line = (
            f"- [{exp_no}] {m1_glass} {m1_length}mm + {m2_film} {m2_length}mm / {thickness}μm, "
            f"Speed={speed} Defocus={defocus} Frequency={frequency} Power={power} -> "
            f"Kerf={kerf}μm Depth={depth}μm ({quality})"
        )
        if notes:
            line += f" — {notes}"
        lines.append(line)
    return "\n".join(lines) if lines else "(데이터 없음)"


def build_chat_context() -> str:
    """현재 DB 상태(실험 현황/소재별 통계/레시피/최근 실험)를 요약한 컨텍스트 문자열을 만든다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            summary = _fetch_summary(cur)
            material_types = _fetch_material_types(cur)
            model_metrics = _fetch_model_metrics(cur)
            plasma = _fetch_plasma(cur)
            by_material = _fetch_by_material(cur)
            recipes = _fetch_recipes(cur)
            recent = _fetch_recent(cur, CHAT_CONTEXT_RECENT_LIMIT)
    finally:
        conn.close()

    return CHAT_SYSTEM_TEMPLATE.format(
        system_guide=SYSTEM_GUIDE,
        summary=summary,
        material_types=material_types,
        model_metrics=model_metrics,
        plasma=plasma,
        by_material=by_material,
        recipes=recipes,
        recent_limit=CHAT_CONTEXT_RECENT_LIMIT,
        recent=recent,
    )


def build_chat_prompt(history: list[dict], question: str) -> str:
    """시스템 컨텍스트 + 이전 대화 + 새 질문으로 LLM 프롬프트를 구성한다."""
    context = build_chat_context()

    convo_lines = [f"{'운영자' if msg['role'] == 'user' else 'AI'}: {msg['content']}" for msg in history]
    convo_lines.append(f"운영자: {question}")
    convo_lines.append("AI:")

    return context + "\n\n[대화]\n" + "\n".join(convo_lines)


def generate_chat_reply(history: list[dict], question: str, provider: str | None = None):
    """
    대화 이력과 새 질문을 받아 AI 답변을 생성한다.

    Args:
        provider: "ollama" | "claude" 등. 지정하지 않으면 CHAT_LLM_PROVIDER 설정을 사용한다.

    Returns:
        LLM이 생성한 한국어 답변. 실패 시 None을 반환한다.
    """
    return _call_llm(build_chat_prompt(history, question), provider=provider or CHAT_LLM_PROVIDER)
