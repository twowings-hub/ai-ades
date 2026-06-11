"""
AI-ADES Modeling Agent (Port 8011)

Feature Engineering -> Optuna 튜닝 -> XGBoost 학습 -> SHAP 분석 -> MLflow 기록
파이프라인을 실행하고, 예측/모델 상태 조회 API를 제공한다.
"""
import json
import os

import joblib
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from feature_engineering import (
    FEATURE_COLUMNS,
    _get_connection,
    build_feature_dataframe,
    build_features_for_input,
)
from llm_explainer import generate_explanation
from mlflow_tracker import log_model_run
from optuna_tuner import tune_classification, tune_regression
from shap_analyzer import analyze_feature_importance, explain_instance
from xgboost_pipeline import (
    QUALITY_SCORE_TO_LABEL,
    train_quality_model,
    train_regression_model,
)

load_dotenv()

app = FastAPI(title="AI-ADES Modeling Agent")

# 프론트엔드(Vite 개발 서버)에서의 직접 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.getenv("MODELING_PORT", 8011))
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
METRICS_PATH = os.path.join(MODELS_DIR, "metrics.json")
ENCODER_PATH = os.path.join(MODELS_DIR, "quality_encoder.pkl")

# 학습/로드된 모델을 메모리에 보관
STATE: dict = {
    "kerf_model": None,
    "depth_model": None,
    "quality_model": None,
    "quality_encoder": None,
    "metrics": {},
}


def _response(success: bool, data=None, message: str = ""):
    """API 응답 형식 통일"""
    return {"success": success, "data": data, "message": message}


