"""
AI-ADES Feature Engineering

experiments 테이블에서 학습 데이터를 로드하고
물리적 의미 기반 파생 변수를 추가한다.
"""
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# 모델 입력에 사용하는 최종 feature 목록
FEATURE_COLUMNS = [
    "speed",
    "defocus",
    "frequency",
    "power",
    "m1_length",
    "m2_length",
    "thickness",
    "energy_density",
    "power_x_defocus",
    "freq_x_power",
    "thickness_ratio",
    "normalized_power",
]


def _get_connection():
    """환경변수(.env) 기반 PostgreSQL 커넥션을 생성한다."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def load_training_data() -> pd.DataFrame:
    """
    experiments 테이블에서 학습 가능한 데이터만 로드한다.
    - sensor_data_ok = TRUE (센서 없음 7건 제외)
    - is_outlier = FALSE (Thickness > 140um 이상값 2건 제외)
    """
    query = """
        SELECT
            exp_no,
            m1_length_mm AS m1_length,
            m2_length_mm AS m2_length,
            thickness_um AS thickness,
            speed,
            defocus,
            frequency,
            power,
            kerf_um AS kerf,
            depth_um AS depth,
            quality,
            quality_score
        FROM experiments
        WHERE sensor_data_ok = TRUE AND is_outlier = FALSE
    """
    conn = _get_connection()
    try:
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    return df.astype(
        {
            "m1_length": "float64",
            "m2_length": "float64",
            "thickness": "float64",
            "speed": "float64",
            "defocus": "float64",
            "frequency": "float64",
            "power": "float64",
            "kerf": "float64",
            "depth": "float64",
            "quality_score": "int64",
        }
    )


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    물리적 의미 기반 파생 변수를 추가한다.

    - energy_density   = power / speed           (W·s/mm, 에너지 밀도)
    - power_x_defocus  = power * defocus         (출력-초점 교호작용, defocus=0이면 0)
    - freq_x_power     = frequency * power       (주파수-출력 교호작용)
    - thickness_ratio  = m1_length / m2_length   (소재 비율)
    - normalized_power = power / (speed / 1000)  (속도 정규화 출력)
    """
    df = df.copy()
    df["energy_density"] = df["power"] / df["speed"]
    df["power_x_defocus"] = df["power"] * df["defocus"]
    df["freq_x_power"] = df["frequency"] * df["power"]
    df["thickness_ratio"] = df["m1_length"] / df["m2_length"]
    df["normalized_power"] = df["power"] / (df["speed"] / 1000)
    return df


def build_feature_dataframe() -> pd.DataFrame:
    """학습용 DataFrame(원본 + 파생 변수)을 반환한다."""
    df = load_training_data()
    df = add_derived_features(df)
    return df


def build_features_for_input(payload: dict) -> pd.DataFrame:
    """
    /predict 요청 입력(dict)으로부터 단일 행 feature DataFrame을 생성한다.

    Args:
        payload: speed, defocus, frequency, power, m1_length, m2_length, thickness 포함

    Returns:
        FEATURE_COLUMNS 순서의 단일 행 DataFrame
    """
    df = pd.DataFrame([payload])
    df = add_derived_features(df)
    return df[FEATURE_COLUMNS]


if __name__ == "__main__":
    data = build_feature_dataframe()
    print(f"학습 데이터 {len(data)}건 로드 완료")
    print(data[FEATURE_COLUMNS + ["kerf", "depth", "quality", "quality_score"]].head())
