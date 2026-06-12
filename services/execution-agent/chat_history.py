"""
AI-ADES Execution Agent — AI 채팅 이력 관리

채팅 세션(chat_sessions)과 메시지(chat_messages)를 DB에 저장/조회한다.
운영자가 좌측 이력 목록에서 과거 대화를 선택해 이어볼 수 있도록 지원한다.
"""
from db import get_connection

# 세션 제목으로 사용할 첫 질문의 최대 길이
TITLE_MAX_LENGTH = 40


def _make_title(message: str) -> str:
    """첫 질문 메시지로 세션 제목을 만든다 (너무 길면 잘라서 ... 추가)."""
    message = message.strip().replace("\n", " ")
    if len(message) <= TITLE_MAX_LENGTH:
        return message
    return message[:TITLE_MAX_LENGTH] + "..."


def create_session(first_message: str) -> int:
    """첫 질문을 기반으로 새 채팅 세션을 생성하고 id를 반환한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_sessions (title) VALUES (%s) RETURNING id",
                (_make_title(first_message),),
            )
            session_id = cur.fetchone()[0]
        conn.commit()
        return session_id
    finally:
        conn.close()


def touch_session(session_id: int):
    """세션의 updated_at을 현재 시각으로 갱신한다 (목록 정렬용)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE chat_sessions SET updated_at = now() WHERE id = %s", (session_id,))
        conn.commit()
    finally:
        conn.close()


def add_message(session_id: int, role: str, content: str, provider: str | None = None):
    """세션에 메시지를 추가한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_messages (session_id, role, content, provider) VALUES (%s, %s, %s, %s)",
                (session_id, role, content, provider),
            )
        conn.commit()
    finally:
        conn.close()


def list_sessions() -> list[dict]:
    """최근 업데이트 순으로 채팅 세션 목록을 반환한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC"
            )
            return [
                {"id": id_, "title": title, "created_at": created_at, "updated_at": updated_at}
                for id_, title, created_at, updated_at in cur.fetchall()
            ]
    finally:
        conn.close()


def get_messages(session_id: int) -> list[dict]:
    """세션에 속한 메시지를 시간순으로 반환한다."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY id",
                (session_id,),
            )
            return [{"role": role, "content": content} for role, content in cur.fetchall()]
    finally:
        conn.close()


def delete_session(session_id: int):
    """채팅 세션과 그에 속한 메시지를 삭제한다 (ON DELETE CASCADE)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
        conn.commit()
    finally:
        conn.close()