def _save_metrics_to_db(metrics: dict, run_ids: dict):
    """모델 학습 결과를 model_metrics 테이블에 적재한다 (Grafana 대시보드 조회용)"""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_metrics (
                    kerf_r2, kerf_rmse, depth_r2, depth_rmse,
                    quality_f1_macro, quality_f1_ok, quality_accuracy,
                    mlflow_run_id_kerf, mlflow_run_id_depth, mlflow_run_id_quality
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    metrics["kerf"]["r2"],
                    metrics["kerf"]["rmse"],
                    metrics["depth"]["r2"],
                    metrics["depth"]["rmse"],
                    metrics["quality"]["f1_macro"],
                    metrics["quality"]["f1_ok"],
                    metrics["quality"]["accuracy"],
                    run_ids["kerf_model"],
                    run_ids["depth_model"],
                    run_ids["quality_model"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _load_models_from_disk():
    """컨테이너 재시작 시 저장된 모델/메트릭을 메모리에 로드한다."""
    for name in ("kerf_model", "depth_model", "quality_model"):
        path = os.path.join(MODELS_DIR, f"{name}.pkl")
        if os.path.exists(path):
            STATE[name] = joblib.load(path)

    if os.path.exists(ENCODER_PATH):
        STATE["quality_encoder"] = joblib.load(ENCODER_PATH)

    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            STATE["metrics"] = json.load(f)


@app.on_event("startup")
def startup():
    _load_models_from_disk()


@app.get("/health")
def health():
    """서비스 상태 확인"""
    return _response(
        True,
        {"status": "ok", "service": "modeling-agent", "port": PORT},
        "서비스 정상",
    )


@app.post("/model/train")
def train():
    """FE -> Optuna -> XGBoost -> SHAP -> MLflow 전체 파이프라인 실행"""
    df = build_feature_dataframe()
    if len(df) < 10:
        raise HTTPException(status_code=400, detail="학습 데이터가 부족합니다")

    os.makedirs(MODELS_DIR, exist_ok=True)
    run_ids = {}
    metrics = {}

    # ---- kerf_model ----
    kerf_params = tune_regression(df, "kerf")
    kerf_model, kerf_metrics = train_regression_model(df, "kerf", params=kerf_params)
    run_ids["kerf_model"] = log_model_run("kerf_model", kerf_model, kerf_params, kerf_metrics)
    STATE["kerf_model"] = kerf_model
    metrics["kerf"] = kerf_metrics

    # ---- depth_model ----
    depth_params = tune_regression(df, "depth")
    depth_model, depth_metrics = train_regression_model(df, "depth", params=depth_params)
    depth_importance = analyze_feature_importance(depth_model, df[FEATURE_COLUMNS])
    run_ids["depth_model"] = log_model_run(
        "depth_model", depth_model, depth_params, depth_metrics, depth_importance["feature_importance"]
    )
    STATE["depth_model"] = depth_model
    metrics["depth"] = depth_metrics
    metrics["depth_feature_importance"] = depth_importance

    # ---- quality_model ----
    quality_params = tune_classification(df)
    quality_model, quality_metrics, encoder = train_quality_model(df, params=quality_params)
    run_ids["quality_model"] = log_model_run("quality_model", quality_model, quality_params, quality_metrics)
    STATE["quality_model"] = quality_model
    STATE["quality_encoder"] = encoder
    joblib.dump(encoder, ENCODER_PATH)
    metrics["quality"] = quality_metrics

    STATE["metrics"] = metrics
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump({**metrics, "mlflow_run_ids": run_ids}, f, ensure_ascii=False, indent=2)

    _save_metrics_to_db(metrics, run_ids)

    return _response(
        True,
        {
            "r2_depth": depth_metrics["r2"],
            "f1_ok": quality_metrics["f1_ok"],
            "mlflow_run_id": run_ids["depth_model"],
            "mlflow_run_ids": run_ids,
            "metrics": metrics,
        },
        "모델 학습 완료",
    )


class PredictRequest(BaseModel):
    speed: float
    defocus: float
    frequency: float
    power: float
    m1_length: float
    m2_length: float
    thickness: float


@app.post("/predict")
def predict(req: PredictRequest):
    """단일 조건에 대한 kerf/depth/quality 예측 + SHAP + LLM 설명"""
    if not all([STATE["kerf_model"], STATE["depth_model"], STATE["quality_model"]]):
        raise HTTPException(status_code=400, detail="학습된 모델이 없습니다. 먼저 /model/train을 호출하세요")

    X = build_features_for_input(req.model_dump())

    pred_kerf = float(STATE["kerf_model"].predict(X)[0])
    pred_depth = float(STATE["depth_model"].predict(X)[0])

    quality_proba = STATE["quality_model"].predict_proba(X)[0]
    pred_encoded = int(quality_proba.argmax())
    confidence = float(quality_proba.max())
    pred_quality_score = int(STATE["quality_encoder"].inverse_transform([pred_encoded])[0])
    pred_quality = QUALITY_SCORE_TO_LABEL.get(pred_quality_score, str(pred_quality_score))

    shap_values = explain_instance(STATE["depth_model"], X)

    llm_explanation = generate_explanation(
        {
            "m1_length": req.m1_length,
            "m2_length": req.m2_length,
            "shap_dict": shap_values,
            "pred_depth": round(pred_depth, 2),
            "pred_quality": pred_quality,
        }
    )

    return _response(
        True,
        {
            "pred_kerf": round(pred_kerf, 2),
            "pred_depth": round(pred_depth, 2),
            "pred_quality": pred_quality,
            "confidence": round(confidence, 4),
            "shap_values": shap_values,
            "llm_explanation": llm_explanation,
        },
        "예측 완료",
    )


@app.get("/model/status")
def model_status():
    """현재 로드된 모델의 R²/F1 현황"""
    metrics = STATE["metrics"]
    if not metrics:
        return _response(False, None, "학습된 모델이 없습니다. 먼저 /model/train을 호출하세요")

    return _response(
        True,
        {
            "kerf_r2": metrics.get("kerf", {}).get("r2"),
            "depth_r2": metrics.get("depth", {}).get("r2"),
            "quality_f1_ok": metrics.get("quality", {}).get("f1_ok"),
        },
        "모델 상태 조회 완료",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
