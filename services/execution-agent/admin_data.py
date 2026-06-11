"""
AI-ADES Execution Agent — Admin Console 백엔드: 감사 로그 / 서비스 관리 / 데이터 관리
(Phase 4, CLAUDE.md 11-1)
"""
import csv
import io
import os
import subprocess
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db import get_connection
from responses import make_response as _response

router = APIRouter(prefix="/admin", tags=["admin"])

# docker compose 명령 실행 위치 (docker-compose.yml이 있는 프로젝트 루트)
COMPOSE_DIR = os.getenv("COMPOSE_PROJECT_DIR", "/workspace")
# pg_dump 백업 파일 저장 위치
BACKUP_DIR = os.getenv("BACKUP_DIR", "/app/backups")

RESTARTABLE_SERVICES = {
    "data-prep-agent", "modeling-agent", "frontend",
    "influxdb", "mlflow", "grafana", "kafka",
}


# ------------------------------------------------------------
# [감사 로그]
# ------------------------------------------------------------
@router.get("/audit-logs")
def get_audit_logs(
    page: int = 1,
    limit: int = 20,
    action_type: str | None = None,
    operator: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """감사 로그를 최신순으로 페이지네이션 조회한다 (action_type/operator/기간 필터 지원)"""
    conditions = []
    params: list = []

    if action_type:
        conditions.append("action_type = %s")
        params.append(action_type)
    if operator:
        conditions.append("operator = %s")
        params.append(operator)
    if start_date:
        conditions.append("created_at >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= %s")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * limit

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM audit_logs {where}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT id, action_type, operator, description, old_value, new_value, created_at
                FROM audit_logs {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    logs = [
        {
            "id": r[0],
            "action_type": r[1],
            "operator": r[2],
            "description": r[3],
            "old_value": r[4],
            "new_value": r[5],
            "created_at": r[6].isoformat(),
        }
        for r in rows
    ]

    return _response(True, {"logs": logs, "total": total, "page": page, "limit": limit}, "감사 로그 조회 완료")


# ------------------------------------------------------------
# [서비스 관리]
# ------------------------------------------------------------
@router.post("/services/{service_name}/restart")
def restart_service(service_name: str):
    """docker-compose restart {service_name} 실행 (execution-agent 자기 자신은 차단)"""
    if service_name == "execution-agent":
        return _response(
            False,
            None,
            "execution-agent는 자기 자신을 재시작할 수 없습니다. 수동으로 재시작해주세요.",
        )

    if service_name not in RESTARTABLE_SERVICES:
        raise HTTPException(status_code=404, detail=f"알 수 없는 서비스: {service_name}")

    try:
        result = subprocess.run(
            ["docker", "compose", "restart", service_name],
            cwd=COMPOSE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return _response(False, None, f"재시작 명령 실행 실패: {exc}")

    if result.returncode != 0:
        return _response(False, {"stderr": result.stderr.strip()}, f"{service_name} 재시작 실패")

    return _response(True, {"service": service_name}, f"{service_name} 재시작 완료")


# ------------------------------------------------------------
# [데이터 관리]
# ------------------------------------------------------------
@router.get("/data/stats")
def data_stats():
    """테이블별 건수/이상값/최근 백업 시각을 조회한다"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_outlier = TRUE) FROM experiments")
            exp_total, exp_outliers = cur.fetchone()

            cur.execute("SELECT COUNT(*) FROM recipes")
            recipes_total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM approvals")
            approvals_total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM audit_logs")
            audit_total = cur.fetchone()[0]
    finally:
        conn.close()

    last_backup = None
    if os.path.isdir(BACKUP_DIR):
        files = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".sql")]
        if files:
            files.sort(reverse=True)
            last_backup_path = os.path.join(BACKUP_DIR, files[0])
            last_backup = datetime.fromtimestamp(os.path.getmtime(last_backup_path)).isoformat()

    return _response(
        True,
        {
            "tables": {
                "experiments": {"count": exp_total, "outliers": exp_outliers},
                "recipes": {"count": recipes_total},
                "approvals": {"count": approvals_total},
                "audit_logs": {"count": audit_total},
            },
            "last_backup": last_backup,
        },
        "데이터 현황 조회 완료",
    )


@router.post("/data/backup")
def data_backup():
    """pg_dump로 ades_db 전체를 /app/backups에 백업한다"""
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ades_db_{timestamp}.sql"
    filepath = os.path.join(BACKUP_DIR, filename)

    env = os.environ.copy()
    env["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            result = subprocess.run(
                [
                    "pg_dump",
                    "-h", os.getenv("POSTGRES_HOST", "pm-postgres"),
                    "-p", os.getenv("POSTGRES_PORT", "5432"),
                    "-U", os.getenv("POSTGRES_USER", "ades"),
                    "-d", os.getenv("POSTGRES_DB", "ades_db"),
                ],
                env=env,
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return _response(False, None, f"백업 실행 실패: {exc}")

    if result.returncode != 0:
        if os.path.exists(filepath):
            os.remove(filepath)
        return _response(False, {"stderr": result.stderr.strip()}, "백업 실패")

    return _response(True, {"filename": filename, "path": filepath}, "백업 완료")


@router.get("/data/export")
def data_export():
    """experiments 테이블을 CSV로 다운로드한다"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM experiments ORDER BY id")
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
    finally:
        conn.close()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        yield buf.getvalue()
        for row in rows:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(row)
            yield buf.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=experiments.csv"},
    )
