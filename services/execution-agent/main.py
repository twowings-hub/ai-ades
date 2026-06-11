"""
AI-ADES Execution Agent (Port 8012)

Auto DOE 제안(Bayesian Optimization) -> 운영자 승인/거부 -> 실험 결과 입력 ->
OK 판정 시 레시피 저장까지의 워크플로우를 제공한다.
"""
import os
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import admin
import admin_data
import approval
import material_types
import recipe_db
from bayesian_opt import suggest_params
from db import QUALITY_SCORE, get_connection, judge_quality
from llm_explainer import generate_explanation

load_dotenv()

app = FastAPI(title="AI-ADES Execution Agent")

# 프론트엔드(Vite 개발 서버)에서의 직접 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(admin_data.router)
app.include_router(material_types.router)

PORT = int(os.getenv("EXECUTION_PORT", 8012))
MODELING_AGENT_URL = os.getenv("MODELING_AGENT_URL", "http://modeling-agent:8011")

# 제안(suggestion) -> 승인/결과 입력까지 이어지는 세션 상태 (단일 프로세스 메모리 보관)
SUGGESTIONS: dict = {}


def _response(success: bool, data=None, message: str = ""):
    """API 응답 형식 통일"""
    return {"success": success, "data": data, "message": message}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """공통 에러 응답 형식({"success": false, "data": null, "message": ...})으로 통일"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_response(False, None, exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """요청 바디 검증 오류도 공통 응답 형식으로 통일 (예: reason 최소 길이)"""
    first_error = exc.errors()[0]
    field = ".".join(str(loc) for loc in first_error["loc"] if loc != "body")
    return JSONResponse(
        status_code=422,
        content=_response(False, None, f"{field}: {first_error['msg']}"),
    )


@app.get("/health")
def health():
    """서비스 상태 확인"""
    return _response(
        True,
        {"status": "ok", "service": "execution-agent", "port": PORT},
        "정상",
    )


@app.get("/material-types")
def get_active_material_types():
    """실험 조건 입력 화면(M1/M2 소재 종류 선택)에서 사용할 활성 소재 종류 목록을 반환한다"""
    grouped = {"m1": [], "m2": []}
    for t in material_types.list_material_types(active_only=True):
        grouped.setdefault(t["category"], []).append(
            {"id": t["id"], "name": t["name"], "description": t["description"]}
        )
    return _response(True, grouped, "소재 종류 조회 완료")


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


def _call_predict(params: dict, m1_length: float, m2_length: float, thickness: float) -> dict:
    """modeling-agent POST /predict 호출"""
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


@app.post("/doe/suggest")
def doe_suggest(req: DoeSuggestRequest):
    """Auto DOE 다음 실험 조건을 제안한다 (레시피 존재 시 레시피값 사용)"""
    doe_attempt = len(req.experiment_history) + 1

    recipe, exact_match = recipe_db.find_recipe(req.m1_length, req.m2_length, req.m1_glass, req.m2_film, req.thickness)
    recipe_found = bool(exact_match)

    if recipe_found:
        suggested_params = {
            "speed": recipe["opt_speed"],
            "defocus": recipe["opt_defocus"],
            "frequency": recipe["opt_frequency"],
            "power": recipe["opt_power"],
        }
    else:
        history = [h.model_dump() for h in req.experiment_history]
        suggested_params = suggest_params(history)

    pred = _call_predict(suggested_params, req.m1_length, req.m2_length, req.thickness)

    llm_explanation = generate_explanation(
        {
            "m1_length": req.m1_length,
            "m2_length": req.m2_length,
            "speed": suggested_params["speed"],
            "defocus": suggested_params["defocus"],
            "frequency": suggested_params["frequency"],
            "power": suggested_params["power"],
            "pred_depth": pred["pred_depth"],
            "pred_quality": pred["pred_quality"],
            "doe_attempt": doe_attempt,
        }
    )

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
    }

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
            "llm_explanation": llm_explanation,
            "doe_attempt": doe_attempt,
            "recipe_found": recipe_found,
        },
        f"{doe_attempt}차 파라미터 제안 완료",
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


@app.post("/doe/approve")
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


@app.post("/doe/reject")
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
# /doe/result
# ------------------------------------------------------------
class DoeResultRequest(BaseModel):
    suggestion_id: str
    actual_kerf: float
    actual_depth: float
    operator_name: str


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
                    sensor_data_ok, kerf_um, depth_um, quality, quality_score
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    TRUE, %s, %s, %s, %s
                )
                ON CONFLICT (exp_no) DO NOTHING
                """,
                (
                    exp_no,
                    suggestion.get("m1_glass", "Glass"), suggestion["m1_length"],
                    suggestion.get("m2_film", "Film"), suggestion["m2_length"], suggestion["thickness"],
                    params["speed"], params["defocus"], params["frequency"], params["power"],
                    req.actual_kerf, req.actual_depth, quality, QUALITY_SCORE.get(quality),
                ),
            )
        conn.commit()
    finally:
        conn.close()


@app.post("/doe/result")
def doe_result(req: DoeResultRequest):
    """실험 결과를 입력받아 판정하고, OK이면 레시피를 저장한다."""
    suggestion = _get_suggestion(req.suggestion_id)
    quality = judge_quality(req.actual_depth)
    doe_attempts = suggestion["doe_attempt"]

    _insert_experiment(suggestion, req, quality)

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
        )
        approval.update_recipe_id(req.suggestion_id, recipe_id)
        recipe_saved = True
        result_message = "OK 달성! 레시피가 저장되었습니다."
    else:
        result_message = f"{quality} 판정. /doe/suggest 로 다음 조건을 요청하세요."

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


# ------------------------------------------------------------
# /recipes
# ------------------------------------------------------------
@app.get("/recipes")
def get_recipes():
    """승인된 레시피 전체 목록 조회"""
    recipes = recipe_db.list_recipes()
    return _response(True, {"recipes": recipes, "total": len(recipes)}, "레시피 조회 완료")


@app.get("/recipes/{m1_length}/{m2_length}")
def get_recipe(m1_length: float, m2_length: float, thickness: float | None = None, m1_glass: str = "Glass", m2_film: str = "Film"):
    """
    소재 사양으로 레시피를 조회한다 (정확 매칭 -> 유사 매칭 -> 없음).
    thickness 쿼리 파라미터를 생략하면 두께 조건 없이 m1/m2 길이만으로 조회한다.
    """
    recipe, exact_match = recipe_db.find_recipe(m1_length, m2_length, m1_glass, m2_film, thickness)

    if recipe is None:
        raise HTTPException(status_code=404, detail="레시피 없음. Auto DOE를 실행해주세요.")

    if exact_match:
        message = "레시피 조회 완료"
    else:
        message = "정확히 일치하는 레시피가 없어 유사 레시피를 반환합니다. Thickness 재확인을 권장합니다."

    return _response(True, {"recipe": recipe, "exact_match": exact_match}, message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
