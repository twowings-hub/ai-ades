"""
AI-ADES Execution Agent — Auto DOE 워크플로우

Auto DOE 제안(Bayesian Optimization) -> 운영자 승인/거부 -> 실험 결과 입력 ->
OK 판정 시 레시피 저장까지의 엔드포인트를 제공한다.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

import admin
import approval
import notifier
import recipe_db
from bayesian_opt import _search_space, suggest_params
from db import QUALITY_SCORE, get_connection, judge_quality
from llm_explainer import generate_explanation, generate_result_evaluation
from responses import make_response as _response

router = APIRouter(prefix="/doe", tags=["doe"])

MODELING_AGENT_URL = os.getenv("MODELING_AGENT_URL", "http://modeling-agent:8011")

# 제안(suggestion) -> 승인/결과 입력까지 이어지는 세션 상태 (단일 프로세스 메모리 보관)
SUGGESTIONS: dict = {}


@router.get("/criteria")
def doe_criteria():
    """현재 품질 판정 기준(DEPTH_OK_MIN/MAX)을 반환한다.

    결과 저장 전 '사전 판정 미리보기'에서 사용한다. 값은 .env에서 읽어
    관리자 콘솔의 판정 기준 변경이 즉시 반영되도록 한다 (하드코딩 금지).
    """
    return _response(
        True,
        {
            "depth_ok_min": float(os.getenv("DEPTH_OK_MIN", 0.0)),
            "depth_ok_max": float(os.getenv("DEPTH_OK_MAX", 25.0)),
        },
        "판정 기준 조회 완료",
    )


# ------------------------------------------------------------
# /doe/suggest
# ------------------------------------------------------------
class HistoryItem(BaseModel):
    speed: float
    defocus: float
    frequency: float
    power: float
    actual_depth: float
    actual_kerf: float | None = None
    quality: str | None = None


class DoeSuggestRequest(BaseModel):
    m1_length: float
    m2_length: float
    thickness: float
    m1_glass: str = "Glass"
    m2_film: str = "Film"
    experiment_history: list[HistoryItem] = []
    n_suggestions: int = 1


def _call_predict(params: dict, m1_length: float, m2_length: float, thickness: float,
                  include_shap: bool = True) -> dict:
    """modeling-agent POST /predict 호출 (include_shap=False면 SHAP 생략으로 빠르게)"""
    try:
        resp = requests.post(
            f"{MODELING_AGENT_URL}/predict",
            json={
                "speed": params["speed"],
                "defocus": params["defocus"],
                "frequency": params["frequency"],
                "power": params["power"],
                "m1_length": m1_length,
                "m2_length": m2_length,
                "thickness": thickness,
                "include_shap": include_shap,
            },
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=500, detail=f"modeling-agent 호출 실패: {exc}")

    body = resp.json()
    if not body.get("success"):
        raise HTTPException(status_code=500, detail=f"modeling-agent 예측 실패: {body.get('message')}")

    return body["data"]


def _param_neighbors(param: str, current: float, space: dict) -> list[float]:
    """탐색공간 안에서 한 파라미터를 한 단계 위/아래로 옮긴 값을 반환한다 (하드코딩 금지, .env 기준)."""
    if param == "power":
        pmin, pmax = space["power"]
        step = max(1.0, round((pmax - pmin) * 0.1, 1))  # 범위의 10%를 한 스텝으로
        up, down = round(min(current + step, pmax), 1), round(max(current - step, pmin), 1)
        return [v for v in (up, down) if v != current]
    vals = sorted(set(space[param]))
    i = min(range(len(vals)), key=lambda j: abs(vals[j] - current))  # 현재값에 가장 가까운 인덱스
    return [vals[j] for j in (i + 1, i - 1) if 0 <= j < len(vals)]


def _local_sensitivity(context: dict) -> str | None:
    """조정 가능한 4개 파라미터를 각각 한 단계씩 바꿨을 때 모델이 예측하는 Depth 변화를 계산한다.

    SHAP(왜 그렇게 예측됐나)에 더해, '어느 노브를 어느 방향으로 바꾸면 Depth가 얼마나 변하나'를
    실제 모델 반응으로 보여줘 전문가 조정 제안의 신뢰도를 높인다 (방법 B, 국소 What-if).
    """
    base = {k: context[k] for k in ("speed", "defocus", "frequency", "power")}
    m1, m2, th = context["m1_length"], context["m2_length"], context.get("thickness")
    base_depth = context["pred_depth"]
    space = _search_space()

    # 바꿀 후보(파라미터, 값) 목록을 모은다
    trials = [
        (param, val)
        for param in ("speed", "defocus", "frequency", "power")
        for val in _param_neighbors(param, base[param], space)
    ]

    # SHAP는 불필요(depth만 필요)하므로 생략하고, 호출들을 병렬로 처리해 지연을 줄인다
    def _delta(item):
        param, val = item
        try:
            pred = _call_predict({**base, param: val}, m1, m2, th, include_shap=False)
        except Exception:
            return None
        return f"- {param} {base[param]}→{val}: Depth {pred['pred_depth'] - base_depth:+.1f}μm"

    with ThreadPoolExecutor(max_workers=len(trials) or 1) as pool:
        lines = [r for r in pool.map(_delta, trials) if r]
    return "\n".join(lines) if lines else None


def _generate_explanation_bg(suggestion_id: str, context: dict):
    """LLM 설명을 백그라운드에서 생성하고 SUGGESTIONS에 채워 넣는다 (응답 지연 방지)"""
    # 국소 민감도(What-if)를 계산해 컨텍스트에 추가한다 (실패해도 설명 생성은 진행)
    try:
        context["whatif_summary"] = _local_sensitivity(context)
    except Exception:
        context["whatif_summary"] = None

    explanation = generate_explanation(context)
    suggestion = SUGGESTIONS.get(suggestion_id)
    if suggestion is not None:
        suggestion["llm_explanation"] = explanation
        suggestion["llm_explanation_status"] = "ready"


@router.post("/suggest")
def doe_suggest(req: DoeSuggestRequest, background_tasks: BackgroundTasks):
    """Auto DOE 다음 실험 조건을 제안한다 (레시피 존재 시 레시피값 사용)

    LLM 설명(llm_explanation)은 생성 시간이 오래 걸려 백그라운드로 분리한다.
    응답에는 일단 null로 내려가며, 프론트엔드는 /doe/explanation/{suggestion_id}로 결과를 조회한다.
    """
    doe_attempt = len(req.experiment_history) + 1
    history = [h.model_dump() for h in req.experiment_history]

    recipe, exact_match = recipe_db.find_recipe(req.m1_length, req.m2_length, req.m1_glass, req.m2_film, req.thickness)
    recipe_found = bool(exact_match)

    if recipe_found:
        recipe_params = {
            "speed": recipe["opt_speed"],
            "defocus": recipe["opt_defocus"],
            "frequency": recipe["opt_frequency"],
            "power": recipe["opt_power"],
        }
        # 이 레시피 조건으로 이미 실험했는데 OK가 아니었다면 레시피를 신뢰할 수 없으므로
        # Bayesian Auto DOE 탐색으로 전환한다 (같은 제안 반복을 방지)
        recipe_already_failed = any(
            h["speed"] == recipe_params["speed"]
            and h["defocus"] == recipe_params["defocus"]
            and h["frequency"] == recipe_params["frequency"]
            and h["power"] == recipe_params["power"]
            and h["quality"] != "OK"
            for h in history
        )
        if recipe_already_failed:
            recipe_found = False
            suggested_params = suggest_params(history)
        else:
            suggested_params = recipe_params
    else:
        suggested_params = suggest_params(history)

    pred = _call_predict(suggested_params, req.m1_length, req.m2_length, req.thickness)

    suggestion_id = str(uuid.uuid4())
    SUGGESTIONS[suggestion_id] = {
        "m1_length": req.m1_length,
        "m2_length": req.m2_length,
        "thickness": req.thickness,
        "m1_glass": req.m1_glass,
        "m2_film": req.m2_film,
        "suggested_params": suggested_params,
        "pred": pred,
        "doe_attempt": doe_attempt,
        "recipe_found": recipe_found,
        "llm_explanation": None,
        "llm_explanation_status": "pending",
    }

    background_tasks.add_task(
        _generate_explanation_bg,
        suggestion_id,
        {
            "m1_length": req.m1_length,
            "m2_length": req.m2_length,
            "thickness": req.thickness,
            "speed": suggested_params["speed"],
            "defocus": suggested_params["defocus"],
            "frequency": suggested_params["frequency"],
            "power": suggested_params["power"],
            "pred_depth": pred["pred_depth"],
            "pred_quality": pred["pred_quality"],
            # 전문가 해석용: SHAP 기여도 + OK 목표 밴드(.env 기준, 하드코딩 금지)
            "shap_values": pred["shap_values"],
            "depth_ok_min": float(os.getenv("DEPTH_OK_MIN", 0.0)),
            "depth_ok_max": float(os.getenv("DEPTH_OK_MAX", 25.0)),
            "doe_attempt": doe_attempt,
        },
    )

    return _response(
        True,
        {
            "suggestion_id": suggestion_id,
            "suggested_params": suggested_params,
            "pred_depth": pred["pred_depth"],
            "pred_kerf": pred["pred_kerf"],
            "pred_quality": pred["pred_quality"],
            "confidence": pred["confidence"],
            "shap_values": pred["shap_values"],
            "llm_explanation": None,
            "llm_explanation_status": "pending",
            "doe_attempt": doe_attempt,
            "recipe_found": recipe_found,
        },
        f"{doe_attempt}차 파라미터 제안 완료",
    )


class DoeRepredictRequest(BaseModel):
    suggestion_id: str
    params: dict  # 운영자가 수정한 speed/defocus/frequency/power


@router.post("/repredict")
def doe_repredict(req: DoeRepredictRequest):
    """수정 후 승인 화면에서 운영자가 파라미터를 수정했을 때, 그 값으로 예측을 다시 계산한다."""
    suggestion = _get_suggestion(req.suggestion_id)
    pred = _call_predict(req.params, suggestion["m1_length"], suggestion["m2_length"], suggestion["thickness"])
    # 이후 승인/결과 적재 시에도 최신 예측값을 사용하도록 갱신
    suggestion["pred"] = pred

    return _response(
        True,
        {
            "pred_depth": pred["pred_depth"],
            "pred_kerf": pred["pred_kerf"],
            "pred_quality": pred["pred_quality"],
            "confidence": pred["confidence"],
            "shap_values": pred["shap_values"],
        },
        "재예측 완료",
    )


@router.get("/explanation/{suggestion_id}")
def get_doe_explanation(suggestion_id: str):
    """백그라운드에서 생성 중인 LLM 설명 상태를 조회한다 (프론트엔드 폴링용)"""
    suggestion = _get_suggestion(suggestion_id)
    return _response(
        True,
        {
            "llm_explanation": suggestion.get("llm_explanation"),
            "status": suggestion.get("llm_explanation_status", "ready"),
        },
        "LLM 설명 상태 조회 완료",
    )


# ------------------------------------------------------------
# /doe/approve, /doe/reject
# ------------------------------------------------------------
class DoeApproveRequest(BaseModel):
    suggestion_id: str
    operator_name: str
    final_params: dict | None = None  # 운영자가 파라미터를 수정한 경우(수정 후 승인)


class DoeRejectRequest(BaseModel):
    suggestion_id: str
    operator_name: str
    reason: str = Field(..., min_length=2)


def _get_suggestion(suggestion_id: str) -> dict:
    suggestion = SUGGESTIONS.get(suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="존재하지 않거나 만료된 suggestion_id 입니다")
    return suggestion


@router.post("/approve")
def doe_approve(req: DoeApproveRequest):
    """운영자 승인. 승인 토큰을 발급하고 audit_logs에 기록한다. (final_params 제공 시 '수정 후 승인')"""
    suggestion = _get_suggestion(req.suggestion_id)
    ai_params = suggestion["suggested_params"]
    final_params = req.final_params or ai_params
    pred = suggestion["pred"]
    is_modified = req.final_params is not None and req.final_params != ai_params

    token, expires_at = approval.create_approval(
        req.suggestion_id, ai_params, final_params, req.operator_name, is_modified
    )
    suggestion["operator_name"] = req.operator_name
    # 이후 /doe/result에서 레시피/experiments 적재 시 최종(수정) 파라미터를 사용
    suggestion["suggested_params"] = final_params

    approval.log_audit(
        action_type="approval",
        operator=req.operator_name,
        description=(
            f"DOE 승인: M1={suggestion['m1_length']}mm M2={suggestion['m2_length']}mm "
            f"Power={final_params['power']}W"
        ),
        new_value={
            "params": final_params,
            "pred_depth": pred["pred_depth"],
            "pred_quality": pred["pred_quality"],
        },
    )

    return _response(
        True,
        {"approval_token": token, "recipe_id": None},
        "승인 완료. 실험 후 /doe/result 로 결과를 입력해주세요.",
    )


@router.post("/reject")
def doe_reject(req: DoeRejectRequest):
    """운영자 거부. audit_logs에 기록한다."""
    suggestion = _get_suggestion(req.suggestion_id)
    suggested_params = suggestion["suggested_params"]

    approval.create_rejection(req.suggestion_id, suggested_params, req.operator_name, req.reason)

    approval.log_audit(
        action_type="rejection",
        operator=req.operator_name,
        description=f"DOE 거부: {req.reason}",
        old_value={"params": suggested_params},
    )

    return _response(
        True,
        {"message": "거부 기록 완료"},
        "거부 처리됐습니다. 새 제안을 요청하려면 /doe/suggest 를 다시 호출하세요.",
    )


# ------------------------------------------------------------
# /doe/evaluate, /doe/result
# ------------------------------------------------------------
class DoeResultRequest(BaseModel):
    suggestion_id: str
    actual_kerf: float
    actual_depth: float
    operator_name: str
    notes: str | None = None


class DoeEvaluateRequest(BaseModel):
    suggestion_id: str
    actual_kerf: float
    actual_depth: float


@router.post("/evaluate")
def doe_evaluate(req: DoeEvaluateRequest):
    """실측 결과(Kerf/Depth)를 예측값과 비교해 AI가 보고용 평가 메모 초안을 생성한다.

    운영자는 생성된 초안을 결과 보고 화면의 설명란에서 수정/보완할 수 있다.
    """
    suggestion = _get_suggestion(req.suggestion_id)
    params = suggestion["suggested_params"]
    pred = suggestion["pred"]
    quality = judge_quality(req.actual_depth)

    evaluation = generate_result_evaluation(
        {
            "m1_length": suggestion["m1_length"],
            "m2_length": suggestion["m2_length"],
            "speed": params["speed"],
            "defocus": params["defocus"],
            "frequency": params["frequency"],
            "power": params["power"],
            "pred_kerf": pred["pred_kerf"],
            "pred_depth": pred["pred_depth"],
            "pred_quality": pred["pred_quality"],
            "actual_kerf": req.actual_kerf,
            "actual_depth": req.actual_depth,
            "quality": quality,
            "doe_attempt": suggestion["doe_attempt"],
        }
    )

    return _response(True, {"quality": quality, "evaluation": evaluation}, "AI 평가 생성 완료")


def _insert_experiment(suggestion: dict, req: DoeResultRequest, quality: str):
    """Auto DOE 실험 결과를 experiments 테이블에 적재한다 (재학습 데이터 누적)"""
    params = suggestion["suggested_params"]
    exp_no = f"DOE-{req.suggestion_id[:8]}"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO experiments (
                    exp_no, m1_glass, m1_length_mm, m2_film, m2_length_mm, thickness_um,
                    speed, defocus, frequency, power,
                    sensor_data_ok, kerf_um, depth_um, quality, quality_score, notes
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    TRUE, %s, %s, %s, %s, %s
                )
                ON CONFLICT (exp_no) DO NOTHING
                """,
                (
                    exp_no,
                    suggestion.get("m1_glass", "Glass"), suggestion["m1_length"],
                    suggestion.get("m2_film", "Film"), suggestion["m2_length"], suggestion["thickness"],
                    params["speed"], params["defocus"], params["frequency"], params["power"],
                    req.actual_kerf, req.actual_depth, quality, QUALITY_SCORE.get(quality), req.notes,
                ),
            )
        conn.commit()
    finally:
        conn.close()


