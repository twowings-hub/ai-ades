"""
AI-ADES Optuna 하이퍼파라미터 최적화

kerf_model / depth_model(회귀), quality_model(분류) 각각에 대해
n_trials=100, 모델당 timeout=10분으로 최적 하이퍼파라미터를 탐색한다.
"""
import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import f1_score, r2_score
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier, XGBRegressor

from feature_engineering import FEATURE_COLUMNS
from xgboost_pipeline import (
    DEFAULT_CLASSIFICATION_PARAMS,
    DEFAULT_REGRESSION_PARAMS,
    N_SPLITS,
    RANDOM_STATE,
)

optuna.logging.set_verbosity(optuna.logging.WARNING)

N_TRIALS = 100
TIMEOUT_SEC = 600  # 모델당 10분


def _suggest_params(trial):
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500),
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        # 튜닝 단계에서는 n_jobs=1로 고정 (소규모 fold 데이터에서 스레드 생성 오버헤드로 인한
        # 실행시간 편차 -> timeout 도달 시점 비결정성을 방지하기 위함)
        "n_jobs": 1,
    }


def tune_regression(df, target_col: str) -> dict:
    """회귀 모델(kerf/depth)의 하이퍼파라미터를 Optuna로 탐색한다."""
    X = df[FEATURE_COLUMNS]
    y = df[target_col]
    kf = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    def objective(trial):
        params = {
            **DEFAULT_REGRESSION_PARAMS,
            **_suggest_params(trial),
        }
        scores = []
        for train_idx, val_idx in kf.split(X):
            model = XGBRegressor(**params)
            model.fit(X.iloc[train_idx], y.iloc[train_idx])
            pred = model.predict(X.iloc[val_idx])
            scores.append(r2_score(y.iloc[val_idx], pred))
        return float(np.mean(scores))

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    study.optimize(objective, n_trials=N_TRIALS, timeout=TIMEOUT_SEC)

    return study.best_params


def tune_classification(df) -> dict:
    """quality_model(분류)의 하이퍼파라미터를 Optuna로 탐색한다."""
    X = df[FEATURE_COLUMNS]

    encoder = LabelEncoder()
    y = pd.Series(encoder.fit_transform(df["quality_score"]), index=X.index)
    sample_weight = pd.Series(
        compute_sample_weight(class_weight="balanced", y=y), index=X.index
    )

    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    def objective(trial):
        params = {
            **DEFAULT_CLASSIFICATION_PARAMS,
            **_suggest_params(trial),
            "num_class": df["quality_score"].nunique(),
        }
        scores = []
        for train_idx, val_idx in skf.split(X, y):
            sw = sample_weight.iloc[train_idx].values
            model = XGBClassifier(**params)
            model.fit(X.iloc[train_idx], y.iloc[train_idx], sample_weight=sw)
            pred = model.predict(X.iloc[val_idx])
            scores.append(f1_score(y.iloc[val_idx], pred, average="macro"))
        return float(np.mean(scores))

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    study.optimize(objective, n_trials=N_TRIALS, timeout=TIMEOUT_SEC)

    return study.best_params
