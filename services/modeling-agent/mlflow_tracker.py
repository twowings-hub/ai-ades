"""
AI-ADES MLflow 실험 관리

3개 모델(kerf/depth/quality)을 "ai-ades-laser-cutting" experiment의
별도 run으로 기록하고, 모델 파일을 /models/ 디렉토리에 저장한다.
"""
import os

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import mlflow.xgboost
from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_NAME = "ai-ades-laser-cutting"
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def _setup():
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment(EXPERIMENT_NAME)


def _save_importance_plot(feature_importance: dict, out_path: str):
    features = list(feature_importance.keys())
    values = list(feature_importance.values())

    plt.figure(figsize=(8, 6))
    plt.barh(features[::-1], values[::-1])
    plt.xlabel("SHAP importance (normalized)")
    plt.title("Feature Importance")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def log_model_run(
    model_name: str,
    model,
    params: dict,
    metrics: dict,
    feature_importance: dict | None = None,
) -> str:
    """
    모델 1개를 MLflow run으로 기록하고 /models/{model_name}.pkl로 저장한다.

    Args:
        model_name: "kerf_model" / "depth_model" / "quality_model"
        model: 학습 완료된 XGBoost 모델
        params: 최적 하이퍼파라미터
        metrics: 평가 지표 (R²/RMSE 또는 F1/accuracy)
        feature_importance: SHAP feature importance (있으면 그래프 아티팩트로 기록)

    Returns:
        mlflow run_id
    """
    _setup()
    os.makedirs(MODELS_DIR, exist_ok=True)

    with mlflow.start_run(run_name=model_name) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        mlflow.xgboost.log_model(model, artifact_path="model")

        # 모델 파일 저장 (.pkl)
        model_path = os.path.join(MODELS_DIR, f"{model_name}.pkl")
        joblib.dump(model, model_path)
        mlflow.log_artifact(model_path)

        if feature_importance:
            plot_path = os.path.join(MODELS_DIR, f"{model_name}_importance.png")
            _save_importance_plot(feature_importance, plot_path)
            mlflow.log_artifact(plot_path)

        return run.info.run_id
