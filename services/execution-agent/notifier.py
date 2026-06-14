"""
AI-ADES Execution Agent — 자동 알림 공통 모듈 (Phase 4)

폐쇄망(외부 접속 불가) 환경 기준 설계:
- 모든 알림 이벤트는 notifications 테이블에 기록한다(Grafana 알림판이 이 테이블을 읽음).
- 메일은 사내 SMTP 서버(.env의 SMTP_*)로만 발송한다. 설정이 없으면 조용히 건너뛴다.
- 발송 실패가 호출부(예: /doe/result 결과 저장)를 깨지 않도록 절대 예외를 던지지 않는다.

이벤트 종류(event_type): 'ok' / 'failure' / 'model_degradation'
각 이벤트는 notification_settings의 플래그(notify_on_*)로 on/off 한다.
"""
import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from db import get_connection

# 이벤트 종류 → notification_settings 플래그 컬럼 매핑
_EVENT_FLAG = {
    "ok": "notify_on_ok",
    "failure": "notify_on_failure",
    "model_degradation": "notify_on_model_degradation",
}


def _load_settings() -> dict:
    """알림 설정(수신 메일/플래그/SMTP 서버)을 조회한다. 없으면 기본값(모두 on)."""
    defaults = {
        "email": None,
        "slack_webhook": None,
        "notify_on_ok": True,
        "notify_on_failure": True,
        "notify_on_model_degradation": True,
        "smtp_host": None,
        "smtp_port": None,
        "smtp_user": None,
        "smtp_password": None,
        "smtp_from": None,
        "smtp_use_tls": None,
    }
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT email, slack_webhook, notify_on_ok,
                           notify_on_failure, notify_on_model_degradation,
                           smtp_host, smtp_port, smtp_user, smtp_password,
                           smtp_from, smtp_use_tls
                    FROM notification_settings ORDER BY id LIMIT 1
                    """
                )
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return defaults

    if not row:
        return defaults
    return {
        "email": row[0],
        "slack_webhook": row[1],
        "notify_on_ok": row[2],
        "notify_on_failure": row[3],
        "notify_on_model_degradation": row[4],
        "smtp_host": row[5],
        "smtp_port": row[6],
        "smtp_user": row[7],
        "smtp_password": row[8],
        "smtp_from": row[9],
        "smtp_use_tls": row[10],
    }


def _resolve_smtp(settings: dict) -> dict | None:
    """
    SMTP 접속 설정을 결정한다: DB(관리자 콘솔 설정)가 있으면 우선, 없으면 .env(SMTP_*) 폴백.
    SMTP_HOST가 어디에도 없으면 None을 반환한다(메일 발송 건너뜀).
    """
    host = settings.get("smtp_host") or os.getenv("SMTP_HOST")
    if not host:
        return None

    # DB에 host가 지정된 경우 DB 값을 우선, 아니면 env 값을 사용
    from_db = bool(settings.get("smtp_host"))

    def pick(db_val, env_key, default=None):
        if from_db:
            return db_val if db_val not in (None, "") else default
        return os.getenv(env_key, default)

    port = pick(settings.get("smtp_port"), "SMTP_PORT", "25")
    use_tls_raw = settings.get("smtp_use_tls") if from_db else os.getenv("SMTP_USE_TLS", "false")
    use_tls = use_tls_raw in (True, "1", "true", "True", "yes") if from_db else str(use_tls_raw).lower() in ("1", "true", "yes")

    return {
        "host": host,
        "port": int(port or 25),
        "user": pick(settings.get("smtp_user"), "SMTP_USER") or None,
        "password": pick(settings.get("smtp_password"), "SMTP_PASSWORD") or None,
        "sender": pick(settings.get("smtp_from"), "SMTP_FROM") or settings.get("smtp_user") or "ai-ades@localhost",
        "use_tls": use_tls,
        "timeout": int(os.getenv("SMTP_TIMEOUT", "5")),
    }


def send_email(to_addr: str, subject: str, body: str, settings: dict | None = None) -> str:
    """
    사내 SMTP 서버로 메일을 발송한다. 접속 설정은 DB(관리자 콘솔) 우선, .env 폴백.
    반환값: 'sent' | '미설정' | '실패 (사유)' — 절대 예외를 던지지 않는다.
    """
    if settings is None:
        settings = _load_settings()
    cfg = _resolve_smtp(settings)
    if cfg is None:
        # 사내 SMTP가 구성되지 않음 → 조용히 건너뜀 (폐쇄망에서 정상 상황)
        return "미설정 (SMTP 서버 없음)"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = cfg["sender"]
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=cfg["timeout"]) as server:
            if cfg["use_tls"]:
                server.starttls()
            if cfg["user"] and cfg["password"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["sender"], [to_addr], msg.as_string())
        return "sent"
    except Exception as exc:
        return f"실패 ({exc})"


def _insert_log(event_type: str, quality, exp_no, message: str, email_status: str):
    """알림 이벤트를 notifications 테이블에 기록한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notifications (event_type, quality, exp_no, message, email_status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (event_type, quality, exp_no, message, email_status),
            )
        conn.commit()
    finally:
        conn.close()


def notify(event_type: str, message: str, *, quality=None, exp_no=None) -> str:
    """
    알림 이벤트를 처리한다: 플래그 확인 → (켜져 있으면) 메일 발송 + DB 기록.
    절대 예외를 던지지 않는다(호출부 트랜잭션 보호). 발송 결과 문자열을 반환한다.
    """
    try:
        settings = _load_settings()
        flag = _EVENT_FLAG.get(event_type)
        # 해당 이벤트 알림이 꺼져 있으면 아무것도 하지 않는다
        if flag and not settings.get(flag, True):
            return "skipped (알림 꺼짐)"

        email = settings.get("email")
        if email:
            subject = f"[AI-ADES] {_event_label(event_type)}"
            email_status = send_email(email, subject, message, settings)
        else:
            email_status = "미설정 (수신 메일 없음)"

        _insert_log(event_type, quality, exp_no, message, email_status)
        return email_status
    except Exception as exc:
        # 알림 자체의 실패는 삼킨다 (로그만 남기고 호출부에 영향 주지 않음)
        print(f"[notifier] 알림 처리 실패: {exc}")
        return f"실패 ({exc})"


def _event_label(event_type: str) -> str:
    return {
        "ok": "OK 판정 알림",
        "failure": "가공 실패 알림",
        "model_degradation": "모델 성능 저하 알림",
    }.get(event_type, "알림")
