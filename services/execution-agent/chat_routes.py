"""
AI-ADES Execution Agent — AI 채팅 / 채팅 이력 API

실험 이력/레시피 등 시스템 데이터를 컨텍스트로 사용해 운영자의 질문에 답변하고,
대화를 세션 단위로 저장/조회/삭제할 수 있는 엔드포인트를 제공한다.
"""
from fastapi import APIRouter
from pydantic import BaseModel

import chat_history
from chat import generate_chat_reply
from responses import make_response as _response

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: int | None = None  # 없으면 새 세션 생성
    message: str
    provider: str | None = None  # "ollama" | "claude" | "openai" (지정 시 CHAT_LLM_PROVIDER 설정 대신 사용)


@router.post("")
def chat(req: ChatRequest):
    """실험 이력/레시피 데이터를 컨텍스트로 사용해 운영자의 질문에 AI가 답변한다 (세션 단위로 이력 저장)."""
    session_id = req.session_id
    if session_id is None:
        session_id = chat_history.create_session(req.message)
        history = []
    else:
        history = chat_history.get_messages(session_id)

    chat_history.add_message(session_id, "user", req.message)

    reply = generate_chat_reply(history, req.message, provider=req.provider)
    if reply is None:
        return _response(False, None, "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요.")

    chat_history.add_message(session_id, "assistant", reply, provider=req.provider)
    chat_history.touch_session(session_id)

    return _response(True, {"session_id": session_id, "reply": reply}, "응답 생성 완료")


@router.get("/sessions")
def list_chat_sessions():
    """채팅 이력 목록을 최근 순으로 조회한다."""
    return _response(True, {"sessions": chat_history.list_sessions()}, "채팅 이력 조회 완료")


@router.get("/sessions/{session_id}")
def get_chat_session(session_id: int):
    """특정 채팅 세션의 메시지 전체를 조회한다."""
    return _response(True, {"messages": chat_history.get_messages(session_id)}, "채팅 메시지 조회 완료")


@router.delete("/sessions/{session_id}")
def delete_chat_session(session_id: int):
    """채팅 세션을 삭제한다."""
    chat_history.delete_session(session_id)
    return _response(True, None, "채팅 이력 삭제 완료")
