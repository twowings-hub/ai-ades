"""
AI-ADES 레시피 DB 관리

조회 우선순위:
  1순위: m1_length + m2_length + thickness(±5μm) -> 정확 매칭
  2순위: m1_length + m2_length만 일치 -> 유사 레시피 (경고)
  3순위: 없음 -> Auto DOE 실행
"""
from db import get_connection

THICKNESS_TOLERANCE_UM = 5.0

_RECIPE_COLUMNS = """
    id, m1_glass, m1_length_mm, m2_film, m2_length_mm, thickness_um,
    speed, defocus, frequency, power,
    pred_kerf_um, pred_depth_um, pred_quality, confidence,
    doe_attempts, approved_by, created_at
"""


def _to_dict(row) -> dict:
    return {
        "id": row[0],
        "m1_glass": row[1],
        "m1_length": float(row[2]) if row[2] is not None else None,
        "m2_film": row[3],
        "m2_length": float(row[4]) if row[4] is not None else None,
        "thickness": float(row[5]) if row[5] is not None else None,
        "opt_speed": float(row[6]) if row[6] is not None else None,
        "opt_defocus": float(row[7]) if row[7] is not None else None,
        "opt_frequency": float(row[8]) if row[8] is not None else None,
        "opt_power": float(row[9]) if row[9] is not None else None,
        "pred_kerf": float(row[10]) if row[10] is not None else None,
        "pred_depth": float(row[11]) if row[11] is not None else None,
        "pred_quality": row[12],
        "confidence": float(row[13]) if row[13] is not None else None,
        "doe_attempts": row[14],
        "approved_by": row[15],
        "created_at": row[16].isoformat() if row[16] else None,
    }


def find_recipe(m1_length: float, m2_length: float, m1_glass: str = "Glass", m2_film: str = "Film", thickness: float | None = None):
    """
    레시피를 우선순위에 따라 조회한다.

    Args:
        thickness: None이면 두께(±5μm) 조건 없이 m1/m2 길이만으로 조회한다.

    Returns:
        (recipe: dict | None, exact_match: bool | None)
        - 정확 매칭: (recipe, True)
        - 유사 매칭: (recipe, False)
        - 없음:      (None, None)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if thickness is not None:
                cur.execute(
                    f"""
                    SELECT {_RECIPE_COLUMNS}
                    FROM recipes
                    WHERE status = 'approved'
                      AND m1_glass = %s AND m1_length_mm = %s
                      AND m2_film = %s AND m2_length_mm = %s
                      AND ABS(thickness_um - %s) <= %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (m1_glass, m1_length, m2_film, m2_length, thickness, THICKNESS_TOLERANCE_UM),
                )
                row = cur.fetchone()
                if row:
                    return _to_dict(row), True

            cur.execute(
                f"""
                SELECT {_RECIPE_COLUMNS}
                FROM recipes
                WHERE status = 'approved'
                  AND m1_glass = %s AND m1_length_mm = %s
                  AND m2_film = %s AND m2_length_mm = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (m1_glass, m1_length, m2_film, m2_length),
            )
            row = cur.fetchone()
            if row:
                return _to_dict(row), False

            return None, None
    finally:
        conn.close()


def list_recipes() -> list:
    """승인된 레시피 전체 목록을 최신순으로 조회한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_RECIPE_COLUMNS}
                FROM recipes
                WHERE status = 'approved'
                ORDER BY created_at DESC
                """
            )
            return [_to_dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def save_recipe(
    m1_length: float,
    m2_length: float,
    thickness: float,
    params: dict,
    pred: dict,
    doe_attempts: int,
    approved_by: str,
    m1_glass: str = "Glass",
    m2_film: str = "Film",
) -> int:
    """OK 판정 시 새 레시피를 저장하고 recipe id를 반환한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO recipes (
                    m1_glass, m1_length_mm, m2_film, m2_length_mm, thickness_um,
                    speed, defocus, frequency, power,
                    pred_kerf_um, pred_depth_um, pred_quality, confidence,
                    doe_attempts, status, approved_by, approved_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, 'approved', %s, NOW()
                )
                RETURNING id
                """,
                (
                    m1_glass, m1_length, m2_film, m2_length, thickness,
                    params["speed"], params["defocus"], params["frequency"], params["power"],
                    pred.get("pred_kerf"), pred.get("pred_depth"), pred.get("pred_quality"), pred.get("confidence"),
                    doe_attempts, approved_by,
                ),
            )
            recipe_id = cur.fetchone()[0]
        conn.commit()
        return recipe_id
    finally:
        conn.close()
