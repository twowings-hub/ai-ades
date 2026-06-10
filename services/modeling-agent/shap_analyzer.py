"""
AI-ADES SHAP 분석

XGBoost 전용 TreeExplainer를 사용하여
전체 feature importance 및 개별 예측의 SHAP 값을 계산한다.
"""
import numpy as np
import pandas as pd
import shap

from feature_engineering import FEATURE_COLUMNS


def analyze_feature_importance(model, X: pd.DataFrame) -> dict:
    """
    모델 전체에 대한 SHAP feature importance를 계산한다.

    Returns:
        {
            "feature_importance": {"power": 0.44, "energy_density": 0.21, ...},
            "top_feature": "power"
        }
    """
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    mean_abs = np.abs(shap_values).mean(axis=0)
    total = mean_abs.sum()
    importance = {
        col: float(val / total) for col, val in zip(FEATURE_COLUMNS, mean_abs)
    }
    # 중요도 내림차순 정렬
    importance = dict(sorted(importance.items(), key=lambda kv: kv[1], reverse=True))
    top_feature = next(iter(importance))

    return {"feature_importance": importance, "top_feature": top_feature}


def explain_instance(model, X_row: pd.DataFrame) -> dict:
    """
    단일 입력(X_row, 1행 DataFrame)에 대한 SHAP 값을 계산한다.

    Returns:
        {"power": 0.44, "speed": 0.28, ...} (feature -> SHAP 기여도, 절대값 기준 정렬)
    """
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_row)

    values = shap_values[0]
    result = {col: float(val) for col, val in zip(FEATURE_COLUMNS, values)}
    return dict(sorted(result.items(), key=lambda kv: abs(kv[1]), reverse=True))
