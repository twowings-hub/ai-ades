"""
AI-ADES Data Preparation Agent (Port 8010)

Excel 업로드 -> 파싱/전처리 -> PostgreSQL/InfluxDB 적재 및
데이터 현황 조회 API를 제공한다.
"""
import os
import tempfile

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from excel_parser import parse_excel
from influx_writer import write_to_influx
from plasma_loader import load_plasma_to_postgres
from plasma_parser import parse_plasma_zip
from preprocessor import load_to_postgres

load_dotenv()

app = FastAPI(title="AI-ADES Data Preparation Agent")

# 프론트엔드(Vite 개발 서버)에서의 직접 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.getenv("DATA_PREP_PORT", 8010))
EXECUTION_AGENT_URL = os.getenv("EXECUTION_AGENT_URL", "http://execution-agent:8012")

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


def _check_auto_retrain():
    """execution-agent에 자동 재학습 조건(experiments 누적 건수)을 확인 요청한다 (Phase 6).
    실패해도 업로드 자체는 영향받지 않도록 예외를 무시한다."""
    try:
        requests.post(f"{EXECUTION_AGENT_URL}/admin/model/check-auto-retrain", timeout=5)
    except requests.RequestException:
        pass


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

    if inserted > 0:
        _check_auto_retrain()

    return _response(
        True,
        {"inserted": inserted, "distribution": distribution},
        f"{inserted}건 적재 완료",
    )


@app.post("/data/plasma/upload")
async def upload_plasma(file: UploadFile = File(...)):
    """Plasma 센서 ZIP 업로드 -> 파싱 -> plasma_timeseries 적재 (Phase 6)"""
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="ZIP 파일(.zip)만 업로드 가능합니다")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        df = parse_plasma_zip(tmp_path)
        result = load_plasma_to_postgres(df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"적재 실패: {exc}") from exc
    finally:
        os.remove(tmp_path)

    message = f"{result['inserted']}건 적재 완료 ({result['matched_experiments']}개 실험)"
    if result["unknown_exp_no"]:
        message += f" / 미매칭 exp_no 건너뜀: {result['unknown_exp_no']}"

    return _response(True, result, message)


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

            cur.execute(
                """
                SELECT MIN(m1_length_mm), MAX(m1_length_mm),
                       MIN(m2_length_mm), MAX(m2_length_mm),
                       MIN(thickness_um), MAX(thickness_um)
                FROM experiments
                """
            )
            range_row = cur.fetchone()
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

    # 학습 데이터 범위 (이 범위를 벗어난 입력값은 모델 예측이 외삽(extrapolation)이 되므로
    # 운영자에게 신뢰도 경고를 표시하는 데 사용한다)
    data_ranges = {
        "m1_length_mm": {"min": float(range_row[0]), "max": float(range_row[1])} if range_row[0] is not None else None,
        "m2_length_mm": {"min": float(range_row[2]), "max": float(range_row[3])} if range_row[2] is not None else None,
        "thickness_um": {"min": float(range_row[4]), "max": float(range_row[5])} if range_row[4] is not None else None,
    }

    return _response(
        True,
        {"by_quality": by_quality, "by_material": by_material, "data_ranges": data_ranges},
        "분포 조회 완료",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
