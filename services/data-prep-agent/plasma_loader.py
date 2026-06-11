"""
AI-ADES Plasma 시계열 PostgreSQL 적재 (Phase 6)

plasma_parser.parse_plasma_zip()의 long-format DataFrame을
plasma_timeseries 테이블에 적재한다. exp_no -> experiments.id로 매핑한다.
"""
import os

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

INSERT_SQL = """
INSERT INTO plasma_timeseries (experiment_id, ts, elapsed_ms, channel, value)
VALUES %s
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


def load_plasma_to_postgres(df: pd.DataFrame) -> dict:
    """
    Plasma 시계열 DataFrame을 plasma_timeseries 테이블에 적재한다.

    Args:
        df: plasma_parser.parse_plasma_zip()의 결과 DataFrame
            (exp_no, elapsed_ms, channel, value 컬럼)

    Returns:
        {"inserted": 적재 행 수, "matched_experiments": 매핑된 실험 수,
         "unknown_exp_no": experiments에 없어 건너뛴 exp_no 목록}
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT exp_no, id FROM experiments")
            exp_id_map = {exp_no: exp_id for exp_no, exp_id in cur.fetchall()}

        target_exp_no = set(df["exp_no"].unique())
        unknown_exp_no = sorted(target_exp_no - set(exp_id_map.keys()))
        if unknown_exp_no:
            df = df[~df["exp_no"].isin(unknown_exp_no)]

        # ts: 절대 시각이 없으므로 적재 시각을 가공 시작 시각으로 보고 elapsed_ms를 더해 산출
        base_ts = pd.Timestamp.now(tz="UTC")
        records = [
            (
                exp_id_map[row.exp_no],
                base_ts + pd.to_timedelta(row.elapsed_ms, unit="ms"),
                row.elapsed_ms,
                row.channel,
                row.value,
            )
            for row in df.itertuples(index=False)
        ]

        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, INSERT_SQL, records, page_size=5000)
    finally:
        conn.close()

    return {
        "inserted": len(records),
        "matched_experiments": len(target_exp_no) - len(unknown_exp_no),
        "unknown_exp_no": unknown_exp_no,
    }
