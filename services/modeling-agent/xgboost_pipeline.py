"""
AI-ADES XGBoost 학습 파이프라인

kerf_model(회귀), depth_model(회귀), quality_model(분류) 3개 모델을
독립적으로 학습하고 평가 지표를 반환한다.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score
from sklearn.model_selection import KFold, StratifiedKFold, train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier, XGBRegressor

from feature_engineering import FEATURE_COLUMNS

RANDOM_STATE = 42
TEST_SIZE = 0.2
N_SPLITS = 5

# quality_score(-1, 0, 1) -> 한글 판정 라벨
QUALITY_SCORE_TO_LABEL = {-1: "과가공", 0: "미가공", 1: "OK"}

DEFAULT_REGRESSION_PARAMS = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": RANDOM_STATE,
    "device": "cpu",
    "n_jobs": -1,
}

DEFAULT_CLASSIFICATION_PARAMS = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": RANDOM_STATE,
    "device": "cpu",
    "n_jobs": -1,
    "objective": "multi:softprob",
    "eval_metric": "mlogloss",
}


def _train_holdout_regression(X, y, params):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    model = XGBRegressor(**params)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    return {
        "r2": float(r2_score(y_test, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred))),
    }


def _cv_regression(X, y, params):
    kf = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    r2_list, rmse_list = [], []
    for train_idx, val_idx in kf.split(X):
        model = XGBRegressor(**params)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[val_idx])
        r2_list.append(r2_score(y.iloc[val_idx], pred))
        rmse_list.append(np.sqrt(mean_squared_error(y.iloc[val_idx], pred)))
    return {"cv_r2_mean": float(np.mean(r2_list)), "cv_rmse_mean": float(np.mean(rmse_list))}


def train_regression_model(df, target_col: str, params: dict | None = None):
    """
    회귀 모델(kerf_model, depth_model)을 학습한다.

    Returns:
        (학습 완료된 모델(전체 데이터로 재학습), metrics dict)
    """
    params = {**DEFAULT_REGRESSION_PARAMS, **(params or {})}
    X = df[FEATURE_COLUMNS]
    y = df[target_col]

    metrics = {}
    metrics.update(_train_holdout_regression(X, y, params))
    metrics.update(_cv_regression(X, y, params))

    # 최종 모델은 전체 데이터로 재학습
    model = XGBRegressor(**params)
    model.fit(X, y)

    return model, metrics


def _cv_classification(X, y, sample_weight, params):
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    f1_macro_list = []
    for train_idx, val_idx in skf.split(X, y):
        sw = sample_weight.iloc[train_idx].values
        model = XGBClassifier(**params)
        model.fit(X.iloc[train_idx], y.iloc[train_idx], sample_weight=sw)
        pred = model.predict(X.iloc[val_idx])
        f1_macro_list.append(f1_score(y.iloc[val_idx], pred, average="macro"))
    return {"cv_f1_macro_mean": float(np.mean(f1_macro_list))}


def train_quality_model(df, params: dict | None = None):
    """
    quality_model(분류, quality_score: -1/0/1)을 학습한다.
    OK(1) 클래스는 sample_weight로 가중치를 높여 클래스 불균형을 보정한다.

    Returns:
        (학습 완료된 모델, metrics dict, LabelEncoder)
    """
    params = {**DEFAULT_CLASSIFICATION_PARAMS, **(params or {})}
    params["num_class"] = df["quality_score"].nunique()

    X = df[FEATURE_COLUMNS]
    y_raw = df["quality_score"]

    # XGBoost는 0..n-1 범위의 정수 라벨이 필요 -> LabelEncoder로 인코딩
    encoder = LabelEncoder()
    y = pd.Series(encoder.fit_transform(y_raw), index=y_raw.index)

    # 클래스 불균형 보정: balanced 가중치 (소수 클래스인 OK 가중치 자동 상향)
    sample_weight = pd.Series(
        compute_sample_weight(class_weight="balanced", y=y), index=y.index
    )

    X_train, X_test, y_train, y_test, sw_train, _ = train_test_split(
        X, y, sample_weight, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )

    model = XGBClassifier(**params)
    model.fit(X_train, y_train, sample_weight=sw_train)
    pred = model.predict(X_test)

    metrics = {
        "f1_macro": float(f1_score(y_test, pred, average="macro")),
        "accuracy": float(accuracy_score(y_test, pred)),
    }

    # OK 클래스(quality_score == 1) 단독 F1
    ok_encoded = encoder.transform([1])[0]
    metrics["f1_ok"] = float(
        f1_score(y_test, pred, labels=[ok_encoded], average="macro", zero_division=0)
    )

    metrics.update(_cv_classification(X, y, sample_weight, params))

    # 최종 모델은 전체 데이터로 재학습
    final_sample_weight = compute_sample_weight(class_weight="balanced", y=y)
    final_model = XGBClassifier(**params)
    final_model.fit(X, y, sample_weight=final_sample_weight)

    return final_model, metrics, encoder
