"""
AI-ADES Execution Agent — 공통 API 응답 포맷
"""


def make_response(success: bool, data=None, message: str = ""):
    """API 응답 형식 통일"""
    return {"success": success, "data": data, "message": message}
