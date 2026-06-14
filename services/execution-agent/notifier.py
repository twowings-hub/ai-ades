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
    """알림 설정(수신 메일/플래그)을 조회한다. 없으면 기본값(모두 on)."""
    defaults = {
        "email": None,
        "slack_webhook": None,
        "notify_on_ok": True,
        "notify_on_failure": True,
        "notify_on_model_degradation": True,
    }
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT email, slack_webhook, notify_on_ok,
                           notify_on_failure, notify_on_model_degradation
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
    }


def send_email(to_addr: str, subject: str, body: str) -> str:
    """
    사내 SMTP 서버로 메일을 발송한다 (.env의 SMTP_* 사용).
    반환값: 'sent' | '미설정' | '실패 (사유)' — 절대 예외를 던지지 않는다.
    """
    host = os.getenv("SMTP_HOST")
    if not host:
        # 사내 SMTP가 구성되지 않음 → 조용히 건너뜀 (폐쇄망에서 정상 상황)
        return "미설정 (SMTP_HOST 없음)"

    port = int(os.getenv("SMTP_PORT", "25"))
    user = os.getenv("SMTP_USER") or None
    password = os.getenv("SMTP_PASSWORD") or None
    sender = os.getenv("SMTP_FROM") or user or "ai-ades@localhost"
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() in ("1", "true", "yes")
    timeout = int(os.getenv("SMTP_TIMEOUT", "5"))

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = sender
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(sender, [to_addr], msg.as_string())
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
            email_status = send_email(email, subject, message)
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
