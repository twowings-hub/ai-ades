"""
AI-ADES Modeling Agent (Port 8011)

Feature Engineering -> Optuna 튜닝 -> XGBoost 학습 -> SHAP 분석 -> MLflow 기록
파이프라인을 실행하고, 예측/모델 상태 조회 API를 제공한다.
"""
import json
import os

import joblib
import numpy as np
import torch
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
from lstm_model import (
    LSTMAutoencoder,
    compute_reconstruction_error,
    detect_anomalies,
    make_windows,
    train_autoencoder,
)
from mlflow_tracker import log_anomaly_model_run, log_model_run
from optuna_tuner import tune_classification, tune_regression
from plasma_data import PLASMA_CHANNELS, list_experiment_ids, load_plasma_wide, split_segments
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

# LSTM-Autoencoder (Phase 6) 저장 경로
ANOMALY_MODEL_PATH = os.path.join(MODELS_DIR, "lstm_autoencoder.pt")
ANOMALY_SCALER_PATH = os.path.join(MODELS_DIR, "lstm_scaler.pkl")
ANOMALY_METRICS_PATH = os.path.join(MODELS_DIR, "lstm_metrics.json")

# 학습/로드된 모델을 메모리에 보관
STATE: dict = {
    "kerf_model": None,
    "depth_model": None,
    "quality_model": None,
    "quality_encoder": None,
    "metrics": {},
    "anomaly_model": None,
    "anomaly_scaler": None,
    "anomaly_threshold": None,
    "anomaly_metrics": {},
}


def _response(success: bool, data=None, message: str = ""):
    """API 응답 형식 통일"""
    return {"success": success, "data": data, "message": message}


def _save_metrics_to_db(metrics: dict, run_ids: dict, n_experiments: int):
    """모델 학습 결과를 model_metrics 테이블에 적재한다 (Grafana 대시보드 조회 + Phase 6 자동 재학습 트리거 기준)"""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_metrics (
                    kerf_r2, kerf_rmse, depth_r2, depth_rmse,
                    quality_f1_macro, quality_f1_ok, quality_accuracy,
                    mlflow_run_id_kerf, mlflow_run_id_depth, mlflow_run_id_quality,
                    n_experiments
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    n_experiments,
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

    if os.path.exists(ANOMALY_MODEL_PATH) and os.path.exists(ANOMALY_SCALER_PATH):
        model = LSTMAutoencoder(n_channels=len(PLASMA_CHANNELS))
        model.load_state_dict(torch.load(ANOMALY_MODEL_PATH))
        model.eval()
        STATE["anomaly_model"] = model
        STATE["anomaly_scaler"] = joblib.load(ANOMALY_SCALER_PATH)

    if os.path.exists(ANOMALY_METRICS_PATH):
        with open(ANOMALY_METRICS_PATH, "r", encoding="utf-8") as f:
            STATE["anomaly_metrics"] = json.load(f)
            STATE["anomaly_threshold"] = STATE["anomaly_metrics"].get("threshold")


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

    _save_metrics_to_db(metrics, run_ids, n_experiments=len(df))

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


@app.post("/model/train-anomaly")
def train_anomaly():
    """
    plasma_timeseries에 적재된 모든 실험 데이터로 LSTM-Autoencoder를 학습한다 (Phase 6).
    정상 가공 패턴을 재구성하도록 학습 후, 재구성 오차 95백분위수를 이상감지 임계값으로 저장한다.
    """
    experiment_ids = list_experiment_ids()
    if not experiment_ids:
        raise HTTPException(status_code=400, detail="plasma_timeseries에 적재된 데이터가 없습니다")

    all_windows = []
    for experiment_id in experiment_ids:
        wide = load_plasma_wide(experiment_id)
        windows = make_windows(wide[PLASMA_CHANNELS].to_numpy())
        if len(windows) > 0:
            all_windows.append(windows)

    if not all_windows:
        raise HTTPException(
            status_code=400,
            detail="윈도우를 구성하기에 시계열 길이가 부족합니다 (최소 길이 미달)",
        )

    windows = np.concatenate(all_windows, axis=0)
    model, scaler, threshold, metrics = train_autoencoder(windows)

    os.makedirs(MODELS_DIR, exist_ok=True)
    torch.save(model.state_dict(), ANOMALY_MODEL_PATH)
    joblib.dump(scaler, ANOMALY_SCALER_PATH)

    metrics["n_experiments"] = len(experiment_ids)
    with open(ANOMALY_METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    STATE["anomaly_model"] = model
    STATE["anomaly_scaler"] = scaler
    STATE["anomaly_threshold"] = threshold
    STATE["anomaly_metrics"] = metrics

    log_anomaly_model_run("lstm_autoencoder", model, {"window_size": model.window_size}, {
        "final_loss": metrics["final_loss"],
        "threshold": threshold,
    })

    return _response(
        True,
        {"threshold": threshold, "final_loss": metrics["final_loss"], "n_windows": metrics["n_windows"]},
        "LSTM-Autoencoder 학습 완료",
    )


class AnomalyPredictRequest(BaseModel):
    experiment_id: int


@app.post("/predict-anomaly")
def predict_anomaly(req: AnomalyPredictRequest):
    """
    실험 1건의 Plasma 시계열을 M1/M2/Blank 구간으로 분리하여
    구간별 재구성 오차와 이상 여부를 반환한다 (Phase 6).
    """
    if STATE["anomaly_model"] is None:
        raise HTTPException(status_code=400, detail="학습된 이상감지 모델이 없습니다. 먼저 /model/train-anomaly를 호출하세요")

    wide = load_plasma_wide(req.experiment_id)
    if wide.empty:
        raise HTTPException(status_code=404, detail=f"experiment_id={req.experiment_id}의 Plasma 데이터가 없습니다")

    segments = split_segments(wide)
    threshold = STATE["anomaly_threshold"]

    result = {}
    for segment_name, segment_df in segments.items():
        windows = make_windows(segment_df[PLASMA_CHANNELS].to_numpy())
        if len(windows) == 0:
            result[segment_name] = {"n_windows": 0, "mean_error": None, "anomaly_ratio": None}
            continue

        errors = compute_reconstruction_error(STATE["anomaly_model"], windows, scaler=STATE["anomaly_scaler"])
        anomalies = detect_anomalies(errors, threshold)
        result[segment_name] = {
            "n_windows": int(len(windows)),
            "mean_error": float(errors.mean()),
            "anomaly_ratio": float(anomalies.mean()),
        }

    return _response(True, {"threshold": threshold, "segments": result}, "이상감지 예측 완료")


@app.get("/model/anomaly-status")
def anomaly_status():
    """LSTM-Autoencoder 학습 상태(임계값, 최종 손실)를 반환한다."""
    if STATE["anomaly_model"] is None:
        return _response(False, None, "학습된 이상감지 모델이 없습니다. 먼저 /model/train-anomaly를 호출하세요")

    return _response(
        True,
        {
            "threshold": STATE["anomaly_threshold"],
            "final_loss": STATE["anomaly_metrics"].get("final_loss"),
            "n_windows": STATE["anomaly_metrics"].get("n_windows"),
        },
        "이상감지 모델 상태 조회 완료",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
