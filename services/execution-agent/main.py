"""
AI-ADES Execution Agent (Port 8012)

소재 종류/레시피/실험 이력 조회 등 공통 엔드포인트를 제공한다.
Auto DOE 제안 -> 승인/거부 -> 결과 입력 워크플로우는 doe_routes.py로 분리되어 있다.
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import admin
import admin_data
import chat_routes
import doe_routes
import material_types
import recipe_db
from db import get_connection

load_dotenv()

app = FastAPI(title="AI-ADES Execution Agent")

# 프론트엔드(Vite 개발 서버)에서의 직접 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(admin_data.router)
app.include_router(material_types.router)
app.include_router(chat_routes.router)
app.include_router(doe_routes.router)

PORT = int(os.getenv("EXECUTION_PORT", 8012))


def _response(success: bool, data=None, message: str = ""):
    """API 응답 형식 통일"""
    return {"success": success, "data": data, "message": message}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """공통 에러 응답 형식({"success": false, "data": null, "message": ...})으로 통일"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_response(False, None, exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """요청 바디 검증 오류도 공통 응답 형식으로 통일 (예: reason 최소 길이)"""
    first_error = exc.errors()[0]
    field = ".".join(str(loc) for loc in first_error["loc"] if loc != "body")
    return JSONResponse(
        status_code=422,
        content=_response(False, None, f"{field}: {first_error['msg']}"),
    )


@app.get("/health")
def health():
    """서비스 상태 확인"""
    return _response(
        True,
        {"status": "ok", "service": "execution-agent", "port": PORT},
        "정상",
    )


@app.get("/material-types")
def get_active_material_types():
    """실험 조건 입력 화면(M1/M2 소재 종류 선택)에서 사용할 활성 소재 종류 목록을 반환한다"""
    grouped = {"m1": [], "m2": []}
    for t in material_types.list_material_types(active_only=True):
        grouped.setdefault(t["category"], []).append(
            {"id": t["id"], "name": t["name"], "description": t["description"]}
        )
    return _response(True, grouped, "소재 종류 조회 완료")


# ------------------------------------------------------------
# /recipes
# ------------------------------------------------------------
@app.get("/recipes")
def get_recipes():
    """승인된 레시피 전체 목록 조회"""
    recipes = recipe_db.list_recipes()
    return _response(True, {"recipes": recipes, "total": len(recipes)}, "레시피 조회 완료")


@app.get("/experiments")
def get_experiments(
    quality: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """실험 이력(experiments) 조회. quality 필터, exp_no/설명(notes) 검색, 페이지네이션 지원."""
    conditions = []
    params: list = []

    if quality:
        conditions.append("quality = %s")
        params.append(quality)
    if search:
        conditions.append("(exp_no ILIKE %s OR notes ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM experiments {where_clause}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT id, exp_no, m1_glass, m1_length_mm, m2_film, m2_length_mm, thickness_um,
                       speed, defocus, frequency, power, kerf_um, depth_um, quality, quality_score,
                       notes, created_at
                FROM experiments
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    experiments = [
        {
            "id": r[0],
            "exp_no": r[1],
            "m1_glass": r[2],
            "m1_length": float(r[3]) if r[3] is not None else None,
            "m2_film": r[4],
            "m2_length": float(r[5]) if r[5] is not None else None,
            "thickness": float(r[6]) if r[6] is not None else None,
            "speed": float(r[7]) if r[7] is not None else None,
            "defocus": float(r[8]) if r[8] is not None else None,
            "frequency": float(r[9]) if r[9] is not None else None,
            "power": float(r[10]) if r[10] is not None else None,
            "kerf": float(r[11]) if r[11] is not None else None,
            "depth": float(r[12]) if r[12] is not None else None,
            "quality": r[13],
            "quality_score": r[14],
            "notes": r[15],
            "created_at": r[16].isoformat() if r[16] else None,
        }
        for r in rows
    ]

    return _response(
        True,
        {"experiments": experiments, "total": total, "limit": limit, "offset": offset},
        "실험 이력 조회 완료",
    )


@app.get("/recipes/{m1_length}/{m2_length}")
def get_recipe(m1_length: float, m2_length: float, thickness: float | None = None, m1_glass: str = "Glass", m2_film: str = "Film"):
    """
    소재 사양으로 레시피를 조회한다 (정확 매칭 -> 유사 매칭 -> 없음).
    thickness 쿼리 파라미터를 생략하면 두께 조건 없이 m1/m2 길이만으로 조회한다.
    """
    recipe, exact_match = recipe_db.find_recipe(m1_length, m2_length, m1_glass, m2_film, thickness)

    if recipe is None:
        raise HTTPException(status_code=404, detail="레시피 없음. Auto DOE를 실행해주세요.")

    if exact_match:
        message = "레시피 조회 완료"
    else:
        message = "정확히 일치하는 레시피가 없어 유사 레시피를 반환합니다. Thickness 재확인을 권장합니다."

    return _response(True, {"recipe": recipe, "exact_match": exact_match}, message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
