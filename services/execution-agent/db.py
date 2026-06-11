"""
AI-ADES Execution Agent — 공통 DB 연결 및 품질 판정 유틸리티
"""
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# quality_score 매핑 (CLAUDE.md 4절 기준, 절대 변경 금지)
QUALITY_SCORE = {"OK": 1, "미가공": 0, "과가공": -1, "NG": -2}


def get_connection():
    """환경변수(.env) 기반 PostgreSQL 커넥션을 생성한다."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def judge_quality(depth: float) -> str:
    """
    Depth(μm) 값으로 가공 품질을 판정한다.
    기준값은 .env의 DEPTH_OK_MIN/DEPTH_OK_MAX를 사용한다 (하드코딩 금지).

    - 미가공: depth > DEPTH_OK_MAX
    - 과가공: depth <= DEPTH_OK_MIN
    - OK    : DEPTH_OK_MIN < depth <= DEPTH_OK_MAX
    """
    ok_min = float(os.getenv("DEPTH_OK_MIN", 0.0))
    ok_max = float(os.getenv("DEPTH_OK_MAX", 25.0))

    if depth > ok_max:
        return "미가공"
    if depth <= ok_min:
        return "과가공"
    return "OK"
