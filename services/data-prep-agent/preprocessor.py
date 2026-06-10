"""
AI-ADES 전처리 + PostgreSQL 적재

excel_parser에서 만든 DataFrame을 받아 experiments 테이블에 INSERT한다.
"""
import os

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

INSERT_SQL = """
INSERT INTO experiments (
    exp_no, m1_glass, m1_length_mm, m2_film, m2_length_mm, thickness_um,
    speed, defocus, frequency, power, sensor_data_ok,
    kerf_um, depth_um, quality, quality_score, is_outlier
) VALUES (
    %(exp_no)s, %(m1_glass)s, %(m1_length_mm)s, %(m2_film)s, %(m2_length_mm)s, %(thickness_um)s,
    %(speed)s, %(defocus)s, %(frequency)s, %(power)s, %(sensor_data_ok)s,
    %(kerf_um)s, %(depth_um)s, %(quality)s, %(quality_score)s, %(is_outlier)s
)
ON CONFLICT (exp_no) DO NOTHING
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


def load_to_postgres(df: pd.DataFrame) -> int:
    """
    DataFrame을 experiments 테이블에 적재한다.
    exp_no 기준 ON CONFLICT DO NOTHING으로 중복 적재를 방지한다.

    Args:
        df: excel_parser.parse_excel()의 결과 DataFrame

    Returns:
        실제로 INSERT된 건수
    """
    records = df.where(pd.notnull(df), None).to_dict(orient="records")

    conn = _get_connection()
    inserted = 0
    try:
        with conn:
            with conn.cursor() as cur:
                for record in records:
                    cur.execute(INSERT_SQL, record)
                    inserted += cur.rowcount
    finally:
        conn.close()

    return inserted
