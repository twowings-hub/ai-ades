"""
AI-ADES 운영자 승인 시스템

승인 토큰: UUID 기반, 유효기간 24시간
승인/거부/수정 이력은 approvals 테이블에, 감사 기록은 audit_logs 테이블에 남긴다.
"""
import uuid
from datetime import datetime, timedelta

from psycopg2.extras import Json

from db import get_connection

TOKEN_TTL_HOURS = 24


def create_approval(suggestion_id: str, ai_params: dict, final_params: dict, operator_name: str, is_modified: bool = False):
    """승인(또는 수정 후 승인) 기록을 저장하고 (approval_token, expires_at)을 반환한다."""
    token = f"tok_{uuid.uuid4().hex[:16]}"
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)
    status = "modified" if is_modified else "approved"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 같은 suggestion_id로 재승인(중복 클릭, 재방문 등)하면 기존 기록을 갱신한다
            cur.execute(
                """
                INSERT INTO approvals (
                    suggestion_id, status, ai_params, final_params,
                    operator_name, token, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (suggestion_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    ai_params = EXCLUDED.ai_params,
                    final_params = EXCLUDED.final_params,
                    operator_name = EXCLUDED.operator_name,
                    token = EXCLUDED.token,
                    expires_at = EXCLUDED.expires_at
                """,
                (suggestion_id, status, Json(ai_params), Json(final_params), operator_name, token, expires_at),
            )
        conn.commit()
        return token, expires_at
    finally:
        conn.close()


def create_rejection(suggestion_id: str, ai_params: dict, operator_name: str, reason: str):
    """거부 기록을 저장한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO approvals (
                    suggestion_id, status, ai_params, operator_name, reason
                ) VALUES (%s, 'rejected', %s, %s, %s)
                """,
                (suggestion_id, Json(ai_params), operator_name, reason),
            )
        conn.commit()
    finally:
        conn.close()


def update_recipe_id(suggestion_id: str, recipe_id: int):
    """OK 판정 후 approvals.recipe_id를 갱신한다 (status는 유지)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE approvals SET recipe_id = %s WHERE suggestion_id = %s",
                (recipe_id, suggestion_id),
            )
        conn.commit()
    finally:
        conn.close()


def log_audit(action_type: str, operator: str, description: str, old_value: dict = None, new_value: dict = None):
    """audit_logs 테이블에 감사 기록을 남긴다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (action_type, operator, description, old_value, new_value)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    action_type,
                    operator,
                    description,
                    Json(old_value) if old_value is not None else None,
                    Json(new_value) if new_value is not None else None,
                ),
            )
        conn.commit()
    finally:
        conn.close()
