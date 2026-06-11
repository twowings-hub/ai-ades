"""
AI-ADES Execution Agent — Admin Console 백엔드 (Phase 4, CLAUDE.md 11-1)

시스템 상태 / LLM 관리 / 모델 재학습 / 설정 관리 / 사용자 관리 / 알림 설정을 담당한다.
감사 로그(audit_logs) / 서비스 관리 / 데이터 관리는 admin_data.py에 분리되어 있다.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import psutil
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import approval
import llm_explainer
from db import get_connection
from responses import make_response as _response
from env_utils import update_env

router = APIRouter(prefix="/admin", tags=["admin"])

MODELING_AGENT_URL = os.getenv("MODELING_AGENT_URL", "http://modeling-agent:8011")

# Phase 6: 누적 실험 건수가 마지막 학습 대비 이 값 이상 늘어나면 자동 재학습 트리거
AUTO_RETRAIN_THRESHOLD = int(os.getenv("AUTO_RETRAIN_THRESHOLD", 50))


class OperatorRequest(BaseModel):
    """감사 로그에 남길 운영자 정보를 포함하는 공통 요청 베이스"""
    operator_name: str = "admin"


# ------------------------------------------------------------
# [시스템 상태]
# ------------------------------------------------------------
# (이름, 헬스체크 URL 또는 None(TCP 체크), 표시용 포트)
SERVICES = {
    "data-prep-agent": ("http://data-prep-agent:8010/health", 8010),
    "modeling-agent": ("http://modeling-agent:8011/health", 8011),
    "influxdb": ("http://influxdb:8086/health", 8086),
    "mlflow": ("http://mlflow:5000/health", 5000),
    "grafana": ("http://grafana:3000/api/health", 3010),
    "kafka": (None, 9092),
}


def _check_http(url: str):
    start = time.time()
    try:
        resp = requests.get(url, timeout=3)
        latency = round((time.time() - start) * 1000, 1)
        return ("ok" if resp.status_code < 500 else "degraded"), latency
    except requests.RequestException:
        return "down", None


def _check_tcp(host: str, port: int):
    import socket

    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
        return "ok", round((time.time() - start) * 1000, 1)
    except OSError:
        return "down", None


@router.get("/health")
def admin_health():
    """data-prep/modeling/InfluxDB/MLflow/Grafana/Kafka 헬스체크를 병렬 실행한다"""
    results = {}
    with ThreadPoolExecutor(max_workers=len(SERVICES)) as executor:
        futures = {}
        for name, (url, _port) in SERVICES.items():
            if url:
                futures[executor.submit(_check_http, url)] = name
            else:
                futures[executor.submit(_check_tcp, name, SERVICES[name][1])] = name

        for future, name in futures.items():
            results[name] = future.result()

    services = [
        {"name": name, "port": port, "status": results[name][0], "latency_ms": results[name][1]}
        for name, (_url, port) in SERVICES.items()
    ]
    return _response(True, {"services": services}, "헬스체크 완료")


@router.get("/system-metrics")
def system_metrics():
    """CPU/RAM/Disk + LLM 설정값 + model_metrics 최신값을 조회한다"""
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT kerf_r2, depth_r2, quality_f1_macro, quality_accuracy, trained_at
                FROM model_metrics ORDER BY trained_at DESC LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()

    model_metrics = None
    if row:
        model_metrics = {
            "kerf_r2": float(row[0]) if row[0] is not None else None,
            "depth_r2": float(row[1]) if row[1] is not None else None,
            "quality_f1_macro": float(row[2]) if row[2] is not None else None,
            "quality_accuracy": float(row[3]) if row[3] is not None else None,
            "trained_at": row[4].isoformat() if row[4] else None,
        }

    return _response(
        True,
        {
            "cpu": cpu,
            "ram_used_gb": round(mem.used / 1e9, 2),
            "ram_total_gb": round(mem.total / 1e9, 2),
            "disk_used_gb": round(disk.used / 1e9, 2),
            "disk_total_gb": round(disk.total / 1e9, 2),
            "llm_provider": llm_explainer._STATE["provider"],
            "llm_model": llm_explainer._STATE["model"],
            "model_metrics": model_metrics,
        },
        "시스템 메트릭 조회 완료",
    )


# ------------------------------------------------------------
# [LLM 관리]
# ------------------------------------------------------------
API_MODELS = {
    "claude": ["claude-sonnet-4-6"],
    "openai": ["gpt-4o", "gpt-4o-mini"],
}


@router.get("/llm/available-models")
def llm_available_models():
    """ollama list (API) 결과 + API 모델 고정 목록을 반환한다"""
    ollama_models = []
    base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        ollama_models = [m["name"] for m in resp.json().get("models", [])]
    except requests.RequestException:
        pass

    return _response(True, {"ollama": ollama_models, "api": API_MODELS}, "사용 가능한 모델 조회 완료")


class LlmSwitchRequest(OperatorRequest):
    provider: str
    model: str


@router.post("/llm/switch")
def llm_switch(req: LlmSwitchRequest):
    """LLM 프로바이더/모델을 재시작 없이 전환하고 .env에 반영한다"""
    old_provider = llm_explainer._STATE["provider"]
    old_model = llm_explainer._STATE["model"]

    updates = {"LLM_PROVIDER": req.provider}
    if req.provider == "ollama":
        updates["OLLAMA_MODEL"] = req.model
    update_env(updates)

    llm_explainer.reinitialize(req.provider, req.model)

    approval.log_audit(
        action_type="llm_change",
        operator=req.operator_name,
        description=f"LLM 전환: {old_provider}/{old_model} -> {req.provider}/{req.model}",
        old_value={"provider": old_provider, "model": old_model},
        new_value={"provider": req.provider, "model": req.model},
    )

    return _response(True, {"provider": req.provider, "model": req.model}, "LLM 전환 완료")


@router.post("/llm/test")
def llm_test():
    """현재 설정된 LLM에 테스트 프롬프트를 전송하고 응답시간을 측정한다"""
    prompt = "한국어로 '연결 테스트 성공'이라고만 답하세요"
    provider = llm_explainer._STATE["provider"]

    start = time.time()
    try:
        if provider == "ollama":
            response = llm_explainer._call_ollama(prompt)
        elif provider == "claude":
            response = llm_explainer._call_claude(prompt)
        elif provider == "openai":
            response = llm_explainer._call_openai(prompt)
        else:
            raise ValueError(f"알 수 없는 LLM_PROVIDER: {provider}")
        latency_ms = round((time.time() - start) * 1000, 1)
        return _response(True, {"success": True, "response": response, "latency_ms": latency_ms}, "LLM 테스트 완료")
    except Exception as exc:
        latency_ms = round((time.time() - start) * 1000, 1)
        return _response(True, {"success": False, "response": str(exc), "latency_ms": latency_ms}, "LLM 테스트 실패")


# ------------------------------------------------------------
# [모델 재학습]
# ------------------------------------------------------------
RETRAIN_STATUS = {
    "status": "idle",
    "progress": 0,
    "started_at": None,
    "finished_at": None,
    "result": None,  # "success" | "failed" | None
    "error": None,
    "metrics": None,
}


def _run_retrain():
    RETRAIN_STATUS.update({
        "status": "running",
        "progress": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
        "error": None,
        "metrics": None,
    })
    try:
        resp = requests.post(f"{MODELING_AGENT_URL}/model/train", timeout=1800)
        resp.raise_for_status()
        body = resp.json()
        RETRAIN_STATUS.update({
            "status": "idle",
            "progress": 100,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "result": "success",
            "metrics": body.get("data", {}).get("metrics"),
        })
    except requests.RequestException as exc:
        detail = str(exc)
        if exc.response is not None:
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
        RETRAIN_STATUS.update({
            "status": "idle",
            "progress": 0,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "result": "failed",
            "error": detail,
        })


@router.post("/model/retrain", status_code=202)
def model_retrain(req: OperatorRequest):
    """modeling-agent /model/train을 비동기로 호출하고 즉시 202를 반환한다"""
    if RETRAIN_STATUS["status"] == "running":
        raise HTTPException(status_code=409, detail="이미 재학습이 진행 중입니다")

    threading.Thread(target=_run_retrain, daemon=True).start()

    approval.log_audit(action_type="retrain", operator=req.operator_name, description="모델 재학습 시작")

    return _response(True, {"status": "running"}, "재학습이 시작되었습니다")


@router.get("/model/retrain-status")
def model_retrain_status():
    """모델 재학습 진행 상태를 조회한다"""
    return _response(True, RETRAIN_STATUS, "재학습 상태 조회 완료")


def check_and_trigger_retrain() -> dict:
    """
    experiments 누적 건수가 마지막 학습 시점보다 AUTO_RETRAIN_THRESHOLD 이상 늘었으면
    자동으로 재학습을 트리거한다 (Phase 6).

    Returns:
        {"triggered": bool, "current_count": int, "last_trained_count": int, "threshold": int}
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM experiments")
            current_count = cur.fetchone()[0]

            cur.execute(
                "SELECT n_experiments FROM model_metrics ORDER BY trained_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            last_trained_count = row[0] if row and row[0] is not None else 0
    finally:
        conn.close()

    triggered = False
    if (
        current_count - last_trained_count >= AUTO_RETRAIN_THRESHOLD
        and RETRAIN_STATUS["status"] != "running"
    ):
        threading.Thread(target=_run_retrain, daemon=True).start()
        approval.log_audit(
            action_type="retrain",
            operator="system(auto)",
            description=(
                f"[자동 재학습] 누적 실험 {current_count}건 "
                f"(마지막 학습 {last_trained_count}건 대비 +{current_count - last_trained_count}건, "
                f"기준 {AUTO_RETRAIN_THRESHOLD}건)"
            ),
        )
        triggered = True

    return {
        "triggered": triggered,
        "current_count": current_count,
        "last_trained_count": last_trained_count,
        "threshold": AUTO_RETRAIN_THRESHOLD,
    }


@router.post("/model/check-auto-retrain")
def check_auto_retrain():
    """
    experiments 누적 건수를 확인하여 기준(AUTO_RETRAIN_THRESHOLD) 초과 시 자동 재학습을 트리거한다 (Phase 6).
    데이터 업로드(/data/upload, /data/plasma/upload)나 Auto DOE 결과 저장(/doe/result) 후 호출된다.
    """
    return _response(True, check_and_trigger_retrain(), "자동 재학습 조건 확인 완료")


# ------------------------------------------------------------
# [설정 관리]
# ------------------------------------------------------------
class QualityCriteriaRequest(OperatorRequest):
    depth_ok_min: float
    depth_ok_max: float


@router.patch("/settings/quality-criteria")
def update_quality_criteria(req: QualityCriteriaRequest):
    """품질 판정 기준(DEPTH_OK_MIN/MAX)을 변경하고 즉시 반영한다"""
    old_value = {
        "depth_ok_min": float(os.getenv("DEPTH_OK_MIN", 0.0)),
        "depth_ok_max": float(os.getenv("DEPTH_OK_MAX", 25.0)),
    }
    new_value = {"depth_ok_min": req.depth_ok_min, "depth_ok_max": req.depth_ok_max}

    update_env({"DEPTH_OK_MIN": str(req.depth_ok_min), "DEPTH_OK_MAX": str(req.depth_ok_max)})

    approval.log_audit(
        action_type="setting_change",
        operator=req.operator_name,
        description="품질 판정 기준 변경",
        old_value=old_value,
        new_value=new_value,
    )

    return _response(True, new_value, "품질 판정 기준이 변경되었습니다")


class SearchSpaceRequest(OperatorRequest):
    power_min: float | None = None
    power_max: float | None = None
    speed_values: list[float] | None = None
    defocus_values: list[float] | None = None


@router.patch("/settings/search-space")
def update_search_space(req: SearchSpaceRequest):
    """Auto DOE 탐색 공간을 변경한다 (다음 /doe/suggest 호출부터 즉시 반영)"""
    updates = {}
    old_value = {}
    new_value = {}

    if req.power_min is not None:
        old_value["power_min"] = float(os.getenv("SEARCH_SPACE_POWER_MIN", 2.8))
        updates["SEARCH_SPACE_POWER_MIN"] = str(req.power_min)
        new_value["power_min"] = req.power_min
    if req.power_max is not None:
        old_value["power_max"] = float(os.getenv("SEARCH_SPACE_POWER_MAX", 59.8))
        updates["SEARCH_SPACE_POWER_MAX"] = str(req.power_max)
        new_value["power_max"] = req.power_max
    if req.speed_values is not None:
        old_value["speed_values"] = os.getenv("SEARCH_SPACE_SPEED")
        updates["SEARCH_SPACE_SPEED"] = ",".join(str(v) for v in req.speed_values)
        new_value["speed_values"] = req.speed_values
    if req.defocus_values is not None:
        old_value["defocus_values"] = os.getenv("SEARCH_SPACE_DEFOCUS")
        updates["SEARCH_SPACE_DEFOCUS"] = ",".join(str(v) for v in req.defocus_values)
        new_value["defocus_values"] = req.defocus_values

    if not updates:
        raise HTTPException(status_code=400, detail="변경할 값이 없습니다")

    update_env(updates)

    approval.log_audit(
        action_type="setting_change",
        operator=req.operator_name,
        description="Auto DOE 탐색 공간 변경",
        old_value=old_value,
        new_value=new_value,
    )

    return _response(
        True,
        {
            "speed_values": [float(v) for v in os.getenv("SEARCH_SPACE_SPEED", "200,500,1000").split(",")],
            "defocus_values": [float(v) for v in os.getenv("SEARCH_SPACE_DEFOCUS", "0,1,2,3,4").split(",")],
            "power_min": float(os.getenv("SEARCH_SPACE_POWER_MIN", 2.8)),
            "power_max": float(os.getenv("SEARCH_SPACE_POWER_MAX", 59.8)),
        },
        "탐색 공간이 변경되었습니다",
    )


# ------------------------------------------------------------
# [사용자 관리]
# ------------------------------------------------------------
import hashlib  # noqa: E402


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@router.get("/users")
def list_users():
    """사용자 목록을 조회한다"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, role, created_at FROM users ORDER BY id")
            rows = cur.fetchall()
    finally:
        conn.close()

    users = [{"id": r[0], "name": r[1], "role": r[2], "created_at": r[3].isoformat()} for r in rows]
    return _response(True, {"users": users, "total": len(users)}, "사용자 목록 조회 완료")


class UserCreateRequest(BaseModel):
    name: str
    role: str = "operator"
    password: str


@router.post("/users")
def create_user(req: UserCreateRequest):
    """사용자를 생성한다"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (name, role, password_hash) VALUES (%s, %s, %s) RETURNING id, created_at",
                (req.name, req.role, _hash_password(req.password)),
            )
            user_id, created_at = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    return _response(
        True,
        {"id": user_id, "name": req.name, "role": req.role, "created_at": created_at.isoformat()},
        "사용자 생성 완료",
    )


class UserUpdateRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    password: str | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: int, req: UserUpdateRequest):
    """사용자 정보를 수정한다 (이름/역할/비밀번호)"""
    set_clauses = []
    values = []
    if req.name is not None:
        set_clauses.append("name = %s")
        values.append(req.name)
    if req.role is not None:
        set_clauses.append("role = %s")
        values.append(req.role)
    if req.password is not None:
        set_clauses.append("password_hash = %s")
        values.append(_hash_password(req.password))

    if not set_clauses:
        raise HTTPException(status_code=400, detail="변경할 값이 없습니다")

    values.append(user_id)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s RETURNING id", values)
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        conn.commit()
    finally:
        conn.close()

    return _response(True, {"id": user_id}, "사용자 정보가 수정되었습니다")


# ------------------------------------------------------------
# [알림 설정]
# ------------------------------------------------------------
_NOTIFICATION_DEFAULTS = {
    "email": None,
    "slack_webhook": None,
    "notify_on_ok": True,
    "notify_on_failure": True,
    "notify_on_model_degradation": True,
}


@router.get("/notifications/settings")
def get_notification_settings():
    """알림 설정을 조회한다 (행이 없으면 기본값 반환)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT email, slack_webhook, notify_on_ok, notify_on_failure, notify_on_model_degradation
                FROM notification_settings ORDER BY id LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        return _response(True, _NOTIFICATION_DEFAULTS, "알림 설정 조회 완료 (기본값)")

    return _response(
        True,
        {
            "email": row[0],
            "slack_webhook": row[1],
            "notify_on_ok": row[2],
            "notify_on_failure": row[3],
            "notify_on_model_degradation": row[4],
        },
        "알림 설정 조회 완료",
    )


class NotificationSettingsRequest(BaseModel):
    email: str | None = None
    slack_webhook: str | None = None
    notify_on_ok: bool | None = None
    notify_on_failure: bool | None = None
    notify_on_model_degradation: bool | None = None


@router.patch("/notifications/settings")
def update_notification_settings(req: NotificationSettingsRequest):
    """알림 설정을 갱신한다 (행이 없으면 새로 생성)"""
    payload = req.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="변경할 값이 없습니다")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM notification_settings ORDER BY id LIMIT 1")
            row = cur.fetchone()

            if row is None:
                merged = {**_NOTIFICATION_DEFAULTS, **payload}
                cur.execute(
                    """
                    INSERT INTO notification_settings
                        (email, slack_webhook, notify_on_ok, notify_on_failure, notify_on_model_degradation)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        merged["email"], merged["slack_webhook"], merged["notify_on_ok"],
                        merged["notify_on_failure"], merged["notify_on_model_degradation"],
                    ),
                )
            else:
                set_clauses = [f"{key} = %s" for key in payload]
                values = list(payload.values()) + [row[0]]
                cur.execute(
                    f"UPDATE notification_settings SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = %s",
                    values,
                )
        conn.commit()
    finally:
        conn.close()

    return _response(True, payload, "알림 설정이 변경되었습니다")


@router.post("/notifications/test")
def test_notifications():
    """이메일/Slack 테스트 알림을 발송한다"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email, slack_webhook FROM notification_settings ORDER BY id LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()

    email, slack_webhook = (row[0], row[1]) if row else (None, None)
    results = {}

    if slack_webhook:
        try:
            resp = requests.post(slack_webhook, json={"text": "[AI-ADES] 알림 테스트 메시지입니다."}, timeout=5)
            results["slack"] = "성공" if resp.ok else f"실패 (HTTP {resp.status_code})"
        except requests.RequestException as exc:
            results["slack"] = f"실패 ({exc})"
    else:
        results["slack"] = "미설정"

    if email:
        results["email"] = "이메일 주소는 설정되어 있으나 SMTP 연동이 구현되지 않았습니다"
    else:
        results["email"] = "미설정"

    return _response(True, results, "알림 테스트 완료")
