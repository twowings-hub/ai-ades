# 포트 점유 현황

`docker-compose.yml` 기준, rag-pm-matcher가 점유하는 전체 포트 목록.

## 호스트 포트 (외부 노출)

| 호스트 포트 | 컨테이너 | 컨테이너 내부 포트 | 설명 |
|---|---|---|---|
| 80 | nginx | 80 | 리버스 프록시 (443은 TLS 적용 시 주석 해제) |
| 8000 | vllm | 8000 | Surface 환경에서 `gpu` profile로 비활성 |
| 11434 | ollama | 11434 | CI Assistant + PM Matcher 공유 |
| 3001 | open-webui | 8080 | |
| 3000 | gitea | 3000 | HTTP |
| 2222 | gitea | 22 | SSH |
| 6333 | qdrant | 6333 | 벡터 DB (`profiles` 컬렉션) |
| 8080 | admin-api | 8080 | 기존 admin-api — **변경 금지** |
| 9090 | prometheus | 9090 | |
| 3002 | grafana | 3000 | |
| 3003 | pm-ui | 80 | 직접 접근용 (개발 확인) |

## 내부 전용 포트 (호스트 미노출)

| 포트 | 서비스 | 설명 |
|---|---|---|
| 8001 | pm-api | 신규 PM Matcher API (CLAUDE.md 규정) |
| 5432 | postgres | PM Matcher 전용 DB (`pmdb`, `openwebui`) |
| 6379 | redis | (기본 포트, Celery 브로커 추정) |

pm-worker, libreoffice는 노출 포트 없음.

## 요약

- **호스트 직접 점유**: 80, 2222, 3000, 3001, 3002, 3003, 6333, 8000, 8080, 9090, 11434
- **컨테이너 네트워크 내부 전용**: 5432, 6379, 8001
