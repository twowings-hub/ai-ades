"""
AI-ADES Plasma 시계열 데이터 로딩 (Phase 6)

plasma_timeseries 테이블에서 실험별 시계열을 로드하고,
LSTM-Autoencoder 학습에 사용할 wide-format(시간 x 채널) DataFrame으로 변환한다.
"""
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# plasma_parser.PLASMA_CHANNELS와 동일 (data-prep-agent와 모델 입력 채널 순서를 맞춤)
PLASMA_CHANNELS = ["Area", "Plasma", "P-Raw", "Temp", "T-Raw", "Refl", "R-Raw"]

# M1/M2/Blank 구간 분리 (Phase 6 자동 분리 로직 도입 전 임시 placeholder)
# TODO: 실제 현장 데이터 확보 후 신호 변화점(change-point) 기반 분리로 교체
SEGMENT_LABELS = ["M1", "M2", "Blank"]


def _get_connection():
    """환경변수(.env) 기반 PostgreSQL 커넥션을 생성한다."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def list_experiment_ids() -> list[int]:
    """plasma_timeseries에 데이터가 존재하는 experiment_id 목록을 반환한다."""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT experiment_id FROM plasma_timeseries ORDER BY experiment_id")
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def load_plasma_wide(experiment_id: int) -> pd.DataFrame:
    """
    단일 실험의 Plasma 시계열을 wide-format(행=시간, 열=채널)으로 로드한다.

    Args:
        experiment_id: experiments.id

    Returns:
        elapsed_ms 오름차순 정렬, PLASMA_CHANNELS 컬럼을 포함한 DataFrame
        (결측 채널 값은 직전 값으로 보간)
    """
    conn = _get_connection()
    try:
        df = pd.read_sql(
            """
            SELECT elapsed_ms, channel, value
            FROM plasma_timeseries
            WHERE experiment_id = %(experiment_id)s
            ORDER BY elapsed_ms
            """,
            conn,
            params={"experiment_id": experiment_id},
        )
    finally:
        conn.close()

    if df.empty:
        return pd.DataFrame(columns=["elapsed_ms"] + PLASMA_CHANNELS)

    wide = df.pivot_table(index="elapsed_ms", columns="channel", values="value", aggfunc="mean")
    wide = wide.reindex(columns=PLASMA_CHANNELS)
    wide = wide.sort_index().ffill().bfill().reset_index()

    return wide


def split_segments(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Plasma 시계열을 M1 / M2 / Blank 구간으로 분리한다.

    현재는 행 개수를 동일 비율로 3등분하는 placeholder 구현이다.
    실제 가공에서는 M1(Glass)/M2(Film) 절단 시점에 Plasma 신호가
    뚜렷이 변화하므로, 추후 신호 크기/기울기 기반 change-point 탐지로 교체한다.

    Returns:
        {"M1": df, "M2": df, "Blank": df}
    """
    n = len(df)
    third = n // 3
    return {
        "M1": df.iloc[:third].reset_index(drop=True),
        "M2": df.iloc[third : 2 * third].reset_index(drop=True),
        "Blank": df.iloc[2 * third :].reset_index(drop=True),
    }
