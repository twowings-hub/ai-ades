"""
AI-ADES Execution Agent — .env 파일 런타임 갱신 유틸리티 (Phase 4 Admin Console)

LLM 전환 / 판정 기준 변경 / 탐색 공간 변경 시
.env 파일에 반영하고 os.environ에도 즉시 반영해 재시작 없이 동작하도록 한다.
"""
import os

# 컨테이너 환경에서는 docker-compose.yml에서 ./.env -> /app/.env로 마운트되어야
# 변경 사항이 호스트 .env 파일에 영구 반영된다 (마운트 없으면 컨테이너 내부 사본만 갱신됨).
_CANDIDATES = [
    os.getenv("ENV_FILE_PATH"),
    "/app/.env",
    os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]


def _resolve_env_path() -> str:
    for path in _CANDIDATES:
        if path and os.path.exists(path):
            return path
    # 어디에도 없으면 마지막 후보 경로에 새로 생성
    return _CANDIDATES[-1]


def update_env(updates: dict):
    """.env 파일의 KEY=VALUE를 갱신하고 os.environ에도 즉시 반영한다."""
    env_path = _resolve_env_path()

    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    keys_remaining = set(updates.keys())
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                keys_remaining.discard(key)
                continue
        new_lines.append(line)

    for key in keys_remaining:
        new_lines.append(f"{key}={updates[key]}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    for key, value in updates.items():
        os.environ[key] = str(value)
