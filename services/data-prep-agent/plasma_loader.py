"""
AI-ADES Plasma 시계열 PostgreSQL 적재 (Phase 6)

plasma_parser.parse_plasma_csv() / detect_region() / downsample() 결과를
plasma_timeseries(시계열) + plasma_measurements(파일별 메타데이터/예외 플래그) 테이블에 적재한다.
exp_no -> experiments.id로 매핑한다.
"""
import os

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from plasma_parser import PLASMA_CHANNELS

load_dotenv()

# 배치 적재 단위
BATCH_SIZE = 5000

INSERT_TIMESERIES_SQL = """
INSERT INTO plasma_timeseries (experiment_id, ts, elapsed_ms, channel, value, region)
VALUES %s
"""

INSERT_MEASUREMENT_SQL = """
INSERT INTO plasma_measurements (
    exp_no, experiment_id, configuration, config_id, measurement_id,
    result, comment, measured_at, duration_s, sample_rate_hz, n_samples,
    m1_measured, m2_measured, time_shifted
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _get_connection():
    """환경변수(.env) 기반 PostgreSQL 커넥션을 생성한다."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def _to_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except ValueError:
        return None


def _to_timestamp(value: str | None):
    try:
        return pd.to_datetime(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None


def load_to_db(meta: dict, df: pd.DataFrame, regions: dict) -> int:
    """
    Plasma 시계열(다운샘플 완료, region 컬럼 포함) + 메타데이터를 DB에 적재한다.

    Args:
        meta: parse_plasma_csv()의 meta (exp_no, MeasurementID, Result, ConfigID, Duration, ... 포함)
        df: downsample() 결과 DataFrame (Time, PLASMA_CHANNELS, region 컬럼 포함)
        regions: detect_region() 결과 ({"m1_measured", "m2_measured", "time_shifted"})

    Returns:
        plasma_timeseries에 적재된 행 수 (exp_no가 experiments에 없으면 0건, 메타데이터만 기록)
    """
    exp_no = meta.get("exp_no")

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM experiments WHERE exp_no = %s", (exp_no,))
            row = cur.fetchone()
        experiment_id = row[0] if row else None

        n_inserted = 0
        if experiment_id is not None:
            long_df = df.melt(
                id_vars=["Time", "region"],
                value_vars=PLASMA_CHANNELS,
                var_name="channel",
                value_name="value",
            )

            base_ts = pd.Timestamp.now(tz="UTC")
            records = [
                (
                    experiment_id,
                    base_ts + pd.to_timedelta(r.Time, unit="s"),
                    r.Time * 1000.0,
                    r.channel,
                    float(r.value),
                    r.region,
                )
                for r in long_df.itertuples(index=False)
            ]

            with conn.cursor() as cur:
                for i in range(0, len(records), BATCH_SIZE):
                    psycopg2.extras.execute_values(
                        cur, INSERT_TIMESERIES_SQL, records[i : i + BATCH_SIZE], page_size=BATCH_SIZE
                    )
            n_inserted = len(records)

        with conn.cursor() as cur:
            cur.execute(
                INSERT_MEASUREMENT_SQL,
                (
                    exp_no,
                    experiment_id,
                    meta.get("Configuration"),
                    meta.get("ConfigID"),
                    meta.get("MeasurementID"),
                    meta.get("Result"),
                    meta.get("Comment"),
                    _to_timestamp(meta.get("Date")),
                    _to_float(meta.get("Duration")),
                    _to_int(meta.get("Sample Rate")),
                    len(df),
                    regions.get("m1_measured"),
                    regions.get("m2_measured"),
                    regions.get("time_shifted"),
                ),
            )

        conn.commit()
    finally:
        conn.close()

    return n_inserted


def get_plasma_summary() -> dict:
    """plasma_measurements / plasma_timeseries 적재 현황 + 예외 케이스 건수를 조회한다."""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM plasma_measurements")
            total_files = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM plasma_measurements WHERE experiment_id IS NULL")
            unmatched_exp_no = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM plasma_measurements WHERE m1_measured = FALSE")
            m1_not_measured = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM plasma_measurements WHERE m2_measured = FALSE")
            m2_not_measured = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM plasma_measurements WHERE time_shifted = TRUE")
            time_shifted = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM plasma_timeseries")
            total_samples = cur.fetchone()[0]
    finally:
        conn.close()

    return {
        "total_files": total_files,
        "unmatched_exp_no": unmatched_exp_no,
        "m1_not_measured": m1_not_measured,
        "m2_not_measured": m2_not_measured,
        "time_shifted": time_shifted,
        "total_samples": total_samples,
    }
