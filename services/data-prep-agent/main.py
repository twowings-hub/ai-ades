"""
AI-ADES Data Preparation Agent (Port 8010)

Excel 업로드 -> 파싱/전처리 -> PostgreSQL/InfluxDB 적재 및
데이터 현황 조회 API를 제공한다.
"""
import os
import tempfile

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile

from excel_parser import parse_excel
from influx_writer import write_to_influx
from preprocessor import load_to_postgres

load_dotenv()

app = FastAPI(title="AI-ADES Data Preparation Agent")

PORT = int(os.getenv("DATA_PREP_PORT", 8010))

# 판정 -> 응답 키 매핑
QUALITY_KEY_MAP = {"OK": "ok", "미가공": "underprocess", "과가공": "overprocess", "NG": "ng"}


def _response(success: bool, data=None, message: str = ""):
    """API 응답 형식 통일"""
    return {"success": success, "data": data, "message": message}


def _get_connection():
    """환경변수(.env) 기반 PostgreSQL 커넥션을 생성한다."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


@app.get("/health")
def health():
    """서비스 상태 확인"""
    return _response(
        True,
        {"status": "ok", "service": "data-prep-agent", "port": PORT},
        "서비스 정상",
    )


@app.post("/data/upload")
async def upload_data(file: UploadFile = File(...)):
    """Excel 파일 업로드 -> 파싱 -> PostgreSQL + InfluxDB 동시 적재"""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Excel 파일(.xlsx, .xls)만 업로드 가능합니다")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        df = parse_excel(tmp_path)
        inserted = load_to_postgres(df)
        write_to_influx(df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"적재 실패: {exc}") from exc
    finally:
        os.remove(tmp_path)

    distribution = {
        QUALITY_KEY_MAP.get(k, k): int(v) for k, v in df["quality"].value_counts().items()
    }

    return _response(
        True,
        {"inserted": inserted, "distribution": distribution},
        f"{inserted}건 적재 완료",
    )


@app.get("/data/summary")
def get_summary():
    """experiments 테이블 전체 현황"""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT quality, COUNT(*) FROM experiments GROUP BY quality")
            rows = cur.fetchall()
    finally:
        conn.close()

    counts = {QUALITY_KEY_MAP.get(q, q): int(c) for q, c in rows}
    summary = {
        "total": sum(counts.values()),
        "ok": counts.get("ok", 0),
        "underprocess": counts.get("underprocess", 0),
        "overprocess": counts.get("overprocess", 0),
        "ng": counts.get("ng", 0),
    }

    return _response(True, summary, "데이터 현황 조회 완료")


@app.get("/data/distribution")
def get_distribution():
    """품질별 분포 + 소재 조합별 집계"""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT quality, COUNT(*) FROM experiments GROUP BY quality")
            quality_rows = cur.fetchall()

            cur.execute(
                """
                SELECT m1_glass, m1_length_mm, m2_film, m2_length_mm, COUNT(*)
                FROM experiments
                GROUP BY m1_glass, m1_length_mm, m2_film, m2_length_mm
                ORDER BY m1_length_mm, m2_length_mm
                """
            )
            material_rows = cur.fetchall()
    finally:
        conn.close()

    by_quality = {QUALITY_KEY_MAP.get(q, q): int(c) for q, c in quality_rows}
    by_material = [
        {
            "m1_glass": m1_glass,
            "m1_length_mm": float(m1_len),
            "m2_film": m2_film,
            "m2_length_mm": float(m2_len),
            "count": int(count),
        }
        for m1_glass, m1_len, m2_film, m2_len, count in material_rows
    ]

    return _response(
        True,
        {"by_quality": by_quality, "by_material": by_material},
        "분포 조회 완료",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
