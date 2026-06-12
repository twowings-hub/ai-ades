"""
AI-ADES Auto DOE — Bayesian Optimization (BoTorch GP, CPU)

탐색 공간(speed/defocus/frequency/power)은 .env SEARCH_SPACE_* 값을 사용한다 (하드코딩 금지).
이산 변수(speed/defocus/frequency)는 연속 공간에서 탐색한 뒤 가장 가까운 유효값으로 스냅한다.
획득 함수는 Expected Improvement(EI)를 사용하며, 목표는 depth_pred가 OK 범위
(DEPTH_OK_MIN < depth <= DEPTH_OK_MAX)에 들도록 하는 것이다 (과가공 depth<=0 방지).
"""
import os

import pandas as pd
import torch
from botorch.acquisition import LogExpectedImprovement
from botorch.fit import fit_gpytorch_mll
from botorch.models import SingleTaskGP
from botorch.optim import optimize_acqf
from dotenv import load_dotenv
from gpytorch.mlls import ExactMarginalLogLikelihood

from db import get_connection

load_dotenv()

PARAM_ORDER = ["speed", "defocus", "frequency", "power"]


def _search_space() -> dict:
    """.env SEARCH_SPACE_* 값을 파싱한다."""
    return {
        "speed": [float(v) for v in os.getenv("SEARCH_SPACE_SPEED", "200,500,1000").split(",")],
        "defocus": [float(v) for v in os.getenv("SEARCH_SPACE_DEFOCUS", "0,1,2,3,4").split(",")],
        "frequency": [float(v) for v in os.getenv("SEARCH_SPACE_FREQUENCY", "100,200").split(",")],
        "power": (
            float(os.getenv("SEARCH_SPACE_POWER_MIN", "2.8")),
            float(os.getenv("SEARCH_SPACE_POWER_MAX", "59.8")),
        ),
    }


def _load_experiments_df() -> pd.DataFrame:
    """experiments 테이블(328건)을 GP 초기 관측값으로 로드한다."""
    conn = get_connection()
    try:
        df = pd.read_sql(
            """
            SELECT speed, defocus, frequency, power, depth_um AS depth
            FROM experiments
            WHERE sensor_data_ok = TRUE AND is_outlier = FALSE
              AND speed IS NOT NULL AND defocus IS NOT NULL
              AND frequency IS NOT NULL AND power IS NOT NULL
              AND depth_um IS NOT NULL
            """,
            conn,
        )
    finally:
        conn.close()
    return df


def _history_to_df(experiment_history: list) -> pd.DataFrame:
    """이번 세션의 시도 이력(experiment_history)을 학습 데이터 형식으로 변환한다."""
    if not experiment_history:
        return pd.DataFrame(columns=PARAM_ORDER + ["depth"])

    rows = [
        {
            "speed": h["speed"],
            "defocus": h["defocus"],
            "frequency": h["frequency"],
            "power": h["power"],
            "depth": h["actual_depth"],
        }
        for h in experiment_history
    ]
    return pd.DataFrame(rows)


def _normalize(df: pd.DataFrame, space: dict) -> torch.Tensor:
    """탐색 공간 범위를 기준으로 [0, 1] 범위로 정규화한다."""
    speed_min, speed_max = min(space["speed"]), max(space["speed"])
    defocus_min, defocus_max = min(space["defocus"]), max(space["defocus"])
    freq_min, freq_max = min(space["frequency"]), max(space["frequency"])
    power_min, power_max = space["power"]

    norm = pd.DataFrame()
    norm["speed"] = (df["speed"] - speed_min) / (speed_max - speed_min)
    norm["defocus"] = (df["defocus"] - defocus_min) / (defocus_max - defocus_min)
    norm["frequency"] = (df["frequency"] - freq_min) / (freq_max - freq_min)
    norm["power"] = (df["power"] - power_min) / (power_max - power_min)
    return torch.tensor(norm[PARAM_ORDER].values, dtype=torch.double)


def _score(depth: float) -> float:
    """
    GP 학습 목표값.
    OK 범위(DEPTH_OK_MIN < depth <= DEPTH_OK_MAX) 중심에 가까울수록 높은 점수,
    과가공(depth <= DEPTH_OK_MIN)은 큰 페널티를 부여해 탐색에서 배제되도록 한다.
    """
    ok_min = float(os.getenv("DEPTH_OK_MIN", 0.0))
    ok_max = float(os.getenv("DEPTH_OK_MAX", 25.0))
    target = (ok_min + ok_max) / 2

    if depth <= ok_min:
        return -100.0 - abs(depth)
    if depth > ok_max:
        return -abs(depth - target)
    return 10.0 - abs(depth - target)


def _snap_discrete(value: float, candidates: list) -> float:
    """연속 탐색 결과를 가장 가까운 이산 유효값으로 스냅한다."""
    return min(candidates, key=lambda c: abs(c - value))


def suggest_params(experiment_history: list) -> dict:
    """
    GP(BoTorch) + Expected Improvement 기반 다음 실험 조건을 제안한다.

    Args:
        experiment_history: 이번 세션에서 시도한
            [{"speed", "defocus", "frequency", "power", "actual_depth", ...}, ...]
            (빈 배열이면 experiments 테이블 328건만으로 GP를 초기화한다)

    Returns:
        {"speed": ..., "defocus": ..., "frequency": ..., "power": ...}
    """
    space = _search_space()

    base_df = _load_experiments_df()
    history_df = _history_to_df(experiment_history)
    train_df = pd.concat([base_df, history_df], ignore_index=True).dropna()

    train_X = _normalize(train_df, space)
    train_Y = torch.tensor([[_score(d)] for d in train_df["depth"]], dtype=torch.double)

    model = SingleTaskGP(train_X, train_Y)
    mll = ExactMarginalLogLikelihood(model.likelihood, model)
    fit_gpytorch_mll(mll)

    acq = LogExpectedImprovement(model, best_f=train_Y.max(), maximize=True)
    bounds = torch.tensor([[0.0] * 4, [1.0] * 4], dtype=torch.double)
    candidate, _ = optimize_acqf(
        acq_function=acq,
        bounds=bounds,
        q=1,
        num_restarts=10,
        raw_samples=64,
    )

    cand = candidate[0].tolist()
    speed_min, speed_max = min(space["speed"]), max(space["speed"])
    defocus_min, defocus_max = min(space["defocus"]), max(space["defocus"])
    freq_min, freq_max = min(space["frequency"]), max(space["frequency"])
    power_min, power_max = space["power"]

    suggested_speed = speed_min + cand[0] * (speed_max - speed_min)
    suggested_defocus = defocus_min + cand[1] * (defocus_max - defocus_min)
    suggested_frequency = freq_min + cand[2] * (freq_max - freq_min)
    suggested_power = power_min + cand[3] * (power_max - power_min)

    return {
        "speed": _snap_discrete(suggested_speed, space["speed"]),
        "defocus": _snap_discrete(suggested_defocus, space["defocus"]),
        "frequency": _snap_discrete(suggested_frequency, space["frequency"]),
        "power": round(min(max(suggested_power, power_min), power_max), 2),
    }
