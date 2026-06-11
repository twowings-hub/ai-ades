"""
AI-ADES 소재 종류(Material Types) 관리

M1(Glass)/M2(Film) 소재 종류를 관리자 화면에서 등록/수정/비활성화하고,
실험 조건 입력 화면(ExperimentPage)에서 선택할 수 있도록 제공한다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import approval
from db import get_connection
from responses import make_response as _response

router = APIRouter(prefix="/admin/material-types", tags=["material-types"])

VALID_CATEGORIES = {"m1", "m2"}


def _to_dict(row) -> dict:
    return {
        "id": row[0],
        "category": row[1],
        "name": row[2],
        "description": row[3],
        "is_active": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
    }


def list_material_types(active_only: bool = False) -> list:
    """소재 종류 목록을 조회한다 (active_only=True면 활성 항목만)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            query = "SELECT id, category, name, description, is_active, created_at FROM material_types"
            if active_only:
                query += " WHERE is_active = TRUE"
            query += " ORDER BY category, name"
            cur.execute(query)
            return [_to_dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


@router.get("")
def get_material_types():
    """소재 종류 전체 목록을 조회한다 (관리자 화면)"""
    types = list_material_types()
    return _response(True, {"material_types": types, "total": len(types)}, "소재 종류 조회 완료")


class MaterialTypeCreateRequest(BaseModel):
    category: str
    name: str
    description: str | None = None
    operator_name: str = "admin"


@router.post("")
def create_material_type(req: MaterialTypeCreateRequest):
    """소재 종류를 추가한다 (category: 'm1' 또는 'm2')"""
    if req.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="category는 'm1' 또는 'm2'만 가능합니다")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM material_types WHERE category = %s AND name = %s", (req.category, req.name))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="이미 등록된 소재 종류입니다")

            cur.execute(
                """
                INSERT INTO material_types (category, name, description)
                VALUES (%s, %s, %s)
                RETURNING id, created_at
                """,
                (req.category, req.name, req.description),
            )
            material_type_id, created_at = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    approval.log_audit(
        action_type="setting_change",
        operator=req.operator_name,
        description=f"소재 종류 추가: {req.category}/{req.name}",
        new_value={"category": req.category, "name": req.name, "description": req.description},
    )

    return _response(
        True,
        {
            "id": material_type_id,
            "category": req.category,
            "name": req.name,
            "description": req.description,
            "is_active": True,
            "created_at": created_at.isoformat(),
        },
        "소재 종류가 추가되었습니다",
    )


class MaterialTypeUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    operator_name: str = "admin"


@router.patch("/{material_type_id}")
def update_material_type(material_type_id: int, req: MaterialTypeUpdateRequest):
    """소재 종류 정보를 수정하거나 활성/비활성 처리한다"""
    set_clauses = []
    values = []
    if req.name is not None:
        set_clauses.append("name = %s")
        values.append(req.name)
    if req.description is not None:
        set_clauses.append("description = %s")
        values.append(req.description)
    if req.is_active is not None:
        set_clauses.append("is_active = %s")
        values.append(req.is_active)

    if not set_clauses:
        raise HTTPException(status_code=400, detail="변경할 값이 없습니다")

    values.append(material_type_id)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE material_types SET {', '.join(set_clauses)} WHERE id = %s RETURNING id",
                values,
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="소재 종류를 찾을 수 없습니다")
        conn.commit()
    finally:
        conn.close()

    approval.log_audit(
        action_type="setting_change",
        operator=req.operator_name,
        description=f"소재 종류 수정: id={material_type_id}",
        new_value=req.model_dump(exclude_unset=True, exclude={"operator_name"}),
    )

    return _response(True, {"id": material_type_id}, "소재 종류가 수정되었습니다")


@router.delete("/{material_type_id}")
def delete_material_type(material_type_id: int, operator_name: str = "admin"):
    """소재 종류를 삭제한다 (기존 실험/레시피 데이터의 소재명에는 영향을 주지 않음)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM material_types WHERE id = %s RETURNING category, name",
                (material_type_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="소재 종류를 찾을 수 없습니다")
        conn.commit()
    finally:
        conn.close()

    approval.log_audit(
        action_type="setting_change",
        operator=operator_name,
        description=f"소재 종류 삭제: {row[0]}/{row[1]}",
        old_value={"category": row[0], "name": row[1]},
    )

    return _response(True, {"id": material_type_id}, "소재 종류가 삭제되었습니다")