@router.post("/result")
def doe_result(req: DoeResultRequest, background_tasks: BackgroundTasks):
    """실험 결과를 입력받아 판정하고, OK이면 레시피를 저장한다."""
    suggestion = _get_suggestion(req.suggestion_id)
    quality = judge_quality(req.actual_depth)
    doe_attempts = suggestion["doe_attempt"]

    _insert_experiment(suggestion, req, quality)
    admin.check_and_trigger_retrain()

    recipe_id = None
    recipe_saved = False
    message = "실험 결과 저장 완료"

    if quality == "OK":
        recipe_id = recipe_db.save_recipe(
            m1_length=suggestion["m1_length"],
            m2_length=suggestion["m2_length"],
            thickness=suggestion["thickness"],
            params=suggestion["suggested_params"],
            pred=suggestion["pred"],
            doe_attempts=doe_attempts,
            approved_by=req.operator_name,
            m1_glass=suggestion.get("m1_glass", "Glass"),
            m2_film=suggestion.get("m2_film", "Film"),
            notes=req.notes,
        )
        approval.update_recipe_id(req.suggestion_id, recipe_id)
        recipe_saved = True
        result_message = "OK 달성! 레시피가 저장되었습니다."
    else:
        result_message = f"{quality} 판정. /doe/suggest 로 다음 조건을 요청하세요."

    # 자동 알림: OK이면 'ok', 실패(미가공/과가공/NG)면 'failure' 이벤트를 비차단으로 발송한다.
    # (실패해도 결과 저장 응답을 막지 않도록 BackgroundTasks + notifier 내부 예외격리)
    exp_no = f"DOE-{req.suggestion_id[:8]}"
    _event = "ok" if quality == "OK" else "failure"
    _msg = (
        f"[{quality}] {exp_no} (M1 {suggestion['m1_length']}mm / M2 {suggestion['m2_length']}mm / "
        f"{suggestion['thickness']}μm) — Depth {req.actual_depth}μm, Kerf {req.actual_kerf}μm, "
        f"{doe_attempts}차"
    )
    background_tasks.add_task(notifier.notify, _event, _msg, quality=quality, exp_no=exp_no)

    return _response(
        True,
        {
            "quality": quality,
            "recipe_saved": recipe_saved,
            "recipe_id": recipe_id,
            "doe_attempts": doe_attempts,
            "message": result_message,
        },
        message,
    )
